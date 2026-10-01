import unittest

from log_monitoring import MonitorEvent, SlotResult
from monitoring_round import RoundCoordinator


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
