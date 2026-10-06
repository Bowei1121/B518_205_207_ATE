"""Conservative, read-only checks for a frozen macOS arm64 application."""

import argparse
import plistlib
import re
import subprocess
from pathlib import Path


def version_tuple(value):
    if not re.fullmatch(r"\d+(?:\.\d+){0,2}", value):
        raise ValueError("Invalid macOS version: {}".format(value))
    parts = tuple(int(part) for part in value.split("."))
    return parts + (0,) * (3 - len(parts))


def load_commands(text):
    """Read only OS version commands, never dylib current/compatibility versions."""
    versions, rpaths, dependencies = [], [], []
    for block in re.split(r"(?m)^\s*Load command \d+\s*$", text):
        match = re.search(r"(?m)^\s*cmd (LC_\w+)\s*$", block)
        if not match:
            continue
        name = match[1]
        if name in ("LC_BUILD_VERSION", "LC_VERSION_MIN_MACOSX"):
            if name == "LC_BUILD_VERSION":
                platform = re.search(r"(?m)^\s*platform (\S+)", block)
                if not platform or platform[1].lower() not in ("1", "macos", "macosx"):
                    raise ValueError("non-macOS or unknown build platform")
            field = "minos" if name == "LC_BUILD_VERSION" else "version"
            value = re.search(r"(?m)^\s*" + field + r" (\S+)", block)
            if not value:
                raise ValueError("minimum macOS version unavailable")
            version_tuple(value[1])
            versions.append(value[1])
        elif name == "LC_RPATH" or name in (
            "LC_LOAD_DYLIB", "LC_LOAD_WEAK_DYLIB", "LC_REEXPORT_DYLIB",
            "LC_LOAD_UPWARD_DYLIB", "LC_LAZY_LOAD_DYLIB",
        ):
            field = "path" if name == "LC_RPATH" else "name"
            value = re.search(r"(?m)^\s*" + field + r" (.+?) \(offset \d+\)", block)
            if not value:
                raise ValueError("unreadable {}".format(name))
            (rpaths if name == "LC_RPATH" else dependencies).append(value[1])
    return versions, rpaths, dependencies


def inspect_bundle(app, target="15.0", architecture="arm64", run=subprocess.run):
    target_version = version_tuple(target)
    app = Path(app).resolve()
    errors, binaries = [], {}

    def command(*args):
        return run(list(args), capture_output=True, text=True, check=True).stdout

    def inside(path):
        return app in path.resolve().parents

    try:
        with (app / "Contents/Info.plist").open("rb") as handle:
            info = plistlib.load(handle)
        if version_tuple(info["LSMinimumSystemVersion"]) != target_version:
            errors.append("Info.plist: LSMinimumSystemVersion must equal {}".format(target))
        executable = app / "Contents/MacOS" / info["CFBundleExecutable"]
        if not executable.is_file() or not inside(executable):
            errors.append("Info.plist: bundled executable missing or external")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return ["Info.plist: {}".format(exc)]

    for path in app.rglob("*"):
        if path.is_symlink() and (not inside(path) or not path.exists()):
            errors.append("{}: external or broken symlink".format(path.relative_to(app)))
            continue
        if not path.is_file() or path.resolve() in binaries:
            continue
        display = str(path.relative_to(app))
        try:
            if "Mach-O" not in command("file", "-b", str(path)):
                continue
            if architecture not in command("lipo", "-archs", str(path)).split():
                errors.append("{}: {} architecture missing".format(display, architecture))
                continue
            versions, rpaths, dependencies = load_commands(
                command("otool", "-arch", architecture, "-l", str(path)))
            if not versions:
                errors.append("{}: minimum macOS version unavailable".format(display))
            elif max(map(version_tuple, versions)) > target_version:
                errors.append("{}: requires macOS {}, target is {}".format(
                    display, max(versions, key=version_tuple), target))
            binaries[path.resolve()] = (rpaths, dependencies)
        except (OSError, subprocess.CalledProcessError, ValueError) as exc:
            errors.append("{}: inspection failed: {}".format(display, exc))
    if not binaries:
        errors.append("No inspectable {} Mach-O binaries found in {}".format(architecture, app))
    if executable.resolve() not in binaries:
        errors.append("Main executable is not an inspectable {} Mach-O binary".format(architecture))

    def expand(value, loader):
        for prefix, base in (("@loader_path", loader.parent),
                             ("@executable_path", executable.parent)):
            if value == prefix or value.startswith(prefix + "/"):
                return (base / value[len(prefix):].lstrip("/")).resolve()
        return Path(value).resolve() if value.startswith("/") else None

    visited = set()

    def check_dependencies(path, inherited=(), stack=()):
        if path in stack:
            return
        rpaths, dependencies = binaries[path]
        search = tuple(dict.fromkeys(
            [expand(value, path) for value in rpaths if expand(value, path) is not None]
            + list(inherited)))
        key = (path, search)
        if key in visited:
            return
        visited.add(key)
        for dependency in dependencies:
            if dependency.startswith(("/System/Library/", "/usr/lib/")):
                continue
            if dependency.startswith("@rpath/"):
                candidates = [base / dependency[len("@rpath/"):] for base in search]
            else:
                expanded = expand(dependency, path)
                candidates = [expanded] if expanded is not None else []
            resolved = next((candidate.resolve() for candidate in candidates
                             if candidate.is_file()), None)
            if (dependency.startswith("/") or resolved is None or not inside(resolved)
                    or resolved not in binaries):
                errors.append("{}: unresolved or external dependency {}".format(
                    path.relative_to(app), dependency))
            else:
                check_dependencies(resolved, search, stack + (path,))

    main = executable.resolve()
    if main in binaries:
        check_dependencies(main)
    # Python extensions are loaded dynamically, outside the static executable graph.
    main_search = tuple(expand(value, main) for value in binaries.get(main, ([], []))[0]
                        if expand(value, main) is not None)
    checked = {path for path, _search in visited}
    for path in binaries:
        if path not in checked:
            check_dependencies(path, main_search)
    return list(dict.fromkeys(errors))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app", type=Path)
    parser.add_argument("--target", default="15.0")
    parser.add_argument("--architecture", choices=("arm64", "x86_64"), default="arm64")
    args = parser.parse_args()
    problems = inspect_bundle(args.app, args.target, args.architecture)
    if problems:
        parser.exit(1, "Bundle compatibility check failed:\n" + "\n".join(problems) + "\n")
    print("Bundle compatibility check passed for macOS {} {}".format(
        args.target, args.architecture))
