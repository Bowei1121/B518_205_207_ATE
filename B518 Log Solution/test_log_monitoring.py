import csv
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from log_monitoring import (
    AtlasActiveArchiveMonitor,
    BtLogMonitor,
    parse_archive_timestamp,
)


def write_records(path, sn="", status="PASS"):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["MLB_SN", "status"])
        writer.writeheader()
        writer.writerow({"MLB_SN": sn, "status": status})


def write_bt(path, sn, status, unit):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "SerialNumber", "Unit Number", "Test Pass/Fail Status", "StartTime", "EndTime",
        ])
        writer.writeheader()
        writer.writerow({"SerialNumber": sn, "Unit Number": unit,
                         "Test Pass/Fail Status": status, "StartTime": "x", "EndTime": "y"})


class LogMonitoringTests(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp())
        self.now = datetime(2022, 6, 18, 2, 29, 0)

    def tearDown(self):
        shutil.rmtree(self.temp)

    def test_archive_timestamp_accepts_one_and_two_digit_hour(self):
        self.assertEqual(parse_archive_timestamp("20220618_2-28-01.374-04426F"), datetime(2022, 6, 18, 2, 28, 1, 374000))
        self.assertEqual(parse_archive_timestamp("20220618_02-28-01.374-any"), datetime(2022, 6, 18, 2, 28, 1, 374000))

    def test_fct_latches_active_sn_then_reads_unit_archive(self):
        active, final = self.temp / "active", self.temp / "unit-archive"
        monitor = AtlasActiveArchiveMonitor("FCT", active, final, (1,), now=lambda: self.now, session_root=self.temp / "sessions")
        write_records(active / "group0-slot1" / "system" / "records.csv", "HK5HUX6STQ800003YV")
        monitor.poll_once()
        self.assertEqual(monitor.results[1].sn, "HK5HUX6STQ800003YV")
        self.assertEqual(monitor.results[1].status, "TESTING")
        shutil.rmtree(active / "group0-slot1")
        write_records(final / "HK5HUX6STQ800003YV" / "20220618_2-29-01.374-X" / "system" / "records.csv", "HK5HUX6STQ800003YV", "FAIL")
        monitor.poll_once()
        self.assertEqual(monitor.results[1].sn, "HK5HUX6STQ800003YV")
        self.assertEqual(monitor.results[1].status, "FAIL")

    def test_fct_never_treats_number_sofo_as_serial_number(self):
        active, final = self.temp / "active", self.temp / "unit-archive"
        monitor = AtlasActiveArchiveMonitor("FCT", active, final, (1,), now=lambda: self.now, session_root=self.temp / "sessions")
        write_records(active / "group0-slot1" / "system" / "records.csv", "NUMBER_SOF0")
        monitor.poll_once()
        shutil.rmtree(active / "group0-slot1")
        monitor.poll_once()
        self.assertEqual(monitor.results[1].sn, "SN 讀取失敗")
        self.assertEqual(monitor.results[1].status, "FAIL")

    def test_active_csv_from_before_monitor_start_is_ignored_until_changed(self):
        active, final = self.temp / "active", self.temp / "unit-archive"
        old = active / "group0-slot1" / "system" / "records.csv"
        write_records(old, "HK5HUX6STQ800003YV")
        monitor = AtlasActiveArchiveMonitor("FCT", active, final, (1,), now=lambda: self.now, session_root=self.temp / "sessions")
        monitor.poll_once()
        self.assertEqual(monitor.results[1].status, "WAITING")
        write_records(old, "HK5HUX6STQ800003YV", "FAIL")
        monitor.poll_once()
        self.assertEqual(monitor.results[1].status, "TESTING")

    def test_bt_locks_batch_and_empty_failed_csv_is_notest(self):
        clock = [0.0]
        root = self.temp / "TestData"
        monitor = BtLogMonitor(root, (1,), now=lambda: self.now, monotonic=lambda: clock[0], session_root=self.temp / "sessions")
        filename = "[Thread0][cfg][][FAILED][20220618022901].csv"
        write_bt(root / "2022-06-18" / "FAILED" / filename, "", "FAILED", "0")
        monitor.poll_once()
        clock[0] = 5.1
        monitor.poll_once()
        self.assertEqual(monitor.batch_stamp, "20220618022901")
        self.assertEqual(monitor.results[1].status, "NOTEST")

    def test_bt_batch_conflict_requires_and_applies_review(self):
        clock = [0.0]
        root = self.temp / "TestData"
        monitor = BtLogMonitor(root, (1,), now=lambda: self.now, monotonic=lambda: clock[0], session_root=self.temp / "sessions")
        first = root / "2022-06-18" / "PASSED" / "[Thread0][cfg][HK5HUX6STQ800003YV][PASSED][20220618022901].csv"
        second = root / "2022-06-18" / "PASSED" / "[Thread0][cfg][HK5HUX6STQ900003YV][PASSED][20220618023001].csv"
        write_bt(first, "HK5HUX6STQ800003YV", "PASSED", "0")
        monitor.poll_once(); clock[0] = 5.1; monitor.poll_once()
        write_bt(second, "HK5HUX6STQ900003YV", "PASSED", "0")
        clock[0] = 6.0; monitor.poll_once(); clock[0] = 11.1; monitor.poll_once()
        self.assertIsNotNone(monitor.review_pending)
        monitor.resolve_review("accept")
        monitor.poll_once()
        self.assertEqual(monitor.batch_stamp, "20220618023001")

    def test_bt_caseinfo_reports_testing_before_final_csv(self):
        root, caseinfo = self.temp / "TestData", self.temp / "CaseInfo"
        monitor = BtLogMonitor(root, (1,), caseinfo_root=caseinfo,
                               now=lambda: self.now, session_root=self.temp / "sessions")
        path = caseinfo / "thread1CaseInfo_2022-06-18.txt"
        path.parent.mkdir(parents=True)
        path.write_text(
            "2022/6/18 2:29:01 SNRead: HK5HUX6STQ800003YV\\n"
            "2022/6/18 2:29:02 Running RF test\\n",
            encoding="utf-8",
        )
        monitor.poll_once()
        self.assertEqual(monitor.results[1].sn, "HK5HUX6STQ800003YV")
        self.assertEqual(monitor.results[1].status, "TESTING")

    def test_log_solution_never_imports_control_dependencies(self):
        base = Path(__file__).parent
        content = (base / "log_monitoring.py").read_text() + (base / "b518_log_solution.py").read_text()
        for forbidden in ("import serial", "import cv2", "import socket", "Arduino", "SCREENSHOT"):
            self.assertNotIn(forbidden, content)


if __name__ == "__main__":
    unittest.main()
