import unittest
import tempfile
from datetime import datetime
from pathlib import Path

from configured_monitor import ConfiguredMonitor
from log_monitoring import AtlasActiveArchiveMonitor, BtLogMonitor, MonitorEvent, SlotResult
from machine_profiles import MachineProfile, validate_profile
from monitoring_round import RoundCoordinator


class FakeMonitor:
    def __init__(self, callback):
        self.callback = callback
        self.results = {1: SlotResult(1), 2: SlotResult(2)}
        self.start_timeout_seconds = 30
        self.test_timeout_seconds = 480
        self.round_timeout_seconds = 7200
        self._published = False

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
        pass

    def poll_once(self):
        if self._published:
            return
        self._published = True
        self.results[1].status = "PASS"
        self.callback(MonitorEvent("result", "source 1 passed", 1, status="PASS"))

    def stop(self):
        pass

    def stop_collection(self):
        pass

    def finish(self):
        pass

    def set_result(self, slot, status, sn=None, source="", detail=None, lock_terminal=False):
        self.results[slot].status = status
        self.callback(MonitorEvent("result", "source {}".format(status), slot,
                                   sn or "", status, source, detail or {}))


class ConfiguredMonitorTests(unittest.TestCase):
    def test_capacity_fixtures_publish_mapped_positions_through_shared_round(self):
        for capacity in (4, 6, 10, 12, 20):
            with self.subTest(capacity=capacity):
                with tempfile.TemporaryDirectory() as temporary:
                    root = Path(temporary)
                    active, final = root / "active", root / "final"
                    active.mkdir()
                    final.mkdir()
                    sources = tuple(range(20, 20 - capacity, -1))
                    mapping = {source: display
                               for display, source in enumerate(sources, start=1)}

                    def create(callback):
                        holder = {}

                        def deliver(event):
                            return holder["view"].deliver(event, callback)

                        monitor = AtlasActiveArchiveMonitor(
                            "FCT", active, final, sources, callback=deliver,
                            session_root=root / "sessions",
                        )
                        holder["view"] = ConfiguredMonitor(monitor, mapping)
                        return holder["view"]

                    rounds = RoundCoordinator()
                    rounds.start("FCT", create, run_async=False)
                    for source in reversed(sources):
                        records = active / "group0-slot{}".format(source) / "system" / "records.csv"
                        records.parent.mkdir(parents=True)
                        records.write_text(
                            "MLB_SN,status\nSERIAL{:08d},Pass\n".format(source),
                            encoding="utf-8",
                        )
                    rounds.poll_once()
                    snapshot = rounds.snapshot()

                    self.assertEqual(len(snapshot.results), capacity)
                    self.assertEqual([result.slot for result in snapshot.results],
                                     list(range(1, capacity + 1)))
                    self.assertEqual(snapshot.results[0].sn, "SERIAL{:08d}".format(sources[0]))
                    self.assertEqual(snapshot.results[-1].sn, "SERIAL{:08d}".format(sources[-1]))
                    self.assertTrue(all(result.status == "TESTING" for result in snapshot.results))
                    self.assertEqual([event.event.slot for event in snapshot.events
                                      if event.event.kind == "sn_locked"],
                                     list(range(capacity, 0, -1)))
                    rounds.stop()

    def test_out_of_order_native_positions_map_to_configured_displays_in_round(self):
        class FourPositionMonitor:
            def __init__(self, callback):
                self.callback = callback
                self.results = {slot: SlotResult(slot) for slot in range(1, 5)}
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

            def stop_collection(self):
                pass

            def finish(self):
                pass

            def set_result(self, slot, status, sn=None, source="", detail=None, lock_terminal=False):
                self.results[slot].status = status
                self.callback(MonitorEvent("result", "source result", slot, sn or "", status,
                                           source, detail or {}))

            def start(self):
                pass

            def poll_once(self):
                for source, status in ((4, "FAIL"), (1, "PASS")):
                    self.results[source].status = status
                    self.callback(MonitorEvent("result", "source result", source, status=status))

            def stop(self):
                pass

        mapping = {1: 4, 2: 3, 3: 2, 4: 1}

        def create(callback):
            holder = {}
            monitor = FourPositionMonitor(lambda event: holder["view"].deliver(event, callback))
            holder["view"] = ConfiguredMonitor(monitor, mapping)
            return holder["view"]

        rounds = RoundCoordinator()
        rounds.start("BT", create, run_async=False)
        rounds.poll_once()
        snapshot = rounds.snapshot()

        self.assertEqual([(result.slot, result.status) for result in snapshot.results], [
            (1, "FAIL"), (2, "WAITING"), (3, "WAITING"), (4, "PASS"),
        ])
        self.assertEqual([event.event.slot for event in snapshot.events
                          if event.event.kind == "result"], [1, 4])

    def test_profile_mapping_is_visible_through_round_snapshot_and_events(self):
        def create(callback):
            holder = {}

            def deliver(event):
                return holder["view"].deliver(event, callback)

            monitor = FakeMonitor(deliver)
            configured = ConfiguredMonitor(monitor, {1: 2, 2: 1})
            holder["view"] = configured
            return configured

        rounds = RoundCoordinator()
        rounds.start("DFU", create, run_async=False)
        rounds.poll_once()

        snapshot = rounds.snapshot()
        self.assertEqual([(result.slot, result.status) for result in snapshot.results],
                         [(1, "WAITING"), (2, "PASS")])
        first_result = next(event for event in snapshot.events if event.event.kind == "result")
        self.assertEqual(first_result.event.slot, 2)

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
                    return holder["view"].deliver(event, callback)

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
            rounds.poll_once()

            self.assertEqual([(result.slot, result.status) for result in rounds.snapshot().results],
                             [(1, "WAITING"), (2, "WAITING"), (3, "TESTING")])
            event = next(item.event for item in rounds.snapshot().events if item.event.kind == "result")
            self.assertEqual(event.slot, 3)


if __name__ == "__main__":
    unittest.main()
