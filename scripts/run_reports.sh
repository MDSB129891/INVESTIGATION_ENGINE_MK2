#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
TICKER="${1:-}"
if [[ -z "${TICKER}" ]]; then
  echo "Usage: ./scripts/run_reports.sh TICKER"
  exit 1
fi
export TICKER

echo "=== Phase 0: Engine update (financials + news) ==="
if [[ -n "${UNIVERSE:-}" ]]; then
  python3 scripts/run_arc_reactor_update.py --ticker "${TICKER}" --universe "${UNIVERSE}"
elif [[ -n "${PEERS:-}" ]]; then
  python3 scripts/run_arc_reactor_update.py --ticker "${TICKER}" --peers "${PEERS}"
else
  python3 scripts/run_arc_reactor_update.py --ticker "${TICKER}"
fi

echo "=== Phase 1: Thesis suite (bear/base/bull) ==="
python3 scripts/generate_thesis_suite.py --ticker "${TICKER}"

echo "=== Phase 2: Veracity pack (confidence + clickpack) ==="
python3 scripts/build_veracity_pack.py --ticker "${TICKER}"

echo "=== Phase 3: Full memo (novice-friendly) ==="
python3 scripts/build_investment_memo.py --ticker "${TICKER}"

echo ""
echo "DONE ✅ All outputs created:"
echo "- outputs/news_clickpack_<TICKER>.html"
echo "- outputs/veracity_<TICKER>.json"
echo "- outputs/<TICKER>_Full_Investment_Memo.md"
echo "- export/<TICKER>_Full_Investment_Memo.docx"
echo ""

# Open the key stuff automatically (Mac)
echo "Open outputs manually with your chosen ticker path."
