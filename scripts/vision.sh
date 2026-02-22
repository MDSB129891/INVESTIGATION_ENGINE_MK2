#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [ "${#}" -lt 2 ]; then
  echo "usage: scripts/vision.sh TICKER \"thesis text\" [--peers A,B] [--strict]"
  exit 1
fi

python3 scripts/vision.py "$@"

