import csv
import io
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from log_monitoring import MonitorEvent, SlotResult
from monitoring_round import RoundCoordinator
from rswmt_monitoring import RsWmtLogMonitor


class FakeMonitor:
    def __init__(self, callback):
        self.callback = callback
        self.results = {1: SlotResult(1), 2: SlotResult(2)}
        self.started = 0
        self.stopped = 0
        self.finished = False

    def start(self):
        self.started += 1

    def stop(self):
        self.stopped += 1
        self.results[2].status = "STOPPED"
        self.finished = True
        self.callback(MonitorEvent("stopped", "stopped"))


class MonitoringRoundTests(unittest.TestCase):
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

            rounds.monitor.poll_once()
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
            monitor.poll_once()
            self.assertEqual(rounds.snapshot().results[0].status, 'COMPLETING')
            self.assertFalse(any(event.event.status == 'TESTING' for event in rounds.events_since()))
            elapsed[0] = 93.0
            monitor.poll_once()

            snapshot = rounds.snapshot()
            self.assertEqual(snapshot.results[0].status, 'PASS')
            final = [event.event for event in snapshot.events if event.event.status == 'PASS'][-1]
            self.assertEqual(final.source, str(source))
            self.assertEqual(final.detail.get('source_time'), '2026-09-11T05:45:44')
            self.assertEqual(final.detail.get('batch_evidence'), '2026-09-11T05:44:16')

    def test_repeated_start_while_running_keeps_the_same_round(self):
        monitors = []

        def create(callback):
            monitor = FakeMonitor(callback)
            monitors.append(monitor)
            return monitor

        rounds = RoundCoordinator()
        first = rounds.start("FCT", create)
        monitors[0].results[1].status = "PASS"
        again = rounds.start("FCT", create)

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
        old_round = rounds.start("FCT", create)
        rounds.stop()
        old_events = rounds.events_since()
        current_round = rounds.start("FCT", create)
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
        rounds.start("FCT", create)
        monitor.results[1].status = "PASS"
        snapshot = rounds.stop()

        self.assertEqual([(result.slot, result.status) for result in snapshot.results],
                         [(1, "PASS"), (2, "STOPPED")])
        self.assertEqual(snapshot.state, "STOPPED")
        self.assertFalse(snapshot.result_available)
        self.assertEqual(snapshot.events[-1].event.kind, "stopped")


if __name__ == "__main__":
    unittest.main()
