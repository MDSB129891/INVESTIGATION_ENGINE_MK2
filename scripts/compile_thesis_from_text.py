#!/usr/bin/env python3
import argparse, json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

def normalize_text(s: str) -> str:
    return " ".join((s or "").strip().split())

def keyword_match(text: str, keywords):
    t = (text or "").lower()
    return any(k in t for k in keywords)


def _load_company_intel_sector(ticker: str) -> str:
    p = ROOT / "outputs" / f"company_intel_{ticker.upper()}.json"
    try:
        if p.exists():
            j = json.loads(p.read_text(encoding="utf-8"))
            company = j.get("company", {}) if isinstance(j, dict) else {}
            sector = str(company.get("sector") or "").strip()
            industry = str(company.get("industry") or "").strip()
            return f"{sector} {industry}".strip().lower()
    except Exception:
        pass
    return ""


def _detect_profile(ticker: str, thesis_text: str) -> str:
    text = f"{thesis_text} {_load_company_intel_sector(ticker)}".lower()
    if keyword_match(text, ["bank", "banks", "financial", "insurance", "asset manager", "broker", "lender", "credit"]):
        return "financial"
    if keyword_match(text, ["utility", "utilities", "telecom", "defensive", "consumer staples", "pipeline"]):
        return "defensive"
    if keyword_match(text, ["biotech", "pharma", "semiconductor", "ai", "cloud", "software", "internet", "growth"]):
        return "growth"
    if keyword_match(text, ["energy", "oil", "gas", "mining", "materials"]):
        return "cyclical_commodity"
    return "balanced"


def _profile_thresholds(profile: str) -> dict:
    # Industry-aware defaults so one-size-fits-all does not penalize entire sectors.
    if profile == "financial":
        return {
            "rev_yoy_min": 4.0,
            "fcf_positive_min": 0.0,
            "fcf_margin_min": 2.0,
            "fcf_yield_min": 2.0,
            "news_shock_min": -25.0,
            "risk_tag_max": 5,
        }
    if profile == "defensive":
        return {
            "rev_yoy_min": 3.0,
            "fcf_positive_min": 0.0,
            "fcf_margin_min": 4.0,
            "fcf_yield_min": 2.5,
            "news_shock_min": -22.0,
            "risk_tag_max": 4,
        }
    if profile == "growth":
        return {
            "rev_yoy_min": 10.0,
            "fcf_positive_min": 0.0,
            "fcf_margin_min": 0.0,
            "fcf_yield_min": 1.0,
            "news_shock_min": -18.0,
            "risk_tag_max": 3,
        }
    if profile == "cyclical_commodity":
        return {
            "rev_yoy_min": 5.0,
            "fcf_positive_min": 0.0,
            "fcf_margin_min": 3.0,
            "fcf_yield_min": 2.0,
            "news_shock_min": -24.0,
            "risk_tag_max": 5,
        }
    # balanced default
    return {
        "rev_yoy_min": 8.0,
        "fcf_positive_min": 0.0,
        "fcf_margin_min": 5.0,
        "fcf_yield_min": 3.0,
        "news_shock_min": -20.0,
        "risk_tag_max": 3,
    }


def build_template_claims(ticker: str, thesis_text: str):
    """
    Map plain-English thesis text to a set of measurable claims.

    NOTE: This is intentionally conservative and uses metrics you already have:
    - fcf_yield_pct, latest_fcf_margin_pct, latest_free_cash_flow, latest_revenue_yoy_pct
    - news_shock_30d, risk_*_neg_30d (from news_risk_summary)
    - latest_net_debt_to_fcf (if available in your metric lookup pipeline)
    """
    t = thesis_text.lower()
    profile = _detect_profile(ticker, thesis_text)
    th = _profile_thresholds(profile)

    # Base "always-on" sanity claims (good business health)
    claims = [
        {"id": "c1", "metric": "latest_revenue_yoy_pct", "operator": ">=", "threshold": th["rev_yoy_min"],
         "rationale": "Growth should stay positive in the base case."},
        {"id": "c2", "metric": "latest_free_cash_flow", "operator": ">", "threshold": th["fcf_positive_min"],
         "rationale": "Business should produce positive free cash flow."},
        {"id": "c3", "metric": "latest_fcf_margin_pct", "operator": ">=", "threshold": th["fcf_margin_min"],
         "rationale": "Cash efficiency shouldn't collapse."},
        {"id": "c4", "metric": "fcf_yield_pct", "operator": ">=", "threshold": th["fcf_yield_min"],
         "rationale": "Valuation should not be extremely stretched versus cash generation."},
    ]

    # Risk/news claims (default gentle guardrails)
    claims += [
        {"id": "c5", "metric": "news_shock_30d", "operator": ">=", "threshold": th["news_shock_min"],
         "rationale": "Avoid severe negative headline shock over the last 30 days."},
        {"id": "c6", "metric": "risk_regulatory_neg_30d", "operator": "<=", "threshold": th["risk_tag_max"],
         "rationale": "Regulatory pressure should not spike in the last 30 days."},
        {"id": "c7", "metric": "risk_insurance_neg_30d", "operator": "<=", "threshold": th["risk_tag_max"],
         "rationale": "Insurance-related negative headlines should not spike in the last 30 days."},
        {"id": "c8", "metric": "risk_labor_neg_30d", "operator": "<=", "threshold": th["risk_tag_max"],
         "rationale": "Labor-related negative headlines should not spike in the last 30 days."},
    ]

    # If thesis is about drivers becoming employees / worker classification:
    if keyword_match(t, ["employee", "employees", "classified", "classification", "contractor", "contractors", "labor", "drivers become"]):
        # Tighten labor/regulatory guardrails and focus on margin/cash risk
        for c in claims:
            if c["metric"] == "risk_labor_neg_30d":
                c["threshold"] = 2
                c["rationale"] = "Worker classification risk should stay calm (labor headlines)."
            if c["metric"] == "risk_regulatory_neg_30d":
                c["threshold"] = 2
                c["rationale"] = "Worker classification risk should stay calm (regulatory headlines)."
            if c["metric"] == "latest_fcf_margin_pct":
                c["threshold"] = 8.0
                c["rationale"] = "If labor costs rise, margins get hit first — require cushion."
            if c["metric"] == "fcf_yield_pct":
                c["threshold"] = 4.5
                c["rationale"] = "If risk rises, valuation should compensate via cash yield."

    # If thesis talks about stock dropping a lot, add a "bear cone" expectation (optional metric)
    if keyword_match(t, ["drop", "crash", "significantly", "downside", "collapse"]):
        # This only evaluates if DCF cone values exist in metric lookup (your Friday decision core writes bear/base/bull prices)
        claims.append({
            "id": "c9",
            "metric": "bear_price",  # exists in export/CANON_{T}/{T}_DECISION_CORE.json metrics
            "operator": "<=",
            "threshold": None,  # leave None; this is informational unless you set it
            "rationale": "Bear case price exists in the DCF cone; use HUD for magnitude.",
            "note": "Informational claim: set a threshold if you want an automatic PASS/FAIL."
        })

    return claims, profile, th

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--text", required=True, help="Plain-English thesis text")
    ap.add_argument("--out", default=None, help="Output JSON path (default: theses/{T}_thesis_custom.json)")
    args = ap.parse_args()

    T = args.ticker.strip().upper()
    thesis_text = normalize_text(args.text)

    out_path = Path(args.out) if args.out else Path(f"theses/{T}_thesis_custom.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    claims, profile, thresholds = build_template_claims(T, thesis_text)

    payload = {
        "ticker": T,
        "name": f"{T}: Custom thesis",
        "headline": f"{T}: {thesis_text[:120]}{'...' if len(thesis_text) > 120 else ''}",
        "description": thesis_text,
        "generated_utc": now_utc(),
        "profile": profile,
        "profile_thresholds": thresholds,
        "claims": claims,
    }

    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"✅ wrote thesis json: {out_path}")

if __name__ == "__main__":
    main()
