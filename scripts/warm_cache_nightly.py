#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
OUT = ROOT / "outputs"


def _run(cmd: list[str], env: dict) -> tuple[bool, str]:
    try:
        p = subprocess.run(cmd, cwd=str(ROOT), env=env, check=True, capture_output=True, text=True)
        return True, p.stdout[-4000:]
    except subprocess.CalledProcessError as e:
        out = (e.stdout or "") + "\n" + (e.stderr or "")
        return False, out[-4000:]


def main(tickers_csv: str):
    tickers = [t.strip().upper() for t in tickers_csv.split(",") if t.strip()]
    if not tickers:
        raise SystemExit("No tickers provided")

    py = sys.executable
    run_script = SCRIPTS / "run_arc_reactor_update.py"
    report = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "tickers": tickers,
        "results": [],
    }

    for t in tickers:
        env = os.environ.copy()
        env["TICKER"] = t
        env["PEERS"] = ""
        env["UNIVERSE"] = t
        ok, tail = _run([py, str(run_script)], env=env)
        report["results"].append(
            {
                "ticker": t,
                "ok": ok,
                "log_tail": tail,
                "decision_summary": str(OUT / f"decision_summary_{t}.json"),
                "provider_health": str(OUT / f"provider_health_{t}.json"),
            }
        )
        print(f"[warm-cache] {t}: {'OK' if ok else 'FAIL'}")

    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / "warm_cache_last_run.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("DONE ✅ wrote:", out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Nightly warm-cache runner for top universe tickers.")
    ap.add_argument(
        "--tickers",
        default=os.getenv("WARM_CACHE_UNIVERSE", "AAPL,MSFT,GOOGL,NVDA,AMZN,META,TSLA,WMT,GM"),
        help="Comma-separated tickers to refresh nightly",
    )
    args = ap.parse_args()
    main(args.tickers)

