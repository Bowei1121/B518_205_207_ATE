#!/bin/bash
# Keep an activated Conda environment from silently selecting its own Aqua Tk.
set -euo pipefail
APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
if [[ -n "${PYTHON_BIN:-}" ]]; then
  desktop_python="$PYTHON_BIN"
else
  desktop_python=""
  for candidate in \
    /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 \
    /Library/Frameworks/Python.framework/Versions/Current/bin/python3 \
    /Library/Frameworks/Python.framework/Versions/3.{14,13,11,10,9,8}/bin/python3; do
    if [[ -x "$candidate" ]]; then
      desktop_python="$candidate"
      break
    fi
  done
  if [[ -z "$desktop_python" ]]; then
    printf '%s\n' '找不到 Python.org Framework Python；請設定 PYTHON_BIN=/完整路徑/python3。' >&2
    exit 1
  fi
fi
cd "$APP_DIR"
"$desktop_python" -c 'import sys, tkinter; print("Desktop Python: {} | Python {} | Tcl/Tk {}".format(sys.executable, sys.version.split()[0], tkinter.TkVersion), flush=True)'
if [[ $# -eq 0 ]]; then
  set -- src/b518_log_solution.py
fi
exec "$desktop_python" "$@"
