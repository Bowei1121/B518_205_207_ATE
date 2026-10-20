"""Validate the Python and Tk interpreter used by a native macOS build."""

import argparse
import importlib
import importlib.metadata
import platform
import re
import sys
from pathlib import Path


def check_python(version=None, machine=None, importer=importlib.import_module,
                 required_architecture="arm64", required_version=(3, 12),
                 required_packages=(), package_version=importlib.metadata.version,
                 in_virtualenv=None, require_virtualenv=False):
    errors = []
    actual_version = tuple((version or sys.version_info)[:len(required_version)])
    actual_machine = machine or platform.machine()
    if actual_version != tuple(required_version):
        expected = ".".join(map(str, required_version))
        actual = ".".join(map(str, (version or sys.version_info)[:3]))
        errors.append("Python {} required; this interpreter is Python {}. Set PYTHON_BIN to the "
                      "required interpreter.".format(expected, actual))
    if actual_machine != required_architecture:
        errors.append("Native {} Python required; this interpreter is {}. Do not use another "
                      "architecture or Rosetta Terminal.".format(required_architecture, actual_machine))
    if require_virtualenv and not (sys.prefix != sys.base_prefix if in_virtualenv is None else in_virtualenv):
        errors.append("A Python virtual environment is required; create and activate the project .venv.")
    try:
        importer("tkinter")
        importer("_tkinter")
    except (ImportError, OSError) as exc:
        errors.append("Tk unavailable ({}); reinstall Python.org 3.12.10 with Tcl/Tk support.".format(exc))
    for distribution, expected in required_packages:
        try:
            actual = package_version(distribution)
        except importlib.metadata.PackageNotFoundError:
            errors.append("Missing {}=={}; install the pinned requirements in this interpreter.".format(
                distribution, expected))
            continue
        except (ImportError, OSError, ValueError) as exc:
            errors.append("Could not read {} version ({}); reinstall the pinned requirements.".format(
                distribution, exc))
            continue
        if actual != expected:
            errors.append("{}=={} required; found {}. Reinstall the pinned requirements.".format(
                distribution, expected, actual))
    return errors


def read_pinned_requirements(filename):
    """Read exact package pins from a requirements file and its recursive includes."""
    pins = {}
    visited = set()

    def visit(path):
        path = Path(path).resolve()
        if path in visited:
            return
        visited.add(path)
        for number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            line = raw_line.split("#", 1)[0].strip()
            if not line:
                continue
            if line.startswith(("-r ", "--requirement ")):
                include = line.split(None, 1)[1]
                visit(path.parent / include)
                continue
            if line.startswith("-"):
                continue
            match = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9._-]*)==([A-Za-z0-9][A-Za-z0-9._+-]*)", line)
            if not match:
                raise ValueError("{}:{} must pin a package with ==".format(path, number))
            name = re.sub(r"[-_.]+", "-", match.group(1)).lower()
            version = match.group(2)
            previous = pins.get(name)
            if previous is not None and previous != version:
                raise ValueError("Conflicting pins for {}: {} and {}".format(name, previous, version))
            pins[name] = version

    visit(filename)
    return sorted(pins.items())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--architecture", choices=("arm64", "x86_64"), default="arm64")
    parser.add_argument("--exact-version", help="Require this full interpreter version, e.g. 3.12.10.")
    parser.add_argument("--requirements", help="Verify exact package pins from this file and its -r includes.")
    parser.add_argument("--require-virtualenv", action="store_true",
                        help="Fail unless this interpreter is running from a virtual environment.")
    args = parser.parse_args()
    required_version = (3, 12)
    if args.exact_version:
        try:
            required_version = tuple(int(part) for part in args.exact_version.split("."))
            if len(required_version) != 3:
                raise ValueError
        except ValueError:
            parser.error("--exact-version must be MAJOR.MINOR.PATCH")
    try:
        packages = read_pinned_requirements(args.requirements) if args.requirements else ()
    except (OSError, ValueError) as exc:
        parser.error("cannot read requirements: {}".format(exc))
    problems = check_python(required_architecture=args.architecture,
                            required_version=required_version,
                            required_packages=packages,
                            require_virtualenv=args.require_virtualenv)
    if problems:
        sys.exit("Environment check failed:\n- " + "\n- ".join(problems))
    print("Environment check passed: {} (Python {}, {}, target {}, virtualenv {})".format(
        sys.executable, platform.python_version(), platform.machine(), args.architecture,
        "yes" if sys.prefix != sys.base_prefix else "no"))
    for distribution, version in packages:
        print("  {}=={}".format(distribution, version))
