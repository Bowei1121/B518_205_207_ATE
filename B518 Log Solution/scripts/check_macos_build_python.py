"""Validate the Python and Tk interpreter used by a native macOS build."""

import argparse
import importlib
import platform
import sys


def check_python(version=None, machine=None, importer=importlib.import_module,
                 required_architecture="arm64"):
    errors = []
    if tuple((version or sys.version_info)[:2]) != (3, 12):
        errors.append("Python 3.12 required; install Python.org 3.12.10 universal2 or set PYTHON_BIN.")
    if (machine or platform.machine()) != required_architecture:
        errors.append("Native {} Python required; do not use another architecture or Rosetta Terminal."
                      .format(required_architecture))
    try:
        importer("tkinter")
        importer("_tkinter")
    except (ImportError, OSError) as exc:
        errors.append("Tk unavailable ({}); reinstall Python.org 3.12.10 with Tcl/Tk support.".format(exc))
    return errors


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--architecture", choices=("arm64", "x86_64"), default="arm64")
    args = parser.parse_args()
    problems = check_python(required_architecture=args.architecture)
    if problems:
        sys.exit("\n".join(problems))
    print("Python preflight passed: {} ({}, {})".format(
        sys.executable, platform.machine(), args.architecture))
