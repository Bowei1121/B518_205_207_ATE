"""Validate the interpreter actually used by the macOS 15.5 arm64 build."""

import importlib
import platform
import sys


def check_python(version=None, machine=None, importer=importlib.import_module):
    errors = []
    if tuple((version or sys.version_info)[:2]) != (3, 12):
        errors.append("Python 3.12 required; install Python.org 3.12.10 universal2 or set PYTHON_BIN.")
    if (machine or platform.machine()) != "arm64":
        errors.append("Native arm64 Python required; do not use an Intel interpreter or Rosetta Terminal.")
    try:
        importer("tkinter")
        importer("_tkinter")
    except (ImportError, OSError) as exc:
        errors.append("Tk unavailable ({}); reinstall Python.org 3.12.10 with Tcl/Tk support.".format(exc))
    return errors


if __name__ == "__main__":
    problems = check_python()
    if problems:
        sys.exit("\n".join(problems))
    print("Python preflight passed: {} ({})".format(sys.executable, platform.machine()))
