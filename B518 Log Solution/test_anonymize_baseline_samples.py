import tempfile
import unittest
from pathlib import Path

from anonymize_baseline_samples import _replace_identifiers, build_samples


class AnonymizedSamplePreparationTests(unittest.TestCase):
    def test_identifier_redaction_is_case_insensitive(self):
        result = _replace_identifiers(b"serial=AbC123456; again ABC123456", {"abc123456": "SAMPLESERIAL0001"})

        self.assertEqual(result, b"serial=SAMPLESERIAL0001; again SAMPLESERIAL0001")

    def test_output_inside_source_tree_is_rejected_before_any_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            source_root = Path(temporary) / "source"
            source_root.mkdir()
            output_root = source_root / "generated"

            with self.assertRaisesRegex(ValueError, "outside the supplied source tree"):
                build_samples(source_root, output_root)

            self.assertFalse(output_root.exists())


if __name__ == "__main__":
    unittest.main()
