#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

# --- bootstrap: allow `import analytics...` reliably ---
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
# ------------------------------------------------------

from analytics.scoring_phase4 import enrich_decision_summary


def main():
    outputs = ROOT / "outputs"
    processed = ROOT / "data" / "processed"

    ticker = os.getenv("TICKER", "AAPL").upper()

    summary = enrich_decision_summary(
        root=ROOT,
        ticker=ticker,
        outputs_path=outputs,
        processed_path=processed,
    )

    print(f"DONE ✅ Phase 4 upgraded summary for {ticker}")
    print(f"- outputs/decision_summary.json updated")
    print(f"- outputs/decision_audit_{ticker}.json created")
    print(f"- outputs/decision_card_{ticker}.json created")
    print(f"- completeness_score={summary.get('data_completeness_score')}")


if __name__ == "__main__":
    main()
