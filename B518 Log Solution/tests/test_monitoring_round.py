import csv
import gc
import io
import tempfile
import threading
import time
import unittest
import weakref
from unittest.mock import patch
from datetime import datetime, timedelta
from pathlib import Path

from log_monitoring import BtLogMonitor, MonitorEvent, SlotResult
from monitoring_round import RoundCoordinator
from rswmt_monitoring import RsWmtLogMonitor
import audit_records
from audit_records import read_round_audit


class FakeMonitor:
    def __init__(self, callback):
        self.callback = callback
        self.results = {1: SlotResult(1), 2: SlotResult(2)}
        self.started = 0
        self.stopped = 0
        self.collection_stopped = False
        self.finished = False
        self.start_timeout_seconds = 30
        self.test_timeout_seconds = 480
        self.round_timeout_seconds = 7200

    def round_results(self):
        return tuple(self.results.values())

    def timeout_seconds(self, kind):
        return {"start": self.start_timeout_seconds,
                "test": self.test_timeout_seconds,
                "round": self.round_timeout_seconds}[kind]

    def has_pending_review(self):
        return False

    def resolve_review(self, _choice):
        pass

    def update_round_settings(self, _settings):
        pass

    def publish_round_event(self, event):
        self.callback(event)

    def start(self):
        self.started += 1

    def stop_collection(self):
        self.collection_stopped = True

    def stop(self):
        self.stopped += 1
        self.results[2].status = "STOPPED"
        self.finished = True
        self.callback(MonitorEvent("stopped", "stopped"))

    def poll_once(self):
        pass


class DeadlineMonitor:
    """Small source monitor that exposes facts through the shared round API."""
    def __init__(self, callback, monotonic, slots=(1, 2, 3), start=10, test=5, round_limit=100):
        self.callback = callback
        self.monotonic = monotonic
        self.results = {slot: SlotResult(slot) for slot in slots}
        self.start_timeout_seconds = start
        self.test_timeout_seconds = test
        self.round_timeout_seconds = round_limit
        self._test_started_monotonic = {}
        self._pending = []
        self._locked = set()
        self.finished = False
        self.collection_stopped = False
        self.poll_count = 0
        self.review_pending = None

    def start(self):
        pass

    def poll_once(self):
        if self.collection_stopped:
            return
        self.poll_count += 1
        pending, self._pending = self._pending, []
        for slot, status in pending:
            if slot in self._locked:
                continue
            self.results[slot].status = status
            self.callback(MonitorEvent("result", "slot{} {}".format(slot, status), slot, status=status))

    def publish(self, slot, status):
        self._pending.append((slot, status))

    def resolve_review(self, _choice):
        self.review_pending = None

    def round_results(self):
        return tuple(self.results.values())

    def timeout_seconds(self, kind):
        return {"start": self.start_timeout_seconds,
                "test": self.test_timeout_seconds,
                "round": self.round_timeout_seconds}[kind]

    def has_pending_review(self):
        return self.review_pending is not None

    def update_round_settings(self, _settings):
        pass

    def publish_round_event(self, event):
        self.callback(event)

    def set_result(self, slot, status, detail=None, lock_terminal=False):
        if slot in self._locked:
            return
        self.results[slot].status = status
        if lock_terminal:
            self._locked.add(slot)
        self.callback(MonitorEvent("result", "slot{} {}".format(slot, status), slot, status=status,
                                   detail=detail or {}))

    def apply_round_result(self, slot, status, sn="", source="", detail=None, lock_terminal=False):
        self.results[slot].sn = sn or self.results[slot].sn
        self.results[slot].status = status
        self.results[slot].source = source
        self.results[slot].updated_at = "2026-10-02T10:00:00"
        if lock_terminal:
            self._locked.add(slot)
        self.callback(MonitorEvent("result", "slot{} {}".format(slot, status), slot, sn, status,
                                   source, detail or {}))

    def offer_candidate(self, slot, status, sn, source, detail):
        event = MonitorEvent("result_candidate", "candidate", slot, sn, status, source, detail)
        decision = self.callback(event)
        if decision == "accept":
            self.apply_round_result(slot, status, sn, source, detail)
        return decision

    def stop_collection(self):
        self.collection_stopped = True

    def finish(self):
        self.stop_collection()
        self.finished = True

    def stop(self):
        if self.finished:
            return
        self.stop_collection()
        for result in self.results.values():
            if result.status not in {"PASS", "FAIL", "NOTEST", "TIMEOUT", "STOPPED"}:
                self.set_result(result.slot, "STOPPED")
        self.finished = True
        self.callback(MonitorEvent("stopped", "manually stopped"))


class MonitoringRoundTests(unittest.TestCase):
    def test_confirmed_same_round_conflict_is_captured_without_overwriting_original(self):
        elapsed = [0.0]
        holder = {}

        def factory(callback):
            monitor = DeadlineMonitor(callback, lambda: elapsed[0], slots=(1, 2), start=100)
            holder["monitor"] = monitor
            return monitor

        rounds = RoundCoordinator(monotonic=lambda: elapsed[0])
        rounds.start("BT", factory, run_async=False)
        monitor = holder["monitor"]
        evidence = {"round_evidence_id": "rswmt-run-20261002T100000",
                    "source_time": "2026-10-02T10:00:00"}
        monitor.apply_round_result(1, "PASS", "SERIAL000001", "/logs/original.csv", evidence)
        monitor.apply_round_result(2, "TESTING", "SERIAL000002", "/logs/active.csv", evidence)
        monitor.offer_candidate(
            1, "FAIL", "SERIAL000099", "/logs/correction.csv",
            dict(evidence, source_id="correction.csv", source_time="2026-10-02T10:00:03"),
        )

        snapshot = rounds.snapshot()

        self.assertEqual(snapshot.results[0].status, "PASS")
        self.assertEqual(snapshot.results[0].sn, "SERIAL000001")
        self.assertEqual(snapshot.state.value, "AWAITING_REVIEW")
        self.assertFalse(snapshot.result_available)
        self.assertFalse(snapshot.collection_stopped)
        self.assertEqual(snapshot.results[1].status, "TESTING")
        self.assertEqual(len(snapshot.pending_conflicts), 1)
        conflict = snapshot.pending_conflicts[0]
        self.assertEqual(conflict.slot, 1)
        self.assertEqual(conflict.original.sn, "SERIAL000001")
        self.assertEqual(conflict.candidate.sn, "SERIAL000099")
        self.assertEqual(conflict.candidate.source_time, "2026-10-02T10:00:03")

    def test_each_same_slot_candidate_is_resolved_independently_in_user_selected_order(self):
        def run_choices(choices):
            holder = {}

            def factory(callback):
                monitor = DeadlineMonitor(callback, lambda: 0.0, slots=(1,), start=100)
                holder["monitor"] = monitor
                return monitor

            rounds = RoundCoordinator(monotonic=lambda: 0.0)
            rounds.start("BT", factory, run_async=False)
            monitor = holder["monitor"]
            original = {"round_evidence_id": "b482:1:20261002100001:thread=0;config=cfg",
                        "source_id": "original.csv", "source_time": "2026-10-02 10:00:01"}
            monitor.apply_round_result(1, "PASS", "SERIAL000001", "original.csv", original)
            monitor.offer_candidate(1, "FAIL", "SERIAL000002", "candidate-a.csv", dict(
                original, source_id="candidate-a.csv", source_time="2026-10-02 10:00:02"))
            monitor.offer_candidate(1, "FAIL", "SERIAL000003", "candidate-b.csv", dict(
                original, source_id="candidate-b.csv", source_time="2026-10-02 10:00:03"))

            first = rounds.snapshot()
            self.assertEqual(len(first.pending_conflicts), 2)
            conflict_ids = [item.conflict_id for item in first.pending_conflicts]
            after_first = rounds.resolve_review(conflict_ids[choices[0][0]], choices[0][1])
            self.assertEqual(len(after_first.pending_conflicts), 1)
            after_second = rounds.resolve_review(conflict_ids[choices[1][0]], choices[1][1])
            self.assertFalse(after_second.pending_conflicts)
            resolved = [item.event for item in after_second.events if item.event.kind == "conflict_resolved"]
            self.assertEqual([item.detail["conflict_id"] for item in resolved],
                             [conflict_ids[choices[0][0]], conflict_ids[choices[1][0]]])
            return after_second.results[0], [item.detail for item in resolved]

        accepted_then_kept, accepted_then_kept_events = run_choices(
            [(1, "accept_candidate"), (0, "keep_original")],
        )
        self.assertEqual((accepted_then_kept.sn, accepted_then_kept.status), ("SERIAL000001", "PASS"))
        self.assertEqual(accepted_then_kept_events[-1]["chosen_sn"], "SERIAL000001")
        self.assertEqual(accepted_then_kept_events[-1]["result_after_sn"], "SERIAL000001")

        kept_then_accepted, kept_then_accepted_events = run_choices(
            [(0, "keep_original"), (1, "accept_candidate")],
        )
        self.assertEqual((kept_then_accepted.sn, kept_then_accepted.status), ("SERIAL000003", "FAIL"))
        self.assertEqual(kept_then_accepted_events[-1]["chosen_sn"], "SERIAL000003")
        self.assertEqual(kept_then_accepted_events[-1]["result_after_sn"], "SERIAL000003")

    def test_unconfirmed_round_evidence_fails_slot_without_an_adoption_choice(self):
        holder = {}

        def factory(callback):
            monitor = DeadlineMonitor(callback, lambda: 0.0, slots=(1,), start=100)
            holder["monitor"] = monitor
            return monitor

        rounds = RoundCoordinator(monotonic=lambda: 0.0)
        rounds.start("BT", factory, run_async=False)
        monitor = holder["monitor"]
        monitor.apply_round_result(1, "PASS", "SERIAL000001", "first.csv", {
            "source_id": "first.csv", "source_time": "unknown",
        })
        monitor.offer_candidate(1, "FAIL", "", "other.csv", {
            "source_id": "other.csv", "source_time": "unknown",
        })

        snapshot = rounds.snapshot()
        self.assertFalse(snapshot.pending_conflicts)
        self.assertEqual(snapshot.results[0].sn, "SERIAL000001")
        self.assertEqual(snapshot.results[0].status, "FAIL")
        rejected = [event.event for event in snapshot.events
                    if event.event.kind == "unknown_round_candidate_rejected"]
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0].detail["candidate_source_time"], "unknown")

    def test_first_final_without_round_link_fails_and_audits_candidate_and_operation_time(self):
        fixed_time = datetime(2026, 10, 6, 12, 34, 56)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            holder = {}

            def factory(callback):
                monitor = DeadlineMonitor(callback, lambda: 0.0, slots=(1,), start=100)
                holder["monitor"] = monitor
                return monitor

            rounds = RoundCoordinator(audit_root=root / "audit", wall_clock=lambda: fixed_time)
            rounds.start("BT", factory, run_async=False, capacity=1,
                         audit_context={"project": "B518", "machine": "BT", "platform": "test"})
            holder["monitor"].offer_candidate(1, "PASS", "SERIAL000001", "first.csv", {
                "source_id": "first.csv", "source_time": "2026-10-06T12:30:00",
            })
            snapshot = rounds.poll_once()

            self.assertEqual(snapshot.results[0].status, "FAIL")
            self.assertEqual(snapshot.results[0].sn, "")
            self.assertTrue(snapshot.result_available)
            self.assertFalse(snapshot.pending_conflicts)
            rejected = next(item.event for item in snapshot.events
                            if item.event.kind == "unknown_round_candidate_rejected")
            self.assertEqual(rejected.detail["operation"], "fail_unconfirmed_candidate")
            self.assertEqual(rejected.detail["candidate_sn"], "SERIAL000001")
            self.assertEqual(rejected.detail["candidate_status"], "PASS")
            self.assertEqual(rejected.detail["candidate_source_time"], "2026-10-06T12:30:00")
            self.assertEqual(rejected.detail["operation_at"], "2026-10-06T12:34:56")
            self.assertNotIn("reason", rejected.detail)

            self.assertTrue(rounds.flush_audit())
            audit_path = next((root / "audit").rglob("audit.jsonl"))
            audit = read_round_audit(audit_path)
            stored = next(item for item in audit["events"]
                          if item["kind"] == "unknown_round_candidate_rejected")
            self.assertEqual(stored["operation_at"], "2026-10-06T12:34:56")
            self.assertEqual(stored["source_time"], "2026-10-06T12:30:00")
            self.assertEqual(stored["detail"]["candidate_status"], "PASS")

    def test_unlinked_replacement_candidate_fails_slot_without_adopting_candidate(self):
        holder = {}

        def factory(callback):
            monitor = DeadlineMonitor(callback, lambda: 0.0, slots=(1,), start=100)
            holder["monitor"] = monitor
            return monitor

        rounds = RoundCoordinator(monotonic=lambda: 0.0)
        rounds.start("BT", factory, run_async=False)
        monitor = holder["monitor"]
        monitor.apply_round_result(1, "PASS", "ORIGINAL0001", "original.csv", {
            "source_id": "original.csv", "source_time": "2026-10-06T12:00:00",
            "round_evidence_id": "b482:1:run-a",
        })
        monitor.offer_candidate(1, "PASS", "CANDIDATE001", "candidate.csv", {
            "source_id": "candidate.csv", "source_time": "2026-10-06T12:01:00",
        })
        snapshot = rounds.poll_once()

        self.assertEqual(snapshot.results[0].status, "FAIL")
        self.assertEqual(snapshot.results[0].sn, "ORIGINAL0001")
        self.assertTrue(snapshot.result_available)
        self.assertFalse(snapshot.pending_conflicts)
        rejected = next(item.event for item in snapshot.events
                        if item.event.kind == "unknown_round_candidate_rejected")
        self.assertEqual(rejected.detail["original_sn"], "ORIGINAL0001")
        self.assertEqual(rejected.detail["candidate_sn"], "CANDIDATE001")
        self.assertEqual(rejected.detail["candidate_source_time"], "2026-10-06T12:01:00")

    def test_round_link_without_source_test_time_is_insufficient_and_fails_slot(self):
        holder = {}

        def factory(callback):
            monitor = DeadlineMonitor(callback, lambda: 0.0, slots=(1,), start=100)
            holder["monitor"] = monitor
            return monitor

        rounds = RoundCoordinator(monotonic=lambda: 0.0)
        rounds.start("BT", factory, run_async=False)
        monitor = holder["monitor"]
        round_evidence_id = "b482:1:run-a"
        monitor.apply_round_result(1, "PASS", "SERIAL000001", "original.csv", {
            "source_id": "original.csv", "source_time": "2026-10-06T12:00:00",
            "round_evidence_id": round_evidence_id,
        })
        monitor.offer_candidate(1, "FAIL", "SERIAL000001", "candidate.csv", {
            "source_id": "candidate.csv", "source_time": "2026-10-06",
            "round_evidence_id": round_evidence_id,
        })
        snapshot = rounds.poll_once()

        self.assertEqual(snapshot.results[0].status, "FAIL")
        self.assertTrue(snapshot.result_available)
        self.assertFalse(snapshot.pending_conflicts)
        rejected = next(item.event for item in snapshot.events
                        if item.event.kind == "unknown_round_candidate_rejected")
        self.assertEqual(rejected.detail["candidate_source_time"], "2026-10-06")

    def test_same_result_from_another_path_is_traceable_without_a_new_conflict(self):
        holder = {}

        def factory(callback):
            monitor = DeadlineMonitor(callback, lambda: 0.0, slots=(1,), start=100)
            holder["monitor"] = monitor
            return monitor

        rounds = RoundCoordinator(monotonic=lambda: 0.0)
        rounds.start("BT", factory, run_async=False)
        monitor = holder["monitor"]
        evidence = {"round_evidence_id": "rswmt:1:2026-10-02T10:00:00",
                    "source_id": "first.csv", "source_time": "2026-10-02T10:00:01"}
        monitor.apply_round_result(1, "PASS", "SERIAL000001", "first.csv", evidence)
        monitor.offer_candidate(1, "PASS", "SERIAL000001", "copy.csv", dict(
            evidence, source_id="copy.csv"))

        snapshot = rounds.snapshot()
        self.assertFalse(snapshot.pending_conflicts)
        duplicates = [event.event for event in snapshot.events
                      if event.event.kind == "duplicate_source"]
        self.assertEqual(len(duplicates), 1)
        self.assertEqual(duplicates[0].detail["source_id"], "copy.csv")

    def test_repeated_conflicting_candidate_is_traced_without_a_second_review_item(self):
        holder = {}

        def factory(callback):
            monitor = DeadlineMonitor(callback, lambda: 0.0, slots=(1,), start=100)
            holder["monitor"] = monitor
            return monitor

        rounds = RoundCoordinator(monotonic=lambda: 0.0)
        rounds.start("BT", factory, run_async=False)
        monitor = holder["monitor"]
        evidence = {"round_evidence_id": "b482:1:20261002100001:thread=0;config=cfg",
                    "source_id": "candidate-a.csv", "source_time": "2026-10-02T10:00:01"}
        monitor.apply_round_result(1, "PASS", "SERIAL000001", "original.csv", evidence)
        monitor.offer_candidate(1, "FAIL", "SERIAL000002", "candidate-a.csv", evidence)
        monitor.offer_candidate(1, "FAIL", "SERIAL000002", "candidate-copy.csv", dict(
            evidence, source_id="candidate-copy.csv"))

        snapshot = rounds.snapshot()
        self.assertEqual(len(snapshot.pending_conflicts), 1)
        duplicate = next(item.event for item in snapshot.events
                         if item.event.kind == "duplicate_source")
        self.assertEqual(duplicate.detail["source_id"], "candidate-copy.csv")

    def test_conflict_resolution_does_not_release_round_deadline_results(self):
        elapsed = [0.0]
        holder = {}

        def factory(callback):
            monitor = DeadlineMonitor(callback, lambda: elapsed[0], slots=(1, 2), round_limit=5)
            holder["monitor"] = monitor
            return monitor

        coordinator = RoundCoordinator(monotonic=lambda: elapsed[0])
        coordinator.start("FCT", factory, run_async=False)
        evidence = {"round_evidence_id": "atlas:1:SERIAL000001",
                    "source_time": "2026-10-06T12:00:00"}
        holder["monitor"].apply_round_result(1, "PASS", "SERIAL000001", "active.csv", evidence)
        holder["monitor"].offer_candidate(
            1, "FAIL", "SERIAL000001", "final.csv", dict(evidence, source_id="final.csv"),
        )
        coordinator.poll_once()
        elapsed[0] = 5.0
        expired = coordinator.poll_once()

        self.assertEqual(expired.state.value, "AWAITING_REVIEW")
        self.assertEqual(expired.completion_reason, "round_deadline")
        self.assertFalse(expired.result_available)
        released = coordinator.resolve_review(expired.pending_conflicts[0].conflict_id, "keep_original")
        self.assertEqual(released.state.value, "AWAITING_REVIEW")
        self.assertEqual(released.completion_reason, "round_deadline")
        self.assertFalse(released.result_available)
        self.assertFalse(holder["monitor"].finished)

        alarm_id = released.round_alarm.alarm_id
        stale = coordinator.acknowledge_round_alarm("old-round", alarm_id)
        self.assertFalse(stale.round_alarm.acknowledged_at)
        self.assertEqual(stale.state.value, "AWAITING_REVIEW")
        self.assertEqual(stale.events[-1].event.kind, "round_alarm_acknowledgement_ignored")

        acknowledged = coordinator.acknowledge_round_alarm(released.round_id, alarm_id)
        self.assertTrue(acknowledged.result_available)
        self.assertTrue(holder["monitor"].finished)

    def test_round_deadline_alarm_is_created_once_and_acknowledgement_releases_results(self):
        elapsed = [0.0]
        holder = {}

        def factory(callback):
            monitor = DeadlineMonitor(callback, lambda: elapsed[0], slots=(1, 2), round_limit=5)
            holder["monitor"] = monitor
            return monitor

        coordinator = RoundCoordinator(monotonic=lambda: elapsed[0])
        started = coordinator.start("FCT", factory, run_async=False)
        holder["monitor"].apply_round_result(1, "PASS", "SERIAL000001", "final.csv")
        elapsed[0] = 5.0

        expired = coordinator.poll_once()
        alarm = expired.round_alarm
        self.assertEqual(expired.state.value, "AWAITING_REVIEW")
        self.assertIsNotNone(alarm)
        self.assertEqual(alarm.round_id, started.round_id)
        self.assertFalse(alarm.acknowledged_at)
        self.assertEqual(expired.results[0].status, "PASS")
        self.assertEqual(expired.results[1].status, "NOTEST")
        self.assertFalse(expired.result_available)
        alarm_event = next(event.event for event in expired.events
                           if event.event.kind == "timeout" and
                           event.event.detail.get("kind") == "round")
        collection_event = next(event.event for event in expired.events
                                if event.event.kind == "collection_stopped")
        self.assertEqual(alarm_event.detail["alarm_id"], alarm.alarm_id)
        self.assertEqual(alarm_event.detail["alarm_created_at"], alarm.created_at)
        self.assertEqual(collection_event.detail["reason"], "round_deadline")
        self.assertTrue(collection_event.detail["collection_stopped_at"])

        repeated = coordinator.poll_once()
        self.assertEqual(repeated.round_alarm.alarm_id, alarm.alarm_id)
        self.assertEqual(len([event for event in repeated.events
                              if event.event.kind == "timeout" and
                              event.event.detail.get("kind") == "round"]), 1)

        released = coordinator.acknowledge_round_alarm(started.round_id, alarm.alarm_id)
        self.assertEqual(released.state.value, "COMPLETED")
        self.assertTrue(released.result_available)
        self.assertTrue(released.round_alarm.acknowledged_at)
        acknowledged = next(event.event for event in released.events
                            if event.event.kind == "round_alarm_acknowledged")
        finished = next(event.event for event in released.events
                        if event.event.kind == "finished")
        self.assertEqual(acknowledged.detail["alarm_id"], alarm.alarm_id)
        self.assertEqual(acknowledged.detail["acknowledged_at"], released.round_alarm.acknowledged_at)
        self.assertTrue(finished.detail["results_released_at"])
        self.assertEqual(len([event for event in released.events
                              if event.event.kind == "finished"]), 1)

        duplicate = coordinator.acknowledge_round_alarm(started.round_id, alarm.alarm_id)
        self.assertEqual(duplicate.state.value, "COMPLETED")
        self.assertEqual(len([event for event in duplicate.events
                              if event.event.kind == "round_alarm_acknowledgement_ignored"]), 1)

    def test_round_deadline_preserves_terminals_and_times_out_started_incomplete_positions(self):
        elapsed = [0.0]
        holder = {}

        def factory(callback):
            monitor = DeadlineMonitor(callback, lambda: elapsed[0], slots=(1, 2, 3, 4), round_limit=5)
            holder["monitor"] = monitor
            return monitor

        coordinator = RoundCoordinator(monotonic=lambda: elapsed[0])
        coordinator.start("FCT", factory, run_async=False)
        holder["monitor"].apply_round_result(1, "PASS", "SERIAL000001", "slot1.csv")
        holder["monitor"].apply_round_result(2, "FAIL", "SERIAL000002", "slot2.csv")
        holder["monitor"].apply_round_result(3, "TESTING", "SERIAL000003", "slot3.csv")
        holder["monitor"].apply_round_result(4, "COMPLETING", "SERIAL000004", "slot4.csv")
        elapsed[0] = 5.0

        expired = coordinator.poll_once()

        self.assertEqual([item.status for item in expired.results], ["PASS", "FAIL", "TIMEOUT", "TIMEOUT"])
        deadline_events = [event.event for event in expired.events if event.event.kind == "timeout"]
        self.assertEqual([(event.slot, event.status, event.detail["reason"])
                          for event in deadline_events if event.slot is not None], [
                              (3, "TIMEOUT", "round_deadline"),
                              (4, "TIMEOUT", "round_deadline"),
                          ])
        self.assertEqual(len([event for event in deadline_events
                              if event.detail.get("kind") == "round"]), 1)

    def test_round_deadline_does_not_alarm_when_all_positions_are_already_terminal(self):
        elapsed = [0.0]
        holder = {}

        def factory(callback):
            monitor = DeadlineMonitor(callback, lambda: elapsed[0], slots=(1, 2), round_limit=5)
            holder["monitor"] = monitor
            return monitor

        coordinator = RoundCoordinator(monotonic=lambda: elapsed[0])
        coordinator.start("DFU", factory, run_async=False)
        holder["monitor"].apply_round_result(1, "PASS", "SERIAL000001", "slot1.csv")
        holder["monitor"].apply_round_result(2, "FAIL", "SERIAL000002", "slot2.csv")
        elapsed[0] = 5.0

        completed = coordinator.poll_once()

        self.assertEqual(completed.state.value, "COMPLETED")
        self.assertTrue(completed.result_available)
        self.assertIsNone(completed.round_alarm)
        self.assertFalse([event for event in completed.events
                          if event.event.kind == "timeout" and
                          event.event.detail.get("kind") == "round"])

    def test_round_deadline_is_not_a_confirmation_countdown_after_collection_stops(self):
        elapsed = [0.0]
        holder = {}

        def factory(callback):
            monitor = DeadlineMonitor(callback, lambda: elapsed[0], slots=(1,), round_limit=5)
            holder["monitor"] = monitor
            return monitor

        coordinator = RoundCoordinator(monotonic=lambda: elapsed[0])
        coordinator.start("FCT", factory, run_async=False)
        evidence = {"round_evidence_id": "atlas:1:SERIAL000001",
                    "source_time": "2026-10-06T12:00:00"}
        holder["monitor"].apply_round_result(1, "PASS", "SERIAL000001", "active.csv", evidence)
        holder["monitor"].offer_candidate(
            1, "FAIL", "SERIAL000001", "final.csv", dict(evidence, source_id="final.csv"),
        )
        elapsed[0] = 5.0

        waiting_for_choice = coordinator.poll_once()

        self.assertTrue(waiting_for_choice.collection_stopped)
        self.assertEqual(waiting_for_choice.state.value, "AWAITING_REVIEW")
        self.assertFalse(waiting_for_choice.result_available)
        self.assertIsNone(waiting_for_choice.round_alarm)
        self.assertFalse([event for event in waiting_for_choice.events
                          if event.event.kind == "timeout" and
                          event.event.detail.get("kind") == "round"])

    def test_round_alarm_and_conflict_are_independent_release_blockers(self):
        elapsed = [0.0]
        holder = {}

        def factory(callback):
            monitor = DeadlineMonitor(callback, lambda: elapsed[0], slots=(1, 2), round_limit=5)
            holder["monitor"] = monitor
            return monitor

        coordinator = RoundCoordinator(monotonic=lambda: elapsed[0])
        started = coordinator.start("FCT", factory, run_async=False)
        evidence = {"round_evidence_id": "atlas:1:SERIAL000001",
                    "source_time": "2026-10-06T12:00:00"}
        holder["monitor"].apply_round_result(1, "PASS", "SERIAL000001", "active.csv", evidence)
        holder["monitor"].apply_round_result(2, "TESTING", "SERIAL000002", "active.csv")
        holder["monitor"].offer_candidate(
            1, "FAIL", "SERIAL000001", "final.csv", dict(evidence, source_id="final.csv"),
        )
        elapsed[0] = 5.0
        expired = coordinator.poll_once()
        conflict_id = expired.pending_conflicts[0].conflict_id
        alarm_id = expired.round_alarm.alarm_id

        alarm_acknowledged = coordinator.acknowledge_round_alarm(started.round_id, alarm_id)
        self.assertFalse(alarm_acknowledged.result_available)
        self.assertEqual(len(alarm_acknowledged.pending_conflicts), 1)
        self.assertEqual(alarm_acknowledged.state.value, "AWAITING_REVIEW")

        released = coordinator.resolve_review(conflict_id, "keep_original")
        self.assertTrue(released.result_available)
        self.assertEqual(released.state.value, "COMPLETED")
        self.assertEqual(released.completion_reason, "round_deadline")

    def test_source_preparation_time_counts_toward_round_deadline_without_blocking_ui_caller(self):
        elapsed = [0.0]
        entered = threading.Event()
        release = threading.Event()
        monitor_created = threading.Event()
        deadline_seen = threading.Event()
        holder = {}

        def factory(callback):
            entered.set()
            release.wait(3)
            monitor = DeadlineMonitor(callback, lambda: elapsed[0], slots=(1,), round_limit=5)
            holder["monitor"] = monitor
            monitor_created.set()
            return monitor

        def on_event(event):
            if event.event.kind == "timeout" and event.event.detail.get("kind") == "round":
                deadline_seen.set()

        coordinator = RoundCoordinator(on_event, monotonic=lambda: elapsed[0])
        started = coordinator.start("FCT", factory, run_async=True,
                                    round_timeout_seconds=5, capacity=1)
        self.assertTrue(entered.wait(1))
        elapsed[0] = 5.0
        expired_during_preparation = coordinator.poll_once()
        self.assertIsNotNone(expired_during_preparation.round_alarm)
        self.assertTrue(expired_during_preparation.collection_stopped)
        self.assertFalse(expired_during_preparation.round_alarm_ready)
        self.assertFalse(expired_during_preparation.result_available)
        self.assertEqual(expired_during_preparation.results[0].status, "NOTEST")
        self.assertTrue(deadline_seen.wait(1))
        self.assertEqual(sum(event.event.kind == "timeout" and
                             event.event.detail.get("kind") == "round"
                             for event in expired_during_preparation.events), 1)
        self.assertFalse(release.is_set())
        ignored = coordinator.acknowledge_round_alarm(
            started.round_id, expired_during_preparation.round_alarm.alarm_id)
        self.assertFalse(ignored.round_alarm.acknowledged_at)
        self.assertEqual(ignored.events[-1].event.detail.get("reason"), "source_preparation_pending")
        release.set()
        self.assertTrue(monitor_created.wait(3))
        self.assertTrue(deadline_seen.wait(3))

        expired = coordinator.snapshot()
        self.assertEqual(expired.round_id, started.round_id)
        self.assertTrue(expired.collection_stopped)
        self.assertEqual(expired.results[0].status, "NOTEST")
        self.assertFalse(expired.result_available)
        self.assertEqual(holder["monitor"].poll_count, 0)

    def test_acknowledgement_waits_for_delayed_preparation_adjudication_and_stop(self):
        elapsed = [0.0]
        factory_entered = threading.Event()
        factory_release = threading.Event()
        adjudication_entered = threading.Event()
        adjudication_release = threading.Event()
        ack_started = threading.Event()
        ack_finished = threading.Event()
        holder = {}
        acknowledgement = {}

        class BlockingAdjudicationMonitor(DeadlineMonitor):
            def apply_round_result(self, slot, status, sn="", source="", detail=None, lock_terminal=False):
                adjudication_entered.set()
                adjudication_release.wait(3)
                super().apply_round_result(slot, status, sn, source, detail, lock_terminal)

        def factory(callback):
            factory_entered.set()
            factory_release.wait(3)
            holder["monitor"] = BlockingAdjudicationMonitor(
                callback, lambda: elapsed[0], slots=(1,), round_limit=5)
            return holder["monitor"]

        coordinator = RoundCoordinator(monotonic=lambda: elapsed[0])
        started = coordinator.start("FCT", factory, run_async=True,
                                    round_timeout_seconds=5, capacity=1)
        self.assertTrue(factory_entered.wait(1))
        elapsed[0] = 5.0
        pending = coordinator.poll_once()
        alarm_id = pending.round_alarm.alarm_id
        factory_release.set()
        self.assertTrue(adjudication_entered.wait(2))

        def acknowledge():
            ack_started.set()
            acknowledgement["snapshot"] = coordinator.acknowledge_round_alarm(started.round_id, alarm_id)
            ack_finished.set()

        ack_thread = threading.Thread(target=acknowledge)
        ack_thread.start()
        self.assertTrue(ack_started.wait(1))
        self.assertFalse(ack_finished.wait(0.1))
        during = coordinator.snapshot()
        self.assertFalse(during.round_alarm_ready)
        self.assertFalse(during.result_available)
        self.assertFalse(any(event.event.kind == "collection_stopped" for event in during.events))

        adjudication_release.set()
        self.assertTrue(ack_finished.wait(2))
        ack_thread.join(1)
        released = coordinator.snapshot()
        self.assertTrue(released.result_available)
        self.assertEqual(released.results[0].status, "NOTEST")
        kinds = [event.event.kind for event in released.events]
        self.assertLess(kinds.index("collection_stopped"), kinds.index("round_alarm_acknowledged"))
        self.assertLess(kinds.index("round_alarm_acknowledged"), kinds.index("finished"))

    def test_preparation_alarm_is_persisted_across_monitor_handoff(self):
        elapsed = [0.0]
        settings_entered = threading.Event()
        settings_release = threading.Event()
        holder = {}

        class HandoffMonitor(DeadlineMonitor):
            def __init__(self, callback):
                super().__init__(callback, lambda: elapsed[0], slots=(1,), round_limit=5)
                self.persisted_events = []
                self.start_count = 0

            def update_round_settings(self, _settings):
                settings_entered.set()
                settings_release.wait(3)

            def publish_round_event(self, event):
                self.persisted_events.append(event)
                super().publish_round_event(event)

            def start(self):
                self.start_count += 1

        def factory(callback):
            holder["monitor"] = HandoffMonitor(callback)
            return holder["monitor"]

        coordinator = RoundCoordinator(monotonic=lambda: elapsed[0])
        started = coordinator.start("FCT", factory, run_async=True,
                                    round_timeout_seconds=5, capacity=1)
        self.assertTrue(settings_entered.wait(1))
        elapsed[0] = 5.0
        expired = coordinator.poll_once()
        self.assertIsNotNone(expired.round_alarm)
        self.assertFalse(expired.round_alarm_ready)
        self.assertEqual(expired.results[0].status, "NOTEST")
        settings_release.set()
        for _ in range(200):
            snapshot = coordinator.snapshot()
            if snapshot.round_alarm_ready:
                break
            time.sleep(0.01)

        monitor = holder["monitor"]
        self.assertTrue(snapshot.round_alarm_ready)
        self.assertTrue(monitor.collection_stopped)
        self.assertEqual(monitor.start_count, 0)
        persisted_round_timeouts = [event for event in monitor.persisted_events
                                    if event.kind == "timeout" and event.detail.get("kind") == "round"]
        self.assertEqual(len(persisted_round_timeouts), 1)
        self.assertEqual(snapshot.round_id, started.round_id)

    def test_round_event_callback_does_not_hold_round_lock_against_repeated_start(self):
        callback_finished = threading.Event()
        callback_errors = []
        coordinator_holder = {}
        monitor_holder = {}

        def factory(callback):
            monitor_holder["monitor"] = DeadlineMonitor(callback, time.monotonic, slots=(1,))
            return monitor_holder["monitor"]

        def on_event(event):
            if event.event.kind != "round_alarm_acknowledgement_ignored":
                return

            def repeated_start():
                try:
                    coordinator_holder["coordinator"].start(
                        "FCT", factory, run_async=False, round_timeout_seconds=30, capacity=1)
                    callback_finished.set()
                except Exception as error:
                    callback_errors.append(error)

            thread = threading.Thread(target=repeated_start)
            thread.start()
            if not callback_finished.wait(1):
                callback_errors.append(AssertionError("Repeated start deadlocked against event delivery."))

        coordinator = RoundCoordinator(on_event=on_event)
        coordinator_holder["coordinator"] = coordinator
        started = coordinator.start("FCT", factory, run_async=False,
                                    round_timeout_seconds=30, capacity=1)
        ignored = coordinator.acknowledge_round_alarm(started.round_id, "stale-alarm")
        self.assertEqual(ignored.events[-1].event.kind, "round_alarm_acknowledgement_ignored")
        self.assertTrue(callback_finished.is_set())
        self.assertFalse(callback_errors)
        self.assertEqual(coordinator.snapshot().round_id, started.round_id)

    def test_manual_stop_during_source_preparation_cannot_resume_when_factory_returns(self):
        entered = threading.Event()
        release = threading.Event()
        returned = threading.Event()
        holder = {}

        def factory(callback):
            entered.set()
            release.wait(3)
            holder["monitor"] = DeadlineMonitor(callback, time.monotonic, slots=(1,))
            returned.set()
            return holder["monitor"]

        coordinator = RoundCoordinator()
        started = coordinator.start("FCT", factory, run_async=True,
                                    round_timeout_seconds=30, capacity=1)
        self.assertTrue(entered.wait(1))
        stopped = coordinator.stop()
        self.assertEqual(stopped.state.value, "STOPPED")
        self.assertFalse(stopped.result_available)
        release.set()
        self.assertTrue(returned.wait(3))
        for _ in range(100):
            if not coordinator.snapshot().source_preparation_pending:
                break
            time.sleep(0.01)
        snapshot = coordinator.snapshot()
        self.assertEqual(snapshot.round_id, started.round_id)
        self.assertEqual(snapshot.state.value, "STOPPED")
        self.assertFalse(snapshot.result_available)
        self.assertEqual(holder["monitor"].poll_count, 0)

    def test_pending_bt_candidate_can_be_resolved_after_collection_stops(self):
        elapsed = [0.0]
        now = datetime(2026, 10, 2, 10, 0, 0)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "TestData"
            caseinfo = Path(temporary) / "CaseInfo"
            caseinfo.mkdir()
            caseinfo_path = caseinfo / "thread2CaseInfo_2026-10-02.txt"
            caseinfo_path.write_text("", encoding="utf-8")
            sessions = Path(temporary) / "sessions"
            coordinator = RoundCoordinator(monotonic=lambda: elapsed[0])
            holder = {}

            def factory(callback):
                monitor = BtLogMonitor(
                    root, (1, 2), caseinfo_root=caseinfo, callback=callback, now=lambda: now,
                    monotonic=lambda: elapsed[0], start_timeout_seconds=60,
                    test_timeout_seconds=100, round_timeout_seconds=500,
                    session_root=sessions,
                )
                holder["monitor"] = monitor
                return monitor

            def write_result(thread, serial, stamp):
                path = root / "2026-10-02" / "PASSED" / (
                    "[Thread{}][cfg][{}][PASSED][{}].csv".format(thread, serial, stamp)
                )
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.DictWriter(handle, fieldnames=[
                        "SerialNumber", "Unit Number", "Test Pass/Fail Status", "StartTime", "EndTime",
                    ])
                    writer.writeheader()
                    writer.writerow({"SerialNumber": serial, "Unit Number": "0",
                                     "Test Pass/Fail Status": "PASSED", "StartTime": "x", "EndTime": "y"})
                return path

            coordinator.start("BT", factory, run_async=False)
            monitor = holder["monitor"]
            caseinfo_path.write_text(
                "2026-10-02 10:00:00:000, 1,InitResource,SNRead,--,SNRead,"
                "HK5HUX6STQ800003YV,NA,NA,NA,Passed,1.00\r\n",
                encoding="utf-8",
            )
            first = write_result(0, "HK5HUX6STQ900003YV", "20261002100001")
            coordinator.poll_once()
            elapsed[0] = 5.1
            coordinator.poll_once()
            self.assertEqual([result.status for result in coordinator.snapshot().results],
                             ["PASS", "TESTING"])

            second = write_result(0, "HK5HUX6STQ000003YV", "20261002100001")
            elapsed[0] = 6.0
            coordinator.poll_once()
            elapsed[0] = 11.1
            waiting = coordinator.poll_once()
            self.assertEqual(waiting.state.value, "AWAITING_REVIEW")
            self.assertFalse(waiting.result_available)
            self.assertEqual([result.status for result in waiting.results], ["PASS", "TESTING"])
            self.assertTrue(coordinator.flush_session())
            session_log = coordinator.session_path / "events.log"
            captured_log = session_log.read_text(encoding="utf-8")
            self.assertIn("conflict_id", captured_log)
            self.assertIn("candidate_source_time", captured_log)
            session_metadata = (coordinator.session_path / "session.json").read_text(encoding="utf-8")
            self.assertIn(str(second), session_metadata)

            slot2 = write_result(1, "HK5HUX6STQ800003YV", "20261002100001")
            elapsed[0] = 12.0
            coordinator.poll_once()
            elapsed[0] = 17.1
            waiting = coordinator.poll_once()
            self.assertTrue(waiting.collection_stopped)
            self.assertFalse(waiting.result_available)
            self.assertEqual(len(waiting.pending_conflicts), 1)
            conflict_id = waiting.pending_conflicts[0].conflict_id

            released = coordinator.resolve_review(conflict_id, "accept_candidate")
            self.assertEqual(released.state.value, "COMPLETED")
            self.assertTrue(released.result_available)
            self.assertEqual(released.results[0].sn, "HK5HUX6STQ000003YV")
            self.assertTrue(coordinator.flush_session())
            resolved_log = session_log.read_text(encoding="utf-8")
            self.assertIn("accept_candidate", resolved_log)
            self.assertIn("selected_at", resolved_log)
            self.assertTrue(first.exists())
            self.assertTrue(slot2.exists())
            third = write_result(0, "HK5HUX6STQ100003YV", "20261002100002")
            coordinator.poll_once()
            self.assertEqual(coordinator.snapshot().results[0].sn, "HK5HUX6STQ000003YV")
            self.assertTrue(third.exists())

    def test_terminal_bt_slot_retains_caseinfo_identity_as_unconfirmed_evidence(self):
        elapsed = [0.0]
        now = datetime(2026, 10, 2, 10, 0, 0)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "TestData"
            caseinfo = Path(temporary) / "CaseInfo"
            caseinfo.mkdir()
            caseinfo_path = caseinfo / "thread1CaseInfo_2026-10-02.txt"
            caseinfo_path.write_text("", encoding="utf-8")
            coordinator = RoundCoordinator(monotonic=lambda: elapsed[0])

            def factory(callback):
                return BtLogMonitor(
                    root, (1, 2), caseinfo_root=caseinfo, callback=callback, now=lambda: now,
                    monotonic=lambda: elapsed[0], start_timeout_seconds=60,
                    test_timeout_seconds=100, round_timeout_seconds=500,
                    session_root=Path(temporary) / "sessions",
                )

            coordinator.start("BT", factory, run_async=False)
            result_path = root / "2026-10-02" / "PASSED" / (
                "[Thread0][cfg][HK5HUX6STQ800003YV][PASSED][20261002100001].csv"
            )
            result_path.parent.mkdir(parents=True, exist_ok=True)
            with result_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=[
                    "SerialNumber", "Unit Number", "Test Pass/Fail Status", "StartTime", "EndTime",
                ])
                writer.writeheader()
                writer.writerow({"SerialNumber": "HK5HUX6STQ800003YV", "Unit Number": "0",
                                 "Test Pass/Fail Status": "PASSED", "StartTime": "x", "EndTime": "y"})
            coordinator.poll_once()
            elapsed[0] = 5.1
            active = coordinator.poll_once()
            self.assertEqual(active.results[0].status, "PASS")
            self.assertFalse(active.collection_stopped)

            caseinfo_path.write_text(
                "2026-10-02 10:00:02:000, 1,InitResource,SNRead,--,SNRead,"
                "HK5HUX6STQ900003YV,NA,NA,NA,Passed,1.00\r\n",
                encoding="utf-8",
            )
            observed = coordinator.poll_once()

            self.assertEqual(observed.results[0].sn, "HK5HUX6STQ800003YV")
            self.assertEqual(observed.results[0].status, "FAIL")
            self.assertEqual(observed.results[0].sn, "HK5HUX6STQ800003YV")
            self.assertFalse(observed.pending_conflicts)
            rejected = [item.event for item in observed.events
                        if item.event.kind == "unknown_round_candidate_rejected"]
            self.assertEqual(len(rejected), 1)
            self.assertEqual(rejected[0].detail["candidate_sn"], "HK5HUX6STQ900003YV")
            self.assertEqual(rejected[0].detail["candidate_source_id"], caseinfo_path.name)
            self.assertEqual(rejected[0].detail["candidate_source_time"], "2026-10-02 10:00:02.000")
            self.assertNotIn("reason", rejected[0].detail)
            self.assertTrue(coordinator.flush_session())

    def test_shared_start_deadline_marks_only_unobserved_slots_notest_and_completes_empty_round(self):
        elapsed = [0.0]
        monitors = []

        def create(callback):
            monitor = DeadlineMonitor(callback, lambda: elapsed[0])
            monitors.append(monitor)
            return monitor

        rounds = RoundCoordinator(monotonic=lambda: elapsed[0])
        rounds.start("FCT", create, run_async=False)
        elapsed[0] = 10.0
        snapshot = rounds.poll_once()

        self.assertEqual([result.status for result in snapshot.results], ["NOTEST"] * 3)
        self.assertEqual(snapshot.state, "COMPLETED")
        self.assertTrue(snapshot.result_available)
        notest_events = [item.event for item in snapshot.events
                         if item.event.kind == "timeout" and item.event.status == "NOTEST"]
        self.assertEqual(len(notest_events), 3)
        self.assertTrue(all(event.detail.get("reason") == "start_deadline_no_activity" for event in notest_events))
        self.assertTrue(all(event.detail.get("deadline_seconds") == "10" for event in notest_events))

    def test_shared_start_deadline_preserves_active_and_final_slots_while_others_wait(self):
        elapsed = [0.0]
        monitors = []

        def create(callback):
            monitor = DeadlineMonitor(callback, lambda: elapsed[0])
            monitors.append(monitor)
            return monitor

        rounds = RoundCoordinator(monotonic=lambda: elapsed[0])
        rounds.start("FCT", create, run_async=False)
        monitors[0].publish(1, "TESTING")
        monitors[0].publish(2, "PASS")
        elapsed[0] = 9.0
        rounds.poll_once()
        elapsed[0] = 10.0
        snapshot = rounds.poll_once()

        self.assertEqual([result.status for result in snapshot.results], ["TESTING", "PASS", "NOTEST"])
        self.assertEqual(snapshot.state, "RUNNING")
        self.assertFalse(snapshot.result_available)

    def test_source_preparation_time_counts_from_the_accepted_start(self):
        elapsed = [0.0]
        monitors = []

        def create(callback):
            elapsed[0] = 12.0
            monitor = DeadlineMonitor(callback, lambda: elapsed[0], start=10)
            monitors.append(monitor)
            return monitor

        rounds = RoundCoordinator(monotonic=lambda: elapsed[0])
        rounds.start("FCT", create, run_async=False)
        snapshot = rounds.poll_once()

        self.assertEqual([result.status for result in snapshot.results], ["NOTEST"] * 3)
        self.assertEqual(monitors[0].poll_count, 0)
        self.assertEqual(snapshot.state, "COMPLETED")

    def test_individual_deadline_times_out_completing_slot_and_keeps_other_slots_running(self):
        elapsed = [0.0]
        monitors = []

        def create(callback):
            monitor = DeadlineMonitor(callback, lambda: elapsed[0], test=5)
            monitors.append(monitor)
            return monitor

        rounds = RoundCoordinator(monotonic=lambda: elapsed[0])
        rounds.start("FCT", create, run_async=False)
        monitors[0].publish(1, "TESTING")
        elapsed[0] = 1.0
        rounds.poll_once()
        monitors[0].publish(1, "COMPLETING")
        elapsed[0] = 4.0
        rounds.poll_once()
        elapsed[0] = 6.0
        snapshot = rounds.poll_once()

        self.assertEqual([result.status for result in snapshot.results], ["TIMEOUT", "WAITING", "WAITING"])
        self.assertEqual(snapshot.state, "RUNNING")
        timeout = next(item.event for item in snapshot.events
                       if item.event.status == "TIMEOUT")
        self.assertEqual(timeout.detail.get("reason"), "test_deadline")
        self.assertEqual(timeout.detail.get("elapsed_seconds"), "5")

    def test_deadline_wins_at_exact_boundary_and_results_complete_without_grace_period(self):
        elapsed = [0.0]
        monitors = []

        def create(callback):
            monitor = DeadlineMonitor(callback, lambda: elapsed[0], slots=(1,), start=10)
            monitors.append(monitor)
            return monitor

        rounds = RoundCoordinator(monotonic=lambda: elapsed[0])
        rounds.start("FCT", create, run_async=False)
        monitors[0].publish(1, "PASS")
        elapsed[0] = 10.0
        boundary = rounds.poll_once()
        self.assertEqual(boundary.results[0].status, "NOTEST")
        self.assertEqual(boundary.state, "COMPLETED")
        self.assertTrue(monitors[0].collection_stopped)
        poll_count = monitors[0].poll_count

        elapsed[0] = 11.0
        rounds.poll_once()
        self.assertEqual(monitors[0].poll_count, poll_count)
        self.assertEqual(rounds.snapshot().results[0].status, "NOTEST")

    def test_ambiguous_rswmt_log_retains_candidate_evidence_without_selecting_a_round(self):
        start = datetime(2026, 9, 11, 5, 44, 16)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / 'output' / 'SmtCal'
            output.mkdir(parents=True)
            rounds = RoundCoordinator()
            rounds.start('BT', lambda callback: RsWmtLogMonitor(
                output, slots=(1, 2, 3, 4), callback=callback,
                now=lambda: start + timedelta(seconds=20), monotonic=lambda: 20.0,
                session_root=root / 'sessions',
            ), run_async=False)
            (output / 'ambiguous.log').write_text(
                "2026-09-11 05:44:16,688 STATE:TestRunner Add-in 'initialize'...\n"
                '2026-09-11 05:44:16,793 DEBUG:instrument >> '
                '\'CONFigure:SCSTools:VARiable:DEFine "instance_active_1", 0, INSTrument\\n\'\n'
                '2026-09-11 05:44:20,000 DEBUG:HciCommunication << 30 bytes: .[....MLB#..SERIAL000001 05 5B\n'
                '2026-09-11 05:44:21,000 DEBUG:instrument >> '
                '\'CONFigure:SCSTools:VARiable:DEFine "instance_active_2", 0, INSTrument\\n\'\n'
                '2026-09-11 05:44:22,000 DEBUG:HciCommunication << 30 bytes: .[....MLB#..SERIAL000002 05 5B\n',
                encoding='utf-8',
            )

            rounds.poll_once()
            snapshot = rounds.snapshot()
            review = next(event.event for event in snapshot.events if event.event.kind == 'warning')

            self.assertEqual(review.source, str(output / 'ambiguous.log'))
            self.assertEqual(review.detail.get('source_slots'), '1,2')
            self.assertEqual(review.detail.get('source_sns'), 'SERIAL000001,SERIAL000002')
            self.assertEqual(review.detail.get('batch_candidates'), '2026-09-11T05:44:16.688')
            self.assertEqual(review.detail.get('source_time'), '2026-09-11T05:44:22.000')
            self.assertTrue(all(result.status == 'WAITING' for result in snapshot.results))

            unbound = output / 'unbound.log'
            unbound.write_text(
                '2026-09-11 05:44:23,000 DEBUG:instrument >> '
                '\'CONFigure:SCSTools:VARiable:DEFine "instance_active_3", 0, INSTrument\\n\'\n'
                '2026-09-11 05:44:24,000 DEBUG:HciCommunication << 30 bytes: .[....MLB#..SERIAL000003 05 5B\n',
                encoding='utf-8',
            )
            rounds.poll_once()
            unbound_warning = next(event.event for event in rounds.snapshot().events
                                   if event.event.kind == 'warning' and event.event.source == str(unbound))

            self.assertEqual(unbound_warning.detail.get('source_slots'), '3')
            self.assertEqual(unbound_warning.detail.get('source_sns'), 'SERIAL000003')
            self.assertEqual(unbound_warning.detail.get('source_time'), '2026-09-11T05:44:24.000')
            self.assertNotIn('batch_candidates', unbound_warning.detail)
            self.assertTrue(all(result.status == 'WAITING' for result in rounds.snapshot().results))

            partial = output / 'partial-evidence.log'
            partial.write_text(
                "2026-09-11 05:44:25,000 STATE:TestRunner Add-in 'initialize'...\n"
                '2026-09-11 05:44:26,123 PASS:TestRunner Item complete.\n',
                encoding='utf-8',
            )
            rounds.poll_once()
            partial_warning = next(event.event for event in rounds.snapshot().events
                                   if event.event.kind == 'warning' and event.event.source == str(partial))

            self.assertEqual(partial_warning.detail.get('source_time'), '2026-09-11T05:44:26.123')
            self.assertEqual(partial_warning.detail.get('batch_candidates'), '2026-09-11T05:44:25.000')
            self.assertNotIn('source_slots', partial_warning.detail)
            self.assertNotIn('source_sns', partial_warning.detail)
            self.assertTrue(all(result.status == 'WAITING' for result in rounds.snapshot().results))

    def test_rswmt_live_log_preserves_source_timestamp_precision_in_round_evidence(self):
        start = datetime(2026, 9, 11, 5, 44, 16)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / 'output' / 'SmtCal'
            output.mkdir(parents=True)
            rounds = RoundCoordinator()
            rounds.start('BT', lambda callback: RsWmtLogMonitor(
                output, slots=(1,), callback=callback,
                now=lambda: start + timedelta(seconds=20), monotonic=lambda: 20.0,
                session_root=root / 'sessions',
            ), run_async=False)
            (output / 'live.log').write_text(
                "2026-09-11 05:44:16,688 STATE:TestRunner Add-in 'initialize'...\n"
                '2026-09-11 05:44:16,793 DEBUG:instrument >> '
                '\'CONFigure:SCSTools:VARiable:DEFine "instance_active_1", 0, INSTrument\\n\'\n'
                '2026-09-11 05:44:27,462 DEBUG:HciCommunication << 30 bytes: .[....MLB#..SERIAL000001 05 5B\n'
                '2026-09-11 05:44:28,401 PASS:TestRunner Item complete.\n',
                encoding='utf-8',
            )

            rounds.poll_once()
            result_event = next(event.event for event in rounds.snapshot().events
                                if event.event.status == 'TESTING')

            self.assertEqual(result_event.detail.get('source_time'), '2026-09-11T05:44:28.401')
            self.assertEqual(result_event.detail.get('batch_evidence'), '2026-09-11T05:44:16.688')

    def test_rswmt_final_only_source_delivers_final_evidence_through_round_interface(self):
        start = datetime(2026, 9, 11, 5, 44, 16)
        elapsed = [0.0]
        headers = ['Serial Number', 'Test Pass/Fail Status', 'List of Failing Tests',
                   'Error Description', 'Test Start Time', 'Test Stop Time', 'PRODUCT',
                   'tc=Slot:tech=None:band=None;subtc=None:rate=None:freq=None:pwr=None;']
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / 'output' / 'SmtCal'
            output.mkdir(parents=True)
            rounds = RoundCoordinator()
            rounds.start('BT', lambda callback: RsWmtLogMonitor(
                output, slots=(1,), callback=callback,
                now=lambda: start + timedelta(seconds=elapsed[0]), monotonic=lambda: elapsed[0],
                start_timeout_seconds=240, test_timeout_seconds=480, round_timeout_seconds=7200,
                session_root=root / 'sessions',
            ), run_async=False)

            result_dir = output / '2026-09-11_05-45-44'
            result_dir.mkdir()
            result = io.StringIO()
            writer = csv.writer(result)
            writer.writerow(['Overlay', 'SmtCal'] + [''] * 6)
            writer.writerow(headers)
            writer.writerow(['SERIAL000001', 'Pass', '[]', '', '2026/11/09 05:44:16',
                             '2026/11/09 05:45:44', 'B518', '1'])
            source = result_dir / 'SERIAL000001_2026-09-11_05-45-44.csv'
            source.write_text(result.getvalue(), encoding='utf-8')

            elapsed[0] = 88.0
            rounds.poll_once()
            self.assertEqual(rounds.snapshot().results[0].status, 'COMPLETING')
            self.assertFalse(any(event.event.status == 'TESTING' for event in rounds.events_since()))
            elapsed[0] = 93.0
            rounds.poll_once()

            snapshot = rounds.snapshot()
            self.assertEqual(snapshot.results[0].status, 'PASS')
            self.assertEqual(snapshot.state, 'COMPLETED')
            self.assertTrue(snapshot.collection_stopped)
            final = [event.event for event in snapshot.events if event.event.status == 'PASS'][-1]
            self.assertEqual(final.source, str(source))
            self.assertEqual(final.detail.get('source_time'), '2026-09-11T05:45:44')
            self.assertEqual(final.detail.get('batch_evidence'), '2026-09-11T05:44:16')

    def test_rswmt_adapter_sends_confirmed_same_run_conflicting_final_to_shared_review(self):
        start = datetime(2026, 9, 11, 5, 44, 16)
        elapsed = [0.0]
        headers = ['Serial Number', 'Test Pass/Fail Status', 'List of Failing Tests',
                   'Error Description', 'Test Start Time', 'Test Stop Time', 'PRODUCT',
                   'tc=Slot:tech=None:band=None;subtc=None:rate=None:freq=None:pwr=None;']
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / 'output'
            output.mkdir()
            rounds = RoundCoordinator()
            rounds.start('BT', lambda callback: RsWmtLogMonitor(
                output, slots=(1, 2), callback=callback,
                now=lambda: start + timedelta(seconds=elapsed[0]), monotonic=lambda: elapsed[0],
                start_timeout_seconds=240, test_timeout_seconds=480, round_timeout_seconds=7200,
                session_root=root / 'sessions',
            ), run_async=False)

            def write_final(sn, result, stop_time, filename_time):
                result_dir = output / filename_time
                result_dir.mkdir(parents=True, exist_ok=True)
                buffer = io.StringIO()
                writer = csv.writer(buffer)
                writer.writerow(['Overlay', 'SmtCal'] + [''] * 6)
                writer.writerow(headers)
                writer.writerow([sn, result, '[]', '', '2026/11/09 05:44:16',
                                 '2026/11/09 ' + stop_time, 'B518', '1'])
                path = result_dir / '{}_{}.csv'.format(sn, filename_time)
                path.write_text(buffer.getvalue(), encoding='utf-8')
                return path

            first = write_final('SERIAL000001', 'Pass', '05:45:44', '2026-09-11_05-45-44')
            elapsed[0] = 88.0
            rounds.poll_once()
            elapsed[0] = 93.0
            rounds.poll_once()
            self.assertEqual(rounds.snapshot().results[0].status, 'PASS')

            second = write_final('SERIAL000099', 'Fail', '05:46:00', '2026-09-11_05-46-00')
            elapsed[0] = 104.0
            rounds.poll_once()
            elapsed[0] = 109.0
            snapshot = rounds.poll_once()

            self.assertEqual(snapshot.results[0].status, 'PASS')
            self.assertEqual(snapshot.state.value, 'AWAITING_REVIEW')
            self.assertEqual([(item.original.sn, item.original.status, item.candidate.sn,
                               item.candidate.status, item.candidate.source)
                              for item in snapshot.pending_conflicts], [
                ('SERIAL000001', 'PASS', 'SERIAL000099', 'FAIL', str(second)),
            ])
            conflict = snapshot.pending_conflicts[0]
            self.assertEqual(conflict.candidate.sn, 'SERIAL000099')
            self.assertEqual(conflict.original.source, str(first))
            self.assertEqual(conflict.candidate.source, str(second))
            self.assertEqual(dict(conflict.same_round_evidence)['round_evidence_id'],
                             'rswmt:1:2026-09-11T05:44:16')
            rounds.resolve_review(conflict.conflict_id, 'keep_original')
            rounds.stop()
            self.assertTrue(rounds.flush_session())

            accepted_sequence = rounds.snapshot().event_sequence
            late_dir = output / '2026-09-11_05-46-44'
            late_dir.mkdir()
            (late_dir / 'LATE00000001_2026-09-11_05-46-44.csv').write_text('late data')
            elapsed[0] = 94.0
            rounds.poll_once()
            self.assertEqual(rounds.snapshot().event_sequence, accepted_sequence)
            self.assertEqual(rounds.snapshot().results[0].status, 'PASS')

    def test_rswmt_timeout_is_applied_by_round_and_late_csv_cannot_replace_it(self):
        start = datetime(2026, 9, 11, 5, 44, 16)
        elapsed = [0.0]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / 'output' / 'SmtCal'
            output.mkdir(parents=True)
            rounds = RoundCoordinator(monotonic=lambda: elapsed[0])

            def create(callback):
                return RsWmtLogMonitor(
                    output, slots=(1, 2), callback=callback,
                    now=lambda: start + timedelta(seconds=elapsed[0]),
                    monotonic=lambda: elapsed[0], start_timeout_seconds=30,
                    test_timeout_seconds=5, round_timeout_seconds=100,
                    session_root=root / 'sessions',
                )

            rounds.start('BT', create, run_async=False)
            (output / 'live.log').write_text(
                "2026-09-11 05:44:16,688 STATE:TestRunner Add-in 'initialize'...\n"
                '2026-09-11 05:44:16,793 DEBUG:instrument >> '
                '\'CONFigure:SCSTools:VARiable:DEFine "instance_active_1", 0, INSTrument\\n\'\n'
                '2026-09-11 05:44:27,462 DEBUG:HciCommunication << 30 bytes: .[....MLB#..'
                'TESTSERIAL0001 05 5B\n'
                '2026-09-11 05:44:28,000 PASS:TestRunner Item complete.\n',
                encoding='utf-8',
            )
            rounds.poll_once()
            self.assertEqual(rounds.snapshot().results[0].status, 'TESTING')
            elapsed[0] = 5.0
            rounds.poll_once()
            self.assertEqual([result.status for result in rounds.snapshot().results],
                             ['TIMEOUT', 'WAITING'])

            result_dir = output / '2026-09-11_05-45-44'
            result_dir.mkdir()
            final_data = io.StringIO()
            writer = csv.writer(final_data)
            headers = ['Serial Number', 'Test Pass/Fail Status', 'List of Failing Tests',
                       'Error Description', 'Test Start Time', 'Test Stop Time', 'PRODUCT',
                       'tc=Slot:tech=None:band=None;subtc=None:rate=None:freq=None:pwr=None;']
            writer.writerow(['Overlay', 'SmtCal'] + [''] * 6)
            writer.writerow(headers)
            writer.writerow(['TESTSERIAL0001', 'Pass', '[]', '', '2026/11/09 05:44:16',
                             '2026/11/09 05:45:44', 'B518', '1'])
            (result_dir / 'TESTSERIAL0001_2026-09-11_05-45-44.csv').write_text(final_data.getvalue())
            elapsed[0] = 6.0
            rounds.poll_once()
            self.assertEqual(rounds.snapshot().results[0].status, 'TIMEOUT')
            rounds.stop()
            self.assertTrue(rounds.flush_session())

    def test_repeated_start_while_running_keeps_the_same_round(self):
        monitors = []

        def create(callback):
            monitor = FakeMonitor(callback)
            monitors.append(monitor)
            return monitor

        rounds = RoundCoordinator()
        first = rounds.start("FCT", create, run_async=False)
        monitors[0].results[1].status = "PASS"
        again = rounds.start("FCT", create, run_async=False)

        self.assertEqual(first.round_id, again.round_id)
        self.assertEqual(monitors[0].started, 1)
        self.assertEqual(len(monitors), 1)
        self.assertEqual(rounds.snapshot().results[0].status, "PASS")

    def test_queued_event_from_previous_round_cannot_change_current_snapshot_or_events(self):
        monitors = []

        def create(callback):
            monitor = FakeMonitor(callback)
            monitors.append(monitor)
            return monitor

        rounds = RoundCoordinator()
        old_round = rounds.start("FCT", create, run_async=False)
        rounds.stop()
        old_events = rounds.events_since()
        current_round = rounds.start("FCT", create, run_async=False)
        before = rounds.snapshot()
        old_monitor = monitors[0]
        old_monitor.results[1].status = "FAIL"
        old_monitor.callback(MonitorEvent("result", "stale", 1, status="FAIL"))

        after = rounds.snapshot()
        self.assertEqual(old_round.round_id, old_events[-1].round_id)
        self.assertNotEqual(old_round.round_id, current_round.round_id)
        self.assertEqual(after.results, before.results)
        self.assertEqual(rounds.events_since(before.event_sequence), ())

    def test_manual_stop_preserves_completed_results_and_marks_incomplete_stopped(self):
        monitor = None

        def create(callback):
            nonlocal monitor
            monitor = FakeMonitor(callback)
            return monitor

        rounds = RoundCoordinator()
        rounds.start("FCT", create, run_async=False)
        monitor.results[1].status = "PASS"
        snapshot = rounds.stop()

        self.assertEqual([(result.slot, result.status) for result in snapshot.results],
                         [(1, "PASS"), (2, "STOPPED")])
        self.assertEqual(snapshot.state, "STOPPED")
        self.assertFalse(snapshot.result_available)
        self.assertEqual(snapshot.events[-1].event.kind, "stopped")

    def test_manual_stop_keeps_mixed_terminals_and_stops_only_incomplete_positions(self):
        elapsed = [0.0]
        monitors = []

        def create(callback):
            monitor = DeadlineMonitor(callback, lambda: elapsed[0],
                                      slots=range(1, 8), start=30, test=100)
            monitors.append(monitor)
            return monitor

        rounds = RoundCoordinator(monotonic=lambda: elapsed[0])
        rounds.start("FCT", create, run_async=False)
        for slot, status in ((1, "PASS"), (2, "FAIL"), (3, "NOTEST"), (4, "TIMEOUT"),
                             (5, "TESTING"), (6, "COMPLETING")):
            monitors[0].publish(slot, status)
        rounds.poll_once()
        snapshot = rounds.stop()

        self.assertEqual([result.status for result in snapshot.results], [
            "PASS", "FAIL", "NOTEST", "TIMEOUT", "STOPPED", "STOPPED", "STOPPED",
        ])
        self.assertEqual(snapshot.state, "STOPPED")
        self.assertFalse(snapshot.result_available)
        self.assertTrue(snapshot.collection_stopped)
        self.assertEqual(snapshot.completion_reason, "manual_stop")

    def test_failed_previous_round_remains_queryable_and_retriable_after_new_round_starts(self):
        with tempfile.TemporaryDirectory() as temporary:
            monitors = []

            def create(callback):
                monitor = FakeMonitor(callback)
                monitors.append(monitor)
                return monitor

            rounds = RoundCoordinator(audit_root=Path(temporary))
            first = rounds.start("FCT", create, run_async=False)
            self.assertTrue(rounds.flush_audit())
            original_write = audit_records.os.write
            injected = threading.Event()

            def fail_probe(descriptor, content):
                if b"cross_round_failure_probe" in content:
                    injected.set()
                    raise OSError("temporary previous-round disk fault")
                return original_write(descriptor, content)

            with patch.object(audit_records.os, "write", side_effect=fail_probe):
                monitors[0].callback(MonitorEvent(
                    "cross_round_failure_probe", "preserve with original round identity"))
                self.assertTrue(injected.wait(2))
                self.assertFalse(rounds.flush_audit(timeout=2))
                rounds.stop()
                second = rounds.start("FCT", create, run_async=False)

            self.assertNotEqual(first.round_id, second.round_id)
            unsaved = rounds.unsaved_rounds()
            by_id = {item.round_id: item for item in unsaved}
            self.assertEqual(set(by_id), {first.round_id, second.round_id})
            self.assertIn("temporary previous-round disk fault", by_id[first.round_id].save_errors[0])
            self.assertTrue(rounds.has_unsaved_rounds)
            self.assertTrue(rounds.retry_saves(first.round_id))

            deadline = time.monotonic() + 3
            recovered = None
            while time.monotonic() < deadline:
                candidates = {item.round_id: item for item in rounds.unsaved_rounds()}
                recovered = candidates.get(first.round_id)
                if recovered is None:
                    break
                time.sleep(0.01)

            rebuilt = read_round_audit(Path(temporary) / first.round_id / "audit.jsonl")
            probe = [event for event in rebuilt["events"]
                     if event["kind"] == "cross_round_failure_probe"]
            self.assertTrue(rebuilt["audit_complete"])
            self.assertEqual(len(probe), 1)
            self.assertEqual(probe[0]["round_id"], first.round_id)
            self.assertEqual(probe[0]["message"], "preserve with original round identity")
            self.assertNotIn(first.round_id, {item.round_id for item in rounds.unsaved_rounds()})
            rounds.stop()
            self.assertTrue(rounds.flush_audit())
            self.assertFalse(rounds.has_unsaved_rounds)

    def test_multiple_failed_rounds_recover_independently_without_cross_round_records(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            monitors = []

            def create(callback):
                monitor = FakeMonitor(callback)
                monitors.append(monitor)
                return monitor

            rounds = RoundCoordinator(audit_root=root)
            failed_rounds = []
            for index in range(2):
                snapshot = rounds.start("FCT", create, run_async=False)
                self.assertTrue(rounds.flush_audit())
                rounds.stop()
                marker = "old_round_probe_{}".format(index)
                original_write = audit_records.os.write

                def fail_marker(descriptor, content, marker=marker):
                    if marker.encode("utf-8") in content:
                        raise OSError("disk fault for {}".format(marker))
                    return original_write(descriptor, content)

                with patch.object(audit_records.os, "write", side_effect=fail_marker):
                    monitors[index].callback(MonitorEvent(marker, marker))
                    deadline = time.monotonic() + 2
                    while rounds.round_snapshot(snapshot.round_id).save_state != "failed" and time.monotonic() < deadline:
                        time.sleep(0.01)
                failed_rounds.append(snapshot.round_id)

            current = rounds.start("FCT", create, run_async=False)
            self.assertEqual({item.round_id for item in rounds.unsaved_rounds()},
                             set(failed_rounds) | {current.round_id})
            for index, round_id in enumerate(failed_rounds):
                self.assertTrue(rounds.retry_saves(round_id))
                deadline = time.monotonic() + 3
                while rounds.round_snapshot(round_id) is not None and time.monotonic() < deadline:
                    time.sleep(0.01)
                rebuilt = read_round_audit(root / round_id / "audit.jsonl")
                marker = "old_round_probe_{}".format(index)
                saved = [event for event in rebuilt["events"] if event["kind"] == marker]
                self.assertTrue(rebuilt["audit_complete"])
                self.assertEqual(len(saved), 1)
                self.assertEqual(saved[0]["round_id"], round_id)
                other_marker = "old_round_probe_{}".format(1 - index)
                self.assertFalse(any(event["kind"] == other_marker for event in rebuilt["events"]))

    def test_completed_round_objects_are_released_as_new_rounds_replace_them(self):
        with tempfile.TemporaryDirectory() as temporary:
            rounds = RoundCoordinator(audit_root=Path(temporary))
            monitor_refs = []

            def create(callback):
                monitor = FakeMonitor(callback)
                monitor_refs.append(weakref.ref(monitor))
                return monitor

            for _ in range(6):
                rounds.start("FCT", create, run_async=False)
                rounds.stop()
                self.assertTrue(rounds.flush_audit())
                self.assertEqual(rounds.snapshot().save_state, "complete")

            rounds.start("FCT", create, run_async=False)
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline and any(ref() is not None for ref in monitor_refs[:-1]):
                gc.collect()
                time.sleep(0.05)
            gc.collect()
            self.assertTrue(all(ref() is None for ref in monitor_refs[:-1]))
            self.assertEqual(len(rounds.unsaved_rounds()), 1)

    def test_unsaved_tracking_is_limited_to_rounds_created_in_this_coordinator_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            historical = root / "historical-session-from-last-run"
            historical.mkdir()
            (historical / "audit.jsonl").write_text("not loaded by current-run tracking\n",
                                                     encoding="utf-8")
            rounds = RoundCoordinator(audit_root=root)
            current = rounds.start("FCT", lambda callback: FakeMonitor(callback), run_async=False)

            tracked = rounds.unsaved_rounds()
            self.assertEqual([snapshot.round_id for snapshot in tracked], [current.round_id])
            self.assertFalse(any(snapshot.round_id == historical.name for snapshot in tracked))
            self.assertTrue(rounds.flush_audit())


    def test_graceful_close_waits_for_every_current_run_round_to_be_durable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            historical = root / "prior-run-session"
            historical.mkdir()
            (historical / "audit.jsonl").write_text("historical data remains untouched\n",
                                                     encoding="utf-8")
            rounds = RoundCoordinator(audit_root=root)
            factory = lambda callback: FakeMonitor(callback)
            first = rounds.start("FCT", factory, run_async=False)
            rounds.stop()
            self.assertTrue(rounds.flush_audit())
            self.assertTrue(read_round_audit(
                Path(temporary) / first.round_id / "audit.jsonl")["audit_complete"])
            second = rounds.start("FCT", factory, run_async=False)

            accepted = rounds.request_close()

            self.assertIn(accepted.status, {"saving", "waiting"})
            deadline = time.monotonic() + 3
            while rounds.close_status().status != "complete" and time.monotonic() < deadline:
                threading.Event().wait(0.01)
            closed = rounds.close_status()
            self.assertEqual(closed.status, "complete")
            self.assertIn(second.round_id, closed.round_ids)
            self.assertNotIn(historical.name, closed.round_ids)
            self.assertEqual((historical / "audit.jsonl").read_text(encoding="utf-8"),
                             "historical data remains untouched\n")
            for round_id in {first.round_id, second.round_id}:
                snapshot = rounds.round_snapshot(round_id)
                audit = read_round_audit(Path(temporary) / round_id / "audit.jsonl")
                self.assertTrue(audit["audit_complete"])
                if snapshot is not None:
                    self.assertEqual(snapshot.save_state, "complete")
                    self.assertTrue(snapshot.audit_complete)

    def test_close_waits_for_inflight_operator_resolution_and_freezes_after_completion(self):
        with tempfile.TemporaryDirectory() as temporary:
            action_entered = threading.Event()
            release_action = threading.Event()
            holder = {}

            class BlockingResolutionMonitor(FakeMonitor):
                block_resolution = False

                def apply_round_result(self, slot, status, sn="", source="", detail=None,
                                       lock_terminal=False):
                    if self.block_resolution:
                        action_entered.set()
                        if not release_action.wait(5):
                            raise RuntimeError("test did not release conflict resolution")
                    result = self.results[slot]
                    result.sn = sn or result.sn
                    result.status = status
                    result.source = source or result.source
                    result.updated_at = "2026-10-07T10:00:00"
                    self.callback(MonitorEvent("result", "slot{} {}".format(slot, status),
                                               slot, result.sn, status, source, detail or {}))

            def factory(callback):
                monitor = BlockingResolutionMonitor(callback)
                holder["monitor"] = monitor
                return monitor

            rounds = RoundCoordinator(audit_root=Path(temporary))
            started = rounds.start("FCT", factory, run_async=False, capacity=2)
            monitor = holder["monitor"]
            evidence = {"round_evidence_id": "fct:1:close-race",
                        "source_time": "2026-10-07T10:00:00"}
            monitor.apply_round_result(1, "PASS", "SERIAL000001", "active.csv", evidence)
            self.assertEqual(monitor.callback(MonitorEvent(
                "result_candidate", "candidate", 1, "SERIAL000001", "FAIL", "final.csv",
                dict(evidence, source_id="final.csv"))), "defer")
            conflict_id = rounds.round_snapshot(started.round_id).pending_conflicts[0].conflict_id
            monitor.block_resolution = True
            resolution = threading.Thread(
                target=lambda: rounds.resolve_review(conflict_id, "keep_original"), daemon=True,
            )
            resolution.start()
            self.assertTrue(action_entered.wait(2))

            rounds.request_close()
            self.assertNotEqual(rounds.close_status().status, "complete")
            release_action.set()
            resolution.join(2)
            self.assertFalse(resolution.is_alive())
            deadline = time.monotonic() + 3
            while rounds.close_status().status != "complete" and time.monotonic() < deadline:
                threading.Event().wait(0.01)
            self.assertEqual(rounds.close_status().status, "complete")

            audit_path = Path(temporary) / started.round_id / "audit.jsonl"
            rebuilt = read_round_audit(audit_path)
            self.assertTrue(rebuilt["audit_complete"])
            self.assertEqual([event["kind"] for event in rebuilt["events"]].count(
                "conflict_resolved"), 1)
            count_at_close = len(rebuilt["events"])
            rounds.resolve_review(conflict_id, "accept_candidate")
            self.assertEqual(len(read_round_audit(audit_path)["events"]), count_at_close)

    def test_close_waits_for_source_preparation_and_restarts_after_cancel(self):
        with tempfile.TemporaryDirectory() as temporary:
            entered = threading.Event()
            release = threading.Event()
            rounds = RoundCoordinator(audit_root=Path(temporary))

            def factory(callback):
                entered.set()
                release.wait(4)
                return FakeMonitor(callback)

            started = rounds.start("FCT", factory, run_async=True)
            self.assertTrue(entered.wait(2))
            first_attempt = rounds.request_close()
            self.assertEqual(first_attempt.status, "saving")
            rounds.cancel_close()
            second_attempt = rounds.request_close()
            self.assertGreater(second_attempt.generation, first_attempt.generation)
            release.set()

            deadline = time.monotonic() + 4
            while rounds.close_status().status != "complete" and time.monotonic() < deadline:
                threading.Event().wait(0.01)
            self.assertEqual(rounds.close_status().status, "complete")
            self.assertEqual(rounds.close_status().round_ids, (started.round_id,))
            self.assertTrue(rounds.round_snapshot(started.round_id).audit_complete)

    def test_source_preparation_failure_is_audited_before_close_completes(self):
        with tempfile.TemporaryDirectory() as temporary:
            entered = threading.Event()
            rounds = RoundCoordinator(audit_root=Path(temporary))

            def fail_preparation(_callback):
                entered.set()
                raise RuntimeError("source setup fault")

            started = rounds.start("FCT", fail_preparation, run_async=True)
            self.assertTrue(entered.wait(2))
            rounds.request_close()

            deadline = time.monotonic() + 3
            while rounds.close_status().status != "complete" and time.monotonic() < deadline:
                threading.Event().wait(0.01)
            self.assertEqual(rounds.close_status().status, "complete")
            rebuilt = read_round_audit(Path(temporary) / started.round_id / "audit.jsonl")
            self.assertTrue(rebuilt["audit_complete"])
            self.assertTrue(any(event["kind"] == "start_failed" for event in rebuilt["events"]))

    def test_close_recovers_a_failed_previous_round_and_current_round_without_crossing_events(self):
        with tempfile.TemporaryDirectory() as temporary:
            failure_reported = threading.Event()

            def on_event(event):
                if event.event.kind == "audit_write_failed":
                    failure_reported.set()

            rounds = RoundCoordinator(on_event, audit_root=Path(temporary))
            factory = lambda callback: FakeMonitor(callback)
            first = rounds.start("FCT", factory, run_async=False)
            original_write = audit_records.os.write
            failed = [False]

            def fail_first_stop(descriptor, content):
                if b"collection_stopped" in content and not failed[0]:
                    failed[0] = True
                    raise OSError("previous round disk fault")
                return original_write(descriptor, content)

            with patch.object(audit_records.os, "write", side_effect=fail_first_stop):
                rounds.stop()
                self.assertTrue(failure_reported.wait(2))
            self.assertEqual(rounds.round_snapshot(first.round_id).save_state, "failed")

            second = rounds.start("FCT", factory, run_async=False)
            accepted = rounds.request_close()
            self.assertIn(first.round_id, accepted.round_ids)
            self.assertIn(second.round_id, accepted.round_ids)
            deadline = time.monotonic() + 3
            while rounds.close_status().status != "failed" and time.monotonic() < deadline:
                threading.Event().wait(0.01)
            self.assertEqual(rounds.close_status().status, "failed")

            rounds.retry_close_saves()
            deadline = time.monotonic() + 4
            while rounds.close_status().status != "complete" and time.monotonic() < deadline:
                threading.Event().wait(0.01)
            self.assertEqual(rounds.close_status().status, "complete")
            for round_id in (first.round_id, second.round_id):
                rebuilt = read_round_audit(Path(temporary) / round_id / "audit.jsonl")
                self.assertTrue(rebuilt["audit_complete"])
                self.assertEqual(sum(event["kind"] == "collection_stopped"
                                     for event in rebuilt["events"]), 1)
                self.assertTrue(all(event["detail"].get("round_id", round_id) == round_id
                                    for event in rebuilt["events"]))

    def test_close_cannot_accept_a_new_round_before_completion_or_cancellation(self):
        with tempfile.TemporaryDirectory() as temporary:
            stop_entered = threading.Event()
            release_stop = threading.Event()
            stop_finished = threading.Event()
            holder = {}

            class SlowStopMonitor(FakeMonitor):
                def stop(self):
                    stop_entered.set()
                    release_stop.wait(3)
                    super().stop()
                    stop_finished.set()

            rounds = RoundCoordinator()
            first = rounds.start("FCT", lambda callback: holder.setdefault(
                "monitor", SlowStopMonitor(callback)), run_async=False)
            accepted = rounds.request_close()
            self.assertTrue(stop_entered.wait(2))
            with self.assertRaisesRegex(RuntimeError, "關閉保存進行中"):
                rounds.start("FCT", lambda callback: FakeMonitor(callback), run_async=False)
            rounds.cancel_close()
            release_stop.set()
            deadline = time.monotonic() + 2
            while rounds.snapshot().state.value == "RUNNING" and time.monotonic() < deadline:
                threading.Event().wait(0.01)
            self.assertTrue(stop_finished.wait(2))
            self.assertTrue(rounds.flush_audit())
            next_round = rounds.start("FCT", lambda callback: FakeMonitor(callback), run_async=False)
            self.assertNotEqual(next_round.round_id, first.round_id)
            self.assertTrue(accepted.generation < rounds.close_status().generation)

    def test_successful_flush_does_not_allow_close_when_audit_is_incomplete(self):
        rounds = RoundCoordinator()
        started = rounds.start("FCT", lambda callback: FakeMonitor(callback), run_async=False)
        rounds.stop()
        self.assertTrue(rounds.flush_audit())
        self.assertFalse(rounds.round_snapshot(started.round_id).audit_complete)

        rounds.request_close()

        deadline = time.monotonic() + 2
        while rounds.close_status().status != "failed" and time.monotonic() < deadline:
            threading.Event().wait(0.01)
        self.assertEqual(rounds.close_status().status, "failed")
        self.assertIn("audit_complete 仍為 false", rounds.close_status().message)


if __name__ == "__main__":
    unittest.main()
