import unittest
import tempfile
from datetime import datetime
from pathlib import Path

from configured_monitor import ConfiguredMonitor
from log_monitoring import BtLogMonitor, MonitorEvent, SlotResult
from machine_profiles import MachineProfile, validate_profile
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

    def test_b482_caseinfo_logical_slot_uses_profile_mapping(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            testdata, caseinfo = root / "TestData", root / "CaseInfo"
            testdata.mkdir()
            caseinfo.mkdir()
            profile = MachineProfile(
                "B482", "BT", "b482", 3,
                {"final": str(testdata), "caseinfo": str(caseinfo)},
                ((1, 3), (2, 1), (3, 2)),
                {"start": 30, "test": 240, "round": 7200},
            )
            validate_profile(profile)
            rounds = RoundCoordinator()

            def create(callback):
                holder = {}

                def deliver(event):
                    holder["view"].deliver(event, callback)

                monitor = BtLogMonitor(
                    testdata, tuple(source for source, _display in profile.mapping),
                    caseinfo_root=caseinfo, callback=deliver,
                    now=lambda: datetime(2026, 9, 11, 5, 44, 16),
                    monotonic=lambda: 0.0, session_root=root / "sessions",
                )
                view = ConfiguredMonitor(monitor, dict(profile.mapping))
                holder["view"] = view
                return view

            rounds.start("BT", create, run_async=False)
            (caseinfo / "thread1CaseInfo_2026-09-11.txt").write_text(
                "2026-09-11 05:44:20,000 SNRead: SERIAL000001\n", encoding="utf-8",
            )
            rounds.monitor.poll_once()

            self.assertEqual([(result.slot, result.status) for result in rounds.snapshot().results],
                             [(1, "WAITING"), (2, "WAITING"), (3, "TESTING")])
            event = next(item.event for item in rounds.snapshot().events if item.event.kind == "result")
            self.assertEqual(event.slot, 3)


if __name__ == "__main__":
    unittest.main()
