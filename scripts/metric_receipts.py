from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Optional

@dataclass(frozen=True)
class Receipt:
    metric: str
    label: str
    plain: str
    units: str
    source_file_hint: str
    source_key_hint: str

# Keep it simple + human-friendly.
# You can extend this list anytime without breaking anything.
RECEIPTS: Dict[str, Receipt] = {
    "latest_revenue_yoy_pct": Receipt(
        metric="latest_revenue_yoy_pct",
        label="Revenue growth (YoY)",
        plain="How fast sales are growing vs last year. Growth supports the story, shrinkage is a warning sign.",
        units="pct",
        source_file_hint="data/processed/fundamentals_annual_history.csv",
        source_key_hint="revenue_yoy_pct"
    ),
    "latest_free_cash_flow": Receipt(
        metric="latest_free_cash_flow",
        label="Free cash flow (TTM)",
        plain="Cash left after paying bills and necessary investment. Positive FCF = flexibility.",
        units="usd",
        source_file_hint="data/processed/fundamentals_annual_history.csv",
        source_key_hint="free_cash_flow"
    ),
    "latest_fcf_margin_pct": Receipt(
        metric="latest_fcf_margin_pct",
        label="FCF margin (TTM)",
        plain="Of every $1 of sales, how much becomes real cash. Higher = more efficient.",
        units="pct",
        source_file_hint="data/processed/fundamentals_annual_history.csv",
        source_key_hint="fcf_margin_pct"
    ),
    "fcf_yield_pct": Receipt(
        metric="fcf_yield_pct",
        label="FCF yield",
        plain="Cash return vs what you pay for the company. Higher yield generally means cheaper valuation (all else equal).",
        units="pct",
        source_file_hint="export/CANON_{T}/{T}_DECISION_CORE.json",
        source_key_hint="metrics.fcf_yield (or comps_snapshot fcf_yield_pct)"
    ),
    "news_shock_30d": Receipt(
        metric="news_shock_30d",
        label="News shock (30d)",
        plain="Headline intensity score. More negative = worse headlines. This is NOT fundamentals, it’s risk temperature.",
        units="score",
        source_file_hint="export/CANON_{T}/news_risk_summary_{T}.json",
        source_key_hint="news_shock_30d"
    ),
    "risk_labor_neg_30d": Receipt(
        metric="risk_labor_neg_30d",
        label="Labor risk hits (30d)",
        plain="Count of negative labor-tagged news in last 30 days (lawsuits, classification, strikes, etc).",
        units="count",
        source_file_hint="export/CANON_{T}/news_risk_summary_{T}.json",
        source_key_hint="risk_labor_neg_30d"
    ),
    "risk_regulatory_neg_30d": Receipt(
        metric="risk_regulatory_neg_30d",
        label="Regulatory risk hits (30d)",
        plain="Count of negative regulatory-tagged news in last 30 days (rules, fines, bans, compliance actions).",
        units="count",
        source_file_hint="export/CANON_{T}/news_risk_summary_{T}.json",
        source_key_hint="risk_regulatory_neg_30d"
    ),
    "risk_insurance_neg_30d": Receipt(
        metric="risk_insurance_neg_30d",
        label="Insurance risk hits (30d)",
        plain="Count of negative insurance-tagged news in last 30 days (coverage, claims, pricing, litigation).",
        units="count",
        source_file_hint="export/CANON_{T}/news_risk_summary_{T}.json",
        source_key_hint="risk_insurance_neg_30d"
    ),
}

def get_receipt(metric: str) -> Optional[Receipt]:
    return RECEIPTS.get(metric)
