#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
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
    focus = (il or {}).get("focus", {})
    now = datetime.now(timezone.utc)
    max_pos = float(focus.get("position_size_pct", 0.0) or 0.0)
    action = focus.get("action", "HOLD FIRE")
    entry = focus.get("entry_band_text", "—")

    ladder = []
    if "DEPLOY" in action:
        ladder = [
            {"step": "Starter", "size_pct": round(max_pos * 0.35, 2), "trigger": f"Price enters {entry}"},
            {"step": "Add #1", "size_pct": round(max_pos * 0.35, 2), "trigger": "No thesis-break trigger and momentum stable"},
            {"step": "Add #2", "size_pct": round(max_pos * 0.30, 2), "trigger": "Next catalyst confirms thesis"},
        ]
    elif "TRACK" in action:
        ladder = [{"step": "Watch", "size_pct": round(max_pos, 2), "trigger": "Wait for conviction/reliability upgrade"}]
    else:
        ladder = [{"step": "No Entry", "size_pct": 0.0, "trigger": "Hold fire until guardrails clear"}]

    payload = {
        "ticker": t,
        "generated_utc": now.isoformat(),
        "action": action,
        "entry_band": entry,
        "ladder": ladder,
        "rebalance_dates_utc": [(now + timedelta(days=d)).date().isoformat() for d in (7, 14, 30)],
        "plain_english": "War Machine layer turns strategy into executable steps and timing.",
    }
    j = out / f"war_machine_execution_{t}.json"
    h = out / f"war_machine_execution_{t}.html"
    j.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    h.write_text(f"<!doctype html><html><body style='font-family:ui-sans-serif,system-ui;background:#0f141f;color:#ecf3ff;padding:18px'><h2>War Machine Execution Layer — {t}</h2><pre>{json.dumps(payload, indent=2)}</pre></body></html>", encoding="utf-8")
    print("DONE ✅ wrote:", j)
    print("DONE ✅ wrote:", h)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    args = ap.parse_args()
    main(args.ticker)

