#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

TICKER="${1:-}"
THESIS="${2:-}"

if [[ -z "${TICKER}" ]]; then
  echo "Usage: ./scripts/run_one.sh TICKER [THESIS_TEXT]"
  exit 1
fi

echo "=== Running full pipeline for: ${TICKER} ==="
echo "Thesis override: ${THESIS:-<none>}"

# Update engine for chosen ticker (and optional peers if you want them)
export TICKER="${TICKER}"
if [[ -n "${UNIVERSE:-}" ]]; then
  python3 scripts/run_arc_reactor_update.py --ticker "${TICKER}" --universe "${UNIVERSE}"
elif [[ -n "${PEERS:-}" ]]; then
  python3 scripts/run_arc_reactor_update.py --ticker "${TICKER}" --peers "${PEERS}"
else
  python3 scripts/run_arc_reactor_update.py --ticker "${TICKER}"
fi

python3 scripts/generate_thesis_suite.py --ticker "${TICKER}"
python3 scripts/build_veracity_pack.py --ticker "${TICKER}"

if [[ -n "${THESIS}" ]]; then
  python3 scripts/build_investment_memo.py --ticker "${TICKER}" --thesis "${THESIS}"
else
  python3 scripts/build_investment_memo.py --ticker "${TICKER}"
fi

open "outputs/news_clickpack_${TICKER}.html" || true
open "export/${TICKER}_Full_Investment_Memo.docx" || true

echo "DONE ✅"
