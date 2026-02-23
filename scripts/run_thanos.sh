#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

TICKER="${1:-}"
ARG_THESIS_FILE="${2:-}"
BASE_THESIS="theses/${TICKER}_thesis_base.json"
THESIS_FILE="${THESIS_OVERRIDE:-${ARG_THESIS_FILE:-$BASE_THESIS}}"

if [[ -z "${TICKER}" ]]; then
  echo "Usage: ./scripts/run_thanos.sh TICKER [THESIS_JSON]"
  exit 1
fi

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

PYTHON_BIN="python3"
if [[ -x ".venv/bin/python3" ]]; then
  PYTHON_BIN=".venv/bin/python3"
fi

if [[ ! -f "$THESIS_FILE" ]]; then
  echo "❌ Thesis file not found: $THESIS_FILE"
  exit 1
fi

if [[ -n "${UNIVERSE:-}" ]]; then
  PEERS="$("$PYTHON_BIN" - "$TICKER" "$UNIVERSE" <<'PY'
import sys
t = sys.argv[1].upper()
u = [x.strip().upper() for x in sys.argv[2].split(",") if x.strip()]
print(",".join([x for x in u if x != t]))
PY
)"
elif [[ -n "${PEERS:-}" ]]; then
  PEERS="${PEERS}"
else
  PEERS="$(default_peers_for_ticker "${TICKER}")"
fi

echo "🟣 THANOS (compat wrapper -> VISION)"
echo "Ticker: ${TICKER}"
echo "Thesis file: ${THESIS_FILE}"
echo "Peers: ${PEERS:-<none>}"

"$PYTHON_BIN" scripts/vision.py \
  "${TICKER}" \
  --thesis-file "${THESIS_FILE}" \
  --peers "${PEERS}" \
  --persist-refresh \
  --max-refresh-attempts "${ARC_REACTOR_MAX_ATTEMPTS:-0}" \
  --refresh-sleep-seconds "${ARC_REACTOR_RETRY_SLEEP_SEC:-30}"

echo ""
echo "DONE ✅ THANOS via VISION"
echo "- outputs/decision_dashboard_${TICKER}.html"
echo "- outputs/veracity_${TICKER}.json"
echo "- outputs/alerts_${TICKER}.json"
echo "- outputs/iron_legion_command_${TICKER}.html"
echo "- export/CANON_${TICKER}/${TICKER}_IRONMAN_HUD.html"
echo "- export/${TICKER}_Full_Investment_Memo.pdf"
