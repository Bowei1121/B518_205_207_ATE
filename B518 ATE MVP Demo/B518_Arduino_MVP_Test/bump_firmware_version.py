#!/usr/bin/env python3
"""Bump the canonical B518 Arduino firmware SemVer value."""
from __future__ import annotations

import argparse
import re
from pathlib import Path


VERSION_FILE = Path(__file__).with_name("firmware_version.h")
VERSION_LINE = re.compile(
    r'^(#define\s+B518_FIRMWARE_VERSION\s+")(\d+)\.(\d+)\.(\d+)("\s*)$', re.MULTILINE)


def bump_version(source: str, level: str) -> tuple[str, str]:
    """Return source with a single legal SemVer increment applied."""
    match = VERSION_LINE.search(source)
    if match is None:
        raise RuntimeError(f"Cannot find B518_FIRMWARE_VERSION in {VERSION_FILE.name}")
    major, minor, patch = (int(value) for value in match.group(2, 3, 4))
    if level == "hotfix":
        patch += 1
    elif level == "feature":
        minor, patch = minor + 1, 0
    elif level == "major":
        major, minor, patch = major + 1, 0, 0
    else:
        raise ValueError("level must be hotfix, feature, or major")
    version = f"{major}.{minor}.{patch}"
    return VERSION_LINE.sub(rf"\g<1>{version}\g<5>", source, count=1), version


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("level", choices=("hotfix", "feature", "major"))
    args = parser.parse_args()
    source = VERSION_FILE.read_text(encoding="utf-8")
    updated, version = bump_version(source, args.level)
    old = VERSION_LINE.search(source).group(2) + "." + VERSION_LINE.search(source).group(3) + "." + VERSION_LINE.search(source).group(4)
    VERSION_FILE.write_text(updated, encoding="utf-8")
    print(f"B518 firmware {old} -> {version} ({args.level})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
