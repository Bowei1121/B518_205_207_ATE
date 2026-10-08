import json
import os
import threading
import time
import unittest
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from audit_records import read_round_audit
from machine_profiles import MachineProfile, ProfileError
from monitoring_round import RoundCoordinator
from platform_registry import DEFAULT_PLATFORM_REGISTRY, PlatformRegistry
from round_start_preparation import RoundStartPreparation


class RoundStartPreparationTests(unittest.TestCase):
    def test_required_paths_must_be_present_directories_readable_and_enterable(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            regular_file = root / "not-a-directory"
            regular_file.write_text("source", encoding="utf-8")
            preparation = RoundStartPreparation()

            for configured in ("", "   ", str(root / "missing"), str(regular_file)):
                with self.subTest(path=configured):
                    profile = MachineProfile(
                        "SAMPLE", "FCT", "sample-json", 1,
                        {"active": configured}, ((1, 1),),
                        {"start": 30, "test": 60, "round": 600},
                    )
                    with self.assertRaisesRegex(ProfileError, "受控 JSON Lines 樣本來源"):
                        preparation.prepare(profile, root / "sessions")

            inaccessible = root / "inaccessible"
            inaccessible.mkdir()
            inaccessible.chmod(0)
            try:
                self.assertFalse(os.access(str(inaccessible), os.R_OK | os.X_OK))
                profile = MachineProfile(
                    "SAMPLE", "FCT", "sample-json", 1,
                    {"active": str(inaccessible)}, ((1, 1),),
                    {"start": 30, "test": 60, "round": 600},
                )
                with self.assertRaisesRegex(ProfileError, "受控 JSON Lines 樣本來源"):
                    preparation.prepare(profile, root / "sessions")
            finally:
                inaccessible.chmod(0o700)

    def test_blank_optional_path_is_omitted_but_invalid_nonblank_path_is_rejected(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            results = root / "results"
            results.mkdir()
            preparation = RoundStartPreparation()
            blank_optional = MachineProfile(
                "B482", "BT", "b482", 1,
                {"final": str(results), "caseinfo": "   "}, ((1, 1),),
                {"start": 30, "test": 60, "round": 600},
            )
            prepared = preparation.prepare(blank_optional, root / "sessions")
            self.assertEqual(prepared.station, "BT")

            invalid_optional = MachineProfile(
                "B482", "BT", "b482", 1,
                {"final": str(results), "caseinfo": str(root / "missing-caseinfo")},
                ((1, 1),), {"start": 30, "test": 60, "round": 600},
            )
            with self.assertRaisesRegex(ProfileError, "B482 CaseInfo／進度路徑（選填）"):
                preparation.prepare(invalid_optional, root / "sessions")

    def test_all_registered_platforms_start_through_the_preparation_interface(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            cases = (
                ("B518", "DFU", "atlas", {"active": "active", "final": "final"}, 2),
                ("B518", "FCT", "atlas", {"active": "active", "final": "final"}, 2),
                ("B482", "BT", "b482", {"final": "final", "caseinfo": ""}, 4),
                ("B518", "BT", "rswmt", {"final": "final", "caseinfo": ""}, 3),
                ("SAMPLE", "FCT", "sample-json", {"active": "active"}, 20),
            )
            for index, (project, machine, platform, configured, source_position) in enumerate(cases):
                with self.subTest(platform=platform):
                    case_root = root / str(index)
                    resolved = {}
                    for field, relative in configured.items():
                        if not relative:
                            resolved[field] = relative
                            continue
                        path = case_root / relative
                        path.mkdir(parents=True, exist_ok=True)
                        if platform == "sample-json":
                            (path / "events.jsonl").write_text("", encoding="utf-8")
                        resolved[field] = str(path)
                    profile = MachineProfile(
                        project, machine, platform, 1, resolved,
                        ((source_position, 1),),
                        {"start": 30, "test": 60, "round": 600},
                    )
                    sessions = case_root / "sessions"
                    coordinator = RoundCoordinator(audit_root=sessions)
                    prepared = RoundStartPreparation().prepare(profile, sessions)
                    started = prepared.start(coordinator, run_async=False)
                    self.assertEqual(started.station, machine)
                    self.assertEqual(started.results[0].slot, 1)
                    self.assertIsNotNone(coordinator.session_path)
                    self.assertTrue(coordinator.flush_session(timeout=2))
                    self.assertTrue(coordinator.flush_audit(timeout=2))
                    self.assertTrue((coordinator.session_path / "session.json").is_file())
                    self.assertTrue((coordinator.session_path / "audit.jsonl").is_file())
                    coordinator.stop()
                    self.assertTrue(coordinator.flush_session(timeout=2))
                    self.assertTrue(coordinator.flush_audit(timeout=2))

    def test_stopping_while_source_is_preparing_keeps_round_stopped_after_factory_returns(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            (source / "events.jsonl").write_text("", encoding="utf-8")
            factory_entered = threading.Event()
            release_factory = threading.Event()
            monitor_created = threading.Event()
            round_events = []
            base_factory = DEFAULT_PLATFORM_REGISTRY.get("sample-json").monitor_factory

            def delayed_factory(**context):
                factory_entered.set()
                if not release_factory.wait(3):
                    raise AssertionError("The controlled source factory was never released.")
                monitor = base_factory(**context)
                monitor_created.set()
                return monitor

            registry = PlatformRegistry()
            for name in DEFAULT_PLATFORM_REGISTRY.names:
                definition = DEFAULT_PLATFORM_REGISTRY.get(name)
                if name == "sample-json":
                    definition = replace(definition, monitor_factory=delayed_factory)
                registry.register(definition)

            profile = MachineProfile(
                "SAMPLE", "FCT", "sample-json", 1, {"active": str(source)},
                ((1, 1),), {"start": 30, "test": 60, "round": 600},
            )
            sessions = root / "sessions"
            coordinator = RoundCoordinator(audit_root=sessions)
            prepared = RoundStartPreparation(registry).prepare(profile, sessions)
            started = prepared.start(coordinator, run_async=True)
            self.assertTrue(factory_entered.wait(2))
            self.assertEqual(started.round_id, coordinator.snapshot().round_id)

            stopped = coordinator.stop()
            self.assertEqual(stopped.state.value, "STOPPED")
            release_factory.set()
            self.assertTrue(monitor_created.wait(2))

            closing = coordinator.request_close()
            self.assertEqual(closing.status, "saving")
            deadline = time.monotonic() + 3
            while coordinator.close_status().status not in {"complete", "failed"}:
                if time.monotonic() >= deadline:
                    self.fail("Close coordination did not finish after source preparation returned.")
                threading.Event().wait(0.01)

            self.assertEqual(coordinator.close_status().status, "complete")
            deadline = time.monotonic() + 3
            while not all(status.cleanup_eligible for status in coordinator.archive_statuses()):
                if time.monotonic() >= deadline:
                    self.fail("Public archive status did not confirm the background archive write.")
                threading.Event().wait(0.01)
            self.assertTrue(coordinator.flush_session(timeout=2))
            self.assertTrue(coordinator.flush_audit(timeout=2))
            rebuilt = read_round_audit(coordinator.session_path / "audit.jsonl")
            self.assertEqual(rebuilt["round"]["round_id"], started.round_id)
            self.assertIn("collection_stopped", [event["kind"] for event in rebuilt["events"]])
            self.assertNotIn("round_ready", [event["kind"] for event in rebuilt["events"]])

    def test_source_creation_failure_through_preparation_is_audited_before_close_completes(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            (source / "events.jsonl").write_text("", encoding="utf-8")
            factory_entered = threading.Event()
            release_factory = threading.Event()
            failure_reported = threading.Event()

            def failing_factory(**_context):
                factory_entered.set()
                if not release_factory.wait(3):
                    raise AssertionError("The controlled source factory was never released.")
                raise OSError("controlled source creation failure")

            def on_event(event):
                if event.event.kind == "start_failed":
                    failure_reported.set()

            registry = PlatformRegistry()
            for name in DEFAULT_PLATFORM_REGISTRY.names:
                definition = DEFAULT_PLATFORM_REGISTRY.get(name)
                if name == "sample-json":
                    definition = replace(definition, monitor_factory=failing_factory)
                registry.register(definition)

            profile = MachineProfile(
                "SAMPLE", "FCT", "sample-json", 1, {"active": str(source)},
                ((1, 1),), {"start": 30, "test": 60, "round": 600},
            )
            sessions = root / "sessions"
            coordinator = RoundCoordinator(on_event=on_event, audit_root=sessions)
            prepared = RoundStartPreparation(registry).prepare(profile, sessions)
            started = prepared.start(coordinator, run_async=True)
            self.assertTrue(factory_entered.wait(2))
            closing = coordinator.request_close()
            self.assertEqual(closing.status, "saving")
            self.assertFalse(failure_reported.is_set())

            release_factory.set()
            self.assertTrue(failure_reported.wait(2))
            deadline = time.monotonic() + 3
            while coordinator.close_status().status not in {"complete", "failed"}:
                if time.monotonic() >= deadline:
                    self.fail("Close coordination did not finish after source failure was recorded: "
                              "{}; snapshot={!r}; archive={!r}".format(
                                  coordinator.close_status(), coordinator.snapshot(),
                                  coordinator.archive_statuses()))
                threading.Event().wait(0.01)

            self.assertEqual(coordinator.close_status().status, "complete")
            snapshot = coordinator.snapshot()
            self.assertEqual(snapshot.round_id, started.round_id)
            self.assertEqual(snapshot.completion_reason, "start_failed")
            start_failures = [item for item in snapshot.events if item.event.kind == "start_failed"]
            self.assertEqual(len(start_failures), 1)
            rebuilt = read_round_audit(sessions / started.round_id / "audit.jsonl")
            persisted_failures = [event for event in rebuilt["events"]
                                  if event["kind"] == "start_failed"]
            self.assertEqual(len(persisted_failures), 1)
            self.assertIn("controlled source creation failure", persisted_failures[0]["message"])

    def test_injected_round_deadline_during_preparation_stops_late_source_before_ready(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            (source / "events.jsonl").write_text("", encoding="utf-8")
            elapsed = [0.0]
            started_at = datetime(2026, 10, 8, 9, 0, 0)
            factory_entered = threading.Event()
            release_factory = threading.Event()
            monitor_created = threading.Event()
            base_factory = DEFAULT_PLATFORM_REGISTRY.get("sample-json").monitor_factory

            def delayed_factory(**context):
                factory_entered.set()
                if not release_factory.wait(3):
                    raise AssertionError("The controlled source factory was never released.")
                monitor = base_factory(**context)
                monitor_created.set()
                return monitor

            registry = PlatformRegistry()
            for name in DEFAULT_PLATFORM_REGISTRY.names:
                definition = DEFAULT_PLATFORM_REGISTRY.get(name)
                if name == "sample-json":
                    definition = replace(definition, monitor_factory=delayed_factory)
                registry.register(definition)

            profile = MachineProfile(
                "SAMPLE", "FCT", "sample-json", 1, {"active": str(source)},
                ((1, 1),), {"start": 30, "test": 60, "round": 5},
            )
            sessions = root / "sessions"
            coordinator = RoundCoordinator(
                monotonic=lambda: elapsed[0], audit_root=sessions,
                wall_clock=lambda: started_at,
            )
            preparation = RoundStartPreparation(registry)
            prepared = preparation.prepare(
                profile, sessions, now=lambda: started_at,
                monotonic=lambda: elapsed[0],
            )
            started = prepared.start(coordinator, run_async=True)
            self.assertTrue(factory_entered.wait(2))

            elapsed[0] = 5.0
            expired = coordinator.poll_once()
            self.assertTrue(expired.collection_stopped)
            self.assertEqual(expired.round_alarm.created_at, started_at.isoformat(timespec="seconds"))
            self.assertFalse(expired.round_alarm_ready)
            self.assertFalse(expired.result_available)

            release_factory.set()
            self.assertTrue(monitor_created.wait(2))
            deadline = time.monotonic() + 3
            while not coordinator.snapshot().round_alarm_ready:
                if time.monotonic() >= deadline:
                    self.fail("The late source did not complete deadline handoff.")
                threading.Event().wait(0.01)

            handed_off = coordinator.snapshot()
            self.assertEqual(handed_off.round_id, started.round_id)
            self.assertFalse(any(item.event.kind == "round_ready" for item in handed_off.events))
            self.assertTrue(coordinator.acknowledge_round_alarm(
                started.round_id, handed_off.round_alarm.alarm_id).result_available)
            coordinator.request_close()
            deadline = time.monotonic() + 3
            while coordinator.close_status().status not in {"complete", "failed"}:
                if time.monotonic() >= deadline:
                    self.fail("Close coordination did not finish after deadline handoff.")
                threading.Event().wait(0.01)
            self.assertEqual(coordinator.close_status().status, "complete")
            deadline = time.monotonic() + 3
            while not all(status.cleanup_eligible for status in coordinator.archive_statuses()):
                if time.monotonic() >= deadline:
                    self.fail("Public archive status did not confirm the background archive write.")
                threading.Event().wait(0.01)
            self.assertTrue(coordinator.flush_session(timeout=2))
            self.assertTrue(coordinator.flush_audit(timeout=2))

    def test_prepared_profile_starts_real_round_and_persists_matching_session_and_audit(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            event_file = source / "events.jsonl"
            event_file.write_text("", encoding="utf-8")
            paths = {"active": str(source)}
            mapping = ((20, 1), (4, 2))
            timeouts = {"start": 30, "test": 60, "round": 600}
            profile = MachineProfile(
                "SAMPLE", "FCT", "sample-json", 2, paths, mapping, timeouts,
            )
            sessions = root / "sessions"
            prepared = RoundStartPreparation().prepare(profile, sessions)

            # A round uses the values captured during preparation even if the
            # engineer's original profile dictionaries are later edited.
            paths["active"] = str(root / "changed-after-prepare")
            mapping = ((1, 1), (2, 2))
            timeouts["round"] = 1

            coordinator = RoundCoordinator(audit_root=sessions)
            started = prepared.start(coordinator, run_async=False)
            self.assertEqual(started.station, "FCT")
            self.assertEqual([(result.slot, result.status) for result in started.results], [
                (1, "WAITING"), (2, "WAITING"),
            ])

            event_file.write_text(
                '{"kind":"final","position":20,"sn":"ASSEMBLY000020",'
                '"status":"PASS","source_time":"2026-10-08T09:00:00",'
                '"batch_id":"round-start-r1"}\n'
                '{"kind":"final","position":4,"sn":"ASSEMBLY000004",'
                '"status":"FAIL","source_time":"2026-10-08T09:00:01",'
                '"batch_id":"round-start-r1"}\n',
                encoding="utf-8",
            )
            completed = coordinator.poll_once()
            self.assertEqual([(result.slot, result.sn, result.status)
                              for result in completed.results], [
                (1, "ASSEMBLY000020", "PASS"), (2, "ASSEMBLY000004", "FAIL"),
            ])
            self.assertTrue(coordinator.flush_session(timeout=2))
            self.assertTrue(coordinator.flush_audit(timeout=2))

            session_path = coordinator.session_path
            session = json.loads((session_path / "session.json").read_text(encoding="utf-8"))
            session_profile = session["settings"]["profile_snapshot"]["profile"]
            self.assertEqual(session_profile["paths"]["active"], str(source))
            self.assertEqual(session_profile["mapping"], [
                {"source": 20, "display": 1}, {"source": 4, "display": 2},
            ])
            rebuilt = read_round_audit(session_path / "audit.jsonl")
            audit_config = rebuilt["round"]["config"]
            self.assertEqual(audit_config["config_snapshot"]["paths"]["active"], str(source))
            self.assertEqual(audit_config["mapping"], [
                {"source": 20, "display": 1}, {"source": 4, "display": 2},
            ])
            self.assertEqual([(slot, value["status"])
                              for slot, value in sorted(rebuilt["results"].items())], [
                (1, "PASS"), (2, "FAIL"),
            ])


if __name__ == "__main__":
    unittest.main()
