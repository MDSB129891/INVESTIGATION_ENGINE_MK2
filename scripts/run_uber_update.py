import os
#!/usr/bin/env python3
import sys
from pathlib import Path

# Make project root importable when running from scripts/
sys.path.append(str(Path(__file__).resolve().parents[1]))

import json
from dataclasses import dataclass
from datetime import date
from typing import Dict
from urllib.parse import urlencode
import requests

import pandas as pd

from analytics.fmp_pull import (
    fetch_quotes,
    fetch_income_statement,
    fetch_cashflow_statement,
    fetch_balance_sheet,
)

from analytics.news.pipeline import run_news_pipeline, summarize_news_for_scoring
from analytics.news.sentiment_proxy import build_news_sentiment_proxy
from analytics.news.risk_dashboard import build_news_risk_dashboard
from analytics.news.evidence import build_evidence_table, write_evidence_html

# ---- Thanos-safe universe config (do not edit by hand) ----
TICKER = os.getenv("TICKER", "AAPL").strip().upper()
PEERS = [s.strip().upper() for s in os.getenv("PEERS", "LYFT,DASH").split(",") if s.strip()]
UNIVERSE = [TICKER] + [p for p in PEERS if p != TICKER]
# Optional override: set UNIVERSE="AAPL,MSFT,GOOGL" to fully control
UNIVERSE_ENV = os.getenv("UNIVERSE", "")
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
    for p in [DATA_RAW, DATA_PROCESSED, OUTPUTS]:
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
    for key in ("apikey=", "apiKey="):
        i = url.find(key)
        if i >= 0:
            j = url.find("&", i)
            if j == -1:
                j = len(url)
            url = url[: i + len(key)] + "***REDACTED***" + url[j:]
    return url


def _check_url(name: str, base_url: str, params: dict, timeout: int = 12) -> dict:
    full = base_url + ("?" + urlencode(params) if params else "")
    try:
        r = requests.get(base_url, params=params, timeout=timeout)
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
            "error": str(e),
        }


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

    if not massive_key:
        refresh_warnings.append("Massive API key missing (set MASSIVE_API_KEY or POLYGON_API_KEY for provider preflight).")

    # Quotes (resilient)
    quotes = pd.DataFrame()
    try:
        quotes = fetch_quotes(UNIVERSE)
        if not quotes.empty:
            write_csv(quotes, DATA_RAW / "quotes_universe_raw.csv")
        else:
            refresh_warnings.append("Quote pull returned zero rows.")
    except Exception as e:
        refresh_warnings.append(f"Primary quote pull failed: {e}")
        q_cache = DATA_RAW / "quotes_universe_raw.csv"
        if q_cache.exists():
            try:
                quotes = pd.read_csv(q_cache)
                refresh_warnings.append("Quote hydration from cache completed for full universe coverage.")
            except Exception:
                refresh_warnings.append("Quote cache exists but could not be read.")
        else:
            refresh_warnings.append("Quote fallback unavailable; price/market cap may be missing.")

    # Fundamentals TTM per ticker (resilient per ticker)
    ttm_latest = {}
    all_qhist = []
    all_ttm = []

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

    qhist_all = pd.concat(all_qhist, ignore_index=True) if all_qhist else pd.DataFrame()
    ttm_all = pd.concat(all_ttm, ignore_index=True) if all_ttm else pd.DataFrame()

    if not qhist_all.empty:
        write_csv(qhist_all, DATA_PROCESSED / "fundamentals_quarterly_history_universe.csv")
    if not ttm_all.empty:
        write_csv(ttm_all, DATA_PROCESSED / "fundamentals_ttm_universe.csv")

    comps = build_comps_snapshot(ttm_latest, quotes) if ttm_latest else pd.DataFrame()
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

    # NEWS (stable): SEC + Finnhub company news
    news_df = pd.DataFrame()
    try:
        news_df = run_news_pipeline(
            tickers=UNIVERSE,
            days_back=30,
            enable_sources=["sec", "finnhub"],
            sec_user_agent=None,
            debug=True,
        )
        write_csv(news_df, DATA_PROCESSED / "news_unified.csv")
    except Exception as e:
        refresh_warnings.append(f"News refresh failed: {e}")
        n_cache = DATA_PROCESSED / "news_unified.csv"
        if n_cache.exists():
            try:
                news_df = pd.read_csv(n_cache)
                refresh_warnings.append("Using cached news_unified.csv due to refresh failure.")
            except Exception:
                refresh_warnings.append("news_unified.csv cache exists but could not be read.")

    # Sentiment proxy (works without paid endpoints)
    proxy_df = build_news_sentiment_proxy(news_df) if not news_df.empty else pd.DataFrame()
    if not proxy_df.empty:
        write_csv(proxy_df, DATA_PROCESSED / "news_sentiment_proxy.csv")
    else:
        p_cache = DATA_PROCESSED / "news_sentiment_proxy.csv"
        if p_cache.exists():
            try:
                proxy_df = pd.read_csv(p_cache)
                refresh_warnings.append("Using cached news_sentiment_proxy.csv due to refresh failure.")
            except Exception:
                refresh_warnings.append("news_sentiment_proxy.csv cache exists but could not be read.")

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
    if comps.empty:
        raise RuntimeError("No comps snapshot available (live or cache), cannot score decision.")
    decision = compute_decision_with_peers_and_news(comps, news_summary, proxy_row)

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

    provider_health = {
        "as_of": AS_OF,
        "primary": PRIMARY,
        "provider_priority": provider_priority,
        "fmp_api_key_present": bool(fmp_key),
        "massive_api_key_present": bool(massive_key),
        "checks": checks,
    }
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

    source_hint = "fmp_paid" if (checks and checks[0].get("ok")) else ("raw_cache" if (DATA_RAW / "quotes_universe_raw.csv").exists() else "unavailable")
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

    write_json(
        {
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
            "news_sources_enabled": ["sec", "finnhub"],
            "evidence_files": {
                "csv": f"data/processed/news_evidence_{PRIMARY}.csv",
                "html": f"outputs/news_evidence_{PRIMARY}.html",
            },
            "refresh_warnings": refresh_warnings,
            "provider_health_file": f"outputs/provider_health_{PRIMARY}.json",
            "metric_provider_used_file": f"outputs/metric_provider_used_{PRIMARY}.json",
            "metric_provider_used": metric_provider_used,
        },
        OUTPUTS / "decision_summary.json",
    )

    write_json(
        {
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
                "outputs/decision_explanation.json",
            ],
            "refresh_warnings": refresh_warnings,
        },
        OUTPUTS / "decision_explanation.json",
    )

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
