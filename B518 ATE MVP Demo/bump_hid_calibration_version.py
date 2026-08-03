#!/usr/bin/env python3
"""Increment the standalone HID calibration patch version."""
from __future__ import annotations

import re
from pathlib import Path


VERSION_FILE = Path(__file__).with_name("hid_calibration_version.py")
VERSION_LINE = re.compile(r'^(VERSION\s*=\s*")(\d+)\.(\d+)\.(\d+)("\s*)$', re.MULTILINE)


def bump_version(source: str) -> tuple[str, str]:
    match = VERSION_LINE.search(source)
    if match is None:
        raise RuntimeError(f"Cannot find VERSION in {VERSION_FILE.name}")
    major, minor, patch = (int(value) for value in match.group(2, 3, 4))
    version = f"{major}.{minor}.{patch + 1}"
    return VERSION_LINE.sub(rf"\g<1>{version}\g<5>", source, count=1), version


def main() -> int:
    updated, version = bump_version(VERSION_FILE.read_text(encoding="utf-8"))
    VERSION_FILE.write_text(updated, encoding="utf-8")
    print(version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
