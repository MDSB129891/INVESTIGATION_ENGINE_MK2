#!/usr/bin/env bash
set -euo pipefail

TICKER="${1:-}"
THESIS="${2:-}"

if [ -z "$TICKER" ]; then
  echo "Usage: ./scripts/run_dopamine.sh TICKER [thesis.json]"
  echo "Example: ./scripts/run_dopamine.sh GM theses/GM_custom.json"
  exit 1
fi

TICKER="$(echo "$TICKER" | tr '[:lower:]' '[:upper:]')"

echo "⚡ DOPAMINE RUN"
echo "ticker=$TICKER"
echo "thesis=${THESIS:-<none>}"
echo ""

# 1) Full engine run (creates dashboard, clickpack, alerts, claim evidence, etc.)
if [ -n "${THESIS:-}" ]; then
  ./scripts/run_galactus.sh "$TICKER" "$THESIS"
else
  ./scripts/run_thanos.sh "$TICKER"
fi

# 2) Build SUPER memo (the hand-holding, explain-everything memo)
if [ -n "${THESIS:-}" ]; then
  python3 scripts/build_super_memo.py --ticker "$TICKER" --thesis "$THESIS"
else
  # fallback thesis: base auto thesis (if exists)
  if [ -f "theses/${TICKER}_thesis_base.json" ]; then
    python3 scripts/build_super_memo.py --ticker "$TICKER" --thesis "theses/${TICKER}_thesis_base.json"
  else
    echo "⚠️ No thesis provided and no theses/${TICKER}_thesis_base.json found. Skipping SUPER memo."
  fi
fi

echo ""
echo "🚀 OPENING RESULTS (dopamine mode)"

# 3) Open the goodies (best effort)
# DISABLED (JARVIS controls opening): [ -f "outputs/decision_dashboard_${TICKER}.html" ] && open "outputs/decision_dashboard_${TICKER}.html" || true
[ -f "outputs/news_clickpack_${TICKER}.html" ] && open "outputs/news_clickpack_${TICKER}.html" || true
[ -f "outputs/claim_evidence_${TICKER}.html" ] && open "outputs/claim_evidence_${TICKER}.html" || true

[ -f "export/${TICKER}_SUPER_Memo.docx" ] && open "export/${TICKER}_SUPER_Memo.docx" || true
[ -f "outputs/${TICKER}_SUPER_Memo.md" ] && open "outputs/${TICKER}_SUPER_Memo.md" || true

echo "✅ DONE. If something didn’t open, it usually means the file wasn’t generated (or the name differs)."
