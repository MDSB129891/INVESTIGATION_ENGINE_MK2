# Single source of truth for metric units
# unit codes:
#  - usd   : dollars
#  - pct   : percent (0-100 display)
#  - x     : multiple (e.g., 3.2x)
#  - count : integer count
#  - score : unitless score (e.g., news shock)
#  - num   : plain number

METRIC_SCHEMA = {
    # Pricing / valuation
    "price_used": "usd",
    "market_cap_used": "usd",
    "market_cap": "usd",
    "enterprise_value": "usd",
    "ev_sales": "x",
    "pe_ratio": "x",
    "ev_ebitda": "x",

    # Cash / balance sheet
    "fcf_ttm": "usd",
    "net_debt": "usd",

    # Margins / yields
    "fcf_margin": "pct",
    "fcf_yield": "pct",
    "gross_margin": "pct",
    "operating_margin": "pct",

    # DCF cone outputs
    "bear_price": "usd",
    "base_price": "usd",
    "bull_price": "usd",

    # News / risk
    "news_shock": "score",
    "risk_total_30d": "count",
    "risk_labor_neg_30d": "count",
    "risk_regulatory_neg_30d": "count",
    "risk_insurance_neg_30d": "count",
    "risk_safety_neg_30d": "count",
    "risk_competition_neg_30d": "count",
}
