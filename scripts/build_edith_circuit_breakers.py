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
    il = _read(out / f"iron_legion_command_{t}.json")
    rows = il.get("legion_table") or []
    total_size = sum(float(r.get("position_size_pct", 0.0) or 0.0) for r in rows)
    risk_off_count = sum(1 for r in rows if r.get("regime") == "Risk-Off")
    breakers = {
        "max_total_position_15pct": total_size <= 15.0,
        "max_single_position_8pct": all(float(r.get("position_size_pct", 0.0) or 0.0) <= 8.0 for r in rows),
        "risk_off_overload_guard": risk_off_count <= max(1, len(rows) // 2),
    }
    payload = {
        "ticker": t,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "checks": breakers,
        "total_position_pct": round(total_size, 2),
        "plain_english": "EDITH breakers prevent oversized or unstable portfolio exposure.",
    }
    j = out / f"edith_circuit_breakers_{t}.json"
    h = out / f"edith_circuit_breakers_{t}.html"
    j.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    h.write_text(f"<!doctype html><html><body style='font-family:ui-sans-serif,system-ui;background:#12182a;color:#ebf2ff;padding:18px'><h2>EDITH Circuit Breakers — {t}</h2><pre>{json.dumps(payload, indent=2)}</pre></body></html>", encoding="utf-8")
    print("DONE ✅ wrote:", j)
    print("DONE ✅ wrote:", h)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    args = ap.parse_args()
    main(args.ticker)

