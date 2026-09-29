import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from verify_macos_bundle import inspect_bundle, version_tuple


class BundleCheckTests(unittest.TestCase):
    def test_numeric_version_comparison(self):
        self.assertLess(version_tuple("15.5"), version_tuple("15.10"))

    def test_rejects_newer_binary_and_external_homebrew_library(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Path(directory) / "Example.app"
            app.mkdir()
            binary = app / "example"
            binary.touch()

            def fake_run(command, **_kwargs):
                outputs = {
                    "file": "Mach-O 64-bit executable arm64",
                    "lipo": "arm64",
                    "otool--l": "cmd LC_BUILD_VERSION\n    minos 26.0\n",
                    "otool--L": "example:\n\t/opt/homebrew/lib/libexample.dylib (compatibility version 1.0.0)\n",
                }
                key = command[0] if command[0] != "otool" else "otool-" + command[1]
                return SimpleNamespace(stdout=outputs[key])

            errors = inspect_bundle(app, run=fake_run)
            self.assertTrue(any("requires macOS 26.0" in error for error in errors))
            self.assertTrue(any("/opt/homebrew/" in error for error in errors))

    def test_rejects_wrong_architecture_and_unreadable_minimum_version(self):
        with tempfile.TemporaryDirectory() as directory:
            app = Path(directory) / "Example.app"
            app.mkdir()
            (app / "wrong_arch").touch()
            (app / "unknown_version").touch()

            def fake_run(command, **_kwargs):
                path = command[-1]
                if command[0] == "file":
                    value = "Mach-O 64-bit executable"
                elif command[0] == "lipo":
                    value = "x86_64" if path.endswith("wrong_arch") else "arm64"
                elif command[1] == "-l":
                    value = "cmd LC_SEGMENT_64\n"
                else:
                    value = "example:\n"
                return SimpleNamespace(stdout=value)

            errors = inspect_bundle(app, run=fake_run)
            self.assertTrue(any("arm64 architecture missing" in error for error in errors))
            self.assertTrue(any("minimum macOS version unavailable" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
