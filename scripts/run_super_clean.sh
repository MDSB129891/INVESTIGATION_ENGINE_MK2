#!/usr/bin/env bash
set -euo pipefail

TICKER="${1:?ticker required}"
TICKER_UP="$(echo "$TICKER" | tr '[:lower:]' '[:upper:]')"
THESIS_PATH="${2:-}"

# make sure data exists for ticker
./scripts/run_thanos.sh "$TICKER_UP" >/dev/null 2>&1 || true

# build clean memo (MD)
python3 scripts/build_super_clean_memo.py --ticker "$TICKER_UP" --thesis "${THESIS_PATH:-theses/${TICKER_UP}_custom.json}" || true

# convert MD -> PDF by going MD -> HTML -> PDF is overkill; easiest is: open MD + dashboard.
# If you insist on PDF, we can add md->docx->pdf in the next step with python-docx or pandoc.
echo ""
echo "OPEN (clean order):"
# DISABLED (JARVIS controls opening): [ -f "outputs/decision_dashboard_${TICKER_UP}.html" ] && open "outputs/decision_dashboard_${TICKER_UP}.html" || true
[ -f "outputs/${TICKER_UP}_SUPER_CLEAN.md" ] && open "outputs/${TICKER_UP}_SUPER_CLEAN.md" || true
