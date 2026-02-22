#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _run(cmd, env=None, allow_fail=False):
    pretty = " ".join(shlex.quote(str(x)) for x in cmd)
    print(f"$ {pretty}")
    try:
        subprocess.run(cmd, cwd=str(ROOT), env=env, check=True)
        return True
    except subprocess.CalledProcessError as exc:
        print(f"⚠️ step failed (exit={exc.returncode}): {pretty}")
        if not allow_fail:
            raise
        return False


def _script(name: str) -> Path:
    return SCRIPTS / name


def main():
    ap = argparse.ArgumentParser(description="VISION controller: ticker + thesis -> full armor pipeline")
    ap.add_argument("ticker", help="Ticker symbol (e.g., GM)")
    ap.add_argument("thesis", help="Plain-English thesis text")
    ap.add_argument("--peers", default="", help="Comma separated peers, e.g., F,TM")
    ap.add_argument("--strict", action="store_true", help="Run strict mode (continue on refresh errors but mark warnings)")
    ap.add_argument("--godkiller", action="store_true", help="Max-strength run: strict + per-ticker integrity + legion readiness summary")
    args = ap.parse_args()

    t = args.ticker.upper().strip()
    peers = [p.strip().upper() for p in args.peers.split(",") if p.strip()]
    universe = [t] + [p for p in peers if p != t]
    thesis_out = ROOT / "theses" / f"{t}_thesis_custom.json"
    thesis_out.parent.mkdir(parents=True, exist_ok=True)

    if args.godkiller:
        args.strict = True

    print(f"VISION controller running for {t}")
    if args.godkiller:
        print("Mode: GODKILLER")
    print(f"Peers: {','.join(peers) if peers else '<none>'}")
    print(f"Thesis output: {thesis_out}")

    py = sys.executable
    env = os.environ.copy()
    env["TICKER"] = t
    env["PEERS"] = ",".join(peers)
    env["UNIVERSE"] = ",".join(universe)

    _run([py, str(_script("compile_thesis_from_text.py")), "--ticker", t, "--text", args.thesis, "--out", str(thesis_out)], env=env)

    # Refresh/update stage. If it fails, continue from latest processed artifacts.
    refresh_ok = _run([py, str(_script("run_arc_reactor_update.py"))], env=env, allow_fail=True)
    if not refresh_ok:
        print("⚠️ refresh failed; continuing with existing processed/cache data")

    post_steps = [
        ("build_news_risk_summary.py", ["--ticker", t]),
        ("build_macro_context.py", []),  # optional script, skip if missing
        ("friday/build_core_metrics.py", ["--ticker", t]),
        ("friday/build_decision_core.py", ["--ticker", t]),
        ("build_montecarlo.py", ["--ticker", t]),
        ("build_timestone.py", ["--ticker", t]),
        ("build_claim_evidence.py", ["--ticker", t, "--thesis", str(thesis_out)]),
        ("build_receipts_index.py", ["--ticker", t]),
        ("build_ironman_hud.py", ["--ticker", t]),
        ("build_iron_legion.py", ["--focus", t]),
        ("build_recommendation_brief.py", ["--ticker", t, "--thesis", args.thesis]),
        ("build_mission_report.py", ["--tickers", ",".join(universe)]),  # optional script, skip if missing
        ("check_pipeline_integrity.py", ["--ticker", t]),
        ("build_armor_calibration.py", ["--ticker", t]),
        ("build_confidence_governor.py", ["--ticker", t]),
        ("build_arc_reactor_drift_monitor.py", ["--ticker", t]),
        ("build_friday_scenario_forge.py", ["--ticker", t]),
        ("build_edith_circuit_breakers.py", ["--ticker", t]),
        ("build_hulkbuster_stress_suite.py", ["--ticker", t]),
        ("build_explainability_overlay.py", ["--ticker", t]),
        ("build_war_machine_execution.py", ["--ticker", t]),
        ("build_shield_evidence_locker.py", ["--ticker", t]),
        ("build_legion_commander.py", ["--ticker", t]),
    ]

    soft_fail_steps = {
        "build_macro_context.py",
        "build_mission_report.py",
        "build_recommendation_brief.py",
        "build_montecarlo.py",
        "check_pipeline_integrity.py",
        "build_armor_calibration.py",
        "build_confidence_governor.py",
        "build_arc_reactor_drift_monitor.py",
        "build_friday_scenario_forge.py",
        "build_edith_circuit_breakers.py",
        "build_hulkbuster_stress_suite.py",
        "build_explainability_overlay.py",
        "build_war_machine_execution.py",
        "build_shield_evidence_locker.py",
        "build_legion_commander.py",
    }

    for rel_script, extra in post_steps:
        p = _script(rel_script)
        if not p.exists():
            print(f"⚠️ skipped missing script: {p}")
            continue
        _run([py, str(p), *extra], env=env, allow_fail=(not args.strict or rel_script in soft_fail_steps))

    if args.godkiller:
        # Build integrity packs for peers as well so the legion table has audited context.
        integ_script = _script("check_pipeline_integrity.py")
        if integ_script.exists():
            for peer in universe[1:]:
                _run([py, str(integ_script), "--ticker", peer], env=env, allow_fail=True)

        # Aggregate readiness summary for focus + peers.
        readiness = {"mode": "godkiller", "focus": t, "universe": universe, "tickers": {}}
        for tk in universe:
            p = ROOT / "outputs" / f"pipeline_integrity_{tk}.json"
            if p.exists():
                try:
                    readiness["tickers"][tk] = json.loads(p.read_text(encoding="utf-8"))
                except Exception:
                    readiness["tickers"][tk] = {"status": "unreadable"}
            else:
                readiness["tickers"][tk] = {"status": "missing"}
        out = ROOT / "outputs" / f"godkiller_status_{t}.json"
        out.write_text(json.dumps(readiness, indent=2), encoding="utf-8")
        print(f"- Godkiller Status: {out}")

    # Append run history for drift monitor.
    try:
        ds = json.loads((ROOT / "outputs" / f"decision_summary_{t}.json").read_text(encoding="utf-8"))
    except Exception:
        ds = {}
    try:
        il = json.loads((ROOT / "outputs" / f"iron_legion_command_{t}.json").read_text(encoding="utf-8"))
    except Exception:
        il = {}
    focus = (il.get("focus") or {})
    hist = ROOT / "outputs" / "run_history.csv"
    first = not hist.exists()
    with hist.open("a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if first:
            w.writerow(["generated_utc", "ticker", "score", "rating", "conviction", "reliability", "mc_fallback"])
        w.writerow([
            (ds.get("as_of") or ""),
            t,
            ds.get("score"),
            ds.get("rating"),
            focus.get("conviction_score"),
            focus.get("reliability_score"),
            (focus.get("reliability_details", {}) or {}).get("mc_fallback_used"),
        ])

    print("DONE ✅ VISION")
    print(f"- Thesis: {thesis_out}")
    print(f"- HUD: {ROOT / 'export' / f'CANON_{t}' / f'{t}_IRONMAN_HUD.html'}")
    print(f"- Iron Legion Command: {ROOT / 'outputs' / f'iron_legion_command_{t}.html'}")
    print(f"- Recommendation Brief PDF: {ROOT / 'outputs' / f'recommendation_brief_{t}.pdf'}")
    print(f"- Legion Commander: {ROOT / 'outputs' / f'legion_commander_{t}.html'}")
    print(f"- Decision Core: {ROOT / 'export' / f'CANON_{t}' / f'{t}_DECISION_CORE.json'}")
    print(f"- Monte Carlo: {ROOT / 'export' / f'CANON_{t}' / f'{t}_MONTECARLO.json'}")


if __name__ == "__main__":
    main()
