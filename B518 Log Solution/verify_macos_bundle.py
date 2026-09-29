"""Reject a frozen macOS app that cannot run on the requested older system."""

import argparse
import re
import subprocess
from pathlib import Path


def version_tuple(value):
    return tuple(int(part) for part in value.split("."))


def inspect_bundle(app, target="15.5", run=subprocess.run):
    errors = []
    app = Path(app)
    binaries = []
    for path in app.rglob("*"):
        if not path.is_file():
            continue
        kind = run(["file", "-b", str(path)], capture_output=True, text=True, check=True).stdout
        if "Mach-O" in kind:
            binaries.append(path)
    if not binaries:
        return ["No Mach-O binaries found in {}".format(app)]
    names = {path.name for path in binaries}
    for path in binaries:
        display = str(path.relative_to(app))
        archs = run(["lipo", "-archs", str(path)], capture_output=True, text=True, check=True).stdout.split()
        if "arm64" not in archs:
            errors.append("{}: arm64 architecture missing".format(display))
            continue
        commands = run(["otool", "-l", str(path)], capture_output=True, text=True, check=True).stdout
        versions = re.findall(r"\b(?:minos|version)\s+(\d+\.\d+(?:\.\d+)?)", commands)
        if not versions:
            errors.append("{}: minimum macOS version unavailable".format(display))
        elif any(version_tuple(value) > version_tuple(target) for value in versions):
            errors.append("{}: requires macOS {}, target is {}".format(display, max(versions, key=version_tuple), target))
        libraries = run(["otool", "-L", str(path)], capture_output=True, text=True, check=True).stdout
        for line in libraries.splitlines()[1:]:
            dependency = line.strip().split(" (")[0]
            if dependency.startswith(("/System/Library/", "/usr/lib/")):
                continue
            if dependency.startswith("@rpath/"):
                if Path(dependency).name not in names:
                    errors.append("{}: unresolved bundled dependency {}".format(display, dependency))
            elif dependency.startswith("@loader_path/"):
                resolved = path.parent / dependency[len("@loader_path/"):]
                if not resolved.is_file():
                    errors.append("{}: unresolved loader dependency {}".format(display, dependency))
            elif dependency.startswith("@executable_path/"):
                resolved = app / "Contents" / "MacOS" / dependency[len("@executable_path/"):]
                if not resolved.is_file():
                    errors.append("{}: unresolved executable dependency {}".format(display, dependency))
            elif dependency.startswith("/"):
                errors.append("{}: external dependency {}".format(display, dependency))
    return errors


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app", type=Path)
    parser.add_argument("--target", default="15.5")
    args = parser.parse_args()
    problems = inspect_bundle(args.app, args.target)
    if problems:
        parser.exit(1, "Bundle compatibility check failed:\n" + "\n".join(problems) + "\n")
    print("Bundle compatibility check passed for macOS {} arm64".format(args.target))
