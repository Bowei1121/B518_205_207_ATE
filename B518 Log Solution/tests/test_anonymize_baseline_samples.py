import tempfile
import unittest
from pathlib import Path

from anonymize_baseline_samples import _atlas_related_identifiers, _replace_identifiers, build_samples


class AnonymizedSamplePreparationTests(unittest.TestCase):
    def test_identifier_redaction_is_case_insensitive(self):
        result = _replace_identifiers(b"serial=AbC123456; again ABC123456", {"abc123456": "SAMPLESERIAL0001"})

        self.assertEqual(result, b"serial=SAMPLESERIAL0001; again SAMPLESERIAL0001")

    def test_atlas_instrument_serials_and_fixture_ids_are_collected(self):
        with tempfile.TemporaryDirectory() as temporary:
            sample = Path(temporary) / "records.csv"
            sample.write_text(
                "FixtureID,CYG-F011041-S02\n"
                "Xavier-001-006A/7A,GQQ33040482LTJT5Z\n"
                ",,,CreateAttr Xavier-001-006A7A,,,,,,,,,,,,\n"
                "DMM-002,H4G3362001HQ17812\n",
                encoding="utf-8",
            )

            self.assertEqual(
                _atlas_related_identifiers(sample),
                {
                    "CYG-F011041-S02",
                    "Xavier-001-006A/7A",
                    "Xavier-001-006A7A",
                    "GQQ33040482LTJT5Z",
                    "DMM-002",
                    "H4G3362001HQ17812",
                },
            )

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
