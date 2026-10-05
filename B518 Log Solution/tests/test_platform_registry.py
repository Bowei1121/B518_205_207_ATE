import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from configured_monitor import ConfiguredMonitor
from machine_profiles import MachineProfile, ProfileCatalog, ProfileError
from monitoring_round import RoundCoordinator
from platform_registry import DEFAULT_PLATFORM_REGISTRY, PlatformDefinition, PlatformRegistry
from sample_json_monitor import SampleJsonLinesSource


class PlatformRegistryTests(unittest.TestCase):
    def test_json_lines_source_ignores_startup_history_and_waits_for_complete_records(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "events.jsonl"
            path.write_text(
                '{"kind":"final","position":1,"status":"PASS",'
                '"batch_id":"old-run"}\n', encoding="utf-8")
            source = SampleJsonLinesSource(root, (1,))
            self.assertEqual(source.poll(), ())

            with path.open("a", encoding="utf-8") as handle:
                handle.write('{"kind":"activity","position":1,"sn":"SAMPLE000001"')
            self.assertEqual(source.poll(), ())
            with path.open("a", encoding="utf-8") as handle:
                handle.write('}\n')
            observed = source.poll()

            self.assertEqual(len(observed), 1)
            self.assertEqual(observed[0].status, "TESTING")
            evidence = observed[0].evidence()
            self.assertEqual(evidence["source_time"], "unknown")
            self.assertNotIn("round_evidence_id", evidence)
            with path.open("a", encoding="utf-8") as handle:
                handle.write('{"kind":"final","position":1,"status":"MYSTERY"}\n')
                handle.write('not-json\n')
            diagnostics = source.poll()
            self.assertEqual(len(diagnostics), 2)
            self.assertTrue(all(item.kind == "warning" and item.source_time == ""
                                for item in diagnostics))

    def test_registered_sample_format_is_selectable_by_project_and_machine(self):
        definition = DEFAULT_PLATFORM_REGISTRY.get("sample-json")
        self.assertEqual(definition.machines, ("FCT",))
        self.assertEqual(definition.source_positions, tuple(range(1, 21)))
        self.assertEqual(definition.required_paths, ("active",))

        profile = MachineProfile(
            "SAMPLE", "FCT", "sample-json", 2,
            {"active": "/not/on/this/computer"}, ((20, 1), (4, 2)),
            {"start": 30, "test": 60, "round": 600},
        )
        catalog = ProfileCatalog((profile,))
        self.assertEqual(catalog.get("SAMPLE", "FCT").platform, "sample-json")
        self.assertEqual(catalog.projects, ("SAMPLE",))

    def test_unknown_platform_remains_rejected_after_registration(self):
        profile = MachineProfile(
            "SAMPLE", "FCT", "unregistered-format", 1,
            {"active": "/tmp/source"}, ((1, 1),),
            {"start": 30, "test": 60, "round": 600},
        )
        with self.assertRaisesRegex(ProfileError, "未知平台"):
            ProfileCatalog((profile,))

    def test_sample_adapter_activity_final_and_conflict_use_shared_round_and_mapping(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            evidence_file = source / "events.jsonl"
            evidence_file.write_text("", encoding="utf-8")
            mapping = {20: 1, 4: 2}
            registry = DEFAULT_PLATFORM_REGISTRY
            rounds = RoundCoordinator(audit_root=root / "sessions")

            def monitor_factory(callback):
                holder = {}

                def deliver(event):
                    view = holder.get("view")
                    return view.deliver(event, callback) if view else callback(event)

                monitor = registry.create_monitor(
                    "sample-json", station="FCT", paths={"active": source},
                    source_slots=tuple(mapping), callback=deliver,
                    timeouts={"start": 30, "test": 60, "round": 600},
                    session_root=root / "sessions", async_session_writes=False,
                )
                view = ConfiguredMonitor(monitor, mapping)
                holder["view"] = view
                return view

            initial = rounds.start("FCT", monitor_factory, run_async=False,
                                   capacity=2, round_timeout_seconds=600,
                                   audit_context={"project": "SAMPLE", "machine": "FCT",
                                                  "platform": "sample-json", "profile_version": 1})
            self.assertFalse(initial.result_available)

            records = (
                '{"kind":"activity","position":20,"sn":"SAMPLE000020",'
                '"source_time":"2026-10-05T09:00:00","batch_id":"fixture-run-7"}\n'
                '{"kind":"final","position":20,"sn":"SAMPLE000020","status":"PASS",'
                '"source_time":"2026-10-05T09:00:03","batch_id":"fixture-run-7"}\n'
                '{"kind":"final","position":4,"sn":"SAMPLE000004","status":"FAIL",'
                '"source_time":"2026-10-05T09:00:04","batch_id":"fixture-run-7"}\n'
                '{"kind":"final","position":4,"sn":"SAMPLE000004","status":"PASS",'
                '"source_time":"2026-10-05T09:00:05","batch_id":"fixture-run-7"}\n'
                '{"kind":"final","position":7,"status":"FAIL"}\n'
            )
            evidence_file.write_text(records, encoding="utf-8")
            rounds.poll_once()
            snapshot = rounds.snapshot()

            self.assertEqual([(item.slot, item.sn, item.status) for item in snapshot.results], [
                (1, "SAMPLE000020", "PASS"), (2, "SAMPLE000004", "FAIL"),
            ])
            self.assertEqual(len(snapshot.pending_conflicts), 1, snapshot.events)
            self.assertFalse(snapshot.result_available)
            self.assertFalse(any(event.event.status == "TESTING" and event.event.slot == 2
                                 for event in snapshot.events))
            unmapped = next(event.event for event in snapshot.events
                            if event.event.kind == "unmapped_source")
            self.assertEqual(unmapped.detail["source_position"], "7")
            self.assertEqual(unmapped.detail["source_time"], "unknown")
            self.assertNotIn("round_evidence_id", unmapped.detail)
            conflict = snapshot.pending_conflicts[0]
            self.assertEqual(dict(conflict.same_round_evidence)["round_evidence_id"],
                             "sample-json:fixture-run-7:4")

            rounds.resolve_review(conflict.conflict_id, "accept_candidate")
            released = rounds.snapshot()
            self.assertTrue(released.result_available)
            self.assertEqual(released.results[1].status, "PASS")
            self.assertTrue(rounds.flush_audit())

            from audit_records import read_round_audit
            rebuilt = read_round_audit(rounds.monitor.session.path / "audit.jsonl")
            self.assertTrue(rebuilt["result_available"])
            self.assertEqual([(slot, value["status"]) for slot, value in sorted(rebuilt["results"].items())],
                             [(1, "PASS"), (2, "PASS")])

    def test_registry_rejects_duplicate_names_and_builds_registered_adapter(self):
        registry = PlatformRegistry()
        factory = lambda **context: context
        definition = PlatformDefinition(
            "test", ("FCT",), (1,), ("active",), (),
            {"active": "來源"}, factory,
        )
        registry.register(definition)
        with self.assertRaisesRegex(ValueError, "重複"):
            registry.register(definition)
        built = registry.create_monitor(
            "test", station="FCT", paths={"active": Path("/tmp")},
            source_slots=(1,), callback=lambda _event: None,
            timeouts={"start": 1, "test": 1, "round": 2},
            session_root=Path("/tmp"), async_session_writes=False,
        )
        self.assertEqual(built["station"], "FCT")


if __name__ == "__main__":
    unittest.main()
