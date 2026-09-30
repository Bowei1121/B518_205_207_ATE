import tempfile
import unittest
from pathlib import Path

from replay_baseline_samples import ReplayError, find_rswmt_run, replay_b482_caseinfo


class BaselineSampleSelectionTests(unittest.TestCase):
    def test_multiple_rswmt_runs_require_explicit_selection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ("run-a", "run-b"):
                run = root / name
                run.mkdir()
                (run / "slot.csv").write_text("sample", encoding="utf-8")

            with self.assertRaisesRegex(ReplayError, "Multiple RS-WMT runs"):
                find_rswmt_run(root)
            self.assertEqual(find_rswmt_run(root, "run-b").name, "run-b")

    def test_single_rswmt_run_is_selected_without_a_selector(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary) / "only-run"
            run.mkdir()
            (run / "slot.csv").write_text("sample", encoding="utf-8")

            self.assertEqual(find_rswmt_run(temporary).name, "only-run")

    def test_multiple_caseinfo_days_require_explicit_selection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for day in ("2026-08-21", "2026-08-22"):
                for thread in range(1, 5):
                    (root / "thread{}CaseInfo_{}.txt".format(thread, day)).write_text(
                        "", encoding="utf-8"
                    )

            with self.assertRaisesRegex(ReplayError, "Multiple complete B482 CaseInfo dates"):
                replay_b482_caseinfo(root)
            with self.assertRaisesRegex(ReplayError, "requested B482 CaseInfo date"):
                replay_b482_caseinfo(root, "2026-08-23")


if __name__ == "__main__":
    unittest.main()
