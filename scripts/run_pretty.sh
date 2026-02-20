#!/usr/bin/env bash
set -euo pipefail

TICKER="${1:?ticker required}"
THESIS="${2:?thesis json required}"
T="$(echo "$TICKER" | tr '[:lower:]' '[:upper:]')"

echo "🚀 PRETTY RUN: $T"
echo "   thesis: $THESIS"

# 1) Ensure data exists for this ticker (you already do this via thanos)
# If you want auto: uncomment next line
# ./scripts/run_thanos.sh "$T" >/dev/null 2>&1 || true

# 2) Build pretty memo
python3 scripts/build_superplus_pretty.py --ticker "$T" --thesis "$THESIS"

# 3) Open ONLY 2 things, in order
if [ -f "outputs/decision_dashboard_${T}.html" ]; then
# DISABLED (JARVIS controls opening):   open "outputs/decision_dashboard_${T}.html" || true
fi
if [ -f "export/${T}_SUPERPLUS_PRETTY.pdf" ]; then
  open "export/${T}_SUPERPLUS_PRETTY.pdf" || true
else
  echo "⚠️ Missing PDF: export/${T}_SUPERPLUS_PRETTY.pdf"
fi
