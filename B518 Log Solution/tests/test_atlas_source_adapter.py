import csv
import os
import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from log_monitoring import AtlasActiveArchiveMonitor
from monitoring_round import RoundCoordinator


def write_records(path, serial, status="PASS"):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["MLB_SN", "status"])
        writer.writeheader()
        writer.writerow({"MLB_SN": serial, "status": status})


class AtlasSourceAdapterRoundTests(unittest.TestCase):
    def start_round(self, root, active, final):
        rounds = RoundCoordinator()
        rounds.start(
            "FCT",
            lambda callback: AtlasActiveArchiveMonitor(
                "FCT", active, final, (1,), callback=callback,
                now=lambda: datetime(2026, 9, 10, 10, 0, 0), session_root=root / "sessions",
            ),
            run_async=False,
        )
        return rounds

    def test_startup_snapshot_ignores_old_active_data_and_reports_source_prepared(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            active = root / "active"
            final = root / "unit-archive"
            write_records(active / "group0-slot1" / "system" / "records.csv", "SAMPLE123456")
            rounds = RoundCoordinator()
            rounds.start(
                "FCT",
                lambda callback: AtlasActiveArchiveMonitor(
                    "FCT", active, final, (1,), callback=callback,
                    now=lambda: datetime(2026, 9, 10, 10, 0, 0), session_root=root / "sessions",
                ),
                run_async=False,
            )

            rounds.monitor.poll_once()
            snapshot = rounds.snapshot()

            self.assertEqual(snapshot.results[0].status, "WAITING")
            self.assertIn("source_prepared", [event.event.kind for event in snapshot.events])

    def test_archive_result_is_used_only_after_its_file_signature_is_stable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            active = root / "active"
            final = root / "unit-archive"
            rounds = RoundCoordinator()
            rounds.start(
                "FCT",
                lambda callback: AtlasActiveArchiveMonitor(
                    "FCT", active, final, (1,), callback=callback,
                    now=lambda: datetime(2026, 9, 10, 10, 0, 0), session_root=root / "sessions",
                ),
                run_async=False,
            )
            rounds.monitor.poll_once()
            write_records(active / "group0-slot1" / "system" / "records.csv", "SAMPLE123456")
            rounds.monitor.poll_once()
            shutil.rmtree(active / "group0-slot1")
            rounds.monitor.poll_once()
            archive = final / "SAMPLE123456" / "20260910_10-00-01.000-run" / "system" / "records.csv"
            write_records(archive, "SAMPLE123456", "PASS")

            rounds.monitor.poll_once()
            first_observation = rounds.snapshot()

            self.assertEqual(first_observation.results[0].status, "COMPLETING")
            self.assertFalse(any(event.event.kind == "final" for event in first_observation.events))

            rounds.monitor.poll_once()
            stable_observation = rounds.snapshot()
            rounds.monitor.poll_once()

            self.assertEqual(stable_observation.results[0].status, "PASS")
            self.assertEqual(
                sum(event.event.kind == "final" for event in rounds.events_since()),
                1,
            )
            write_records(active / "group0-slot1" / "system" / "records.csv", "LATER987654", "FAIL")
            rounds.monitor.poll_once()
            after_later_progress = rounds.snapshot()

            self.assertEqual(after_later_progress.results[0].status, "PASS")
            self.assertEqual(after_later_progress.results[0].sn, "SAMPLE123456")
            self.assertEqual(
                sum(event.event.kind == "final" for event in after_later_progress.events),
                1,
            )

    def test_unchanged_record_in_existing_active_directory_is_still_active(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            active, final = root / "active", root / "unit-archive"
            system = active / "group0-slot1" / "system"
            older_record = system / "records.csv"
            selected_record = system / "record.csv"
            write_records(older_record, "NUMBER_SOF0", "PASS")
            write_records(selected_record, "NUMBER_SOF0", "PASS")
            selected_mtime = selected_record.stat().st_mtime_ns
            rounds = self.start_round(root, active, final)
            rounds.monitor.poll_once()
            write_records(older_record, "SAMPLE123456", "FAIL")
            rounds.monitor.poll_once()

            os.utime(older_record, ns=(selected_mtime - 1_000_000_000, selected_mtime - 1_000_000_000))
            rounds.monitor.poll_once()
            snapshot = rounds.snapshot()

            self.assertEqual(snapshot.results[0].status, "TESTING")
            self.assertFalse(any(event.event.kind == "completing" for event in snapshot.events))

    def test_first_trusted_identity_is_locked_and_invalid_value_is_not_exposed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            active, final = root / "active", root / "unit-archive"
            rounds = self.start_round(root, active, final)
            rounds.monitor.poll_once()
            record = active / "group0-slot1" / "system" / "records.csv"

            write_records(record, "NUMBER_SOF0")
            rounds.monitor.poll_once()
            self.assertEqual(rounds.snapshot().results[0].sn, "")
            self.assertFalse(any(event.event.kind == "sn_locked" for event in rounds.events_since()))

            write_records(record, "SAMPLE123456")
            rounds.monitor.poll_once()
            write_records(record, "LATER987654")
            rounds.monitor.poll_once()

            snapshot = rounds.snapshot()
            self.assertEqual(snapshot.results[0].sn, "SAMPLE123456")
            self.assertEqual(snapshot.results[0].status, "TESTING")
            self.assertEqual(sum(event.event.kind == "sn_locked" for event in snapshot.events), 1)

    def test_unreadable_identity_keeps_the_atlas_sn_failure_result(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            active, final = root / "active", root / "unit-archive"
            rounds = self.start_round(root, active, final)
            rounds.monitor.poll_once()
            write_records(active / "group0-slot1" / "system" / "records.csv", "NUMBER_SOF0")
            rounds.monitor.poll_once()
            shutil.rmtree(active / "group0-slot1")

            snapshot = rounds.monitor.poll_once()
            observed = rounds.snapshot()

            self.assertEqual(observed.results[0].status, "FAIL")
            self.assertEqual(observed.results[0].sn, "SN 讀取失敗")
            self.assertEqual(
                [event.event.kind for event in observed.events].count("result"),
                2,
            )


if __name__ == "__main__":
    unittest.main()
