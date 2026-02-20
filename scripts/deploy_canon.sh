#!/usr/bin/env bash
set -euo pipefail

TICKER="${1:-}"
THESIS_FILE="${2:-}"         # optional
MODE="${3:-open}"            # open | nuke

if [ -z "${TICKER}" ]; then
  echo "Usage:"
  echo "  ./scripts/deploy_canon.sh TICKER [thesis.json] [open|nuke]"
  echo ""
  echo "Examples:"
  echo "  ./scripts/deploy_canon.sh UBER"
  echo "  ./scripts/deploy_canon.sh GM theses/GM_custom.json nuke"
  exit 1
fi

T="$(echo "$TICKER" | tr '[:lower:]' '[:upper:]')"

echo "📦 CANON DEPLOY"
echo "Ticker: ${T}"
echo "Thesis: ${THESIS_FILE:-<none>}"
echo "Mode: ${MODE}"
echo ""

# 1) Run the engine + standard pack (news/veracity/alerts/dashboard/claim evidence)
if [ -n "${THESIS_FILE}" ]; then
  ./scripts/run_thanos.sh "${T}" "${THESIS_FILE}"
else
  ./scripts/run_thanos.sh "${T}"
fi

# 2) Build SUPER memo (MD + DOCX) using thesis file if provided
#    (This is where your metric explanation + storytime should live.)
if [ -n "${THESIS_FILE}" ]; then
  python3 scripts/build_super_memo.py --ticker "${T}" --thesis "${THESIS_FILE}"
else
  # fallback to base thesis if none passed
  python3 scripts/build_super_memo.py --ticker "${T}" --thesis "theses/${T}_thesis_base.json"
fi

# 3) Convert SUPER DOCX -> PDF (non-editable)
if [ -f "export/${T}_SUPER_Memo.docx" ]; then
  /opt/homebrew/bin/soffice --headless --convert-to pdf --outdir export "export/${T}_SUPER_Memo.docx" >/dev/null 2>&1 || true
fi

# 4) Optional: delete repetitive / noisy outputs (keep canon only)
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
echo "✅ CANON OUTPUTS (keep):"
echo " - outputs/decision_dashboard_${T}.html"
echo " - export/${T}_SUPER_Memo.pdf"
echo " - outputs/news_clickpack_${T}.html"
echo " - outputs/claim_evidence_${T}.html"
echo " - outputs/alerts_${T}.json"
echo " - outputs/veracity_${T}.json"

echo ""
echo "🚀 Opening (dopamine + order):"
# Only open these 4, in this order.
# DISABLED (JARVIS controls opening): [ -f "outputs/decision_dashboard_${T}.html" ] && open "outputs/decision_dashboard_${T}.html" || true
[ -f "export/${T}_SUPER_Memo.pdf" ] && open "export/${T}_SUPER_Memo.pdf" || true
[ -f "outputs/news_clickpack_${T}.html" ] && open "outputs/news_clickpack_${T}.html" || true
[ -f "outputs/claim_evidence_${T}.html" ] && open "outputs/claim_evidence_${T}.html" || true

echo ""
echo "🏁 Done."
