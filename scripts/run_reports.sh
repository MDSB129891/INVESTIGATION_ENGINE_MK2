#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "=== Phase 0: Engine update (financials + news) ==="
python3 scripts/run_arc_reactor_update.py

echo "=== Phase 1: Thesis suite (bear/base/bull) ==="
python3 scripts/generate_thesis_suite.py

echo "=== Phase 2: Veracity pack (confidence + clickpack) ==="
python3 scripts/build_veracity_pack.py

echo "=== Phase 3: Full memo (novice-friendly) ==="
python3 scripts/build_investment_memo.py

echo ""
echo "DONE ✅ All outputs created:"
echo "- outputs/news_clickpack_<TICKER>.html"
echo "- outputs/veracity_<TICKER>.json"
echo "- outputs/<TICKER>_Full_Investment_Memo.md"
echo "- export/<TICKER>_Full_Investment_Memo.docx"
echo ""

# Open the key stuff automatically (Mac)
echo "Open outputs manually with your chosen ticker path."
