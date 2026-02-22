#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def _safe_float(v):
    try:
        return float(v)
    except Exception:
        return None


def _hit_rate(df: pd.DataFrame, signal_col: str, target_col: str, signal_fn, target_fn):
    rows = []
    for i in range(len(df) - 1):
        s = _safe_float(df.iloc[i].get(signal_col))
        t_next = _safe_float(df.iloc[i + 1].get(target_col))
        if s is None or t_next is None:
            continue
        pred = bool(signal_fn(s))
        actual = bool(target_fn(t_next))
        rows.append(1 if pred == actual else 0)
    if not rows:
        return None, 0
    return round(sum(rows) / len(rows) * 100.0, 1), len(rows)


def main(ticker: str):
    t = ticker.upper()
    annual = ROOT / "data" / "processed" / "fundamentals_annual_history.csv"
    out_dir = ROOT / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(annual) if annual.exists() else pd.DataFrame()
    if not df.empty and "ticker" in df.columns:
        df["ticker"] = df["ticker"].astype(str).str.upper()
        df = df[df["ticker"] == t]
    if "period_end" in df.columns:
        df = df.sort_values("period_end")

    growth_hr, growth_n = _hit_rate(
        df,
        "revenue_yoy_pct",
        "revenue_yoy_pct",
        lambda x: x > 0,
        lambda y: y > 0,
    )
    cash_hr, cash_n = _hit_rate(
        df,
        "fcf_margin_pct",
        "free_cash_flow",
        lambda x: x >= 5,
        lambda y: y > 0,
    )
    debt_hr, debt_n = _hit_rate(
        df,
        "debt",
        "free_cash_flow",
        lambda x: x < 0,  # always false normally; placeholder if debt anomalies appear
        lambda y: y > 0,
    )
    # debt signal fallback: better if debt growth is contained
    if debt_hr is None and not df.empty and "debt" in df.columns:
        vals = pd.to_numeric(df["debt"], errors="coerce").dropna().tolist()
        if len(vals) > 2:
            stable = sum(1 for i in range(1, len(vals)) if vals[i] <= vals[i - 1] * 1.1)
            debt_hr = round(stable / (len(vals) - 1) * 100.0, 1)
            debt_n = len(vals) - 1

    modules = [
        {"name": "Time Stone (growth persistence)", "hit_rate_pct": growth_hr, "samples": growth_n},
        {"name": "Power Stone (cash persistence)", "hit_rate_pct": cash_hr, "samples": cash_n},
        {"name": "Space Stone (debt discipline proxy)", "hit_rate_pct": debt_hr, "samples": debt_n},
    ]
    valid = [m["hit_rate_pct"] for m in modules if m["hit_rate_pct"] is not None]
    overall = round(sum(valid) / len(valid), 1) if valid else None

    payload = {
        "ticker": t,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "overall_hit_rate_pct": overall,
        "modules": modules,
        "plain_english": (
            "This checks how often your core signals were directionally right in later periods. "
            "Higher hit rate means the signal has been more trustworthy historically."
        ),
    }

    j = out_dir / f"armor_calibration_{t}.json"
    h = out_dir / f"armor_calibration_{t}.html"
    j.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    html = [
        "<!doctype html><html><head><meta charset='utf-8'><title>Armor Calibration</title></head>",
        "<body style='font-family:ui-sans-serif,system-ui;background:#0f1524;color:#e8eeff;padding:20px'>",
        f"<h2>Armor Calibration Bay — {t}</h2>",
        f"<p>{payload['plain_english']}</p>",
        f"<p><b>Overall hit rate:</b> {overall if overall is not None else '—'}%</p>",
        "<table border='1' cellpadding='8' cellspacing='0'><tr><th>Module</th><th>Hit rate</th><th>Samples</th></tr>",
    ]
    for m in modules:
        hr = "—" if m["hit_rate_pct"] is None else f"{m['hit_rate_pct']}%"
        html.append(f"<tr><td>{m['name']}</td><td>{hr}</td><td>{m['samples']}</td></tr>")
    html.append("</table></body></html>")
    h.write_text("\n".join(html), encoding="utf-8")
    print("DONE ✅ wrote:", j)
    print("DONE ✅ wrote:", h)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    args = ap.parse_args()
    main(args.ticker)

