import csv
import json
import log_monitoring
import shutil
import tempfile
import threading
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from log_monitoring import AtlasActiveArchiveMonitor, BaseMonitor, BtLogMonitor, MonitorEvent, parse_archive_timestamp
from b482_source_adapter import B482SourceAdapter, B482ObservationKind
from language_catalog import make_bilingual_message


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
        self.sessions = []
        original_store = log_monitoring.SessionStore

        def track_session(*args, **kwargs):
            store = original_store(*args, **kwargs)
            self.sessions.append(store)
            return store

        self.session_store_patch = patch.object(
            log_monitoring, "SessionStore", side_effect=track_session)
        self.session_store_patch.start()

    def tearDown(self):
        for store in self.sessions:
            self.assertTrue(store.flush())
        self.session_store_patch.stop()
        shutil.rmtree(self.temp)

    def test_session_event_keeps_one_immutable_bilingual_record(self):
        store = log_monitoring.SessionStore("bilingual", {}, self.temp / "sessions")
        parameters = {"station": "FCT", "slot": 3, "status": "PASS"}
        message = make_bilingual_message("round.result", parameters)
        parameters["slot"] = 9

        store.enqueue_event("slot3 PASS", {"round_id": "round-1"}, message)
        self.assertTrue(store.flush())
        record = json.loads((store.path / "events.log").read_text(encoding="utf-8"))
        self.assertEqual(record["message"], "slot3 PASS")
        self.assertEqual(record["detail"], {"round_id": "round-1"})
        self.assertEqual(record["localized_message"]["parameters"]["slot"], 3)
        self.assertEqual(record["localized_message"]["en"], "FCT Slot 3 result: PASS")
        self.assertEqual(record["localized_message"]["zh-TW"], "FCT 通道 3 結果：PASS")

    def test_platform_message_is_captured_before_session_persistence(self):
        monitor = BaseMonitor("FCT", {}, [1], session_root=self.temp / "platform-events",
                              now=lambda: self.now)
        event = MonitorEvent(
            "warning", "legacy warning", source="/tmp/bad.jsonl",
            detail={"source_id": "bad.jsonl#1", "raw_error": "invalid token"},
            message_id="platform.sample_json.invalid_record",
            message_parameters={"source_filename": "bad.jsonl"},
            diagnostic="invalid token",
        )
        monitor.emit(event)
        self.assertTrue(monitor.session.flush())

        saved = json.loads((monitor.session.path / "events.log").read_text(encoding="utf-8"))
        localized = saved["localized_message"]
        self.assertEqual(localized["message_id"], "platform.sample_json.invalid_record")
        self.assertEqual(localized["en"], "Sample JSON source record is invalid: bad.jsonl")
        self.assertEqual(localized["zh-TW"], "Sample JSON 來源記錄無效：bad.jsonl")
        self.assertEqual(localized["diagnostic"], "invalid token")
        self.assertEqual(saved["detail"]["raw_error"], "invalid token")

    def test_atlas_and_b482_producers_capture_platform_message_ids(self):
        atlas_events = []
        atlas = AtlasActiveArchiveMonitor(
            "FCT", self.temp / "atlas-active", self.temp / "atlas-final", (1,),
            now=lambda: self.now, session_root=self.temp / "sessions", callback=atlas_events.append,
        )
        atlas.poll_once()
        self.assertEqual(atlas_events[0].localized_message.message_id,
                         "platform.atlas.source_prepared")

        clock = [0.0]
        source = self.temp / "b482"
        b482_events = []
        b482 = BtLogMonitor(
            source, (1,), now=lambda: self.now, monotonic=lambda: clock[0],
            session_root=self.temp / "sessions", callback=b482_events.append,
        )
        write_bt(source / "2022-06-18" / "PASSED" /
                 "[Thread0][cfg][HK5HUX6STQ800003YV][PASSED][20220618022901].csv",
                 "HK5HUX6STQ800003YV", "PASSED", "0")
        b482.poll_once()
        clock[0] = 5.1
        b482.poll_once()
        self.assertEqual(b482_events[0].localized_message.message_id, "platform.b482.batch")
        self.assertEqual(b482_events[0].localized_message.as_record()["parameters"]["batch_id"],
                         "20220618022901")

    def test_atlas_csv_read_failure_is_a_bilingual_app_event_with_raw_diagnostic(self):
        active, final = self.temp / "atlas-active-read-error", self.temp / "atlas-final-read-error"
        target = active / "group0-slot1" / "system" / "records.csv"
        target.parent.mkdir(parents=True)
        events = []
        monitor = AtlasActiveArchiveMonitor(
            "FCT", active, final, (1,), now=lambda: self.now,
            session_root=self.temp / "sessions", callback=events.append,
        )
        write_records(target, "HK5HUX6STQ800003YV")
        original_open = Path.open

        def fail_source_read(path, *args, **kwargs):
            if path == target and kwargs.get("mode", args[0] if args else "r") == "r":
                raise OSError("controlled source read failure")
            return original_open(path, *args, **kwargs)

        with patch.object(Path, "open", fail_source_read):
            monitor.poll_once()

        warning = next(event for event in events if event.kind == "warning")
        self.assertEqual(warning.localized_message.message_id, "platform.atlas.source_error")
        self.assertEqual(warning.localized_message.as_record()["parameters"]["source_filename"],
                         "records.csv")
        self.assertEqual(warning.detail["raw_diagnostic"], "controlled source read failure")

        b482_root = self.temp / "b482-read-error"
        b482_target = b482_root / "2022-06-18" / "PASSED" / (
            "[Thread0][cfg][HK5HUX6STQ800003YV][PASSED][20220618022901].csv")
        b482_target.parent.mkdir(parents=True)
        b482_events = []
        b482 = BtLogMonitor(
            b482_root, (1,), now=lambda: self.now, monotonic=lambda: 1,
            session_root=self.temp / "sessions", callback=b482_events.append,
        )
        write_bt(b482_target, "HK5HUX6STQ800003YV", "PASSED", "0")
        def fail_b482_read(path, *args, **kwargs):
            if path == b482_target and kwargs.get("mode", args[0] if args else "r") == "r":
                raise OSError("controlled source read failure")
            return original_open(path, *args, **kwargs)

        with patch.object(Path, "open", fail_b482_read):
            # The adapter reports a stable file's CSV read failure without
            # changing its existing candidate acceptance policy.
            b482.poll_once()
        warning = next(event for event in b482_events if event.kind == "warning")
        self.assertEqual(warning.localized_message.message_id, "platform.b482.source_error")
        self.assertEqual(warning.detail["raw_diagnostic"], "controlled source read failure")

    def test_legacy_session_adapter_keeps_its_existing_event_call_shape(self):
        monitor = BaseMonitor("FCT", {}, [1], session_root=self.temp / "legacy")
        captured = []
        published = []

        class LegacySession:
            def enqueue_event(self, message, detail=None):
                captured.append((message, detail))

        monitor.session = LegacySession()
        monitor.callback = published.append
        monitor.emit(MonitorEvent("source_prepared", "Source ready"))
        monitor.emit(MonitorEvent("round_started", "FCT round start accepted"))
        self.assertEqual(captured, [
            ("Source ready", {}), ("FCT round start accepted", {}),
        ])
        self.assertIsNotNone(published[1].localized_message)

    def test_session_adapter_with_keyword_extension_receives_identity_as_keywords(self):
        monitor = BaseMonitor("FCT", {}, [1], session_root=self.temp / "keyword-adapter",
                              now=lambda: self.now)
        captured = []

        class ExtensibleSession:
            def enqueue_event(self, message, detail=None, **kwargs):
                captured.append((message, detail, kwargs))

        monitor.session = ExtensibleSession()
        def assign_context(event):
            event.detail["round_id"] = "round-keyword"
            event.sequence = 1
            event.observed_at = self.now.isoformat(timespec="seconds")

        monitor.set_event_context_provider(assign_context)
        monitor.emit(MonitorEvent("result", "slot1 PASS", 1, status="PASS"))

        self.assertEqual(len(captured), 1)
        message, _detail, kwargs = captured[0]
        self.assertEqual(message, "slot1 PASS")
        self.assertEqual(kwargs["round_id"], "round-keyword")
        self.assertEqual(kwargs["sequence"], 1)
        self.assertEqual(kwargs["timestamp"], self.now.isoformat(timespec="seconds"))
        self.assertEqual(kwargs["localized_message"].message_id, "round.result")

    def test_archive_timestamp_accepts_one_and_two_digit_hour(self):
        self.assertEqual(parse_archive_timestamp("20220618_2-28-01.374-04426F"), datetime(2022, 6, 18, 2, 28, 1, 374000))
        self.assertEqual(parse_archive_timestamp("20220618_02-28-01.374-any"), datetime(2022, 6, 18, 2, 28, 1, 374000))

    def test_session_sync_failure_retains_original_event_for_nonblocking_retry(self):
        store = log_monitoring.SessionStore("recoverable", {}, self.temp / "sessions")
        original_event = store.event
        captured = []

        def fail_once(message, detail=None, timestamp=None):
            if not captured:
                captured.append(timestamp)
                raise OSError("temporary disk fault")
            return original_event(message, detail, timestamp)

        with patch.object(store, "event", side_effect=fail_once):
            with self.assertRaises(OSError):
                store.enqueue_event("keep original", {"source": "test"})
            store.enqueue_event("later event", {"source": "test"})
        self.assertFalse(store.flush())
        self.assertTrue(store.write_errors)

        with patch.object(store, "event", side_effect=original_event):
            self.assertTrue(store.retry())
            self.assertTrue(store.flush(timeout=2))
        records = [json.loads(line) for line in
                   (store.path / "events.log").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([record["message"] for record in records], ["keep original", "later event"])
        self.assertEqual(records[0]["detail"], {"source": "test"})
        self.assertEqual(records[0]["timestamp"], captured[0])
        self.assertFalse(store.write_errors)
        self.assertTrue(store.write_history)

    def test_session_retry_failure_keeps_original_ahead_of_later_retained_writes(self):
        store = log_monitoring.SessionStore("retry-order", {}, self.temp / "sessions")
        original_event = store.event
        initial_timestamp = []

        def fail_initial(message, detail=None, timestamp=None):
            if message == "first event":
                initial_timestamp.append(timestamp)
                raise OSError("first append failed")
            return original_event(message, detail, timestamp)

        with patch.object(store, "event", side_effect=fail_initial):
            with self.assertRaises(OSError):
                store.enqueue_event("first event", {"order": "first"})
            store.enqueue_event("second event", {"order": "second"})

        retry_attempts = []

        def fail_first_retry(message, detail=None, timestamp=None):
            if message == "first event" and not retry_attempts:
                retry_attempts.append(timestamp)
                raise OSError("retry still unavailable")
            return original_event(message, detail, timestamp)

        with patch.object(store, "event", side_effect=fail_first_retry):
            self.assertTrue(store.retry())
            self.assertFalse(store.flush(timeout=2))
            self.assertTrue(store.retry())
            self.assertTrue(store.flush(timeout=2))

        records = [json.loads(line) for line in
                   (store.path / "events.log").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([record["message"] for record in records],
                         ["first event", "second event"])
        self.assertEqual(records[0]["timestamp"], initial_timestamp[0])
        self.assertEqual(records[0]["detail"], {"order": "first"})
        self.assertEqual(records[1]["detail"], {"order": "second"})

    def test_session_flush_waits_for_writes_added_during_repeated_retry(self):
        store = log_monitoring.SessionStore("retry-pending", {}, self.temp / "sessions")
        original_event = store.event

        def fail_initial(message, detail=None, timestamp=None):
            if message == "first event":
                raise OSError("initial append failed")
            return original_event(message, detail, timestamp)

        with patch.object(store, "event", side_effect=fail_initial):
            with self.assertRaises(OSError):
                store.enqueue_event("first event")
            store.enqueue_event("second event")

        first_retry_entered = threading.Event()
        release_first_retry = threading.Event()

        def fail_first_retry(message, detail=None, timestamp=None):
            if message == "first event":
                first_retry_entered.set()
                release_first_retry.wait(2)
                raise OSError("retry append failed")
            return original_event(message, detail, timestamp)

        with patch.object(store, "event", side_effect=fail_first_retry):
            self.assertTrue(store.retry())
            self.assertTrue(first_retry_entered.wait(2))
            store.enqueue_event("third event")
            release_first_retry.set()
            self.assertFalse(store.flush(timeout=2))

        third_retry_entered = threading.Event()
        release_third_retry = threading.Event()

        def block_third_retry(message, detail=None, timestamp=None):
            if message == "third event":
                third_retry_entered.set()
                release_third_retry.wait(2)
            return original_event(message, detail, timestamp)

        with patch.object(store, "event", side_effect=block_third_retry):
            self.assertTrue(store.retry())
            self.assertTrue(third_retry_entered.wait(2))
            self.assertFalse(store.flush(timeout=0.05))
            release_third_retry.set()
            self.assertTrue(store.flush(timeout=2))

        records = [json.loads(line) for line in
                   (store.path / "events.log").read_text(encoding="utf-8").splitlines()]
        self.assertEqual([record["message"] for record in records],
                         ["first event", "second event", "third event"])

    def test_session_retry_from_failure_callback_keeps_a_worker_for_retained_write(self):
        failure_reported = threading.Event()
        retries = []
        store_holder = {}

        def retry_from_callback(_label, _error):
            retries.append(store_holder["store"].retry())
            failure_reported.set()

        store = log_monitoring.SessionStore(
            "retry-callback", {}, self.temp / "sessions", on_error=retry_from_callback,
            async_writes=True)
        store_holder["store"] = store
        original_event = store.event
        write_attempts = []

        def fail_once(message, detail=None, timestamp=None):
            write_attempts.append(message)
            if len(write_attempts) == 1:
                raise OSError("background append failed")
            return original_event(message, detail, timestamp)

        with patch.object(store, "event", side_effect=fail_once):
            store.enqueue_event("recover from callback")
            self.assertTrue(failure_reported.wait(2))
            self.assertTrue(store.flush(timeout=2))

        records = [json.loads(line) for line in
                   (store.path / "events.log").read_text(encoding="utf-8").splitlines()]
        self.assertEqual(retries, [True])
        self.assertEqual([record["message"] for record in records], ["recover from callback"])

    def test_session_background_failure_retains_work_until_retry(self):
        failed = threading.Event()
        store = log_monitoring.SessionStore(
            "async-recoverable", {}, self.temp / "sessions",
            on_error=lambda _label, _error: failed.set(), async_writes=True)
        original_event = store.event

        def fail_once(_message, _detail=None, _timestamp=None):
            raise OSError("temporary background disk fault")

        with patch.object(store, "event", side_effect=fail_once):
            store.enqueue_event("background work", {"id": "original"})
            self.assertTrue(failed.wait(2))
            self.assertFalse(store.flush(timeout=1))

        with patch.object(store, "event", side_effect=original_event):
            self.assertTrue(store.retry())
            self.assertTrue(store.flush(timeout=2))
        record = json.loads((store.path / "events.log").read_text(encoding="utf-8"))
        self.assertEqual(record["message"], "background work")
        self.assertEqual(record["detail"], {"id": "original"})
        self.assertTrue(store.write_history)

    def test_session_initialization_failure_is_recoverable_after_location_repair(self):
        root = self.temp / "blocked-root"
        root.write_text("not a directory", encoding="utf-8")
        store = log_monitoring.SessionStore("init-recovery", {}, root)
        self.assertTrue(store.write_errors)
        self.assertFalse(store.flush())

        root.unlink()
        self.assertTrue(store.retry())
        self.assertTrue(store.flush(timeout=2))
        self.assertTrue((store.path / "session.json").is_file())
        self.assertTrue(store.write_history)

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
        self.assertEqual(monitor.results[1].status, "COMPLETING")
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

    def test_active_batch_leaves_unseen_slots_waiting_for_shared_start_deadline(self):
        active, final = self.temp / "active", self.temp / "unitest"
        monitor = AtlasActiveArchiveMonitor("DFU", active, final, (1, 2), now=lambda: self.now, session_root=self.temp / "sessions")
        write_records(active / "group0-slot1" / "system" / "records.csv", "HK5HUX6STQ800003YV", "PASS")
        monitor.poll_once()
        self.assertEqual(monitor.results[2].status, "WAITING")
        (active / "group0-slot1").rename(active / "completed-slot1")
        monitor.poll_once()
        self.now += timedelta(seconds=300)
        monitor.poll_once()
        self.assertEqual(monitor.results[2].status, "WAITING")

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

    def test_bt_locks_batch_and_empty_failed_csv_is_fail(self):
        clock = [0.0]
        root = self.temp / "TestData"
        monitor = BtLogMonitor(root, (1,), now=lambda: self.now, monotonic=lambda: clock[0], session_root=self.temp / "sessions")
        filename = "[Thread0][cfg][][FAILED][20220618022901].csv"
        write_bt(root / "2022-06-18" / "FAILED" / filename, "", "FAILED", "0")
        monitor.poll_once()
        clock[0] = 5.1
        monitor.poll_once()
        self.assertEqual(monitor.batch_stamp, "20220618022901")
        self.assertEqual(monitor.results[1].status, "FAIL")

    def test_b482_adapter_exposes_exact_batch_identity_for_common_round(self):
        clock = [0.0]
        root = self.temp / "TestData"
        root.mkdir()
        adapter = B482SourceAdapter(root, None, self.now, lambda: self.now, lambda: clock[0])
        first = root / "2022-06-18" / "PASSED" / "[Thread0][cfg][HK5HUX6STQ800003YV][PASSED][20220618022901].csv"
        second = root / "2022-06-18" / "PASSED" / "[Thread0][cfg][HK5HUX6STQ900003YV][PASSED][20220618022901].csv"
        other_batch = root / "2022-06-18" / "PASSED" / "[Thread0][cfg][HK5HUX6STQ700003YV][PASSED][20220618023001].csv"
        write_bt(first, "HK5HUX6STQ800003YV", "PASSED", "0")
        write_bt(second, "HK5HUX6STQ900003YV", "PASSED", "0")
        write_bt(other_batch, "HK5HUX6STQ700003YV", "PASSED", "0")
        adapter.poll()
        clock[0] = 5.1
        observations = [item for item in adapter.poll()
                        if item.kind == B482ObservationKind.TESTDATA_RESULT]
        evidence = {item.sn: item.evidence()["round_evidence_id"] for item in observations}
        self.assertEqual(evidence["HK5HUX6STQ800003YV"], evidence["HK5HUX6STQ900003YV"])
        self.assertNotEqual(evidence["HK5HUX6STQ800003YV"], evidence["HK5HUX6STQ700003YV"])

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
        monitor = BtLogMonitor(self.temp / "TestData", (1,),
                               now=lambda: self.now, session_root=self.temp / "sessions")
        self.assertEqual(monitor.start_timeout_seconds, 30)
        self.assertEqual(monitor.test_timeout_seconds, 240)

    def test_log_solution_never_imports_control_dependencies(self):
        base = Path(__file__).resolve().parents[1] / "src"
        content = "".join((base / name).read_text() for name in (
            "log_monitoring.py", "b518_log_solution.py", "global_hotkey.py",
        ))
        for forbidden in ("import serial", "import cv2", "import socket", "Arduino", "SCREENSHOT"):
            self.assertNotIn(forbidden, content)


if __name__ == "__main__":
    unittest.main()
