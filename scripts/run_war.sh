#!/usr/bin/env bash
set -euo pipefail

TICKER="${1:-}"
THESIS_FILE="${2:-}"

if [ -z "$TICKER" ] || [ -z "$THESIS_FILE" ]; then
  echo "Usage: ./scripts/run_war.sh TICKER theses/XYZ_custom.json"
  exit 1
fi

TICKER_UPPER="$(echo "$TICKER" | tr '[:lower:]' '[:upper:]')"

echo "⚔️  WAR RUN"
echo "Ticker: $TICKER_UPPER"
echo "Thesis file: $THESIS_FILE"
echo ""

# 1) Build SUPER memo (this is the one you actually want)
python3 scripts/build_super_memo.py --ticker "$TICKER_UPPER" --thesis "$THESIS_FILE"

# 2) Convert SUPER DOCX -> PDF (locked, non-editable)
if command -v /opt/homebrew/bin/soffice >/dev/null 2>&1; then
  SOFFICE="/opt/homebrew/bin/soffice"
elif command -v soffice >/dev/null 2>&1; then
  SOFFICE="$(command -v soffice)"
else
  echo "❌ LibreOffice 'soffice' not found. Install LibreOffice or link soffice."
  exit 1
fi

DOCX="export/${TICKER_UPPER}_SUPER_Memo.docx"
PDF="export/${TICKER_UPPER}_SUPER_Memo.pdf"

if [ ! -f "$DOCX" ]; then
  echo "❌ SUPER docx not found: $DOCX"
  echo "   That means build_super_memo.py did not output to that path/name."
  echo "   Running a quick search..."
  ls -lah export | grep -i "${TICKER_UPPER}.*super" || true
  exit 1
fi

"$SOFFICE" --headless --convert-to pdf --outdir export "$DOCX" >/dev/null 2>&1 || true

if [ ! -f "$PDF" ]; then
  echo "❌ PDF was not created: $PDF"
  echo "   Try manual conversion:"
  echo "   $SOFFICE --headless --convert-to pdf --outdir export $DOCX"
  exit 1
fi

echo ""
echo "✅ SUPER PDF READY:"
ls -lh "$DOCX" "$PDF"
echo ""

# 3) Optional: run the full galactus pipeline AFTER (keeps your other artifacts)
# Comment this out if you only want SUPER.
if [ -f "./scripts/run_galactus.sh" ]; then
  ./scripts/run_galactus.sh "$TICKER_UPPER" "$THESIS_FILE" || true
fi

# 4) Open ONLY the dopamine order (no tab spam)
echo ""
echo "🚀 OPENING (order): Dashboard -> SUPER PDF"
if [ -f "outputs/decision_dashboard_${TICKER_UPPER}.html" ]; then
# DISABLED (JARVIS controls opening):   open "outputs/decision_dashboard_${TICKER_UPPER}.html" || true
fi
open "$PDF" || true
