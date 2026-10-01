import csv
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


if __name__ == "__main__":
    unittest.main()
