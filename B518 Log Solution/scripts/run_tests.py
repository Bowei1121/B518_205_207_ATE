"""Run the application tests from any working directory; optionally pass test modules."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for directory in ("src", "tools", "scripts", "tests"):
    sys.path.insert(0, str(ROOT / directory))

if __name__ == "__main__":
    loader = unittest.defaultTestLoader
    if len(sys.argv) > 1:
        suite = loader.loadTestsFromNames(sys.argv[1:])
    else:
        suite = loader.discover(str(ROOT / "tests"))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(not result.wasSuccessful())
