import tempfile
import threading
import csv
import io
import json
import unittest
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from log_monitoring import AtlasActiveArchiveMonitor, BtLogMonitor, MonitorEvent, SessionStore, SlotResult
from monitoring_round import RoundCoordinator
from audit_records import AuditRecordError, RoundAuditStore, read_round_audit
from rswmt_monitoring import RsWmtLogMonitor
from configured_monitor import ConfiguredMonitor


class AuditFakeMonitor:
    def __init__(self, callback, clock, slots=(1, 2)):
        self.callback = callback
        self.clock = clock
        self.results = {slot: SlotResult(slot) for slot in slots}
        self.round_limits = {"start": 30, "test": 60, "round": 10}
        self.pending = []
        self.collection_stopped = False

    def round_results(self):
        return tuple(self.results.values())

    def timeout_seconds(self, kind):
        return self.round_limits[kind]

    def update_round_settings(self, _settings):
        pass

    def publish_round_event(self, event):
        self.callback(event)

    def apply_round_result(self, slot, status, sn="", source="", detail=None, lock_terminal=False):
        result = self.results[slot]
        result.status, result.sn, result.source = status, sn or result.sn, source or result.source
        result.updated_at = "2026-10-05T12:00:00"
        self.callback(MonitorEvent("result", "slot{} {}".format(slot, status), slot, result.sn,
                                   status, result.source, detail or {}))

    def set_result(self, slot, status, detail=None, lock_terminal=False):
        self.apply_round_result(slot, status, detail=detail, lock_terminal=lock_terminal)

    def start(self):
        pass

    def poll_once(self):
        pending, self.pending = self.pending, []
        for action in pending:
            action()

    def stop_collection(self):
        self.collection_stopped = True

    def finish(self):
        self.collection_stopped = True

    def stop(self):
        self.collection_stopped = True
        for slot, result in self.results.items():
            if result.status not in {"PASS", "FAIL", "NOTEST", "TIMEOUT", "STOPPED"}:
                self.apply_round_result(slot, "STOPPED")
        self.callback(MonitorEvent("stopped", "manual stop"))


class RoundAuditRecordTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.audit_root = Path(self.temp.name) / "sessions"
        self.clock = [0.0]
        self.monitors = []
        self.coordinator = RoundCoordinator(monotonic=lambda: self.clock[0], audit_root=self.audit_root)

    def start_round(self, round_timeout=10):
        def factory(callback):
            monitor = AuditFakeMonitor(callback, lambda: self.clock[0])
            monitor.round_limits["round"] = round_timeout
            self.monitors.append(monitor)
            return monitor

        return self.coordinator.start(
            "FCT", factory, run_async=False, round_timeout_seconds=round_timeout,
            capacity=2,
            audit_context={"project": "B518", "machine": "FCT", "platform": "atlas",
                           "profile_version": 1, "capacity": 2,
                           "mapping": [{"source": 2, "display": 1}, {"source": 4, "display": 2}],
                           "timeouts": {"start": 30, "test": 60, "round": round_timeout}},
        )

    def audit_path(self, round_id):
        return self.audit_root / round_id / "audit.jsonl"

    def rebuild_current_round(self, round_id):
        self.assertTrue(self.coordinator.flush_audit())
        return read_round_audit(self.audit_path(round_id))

    def test_normal_round_can_be_rebuilt_from_a_fresh_disk_reader(self):
        started = self.start_round()
        monitor = self.monitors[0]
        monitor.pending.extend([
            lambda: monitor.apply_round_result(1, "PASS", "SN-A", "/source/a",
                                               {"source_position": 2, "source_time": "2026-10-05T11:59:00"}),
            lambda: monitor.apply_round_result(2, "FAIL", "SN-B", "/source/b",
                                               {"source_position": 4, "source_time": "2026-10-05T11:59:01"}),
        ])
        completed = self.coordinator.poll_once()

        self.assertTrue(completed.result_available)
        rebuilt = self.rebuild_current_round(started.round_id)
        self.assertEqual(rebuilt["round"]["config"]["profile_version"], 1)
        self.assertEqual(rebuilt["results"][1]["status"], "PASS")
        self.assertEqual(rebuilt["results"][2]["status"], "FAIL")
        kinds = [event["kind"] for event in rebuilt["events"]]
        self.assertLess(kinds.index("collection_stopped"), kinds.index("finished"))
        self.assertTrue(rebuilt["result_available"])
        self.assertEqual([event["sequence"] for event in rebuilt["events"]],
                         list(range(1, len(rebuilt["events"]) + 1)))

    def test_completed_round_audit_writers_exit_after_idle_period(self):
        round_ids = []
        for _ in range(6):
            started = self.start_round()
            round_ids.append(started.round_id)
            monitor = self.monitors[-1]
            monitor.pending.extend([
                lambda monitor=monitor: monitor.apply_round_result(1, "PASS", "SN-A"),
                lambda monitor=monitor: monitor.apply_round_result(2, "PASS", "SN-B"),
            ])
            completed = self.coordinator.poll_once()
            self.assertTrue(completed.result_available)
            self.assertTrue(self.coordinator.flush_audit())

        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline:
            workers = [thread for thread in threading.enumerate()
                       if thread.is_alive() and thread.name.startswith("round-audit-")
                       and any(thread.name == "round-audit-{}".format(round_id)
                               for round_id in round_ids)]
            if not workers:
                break
            time.sleep(0.01)

        self.assertEqual(workers, [], "completed rounds retained idle audit workers")

    def test_round_alarm_can_be_acknowledged_after_idle_writer_exits(self):
        started = self.start_round(round_timeout=3)
        self.clock[0] = 3.0
        waiting = self.coordinator.poll_once()
        self.assertIsNotNone(waiting.round_alarm)
        self.assertTrue(self.coordinator.flush_audit())

        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline and any(
                thread.is_alive() and thread.name == "round-audit-{}".format(started.round_id)
                for thread in threading.enumerate()):
            time.sleep(0.01)
        self.assertFalse(any(
            thread.is_alive() and thread.name == "round-audit-{}".format(started.round_id)
            for thread in threading.enumerate()))

        completed = self.coordinator.acknowledge_round_alarm(
            started.round_id, waiting.round_alarm.alarm_id)
        self.assertTrue(completed.result_available)
        rebuilt = self.rebuild_current_round(started.round_id)
        kinds = [event["kind"] for event in rebuilt["events"]]
        self.assertLess(kinds.index("collection_stopped"), kinds.index("round_alarm_acknowledged"))
        self.assertLess(kinds.index("round_alarm_acknowledged"), kinds.index("finished"))

    def test_conflict_resolution_after_manual_stop_and_idle_exit_is_reconstructable(self):
        started = self.start_round()
        monitor = self.monitors[0]
        monitor.pending.append(lambda: monitor.apply_round_result(
            1, "PASS", "SN-OLD", "/source/old",
            {"source_position": 2, "source_id": "original", "source_time": "2026-10-05T11:00:00",
             "round_evidence_id": "batch-1"},
        ))
        self.coordinator.poll_once()
        monitor.callback(MonitorEvent(
            "result_candidate", "candidate", slot=1, sn="SN-NEW", status="FAIL", source="/source/new",
            detail={"source_position": 2, "source_id": "candidate", "source_time": "2026-10-05T11:01:00",
                    "round_evidence_id": "batch-1"},
        ))
        waiting = self.coordinator.stop()
        self.assertTrue(waiting.collection_stopped)
        self.assertEqual(waiting.state.value, "STOPPED")
        conflict_id = waiting.pending_conflicts[0].conflict_id
        self.assertTrue(self.coordinator.flush_audit())

        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline and any(
                thread.is_alive() and thread.name == "round-audit-{}".format(started.round_id)
                for thread in threading.enumerate()):
            time.sleep(0.01)
        self.assertFalse(any(
            thread.is_alive() and thread.name == "round-audit-{}".format(started.round_id)
            for thread in threading.enumerate()))

        completed = self.coordinator.resolve_review(conflict_id, "accept_candidate")
        self.assertEqual(completed.state.value, "STOPPED")
        rebuilt = self.rebuild_current_round(started.round_id)
        resolution = next(event for event in rebuilt["events"]
                          if event["kind"] == "conflict_resolved")
        self.assertEqual(resolution["detail"]["choice"], "accept_candidate")
        self.assertEqual(rebuilt["results"][1]["sn"], "SN-NEW")

    def test_concurrent_audit_events_near_idle_exit_are_all_reconstructed_in_order(self):
        started = self.start_round()
        self.assertTrue(self.coordinator.flush_audit())

        for index in range(10):
            self.assertTrue(self.coordinator.flush_audit())
            if index % 2 == 0:
                time.sleep(0.19)
            barrier = threading.Barrier(3)

            def acknowledge_stale_alarm():
                barrier.wait()
                self.coordinator.acknowledge_round_alarm("stale-round", "stale-alarm")

            workers = [threading.Thread(target=acknowledge_stale_alarm) for _ in range(2)]
            for worker in workers:
                worker.start()
            barrier.wait()
            for worker in workers:
                worker.join(2)
                self.assertFalse(worker.is_alive())

        self.assertTrue(self.coordinator.flush_audit())
        rebuilt = self.rebuild_current_round(started.round_id)
        events = rebuilt["events"]
        self.assertEqual(len([event for event in events
                              if event["kind"] == "round_alarm_acknowledgement_ignored"]), 20)
        self.assertEqual([event["sequence"] for event in events],
                         list(range(1, len(events) + 1)))
        self.assertTrue(rebuilt["audit_complete"])

    def test_conflict_candidate_choice_and_release_are_reconstructable(self):
        started = self.start_round()
        monitor = self.monitors[0]
        monitor.pending.append(lambda: monitor.apply_round_result(
            1, "PASS", "SN-OLD", "/source/old",
            {"source_position": 2, "source_id": "original", "source_time": "2026-10-05T11:00:00",
             "round_evidence_id": "batch-1"},
        ))
        self.coordinator.poll_once()
        monitor.callback(MonitorEvent(
            "result_candidate", "candidate", slot=1, sn="SN-NEW", status="FAIL", source="/source/new",
            detail={"source_position": 2, "source_id": "candidate", "source_time": "2026-10-05T11:01:00",
                    "round_evidence_id": "batch-1"},
        ))
        waiting = self.coordinator.snapshot()
        self.assertFalse(waiting.result_available)
        conflict_id = waiting.pending_conflicts[0].conflict_id
        monitor.pending.append(lambda: monitor.apply_round_result(2, "PASS", "SN-OTHER", "/source/other"))
        waiting = self.coordinator.poll_once()
        self.assertTrue(waiting.collection_stopped)
        completed = self.coordinator.resolve_review(conflict_id, "accept_candidate")

        self.assertTrue(completed.result_available)
        rebuilt = self.rebuild_current_round(started.round_id)
        conflict = next(event for event in rebuilt["events"] if event["kind"] == "conflict_detected")
        resolution = next(event for event in rebuilt["events"] if event["kind"] == "conflict_resolved")
        self.assertEqual(conflict["detail"]["candidate"]["sn"], "SN-NEW")
        self.assertEqual(resolution["detail"]["choice"], "accept_candidate")
        self.assertEqual(rebuilt["results"][1]["sn"], "SN-NEW")
        self.assertTrue(rebuilt["result_available"])

    def test_round_deadline_alarm_and_release_have_independent_durable_events(self):
        started = self.start_round(round_timeout=3)
        self.clock[0] = 3.0
        waiting = self.coordinator.poll_once()
        self.assertFalse(waiting.result_available)
        alarm_id = waiting.round_alarm.alarm_id
        self.assertTrue(waiting.collection_stopped)
        released = self.coordinator.acknowledge_round_alarm(started.round_id, alarm_id)
        self.assertTrue(released.result_available)

        rebuilt = self.rebuild_current_round(started.round_id)
        kinds = [event["kind"] for event in rebuilt["events"]]
        self.assertIn("timeout", kinds)
        self.assertIn("round_alarm_acknowledged", kinds)
        self.assertLess(kinds.index("collection_stopped"), kinds.index("round_alarm_acknowledged"))
        self.assertLess(kinds.index("round_alarm_acknowledged"), kinds.index("finished"))
        self.assertTrue(rebuilt["result_available"])
        self.assertEqual({result["status"] for result in rebuilt["results"].values()}, {"NOTEST"})

    def test_reader_rejects_truncated_or_corrupt_records(self):
        started = self.start_round()
        path = self.audit_path(started.round_id)
        self.assertTrue(self.coordinator.flush_audit())
        with path.open("a", encoding="utf-8") as handle:
            handle.write('{"truncated":')
        with self.assertRaises(AuditRecordError):
            read_round_audit(path)

    def test_reader_reports_malformed_record_shapes_and_invalid_utf8(self):
        started = self.start_round()
        path = self.audit_path(started.round_id)
        self.assertTrue(self.coordinator.flush_audit())
        header = path.read_bytes().splitlines()[0]
        malformed_event = json.dumps({
            "record_type": "event", "schema_version": 1,
            "round_id": started.round_id, "sequence": 1,
        }).encode("utf-8")
        for contents in (b"[]\n", header + b"\n" + malformed_event + b"\n", b"\xff\n"):
            with self.subTest(contents=contents):
                path.write_bytes(contents)
                with self.assertRaises(AuditRecordError):
                    read_round_audit(path)

    def test_reader_rejects_incomplete_result_event_instead_of_rebuilding_silently(self):
        started = self.start_round()
        path = self.audit_path(started.round_id)
        self.assertTrue(self.coordinator.flush_audit())
        header = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
        incomplete_result = {
            "record_type": "event", "schema_version": 1,
            "round_id": started.round_id, "sequence": 1, "kind": "result",
            "observed_at": "2026-10-05T12:00:00", "elapsed_seconds": 1.0,
            "detail": {},
        }
        path.write_text(json.dumps(header) + "\n" + json.dumps(incomplete_result) + "\n",
                        encoding="utf-8")

        with self.assertRaises(AuditRecordError):
            read_round_audit(path)

    def test_audit_write_failure_is_visible_but_does_not_block_product_release(self):
        started = self.start_round()
        monitor = self.monitors[0]
        monitor.pending.extend([
            lambda: monitor.apply_round_result(1, "PASS", "SN-A"),
            lambda: monitor.apply_round_result(2, "PASS", "SN-B"),
        ])
        with patch.object(RoundAuditStore, "append_event", side_effect=OSError("disk full")):
            completed = self.coordinator.poll_once()

        self.assertTrue(completed.result_available)
        self.assertFalse(completed.audit_complete)
        self.assertTrue(completed.audit_errors)
        self.assertIn("audit_write_failed", [event.event.kind for event in completed.events])
        self.assertTrue(self.coordinator.flush_audit())

    def test_background_disk_failure_is_visible_without_blocking_release(self):
        started = self.start_round()
        monitor = self.monitors[0]
        monitor.pending.extend([
            lambda: monitor.apply_round_result(1, "PASS", "SN-A"),
            lambda: monitor.apply_round_result(2, "PASS", "SN-B"),
        ])
        with patch.object(RoundAuditStore, "_append_complete_line",
                          side_effect=OSError("disk full")):
            completed = self.coordinator.poll_once()
            self.assertTrue(completed.result_available)
            self.assertFalse(self.coordinator.flush_audit(timeout=2))
            completed = self.coordinator.snapshot()

        self.assertTrue(completed.result_available)
        self.assertFalse(completed.audit_complete)
        self.assertTrue(completed.audit_errors)
        self.assertIn("audit_write_failed", [event.event.kind for event in completed.events])

    def test_atomic_legacy_result_update_keeps_previous_complete_file_on_failure(self):
        store = SessionStore("atomic-session", {}, Path(self.temp.name) / "legacy")
        store.update_results([SlotResult(1, "SN-OLD", "PASS")])
        path = store.path / "results.csv"
        previous = path.read_bytes()

        with patch("log_monitoring.os.replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                store.update_results([SlotResult(1, "SN-NEW", "FAIL")])

        self.assertEqual(path.read_bytes(), previous)

    def test_session_writes_are_queued_off_the_calling_thread(self):
        store = SessionStore("queued-session", {}, Path(self.temp.name) / "queued", async_writes=True)
        entered = threading.Event()
        release = threading.Event()

        def slow_event(_message, _detail=None):
            entered.set()
            release.wait(2)

        with patch.object(store, "event", side_effect=slow_event):
            started_at = __import__("time").monotonic()
            store.enqueue_event("queued event")
            elapsed = __import__("time").monotonic() - started_at
            self.assertLess(elapsed, 0.1)
            self.assertTrue(entered.wait(1))
            release.set()
            self.assertTrue(store.flush())

    def test_parallel_round_events_keep_a_deterministic_persistent_order(self):
        started = self.start_round()
        monitor = self.monitors[0]
        workers = [threading.Thread(target=monitor.callback,
                                    args=(MonitorEvent("diagnostic", "event-{}".format(index)),))
                   for index in range(8)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(2)
            self.assertFalse(worker.is_alive())

        self.assertTrue(self.coordinator.flush_audit())
        rebuilt = self.rebuild_current_round(started.round_id)
        sequences = [event["sequence"] for event in rebuilt["events"]]
        self.assertEqual(sequences, sorted(sequences))
        self.assertEqual(len(sequences), len(set(sequences)))
        self.assertTrue(rebuilt["audit_complete"])

    def test_source_preparation_deadline_is_written_before_delayed_adapter_returns(self):
        entered = threading.Event()
        release = threading.Event()
        monitors = []

        def factory(callback):
            entered.set()
            release.wait(3)
            monitor = AuditFakeMonitor(callback, lambda: self.clock[0])
            monitors.append(monitor)
            return monitor

        started = self.coordinator.start("FCT", factory, run_async=True,
                                         round_timeout_seconds=3, capacity=2,
                                         audit_context={"profile_version": 1})
        self.assertTrue(entered.wait(2))
        self.clock[0] = 3
        timed_out = self.coordinator.poll_once()
        self.assertFalse(timed_out.result_available)
        release.set()
        deadline = __import__("time").monotonic() + 2
        while self.coordinator.snapshot().round_alarm_ready is False:
            if __import__("time").monotonic() >= deadline:
                self.fail("delayed adapter did not finish deadline handoff")
            __import__("time").sleep(0.01)
        self.coordinator.acknowledge_round_alarm(started.round_id,
                                                  self.coordinator.snapshot().round_alarm.alarm_id)

        rebuilt = self.rebuild_current_round(started.round_id)
        kinds = [event["kind"] for event in rebuilt["events"]]
        self.assertIn("timeout", kinds)
        self.assertIn("round_alarm_created", kinds)
        self.assertIn("collection_stopped", kinds)
        self.assertIn("finished", kinds)
        self.assertTrue(rebuilt["result_available"])

    def test_atlas_adapter_and_profile_mapping_are_persisted_through_shared_round(self):
        root = Path(self.temp.name)
        active, archive = root / "active", root / "archive"
        now = datetime(2026, 10, 5, 12, 0, 0)
        coordinator = RoundCoordinator(audit_root=root / "adapter-sessions")

        def factory(callback):
            view_holder = {}

            def deliver(event):
                view = view_holder.get("view")
                return view.deliver(event, callback) if view else callback(event)

            monitor = AtlasActiveArchiveMonitor("FCT", active, archive, (2,), callback=callback,
                                                now=lambda: now, session_root=root / "legacy-sessions")
            monitor.callback = deliver
            configured = ConfiguredMonitor(monitor, {2: 1})
            view_holder["view"] = configured
            return configured

        started = coordinator.start("FCT", factory, run_async=False, capacity=1,
                                    audit_context={"profile_version": 1, "mapping": [
                                        {"source": 2, "display": 1}], "capacity": 1})
        active_record = active / "group0-slot2" / "system" / "records.csv"
        active_record.parent.mkdir(parents=True)
        active_record.write_text("MLB_SN,status\nATLASAUDIT0001,Pass\n", encoding="utf-8")
        coordinator.poll_once()
        self.assertEqual(coordinator.snapshot().results[0].status, "TESTING")
        archive_record = (archive / "ATLASAUDIT0001" / "20261005_12-00-01.000-ticket13"
                          / "system" / "records.csv")
        archive_record.parent.mkdir(parents=True)
        archive_record.write_text("MLB_SN,status\nATLASAUDIT0001,Pass\n", encoding="utf-8")
        import shutil
        shutil.rmtree(active / "group0-slot2")
        coordinator.poll_once()
        completed = coordinator.poll_once()

        self.assertTrue(completed.result_available)
        self.assertTrue(coordinator.flush_audit())
        rebuilt = read_round_audit(coordinator.session_path / "audit.jsonl")
        result = rebuilt["results"][1]
        self.assertEqual((result["source_position"], result["sn"], result["status"]),
                         ("2", "ATLASAUDIT0001", "PASS"))
        self.assertEqual(rebuilt["round"]["round_id"], started.round_id)

    def test_b482_adapter_source_batch_is_reconstructable_from_common_round(self):
        root = Path(self.temp.name)
        output = root / "TestData"
        now = datetime(2026, 10, 5, 12, 0, 0)
        clock = [0.0]
        coordinator = RoundCoordinator(monotonic=lambda: clock[0], audit_root=root / "sessions")

        def factory(callback):
            view_holder = {}

            def deliver(event):
                view = view_holder.get("view")
                return view.deliver(event, callback) if view else callback(event)

            monitor = BtLogMonitor(output, (1,), callback=deliver, now=lambda: now,
                                   monotonic=lambda: clock[0], start_timeout_seconds=240,
                                   test_timeout_seconds=60, round_timeout_seconds=120,
                                   session_root=root / "legacy-sessions")
            configured = ConfiguredMonitor(monitor, {1: 1})
            view_holder["view"] = configured
            return configured

        started = coordinator.start("BT", factory, run_async=False, capacity=1)
        result = output / "2026-10-05" / "PASSED" / (
            "[Thread0][cfg][B482AUDIT0001][PASSED][20261005120001].csv")
        result.parent.mkdir(parents=True)
        with result.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["SerialNumber", "Unit Number",
                "Test Pass/Fail Status", "StartTime", "EndTime"])
            writer.writeheader()
            writer.writerow({"SerialNumber": "B482AUDIT0001", "Unit Number": "0",
                             "Test Pass/Fail Status": "PASSED", "StartTime": "x", "EndTime": "y"})
        coordinator.poll_once()
        clock[0] = 5.1
        coordinator.poll_once()
        completed = coordinator.poll_once()

        self.assertTrue(coordinator.flush_audit())
        rebuilt = read_round_audit(coordinator.session_path / "audit.jsonl")
        self.assertTrue(completed.result_available)
        self.assertEqual(rebuilt["results"][1]["status"], "PASS")
        self.assertEqual(rebuilt["results"][1]["source_position"], "1")
        self.assertEqual(rebuilt["round"]["round_id"], started.round_id)

    def test_rswmt_final_only_adapter_is_recorded_without_inventing_activity(self):
        root = Path(self.temp.name)
        output = root / "SmtCal"
        output.mkdir()
        start = datetime(2026, 9, 11, 5, 44, 16)
        clock = [0.0]
        coordinator = RoundCoordinator(monotonic=lambda: clock[0], audit_root=root / "sessions")
        header = ["Serial Number", "Test Pass/Fail Status", "List of Failing Tests",
                  "Error Description", "Test Start Time", "Test Stop Time", "PRODUCT",
                  "tc=Slot:tech=None:band=None;subtc=None:rate=None:freq=None:pwr=None;"]
        content = io.StringIO()
        writer = csv.writer(content)
        writer.writerow(["Overlay", "SmtCal"] + [""] * 6)
        writer.writerow(header)
        for name in ("Upper Limits", "Lower Limits", "Apple Pass Upper Limits",
                     "Apple Pass Lower Limits", "Measurement Unit"):
            writer.writerow([name + "----->"] + [""] * 7)
        writer.writerow(["RSWMTAUDIT0001", "Pass", "[]", "", "2026/11/09 05:44:16",
                         "2026/11/09 05:45:44", "B518", 1])
        path = output / "2026-09-11_05-45-44" / "RSWMTAUDIT0001_2026-09-11_05-45-44.csv"

        def factory(callback):
            return RsWmtLogMonitor(output, slots=(1,), callback=callback,
                                   now=lambda: start + timedelta(seconds=clock[0]),
                                   monotonic=lambda: clock[0], start_timeout_seconds=240,
                                   test_timeout_seconds=60, round_timeout_seconds=120,
                                   session_root=root / "legacy-sessions")

        started = coordinator.start("BT", factory, run_async=False, capacity=1)
        path.parent.mkdir(parents=True)
        path.write_text(content.getvalue(), encoding="utf-8")
        coordinator.poll_once()
        clock[0] = 5.1
        clock[0] = 88.0
        coordinator.poll_once()
        clock[0] = 93.0
        coordinator.poll_once()
        completed = coordinator.poll_once()

        self.assertTrue(coordinator.flush_audit())
        rebuilt = read_round_audit(coordinator.session_path / "audit.jsonl")
        self.assertTrue(completed.result_available)
        self.assertEqual(rebuilt["results"][1]["status"], "PASS")
        self.assertEqual(rebuilt["results"][1]["source_time"], "2026-09-11T05:45:44")
        kinds = [event["kind"] for event in rebuilt["events"]]
        self.assertNotIn("TESTING", kinds)
        self.assertEqual(rebuilt["round"]["round_id"], started.round_id)


if __name__ == "__main__":
    unittest.main()
