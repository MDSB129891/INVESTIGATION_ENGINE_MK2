#!/usr/bin/env bash
set -euo pipefail

TICKER="${1:-}"
THESIS="${2:-}"

if [ -z "$TICKER" ] || [ -z "$THESIS" ]; then
  echo "Usage: ./scripts/run_super2.sh TICKER theses/TICKER_custom.json"
  exit 1
fi

T="$(echo "$TICKER" | tr '[:lower:]' '[:upper:]')"

python3 scripts/build_super_memo2.py --ticker "$T" --thesis "$THESIS"

# Build PDF (best effort) + open in order
if [ -f "outputs/decision_dashboard_${T}.html" ]; then
# DISABLED (JARVIS controls opening):   open "outputs/decision_dashboard_${T}.html" || true
fi

if [ -f "export/${T}_SUPER_Memo2.pdf" ]; then
  open "export/${T}_SUPER_Memo2.pdf" || true
else
  echo "⚠️ PDF missing: export/${T}_SUPER_Memo2.pdf"
  echo "Try: /opt/homebrew/bin/soffice --headless --convert-to pdf --outdir export export/${T}_SUPER_Memo2.docx"
fi
