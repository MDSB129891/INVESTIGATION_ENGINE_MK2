#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_PROCESSED = ROOT / "data" / "processed"
THESES = ROOT / "theses"

DEFAULT_TICKER = "AAPL"

import argparse



def safe_read_csv(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def coerce_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        if isinstance(x, str) and x.strip() == "":
            return None
        return float(x)
    except Exception:
        return None


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def build_metrics_snapshot(ticker: str) -> Dict[str, Any]:
    """
    Reads processed files your pipeline generates.
    Returns a metrics dict with keys referenced inside thesis JSON.
    """
    out: Dict[str, Any] = {}

    # Annual fundamentals history
    f = safe_read_csv(DATA_PROCESSED / "fundamentals_annual_history.csv")
    if not f.empty:
        if "period_end" in f.columns:
            f = f.sort_values("period_end")
        last = f.iloc[-1]

        out["latest_period_end"] = last.get("period_end")
        out["latest_revenue_yoy_pct"] = last.get("revenue_yoy_pct")
        out["latest_free_cash_flow"] = last.get("free_cash_flow")
        out["latest_fcf_margin_pct"] = last.get("fcf_margin_pct")

        cash = coerce_float(last.get("cash"))
        debt = coerce_float(last.get("debt"))
        out["latest_cash"] = cash
        out["latest_debt"] = debt
        if cash is not None and debt is not None:
            out["latest_net_debt"] = debt - cash
            fcf = coerce_float(out.get("latest_free_cash_flow"))
            if fcf and fcf != 0:
                out["latest_net_debt_to_fcf"] = (debt - cash) / fcf

    # Comps snapshot (valuation)
    comps = safe_read_csv(DATA_PROCESSED / "comps_snapshot.csv")
    if not comps.empty and "ticker" in comps.columns:
        r = comps[comps["ticker"].astype(str).str.upper() == ticker.upper()]
        if not r.empty:
            row = r.iloc[0].to_dict()
            out["price"] = row.get("price")
            out["market_cap"] = row.get("market_cap")
            fy = row.get("fcf_yield")
            if fy is not None:
                try:
                    out["fcf_yield_pct"] = float(fy) * 100.0
                except Exception:
                    out["fcf_yield_pct"] = fy

    # News proxy
    proxy = safe_read_csv(DATA_PROCESSED / "news_sentiment_proxy.csv")
    if not proxy.empty and "ticker" in proxy.columns:
        r = proxy[proxy["ticker"].astype(str).str.upper() == ticker.upper()]
        if not r.empty:
            row = r.iloc[0].to_dict()
            out["news_shock_30d"] = row.get("shock_30d")
            out["news_neg_30d"] = row.get("neg_30d")
            out["news_articles_30d"] = row.get("articles_30d")
            out["news_proxy_score_30d"] = row.get("proxy_score_30d")

    # Risk dashboard (tag counts) — normalize + fill missing
    risk = safe_read_csv(DATA_PROCESSED / "news_risk_dashboard.csv")
    if not risk.empty and "ticker" in risk.columns:
        rd = risk[risk["ticker"].astype(str).str.upper() == ticker.upper()].copy()
        if not rd.empty and "risk_tag" in rd.columns:
            alias = {
                "LABOUR": "LABOR",
                "WORKFORCE": "LABOR",
                "EMPLOYMENT": "LABOR",
            }
            for _, rr in rd.iterrows():
                raw_tag = str(rr.get("risk_tag", "OTHER")).strip().upper()
                tag = alias.get(raw_tag, raw_tag)
                out[f"risk_{tag.lower()}_neg_30d"] = rr.get("neg_count_30d")

    # Ensure common tags exist (prevents UNKNOWN)
    for t in ["insurance", "regulatory", "labor", "safety"]:
        out.setdefault(f"risk_{t}_neg_30d", 0)

    return out


def build_suite(ticker: str, m: Dict[str, Any]) -> Dict[str, dict]:
    """
    Smart defaults:
    - Bear: conservative + requires cheaper valuation and quiet risk
    - Base: normal world
    - Bull: optimistic but plausible
    """
    rev = coerce_float(m.get("latest_revenue_yoy_pct")) or 10.0
    fcfm = coerce_float(m.get("latest_fcf_margin_pct")) or 10.0
    fy = coerce_float(m.get("fcf_yield_pct")) or 4.0
    shock = coerce_float(m.get("news_shock_30d")) or -12.0

    ndebt_fcf = coerce_float(m.get("latest_net_debt_to_fcf"))

    ins = int(coerce_float(m.get("risk_insurance_neg_30d")) or 0)
    reg = int(coerce_float(m.get("risk_regulatory_neg_30d")) or 0)
    lab = int(coerce_float(m.get("risk_labor_neg_30d")) or 0)

    base_rev = clamp(0.60 * rev, 8.0, 20.0)
    bull_rev = clamp(0.85 * rev, 12.0, 30.0)
    bear_rev = clamp(0.40 * rev, 4.0, 12.0)

    base_fcfm = clamp(0.60 * fcfm, 8.0, 20.0)
    bull_fcfm = clamp(0.80 * fcfm, 12.0, 30.0)
    bear_fcfm = clamp(0.50 * fcfm, 6.0, 15.0)

    base_yield = clamp(0.70 * fy, 3.0, 8.0)
    bull_yield = clamp(0.55 * fy, 2.0, 6.0)
    bear_yield = clamp(0.90 * fy, 5.0, 12.0)

    base_shock = min(-5.0, shock)
    bear_shock = max(base_shock, -10.0)
    bull_shock = min(base_shock, -20.0)

    base_ins = max(3, ins)
    bear_ins = max(2, ins)
    bull_ins = max(4, ins + 1)

    base_reg = max(3, reg)
    bear_reg = max(2, reg)
    bull_reg = max(4, reg + 1)

    base_lab = max(3, lab)
    bear_lab = max(2, lab)
    bull_lab = max(4, lab + 1)

    def net_debt_claim(max_years: float, weight: int):
        return {
            "id": "balance_net_debt_to_fcf",
            "statement": f"Debt burden is manageable (net debt <= ~{max_years} years of free cash flow)",
            "metric": "latest_net_debt_to_fcf",
            "operator": "<=",
            "threshold": max_years,
            "weight": weight,
        }

    base_claims = [
        {"id": "rev_growth", "statement": "Revenue is still growing at a healthy pace", "metric": "latest_revenue_yoy_pct", "operator": ">=", "threshold": round(base_rev, 1), "weight": 2},
        {"id": "fcf_positive", "statement": "Free cash flow is positive (business generates real cash)", "metric": "latest_free_cash_flow", "operator": ">", "threshold": 0, "weight": 3},
        {"id": "fcf_margin", "statement": "Free cash flow margin is solid (company converts sales into cash)", "metric": "latest_fcf_margin_pct", "operator": ">=", "threshold": round(base_fcfm, 1), "weight": 2},
        {"id": "valuation_fcf_yield", "statement": "Valuation is not expensive versus cash (FCF yield is decent)", "metric": "fcf_yield_pct", "operator": ">=", "threshold": round(base_yield, 1), "weight": 2},
        {"id": "news_shock_ok", "statement": "Recent news shock is not severe (not a headline crisis)", "metric": "news_shock_30d", "operator": ">=", "threshold": round(base_shock, 1), "weight": 1},
        {"id": "insurance_not_spiking", "statement": "Insurance risk is not spiking recently", "metric": "risk_insurance_neg_30d", "operator": "<=", "threshold": base_ins, "weight": 1},
        {"id": "regulatory_not_spiking", "statement": "Regulatory risk is not spiking recently", "metric": "risk_regulatory_neg_30d", "operator": "<=", "threshold": base_reg, "weight": 1},
        {"id": "labor_not_spiking", "statement": "Labor risk is not spiking recently", "metric": "risk_labor_neg_30d", "operator": "<=", "threshold": base_lab, "weight": 1},
    ]

    bull_claims = [
        {"id": "rev_growth", "statement": "Revenue growth stays strong (upside scenario)", "metric": "latest_revenue_yoy_pct", "operator": ">=", "threshold": round(bull_rev, 1), "weight": 3},
        {"id": "fcf_positive", "statement": "Free cash flow stays positive", "metric": "latest_free_cash_flow", "operator": ">", "threshold": 0, "weight": 3},
        {"id": "fcf_margin", "statement": "Cash conversion stays excellent (high FCF margin)", "metric": "latest_fcf_margin_pct", "operator": ">=", "threshold": round(bull_fcfm, 1), "weight": 3},
        {"id": "valuation_ok", "statement": "Valuation stays reasonable even if investors get more optimistic", "metric": "fcf_yield_pct", "operator": ">=", "threshold": round(bull_yield, 1), "weight": 1},
        {"id": "news_shock_ok", "statement": "News risk is not a major crisis even in a noisy world", "metric": "news_shock_30d", "operator": ">=", "threshold": round(bull_shock, 1), "weight": 1},
        {"id": "insurance_ok", "statement": "Insurance risk stays manageable", "metric": "risk_insurance_neg_30d", "operator": "<=", "threshold": bull_ins, "weight": 1},
    ]

    bear_claims = [
        {"id": "fcf_positive", "statement": "Free cash flow is still positive even if conditions worsen", "metric": "latest_free_cash_flow", "operator": ">", "threshold": 0, "weight": 4},
        {"id": "rev_not_collapsing", "statement": "Revenue growth does not collapse", "metric": "latest_revenue_yoy_pct", "operator": ">=", "threshold": round(bear_rev, 1), "weight": 2},
        {"id": "fcf_margin_floor", "statement": "Cash conversion stays above a minimum floor", "metric": "latest_fcf_margin_pct", "operator": ">=", "threshold": round(bear_fcfm, 1), "weight": 2},
        {"id": "valuation_must_be_cheap", "statement": "Stock is cheap enough to compensate for risks (higher required cash yield)", "metric": "fcf_yield_pct", "operator": ">=", "threshold": round(bear_yield, 1), "weight": 3},
        {"id": "news_must_be_quiet", "statement": "News risk is not escalating (quiet headlines)", "metric": "news_shock_30d", "operator": ">=", "threshold": round(bear_shock, 1), "weight": 2},
        {"id": "insurance_must_be_low", "statement": "Insurance risk stays low (if this spikes, it can be structural)", "metric": "risk_insurance_neg_30d", "operator": "<=", "threshold": bear_ins, "weight": 2},
        {"id": "regulatory_must_be_low", "statement": "Regulatory risk stays low", "metric": "risk_regulatory_neg_30d", "operator": "<=", "threshold": bear_reg, "weight": 1},
        {"id": "labor_must_be_low", "statement": "Labor risk stays low", "metric": "risk_labor_neg_30d", "operator": "<=", "threshold": bear_lab, "weight": 1},
    ]

    if ndebt_fcf is not None:
        base_claims.append(net_debt_claim(max_years=3.0, weight=1))
        bull_claims.append(net_debt_claim(max_years=4.0, weight=1))
        bear_claims.append(net_debt_claim(max_years=2.5, weight=2))

    return {
        "base": {
            "name": f"{ticker}: Base case — growth + cash generation supports the thesis",
            "ticker": ticker,
            "description": "Normal world: we want healthy growth, strong free cash flow, reasonable valuation, and non-escalating risk headlines.",
            "claims": base_claims,
        },
        "bull": {
            "name": f"{ticker}: Bull case — strong execution and upside scenario",
            "ticker": ticker,
            "description": "Good world: growth stays strong, margins stay high, and valuation can be a bit richer without breaking the story.",
            "claims": bull_claims,
        },
        "bear": {
            "name": f"{ticker}: Bear case — only buy if resilient + cheap + risks quiet",
            "ticker": ticker,
            "description": "Bad world: only buy if cash stays positive, valuation is cheap enough, and risk headlines are not escalating.",
            "claims": bear_claims,
        },
    }


def main(ticker: str = DEFAULT_TICKER):
    ticker = ticker
    THESES.mkdir(parents=True, exist_ok=True)

    metrics = build_metrics_snapshot(ticker)
    suite = build_suite(ticker, metrics)

    (THESES / f"{ticker}_thesis_base.json").write_text(json.dumps(suite["base"], indent=2), encoding="utf-8")
    (THESES / f"{ticker}_thesis_bull.json").write_text(json.dumps(suite["bull"], indent=2), encoding="utf-8")
    (THESES / f"{ticker}_thesis_bear.json").write_text(json.dumps(suite["bear"], indent=2), encoding="utf-8")

    print("DONE ✅ Smart thesis suite generated:")
    print(f"- {THESES / f'{ticker}_thesis_base.json'}")
    print(f"- {THESES / f'{ticker}_thesis_bull.json'}")
    print(f"- {THESES / f'{ticker}_thesis_bear.json'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", default=DEFAULT_TICKER)
    args = ap.parse_args()
    main(args.ticker)
