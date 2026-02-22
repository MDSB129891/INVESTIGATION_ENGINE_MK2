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
    integ = _read(out / f"pipeline_integrity_{t}.json")
    claim = _read(out / f"claim_evidence_{t}.json")
    il = _read(out / f"iron_legion_command_{t}.json")

    fail_claim = sum(1 for r in (claim.get("results") or []) if str((r or {}).get("status", "")).upper() == "FAIL")
    unknown_claim = sum(1 for r in (claim.get("results") or []) if str((r or {}).get("status", "")).upper() == "UNKNOWN")

    tests = [
        {"name": "Missing file stress", "pass": len(integ.get("missing_files") or []) == 0},
        {"name": "Provider field stress", "pass": len(integ.get("missing_metric_provider_fields") or []) == 0},
        {"name": "Thesis contradiction stress", "pass": fail_claim == 0},
        {"name": "Unknown evidence stress", "pass": unknown_claim <= 1},
        {"name": "Reliability stress", "pass": float(((il.get("focus") or {}).get("reliability_score") or 0.0)) >= 70.0},
    ]
    pass_n = sum(1 for x in tests if x["pass"])
    payload = {
        "ticker": t,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "tests": tests,
        "pass_count": pass_n,
        "total_tests": len(tests),
        "plain_english": "Hulkbuster stress tests check whether the decision still holds under messy conditions.",
    }
    j = out / f"hulkbuster_stress_{t}.json"
    h = out / f"hulkbuster_stress_{t}.html"
    j.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    h.write_text(f"<!doctype html><html><body style='font-family:ui-sans-serif,system-ui;background:#1a1010;color:#ffefef;padding:18px'><h2>Hulkbuster Stress Suite — {t}</h2><pre>{json.dumps(payload, indent=2)}</pre></body></html>", encoding="utf-8")
    print("DONE ✅ wrote:", j)
    print("DONE ✅ wrote:", h)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    args = ap.parse_args()
    main(args.ticker)

