#!/usr/bin/env bash
set -euo pipefail

TICKER="${1:?ticker required}"
THESIS="${2:-}"

T="$(echo "$TICKER" | tr '[:lower:]' '[:upper:]')"

echo "📘 SUPER STORYTIME RUN"
echo "Ticker: $T"
echo "Thesis: ${THESIS:-<none>}"
echo

python3 scripts/build_super_storytime_memo.py --ticker "$T" ${THESIS:+--thesis "$THESIS"}

# OPEN IN ORDER (dopamine, but clean)
if [ -f "outputs/decision_dashboard_${T}.html" ]; then
# DISABLED (JARVIS controls opening):   open "outputs/decision_dashboard_${T}.html" || true
fi

if [ -f "export/${T}_SUPER_Storytime_Memo.pdf" ]; then
  open "export/${T}_SUPER_Storytime_Memo.pdf" || true
else
  echo "⚠️ Missing PDF: export/${T}_SUPER_Storytime_Memo.pdf"
  echo "Try:"
  echo "  /opt/homebrew/bin/soffice --headless --convert-to pdf --outdir export export/${T}_SUPER_Storytime_Memo.docx"
fi
