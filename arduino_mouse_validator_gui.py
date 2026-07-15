#!/usr/bin/env python3
"""GUI-only entry point for packaging Arduino Mouse Validator as a macOS app."""

from __future__ import annotations

import sys

from arduino_mouse_validator import main


if __name__ == "__main__":
    # Keep extra options available for testing, while always opening the GUI.
    raise SystemExit(main(["--gui", *sys.argv[1:]]))
