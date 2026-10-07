import hashlib
import json
import shutil
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from audit_records import AuditEvent, RoundAuditStore, read_round_audit
from log_monitoring import BaseMonitor, SessionStore
from log_monitoring import MonitorEvent
from monitoring_round import RoundCoordinator
from round_archival import read_round_archive, write_round_archive


class CompletingMonitor(BaseMonitor):
    def __init__(self, callback, root, now):
        super().__init__("FCT", {}, (1,), callback=callback, session_root=root,
                         now=now, round_timeout_seconds=3600)
        self.completed = False

    def poll_once(self):
        if not self.completed:
            self.completed = True
            self.set_result(1, "PASS", "SERIAL000001", "source.csv", {
                "round_evidence_id": "test-round-1", "source_time": "2026-10-07T08:01:00",
            })


class RoundArchivalTests(unittest.TestCase):
    def wait_for_state(self, coordinator, round_id, states):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            status = coordinator.archive_status(round_id)
            if status and status.status in states:
                return status
            time.sleep(0.01)
        self.fail("timed out waiting for round archive status: {}".format(
            (coordinator.archive_status(round_id), coordinator.round_snapshot(round_id))))

    def wait_for_archive(self, coordinator, round_id):
        return self.wait_for_state(coordinator, round_id, {"archived", "failed"})

    def test_completed_round_is_archived_by_coordinator_using_actual_injected_time(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            now = [datetime(2026, 10, 7, 8, 0, tzinfo=timezone(timedelta(hours=8)))]
            rounds = RoundCoordinator(audit_root=root / "sessions", wall_clock=lambda: now[0])
            started = rounds.start("FCT", lambda callback: CompletingMonitor(
                callback, root / "sessions", lambda: now[0]), run_async=False)
            rounds.poll_once()
            now[0] += timedelta(days=3)
            rounds.retry_archival(started.round_id)

            status = self.wait_for_archive(rounds, started.round_id)

            self.assertEqual(status.status, "archived")
            self.assertEqual(status.archived_at, now[0].isoformat(timespec="seconds"))
            rebuilt = read_round_archive(status.path, expected_round_id=started.round_id)
            self.assertEqual(rebuilt.status, "archived")

    def test_round_with_pending_conflict_is_protected_until_operator_resolves_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            now = [datetime(2026, 10, 7, 8, 0, tzinfo=timezone(timedelta(hours=8)))]

            class ConflictMonitor(CompletingMonitor):
                def poll_once(self):
                    if not self.completed:
                        self.completed = True
                        detail = {"round_evidence_id": "test-round-1",
                                  "source_time": "2026-10-07T08:01:00", "source_id": "first.csv"}
                        self.set_result(1, "PASS", "SERIAL000001", "first.csv", detail)
                        self.callback(MonitorEvent(
                            "result_candidate", "corrected candidate", 1, "SERIAL000001", "FAIL",
                            "corrected.csv", dict(detail, source_id="corrected.csv")))

            rounds = RoundCoordinator(audit_root=root / "sessions", wall_clock=lambda: now[0])
            started = rounds.start("FCT", lambda callback: ConflictMonitor(
                callback, root / "sessions", lambda: now[0]), run_async=False)
            rounds.poll_once()
            pending = self.wait_for_state(rounds, started.round_id, {"protected"})
            self.assertEqual(pending.status, "protected")
            self.assertIn("待確認", pending.message)
            self.assertTrue(rounds.has_unarchived_rounds)
            self.assertEqual(list(root.rglob("round-archive.json")), [])

            now[0] += timedelta(days=3)
            conflict_id = rounds.snapshot().pending_conflicts[0].conflict_id
            rounds.resolve_review(conflict_id, "keep_original")
            archived = self.wait_for_archive(rounds, started.round_id)
            self.assertEqual(archived.status, "archived")
            self.assertEqual(archived.archived_at, now[0].isoformat(timespec="seconds"))

    def test_manual_stop_and_pending_alarm_only_archive_after_required_operator_work(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            now = [datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc)]
            elapsed = [0.0]
            rounds = RoundCoordinator(audit_root=root / "sessions", wall_clock=lambda: now[0],
                                      monotonic=lambda: elapsed[0])
            stopped = rounds.start("FCT", lambda callback: CompletingMonitor(
                callback, root / "sessions", lambda: now[0]), run_async=False)
            rounds.stop()
            manual_archive = self.wait_for_archive(rounds, stopped.round_id)
            self.assertEqual(manual_archive.status, "archived")

            class AlarmMonitor(BaseMonitor):
                def __init__(self, callback):
                    super().__init__("FCT", {}, (1,), callback=callback, session_root=root / "sessions",
                                     now=lambda: now[0], monotonic=lambda: elapsed[0],
                                     round_timeout_seconds=5)

                def poll_once(self):
                    return

            now[0] += timedelta(minutes=1)
            alarm_round = rounds.start("FCT", AlarmMonitor, run_async=False)
            elapsed[0] = 5.0
            expired = rounds.poll_once()
            protected = self.wait_for_state(rounds, alarm_round.round_id, {"protected"})
            self.assertIn("警報", protected.message)
            self.assertEqual(expired.round_alarm.acknowledged_at, "")

            rounds.acknowledge_round_alarm(alarm_round.round_id, expired.round_alarm.alarm_id)
            alarm_archive = self.wait_for_archive(rounds, alarm_round.round_id)
            self.assertEqual(alarm_archive.status, "archived")

    def test_source_preparation_in_progress_cannot_be_archived_early(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            entered = threading.Event()
            release = threading.Event()
            now = datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc)

            def prepare(callback):
                entered.set()
                release.wait(2)
                return CompletingMonitor(callback, root / "sessions", lambda: now)

            rounds = RoundCoordinator(audit_root=root / "sessions", wall_clock=lambda: now)
            started = rounds.start("FCT", prepare, run_async=True)
            self.assertTrue(entered.wait(2))
            protected = rounds.archive_status(started.round_id)
            self.assertNotEqual(protected.status, "archived")
            self.assertEqual(list(root.rglob("round-archive.json")), [])

            release.set()
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                snapshot = rounds.round_snapshot(started.round_id)
                if snapshot and not snapshot.source_preparation_pending:
                    break
                time.sleep(0.01)
            rounds.stop()
            archived = self.wait_for_archive(rounds, started.round_id)
            self.assertEqual(archived.status, "archived")

    def test_new_persisted_event_invalidates_then_reseals_the_previous_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            now = [datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc)]
            rounds = RoundCoordinator(audit_root=root / "sessions", wall_clock=lambda: now[0])
            holder = {}
            started = rounds.start("FCT", lambda callback: holder.setdefault(
                "monitor", CompletingMonitor(callback, root / "sessions", lambda: now[0])),
                run_async=False)
            rounds.poll_once()
            first = self.wait_for_archive(rounds, started.round_id)
            self.assertEqual(first.status, "archived")

            now[0] += timedelta(days=1)
            self.assertTrue(rounds.retry_saves(started.round_id))
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                status = rounds.archive_status(started.round_id)
                if status and status.status == "archived" and status.archived_at != first.archived_at:
                    break
                time.sleep(0.01)
            self.assertEqual(status.status, "archived")
            self.assertNotEqual(status.archived_at, first.archived_at)
            self.assertTrue(read_round_archive(status.path, started.round_id).cleanup_eligible)

    def test_archive_check_racing_a_new_round_event_seals_the_latest_disk_contents(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            now = [datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc)]
            archive_check_entered = threading.Event()
            release_archive_check = threading.Event()
            clock_lock = threading.Lock()
            block_background_clock = [False]

            def wall_clock():
                should_block = False
                with clock_lock:
                    if block_background_clock[0] and threading.current_thread() is not threading.main_thread():
                        block_background_clock[0] = False
                        should_block = True
                if should_block:
                    archive_check_entered.set()
                    release_archive_check.wait(2)
                return now[0]

            rounds = RoundCoordinator(audit_root=root / "sessions", wall_clock=wall_clock)
            started = rounds.start("FCT", lambda callback: CompletingMonitor(
                callback, root / "sessions", lambda: now[0]), run_async=False)
            self.wait_for_state(rounds, started.round_id, {"protected"})
            with clock_lock:
                block_background_clock[0] = True
            rounds.poll_once()
            self.assertTrue(archive_check_entered.wait(2))

            self.assertTrue(rounds.retry_saves(started.round_id))
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                snapshot = rounds.round_snapshot(started.round_id)
                if snapshot and any(event.event.kind == "save_recovered" for event in snapshot.events):
                    break
                time.sleep(0.01)
            self.assertTrue(snapshot and any(event.event.kind == "save_recovered"
                                             for event in snapshot.events))
            self.assertTrue(rounds.has_unarchived_rounds)
            state_before_seal = rounds.round_snapshot(started.round_id)
            self.assertTrue(state_before_seal.collection_stopped,
                            (state_before_seal.state, state_before_seal.collection_stopped))
            self.assertIsNotNone(rounds.round_snapshot(started.round_id))
            release_archive_check.set()

            archived = self.wait_for_archive(rounds, started.round_id)
            self.assertEqual(archived.status, "archived")
            rebuilt = read_round_archive(archived.path, started.round_id)
            self.assertTrue(rebuilt.cleanup_eligible)
            audit = read_round_audit(next(item.path for item in rebuilt.components
                                          if item.name == "audit.jsonl"))
            self.assertEqual(audit["events"][-1]["kind"], "save_recovered")

    def test_failed_archive_write_stays_protected_then_retry_seals(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            now = [datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc)]
            rounds = RoundCoordinator(audit_root=root / "sessions", wall_clock=lambda: now[0])
            started = rounds.start("FCT", lambda callback: CompletingMonitor(
                callback, root / "sessions", lambda: now[0]), run_async=False)
            import round_archival
            original_replace = round_archival.os.replace

            def fail_archive_replace(source, destination):
                if str(destination).endswith("round-archive.json"):
                    raise OSError("temporary archive disk fault")
                return original_replace(source, destination)

            with patch.object(round_archival.os, "replace", side_effect=fail_archive_replace):
                rounds.poll_once()
                failed = self.wait_for_archive(rounds, started.round_id)
                self.assertEqual(failed.status, "failed")
                self.assertIn("temporary archive disk fault", failed.message)
                self.assertFalse(failed.cleanup_eligible)
                self.assertTrue(rounds.has_unarchived_rounds)

            self.assertTrue(rounds.retry_archival(started.round_id))
            recovered = self.wait_for_state(rounds, started.round_id, {"archived"})
            self.assertEqual(recovered.status, "archived")

    def test_normal_close_waits_for_archive_write_repair_and_retry(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            now = [datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc)]
            rounds = RoundCoordinator(audit_root=root / "sessions", wall_clock=lambda: now[0])
            started = rounds.start("FCT", lambda callback: CompletingMonitor(
                callback, root / "sessions", lambda: now[0]), run_async=False)
            import round_archival
            original_replace = round_archival.os.replace

            def fail_archive_replace(source, destination):
                if str(destination).endswith("round-archive.json"):
                    raise OSError("archive device unavailable")
                return original_replace(source, destination)

            with patch.object(round_archival.os, "replace", side_effect=fail_archive_replace):
                rounds.poll_once()
                failed = self.wait_for_state(rounds, started.round_id, {"failed"})
                self.assertIn("archive device unavailable", failed.message)
                rounds.request_close()
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline and rounds.close_status().status != "failed":
                    time.sleep(0.01)
                self.assertEqual(rounds.close_status().status, "failed")
                self.assertIn("封存資訊保存失敗", rounds.close_status().message)

            rounds.retry_close_saves()
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline and rounds.close_status().status != "complete":
                time.sleep(0.01)
            self.assertEqual(rounds.close_status().status, "complete")
            self.assertTrue(read_round_archive(
                rounds.archive_status(started.round_id).path, started.round_id).cleanup_eligible)

    def create_complete_round(self, root, round_id="round-archive"):
        session = SessionStore(round_id, {"round_id": round_id}, root / "sessions")
        session.enqueue_event("round stopped", {"round_id": round_id})
        session.update_results(())
        session.finish("2026-10-07T09:00:00")
        audit = RoundAuditStore(root / "audit", round_id, "FCT",
                                "2026-10-07T08:00:00", 0.0)
        audit.append_event(AuditEvent(1, "collection_stopped", "round stopped", None,
                                      detail={"round_id": round_id}),
                           "2026-10-07T09:00:00", 3600.0)
        self.assertTrue(audit.flush())
        return audit.audit_path, session.path

    def test_archive_round_can_be_verified_from_disk_and_binds_every_session_piece(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            audit_path, session_path = self.create_complete_round(root)

            archived = write_round_archive(
                audit_path, session_path,
                datetime(2026, 10, 7, 9, 30, tzinfo=timezone.utc),
            )
            rebuilt = read_round_archive(archived.path, expected_round_id="round-archive")

            self.assertEqual(rebuilt.status, "archived")
            self.assertEqual(rebuilt.archived_at, "2026-10-07T09:30:00+00:00")
            self.assertEqual({item.name for item in rebuilt.components},
                             {"audit.jsonl", "session.json", "events.log", "results.csv"})

            repeated = write_round_archive(
                audit_path, session_path,
                datetime(2026, 10, 8, 9, 30, tzinfo=timezone.utc),
            )
            self.assertEqual(repeated.archived_at, "2026-10-07T09:30:00+00:00")

            results = session_path / "results.csv"
            results.write_text("slot,sn,status,source,updated_at\n", encoding="utf-8")
            changed = read_round_archive(archived.path, expected_round_id="round-archive")
            self.assertEqual(changed.status, "protected")
            rearchived = write_round_archive(
                audit_path, session_path,
                datetime(2026, 10, 8, 9, 30, tzinfo=timezone.utc),
            )
            self.assertEqual(rearchived.archived_at, "2026-10-08T09:30:00+00:00")

            payload = json.loads(rearchived.path.read_text(encoding="utf-8"))
            payload["archived_at"] = "2026-10-08T09:30:00"
            rearchived.path.write_text(json.dumps(payload), encoding="utf-8")
            tampered = read_round_archive(rearchived.path, expected_round_id="round-archive")
            self.assertEqual(tampered.status, "protected")
            self.assertIn("完整性", tampered.message)

    def test_missing_or_unknown_archive_metadata_keeps_old_round_protected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "legacy" / "round-archive.json"
            missing = read_round_archive(path, expected_round_id="legacy-round")
            self.assertEqual(missing.status, "protected")
            self.assertIn("無法讀取", missing.message)

            path.parent.mkdir()
            path.write_text(json.dumps({"record_type": "round_archive", "schema_version": 99,
                                        "round_id": "legacy-round"}), encoding="utf-8")
            unknown = read_round_archive(path, expected_round_id="legacy-round")
            self.assertEqual(unknown.status, "protected")
            self.assertIn("版本未知", unknown.message)

    def test_archive_time_must_have_timezone_and_legacy_session_stays_readable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            audit_path, session_path = self.create_complete_round(root)

            with self.assertRaises(ValueError):
                write_round_archive(audit_path, session_path, datetime(2026, 10, 7, 9, 30))

            (session_path / "session.json").write_text(json.dumps({
                "schema_version": 1, "settings": {}, "started_at": "2020-01-01T00:00:00",
                "finished_at": "2020-01-01T01:00:00", "sources": [],
            }), encoding="utf-8")
            with self.assertRaises(ValueError):
                write_round_archive(
                    audit_path, session_path,
                    datetime(2026, 10, 7, 9, 30, tzinfo=timezone.utc),
                )

    def test_disk_archival_rejects_unresolved_conflicts_and_alarms(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cases = (
                ("unresolved-conflict", "conflict_detected", {"conflict_id": "conflict-1"}, "衝突"),
                ("unacknowledged-alarm", "round_alarm_created", {"alarm_id": "alarm-1"}, "警報"),
            )
            for round_id, kind, detail, expected_reason in cases:
                with self.subTest(kind=kind):
                    audit_path, session_path = self.create_complete_round(root, round_id)
                    original = write_round_archive(
                        audit_path, session_path,
                        datetime(2026, 10, 7, 9, 30, tzinfo=timezone.utc),
                    )
                    audit = RoundAuditStore(root / "audit", round_id, "FCT",
                                            "2026-10-07T08:00:00", 0.0)
                    audit.append_event(AuditEvent(2, kind, "pending operator action", 1,
                                                  detail=detail),
                                       "2026-10-07T09:01:00", 3660.0)
                    self.assertTrue(audit.flush())
                    manifest = json.loads(original.path.read_text(encoding="utf-8"))
                    component = next(item for item in manifest["components"]
                                     if item["name"] == "audit.jsonl")
                    audit_bytes = audit_path.read_bytes()
                    component["size"] = len(audit_bytes)
                    component["sha256"] = hashlib.sha256(audit_bytes).hexdigest()
                    manifest.pop("seal_sha256")
                    canonical = json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                                           separators=(",", ":")).encode("utf-8")
                    manifest["seal_sha256"] = hashlib.sha256(canonical).hexdigest()
                    original.path.write_text(json.dumps(manifest), encoding="utf-8")
                    disk_status = read_round_archive(original.path, expected_round_id=round_id)
                    self.assertFalse(disk_status.cleanup_eligible)
                    self.assertIn(expected_reason, disk_status.message)
                    with self.assertRaisesRegex(ValueError, expected_reason):
                        write_round_archive(
                            audit_path, session_path,
                            datetime(2026, 10, 7, 9, 30, tzinfo=timezone.utc),
                        )

    def test_disk_archival_rejects_parseable_but_incomplete_session_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for missing_field in ("started_at", "sources"):
                with self.subTest(field=missing_field):
                    audit_path, session_path = self.create_complete_round(
                        root, "missing-" + missing_field)
                    metadata_path = session_path / "session.json"
                    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                    metadata.pop(missing_field)
                    metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "Session"):
                        write_round_archive(
                            audit_path, session_path,
                            datetime(2026, 10, 7, 9, 30, tzinfo=timezone.utc),
                        )

    def test_archive_writer_requires_the_coordinators_expected_round_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            audit_path, session_path = self.create_complete_round(Path(temporary), "round-a")
            with self.assertRaisesRegex(ValueError, "輪次身分不一致"):
                write_round_archive(
                    audit_path, session_path,
                    datetime(2026, 10, 7, 9, 30, tzinfo=timezone.utc),
                    expected_round_id="round-b",
                )

    def test_detached_retry_rejects_a_consistent_replacement_from_another_round(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            now = [datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc)]
            rounds = RoundCoordinator(audit_root=root / "sessions", wall_clock=lambda: now[0])
            first = rounds.start("FCT", lambda callback: CompletingMonitor(
                callback, root / "sessions", lambda: now[0]), run_async=False)
            rounds.poll_once()
            first_archive = self.wait_for_archive(rounds, first.round_id)
            self.assertEqual(first_archive.status, "archived")
            first_audit = next(item.path for item in first_archive.components
                               if item.name == "audit.jsonl")
            first_session = next(item.path.parent for item in first_archive.components
                                 if item.name == "session.json")

            now[0] += timedelta(seconds=1)
            rounds.start("FCT", lambda callback: CompletingMonitor(
                callback, root / "sessions", lambda: now[0]), run_async=False)
            self.assertIsNone(rounds.round_snapshot(first.round_id))

            replacement_audit, replacement_session = self.create_complete_round(
                root / "replacement", "replacement-round")
            shutil.copyfile(replacement_audit, first_audit)
            for name in ("session.json", "events.log", "results.csv"):
                shutil.copyfile(replacement_session / name, first_session / name)

            self.assertTrue(rounds.retry_archival(first.round_id))
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                status = rounds.archive_status(first.round_id)
                if status and status.status == "protected" and "身分不一致" in status.message:
                    break
                time.sleep(0.01)
            self.assertEqual(status.status, "protected")
            self.assertIn("身分不一致", status.message)

    def test_close_stays_open_when_a_detached_round_fails_disk_verification(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            now = [datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc)]
            rounds = RoundCoordinator(audit_root=root / "sessions", wall_clock=lambda: now[0])
            started = rounds.start("FCT", lambda callback: CompletingMonitor(
                callback, root / "sessions", lambda: now[0]), run_async=False)
            rounds.poll_once()
            archived = self.wait_for_archive(rounds, started.round_id)
            self.assertEqual(archived.status, "archived")
            now[0] += timedelta(seconds=1)
            rounds.start("FCT", lambda callback: CompletingMonitor(
                callback, root / "sessions", lambda: now[0]), run_async=False)
            self.assertIsNone(rounds.round_snapshot(started.round_id))
            audit_component = next(item for item in archived.components if item.name == "audit.jsonl")
            audit_bytes = audit_component.path.read_bytes()
            audit_component.path.unlink()

            rounds.request_close()
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline and rounds.close_status().status not in {"complete", "failed"}:
                time.sleep(0.01)
            self.assertEqual(rounds.close_status().status, "failed")
            self.assertIn("封存", rounds.close_status().message)

            audit_component.path.write_bytes(audit_bytes)
            rounds.retry_close_saves()
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline and rounds.close_status().status != "complete":
                time.sleep(0.01)
            self.assertEqual(rounds.close_status().status, "complete")


if __name__ == "__main__":
    unittest.main()
