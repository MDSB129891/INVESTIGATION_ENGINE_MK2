#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main(ticker: str):
    t = ticker.upper()
    out = ROOT / "outputs"
    core = _read(ROOT / "export" / f"CANON_{t}" / f"{t}_DECISION_CORE.json")
    metrics = (core.get("metrics") or {})
    base_price = metrics.get("base_price")
    price = metrics.get("price_used")
    scenarios = [
        {"name": "Rates Up Shock", "multiplier": 0.85, "note": "Higher discount rate compresses valuation."},
        {"name": "Base Case", "multiplier": 1.00, "note": "Current assumptions continue."},
        {"name": "Execution Outperformance", "multiplier": 1.20, "note": "Growth and margin beat assumptions."},
    ]
    rows = []
    for s in scenarios:
        val = None
        if base_price is not None:
            try:
                val = float(base_price) * s["multiplier"]
            except Exception:
                val = None
        rows.append({**s, "scenario_price": val})
    payload = {
        "ticker": t,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "current_price": price,
        "base_price": base_price,
        "scenarios": rows,
        "plain_english": "Scenario Forge shows how valuation changes under different macro/execution worlds.",
    }
    j = out / f"friday_scenario_forge_{t}.json"
    h = out / f"friday_scenario_forge_{t}.html"
    j.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    h.write_text(f"<!doctype html><html><body style='font-family:ui-sans-serif,system-ui;background:#0e1627;color:#eaf0ff;padding:18px'><h2>Friday Scenario Forge — {t}</h2><pre>{json.dumps(payload, indent=2)}</pre></body></html>", encoding="utf-8")
    print("DONE ✅ wrote:", j)
    print("DONE ✅ wrote:", h)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    args = ap.parse_args()
    main(args.ticker)

