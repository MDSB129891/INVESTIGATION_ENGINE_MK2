#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

TICKER="${1:-}"
THESIS_TEXT="${2:-}"

if [[ -z "${TICKER}" || -z "${THESIS_TEXT}" ]]; then
  echo "Usage: ./scripts/run_everything.sh TICKER \"THESIS TEXT\""
  echo "Example: ./scripts/run_everything.sh UBER \"Drivers become employees and margins compress\""
  exit 1
fi

TICKER_UPPER="$(printf "%s" "${TICKER}" | tr '[:lower:]' '[:upper:]')"

default_peers_for_ticker() {
  case "$1" in
    GM) echo "F,TM" ;;
    F) echo "GM,TM" ;;
    TM) echo "GM,F" ;;
    TSLA) echo "GM,F" ;;
    UBER) echo "LYFT,DASH" ;;
    LYFT) echo "UBER,DASH" ;;
    DASH) echo "UBER,LYFT" ;;
    INTC) echo "AMD,NVDA" ;;
    AMD) echo "INTC,NVDA" ;;
    NVDA) echo "AMD,INTC" ;;
    AAPL) echo "MSFT,GOOGL" ;;
    MSFT) echo "AAPL,GOOGL" ;;
    GOOGL|GOOG) echo "MSFT,META" ;;
    META) echo "GOOGL,SNAP" ;;
    AMZN) echo "WMT,TGT" ;;
    WMT) echo "TGT,COST" ;;
    *) echo "SPY" ;;
  esac
}

PEERS_EFFECTIVE="${PEERS:-}"
if [[ -z "${PEERS_EFFECTIVE}" ]]; then
  PEERS_EFFECTIVE="$(default_peers_for_ticker "${TICKER_UPPER}")"
fi

PYTHON_BIN="python3"
if [[ -x ".venv/bin/python3" ]]; then
  PYTHON_BIN=".venv/bin/python3"
fi

echo "🚀 RUN EVERYTHING"
echo "Ticker: ${TICKER_UPPER}"
echo "Thesis: ${THESIS_TEXT}"
echo "Peers: ${PEERS_EFFECTIVE}"
echo ""

"${PYTHON_BIN}" scripts/vision.py "${TICKER_UPPER}" "${THESIS_TEXT}" \
  --peers "${PEERS_EFFECTIVE}" \
  --persist-refresh \
  --max-refresh-attempts "${ARC_REACTOR_MAX_ATTEMPTS:-5}" \
  --refresh-sleep-seconds "${ARC_REACTOR_RETRY_SLEEP_SEC:-15}"

echo ""
echo "🚀 OPENING PRIMARY OUTPUT (HUD)"

TO_OPEN=(
  "export/CANON_${TICKER_UPPER}/${TICKER_UPPER}_IRONMAN_HUD.html"
)

for f in "${TO_OPEN[@]}"; do
  if [[ -f "${f}" ]]; then
    echo "open ${f}"
    open "${f}" || true
  else
    echo "skip missing: ${f}"
  fi
done

echo ""
echo "Other outputs:"
echo "- Dashboard: outputs/decision_dashboard_${TICKER_UPPER}.html"
echo "- Legion: outputs/iron_legion_command_${TICKER_UPPER}.html"
echo "- J.A.R.V.I.S. News Sources (Primary news view): export/CANON_${TICKER_UPPER}/${TICKER_UPPER}_NEWS_SOURCES.html"
echo "- Stormbreaker: export/CANON_${TICKER_UPPER}/${TICKER_UPPER}_STORMBREAKER.html"
echo "- News Clickpack (Secondary drill-down): outputs/news_clickpack_${TICKER_UPPER}.html"
echo "- Receipts: outputs/receipts_${TICKER_UPPER}.html"
echo "- Timestone: export/CANON_${TICKER_UPPER}/${TICKER_UPPER}_TIMESTONE.html"
echo "- Memo PDF: export/${TICKER_UPPER}_Full_Investment_Memo.pdf"
echo "- Recommendation PDF: outputs/recommendation_brief_${TICKER_UPPER}.pdf"
echo ""
echo "✅ DONE"
