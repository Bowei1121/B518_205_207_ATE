import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from audit_records import read_round_audit
from machine_profiles import MachineProfile
from monitoring_round import RoundCoordinator
from round_start_preparation import RoundStartPreparation


class RoundStartPreparationTests(unittest.TestCase):
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
