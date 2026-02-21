from __future__ import annotations

from typing import Any, Dict

# Unit tags:
# - usd: dollars
# - pct: percent (expects fraction or already-percent; we handle both)
# - x: multiple (EV/EBITDA etc)
# - count: integer count
# - num: plain number
# - date: iso date string (we keep as-is)

UNITS: Dict[str, str] = {
    # Core financials
    "revenue_ttm": "usd",
    "ebitda_ttm": "usd",
    "fcf_ttm": "usd",
    "market_cap": "usd",
    "net_debt": "usd",

    # Ratios
    "fcf_margin": "pct",
    "fcf_yield": "pct",
    "gross_margin": "pct",
    "operating_margin": "pct",
    "ev_ebitda": "x",
    "pe": "x",

    # News / risk
    "news_shock_30d": "num",
    "risk_labor_neg_30d": "count",
    "risk_regulatory_neg_30d": "count",
    "risk_insurance_neg_30d": "count",
    "risk_safety_neg_30d": "count",
    "risk_competition_neg_30d": "count",
    "risk_total_30d": "count",
    "generated_at": "date",
}

def _fmt_usd(v: float) -> str:
    # Human readable: $12.3B, $450M, $123K
    abs_v = abs(v)
    if abs_v >= 1e12:
        return f"${v/1e12:.2f}T"
    if abs_v >= 1e9:
        return f"${v/1e9:.2f}B"
    if abs_v >= 1e6:
        return f"${v/1e6:.2f}M"
    if abs_v >= 1e3:
        return f"${v/1e3:.2f}K"
    return f"${v:,.0f}"

def _fmt_pct(v: float) -> str:
    # Accept either 0.0644 or 6.44
    if abs(v) <= 1.5:
        v = v * 100.0
    return f"{v:.2f}%"

def _fmt_x(v: float) -> str:
    return f"{v:.2f}x"

def _fmt_count(v: float) -> str:
    return str(int(round(v)))

def _fmt_num(v: float) -> str:
    # Keep compact but readable
    if abs(v) >= 1000:
        return f"{v:,.0f}"
    if abs(v) >= 10:
        return f"{v:.1f}"
    return f"{v:.2f}"

def fmt(key: str, value: Any) -> str:
    if value is None:
        return "N/A"

    unit = UNITS.get(key, "num")

    # If it's already a string and unit is date/text, just return it
    if isinstance(value, str):
        return value if value.strip() else "N/A"

    try:
        v = float(value)
    except Exception:
        return str(value)

    if unit == "usd":
        return _fmt_usd(v)
    if unit == "pct":
        return _fmt_pct(v)
    if unit == "x":
        return _fmt_x(v)
    if unit == "count":
        return _fmt_count(v)
    if unit == "date":
        return str(value)
    return _fmt_num(v)

def label(key: str) -> str:
    # Simple prettifier: fcf_ttm -> FCF TTM
    return key.replace("_", " ").upper()


# --- KEY-BASED UNITS (schema driven) ---
def unit_for_key(key: str) -> str:
    """
    Returns the unit string for a metric key using metric_schema.py.
    Falls back to guessing.
    """
    try:
        from scripts.friday.metric_schema import METRIC_SCHEMA
        u = METRIC_SCHEMA.get(key)
        if u:
            return u
    except Exception:
        pass

    # fallback guesses
    k = (key or "").lower()
    if "yield" in k or "margin" in k or k.endswith("_pct") or "pct" in k:
        return "pct"
    if "multiple" in k or "ratio" in k or k.startswith("ev_") or k in ("pe", "pe_ratio", "ev_ebitda"):
        return "x"
    if "risk_" in k or k.endswith("_count") or "count" in k:
        return "count"
    if "cap" in k or "revenue" in k or "debt" in k or "cash" in k or "price" in k or "fcf" in k:
        return "usd"
    if "shock" in k or "score" in k:
        return "score"
    return "num"

def fmt_key(key: str, value):
    """Format a metric by key using metric_schema."""
    return fmt(unit_for_key(key), value)

# --- Schema-first helpers (auto-injected) ---
def fmt_unit(unit: str) -> str:
    u = (unit or "").lower().strip()
    return {"usd":"$", "pct":"%", "x":"x", "count":"#", "score":"score", "num":"num"}.get(u, u)
