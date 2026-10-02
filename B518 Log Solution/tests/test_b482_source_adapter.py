import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from log_monitoring import BtLogMonitor
from monitoring_round import RoundCoordinator


class B482SourceAdapterRoundTests(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.temp)

    def start_round(self, testdata, caseinfo=None, monotonic=None):
        now = datetime(2026, 8, 21, 15, 20, 0)
        clock = monotonic or (lambda: 0.0)
        rounds = RoundCoordinator()
        rounds.start(
            "BT",
            lambda on_event: BtLogMonitor(
                testdata, (1, 2, 3, 4), caseinfo_root=caseinfo,
                callback=on_event, now=lambda: now, monotonic=clock,
                session_root=self.temp / "sessions",
            ),
            run_async=False,
        )
        return rounds

    def test_round_event_exposes_caseinfo_source_time_and_second_snread_action(self):
        testdata, caseinfo = self.temp / "TestData", self.temp / "CaseInfo"
        caseinfo.mkdir()
        path = caseinfo / "thread1CaseInfo_2026-08-22.txt"
        rounds = self.start_round(testdata, caseinfo)
        path.write_text(
            "2026-08-21 15:19:54:160, 4,InitResource,SNRead,--,SNRead,"
            "HK5HVH6ZSB300003YV,NA,NA,NA,Passed,9.50\r\n"
            "2026-08-21 15:19:55:592, 5,TestFlow,SNRead,--,CBRead,"
            "WRONGSERIAL123,NA,NA,NA,Passed,0.00\r\n",
            encoding="utf-8",
        )

        rounds.poll_once()
        snapshot = rounds.snapshot()

        self.assertEqual(snapshot.results[0].status, "TESTING")
        self.assertEqual(snapshot.results[0].sn, "HK5HVH6ZSB300003YV")
        event = next(item.event for item in snapshot.events if item.event.kind == "result")
        self.assertEqual(event.detail["source_id"], path.name)
        self.assertEqual(event.detail["source_time"], "2026-08-21 15:19:54.160")
        self.assertEqual(event.detail["batch_evidence"], "caseinfo_date=2026-08-22;thread=1")

    def test_round_waits_for_partial_caseinfo_record_then_reports_activity(self):
        testdata, caseinfo = self.temp / "TestData", self.temp / "CaseInfo"
        caseinfo.mkdir()
        path = caseinfo / "thread1CaseInfo_2026-08-22.txt"
        prefix = "2026-08-21 15:19:54:160, 4,InitResource,SNRead,--,SNRead,HK5HVH6ZF4U00003YV"
        rounds = self.start_round(testdata, caseinfo)
        path.write_text(prefix, encoding="utf-8")

        rounds.poll_once()
        self.assertEqual(rounds.snapshot().results[0].status, "WAITING")

        path.write_text(prefix + ",NA,NA,NA,Passed,11.94\r\n", encoding="utf-8")
        rounds.poll_once()

        self.assertEqual(rounds.snapshot().results[0].status, "TESTING")
        self.assertEqual(rounds.snapshot().results[0].sn, "HK5HVH6ZF4U00003YV")

    def test_empty_sn_failed_testdata_result_keeps_notest_and_batch_evidence(self):
        testdata = self.temp / "TestData"
        result = testdata / "2026-08-21" / "FAILED" / "[Thread0][cfg][][FAILED][20260821151940].csv"
        testdata.mkdir()
        clock = [0.0]
        rounds = self.start_round(testdata, monotonic=lambda: clock[0])
        result.parent.mkdir(parents=True)
        result.write_text(
            "SerialNumber,Unit Number,Test Pass/Fail Status,StartTime,EndTime\n"
            ",0,FAILED,start,end\n",
            encoding="utf-8",
        )

        rounds.poll_once()
        clock[0] = 5.1
        rounds.poll_once()
        snapshot = rounds.snapshot()

        self.assertEqual(snapshot.results[0].status, "NOTEST")
        event = next(item.event for item in snapshot.events if item.event.kind == "result")
        self.assertEqual(event.detail["source_id"], "2026-08-21/FAILED/" + result.name)
        self.assertEqual(event.detail["source_time"], "2026-08-21 15:19:40")
        self.assertEqual(event.detail["batch_id"], "20260821151940")
        self.assertEqual(event.detail["batch_evidence"], "thread=0;config=cfg")

    def test_testdata_threads_keep_their_established_round_positions(self):
        testdata = self.temp / "TestData"
        testdata.mkdir()
        clock = [0.0]
        rounds = self.start_round(testdata, monotonic=lambda: clock[0])
        samples = (
            (0, "PASSED", "SAMPLE00000001"),
            (1, "FAILED", "SAMPLE00000002"),
            (2, "FAILED", ""),
            (3, "PASSED", "SAMPLE00000004"),
        )
        for thread, folder_status, sn in samples:
            name = "[Thread{}][cfg][{}][{}][20260821151940].csv".format(
                thread, sn, folder_status,
            )
            path = testdata / "2026-08-21" / folder_status / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                "SerialNumber,Unit Number,Test Pass/Fail Status,StartTime,EndTime\n"
                "{},{},{},start,end\n".format(sn, thread, folder_status),
                encoding="utf-8",
            )

        rounds.poll_once()
        clock[0] = 5.1
        rounds.poll_once()

        results = rounds.snapshot().results
        self.assertEqual([(item.slot, item.sn, item.status) for item in results], [
            (1, "SAMPLE00000001", "PASS"),
            (2, "SAMPLE00000002", "FAIL"),
            (3, "", "NOTEST"),
            (4, "SAMPLE00000004", "PASS"),
        ])

    def test_testdata_present_at_round_start_is_not_used_as_this_round_result(self):
        testdata = self.temp / "TestData"
        result = testdata / "2026-08-21" / "PASSED" / (
            "[Thread0][cfg][HK5HVH6ZSB300003YV][PASSED][20260821151940].csv"
        )
        result.parent.mkdir(parents=True)
        result.write_text(
            "SerialNumber,Unit Number,Test Pass/Fail Status,StartTime,EndTime\n"
            "HK5HVH6ZSB300003YV,0,PASSED,start,end\n",
            encoding="utf-8",
        )
        rounds = self.start_round(testdata)

        rounds.poll_once()

        self.assertEqual(rounds.snapshot().results[0].status, "WAITING")

    def test_caseinfo_content_present_at_round_start_is_ignored_until_new_line_is_appended(self):
        testdata, caseinfo = self.temp / "TestData", self.temp / "CaseInfo"
        caseinfo.mkdir()
        path = caseinfo / "thread1CaseInfo_2026-08-22.txt"
        path.write_text(
            "2026-08-21 15:19:54:160, 4,InitResource,SNRead,--,SNRead,"
            "HISTORICALSN0001,NA,NA,NA,Passed,9.50\r\n",
            encoding="utf-8",
        )
        rounds = self.start_round(testdata, caseinfo)

        rounds.poll_once()
        self.assertEqual(rounds.snapshot().results[0].status, "WAITING")

        with path.open("a", encoding="utf-8") as handle:
            handle.write(
                "2026-08-21 15:19:55:160, 5,TestFlow,SNRead,--,SNRead,"
                "HK5HVH6ZF4U00003YV,NA,NA,NA,Passed,9.50\r\n"
            )
        rounds.poll_once()

        result = rounds.snapshot().results[0]
        self.assertEqual(result.status, "TESTING")
        self.assertEqual(result.sn, "HK5HVH6ZF4U00003YV")


if __name__ == "__main__":
    unittest.main()
