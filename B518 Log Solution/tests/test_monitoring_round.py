import csv
import io
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from log_monitoring import BtLogMonitor, MonitorEvent, SlotResult
from monitoring_round import RoundCoordinator
from rswmt_monitoring import RsWmtLogMonitor


class FakeMonitor:
    def __init__(self, callback):
        self.callback = callback
        self.results = {1: SlotResult(1), 2: SlotResult(2)}
        self.started = 0
        self.stopped = 0
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
        return self.callback(MonitorEvent("result_candidate", "candidate", slot, sn, status,
                                           source, detail))

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
        evidence = {"round_evidence_id": "rswmt-run-20261002T100000"}
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
        first_id, second_id = [item.conflict_id for item in first.pending_conflicts]
        kept = rounds.resolve_review(first_id, "keep_original")
        self.assertEqual([item.conflict_id for item in kept.pending_conflicts], [second_id])
        self.assertEqual(kept.results[0].sn, "SERIAL000001")
        adopted = rounds.resolve_review(second_id, "accept_candidate")
        self.assertEqual(adopted.results[0].sn, "SERIAL000003")
        self.assertEqual(adopted.results[0].status, "FAIL")
        self.assertFalse(adopted.pending_conflicts)
        resolved = [item.event for item in adopted.events if item.event.kind == "conflict_resolved"]
        self.assertEqual([item.detail["conflict_id"] for item in resolved], [first_id, second_id])

    def test_unconfirmed_round_evidence_is_retained_without_an_adoption_choice(self):
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
        unresolved = [event.event for event in snapshot.events
                      if event.event.kind == "unresolved_source_conflict"]
        self.assertEqual(len(unresolved), 1)
        self.assertEqual(unresolved[0].detail["candidate_source_time"], "unknown")

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

    def test_conflict_resolution_does_not_release_round_deadline_results(self):
        elapsed = [0.0]
        holder = {}

        def factory(callback):
            monitor = DeadlineMonitor(callback, lambda: elapsed[0], slots=(1, 2), round_limit=5)
            holder["monitor"] = monitor
            return monitor

        coordinator = RoundCoordinator(monotonic=lambda: elapsed[0])
        coordinator.start("FCT", factory, run_async=False)
        evidence = {"round_evidence_id": "atlas:1:SERIAL000001"}
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

            def factory(callback):
                return BtLogMonitor(
                    root, (1, 2), caseinfo_root=caseinfo, callback=callback, now=lambda: now,
                    monotonic=lambda: elapsed[0], start_timeout_seconds=60,
                    test_timeout_seconds=100, round_timeout_seconds=500,
                    session_root=sessions,
                )

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
            monitor = coordinator.monitor
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
            self.assertTrue(first.exists())
            self.assertTrue(slot2.exists())
            third = write_result(0, "HK5HUX6STQ100003YV", "20261002100002")
            coordinator.poll_once()
            self.assertEqual(coordinator.snapshot().results[0].sn, "HK5HUX6STQ000003YV")
            self.assertTrue(third.exists())

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

            monitor = rounds.monitor
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


if __name__ == "__main__":
    unittest.main()
