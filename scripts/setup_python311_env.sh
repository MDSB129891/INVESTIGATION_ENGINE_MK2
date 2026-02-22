#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

pick_py() {
  local c
  for c in python3.14 python3.13 python3.12 python3.11 python3; do
    if command -v "$c" >/dev/null 2>&1; then
      if "$c" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 11) else 1)
PY
      then
        command -v "$c"
        return 0
      fi
    fi
  done
  return 1
}

PY_BIN="$(pick_py || true)"
if [[ -z "${PY_BIN:-}" ]]; then
  echo "Python 3.11+ not found."
  echo "Install with one of:"
  echo "  brew install python@3.12"
  echo "  pyenv install 3.12.9"
  exit 1
fi

if [[ -d ".venv" ]]; then
  backup=".venv.backup.$(date +%Y%m%d%H%M%S)"
  echo "Existing .venv moved to $backup"
  mv .venv "$backup"
fi

echo "Creating .venv with $PY_BIN"
"$PY_BIN" -m venv .venv

.venv/bin/python -m pip install --upgrade pip setuptools wheel
.venv/bin/pip install -r requirements.txt

echo "Done."
echo "Activate with: source .venv/bin/activate"
echo "Python: $(.venv/bin/python --version)"
