#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${PORT:-8765}"
HOST="${HOST:-127.0.0.1}"

if [[ $# -lt 2 ]]; then
  echo "Usage:"
  echo "  ./scripts/run_local_armor_showcase.sh <TICKER> \"<THESIS>\" [PEERS]"
  echo
  echo "Example:"
  echo "  ./scripts/run_local_armor_showcase.sh GOOGL \"Google benefits from AI demand over next 6 months\" \"MSFT,AMZN\""
  exit 1
fi

TICKER="$(echo "$1" | tr '[:lower:]' '[:upper:]')"
THESIS="$2"
PEERS="${3:-}"

cd "$ROOT"

python_ge_311() {
  local py="$1"
  "$py" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
}

select_python_311() {
  local candidates=()
  if [[ -x ".venv/bin/python" ]]; then
    candidates+=(".venv/bin/python")
  fi
  candidates+=("python3.14" "python3.13" "python3.12" "python3.11" "python3")

  local c path
  for c in "${candidates[@]}"; do
    if [[ -x "$c" ]]; then
      path="$c"
    elif command -v "$c" >/dev/null 2>&1; then
      path="$(command -v "$c")"
    else
      continue
    fi
    if python_ge_311 "$path"; then
      echo "$path"
      return 0
    fi
  done
  return 1
}

ensure_venv() {
  local py="$1"
  local rebuild=0
  if [[ ! -x ".venv/bin/python" ]]; then
    rebuild=1
  elif ! python_ge_311 ".venv/bin/python"; then
    rebuild=1
  fi

  if [[ "$rebuild" -eq 1 ]]; then
    echo "== Creating .venv with $py (Python 3.11+) =="
    if [[ -d ".venv" ]]; then
      local backup=".venv.backup.$(date +%Y%m%d%H%M%S)"
      echo "== Existing .venv moved to $backup =="
      mv .venv "$backup"
    fi
    "$py" -m venv .venv
    .venv/bin/python -m pip install --upgrade pip setuptools wheel
    .venv/bin/pip install -r requirements.txt
  fi
}

PY_BIN="$(select_python_311 || true)"
if [[ -z "${PY_BIN:-}" ]]; then
  echo "ERROR: Python 3.11+ not found."
  echo "Install one of these first:"
  echo "  brew install python@3.12"
  echo "  or pyenv install 3.12.9"
  exit 1
fi

ensure_venv "$PY_BIN"

# shellcheck disable=SC1091
source .venv/bin/activate
PY_RUN=".venv/bin/python"

if [[ -f ".env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

echo "== Running full Vision pipeline =="
if [[ -n "$PEERS" ]]; then
  "$PY_RUN" scripts/vision.py "$TICKER" "$THESIS" --peers "$PEERS" --strict
else
  "$PY_RUN" scripts/vision.py "$TICKER" "$THESIS" --strict
fi

PID_FILE="outputs/http_server.pid"
LOG_FILE="outputs/http_server.log"
mkdir -p outputs

if [[ -f "$PID_FILE" ]]; then
  OLD_PID="$(cat "$PID_FILE" || true)"
  if [[ -n "${OLD_PID:-}" ]] && ps -p "$OLD_PID" >/dev/null 2>&1; then
    echo "== Reusing existing local server (PID $OLD_PID) =="
  else
    rm -f "$PID_FILE"
  fi
fi

if [[ ! -f "$PID_FILE" ]]; then
  echo "== Starting local HTTP server at http://$HOST:$PORT =="
  nohup "$PY_RUN" -m http.server "$PORT" --bind "$HOST" > "$LOG_FILE" 2>&1 &
  echo $! > "$PID_FILE"
  sleep 1
fi

HUD_URL="http://$HOST:$PORT/export/CANON_${TICKER}/${TICKER}_IRONMAN_HUD.html"
NEWS_URL="http://$HOST:$PORT/export/CANON_${TICKER}/${TICKER}_NEWS_SOURCES.html"
LEGION_URL="http://$HOST:$PORT/outputs/iron_legion_command_${TICKER}.html"
MISSION_URL="http://$HOST:$PORT/outputs/mission_report_${TICKER}.html"
RECO_URL="http://$HOST:$PORT/outputs/recommendation_brief_${TICKER}.pdf"
COMMANDER_URL="http://$HOST:$PORT/outputs/legion_commander_${TICKER}.html"
STORMBREAKER_URL="http://$HOST:$PORT/export/CANON_${TICKER}/${TICKER}_STORMBREAKER.html"

echo
echo "== Open these URLs =="
echo "HUD:           $HUD_URL"
echo "News Sources:  $NEWS_URL"
echo "Iron Legion:   $LEGION_URL"
echo "Mission Report:$MISSION_URL"
echo "Rec Brief PDF: $RECO_URL"
echo "Commander:     $COMMANDER_URL"
echo "Stormbreaker:  $STORMBREAKER_URL"
echo
echo "Stop server later with:"
echo "  kill \$(cat outputs/http_server.pid)"

open_url() {
  local url="$1"
  if command -v open >/dev/null 2>&1; then
    open "$url" && return 0
    open -a "Google Chrome" "$url" && return 0
    open -a "Safari" "$url" && return 0
  fi
  "$PY_RUN" -m webbrowser "$url" >/dev/null 2>&1 && return 0
  return 1
}

echo "== Opening full showcase in browser =="
open_url "$COMMANDER_URL" || echo "Could not auto-open Commander. Open manually: $COMMANDER_URL"
open_url "$HUD_URL" || echo "Could not auto-open HUD. Open manually: $HUD_URL"
open_url "$NEWS_URL" || echo "Could not auto-open News Sources. Open manually: $NEWS_URL"
open_url "$LEGION_URL" || echo "Could not auto-open Iron Legion. Open manually: $LEGION_URL"
open_url "$STORMBREAKER_URL" || echo "Could not auto-open Stormbreaker. Open manually: $STORMBREAKER_URL"
open_url "$MISSION_URL" || echo "Could not auto-open Mission Report. Open manually: $MISSION_URL"
open_url "$RECO_URL" || echo "Could not auto-open Recommendation PDF. Open manually: $RECO_URL"
