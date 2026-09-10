import csv
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from log_monitoring import (
    AtlasActiveArchiveMonitor,
    BaseMonitor,
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


class TimeoutMonitor(BaseMonitor):
    """Minimal monitor that exercises BaseMonitor timeout handling."""
    def poll_once(self):
        self.check_timeouts()


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

    def test_active_batch_marks_unseen_slots_notest_only_after_active_is_gone(self):
        active, final = self.temp / "active", self.temp / "unitest"
        monitor = AtlasActiveArchiveMonitor("DFU", active, final, (1, 2), now=lambda: self.now, session_root=self.temp / "sessions")
        write_records(active / "group0-slot1" / "system" / "records.csv", "HK5HUX6STQ800003YV", "PASS")
        monitor.poll_once()
        self.assertEqual(monitor.results[2].status, "WAITING")
        (active / "group0-slot1").rename(active / "completed-slot1")
        monitor.poll_once()
        self.now += timedelta(seconds=3)
        monitor.poll_once()
        self.assertEqual(monitor.results[2].status, "NOTEST")

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

    def test_bt_caseinfo_parses_production_csv_records_for_all_threads(self):
        root, caseinfo = self.temp / "TestData", self.temp / "CaseInfo"
        monitor = BtLogMonitor(root, (1, 2, 3, 4), caseinfo_root=caseinfo,
                               now=lambda: datetime(2026, 8, 21, 15, 19, 0),
                               session_root=self.temp / "sessions")
        serials = {
            1: "HK5HVH6ZF4U00003YV", 2: "HK5HVH6ZSAT00003YV",
            3: "HK5HVH6YXFJ00003YV", 4: "HK5HVH6ZSB300003YV",
        }
        caseinfo.mkdir()
        for slot, sn in serials.items():
            (caseinfo / "thread{}CaseInfo_2026-08-22.txt".format(slot)).write_text(
                "2026-08-21 15:19:01:049, 1,InitResource,OpenFixture,--,OpenFixture,,NA,NA,NA,,\r"
                "2026-08-21 15:19:24:160, 4,InitResource,SNRead,--,SNRead,{},NA,NA,NA,Passed,11.94\r"
                "2026-08-21 15:19:25:592, 8,InitResource,ConnectDUT,--,ConnectDUT,,NA,NA,NA,Passed,1.43\r\n".format(sn),
                encoding="utf-8",
            )
        monitor.poll_once()
        for slot, sn in serials.items():
            self.assertEqual(monitor.results[slot].status, "TESTING")
            self.assertEqual(monitor.results[slot].sn, sn)

    def test_bt_caseinfo_uses_second_snread_action_to_identify_barcode(self):
        root, caseinfo = self.temp / "TestData", self.temp / "CaseInfo"
        monitor = BtLogMonitor(root, (1,), caseinfo_root=caseinfo,
                               now=lambda: datetime(2026, 9, 10, 10, 0, 0),
                               session_root=self.temp / "sessions")
        path = caseinfo / "thread1CaseInfo_2026-09-10.txt"
        path.parent.mkdir()
        path.write_text(
            "2026-09-10 10:00:00:000, 4,InitResource,SNRead,--,SNRead,HK5HVH6ZSB300003YV,NA,NA,NA,Passed,9.50\r"
            "2026-09-10 10:00:01:000, 5,TestFlow,SNRead,--,CBRead,HK5HVH6ZWRONG003YV,NA,NA,NA,Passed,0.00\r"
            "2026-09-10 10:00:02:000, 6,TestFlow,CBRead,--,CBRead,2,NA,NA,NA,Passed,0.00\r\n",
            encoding="utf-8",
        )
        monitor.poll_once()
        self.assertEqual(monitor.results[1].status, "TESTING")
        self.assertEqual(monitor.results[1].sn, "HK5HVH6ZSB300003YV")

    def test_bt_caseinfo_buffers_partial_production_record(self):
        root, caseinfo = self.temp / "TestData", self.temp / "CaseInfo"
        monitor = BtLogMonitor(root, (1,), caseinfo_root=caseinfo,
                               now=lambda: datetime(2026, 8, 21, 15, 19, 0),
                               session_root=self.temp / "sessions")
        path = caseinfo / "thread1CaseInfo_2026-08-22.txt"
        path.parent.mkdir()
        path.write_text("2026-08-21 15:19:24:160, 4,InitResource,SNRead,--,SNRead,HK5HVH6ZF4U00003YV", encoding="utf-8")
        monitor.poll_once()
        self.assertEqual(monitor.results[1].status, "WAITING")
        path.write_text(path.read_text(encoding="utf-8") + ",NA,NA,NA,Passed,11.94\r\n"
                        "2026-08-21 15:19:25:592, 8,InitResource,ConnectDUT,--,ConnectDUT,,NA,NA,NA,Passed,1.43\r\n", encoding="utf-8")
        monitor.poll_once()
        self.assertEqual(monitor.results[1].status, "TESTING")
        self.assertEqual(monitor.results[1].sn, "HK5HVH6ZF4U00003YV")

    def test_bt_caseinfo_ignores_invalid_and_expired_production_sn(self):
        root, caseinfo = self.temp / "TestData", self.temp / "CaseInfo"
        monitor = BtLogMonitor(root, (1,), caseinfo_root=caseinfo,
                               now=lambda: datetime(2026, 8, 21, 15, 19, 0),
                               session_root=self.temp / "sessions")
        path = caseinfo / "thread1CaseInfo_2026-08-22.txt"
        path.parent.mkdir()
        path.write_text(
            "2026-08-21 15:18:00:000, 4,InitResource,SNRead,--,SNRead,EXPIRED123,NA,NA,NA,Passed,1\r"
            "2026-08-21 15:19:24:160, 4,InitResource,SNRead,--,SNRead,NUMBER_SOF0,NA,NA,NA,Passed,1\r"
            "2026-08-21 15:19:25:160, 8,InitResource,ConnectDUT,--,ConnectDUT,,NA,NA,NA,Passed,1\r\n",
            encoding="utf-8",
        )
        monitor.poll_once()
        self.assertEqual(monitor.results[1].status, "TESTING")
        self.assertEqual(monitor.results[1].sn, "")

    def test_bt_caseinfo_production_closefixture_reports_completing(self):
        root, caseinfo = self.temp / "TestData", self.temp / "CaseInfo"
        monitor = BtLogMonitor(root, (1,), caseinfo_root=caseinfo,
                               now=lambda: datetime(2026, 8, 21, 15, 19, 0),
                               session_root=self.temp / "sessions")
        path = caseinfo / "thread1CaseInfo_2026-08-22.txt"
        path.parent.mkdir()
        path.write_text(
            "2026-08-21 15:19:24:160, 4,InitResource,SNRead,--,SNRead,HK5HVH6ZF4U00003YV,NA,NA,NA,Passed,1\r"
            "2026-08-21 15:19:25:160, 5,UnInitResource,CloseFixture,--,CloseFixture,,NA,NA,NA,Passed,1\r\n",
            encoding="utf-8",
        )
        monitor.poll_once()
        self.assertEqual(monitor.results[1].status, "COMPLETING")
        self.assertEqual(monitor.results[1].sn, "HK5HVH6ZF4U00003YV")

    def test_station_timeout_defaults_match_the_operating_limits(self):
        clock = [0.0]
        monitor = TimeoutMonitor("BT", {}, (1,), now=lambda: self.now,
                                 monotonic=lambda: clock[0], session_root=self.temp / "sessions")
        self.assertEqual(monitor.start_timeout_seconds, 30)
        self.assertEqual(monitor.test_timeout_seconds, 240)

    def test_start_timeout_marks_all_slots_and_stops_monitoring(self):
        clock, events = [0.0], []
        monitor = TimeoutMonitor("FCT", {}, (1, 2), now=lambda: self.now,
                                 monotonic=lambda: clock[0], start_timeout_seconds=30,
                                 test_timeout_seconds=480, callback=events.append,
                                 session_root=self.temp / "sessions")
        clock[0] = 29.9
        monitor.poll_once()
        self.assertFalse(monitor.finished)
        clock[0] = 30.0
        monitor.poll_once()
        self.assertTrue(monitor.finished)
        self.assertEqual([monitor.results[slot].status for slot in (1, 2)], ["TIMEOUT", "TIMEOUT"])
        self.assertEqual(events[-1].kind, "timeout")
        self.assertIn("未進入測試", events[-1].message)

    def test_test_timeout_marks_only_the_slots_that_exceeded_their_limit(self):
        clock, events = [0.0], []
        monitor = TimeoutMonitor("DFU", {}, (1, 2, 3), now=lambda: self.now,
                                 monotonic=lambda: clock[0], start_timeout_seconds=30,
                                 test_timeout_seconds=10, callback=events.append,
                                 session_root=self.temp / "sessions")
        monitor.set_result(1, "PASS", "DONE")
        monitor.set_result(2, "TESTING", "RUNNING")
        monitor.set_result(3, "TESTING", "ALSO_RUNNING")
        clock[0] = 10.0
        monitor.poll_once()
        self.assertEqual(monitor.results[1].status, "PASS")
        self.assertEqual(monitor.results[2].status, "TIMEOUT")
        self.assertEqual(monitor.results[3].status, "TIMEOUT")
        self.assertFalse(monitor.finished)
        self.assertEqual([event.slot for event in events if event.kind == "timeout"], [2, 3])

    def test_test_updates_and_completing_do_not_reset_the_timeout_clock(self):
        clock = [0.0]
        monitor = TimeoutMonitor("FCT", {}, (1,), now=lambda: self.now,
                                 monotonic=lambda: clock[0], start_timeout_seconds=30,
                                 test_timeout_seconds=10, session_root=self.temp / "sessions")
        monitor.set_result(1, "TESTING")
        clock[0] = 9.0
        monitor.set_result(1, "TESTING")
        monitor.set_result(1, "COMPLETING")
        clock[0] = 10.0
        monitor.poll_once()
        self.assertEqual(monitor.results[1].status, "TIMEOUT")

    def test_final_result_at_the_timeout_boundary_wins_over_timeout(self):
        clock = [0.0]
        monitor = TimeoutMonitor("FCT", {}, (1,), now=lambda: self.now,
                                 monotonic=lambda: clock[0], start_timeout_seconds=30,
                                 test_timeout_seconds=10, session_root=self.temp / "sessions")
        monitor.set_result(1, "TESTING", "RUNNING")
        clock[0] = 10.0
        monitor.set_result(1, "PASS", "DONE")
        monitor.poll_once()
        self.assertEqual(monitor.results[1].status, "PASS")
        self.assertFalse(monitor.finished)

    def test_log_solution_never_imports_control_dependencies(self):
        base = Path(__file__).parent
        content = "".join((base / name).read_text() for name in (
            "log_monitoring.py", "b518_log_solution.py", "global_hotkey.py",
        ))
        for forbidden in ("import serial", "import cv2", "import socket", "Arduino", "SCREENSHOT"):
            self.assertNotIn(forbidden, content)


if __name__ == "__main__":
    unittest.main()
