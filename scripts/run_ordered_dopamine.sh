#!/usr/bin/env bash
set -euo pipefail

TICKER="${1:-}"
THESIS="${2:-}"

if [ -z "$TICKER" ]; then
  echo "Usage: ./scripts/run_ordered_dopamine.sh TICKER [thesis.json]"
  echo "Example: ./scripts/run_ordered_dopamine.sh GM theses/GM_custom.json"
  exit 1
fi

TICKER="$(echo "$TICKER" | tr '[:lower:]' '[:upper:]')"

echo "⚡ ORDERED DOPAMINE RUN"
echo "ticker=$TICKER"
echo "thesis=${THESIS:-<none>}"
echo ""

# 1) Full pipeline
if [ -n "${THESIS:-}" ]; then
  ./scripts/run_galactus.sh "$TICKER" "$THESIS"
else
  ./scripts/run_thanos.sh "$TICKER"
fi

# 2) Build the beautiful SUPER memo (this is the missing piece)
if [ -n "${THESIS:-}" ]; then
  python3 scripts/build_super_memo.py --ticker "$TICKER" --thesis "$THESIS"
else
  # fallback to base thesis if it exists
  if [ -f "theses/${TICKER}_thesis_base.json" ]; then
    python3 scripts/build_super_memo.py --ticker "$TICKER" --thesis "theses/${TICKER}_thesis_base.json"
  else
    echo "⚠️ No thesis provided and no theses/${TICKER}_thesis_base.json found, skipping SUPER memo."
  fi
fi

echo ""
echo "🚀 OPENING (ordered dopamine)"
echo "1) Dashboard"
# DISABLED (JARVIS controls opening): [ -f "outputs/decision_dashboard_${TICKER}.html" ] && open "outputs/decision_dashboard_${TICKER}.html" || true
sleep 0.8

echo "2) SUPER Memo (Word)"
[ -f "export/${TICKER}_SUPER_Memo.docx" ] && open "export/${TICKER}_SUPER_Memo.docx" || true
sleep 0.8

echo "3) SUPER Memo (Markdown)"
[ -f "outputs/${TICKER}_SUPER_Memo.md" ] && open "outputs/${TICKER}_SUPER_Memo.md" || true
sleep 0.8

echo "4) Claim Evidence (HTML)"
[ -f "outputs/claim_evidence_${TICKER}.html" ] && open "outputs/claim_evidence_${TICKER}.html" || true
sleep 0.8

echo "5) News Clickpack"
[ -f "outputs/news_clickpack_${TICKER}.html" ] && open "outputs/news_clickpack_${TICKER}.html" || true
sleep 0.8

echo "6) Alerts (JSON)"
[ -f "outputs/alerts_${TICKER}.json" ] && open "outputs/alerts_${TICKER}.json" || true

echo ""
echo "✅ DONE. If something didn’t open, it usually means that file wasn’t generated."
