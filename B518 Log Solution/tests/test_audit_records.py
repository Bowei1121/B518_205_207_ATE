import tempfile
import threading
import csv
import io
import json
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import audit_records
from log_monitoring import (AtlasActiveArchiveMonitor, BaseMonitor, BtLogMonitor, MonitorEvent,
                            SessionStore, SlotResult)
from monitoring_round import RoundCoordinator
from audit_records import AuditEvent, AuditRecordError, RoundAuditStore, read_round_audit
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

    def wait_for_threads_to_return_to(self, baseline, timeout=0.75):
        deadline = time.monotonic() + timeout
        while threading.active_count() > baseline and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertLessEqual(threading.active_count(), baseline,
                             "completed rounds retained audit writer threads")

    def wait_for_retry_to_finish(self, timeout=3):
        deadline = time.monotonic() + timeout
        while self.coordinator.snapshot().retry_in_progress and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertFalse(self.coordinator.snapshot().retry_in_progress,
                         "current-round save retry did not finish")

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
        localized_by_kind = {event["kind"]: event["localized_message"]["message_id"]
                             for event in rebuilt["events"] if "localized_message" in event}
        self.assertEqual(localized_by_kind["round_started"], "round.started")
        self.assertEqual(localized_by_kind["round_ready"], "round.ready")
        self.assertEqual(localized_by_kind["collection_stopped"], "round.collection_stopped")
        self.assertEqual(localized_by_kind["finished"], "round.finished")
        self.assertTrue(rebuilt["result_available"])
        self.assertEqual([event["sequence"] for event in rebuilt["events"]],
                         list(range(1, len(rebuilt["events"]) + 1)))

    def test_shared_round_result_is_one_versioned_bilingual_audit_event(self):
        session_root = Path(self.temp.name) / "legacy-sessions"
        session_stores = []

        def factory(callback):
            session = SessionStore("shared-round-session", {}, session_root)
            session_stores.append(session)

            class SessionBackedMonitor(AuditFakeMonitor):
                station = "FCT"

                def __init__(self):
                    super().__init__(callback, lambda: self_outer.clock[0])
                    self.session = session
                    self.settings = {}

                def update_round_settings(self, settings):
                    self.settings.update(settings)

                def apply_round_result(self, slot, status, sn="", source="", detail=None,
                                       lock_terminal=False):
                    result = self.results[slot]
                    result.status, result.sn, result.source = status, sn, source
                    BaseMonitor.emit(self, MonitorEvent(
                        "result", "slot{} {}".format(slot, status), slot, sn, status,
                        source, detail or {},
                    ))

            self_outer = self
            monitor = SessionBackedMonitor()
            self.monitors.append(monitor)
            return monitor

        started = self.coordinator.start(
            "FCT", factory, run_async=False, round_timeout_seconds=10, capacity=2,
            audit_context={"project": "B518", "machine": "FCT", "platform": "atlas",
                           "profile_version": 1, "capacity": 2,
                           "mapping": [{"source": 2, "display": 1},
                                       {"source": 4, "display": 2}],
                           "timeouts": {"start": 30, "test": 60, "round": 10}},
        )
        self.monitors[0].apply_round_result(
            1, "PASS", "SN-123", "/tmp/source-a.csv",
            {"source_position": 2, "source_time": "2026-10-08T09:10:11"},
        )

        self.assertTrue(self.coordinator.flush_audit())
        rebuilt = read_round_audit(self.coordinator.session_path / "audit.jsonl")
        results = [event for event in rebuilt["events"] if event["kind"] == "result"]
        self.assertEqual(len(results), 1)
        event = results[0]
        self.assertEqual(event["message"], "slot1 PASS")
        self.assertEqual(event["round_id"], started.round_id)
        self.assertEqual(event["display_position"], 1)
        localized = event["localized_message"]
        self.assertEqual(localized["version"], 1)
        self.assertEqual(localized["message_id"], "round.result")
        self.assertEqual(localized["parameters"], {
            "station": "FCT", "slot": 1, "status": "PASS",
        })
        self.assertEqual(localized["en"], "FCT Slot 1 result: PASS")
        self.assertEqual(localized["zh-TW"], "FCT 通道 1 結果：PASS")
        session_stores[0].flush(2)
        session_events = [json.loads(line) for line in
                          (session_root / "shared-round-session" / "events.log").read_text(
                              encoding="utf-8").splitlines()]
        session_result = next(item for item in session_events if item["message"] == "slot1 PASS")
        self.assertEqual(session_result["localized_message"], localized)
        self.assertEqual(session_result["detail"]["round_id"], started.round_id)
        self.assertEqual(session_result["round_id"], event["round_id"])
        self.assertEqual(session_result["sequence"], event["sequence"])
        self.assertEqual(session_result["timestamp"], event["observed_at"])
        self.assertEqual([item["sequence"] for item in rebuilt["events"]],
                         list(range(1, len(rebuilt["events"]) + 1)))
        self.assertTrue(rebuilt["audit_complete"])

    def test_completed_round_audit_writers_exit_after_idle_period(self):
        thread_baseline = threading.active_count()
        for _ in range(6):
            started = self.start_round()
            monitor = self.monitors[-1]
            monitor.pending.extend([
                lambda monitor=monitor: monitor.apply_round_result(1, "PASS", "SN-A"),
                lambda monitor=monitor: monitor.apply_round_result(2, "PASS", "SN-B"),
            ])
            completed = self.coordinator.poll_once()
            self.assertTrue(completed.result_available)
            self.assertTrue(self.coordinator.flush_audit())

        self.wait_for_threads_to_return_to(thread_baseline)

    def test_round_alarm_can_be_acknowledged_after_idle_writer_exits(self):
        thread_baseline = threading.active_count()
        started = self.start_round(round_timeout=3)
        self.clock[0] = 3.0
        waiting = self.coordinator.poll_once()
        self.assertIsNotNone(waiting.round_alarm)
        self.assertTrue(self.coordinator.flush_audit())

        self.wait_for_threads_to_return_to(thread_baseline)

        completed = self.coordinator.acknowledge_round_alarm(
            started.round_id, waiting.round_alarm.alarm_id)
        self.assertTrue(completed.result_available)
        rebuilt = self.rebuild_current_round(started.round_id)
        kinds = [event["kind"] for event in rebuilt["events"]]
        self.assertLess(kinds.index("collection_stopped"), kinds.index("round_alarm_acknowledged"))
        self.assertLess(kinds.index("round_alarm_acknowledged"), kinds.index("finished"))

    def test_transient_audit_append_failure_retries_original_record_from_public_coordinator(self):
        wall_clock = [datetime(2026, 10, 7, 12, 0, 0)]
        self.coordinator = RoundCoordinator(
            monotonic=lambda: self.clock[0], audit_root=self.audit_root,
            wall_clock=lambda: wall_clock[0])
        started = self.start_round()
        original_append = RoundAuditStore.append_event
        failed = threading.Event()

        def fail_one_append(store, event, observed_at, elapsed_seconds):
            if not failed.is_set() and event.kind == "result":
                failed.set()
                raise OSError("temporary disk fault")
            return original_append(store, event, observed_at, elapsed_seconds)

        with patch.object(RoundAuditStore, "append_event", new=fail_one_append):
            self.monitors[0].callback(MonitorEvent(
                "result", "preserve this", slot=1, status="PASS",
                detail={"original": "payload"}))
            deadline = time.monotonic() + 2
            while not failed.is_set() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(failed.is_set())
            self.assertTrue(self.coordinator.flush_audit(timeout=0.2))
            self.assertFalse(self.coordinator.snapshot().audit_complete)

        wall_clock[0] = datetime(2026, 10, 7, 12, 30, 0)
        self.assertTrue(self.coordinator.retry_saves())
        self.wait_for_retry_to_finish()
        self.assertTrue(self.coordinator.flush_audit(timeout=2))
        rebuilt = read_round_audit(self.audit_path(started.round_id))
        event = next(item for item in rebuilt["events"] if item["kind"] == "result")
        live = next(item for item in self.coordinator.snapshot().events
                    if item.event.kind == "result")
        self.assertEqual(event["sequence"], live.sequence)
        self.assertEqual(event["observed_at"], "2026-10-07T12:00:00")
        self.assertEqual(event["detail"], {"original": "payload"})
        self.assertEqual(event["localized_message"]["message_id"], "round.result")
        self.assertEqual(event["localized_message"]["en"], "FCT Slot 1 result: PASS")
        self.assertEqual([item["sequence"] for item in rebuilt["events"]],
                         list(range(1, len(rebuilt["events"]) + 1)))
        self.assertTrue(self.coordinator.snapshot().audit_complete)

    def test_audit_store_initialization_failure_is_retained_and_rebuilt_after_retry(self):
        original_store = RoundAuditStore
        attempts = [0]

        def fail_initialization_once(*args, **kwargs):
            attempts[0] += 1
            if attempts[0] == 1:
                raise OSError("temporary audit directory failure")
            return original_store(*args, **kwargs)

        self.coordinator = RoundCoordinator(monotonic=lambda: self.clock[0],
                                            audit_root=self.audit_root)
        with patch("monitoring_round.RoundAuditStore", side_effect=fail_initialization_once):
            started = self.start_round()
        self.monitors[0].callback(MonitorEvent(
            "initialization_recovery_probe", "retain before store exists"))
        self.coordinator.stop()

        failed = self.coordinator.snapshot()
        self.assertEqual(failed.save_state, "failed")
        self.assertFalse(failed.audit_complete)
        self.assertIn("temporary audit directory failure", failed.save_errors[0])
        self.assertTrue(self.coordinator.retry_saves())
        self.wait_for_retry_to_finish()

        rebuilt = read_round_audit(self.audit_path(started.round_id))
        probe = next(event for event in rebuilt["events"]
                     if event["kind"] == "initialization_recovery_probe")
        self.assertEqual(probe["message"], "retain before store exists")
        self.assertEqual([event["sequence"] for event in rebuilt["events"]],
                         list(range(1, len(rebuilt["events"]) + 1)))
        self.assertTrue(rebuilt["audit_complete"])
        self.assertEqual(self.coordinator.snapshot().save_state, "complete")

    def test_monitor_startup_failure_is_not_mislabeled_as_persistence_failure(self):
        start_failed = threading.Event()

        def observe(round_event):
            if round_event.event.kind == "start_failed":
                start_failed.set()

        coordinator = RoundCoordinator(on_event=observe, audit_root=self.audit_root)

        def broken_factory(_callback):
            raise RuntimeError("monitor source is unavailable")

        started = coordinator.start("FCT", broken_factory, run_async=True, capacity=1)
        self.assertTrue(start_failed.wait(2))
        self.assertTrue(coordinator.flush_audit(timeout=2))
        snapshot = coordinator.snapshot()
        self.assertEqual(snapshot.save_state, "complete")
        self.assertEqual(snapshot.save_errors, ())
        rebuilt = read_round_audit(self.audit_path(started.round_id))
        self.assertTrue(any(event["kind"] == "start_failed" for event in rebuilt["events"]))

    def test_append_completed_before_error_report_is_not_duplicated_on_retry(self):
        started = self.start_round()
        original_write = audit_records.os.write
        reported = threading.Event()

        def append_then_report_error(descriptor, content):
            written = original_write(descriptor, content)
            if b"durable_before_error" in content:
                reported.set()
                raise OSError("acknowledgement lost after append")
            return written

        with patch.object(audit_records.os, "write", side_effect=append_then_report_error), \
                patch.object(audit_records.os, "ftruncate", side_effect=OSError("cannot roll back")):
            self.monitors[0].callback(MonitorEvent("durable_before_error", "exactly once"))
            self.assertTrue(reported.wait(2))
            self.assertFalse(self.coordinator.flush_audit(timeout=0.2))

        self.assertTrue(self.coordinator.retry_saves())
        self.wait_for_retry_to_finish()
        self.assertTrue(self.coordinator.flush_audit(timeout=2))
        rebuilt = read_round_audit(self.audit_path(started.round_id))
        events = [item for item in rebuilt["events"] if item["kind"] == "durable_before_error"]
        self.assertEqual(len(events), 1)
        self.assertTrue(rebuilt["audit_complete"])

    def test_partial_audit_append_is_repaired_without_overwriting_valid_records(self):
        started = self.start_round()
        original_write = audit_records.os.write
        failed = threading.Event()

        def partial_then_fail(descriptor, content):
            if b"partial_probe" in content and not failed.is_set():
                failed.set()
                original_write(descriptor, content[:max(1, len(content) // 2)])
                raise OSError("partial disk write")
            return original_write(descriptor, content)

        with patch.object(audit_records.os, "write", side_effect=partial_then_fail), \
                patch.object(audit_records.os, "ftruncate", side_effect=OSError("rollback unavailable")):
            self.monitors[0].callback(MonitorEvent("partial_probe", "repair only trailing bytes"))
            self.assertTrue(failed.wait(2))
            self.assertFalse(self.coordinator.flush_audit(timeout=1))

        self.assertTrue(self.coordinator.retry_saves())
        self.wait_for_retry_to_finish()
        self.assertTrue(self.coordinator.flush_audit(timeout=2))
        rebuilt = read_round_audit(self.audit_path(started.round_id))
        self.assertEqual(len([event for event in rebuilt["events"] if event["kind"] == "partial_probe"]), 1)
        self.assertEqual([event["sequence"] for event in rebuilt["events"]],
                         list(range(1, len(rebuilt["events"]) + 1)))
        self.assertTrue(rebuilt["audit_complete"])

    def test_synchronous_audit_enqueue_failure_preserves_order_after_recovery(self):
        started = self.start_round()
        original_append = RoundAuditStore.append_event
        failed = threading.Event()

        def fail_before_enqueue(store, event, observed_at, elapsed_seconds):
            if event.kind == "sync_enqueue_probe" and not failed.is_set():
                failed.set()
                raise OSError("temporary enqueue failure")
            return original_append(store, event, observed_at, elapsed_seconds)

        with patch.object(RoundAuditStore, "append_event", new=fail_before_enqueue):
            self.monitors[0].callback(MonitorEvent("sync_enqueue_probe", "first"))
            self.assertTrue(failed.is_set())
            later = threading.Thread(target=self.monitors[0].callback,
                                     args=(MonitorEvent("after_sync_enqueue", "second"),))
            later.start()
            later.join(2)
            self.assertFalse(later.is_alive(), "saving failure blocked event collection")

        self.assertTrue(self.coordinator.retry_saves())
        self.wait_for_retry_to_finish()
        later.join(2)
        self.assertFalse(later.is_alive())
        self.assertTrue(self.coordinator.flush_audit(timeout=2))
        rebuilt = read_round_audit(self.audit_path(started.round_id))
        kinds = [event["kind"] for event in rebuilt["events"]]
        self.assertLess(kinds.index("sync_enqueue_probe"), kinds.index("after_sync_enqueue"))
        self.assertEqual([event["sequence"] for event in rebuilt["events"]],
                         list(range(1, len(rebuilt["events"]) + 1)))

    def test_audit_events_arriving_during_retry_are_drained_before_complete(self):
        started = self.start_round()
        original_append = RoundAuditStore.append_event
        failed = threading.Event()

        def fail_first_enqueue(store, event, observed_at, elapsed_seconds):
            if event.kind == "retry_gap" and not failed.is_set():
                failed.set()
                raise OSError("temporary synchronous append failure")
            return original_append(store, event, observed_at, elapsed_seconds)

        with patch.object(RoundAuditStore, "append_event", new=fail_first_enqueue):
            self.monitors[0].callback(MonitorEvent("retry_gap", "first"))
            self.coordinator.stop()
            self.assertTrue(failed.is_set())

        retry_entered = threading.Event()
        release_retry = threading.Event()

        def hold_recovery(store, event, observed_at, elapsed_seconds):
            if event.kind == "retry_gap":
                retry_entered.set()
                release_retry.wait(2)
            return original_append(store, event, observed_at, elapsed_seconds)

        with patch.object(RoundAuditStore, "append_event", new=hold_recovery):
            self.assertTrue(self.coordinator.retry_saves())
            self.assertTrue(retry_entered.wait(2))
            self.monitors[0].callback(MonitorEvent("arrived_during_retry", "must be drained"))
            release_retry.set()

        self.wait_for_retry_to_finish()
        self.assertEqual(self.coordinator.snapshot().save_state, "complete")
        rebuilt = read_round_audit(self.audit_path(started.round_id))
        kinds = [event["kind"] for event in rebuilt["events"]]
        self.assertIn("arrived_during_retry", kinds)
        self.assertEqual(kinds[-1], "save_recovered")
        self.assertEqual([event["sequence"] for event in rebuilt["events"]],
                         list(range(1, len(rebuilt["events"]) + 1)))

    def test_audit_session_path_association_failure_is_retried_through_coordinator(self):
        blocked_path = Path(self.temp.name) / "blocked-session-path"
        blocked_path.write_text("temporary obstruction", encoding="utf-8")

        def factory(callback):
            monitor = AuditFakeMonitor(callback, lambda: self.clock[0])
            monitor.session = SimpleNamespace(path=blocked_path)
            self.monitors.append(monitor)
            return monitor

        started = self.coordinator.start("FCT", factory, run_async=False, capacity=2)
        self.assertEqual(self.coordinator.snapshot().save_state, "failed")
        self.assertTrue(self.coordinator.snapshot().save_errors)

        blocked_path.unlink()
        self.assertTrue(self.coordinator.retry_saves())
        deadline = time.monotonic() + 2
        while self.coordinator.snapshot().retry_in_progress and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertEqual(self.coordinator.snapshot().save_state, "saving")
        self.assertFalse(self.coordinator.snapshot().save_errors)
        self.coordinator.stop()
        self.assertTrue(self.coordinator.flush_audit(timeout=2))
        self.assertEqual(self.coordinator.session_path, blocked_path)
        rebuilt = read_round_audit(blocked_path / "audit.jsonl")
        self.assertEqual(rebuilt["round"]["round_id"], started.round_id)
        self.assertTrue(rebuilt["audit_complete"])
        self.assertFalse(self.coordinator.snapshot().save_errors)
        self.assertEqual(self.coordinator.snapshot().save_state, "complete")

    def test_conflict_resolution_after_manual_stop_and_idle_exit_is_reconstructable(self):
        thread_baseline = threading.active_count()
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

        self.wait_for_threads_to_return_to(thread_baseline)

        completed = self.coordinator.resolve_review(conflict_id, "accept_candidate")
        self.assertEqual(completed.state.value, "STOPPED")
        rebuilt = self.rebuild_current_round(started.round_id)
        resolution = next(event for event in rebuilt["events"]
                          if event["kind"] == "conflict_resolved")
        self.assertEqual(resolution["detail"]["choice"], "accept_candidate")
        self.assertEqual(resolution["localized_message"]["message_id"],
                         "round.conflict.accepted_candidate")
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

    def test_session_attachment_waits_for_the_destination_path_lock(self):
        source_root = Path(self.temp.name) / "audit"
        destination_root = Path(self.temp.name) / "sessions"
        round_id = "shared-round"
        source = RoundAuditStore(source_root, round_id, "FCT", "2026-10-05T12:00:00", 0.0)
        self.assertTrue(source.flush())
        source.append_event(AuditEvent(1, "diagnostic", "source event", None),
                            "2026-10-05T12:00:01", 1.0)
        self.assertTrue(source.flush())

        writer_holds_destination = threading.Event()
        release_destination_writer = threading.Event()
        attach_started = threading.Event()
        attach_finished = threading.Event()
        attach_errors = []
        original_fsync = audit_records.os.fsync
        first_fsync = [True]
        first_fsync_lock = threading.Lock()

        def controlled_fsync(descriptor):
            with first_fsync_lock:
                should_pause = first_fsync[0]
                first_fsync[0] = False
            if should_pause:
                writer_holds_destination.set()
                release_destination_writer.wait(2)
            return original_fsync(descriptor)

        def attach_source():
            attach_started.set()
            try:
                source.attach_session(destination_root / round_id)
            except Exception as error:
                attach_errors.append(error)
            finally:
                attach_finished.set()

        with patch.object(audit_records.os, "fsync", side_effect=controlled_fsync):
            destination_store = RoundAuditStore(
                destination_root, round_id, "FCT", "2026-10-05T12:00:00", 0.0)
            self.assertTrue(writer_holds_destination.wait(1))
            attacher = threading.Thread(target=attach_source)
            attacher.start()
            self.assertTrue(attach_started.wait(1))
            self.assertFalse(attach_finished.wait(0.05),
                             "session attachment bypassed the active destination lock")
            release_destination_writer.set()
            attacher.join(2)
            self.assertFalse(attacher.is_alive())
            self.assertTrue(destination_store.flush())

        self.assertEqual(attach_errors, [])
        self.assertTrue(source.flush())
        rebuilt = read_round_audit(destination_root / round_id / "audit.jsonl")
        self.assertEqual([event["sequence"] for event in rebuilt["events"]], [1])
        self.assertEqual(rebuilt["events"][0]["message"], "source event")

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
        self.assertEqual(conflict["localized_message"]["message_id"],
                         "round.conflict.detected")
        self.assertEqual(resolution["detail"]["choice"], "accept_candidate")
        self.assertEqual(resolution["localized_message"]["message_id"],
                         "round.conflict.accepted_candidate")
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
        event_by_kind = {event["kind"]: event for event in rebuilt["events"]}
        self.assertEqual(event_by_kind["timeout"]["localized_message"]["message_id"],
                         "round.timeout.whole")
        self.assertEqual(event_by_kind["round_alarm_acknowledged"]["localized_message"]["message_id"],
                         "round.alarm.acknowledged")

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
        self.assertTrue(any("稽核紀錄保存失敗" in message for message in completed.save_history))
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
        self.assertTrue(any("稽核紀錄保存失敗" in message for message in completed.save_history))

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

        def slow_event(_message, _detail=None, _timestamp=None):
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
