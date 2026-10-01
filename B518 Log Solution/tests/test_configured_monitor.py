import unittest

from configured_monitor import ConfiguredMonitor
from log_monitoring import MonitorEvent, SlotResult
from monitoring_round import RoundCoordinator


class FakeMonitor:
    def __init__(self, callback):
        self.callback = callback
        self.results = {1: SlotResult(1), 2: SlotResult(2)}

    def start(self):
        self.results[1].status = "PASS"
        self.callback(MonitorEvent("result", "source 1 passed", 1, status="PASS"))

    def stop(self):
        pass


class ConfiguredMonitorTests(unittest.TestCase):
    def test_profile_mapping_is_visible_through_round_snapshot_and_events(self):
        def create(callback):
            holder = {}

            def deliver(event):
                holder["view"].deliver(event, callback)

            monitor = FakeMonitor(deliver)
            configured = ConfiguredMonitor(monitor, {1: 2, 2: 1})
            holder["view"] = configured
            return configured

        rounds = RoundCoordinator()
        rounds.start("DFU", create)

        snapshot = rounds.snapshot()
        self.assertEqual([(result.slot, result.status) for result in snapshot.results],
                         [(1, "WAITING"), (2, "PASS")])
        self.assertEqual(snapshot.events[0].event.slot, 2)

    def test_warning_for_unmapped_source_is_kept_without_claiming_a_display_slot(self):
        configured = ConfiguredMonitor(FakeMonitor(lambda _event: None), {1: 2, 2: 1})
        delivered = []

        configured.deliver(MonitorEvent("warning", "unknown source position", 9), delivered.append)

        self.assertEqual(len(delivered), 1)
        self.assertIsNone(delivered[0].slot)
        self.assertEqual(delivered[0].detail["source_slot"], "9")


if __name__ == "__main__":
    unittest.main()
