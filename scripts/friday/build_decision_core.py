import sys
from pathlib import Path

# Make repo root importable when running this file directly
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.friday.units import fmt_key, unit_for_key, fmt_unit, label


def _load_ev_fields(ticker: str):
    """Return {'enterprise_value': float, 'ev_sales': float} when available."""
    try:
        import pandas as pd
        df = pd.read_csv("data/processed/comps_snapshot.csv")
        if "ticker" not in df.columns:
            return {}
        df["ticker"] = df["ticker"].astype(str).str.upper()
        row = df[df["ticker"] == str(ticker).upper()]
        if row.empty:
            return {}
        r = row.iloc[0]
        out = {}
        if "enterprise_value" in df.columns and pd.notna(r.get("enterprise_value")):
            out["enterprise_value"] = float(r["enterprise_value"])
        if "ev_sales" in df.columns and pd.notna(r.get("ev_sales")):
            out["ev_sales"] = float(r["ev_sales"])
        return out
    except Exception:
        return {}

#!/usr/bin/env python3
import argparse, json, math
from pathlib import Path
from datetime import datetime, timezone
import json as _json

# --- unit symbol helper (auto) ---
_UNIT_SYMBOL_MAP = {"usd":"$", "pct":"%", "x":"x", "count":"#", "score":"score", "num":"num"}
def _unit_sym(u: str) -> str:
    u = (u or "").lower().strip()
    return _UNIT_SYMBOL_MAP.get(u, u)

def _unit_display(u: str) -> str:
    # show both: symbol + code (ex: "$ · usd")
    u2 = (u or "").strip()
    sym = _unit_sym(u2)
    return f"{sym} · {u2}" if u2 else sym

ROOT = Path(__file__).resolve().parents[2]   # repo root
CANON = ROOT / "export"
OUTS  = ROOT / "outputs"
THES  = ROOT / "theses"

def _load_json(path: Path):
    if not path.exists():
        return None
    return _json.loads(path.read_text(encoding="utf-8"))

def _label(key: str) -> str:
    return key.replace("_", " ").upper()

def _fmt_usd(v: float) -> str:
    a = abs(v)
    if a >= 1e12: return f"${v/1e12:.2f}T"
    if a >= 1e9:  return f"${v/1e9:.2f}B"
    if a >= 1e6:  return f"${v/1e6:.2f}M"
    if a >= 1e3:  return f"${v/1e3:.2f}K"
    return f"${v:,.0f}"

def _fmt_pct(v: float) -> str:
    return f"{v:.2f}%"

def _fmt_x(v: float) -> str:
    return f"{v:.2f}x"

def _fmt_count(v: float) -> str:
    try:
        return str(int(round(v)))
    except Exception:
        return str(v)

def _fmt_score(v: float) -> str:
    # keep as plain number, one decimal if needed
    if float(v).is_integer():
        return str(int(v))
    return f"{v:.1f}"

def _fmt_num(v: float) -> str:
    if float(v).is_integer():
        return f"{int(v):,}"
    return f"{v:,.2f}"

def _unit_for_key(schema: dict, k: str) -> str:
    # schema wins, fallback heuristics
    if k in schema:
        return schema[k]
    kl = k.lower()
    if "margin" in kl or "yield" in kl or kl.endswith("_pct") or "pct" in kl:
        return "pct"
    if "pe" in kl or "ev_" in kl or "multiple" in kl or "ratio" in kl:
        return "x"
    if "risk_" in kl or "count" in kl:
        return "count"
    if "shock" in kl or "score" in kl:
        return "score"
    if "cap" in kl or "revenue" in kl or "debt" in kl or "cash" in kl or "price" in kl or "fcf" in kl:
        return "usd"
    return "num"

def _fmt_by_unit(unit: str, v):
    if v is None:
        return "N/A"
    try:
        fv = float(v)
    except Exception:
        return str(v)

    if unit == "usd":   return _fmt_usd(fv)
    if unit == "pct":   return _fmt_pct(fv)
    if unit == "x":     return _fmt_x(fv)
    if unit == "count": return _fmt_count(fv)
    if unit == "score": return _fmt_score(fv)
    return _fmt_num(fv)

def main(ticker: str):
    T = ticker.upper()
    canon_dir = CANON / f"CANON_{T}"
    canon_dir.mkdir(parents=True, exist_ok=True)

    # Load schema if present
    schema_path = ROOT / "scripts" / "friday" / "metric_schema.py"
    schema = {}
    if schema_path.exists():
        # safe import by exec into dict (avoid package/path issues)
        ns = {}
        exec(schema_path.read_text(encoding="utf-8"), ns, ns)
        schema = ns.get("METRIC_SCHEMA", {}) or {}

    # Inputs we can pull from canon
    dcf = _load_json(canon_dir / f"{T}_DCF.json") or {}
    core = _load_json(canon_dir / f"{T}_CORE_METRICS.json") or {}
    core.update(_load_ev_fields(T))

    risk = _load_json(canon_dir / f"news_risk_summary_{T}.json") or {}

    # Build a flat metrics dict (only include things that exist)
    metrics = {}

    # DCF inputs
    if isinstance(dcf, dict):
        inp = dcf.get("inputs") or {}
        if isinstance(inp, dict):
            for k in ["fcf_ttm", "net_debt", "price_used", "market_cap_used"]:
                if k in inp: metrics[k] = inp.get(k)
        val = dcf.get("valuation_per_share") or {}
        if isinstance(val, dict):
            for k in ["bear_price", "base_price", "bull_price"]:
                if k in val: metrics[k] = val.get(k)

        # FCF yield if possible
        try:
            fcf = float((dcf.get("inputs") or {}).get("fcf_ttm"))
            mcap = float((dcf.get("inputs") or {}).get("market_cap_used"))
            if mcap != 0:
                metrics["fcf_yield"] = (fcf / mcap) * 100.0
        except Exception:
            pass

    # Core metrics file (already computed in your pipeline)
    if isinstance(core, dict):
        for k, v in core.items():
            # Skip nested blobs + noisy keys
            if str(k).lower() in ('metrics','sources'):
                continue
            if isinstance(v, (dict, list)):
                continue
            if k == "ticker": 
                continue
            metrics[k] = v

    # Risk summary
    if isinstance(risk, dict):
        for k, v in risk.items():
            if k in ("ticker", "generated_at"):
                continue
            metrics[k] = v

    # If you want to guarantee visibility of unit types:
    # Keep list ordered for readability
    preferred_order = [
        "price_used", "market_cap_used", "fcf_ttm", "fcf_margin", "fcf_yield",
        "gross_margin", "operating_margin",
        "pe_ratio", "ev_ebitda",
        "news_shock", "risk_total_30d",
        "risk_labor_neg_30d","risk_regulatory_neg_30d","risk_insurance_neg_30d","risk_safety_neg_30d","risk_competition_neg_30d",
        "bear_price","base_price","bull_price",
        "net_debt",
    ]

    ordered_keys = []
    for k in preferred_order:
        if k in metrics and k not in ordered_keys:
            ordered_keys.append(k)
    for k in sorted(metrics.keys()):
        if k not in ordered_keys:
            ordered_keys.append(k)

    # Render
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    li_rows = []
    for k in ordered_keys:
        v = metrics.get(k)
        unit = _unit_for_key(schema, k)
        rendered = _fmt_by_unit(unit, v)
        li_rows.append(f"<li><b>{_label(k)}</b> <span style='opacity:.7'>(<code>{_unit_display(unit)}</code>)</span>: <span>{rendered}</span></li>")

    html = f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{T} — DECISION CORE</title>
</head>
<body style="background:#000;color:#0f0;font-family:ui-monospace,Menlo,Monaco,Consolas,monospace;padding:18px;">
  <h1 style="margin:0 0 10px 0;">{T} — DECISION CORE</h1>
  <div style="opacity:.8;margin-bottom:12px;">Generated: {now}</div>

  <h2 style="margin:14px 0 6px 0;">Metrics (unit-labeled)</h2>
  <ul>
    {"".join(li_rows)}
  </ul>

  <hr style="border:0;border-top:1px solid #0f0;opacity:.25;margin:16px 0;" />

  <div style="font-size:14px;line-height:1.35;opacity:.9;">
    <b>Plain-English:</b><br/>
    • <b>FCF (TTM)</b> = cash the business kept over the last 12 months after expenses/investment.<br/>
    • <b>FCF margin</b> = how much of revenue turns into free cash (higher is better).<br/>
    • <b>FCF yield</b> = free cash return vs what the market is paying (higher can mean “cheaper”).<br/>
    • <b>News shock</b> = headline tone/pressure score (lower/more negative = worse headlines).<br/>
    • <b>Risk counts</b> = how many negative-risk headlines in each bucket (more = more heat).<br/>
    • <b>DCF cone</b> = rough “fair value range” per share under bear/base/bull assumptions.<br/>
  </div>
</body>
</html>
"""

    out_json = canon_dir / f"{T}_DECISION_CORE.json"
    out_html = canon_dir / f"{T}_DECISION_CORE.html"

    out_json.write_text(_json.dumps({"ticker": T, "generated_at": now, "metrics": metrics}, indent=2), encoding="utf-8")

    # EV_FIXUP_BEGIN (post-write patch to keep JSON aligned with core)
    try:
        _d = _json.loads(out_json.read_text(encoding='utf-8'))
        _d['enterprise_value'] = core.get('enterprise_value')
        _d['ev_sales'] = core.get('ev_sales')
        out_json.write_text(_json.dumps(_d, indent=2), encoding='utf-8')
    except Exception:
        pass
    # EV_FIXUP_END

    out_html.write_text(html, encoding="utf-8")

    print("DONE ✅", out_json)
    print("DONE ✅", out_html)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    a = ap.parse_args()
    main(a.ticker)
