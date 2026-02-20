#!/usr/bin/env bash
set -euo pipefail

TICKER="${1:-}"
MODE="${2:-open_only}"   # open_only | nuke

if [ -z "${TICKER}" ]; then
  echo "Usage: ./scripts/cleanup_outputs.sh TICKER [open_only|nuke]"
  exit 1
fi

T="$(echo "$TICKER" | tr '[:lower:]' '[:upper:]')"

echo "🧹 CLEANUP for ${T} (mode=${MODE})"

echo ""
echo "✅ Canon outputs (keep):"
echo " - outputs/decision_dashboard_${T}.html"
echo " - export/${T}_SUPER_Memo.pdf"
echo " - outputs/news_clickpack_${T}.html"
echo " - outputs/claim_evidence_${T}.html"
echo " - outputs/alerts_${T}.json"
echo " - outputs/veracity_${T}.json"

if [ "${MODE}" = "nuke" ]; then
  echo ""
  echo "🧨 Removing repetitive outputs for ${T}..."

  rm -f "outputs/${T}_Full_Investment_Memo.md" || true
  rm -f "export/${T}_Full_Investment_Memo.docx" || true
  rm -f "export/${T}_Full_Investment_Memo.pdf" || true

  rm -f "outputs/${T}_BIG_Memo.md" || true
  rm -f "export/${T}_BIG_Memo.docx" || true

  rm -f "outputs/${T}_ULTRA_Memo.md" || true
  rm -f "export/${T}_ULTRA_Memo.docx" || true
  rm -f "export/${T}_ULTRA_Memo.pdf" || true

  rm -f "outputs/thesis_validation_${T}.md" || true
  rm -f "export/${T}_Thesis_Memo.docx" || true

  echo "✅ Done."
fi

echo ""
echo "🚀 Opening canon outputs (in order)..."
# DISABLED (JARVIS controls opening): [ -f "outputs/decision_dashboard_${T}.html" ] && open "outputs/decision_dashboard_${T}.html" || true
[ -f "export/${T}_SUPER_Memo.pdf" ] && open "export/${T}_SUPER_Memo.pdf" || true
[ -f "outputs/news_clickpack_${T}.html" ] && open "outputs/news_clickpack_${T}.html" || true
[ -f "outputs/claim_evidence_${T}.html" ] && open "outputs/claim_evidence_${T}.html" || true
