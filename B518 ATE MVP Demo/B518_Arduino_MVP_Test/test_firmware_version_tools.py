import sys
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from bump_firmware_version import bump_version
from verify_firmware_version import legal_transition, parse_version


VERSION_SOURCE = '#define B518_FIRMWARE_VERSION "1.2.3"\n'


class FirmwareVersionToolTests(unittest.TestCase):
    def test_bump_hotfix_feature_and_major(self):
        updated, version = bump_version(VERSION_SOURCE, "hotfix")
        self.assertEqual(version, "1.2.4")
        self.assertIn('"1.2.4"', updated)
        _, version = bump_version(VERSION_SOURCE, "feature")
        self.assertEqual(version, "1.3.0")
        _, version = bump_version(VERSION_SOURCE, "major")
        self.assertEqual(version, "2.0.0")

    def test_bump_rejects_missing_or_invalid_level(self):
        with self.assertRaises(RuntimeError):
            bump_version("#define OTHER_VERSION \"1.2.3\"\n", "hotfix")
        with self.assertRaises(ValueError):
            bump_version(VERSION_SOURCE, "invalid")

    def test_parse_version_and_legal_transitions(self):
        self.assertEqual(parse_version(VERSION_SOURCE), (1, 2, 3))
        with self.assertRaises(ValueError):
            parse_version('#define B518_FIRMWARE_VERSION "1.2"\n')
        self.assertTrue(legal_transition((1, 2, 3), (1, 2, 4)))
        self.assertTrue(legal_transition((1, 2, 3), (1, 3, 0)))
        self.assertTrue(legal_transition((1, 2, 3), (2, 0, 0)))
        self.assertFalse(legal_transition((1, 2, 3), (1, 2, 5)))
        self.assertFalse(legal_transition((1, 2, 3), (1, 3, 1)))
        self.assertFalse(legal_transition((1, 2, 3), (0, 9, 9)))


if __name__ == "__main__":
    unittest.main()
