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
    integ = _read(out / f"pipeline_integrity_{t}.json")
    ds = _read(out / f"decision_summary_{t}.json")
    focus = (il or {}).get("focus", {})
    rel = float(focus.get("reliability_score", 0.0))
    conv = float(focus.get("conviction_score", 0.0))
    tests = focus.get("thesis_test_counts", {}) or {}
    fail_n = int(tests.get("fail", 0))
    refresh_warn = (integ.get("refresh_warnings") or [])
    missing_metric_fields = integ.get("missing_metric_provider_fields") or []
    mc_fallback = bool((focus.get("reliability_details") or {}).get("mc_fallback_used", False))
    freshness_passed = bool(((ds.get("freshness_sla") or {}).get("passed", False)))

    gates = {
        "reliability_gate": rel >= 75.0,
        "conviction_gate": conv >= 60.0,
        "thesis_fail_gate": fail_n == 0,
        "data_stability_gate": len(refresh_warn) <= 4,
        "metric_completeness_gate": len(missing_metric_fields) == 0,
        "freshness_gate": freshness_passed,
        "mc_quality_gate": not mc_fallback,
    }
    all_pass = all(gates.values())
    governed_action = focus.get("action", "HOLD FIRE")
    if not all_pass:
        governed_action = "HOLD FIRE"

    payload = {
        "ticker": t,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "incoming_action": focus.get("action", "UNKNOWN"),
        "governed_action": governed_action,
        "gates": gates,
        "summary_public": (
            "Governor allows deploy only when conviction, reliability, and thesis quality are all healthy."
        ),
        "summary_pro": (
            f"gates={gates}, reliability={rel}, conviction={conv}, thesis_fail={fail_n}, "
            f"refresh_warn_count={len(refresh_warn)}, missing_metric_fields={len(missing_metric_fields)}, "
            f"freshness_passed={freshness_passed}, mc_fallback={mc_fallback}"
        ),
    }

    j = out / f"confidence_governor_{t}.json"
    h = out / f"confidence_governor_{t}.html"
    j.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    h.write_text(
        (
            "<!doctype html><html><body style='font-family:ui-sans-serif,system-ui;background:#111a2b;color:#e7efff;padding:18px'>"
            f"<h2>J.A.R.V.I.S. Confidence Governor — {t}</h2>"
            f"<p><b>Incoming:</b> {payload['incoming_action']}<br/><b>Governed:</b> {payload['governed_action']}</p>"
            f"<p>{payload['summary_public']}</p><pre>{payload['summary_pro']}</pre></body></html>"
        ),
        encoding="utf-8",
    )
    print("DONE ✅ wrote:", j)
    print("DONE ✅ wrote:", h)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ticker", required=True)
    args = ap.parse_args()
    main(args.ticker)
