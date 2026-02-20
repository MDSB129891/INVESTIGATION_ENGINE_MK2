#!/usr/bin/env bash
set -euo pipefail

T="${1:?ticker required}"
T_UP="$(echo "$T" | tr '[:lower:]' '[:upper:]')"
THESIS="${2:-}"

# 1) Run your pipeline (generates dashboard, etc.)
./scripts/run_thanos.sh "$T_UP" >/dev/null 2>&1 || true

# 2) Build SUPER memo (DOCX) using your existing builder
#    If you pass a thesis path, use it; otherwise just omit thesis.
if [ -n "$THESIS" ]; then
  python3 scripts/build_super_memo.py --ticker "$T_UP" --thesis "$THESIS"
else
  # if your build_super_memo.py REQUIRES thesis, set a sane default file
  DEFAULT_THESIS="theses/${T_UP}_custom.json"
  if [ -f "$DEFAULT_THESIS" ]; then
    python3 scripts/build_super_memo.py --ticker "$T_UP" --thesis "$DEFAULT_THESIS"
  else
    echo "⚠️ No thesis provided and no default found at $DEFAULT_THESIS"
    echo "   Run: python3 scripts/new_thesis.py $T_UP \"your thesis\""
    exit 1
  fi
fi

# 3) Convert SUPER DOCX -> PDF (LibreOffice)
DOCX="export/${T_UP}_SUPER_Memo.docx"
PDF="export/${T_UP}_SUPER_Memo.pdf"

if [ -f "$DOCX" ]; then
  /opt/homebrew/bin/soffice --headless --convert-to pdf --outdir export "$DOCX" >/dev/null 2>&1 || true
fi

# 4) OPEN ONLY TWO THINGS (clean dopamine order)
echo ""
echo "OPENING (only 2 things, in order):"
if [ -f "outputs/decision_dashboard_${T_UP}.html" ]; then
# DISABLED (JARVIS controls opening):   open "outputs/decision_dashboard_${T_UP}.html" || true
else
  echo "⚠️ Missing: outputs/decision_dashboard_${T_UP}.html"
fi

if [ -f "$PDF" ]; then
  open "$PDF" || true
else
  echo "⚠️ Missing PDF: $PDF"
  echo "   (DOCX exists?)"
  ls -lh "$DOCX" 2>/dev/null || true
fi
