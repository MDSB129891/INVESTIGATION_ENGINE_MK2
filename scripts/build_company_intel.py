#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from analytics.provider_net import request_with_resilience

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"


def _sf(v):
    try:
        if v is None:
            return None
        x = float(v)
        if x != x:
            return None
        return x
    except Exception:
        return None


def _pick(*vals):
    for v in vals:
        if v not in (None, "", "null"):
            return v
    return None


def _fmp_profile(t: str, key: str):
    if not key:
        return {}
    try:
        r = request_with_resilience(
            "fmp",
            "https://financialmodelingprep.com/stable/profile",
            params={"symbol": t, "apikey": key},
            max_retries=2,
        )
        arr = r.json() or []
        if isinstance(arr, list) and arr:
            x = arr[0] or {}
            return {
                "name": x.get("companyName") or x.get("name"),
                "sector": x.get("sector"),
                "industry": x.get("industry"),
                "country": x.get("country"),
                "exchange": x.get("exchangeShortName") or x.get("exchange"),
                "website": x.get("website"),
                "description": x.get("description"),
                "market_cap": _sf(x.get("mktCap") or x.get("marketCap")),
                "price": _sf(x.get("price")),
                "source_ok": True,
            }
    except Exception:
        pass
    return {"source_ok": False}


def _massive_ref(t: str, key: str):
    if not key:
        return {}
    out = {"source_ok": False}
    try:
        rr = request_with_resilience(
            "massive",
            f"https://api.polygon.io/v3/reference/tickers/{t}",
            params={"apiKey": key},
            max_retries=2,
        )
        j = rr.json() or {}
        x = j.get("results") or {}
        out.update(
            {
                "name": x.get("name"),
                "sector": x.get("sic_description"),
                "country": x.get("locale"),
                "exchange": x.get("primary_exchange"),
                "market_cap": _sf(x.get("market_cap")),
                "description": x.get("description"),
                "source_ok": True,
            }
        )
    except Exception:
        pass
    try:
        rs = request_with_resilience(
            "massive",
            f"https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers/{t}",
            params={"apiKey": key},
            max_retries=2,
        )
        s = (rs.json() or {}).get("ticker") or {}
        out["price"] = _sf(_pick((s.get("day") or {}).get("c"), (s.get("lastTrade") or {}).get("p"), (s.get("prevDay") or {}).get("c")))
    except Exception:
        pass
    return out


def _alpha_overview(t: str, key: str):
    if not key:
        return {}
    try:
        r = request_with_resilience(
            "alphavantage",
            "https://www.alphavantage.co/query",
            params={"function": "OVERVIEW", "symbol": t, "apikey": key},
            max_retries=2,
        )
        x = r.json() or {}
        if isinstance(x, dict) and x.get("Symbol"):
            return {
                "name": x.get("Name"),
                "sector": x.get("Sector"),
                "industry": x.get("Industry"),
                "country": x.get("Country"),
                "exchange": x.get("Exchange"),
                "description": x.get("Description"),
                "market_cap": _sf(x.get("MarketCapitalization")),
                "source_ok": True,
            }
    except Exception:
        pass
    return {"source_ok": False}


def _sec_cik(t: str):
    try:
        r = request_with_resilience("sec", "https://www.sec.gov/files/company_tickers.json", max_retries=2)
        data = r.json() or {}
        tu = t.upper()
        for _, row in data.items():
            if str(row.get("ticker", "")).upper() == tu:
                cik_int = int(row.get("cik_str"))
                return f"{cik_int:010d}"
    except Exception:
        pass
    return None


def main(ticker: str):
    t = ticker.upper().strip()
    fmp_key = (os.getenv("FMP_API_KEY") or "").strip()
    massive_key = (os.getenv("MASSIVE_API_KEY") or os.getenv("POLYGON_API_KEY") or "").strip()
    alpha_key = (
        os.getenv("ALPHAVANTAGE_API_KEY")
        or os.getenv("ALPHA_VANTAGE_API_KEY")
        or os.getenv("ALPHAVANTAGE_KEY")
        or os.getenv("ALPHA_VANTAGE_KEY")
        or os.getenv("AV_API_KEY")
        or ""
    ).strip()

    fmp = _fmp_profile(t, fmp_key)
    massive = _massive_ref(t, massive_key)
    alpha = _alpha_overview(t, alpha_key)
    cik = _sec_cik(t)

    price_vals = [v for v in [_sf(fmp.get("price")), _sf(massive.get("price"))] if v is not None]
    mcap_vals = [v for v in [_sf(fmp.get("market_cap")), _sf(massive.get("market_cap")), _sf(alpha.get("market_cap"))] if v is not None]

    price = price_vals[0] if price_vals else None
    market_cap = mcap_vals[0] if mcap_vals else None
    price_var = None
    mcap_var = None
    if len(price_vals) >= 2:
        den = max(abs(price_vals[0]), abs(price_vals[1]), 1e-9)
        price_var = abs(price_vals[0] - price_vals[1]) / den * 100.0
    if len(mcap_vals) >= 2:
        den = max(abs(mcap_vals[0]), abs(mcap_vals[1]), 1e-9)
        mcap_var = abs(mcap_vals[0] - mcap_vals[1]) / den * 100.0

    name = _pick(fmp.get("name"), massive.get("name"), alpha.get("name"), t)
    sector = _pick(fmp.get("sector"), alpha.get("sector"), massive.get("sector"))
    industry = _pick(fmp.get("industry"), alpha.get("industry"))
    country = _pick(fmp.get("country"), alpha.get("country"), massive.get("country"))
    exchange = _pick(fmp.get("exchange"), alpha.get("exchange"), massive.get("exchange"))
    website = _pick(fmp.get("website"))
    description = _pick(fmp.get("description"), alpha.get("description"), massive.get("description"))

    field_sources = {
        "name": "fmp|massive|alpha",
        "sector": "fmp|alpha|massive",
        "industry": "fmp|alpha",
        "country": "fmp|alpha|massive",
        "exchange": "fmp|alpha|massive",
        "website": "fmp",
        "description": "fmp|alpha|massive",
        "price": "fmp|massive",
        "market_cap": "fmp|massive|alpha",
        "sec_cik": "sec",
    }

    coverage = sum(1 for v in [name, sector, industry, country, exchange, website, description, price, market_cap, cik] if v not in (None, ""))
    confidence = "HIGH" if coverage >= 8 else ("MEDIUM" if coverage >= 5 else "LOW")
    if price_var is not None and price_var > 2.0:
        confidence = "MEDIUM" if confidence == "HIGH" else confidence
    if mcap_var is not None and mcap_var > 8.0:
        confidence = "MEDIUM" if confidence == "HIGH" else confidence

    payload = {
        "ticker": t,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "company": {
            "name": name,
            "sector": sector,
            "industry": industry,
            "country": country,
            "exchange": exchange,
            "website": website,
            "description": description,
            "sec_cik": cik,
        },
        "market": {
            "price": price,
            "market_cap": market_cap,
        },
        "crosscheck": {
            "price_variance_pct_fmp_vs_massive": price_var,
            "market_cap_variance_pct": mcap_var,
        },
        "confidence_grade": confidence,
        "coverage_fields_present": coverage,
        "field_sources": field_sources,
        "provider_health": {
            "fmp_ok": bool(fmp.get("source_ok")),
            "massive_ok": bool(massive.get("source_ok")),
            "alpha_ok": bool(alpha.get("source_ok")),
            "sec_ok": bool(cik),
        },
    }

    OUT.mkdir(parents=True, exist_ok=True)
    j = OUT / f"company_intel_{t}.json"
    h = OUT / f"company_intel_{t}.html"
    j.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    h.write_text(
        f"""<!doctype html><html><head><meta charset='utf-8'><title>Company Intel — {t}</title></head>
<body style='font-family:ui-sans-serif,system-ui;background:#111827;color:#eaf1ff;padding:18px'>
<h2>Company Intel — {t}</h2><pre>{json.dumps(payload, indent=2)}</pre></body></html>""",
        encoding="utf-8",
    )
    print("DONE ✅ wrote:", j)
    print("DONE ✅ wrote:", h)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Build free company profile intelligence from multiple sources.")
    ap.add_argument("--ticker", required=True)
    args = ap.parse_args()
    main(args.ticker)
