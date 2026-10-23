import tempfile
import unittest
from pathlib import Path

from prepare_macos_build_version import prepare_version


class BuildVersionTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "VERSION"

    def test_local_build_increments_and_saves_patch(self):
        self.path.write_text("1.2.9\n")
        self.assertEqual(prepare_version(self.path), "1.2.10")
        self.assertEqual(self.path.read_text(), "1.2.10\n")

    def test_repeated_ci_builds_preserve_version_file_exactly(self):
        original = b"0.1.0\n"
        self.path.write_bytes(original)
        for _ in range(2):
            self.assertEqual(prepare_version(self.path, preserve=True), "0.1.0")
            self.assertEqual(self.path.read_bytes(), original)

    def test_invalid_version_never_changes_file(self):
        for value in ("", "1.2", "v1.2.3", "1.2.-3", "01.2.3", "1.2.3-beta"):
            for preserve in (False, True):
                with self.subTest(value=value, preserve=preserve):
                    self.path.write_text(value)
                    with self.assertRaises(ValueError):
                        prepare_version(self.path, preserve=preserve)
                    self.assertEqual(self.path.read_text(), value)
