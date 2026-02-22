#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main(ticker: str):
    t = ticker.upper()
    out = ROOT / "outputs"
    hist = out / "run_history.csv"
    rows = []
    if hist.exists():
        with hist.open("r", encoding="utf-8") as f:
            r = csv.DictReader(f)
            rows = [x for x in r if str(x.get("ticker", "")).upper() == t]
    rows = rows[-25:]

    def _f(x):
        try:
            return float(x)
        except Exception:
            return None

    scores = [_f(r.get("score")) for r in rows]
    scores = [s for s in scores if s is not None]
    fallback_rate = 0.0
    if rows:
        fallback_rate = sum(1 for r in rows if str(r.get("mc_fallback", "")).lower() == "true") / len(rows) * 100.0
    drift = "stable"
    if len(scores) >= 5:
        recent = sum(scores[-5:]) / 5.0
        base = sum(scores[:-5]) / max(1, len(scores[:-5])) if len(scores) > 5 else recent
        if abs(recent - base) >= 12:
            drift = "elevated"

    payload = {
        "ticker": t,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "sample_runs": len(rows),
        "score_drift_state": drift,
        "mc_fallback_rate_pct": round(fallback_rate, 1),
        "public_message": "Drift monitor checks if model behavior is changing too much run-to-run.",
    }
    j = out / f"arc_reactor_drift_{t}.json"
    h = out / f"arc_reactor_drift_{t}.html"
    j.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    h.write_text(
        f"<!doctype html><html><body style='font-family:ui-sans-serif,system-ui;background:#0f1726;color:#ecf1ff;padding:18px'><h2>Arc Reactor Drift Monitor — {t}</h2><pre>{json.dumps(payload, indent=2)}</pre></body></html>",
        encoding="utf-8",
    )
    print("DONE ✅ wrote:", j)
    print("DONE ✅ wrote:", h)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    args = ap.parse_args()
    main(args.ticker)

