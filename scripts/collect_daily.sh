#!/usr/bin/env bash
set -euo pipefail

VENV=${VENV:-.venv}
if [ -x "$VENV/bin/python" ]; then
  PYTHON=${PYTHON:-$VENV/bin/python}
else
  PYTHON=${PYTHON:-python3}
fi
DATE=${1:-$(date +%F)}

if [ -x "$PYTHON" ] || command -v "$PYTHON" >/dev/null 2>&1; then
  :
else
  echo "Python executable not found at $PYTHON" >&2
  echo "Activate your virtualenv or set VENV/PYTHON to the right path, or install python3." >&2
  exit 1
fi

$PYTHON collector/run.py --date "$DATE" --headless
