#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed"
OUT = ROOT / "outputs"
OUT.mkdir(parents=True, exist_ok=True)

def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

def f(x: Any) -> Optional[float]:
    try:
        if x is None: return None
        if isinstance(x, str) and x.strip() == "": return None
        return float(x)
    except Exception:
        return None

def read_csv(p: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(p)
    except Exception:
        return pd.DataFrame()

def get_latest_fundamentals() -> Dict[str, Any]:
    df = read_csv(DATA / "fundamentals_annual_history.csv")
    if df.empty: return {}
    if "period_end" in df.columns:
        df = df.sort_values("period_end")
    last = df.iloc[-1].to_dict()
    return last

def get_news_proxy_row(ticker: str) -> Dict[str, Any]:
    df = read_csv(DATA / "news_sentiment_proxy.csv")
    if df.empty or "ticker" not in df.columns: return {}
    r = df[df["ticker"].astype(str).str.upper() == ticker.upper()]
    return {} if r.empty else r.iloc[0].to_dict()

def get_risk_map(ticker: str) -> Dict[str, Any]:
    df = read_csv(DATA / "news_risk_dashboard.csv")
    if df.empty or "ticker" not in df.columns: return {}
    r = df[df["ticker"].astype(str).str.upper() == ticker.upper()].copy()
    if r.empty: return {}
    alias = {"LABOUR":"LABOR","WORKFORCE":"LABOR","EMPLOYMENT":"LABOR"}
    out = {}
    for _, rr in r.iterrows():
        tag = alias.get(str(rr.get("risk_tag","OTHER")).upper(), str(rr.get("risk_tag","OTHER")).upper())
        out[f"risk_{tag.lower()}_neg_30d"] = rr.get("neg_count_30d", 0)
        out[f"risk_{tag.lower()}_shock_30d"] = rr.get("shock_30d", 0)
    return out

def main(ticker: str):
    fund = get_latest_fundamentals()
    proxy = get_news_proxy_row(ticker)
    risk = get_risk_map(ticker)

    revenue_yoy = f(fund.get("revenue_yoy_pct"))
    fcf = f(fund.get("free_cash_flow"))
    fcf_margin = f(fund.get("fcf_margin_pct"))
    news_shock = f(proxy.get("shock_30d"))

    alerts = []

    # Thesis-breaker style triggers (simple red lines)
    if revenue_yoy is not None and revenue_yoy < 5:
        alerts.append({"id":"rev_slowdown", "severity":"HIGH", "message":"Revenue growth slowed to low single digits (<5%). Thesis may weaken."})
    if fcf is not None and fcf < 0:
        alerts.append({"id":"fcf_negative", "severity":"HIGH", "message":"Free Cash Flow is negative. Thesis may break if sustained."})
    if fcf_margin is not None and fcf_margin < 5:
        alerts.append({"id":"margin_weak", "severity":"MED", "message":"FCF margin is weak (<5%). Company is not converting sales into cash efficiently."})
    if news_shock is not None and news_shock < -20:
        alerts.append({"id":"headline_crisis", "severity":"MED", "message":"News shock is severe (<-20). Risks may be escalating."})

    # Risk-tag spikes
    for tag in ["insurance","regulatory","labor","safety"]:
        k = f"risk_{tag}_neg_30d"
        v = f(risk.get(k, 0)) or 0
        if v >= 6:
            alerts.append({"id":f"{tag}_spike", "severity":"MED", "message":f"{tag.title()} negatives are elevated (>=6 in 30d). Read clickpack top items."})

    payload = {
        "ticker": ticker.upper(),
        "generated_utc": utc_now(),
        "inputs": {
            "revenue_yoy_pct": revenue_yoy,
            "free_cash_flow": fcf,
            "fcf_margin_pct": fcf_margin,
            "news_shock_30d": news_shock,
            "risk_counts_30d": {k: risk.get(k) for k in sorted(risk.keys()) if k.endswith("_neg_30d")},
        },
        "alerts": alerts,
        "alert_count": len(alerts),
    }

    out = OUT / f"alerts_{ticker.upper()}.json"
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"DONE ✅ alerts created: {out}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", default=os.getenv("TICKER", "").strip().upper())
    args = ap.parse_args()
    if not args.ticker:
        raise SystemExit("Missing ticker. Pass --ticker TICKER or set TICKER env var.")
    main(args.ticker)
