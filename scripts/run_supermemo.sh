#!/usr/bin/env bash
set -euo pipefail

TICKER="${1:-}"
THESIS_FILE="${2:-}"

if [ -z "$TICKER" ]; then
  echo "Usage: ./scripts/run_supermemo.sh TICKER theses/TICKER_custom.json"
  exit 1
fi

if [ -z "$THESIS_FILE" ]; then
  # default thesis file if not provided
  THESIS_FILE="theses/${TICKER}_custom.json"
fi

echo "🧠 SUPERMEMO RUN"
echo "Ticker: $TICKER"
echo "Thesis file: $THESIS_FILE"
echo ""

# 1) Run the full engine pack
./scripts/run_thanos.sh "$TICKER" "$THESIS_FILE" || ./scripts/run_thanos.sh "$TICKER"

# 2) Build the BIG memo (the one you actually want)
python3 scripts/build_big_memo.py --ticker "$TICKER" --thesis "$THESIS_FILE"

# 3) Open the dopamine pack
open "export/${TICKER}_BIG_Memo.docx" || true
# DISABLED (JARVIS controls opening): open "outputs/decision_dashboard_${TICKER}.html" || true
open "outputs/news_clickpack_${TICKER}.html" || true
open "outputs/claim_evidence_${TICKER}.html" || true

echo ""
echo "✅ SUPERMEMO COMPLETE"
echo "Docx: export/${TICKER}_BIG_Memo.docx"
echo "Dash: outputs/decision_dashboard_${TICKER}.html"
echo "News: outputs/news_clickpack_${TICKER}.html"
echo "Claims: outputs/claim_evidence_${TICKER}.html"
