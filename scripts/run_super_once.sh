#!/usr/bin/env bash
set -euo pipefail

TICKER="${1:-GM}"
THESIS="${2:-theses/GM_custom.json}"
T="$(echo "$TICKER" | tr '[:lower:]' '[:upper:]')"

echo "✅ SUPER RUN: $T"
echo "   thesis: $THESIS"

python3 -m py_compile scripts/build_super_memo.py
python3 scripts/build_super_memo.py --ticker "$T" --thesis "$THESIS"

# ensure PDF exists (LibreOffice)
if [ -f "export/${T}_SUPER_Memo.docx" ]; then
  /opt/homebrew/bin/soffice --headless --convert-to pdf --outdir export "export/${T}_SUPER_Memo.docx" >/dev/null 2>&1 || true
fi

echo ""
echo "FILES:"
ls -lh "outputs/${T}_SUPER_Memo.md" "export/${T}_SUPER_Memo.docx" "export/${T}_SUPER_Memo.pdf" 2>/dev/null || true

echo ""
echo "OPEN (only 2 things, in order):"
if [ -f "outputs/decision_dashboard_${T}.html" ]; then
# DISABLED (JARVIS controls opening):   open "outputs/decision_dashboard_${T}.html" || true
fi
if [ -f "export/${T}_SUPER_Memo.pdf" ]; then
  open "export/${T}_SUPER_Memo.pdf" || true
else
  echo "⚠️ Missing PDF: export/${T}_SUPER_Memo.pdf"
fi
