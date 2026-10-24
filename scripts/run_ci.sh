#!/usr/bin/env bash
# Minimal CI hook: run the unit-test suite (same command as GitHub Actions).
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN=python3
  else
    PYTHON_BIN=python
  fi
fi
"$PYTHON_BIN" -m unittest discover -s tests -p 'test_*.py' -v
