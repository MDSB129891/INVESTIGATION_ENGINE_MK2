#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [ "${#}" -lt 2 ]; then
  echo "usage: scripts/godkiller.sh TICKER \"thesis text\" [--peers A,B]"
  exit 1
fi

TICKER="$1"
THESIS="$2"
shift 2

python3 scripts/vision.py "$TICKER" "$THESIS" --godkiller "$@"

