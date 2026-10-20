#!/bin/bash
# Keep an activated Conda environment from silently selecting its own Aqua Tk.
set -euo pipefail
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
if [[ -n "${PYTHON_BIN:-}" ]]; then
  desktop_python="$PYTHON_BIN"
else
  desktop_python=/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12
fi
cd "$APP_DIR"
[[ -x "$desktop_python" ]] || {
  printf '%s\n' '找不到 Python.org Python 3.12.10；請安裝 Python.org 3.12.10 universal2，或設定 PYTHON_BIN。' >&2
  exit 1
}
"$desktop_python" scripts/check_macos_build_python.py --exact-version 3.12.10 \
  --architecture "$(uname -m)" \
  --requirements requirements/requirements-macos15-arm64.txt \
  --require-virtualenv
if [[ $# -eq 0 ]]; then
  set -- src/b518_log_solution.py
fi
exec "$desktop_python" "$@"
