"""Preserve the tracked version in CI; retain patch increments for local builds."""

import argparse
import re
from pathlib import Path


def prepare_version(path, preserve=False):
    value = path.read_text().strip()
    if re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", value) is None:
        raise ValueError("VERSION must contain MAJOR.MINOR.PATCH without leading zeros")
    if not preserve:
        major, minor, patch = value.split(".")
        value = "{}.{}.{}".format(major, minor, int(patch) + 1)
        path.write_text(value + "\n")
    return value


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preserve-version", action="store_true")
    args = parser.parse_args()
    try:
        print(prepare_version(Path("VERSION"), preserve=args.preserve_version))
    except (OSError, ValueError) as error:
        parser.exit(2, str(error) + "\n")
