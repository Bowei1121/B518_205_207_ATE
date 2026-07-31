#!/usr/bin/env python3
"""Verify that executable B518 firmware changes include one legal SemVer bump."""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


FIRMWARE_DIR = Path(__file__).resolve().parent
VERSION_FILE = FIRMWARE_DIR / "firmware_version.h"
VERSION_DEFINE = re.compile(r'^#define\s+B518_FIRMWARE_VERSION\s+"(\d+)\.(\d+)\.(\d+)"\s*$', re.MULTILINE)


def parse_version(source: str) -> tuple[int, int, int]:
    match = VERSION_DEFINE.search(source)
    if match is None:
        raise ValueError("B518_FIRMWARE_VERSION must be a MAJOR.MINOR.PATCH numeric SemVer value")
    return tuple(int(value) for value in match.groups())


def legal_transition(old: tuple[int, int, int], new: tuple[int, int, int]) -> bool:
    """Accept exactly one declared hotfix, feature, or major increment."""
    major, minor, patch = old
    return new in {
        (major, minor, patch + 1),
        (major, minor + 1, 0),
        (major + 1, 0, 0),
    }


def git_output(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=FIRMWARE_DIR, text=True, stderr=subprocess.DEVNULL)


def base_file(base: str, relative_path: str) -> str | None:
    try:
        return git_output("show", f"{base}:{relative_path}")
    except subprocess.CalledProcessError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="HEAD", help="Git revision to compare with (default: HEAD)")
    args = parser.parse_args()
    repo_root = Path(git_output("rev-parse", "--show-toplevel").strip())
    relative_dir = FIRMWARE_DIR.relative_to(repo_root).as_posix()
    relative_version = VERSION_FILE.relative_to(repo_root).as_posix()
    changed = set(git_output("diff", "--name-only", args.base, "--", relative_dir).splitlines())
    # git diff intentionally omits an untracked initial header.  Treat the
    # canonical version file as changed when it does not exist in the base.
    if VERSION_FILE.is_file() and base_file(args.base, relative_version) is None:
        changed.add(relative_version)
    executable = {name for name in changed if Path(name).suffix in {".ino", ".h", ".hpp", ".cpp", ".c"}}
    if not executable:
        print("Firmware version check passed: no executable firmware changes.")
        return 0
    if relative_version not in changed:
        print("Firmware version check failed: executable firmware changed without updating firmware_version.h.", file=sys.stderr)
        return 1
    try:
        new = parse_version(VERSION_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"Firmware version check failed: {exc}", file=sys.stderr)
        return 1
    old_source = base_file(args.base, relative_version)
    if old_source is None:
        if new == (1, 0, 0):
            print("Firmware version check passed: initial firmware version 1.0.0.")
            return 0
        print("Firmware version check failed: initial tracked version must be 1.0.0.", file=sys.stderr)
        return 1
    try:
        old = parse_version(old_source)
    except ValueError as exc:
        print(f"Firmware version check failed: base version is invalid: {exc}", file=sys.stderr)
        return 1
    if not legal_transition(old, new):
        print(f"Firmware version check failed: {old[0]}.{old[1]}.{old[2]} -> {new[0]}.{new[1]}.{new[2]} is not one legal increment.", file=sys.stderr)
        return 1
    print(f"Firmware version check passed: {old[0]}.{old[1]}.{old[2]} -> {new[0]}.{new[1]}.{new[2]}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
