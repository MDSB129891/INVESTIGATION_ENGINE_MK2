#!/usr/bin/env python3
import os
import sys
from pathlib import Path

# Make project root importable when running from scripts/
sys.path.append(str(Path(__file__).resolve().parents[1]))

import json
import re
import shutil
from dataclasses import dataclass
from datetime import date, datetime, timezone, timedelta
from typing import Dict
from urllib.parse import urlencode, urlparse, parse_qsl, urlunparse

import pandas as pd
from analytics.provider_net import request_with_resilience, provider_circuit_status, provider_timeout

from analytics.fmp_pull import (
    fetch_quote,
    fetch_quotes,
    fetch_income_statement,
    fetch_cashflow_statement,
    fetch_balance_sheet,
)

from analytics.news.pipeline import run_news_pipeline, summarize_news_for_scoring
from analytics.news.sentiment_proxy import build_news_sentiment_proxy
from analytics.news.risk_dashboard import build_news_risk_dashboard
from analytics.news.evidence import build_evidence_table, write_evidence_html

# ---- Runtime universe config (CLI/env driven; no hardcoded ticker default) ----
def _arg_value(flag: str) -> str:
    try:
        if flag in sys.argv:
            i = sys.argv.index(flag)
            if i + 1 < len(sys.argv):
                return str(sys.argv[i + 1]).strip()
    except Exception:
        pass
    return ""


CLI_TICKER = _arg_value("--ticker")
CLI_PEERS = _arg_value("--peers")
CLI_UNIVERSE = _arg_value("--universe")

TICKER = (CLI_TICKER or os.getenv("TICKER", "")).strip().upper()
if not TICKER:
    raise SystemExit("Missing ticker. Pass --ticker <TICKER> or set TICKER in environment.")

def _default_peers_for_ticker(ticker: str) -> str:
    t = (ticker or "").upper()
    mapping = {
        "GM": "F,TM",
        "F": "GM,TM",
        "TM": "GM,F",
        "TSLA": "GM,F",
        "UBER": "LYFT,DASH",
        "LYFT": "UBER,DASH",
        "DASH": "UBER,LYFT",
        "INTC": "AMD,NVDA",
        "AMD": "INTC,NVDA",
        "NVDA": "AMD,INTC",
        "AAPL": "MSFT,GOOGL",
        "MSFT": "AAPL,GOOGL",
        "GOOGL": "MSFT,META",
        "GOOG": "MSFT,META",
        "META": "GOOGL,SNAP",
        "AMZN": "WMT,TGT",
        "WMT": "TGT,COST",
    }
    return mapping.get(t, "SPY")

PEERS_CSV = CLI_PEERS or os.getenv("PEERS", "") or _default_peers_for_ticker(TICKER)
PEERS = [s.strip().upper() for s in PEERS_CSV.split(",") if s.strip()]
UNIVERSE = [TICKER] + [p for p in PEERS if p != TICKER]

# Optional override: --universe or UNIVERSE="AAPL,MSFT,GOOGL"
UNIVERSE_ENV = CLI_UNIVERSE or os.getenv("UNIVERSE", "")
if UNIVERSE_ENV.strip():
    UNIVERSE = [s.strip().upper() for s in UNIVERSE_ENV.split(",") if s.strip()]
# -----------------------------------------------------------
PRIMARY = UNIVERSE[0]  # dynamic primary ticker
AS_OF = date.today().isoformat()

ROOT = Path(__file__).resolve().parents[1]
DATA_RAW = ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"
OUTPUTS = ROOT / "outputs"


# ---------------------------
# IO helpers
# ---------------------------
def ensure_dirs():
    for p in [DATA_RAW, DATA_PROCESSED, DATA_PROCESSED / "last_good", OUTPUTS]:
        p.mkdir(parents=True, exist_ok=True)


def write_csv(df, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def write_json(obj: dict, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)

    def _json_default(x):
        try:
            import numpy as np

            if isinstance(x, (np.integer,)):
                return int(x)
            if isinstance(x, (np.floating,)):
                return float(x)
            if isinstance(x, (np.bool_,)):
                return bool(x)
        except Exception:
            pass

        try:
            import pandas as pd

            if isinstance(x, pd.Timestamp):
                return x.isoformat()
        except Exception:
            pass

        return str(x)

    path.write_text(json.dumps(obj, indent=2, default=_json_default), encoding="utf-8")


def _read_nonempty_csv(path: Path) -> pd.DataFrame:
    try:
        if path.exists() and path.stat().st_size > 1:
            df = pd.read_csv(path)
            if not df.empty:
                return df
    except Exception:
        pass
    return pd.DataFrame()


def _snapshot_last_good_csv(path: Path, stem: str) -> None:
    df = _read_nonempty_csv(path)
    if df.empty:
        return
    lg_dir = DATA_PROCESSED / "last_good"
    lg_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    dated = lg_dir / f"{stem}_{today}.csv"
    latest = lg_dir / f"{stem}_latest.csv"
    shutil.copy2(path, dated)
    shutil.copy2(path, latest)


def _restore_last_good_csv(target_path: Path, stem: str) -> pd.DataFrame:
    latest = DATA_PROCESSED / "last_good" / f"{stem}_latest.csv"
    df = _read_nonempty_csv(latest)
    if df.empty:
        return pd.DataFrame()
    write_csv(df, target_path)
    return df


# ---------------------------
# Utilities
# ---------------------------
def _safe_float(x):
    if x is None:
        return None
    try:
        if isinstance(x, float) and pd.isna(x):
            return None
        return float(x)
    except Exception:
        return None


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _rank_percentile(series: pd.Series, value: float, higher_is_better: bool = True) -> float:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if len(s) == 0 or value is None:
        return None
    pct = (s <= value).mean() * 100.0
    return pct if higher_is_better else 100.0 - pct


def _redact_url(url: str) -> str:
    if not isinstance(url, str):
        return str(url)
    try:
        parsed = urlparse(url)
        sensitive = {
            "apikey",
            "apiKey",
            "token",
            "api_token",
            "auth-token",
            "authorization",
            "x-api-key",
        }
        q = parse_qsl(parsed.query, keep_blank_values=True)
        safe_q = []
        for k, v in q:
            if k in sensitive:
                safe_q.append((k, "***REDACTED***"))
            else:
                safe_q.append((k, v))
        return urlunparse(parsed._replace(query=urlencode(safe_q)))
    except Exception:
        # Last-resort masking for malformed URLs.
        for key in ("apikey=", "apiKey=", "token=", "api_token=", "authorization=", "x-api-key="):
            i = url.find(key)
            if i >= 0:
                j = url.find("&", i)
                if j == -1:
                    j = len(url)
                url = url[: i + len(key)] + "***REDACTED***" + url[j:]
        return url


def _redact_text(text: str) -> str:
    if not isinstance(text, str):
        return str(text)
    # Replace sensitive query values without looping on already-redacted text.
    for key in ("apikey=", "apiKey=", "token=", "api_token=", "authorization=", "x-api-key="):
        pattern = re.compile(re.escape(key) + r"[^&\s]*")
        text = pattern.sub(key + "***REDACTED***", text)
    return text


def _redact_obj(obj):
    if isinstance(obj, dict):
        return {k: _redact_obj(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact_obj(x) for x in obj]
    if isinstance(obj, str):
        return _redact_text(_redact_url(obj))
    return obj


def _check_url(
    name: str,
    base_url: str,
    params: dict,
    timeout: int = 12,
    headers=None,
    provider=None,
) -> dict:
    full = base_url + ("?" + urlencode(params) if params else "")
    if not provider:
        provider = (
            "fmp"
            if "financialmodelingprep.com" in base_url
            else (
                "massive"
                if "polygon.io" in base_url
                else (
                    "yahoo"
                    if "yahoo.com" in base_url
                    else (
                        "finnhub"
                        if "finnhub.io" in base_url
                        else (
                            "sec"
                            if "sec.gov" in base_url
                            else (
                                "tiingo"
                                if "tiingo.com" in base_url
                                else (
                                    "marketaux"
                                    if "marketaux.com" in base_url
                                    else ("alphavantage" if "alphavantage.co" in base_url else "unknown")
                                )
                            )
                        )
                    )
                )
            )
        )
    try:
        r = request_with_resilience(
            provider,
            base_url,
            params=params,
            timeout=timeout,
            max_retries=1,
            headers=headers,
        )
        return {
            "name": name,
            "url": _redact_url(full),
            "ok": 200 <= r.status_code < 300,
            "status_code": r.status_code,
            "error": None,
        }
    except Exception as e:
        return {
            "name": name,
            "url": _redact_url(full),
            "ok": False,
            "status_code": None,
            "error": _redact_text(str(e)),
        }


def _days_old_from_iso(iso_value: str):
    try:
        dt = datetime.fromisoformat(str(iso_value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0)
    except Exception:
        return None


def _freshness_sla_snapshot(primary: str, comps: pd.DataFrame, news_df: pd.DataFrame) -> dict:
    fund_sla_days = int(os.getenv("FRESHNESS_SLA_FUND_DAYS", "140"))
    news_sla_days = int(os.getenv("FRESHNESS_SLA_NEWS_DAYS", "3"))
    quote_sla_days = int(os.getenv("FRESHNESS_SLA_QUOTE_DAYS", "2"))

    primary = (primary or "").upper().strip()
    fund_age_days = None
    quote_age_days = None
    news_age_days = None

    if comps is not None and not comps.empty and "ticker" in comps.columns:
        cc = comps.copy()
        cc["ticker"] = cc["ticker"].astype(str).str.upper()
        rr = cc[cc["ticker"] == primary]
        if not rr.empty:
            p_end = rr.iloc[0].get("period_end")
            if p_end is not None:
                try:
                    dt = pd.to_datetime(p_end, utc=True, errors="coerce")
                    if pd.notna(dt):
                        fund_age_days = max(0.0, (datetime.now(timezone.utc) - dt.to_pydatetime()).total_seconds() / 86400.0)
                except Exception:
                    pass

    q_cache = DATA_RAW / "quotes_universe_raw.csv"
    if q_cache.exists():
        try:
            m = datetime.fromtimestamp(q_cache.stat().st_mtime, tz=timezone.utc)
            quote_age_days = max(0.0, (datetime.now(timezone.utc) - m).total_seconds() / 86400.0)
        except Exception:
            pass

    if news_df is not None and not news_df.empty and "ticker" in news_df.columns and "published_at" in news_df.columns:
        n = news_df.copy()
        n["ticker"] = n["ticker"].astype(str).str.upper()
        nr = n[n["ticker"] == primary]
        if not nr.empty:
            try:
                dt = pd.to_datetime(nr["published_at"], utc=True, errors="coerce").max()
                if pd.notna(dt):
                    news_age_days = max(0.0, (datetime.now(timezone.utc) - dt.to_pydatetime()).total_seconds() / 86400.0)
            except Exception:
                pass

    fund_ok = (fund_age_days is not None) and (fund_age_days <= fund_sla_days)
    news_ok = (news_age_days is not None) and (news_age_days <= news_sla_days)
    quote_ok = (quote_age_days is not None) and (quote_age_days <= quote_sla_days)
    all_ok = fund_ok and news_ok and quote_ok

    return {
        "passed": bool(all_ok),
        "sla_days": {
            "fundamentals": fund_sla_days,
            "news": news_sla_days,
            "quotes": quote_sla_days,
        },
        "ages_days": {
            "fundamentals": fund_age_days,
            "news": news_age_days,
            "quotes": quote_age_days,
        },
        "checks": {
            "fundamentals": fund_ok,
            "news": news_ok,
            "quotes": quote_ok,
        },
    }


def _crosscheck_fmp_vs_massive(primary: str, fmp_key: str, massive_key: str) -> dict:
    out = {
        "enabled": bool(fmp_key and massive_key),
        "fmp": {"price": None, "market_cap": None},
        "massive": {"price": None, "market_cap": None},
        "variance_pct": {"price": None, "market_cap": None},
        "alerts": [],
    }
    if not out["enabled"]:
        return out

    t = (primary or "").upper().strip()
    try:
        fq = fetch_quote(t)
        if not fq.empty:
            out["fmp"]["price"] = _safe_float(fq.iloc[0].get("price"))
            out["fmp"]["market_cap"] = _safe_float(fq.iloc[0].get("marketCap"))
    except Exception as e:
        out["alerts"].append(f"FMP cross-check fetch failed: {e}")

    try:
        mq = _fetch_quotes_massive([t], massive_key)
        if not mq.empty:
            out["massive"]["price"] = _safe_float(mq.iloc[0].get("price"))
            out["massive"]["market_cap"] = _safe_float(mq.iloc[0].get("marketCap"))
    except Exception as e:
        out["alerts"].append(f"Massive cross-check fetch failed: {e}")

    def _var_pct(a, b):
        if a is None or b is None:
            return None
        if a == 0 and b == 0:
            return 0.0
        den = max(abs(float(a)), abs(float(b)), 1e-9)
        return abs(float(a) - float(b)) / den * 100.0

    p_var = _var_pct(out["fmp"]["price"], out["massive"]["price"])
    m_var = _var_pct(out["fmp"]["market_cap"], out["massive"]["market_cap"])
    out["variance_pct"]["price"] = p_var
    out["variance_pct"]["market_cap"] = m_var

    if p_var is None:
        out["alerts"].append(
            "Price variance unavailable: one side is missing price "
            f"(fmp={out['fmp']['price']}, massive={out['massive']['price']})."
        )
    if m_var is None:
        out["alerts"].append(
            "Market cap variance unavailable: one side is missing market cap "
            f"(fmp={out['fmp']['market_cap']}, massive={out['massive']['market_cap']})."
        )

    price_alert_threshold = float(os.getenv("CROSSCHECK_PRICE_VAR_ALERT_PCT", "2.0"))
    mcap_alert_threshold = float(os.getenv("CROSSCHECK_MCAP_VAR_ALERT_PCT", "8.0"))
    if p_var is not None and p_var > price_alert_threshold:
        out["alerts"].append(
            f"Price variance high between FMP and Massive: {p_var:.2f}% (> {price_alert_threshold:.2f}%)"
        )
    if m_var is not None and m_var > mcap_alert_threshold:
        out["alerts"].append(
            f"Market cap variance high between FMP and Massive: {m_var:.2f}% (> {mcap_alert_threshold:.2f}%)"
        )
    return out


def _fetch_quotes_massive(tickers: list[str], api_key: str, timeout: int = 12) -> pd.DataFrame:
    rows = []
    if not api_key:
        return pd.DataFrame()
    for t in tickers:
        tk = str(t).upper().strip()
        if not tk:
            continue
        price = None
        mcap = None
        try:
            snap_url = f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers/{tk}"
            rs = request_with_resilience("massive", snap_url, params={"apiKey": api_key}, timeout=timeout, max_retries=2)
            if 200 <= rs.status_code < 300:
                j = rs.json() or {}
                td = (j.get("ticker") or {})
                # Prefer today's close when available; then last trade price.
                price = _safe_float((td.get("day") or {}).get("c"))
                if price is None:
                    price = _safe_float((td.get("lastTrade") or {}).get("p"))
                if price is None:
                    price = _safe_float((td.get("prevDay") or {}).get("c"))
        except Exception:
            pass

        # Some plans/times return sparse snapshot payloads. Fallback to previous close endpoint.
        if price is None:
            try:
                prev_url = f"https://api.polygon.io/v2/aggs/ticker/{tk}/prev"
                rp = request_with_resilience("massive", prev_url, params={"apiKey": api_key}, timeout=timeout, max_retries=2)
                if 200 <= rp.status_code < 300:
                    pj = rp.json() or {}
                    arr = pj.get("results") or []
                    if isinstance(arr, list) and arr:
                        price = _safe_float((arr[0] or {}).get("c"))
            except Exception:
                pass

        try:
            ref_url = f"https://api.polygon.io/v3/reference/tickers/{tk}"
            rr = request_with_resilience("massive", ref_url, params={"apiKey": api_key}, timeout=timeout, max_retries=2)
            if 200 <= rr.status_code < 300:
                rj = rr.json() or {}
                mcap = _safe_float((rj.get("results") or {}).get("market_cap"))
        except Exception:
            pass

        if price is not None or mcap is not None:
            rows.append({"symbol": tk, "price": price, "marketCap": mcap})
    return pd.DataFrame(rows)


def _fetch_quotes_yahoo(tickers: list[str], timeout: int = 12) -> pd.DataFrame:
    rows = []
    syms = ",".join([str(t).upper().strip() for t in tickers if str(t).strip()])
    if not syms:
        return pd.DataFrame()
    try:
        r = request_with_resilience(
            "yahoo",
            "https://query1.finance.yahoo.com/v7/finance/quote",
            params={"symbols": syms},
            timeout=timeout,
            max_retries=1,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if not (200 <= r.status_code < 300):
            return pd.DataFrame()
        j = r.json() or {}
        for it in ((j.get("quoteResponse") or {}).get("result") or []):
            tk = str(it.get("symbol") or "").upper().strip()
            if not tk:
                continue
            rows.append(
                {
                    "symbol": tk,
                    "price": _safe_float(it.get("regularMarketPrice")),
                    "marketCap": _safe_float(it.get("marketCap")),
                }
            )
    except Exception:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def _ensure_comps_schema(comps: pd.DataFrame) -> pd.DataFrame:
    required_cols = [
        "ticker",
        "price",
        "market_cap",
        "period_end",
        "revenue_ttm",
        "revenue_ttm_yoy_pct",
        "fcf_ttm",
        "fcf_ttm_yoy_pct",
        "fcf_margin_ttm_pct",
        "cash",
        "debt",
        "net_debt",
        "fcf_yield",
        "net_debt_to_fcf_ttm",
    ]
    if comps is None or comps.empty:
        return pd.DataFrame(columns=required_cols)
    out = comps.copy()
    for c in required_cols:
        if c not in out.columns:
            out[c] = None
    return out[required_cols]


def _bootstrap_primary_row(comps: pd.DataFrame, quotes: pd.DataFrame, primary: str, warnings: list) -> pd.DataFrame:
    primary = (primary or "").upper().strip()
    out = _ensure_comps_schema(comps)

    if not out.empty:
        out["ticker"] = out["ticker"].astype(str).str.upper()
        if (out["ticker"] == primary).any():
            return out

    price = None
    market_cap = None
    if quotes is not None and not quotes.empty and "symbol" in quotes.columns:
        q = quotes.copy()
        q["symbol"] = q["symbol"].astype(str).str.upper()
        qr = q[q["symbol"] == primary]
        if not qr.empty:
            q0 = qr.iloc[0]
            price = _safe_float(q0.get("price"))
            market_cap = _safe_float(q0.get("marketCap"))

    row = {
        "ticker": primary,
        "price": price,
        "market_cap": market_cap,
        "period_end": None,
        "revenue_ttm": None,
        "revenue_ttm_yoy_pct": None,
        "fcf_ttm": None,
        "fcf_ttm_yoy_pct": None,
        "fcf_margin_ttm_pct": None,
        "cash": None,
        "debt": None,
        "net_debt": None,
        "fcf_yield": None,
        "net_debt_to_fcf_ttm": None,
    }
    out = pd.concat([out, pd.DataFrame([row])], ignore_index=True)
    warnings.append(
        f"Primary ticker {primary} was missing from comps snapshot; inserted bootstrap row"
        + (" with live quote fields." if price is not None else " with null fundamentals.")
    )
    return out


def _hydrate_missing_comps_from_last_good(comps: pd.DataFrame, universe: list[str], warnings: list) -> pd.DataFrame:
    out = _ensure_comps_schema(comps)
    if out.empty or "ticker" not in out.columns:
        existing = set()
    else:
        out["ticker"] = out["ticker"].astype(str).str.upper()
        existing = set(out["ticker"].tolist())

    wanted = [str(t).upper().strip() for t in (universe or []) if str(t).strip()]
    missing = [t for t in wanted if t not in existing]
    if not missing:
        return out

    last_good = DATA_PROCESSED / "last_good" / "comps_snapshot_latest.csv"
    if not last_good.exists():
        return out

    try:
        lg = pd.read_csv(last_good)
    except Exception:
        warnings.append("last_good comps snapshot exists but could not be read.")
        return out

    lg = _ensure_comps_schema(lg)
    if lg.empty:
        return out
    lg["ticker"] = lg["ticker"].astype(str).str.upper()

    add = lg[lg["ticker"].isin(missing)]
    if add.empty:
        return out

    out = pd.concat([out, add], ignore_index=True)
    out = out.drop_duplicates(subset=["ticker"], keep="first").reset_index(drop=True)
    restored = ",".join(sorted(set(add["ticker"].tolist())))
    warnings.append(f"Restored missing peer comps from last_good cache: {restored}.")
    return _ensure_comps_schema(out)


# ---------------------------
# Fundamentals builders (quarterly + TTM) per ticker
# ---------------------------
def build_quarterly_history(ticker: str, limit: int = 40) -> pd.DataFrame:
    inc = fetch_income_statement(ticker, period="quarter", limit=limit)
    cfs = fetch_cashflow_statement(ticker, period="quarter", limit=limit)
    bal = fetch_balance_sheet(ticker, period="quarter", limit=limit)

    if inc.empty or cfs.empty or bal.empty:
        raise RuntimeError(f"Quarterly endpoint returned empty for {ticker}")

    df = inc.merge(cfs, on="date", how="inner", suffixes=("", "_cfs"))
    df = df.merge(bal, on="date", how="inner", suffixes=("", "_bal"))

    out = pd.DataFrame(
        {
            "ticker": ticker,
            "period_end": df["date"],
            "revenue": df.get("revenue"),
            "operating_cash_flow": df.get("operatingCashFlow"),
            "capex_raw": df.get("capitalExpenditure"),
            "cash": df.get("cashAndCashEquivalents"),
            "debt": df.get("totalDebt"),
        }
    )

    out["capex_spend"] = out["capex_raw"].apply(lambda x: abs(float(x)) if pd.notna(x) else None)

    def _fcf_row(r):
        if pd.isna(r["operating_cash_flow"]) or pd.isna(r["capex_spend"]):
            return None
        return float(r["operating_cash_flow"]) - float(r["capex_spend"])

    out["free_cash_flow"] = out.apply(_fcf_row, axis=1)
    out = out.sort_values("period_end", ascending=False).reset_index(drop=True)
    return out


def build_ttm_from_quarters(qhist: pd.DataFrame) -> pd.DataFrame:
    if qhist.empty:
        return pd.DataFrame()

    ticker = str(qhist.loc[0, "ticker"])
    tmp = qhist.sort_values("period_end", ascending=True).reset_index(drop=True)

    for col in ["revenue", "free_cash_flow", "cash", "debt"]:
        tmp[col] = pd.to_numeric(tmp[col], errors="coerce")

    tmp["revenue_ttm"] = tmp["revenue"].rolling(4).sum()
    tmp["fcf_ttm"] = tmp["free_cash_flow"].rolling(4).sum()
    tmp["fcf_margin_ttm_pct"] = (tmp["fcf_ttm"] / tmp["revenue_ttm"]) * 100

    tmp["revenue_ttm_yoy_pct"] = tmp["revenue_ttm"].pct_change(4) * 100
    tmp["fcf_ttm_yoy_pct"] = tmp["fcf_ttm"].pct_change(4) * 100

    tmp["ticker"] = ticker
    out = tmp.sort_values("period_end", ascending=False).reset_index(drop=True)
    return out


# ---------------------------
# Comps snapshot
# ---------------------------
def build_comps_snapshot(ttm_latest_by_ticker: Dict[str, pd.Series], quotes: pd.DataFrame) -> pd.DataFrame:
    quote_map = {}
    if not quotes.empty and "symbol" in quotes.columns:
        for _, r in quotes.iterrows():
            quote_map[str(r.get("symbol", "")).upper()] = r

    rows = []
    for t, latest in ttm_latest_by_ticker.items():
        q = quote_map.get(t, {})

        mcap = _safe_float(q.get("marketCap"))
        price = _safe_float(q.get("price"))

        revenue_ttm = _safe_float(latest.get("revenue_ttm"))
        fcf_ttm = _safe_float(latest.get("fcf_ttm"))
        rev_yoy = _safe_float(latest.get("revenue_ttm_yoy_pct"))
        fcf_yoy = _safe_float(latest.get("fcf_ttm_yoy_pct"))
        margin = _safe_float(latest.get("fcf_margin_ttm_pct"))

        cash = _safe_float(latest.get("cash"))
        debt = _safe_float(latest.get("debt"))
        net_debt = None
        if cash is not None and debt is not None:
            net_debt = debt - cash

        fcf_yield = None
        if fcf_ttm is not None and mcap is not None and mcap > 0:
            fcf_yield = fcf_ttm / mcap

        nd_fcf = None
        if net_debt is not None and fcf_ttm is not None and fcf_ttm > 0:
            nd_fcf = net_debt / fcf_ttm

        rows.append(
            {
                "ticker": t,
                "price": price,
                "market_cap": mcap,
                "period_end": latest.get("period_end"),
                "revenue_ttm": revenue_ttm,
                "revenue_ttm_yoy_pct": rev_yoy,
                "fcf_ttm": fcf_ttm,
                "fcf_ttm_yoy_pct": fcf_yoy,
                "fcf_margin_ttm_pct": margin,
                "cash": cash,
                "debt": debt,
                "net_debt": net_debt,
                "fcf_yield": fcf_yield,
                "net_debt_to_fcf_ttm": nd_fcf,
            }
        )

    return pd.DataFrame(rows)


# ---------------------------
# Scoring (relative + absolute + NEWS)
# ---------------------------
@dataclass
class DecisionOutput:
    ticker: str
    as_of: str
    score: int
    rating: str
    red_flags: list
    bucket_scores: dict
    peer_ranks: dict
    news_summary: dict
    news_proxy: dict


def compute_decision_with_peers_and_news(comps: pd.DataFrame, news_summary: dict, news_proxy_row: dict) -> DecisionOutput:
    df = comps.copy()
    df["ticker"] = df["ticker"].astype(str).str.upper()

    row = df[df["ticker"] == PRIMARY]
    if row.empty:
        raise RuntimeError(f"{PRIMARY} not found in comps snapshot")
    r = row.iloc[0]

    red_flags = []

    fcf_ttm = _safe_float(r.get("fcf_ttm"))
    fcf_yield = _safe_float(r.get("fcf_yield"))
    rev_yoy = _safe_float(r.get("revenue_ttm_yoy_pct"))
    fcf_yoy = _safe_float(r.get("fcf_ttm_yoy_pct"))
    margin = _safe_float(r.get("fcf_margin_ttm_pct"))
    nd_fcf = _safe_float(r.get("net_debt_to_fcf_ttm"))

    rank_fcf_yield = _rank_percentile(df["fcf_yield"], fcf_yield, higher_is_better=True)
    rank_rev_yoy = _rank_percentile(df["revenue_ttm_yoy_pct"], rev_yoy, higher_is_better=True)
    rank_fcf_yoy = _rank_percentile(df["fcf_ttm_yoy_pct"], fcf_yoy, higher_is_better=True)
    rank_margin = _rank_percentile(df["fcf_margin_ttm_pct"], margin, higher_is_better=True)

    peer_ranks = {
        "fcf_yield_pct_rank": rank_fcf_yield,
        "revenue_ttm_yoy_pct_rank": rank_rev_yoy,
        "fcf_ttm_yoy_pct_rank": rank_fcf_yoy,
        "fcf_margin_ttm_pct_rank": rank_margin,
    }

    buckets = {"cash_level": 0.0, "valuation": 0.0, "growth": 0.0, "quality": 0.0, "balance_risk": 0.0}

    # Cash Level (25)
    if fcf_ttm is None:
        buckets["cash_level"] = 0
        red_flags.append("TTM FCF missing")
    else:
        if fcf_ttm >= 12e9:
            buckets["cash_level"] = 25
        elif fcf_ttm >= 8e9:
            buckets["cash_level"] = 21
        elif fcf_ttm >= 4e9:
            buckets["cash_level"] = 15
        elif fcf_ttm >= 1e9:
            buckets["cash_level"] = 8
        else:
            buckets["cash_level"] = 3
            red_flags.append("Low TTM FCF")

    # Valuation (20)
    val_points = 0.0
    if fcf_yield is None:
        red_flags.append("FCF yield missing")
    else:
        if fcf_yield >= 0.08:
            val_points += 10
        elif fcf_yield >= 0.06:
            val_points += 8
        elif fcf_yield >= 0.04:
            val_points += 5
        elif fcf_yield >= 0.025:
            val_points += 3
        else:
            val_points += 1

    if rank_fcf_yield is not None:
        if rank_fcf_yield >= 75:
            val_points += 10
        elif rank_fcf_yield >= 50:
            val_points += 7
        elif rank_fcf_yield >= 25:
            val_points += 4
        else:
            val_points += 2

    buckets["valuation"] = _clamp(val_points, 0, 20)

    # Growth (20)
    g = 0.0
    if rev_yoy is not None:
        if rev_yoy >= 20:
            g += 6
        elif rev_yoy >= 10:
            g += 4
        elif rev_yoy >= 5:
            g += 2
        elif rev_yoy < 0:
            g -= 3
            red_flags.append("TTM revenue declining YoY")

    if fcf_yoy is not None:
        if fcf_yoy >= 40:
            g += 6
        elif fcf_yoy >= 15:
            g += 4
        elif fcf_yoy >= 5:
            g += 2
        elif fcf_yoy < 0:
            g -= 5
            red_flags.append("TTM FCF declining YoY")

    if rank_rev_yoy is not None:
        g += 4 if rank_rev_yoy >= 75 else 3 if rank_rev_yoy >= 50 else 2 if rank_rev_yoy >= 25 else 1
    if rank_fcf_yoy is not None:
        g += 4 if rank_fcf_yoy >= 75 else 3 if rank_fcf_yoy >= 50 else 2 if rank_fcf_yoy >= 25 else 1

    buckets["growth"] = _clamp(g, 0, 20)

    # Quality (15)
    q = 0.0
    if margin is not None:
        if margin >= 18:
            q += 9
        elif margin >= 12:
            q += 7
        elif margin >= 8:
            q += 5
        elif margin >= 4:
            q += 3
        else:
            q += 1

    if rank_margin is not None:
        q += 6 if rank_margin >= 75 else 4 if rank_margin >= 50 else 3 if rank_margin >= 25 else 2

    buckets["quality"] = _clamp(q, 0, 15)

    # Balance/Risk (20): debt + news penalties + proxy mood
    b = 20.0
    if nd_fcf is not None:
        if nd_fcf >= 3.0:
            b -= 8
            red_flags.append("Net debt high vs TTM FCF")
        elif nd_fcf >= 1.5:
            b -= 4
    else:
        b -= 2

    neg_7d = int(news_summary.get("neg_7d", 0))
    shock_7d = int(news_summary.get("shock_7d", 0))
    tag_counts = news_summary.get("tag_counts_30d", {}) or {}

    if neg_7d >= 6:
        b -= 8
    elif neg_7d >= 3:
        b -= 5
    elif neg_7d >= 1:
        b -= 2

    if shock_7d <= -10:
        b -= 4
    elif shock_7d <= -6:
        b -= 2

    core = ["LABOR", "INSURANCE", "REGULATORY"]
    core_hits = sum(int(tag_counts.get(t, 0)) for t in core)
    if core_hits >= 6:
        b -= 4
        red_flags.append("Frequent LABOR/INSURANCE/REGULATORY negatives (30d)")
    elif core_hits >= 3:
        b -= 2

    proxy7 = news_proxy_row.get("proxy_score_7d")
    if proxy7 is not None:
        try:
            p7 = float(proxy7)
            if p7 <= 25:
                b -= 4
            elif p7 <= 35:
                b -= 2
            elif p7 >= 70:
                b += 1
        except Exception:
            pass

    buckets["balance_risk"] = _clamp(b, 0, 20)

    score = int(round(_clamp(sum(buckets.values()), 0, 100)))
    rating = "BUY" if score >= 80 else "HOLD" if score >= 65 else "AVOID"

    bucket_scores = {k: int(round(v)) for k, v in buckets.items()}

    if neg_7d >= 3:
        red_flags.append(f"News: {neg_7d} negative headlines in last 7d (shock {shock_7d})")

    return DecisionOutput(
        ticker=PRIMARY,
        as_of=AS_OF,
        score=score,
        rating=rating,
        red_flags=red_flags,
        bucket_scores=bucket_scores,
        peer_ranks=peer_ranks,
        news_summary=news_summary,
        news_proxy=news_proxy_row,
    )
def write_ticker_json(outputs_dir, ticker: str, basename: str, obj: dict) -> str:
    """
    Writes BOTH:
      1) outputs/<basename>_<TICKER>.json  (ticker-scoped, never overwritten by other tickers)
      2) outputs/<basename>.json          (latest convenience copy)
    Returns the ticker-scoped path as a string.
    """
    import json
    from pathlib import Path

    outputs_dir = Path(outputs_dir)
    outputs_dir.mkdir(parents=True, exist_ok=True)

    t = (ticker or "").upper().strip()
    scoped = outputs_dir / f"{basename}_{t}.json"
    latest = outputs_dir / f"{basename}.json"

    scoped.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")
    latest.write_text(scoped.read_text(encoding="utf-8"), encoding="utf-8")
    return str(scoped)

# ---------------------------
# Main
# ---------------------------
def main():
    ensure_dirs()
    refresh_warnings = []
    fmp_key = (os.getenv("FMP_API_KEY") or "").strip()
    massive_key = (os.getenv("MASSIVE_API_KEY") or os.getenv("POLYGON_API_KEY") or "").strip()
    finnhub_key = (os.getenv("FINNHUB_API_KEY") or "").strip()
    tiingo_key = (
        os.getenv("TIINGO_API_KEY")
        or os.getenv("TIINGO_TOKEN")
        or os.getenv("TIINGO_KEY")
        or ""
    ).strip()
    marketaux_key = (
        os.getenv("MARKETAUX_API_KEY")
        or os.getenv("MARKETAUX_TOKEN")
        or os.getenv("MARKETAUX_KEY")
        or ""
    ).strip()
    alphavantage_key = (
        os.getenv("ALPHAVANTAGE_API_KEY")
        or os.getenv("ALPHA_VANTAGE_API_KEY")
        or os.getenv("ALPHAVANTAGE_KEY")
        or os.getenv("ALPHA_VANTAGE_KEY")
        or os.getenv("AV_API_KEY")
        or ""
    ).strip()

    if not massive_key:
        refresh_warnings.append("Massive API key missing (set MASSIVE_API_KEY or POLYGON_API_KEY for provider preflight).")

    # Quotes (resilient)
    quote_provider_used = "none"
    quotes = pd.DataFrame()
    try:
        quotes = fetch_quotes(UNIVERSE)
        if not quotes.empty:
            quote_provider_used = "fmp_paid"
            write_csv(quotes, DATA_RAW / "quotes_universe_raw.csv")
        else:
            refresh_warnings.append("Quote pull returned zero rows.")
    except Exception as e:
        refresh_warnings.append(f"Primary quote pull failed: {e}")
    if quotes.empty and massive_key:
        try:
            mq = _fetch_quotes_massive(UNIVERSE, massive_key)
            if not mq.empty:
                quotes = mq
                quote_provider_used = "massive"
                write_csv(quotes, DATA_RAW / "quotes_universe_raw.csv")
                refresh_warnings.append("Quote pull recovered via Massive fallback.")
        except Exception as e:
            refresh_warnings.append(f"Massive quote fallback failed: {e}")
    if quotes.empty:
        try:
            yq = _fetch_quotes_yahoo(UNIVERSE)
            if not yq.empty:
                quotes = yq
                quote_provider_used = "yahoo_public"
                write_csv(quotes, DATA_RAW / "quotes_universe_raw.csv")
                refresh_warnings.append("Quote pull recovered via Yahoo fallback.")
        except Exception as e:
            refresh_warnings.append(f"Yahoo quote fallback failed: {e}")
    if quotes.empty:
        q_cache = DATA_RAW / "quotes_universe_raw.csv"
        if q_cache.exists():
            try:
                quotes = pd.read_csv(q_cache)
                quote_provider_used = "raw_cache"
                refresh_warnings.append("Quote hydration from cache completed for full universe coverage.")
            except Exception:
                refresh_warnings.append("Quote cache exists but could not be read.")
        else:
            quote_provider_used = "unavailable"
            refresh_warnings.append("Quote fallback unavailable; price/market cap may be missing.")

    # Fundamentals TTM per ticker (resilient per ticker)
    ttm_latest = {}
    all_qhist = []
    all_ttm = []

    ttm_cache = pd.DataFrame()
    ttm_cache_path = DATA_PROCESSED / "fundamentals_ttm_universe.csv"
    if ttm_cache_path.exists():
        try:
            ttm_cache = pd.read_csv(ttm_cache_path)
        except Exception:
            ttm_cache = pd.DataFrame()

    for t in UNIVERSE:
        try:
            qhist = build_quarterly_history(t, limit=40)
            ttm = build_ttm_from_quarters(qhist)

            all_qhist.append(qhist)
            all_ttm.append(ttm)

            if not ttm.empty:
                ttm_latest[t] = ttm.iloc[0]
        except Exception as e:
            refresh_warnings.append(f"Fundamentals refresh failed for {t}: {e}")
            # Per-ticker fallback from cached TTM universe.
            try:
                if not ttm_cache.empty and "ticker" in ttm_cache.columns:
                    tc = ttm_cache.copy()
                    tc["ticker"] = tc["ticker"].astype(str).str.upper()
                    tr = tc[tc["ticker"] == t]
                    if not tr.empty:
                        if "period_end" in tr.columns:
                            tr = tr.sort_values("period_end", ascending=False)
                        ttm_latest[t] = tr.iloc[0]
                        refresh_warnings.append(f"Fundamentals for {t} recovered from cached TTM snapshot.")
            except Exception:
                pass

    qhist_all = pd.concat(all_qhist, ignore_index=True) if all_qhist else pd.DataFrame()
    ttm_all = pd.concat(all_ttm, ignore_index=True) if all_ttm else pd.DataFrame()

    if not qhist_all.empty:
        write_csv(qhist_all, DATA_PROCESSED / "fundamentals_quarterly_history_universe.csv")
    if not ttm_all.empty:
        write_csv(ttm_all, DATA_PROCESSED / "fundamentals_ttm_universe.csv")

    comps = build_comps_snapshot(ttm_latest, quotes) if ttm_latest else pd.DataFrame()
    comps = _ensure_comps_schema(comps)
    if not comps.empty:
        write_csv(comps, DATA_PROCESSED / "comps_snapshot.csv")
    else:
        cache_comps = DATA_PROCESSED / "comps_snapshot.csv"
        if cache_comps.exists():
            try:
                comps = pd.read_csv(cache_comps)
                refresh_warnings.append("Using cached comps_snapshot.csv due to refresh failure.")
            except Exception:
                refresh_warnings.append("comps_snapshot.csv cache exists but could not be read.")
    comps = _ensure_comps_schema(comps)
    comps = _bootstrap_primary_row(comps, quotes, PRIMARY, refresh_warnings)
    comps = _hydrate_missing_comps_from_last_good(comps, UNIVERSE, refresh_warnings)
    write_csv(comps, DATA_PROCESSED / "comps_snapshot.csv")
    try:
        c = comps.copy()
        c["ticker"] = c["ticker"].astype(str).str.upper()
        required = set([str(t).upper().strip() for t in UNIVERSE if str(t).strip()])
        present = set(c["ticker"].tolist())
        if required and required.issubset(present):
            _snapshot_last_good_csv(DATA_PROCESSED / "comps_snapshot.csv", "comps_snapshot")
    except Exception:
        pass

    # NEWS (stable): SEC + Finnhub company news
    news_df = pd.DataFrame()
    news_sources_enabled = ["sec", "finnhub"]
    if not finnhub_key:
        # keep source listed for compatibility; connector will emit key-missing error per ticker
        pass
    if tiingo_key:
        news_sources_enabled.append("tiingo")
    if marketaux_key:
        news_sources_enabled.append("marketaux")
    if alphavantage_key:
        news_sources_enabled.append("alphavantage")

    news_fresh_ok = False
    try:
        news_df = run_news_pipeline(
            tickers=UNIVERSE,
            days_back=30,
            enable_sources=news_sources_enabled,
            sec_user_agent=None,
            debug=True,
        )
        if not news_df.empty:
            write_csv(news_df, DATA_PROCESSED / "news_unified.csv")
            _snapshot_last_good_csv(DATA_PROCESSED / "news_unified.csv", "news_unified")
            news_fresh_ok = True
        else:
            refresh_warnings.append("News refresh returned zero rows.")
    except Exception as e:
        refresh_warnings.append(f"News refresh failed: {e}")
    if not news_fresh_ok:
        n_cache = DATA_PROCESSED / "news_unified.csv"
        news_df = _read_nonempty_csv(n_cache)
        if not news_df.empty:
            refresh_warnings.append("Using cached news_unified.csv due to refresh failure.")
        else:
            news_df = _restore_last_good_csv(DATA_PROCESSED / "news_unified.csv", "news_unified")
            if not news_df.empty:
                refresh_warnings.append("Restored news_unified.csv from last_good cache.")
            else:
                refresh_warnings.append("No non-empty news_unified cache was available.")

    # Sentiment proxy (works without paid endpoints)
    proxy_df = build_news_sentiment_proxy(news_df) if not news_df.empty else pd.DataFrame()
    if not proxy_df.empty:
        write_csv(proxy_df, DATA_PROCESSED / "news_sentiment_proxy.csv")
        _snapshot_last_good_csv(DATA_PROCESSED / "news_sentiment_proxy.csv", "news_sentiment_proxy")
    else:
        p_cache = DATA_PROCESSED / "news_sentiment_proxy.csv"
        proxy_df = _read_nonempty_csv(p_cache)
        if not proxy_df.empty:
            refresh_warnings.append("Using cached news_sentiment_proxy.csv due to refresh failure.")
        else:
            proxy_df = _restore_last_good_csv(DATA_PROCESSED / "news_sentiment_proxy.csv", "news_sentiment_proxy")
            if not proxy_df.empty:
                refresh_warnings.append("Restored news_sentiment_proxy.csv from last_good cache.")
            else:
                refresh_warnings.append("No non-empty news_sentiment_proxy cache was available.")

    proxy_row = {}
    if not proxy_df.empty:
        pr = proxy_df[proxy_df["ticker"] == PRIMARY]
        if not pr.empty:
            proxy_row = pr.iloc[0].to_dict()

    # Risk dashboard (TOTAL rows + clean blanks)
    risk_dash = build_news_risk_dashboard(news_df) if not news_df.empty else pd.DataFrame()
    if not risk_dash.empty:
        write_csv(risk_dash, DATA_PROCESSED / "news_risk_dashboard.csv")

    # Evidence pack (clickable + CSV) so you can verify sources
    evidence_focus = build_evidence_table(news_df, ticker=PRIMARY, days=30, max_rows=80) if not news_df.empty else pd.DataFrame()
    if not evidence_focus.empty:
        write_csv(evidence_focus, DATA_PROCESSED / f"news_evidence_{PRIMARY}.csv")
        write_evidence_html(
            evidence_focus,
            OUTPUTS / f"news_evidence_{PRIMARY}.html",
            title=f"News Evidence — {PRIMARY} (last 30d)",
        )

    # Summaries and decision
    news_summary = summarize_news_for_scoring(news_df, primary=PRIMARY, days_short=7, days_long=30)
    decision = compute_decision_with_peers_and_news(comps, news_summary, proxy_row)
    freshness = _freshness_sla_snapshot(PRIMARY, comps, news_df)
    if not freshness.get("passed", False):
        decision.rating = "AVOID"
        decision.score = int(min(decision.score, 45))
        decision.red_flags.append(
            "Freshness SLA failed: one or more core datasets are older than allowed threshold."
        )
        refresh_warnings.append(
            "Freshness SLA failed; recommendation is forced conservative until data is refreshed."
        )

    # Provider health + metric provider provenance (fresh per run)
    provider_priority = ["fmp_paid", "yahoo_public"]
    if massive_key:
        provider_priority.insert(1, "massive")

    checks = []
    if fmp_key:
        checks.append(
            _check_url(
                "fmp_quote",
                "https://financialmodelingprep.com/stable/quote",
                {"symbol": PRIMARY, "apikey": fmp_key},
            )
        )
    else:
        checks.append({"name": "fmp_quote", "url": "https://financialmodelingprep.com/stable/quote?symbol=<T>&apikey=<missing>", "ok": False, "status_code": None, "error": "Missing FMP_API_KEY"})

    if massive_key:
        checks.append(
            _check_url(
                "massive_reference",
                f"https://api.polygon.io/v3/reference/tickers/{PRIMARY}",
                {"apiKey": massive_key},
            )
        )

    checks.append(
        _check_url(
            "yahoo_quote",
            "https://query1.finance.yahoo.com/v7/finance/quote",
            {"symbols": PRIMARY},
        )
    )
    checks.append(
        _check_url(
            "yahoo_summary",
            f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{PRIMARY}",
            {"modules": "price"},
        )
    )

    # News provider preflight checks so source health is auditable.
    news_to = date.today().isoformat()
    news_from = (date.today() - timedelta(days=30)).isoformat()
    sec_ua = (
        os.getenv("SEC_NEWS_USER_AGENT")
        or "investment_decision_engine (research) contact: melbello1205@gmail.com "
    ).strip()
    checks.append(
        _check_url(
            "news_sec_submissions",
            "https://data.sec.gov/submissions/CIK0000320193.json",
            {},
            headers={"User-Agent": sec_ua},
            provider="sec",
        )
    )
    if finnhub_key:
        checks.append(
            _check_url(
                "news_finnhub_company_news",
                "https://finnhub.io/api/v1/company-news",
                {"symbol": PRIMARY, "from": news_from, "to": news_to, "token": finnhub_key},
                provider="finnhub",
            )
        )
    else:
        checks.append(
            {
                "name": "news_finnhub_company_news",
                "url": f"https://finnhub.io/api/v1/company-news?symbol={PRIMARY}&from={news_from}&to={news_to}&token=<missing>",
                "ok": False,
                "status_code": None,
                "error": "Missing FINNHUB_API_KEY",
            }
        )
    if tiingo_key:
        checks.append(
            _check_url(
                "news_tiingo_news",
                "https://api.tiingo.com/tiingo/news",
                {"tickers": PRIMARY, "startDate": news_from, "endDate": news_to, "limit": 1, "token": tiingo_key},
                provider="tiingo",
            )
        )
    else:
        checks.append(
            {
                "name": "news_tiingo_news",
                "url": f"https://api.tiingo.com/tiingo/news?tickers={PRIMARY}&startDate={news_from}&endDate={news_to}&limit=1&token=<missing>",
                "ok": False,
                "status_code": None,
                "error": "Missing TIINGO_API_KEY",
            }
        )
    if marketaux_key:
        checks.append(
            _check_url(
                "news_marketaux_news",
                "https://api.marketaux.com/v1/news/all",
                {"symbols": PRIMARY, "published_after": news_from, "published_before": news_to, "limit": 1, "api_token": marketaux_key},
                provider="marketaux",
            )
        )
    else:
        checks.append(
            {
                "name": "news_marketaux_news",
                "url": f"https://api.marketaux.com/v1/news/all?symbols={PRIMARY}&published_after={news_from}&published_before={news_to}&limit=1&api_token=<missing>",
                "ok": False,
                "status_code": None,
                "error": "Missing MARKETAUX_API_KEY",
            }
        )
    if alphavantage_key:
        checks.append(
            _check_url(
                "news_alphavantage_news",
                "https://www.alphavantage.co/query",
                {"function": "NEWS_SENTIMENT", "tickers": PRIMARY, "limit": 1, "apikey": alphavantage_key},
                provider="alphavantage",
            )
        )
    else:
        checks.append(
            {
                "name": "news_alphavantage_news",
                "url": f"https://www.alphavantage.co/query?function=NEWS_SENTIMENT&tickers={PRIMARY}&limit=1&apikey=<missing>",
                "ok": False,
                "status_code": None,
                "error": "Missing ALPHAVANTAGE_API_KEY",
            }
        )

    crosscheck = _crosscheck_fmp_vs_massive(PRIMARY, fmp_key, massive_key)
    for a in crosscheck.get("alerts", []):
        refresh_warnings.append(a)

    # Redact tokens from warnings before they are persisted or printed.
    refresh_warnings = [_redact_text(str(w)) for w in refresh_warnings]

    provider_health = {
        "as_of": AS_OF,
        "primary": PRIMARY,
        "provider_priority": provider_priority,
        "quote_provider_used": quote_provider_used,
        "timeout_budgets_sec": {
            "fmp": provider_timeout("fmp"),
            "massive": provider_timeout("massive"),
            "yahoo": provider_timeout("yahoo"),
            "finnhub": provider_timeout("finnhub"),
            "sec": provider_timeout("sec"),
            "tiingo": provider_timeout("tiingo"),
            "marketaux": provider_timeout("marketaux"),
            "alphavantage": provider_timeout("alphavantage"),
        },
        "circuit_breakers": {
            "fmp": provider_circuit_status("fmp"),
            "massive": provider_circuit_status("massive"),
            "yahoo": provider_circuit_status("yahoo"),
            "finnhub": provider_circuit_status("finnhub"),
            "sec": provider_circuit_status("sec"),
            "tiingo": provider_circuit_status("tiingo"),
            "marketaux": provider_circuit_status("marketaux"),
            "alphavantage": provider_circuit_status("alphavantage"),
        },
        "crosscheck_fmp_vs_massive": crosscheck,
        "freshness_sla": freshness,
        "fmp_api_key_present": bool(fmp_key),
        "massive_api_key_present": bool(massive_key),
        "finnhub_api_key_present": bool(finnhub_key),
        "tiingo_api_key_present": bool(tiingo_key),
        "marketaux_api_key_present": bool(marketaux_key),
        "alphavantage_api_key_present": bool(alphavantage_key),
        "checks": checks,
    }
    provider_health = _redact_obj(provider_health)
    write_json(provider_health, OUTPUTS / f"provider_health_{PRIMARY}.json")

    # Infer metric-provider used for audit trail.
    metric_provider_used = {}
    r0 = comps[comps["ticker"].astype(str).str.upper() == PRIMARY]
    row0 = r0.iloc[0] if not r0.empty else None
    def _mval(col):
        if row0 is None or col not in comps.columns:
            return None
        v = row0.get(col)
        try:
            if pd.isna(v):
                return None
        except Exception:
            pass
        return float(v) if isinstance(v, (int, float)) else v

    source_hint = quote_provider_used or ("fmp_paid" if (checks and checks[0].get("ok")) else ("raw_cache" if (DATA_RAW / "quotes_universe_raw.csv").exists() else "unavailable"))
    metric_provider_used["price"] = {"provider": source_hint, "value": _mval("price")}
    metric_provider_used["market_cap"] = {"provider": source_hint, "value": _mval("market_cap")}
    metric_provider_used["revenue_ttm_yoy_pct"] = {"provider": source_hint, "value": _mval("revenue_ttm_yoy_pct")}
    metric_provider_used["fcf_ttm"] = {"provider": source_hint, "value": _mval("fcf_ttm")}
    metric_provider_used["fcf_margin_ttm_pct"] = {"provider": source_hint, "value": _mval("fcf_margin_ttm_pct")}
    write_json(
        {
            "ticker": PRIMARY,
            "as_of": AS_OF,
            "metric_provider_used": metric_provider_used,
            "provider_priority": provider_priority,
        },
        OUTPUTS / f"metric_provider_used_{PRIMARY}.json",
    )

    decision_summary_obj = {
        "ticker": decision.ticker,
        "as_of": decision.as_of,
        "score": decision.score,
        "rating": decision.rating,
        "red_flags": decision.red_flags,
        "bucket_scores": decision.bucket_scores,
        "peer_ranks": decision.peer_ranks,
        "news_summary": decision.news_summary,
        "news_sentiment_proxy": decision.news_proxy,
        "universe": UNIVERSE,
        "news_sources_enabled": news_sources_enabled,
        "evidence_files": {
            "csv": f"data/processed/news_evidence_{PRIMARY}.csv",
            "html": f"outputs/news_evidence_{PRIMARY}.html",
        },
        "refresh_warnings": refresh_warnings,
        "freshness_sla": freshness,
        "crosscheck_fmp_vs_massive": crosscheck,
        "provider_health_file": f"outputs/provider_health_{PRIMARY}.json",
        "metric_provider_used_file": f"outputs/metric_provider_used_{PRIMARY}.json",
        "metric_provider_used": metric_provider_used,
    }
    decision_summary_obj["news_sources_enabled"] = news_sources_enabled
    write_json(decision_summary_obj, OUTPUTS / "decision_summary.json")
    write_json(decision_summary_obj, OUTPUTS / f"decision_summary_{PRIMARY}.json")

    decision_explanation_obj = {
        "ticker": decision.ticker,
        "as_of": decision.as_of,
        "score": decision.score,
        "rating": decision.rating,
        "universe": UNIVERSE,
        "bucket_scores": decision.bucket_scores,
        "peer_ranks": decision.peer_ranks,
        "news_summary": decision.news_summary,
        "news_sentiment_proxy": decision.news_proxy,
        "plain_english": {
            "what_this_is": "Arc Reactor engine uses TTM fundamentals + peer comps + stable news risk (SEC filings + Finnhub headlines).",
            "veracity_check": f"Open outputs/news_evidence_{PRIMARY}.html to verify every headline the score is reacting to.",
            "why_proxy": "Finnhub /news-sentiment is often paywalled (403). Proxy uses headline keywords + impact scoring instead.",
        },
        "outputs_written": [
            "data/processed/news_unified.csv",
            "data/processed/news_sentiment_proxy.csv",
            "data/processed/news_risk_dashboard.csv",
            f"data/processed/news_evidence_{PRIMARY}.csv",
            f"outputs/news_evidence_{PRIMARY}.html",
            "outputs/decision_summary.json",
            f"outputs/decision_summary_{PRIMARY}.json",
            "outputs/decision_explanation.json",
            f"outputs/decision_explanation_{PRIMARY}.json",
        ],
        "refresh_warnings": refresh_warnings,
        "freshness_sla": freshness,
        "crosscheck_fmp_vs_massive": crosscheck,
    }
    write_json(decision_explanation_obj, OUTPUTS / "decision_explanation.json")
    write_json(decision_explanation_obj, OUTPUTS / f"decision_explanation_{PRIMARY}.json")

    write_json({"ticker": PRIMARY, "refresh_warnings": refresh_warnings}, OUTPUTS / f"refresh_warnings_{PRIMARY}.json")

    print("SUCCESS — Engine Running (SEC + Finnhub + Proxy + Evidence)")
    print("Universe:", UNIVERSE)
    print("Score:", decision.score)
    print("Rating:", decision.rating)
    print("Bucket scores:", decision.bucket_scores)
    if refresh_warnings:
        print("Refresh warnings:")
        for w in refresh_warnings:
            print(" -", w)
    if decision.red_flags:
        print("Red flags:")
        for rf in decision.red_flags:
            print(" -", rf)


if __name__ == "__main__":
    main()
