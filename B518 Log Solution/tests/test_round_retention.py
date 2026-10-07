import json
import shutil
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from log_monitoring import BaseMonitor
from monitoring_round import RoundCoordinator
import round_retention
from round_archival import write_round_archive


class CompleteMonitor(BaseMonitor):
    def __init__(self, callback, root, now):
        super().__init__("FCT", {}, (1,), callback=callback, session_root=root, now=now,
                         round_timeout_seconds=3600)
        self.done = False

    def poll_once(self):
        if not self.done:
            self.done = True
            self.set_result(1, "PASS", "SERIAL000001", "source.csv", {
                "round_evidence_id": "retention-test", "source_time": "2026-10-07T08:01:00",
            })


class RoundRetentionTests(unittest.TestCase):
    def wait_until(self, predicate):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.01)
        self.fail("timed out waiting for round retention")

    def make_archived_round(self, root, now):
        rounds = RoundCoordinator(audit_root=root / "sessions", wall_clock=lambda: now[0])
        started = rounds.start("FCT", lambda callback: CompleteMonitor(
            callback, root / "sessions", lambda: now[0]), run_async=False)
        rounds.poll_once()
        self.wait_until(lambda: (rounds.archive_status(started.round_id) is not None and
                                 rounds.archive_status(started.round_id).status == "archived"))
        return rounds, started.round_id

    def test_public_cleanup_removes_expired_round_and_persists_summary_for_fresh_reader(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            now = [datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc)]
            writer, round_id = self.make_archived_round(root, now)
            archive = writer.archive_status(round_id)
            protected_files = {
                root / "preferences.json": b'{"keep": true}',
                root / "manual-export.json": b'{"export": "keep"}',
                root / "source-log.txt": b"source log stays outside sessions",
            }
            for path, contents in protected_files.items():
                path.write_bytes(contents)
            now[0] = datetime.fromisoformat(archive.archived_at) + timedelta(days=366)
            rounds = RoundCoordinator(audit_root=root / "sessions", wall_clock=lambda: now[0])

            rounds.request_retention_cleanup(365)
            self.wait_until(lambda: rounds.retention_cleanup_status().status == "complete")

            self.assertFalse(archive.path.parent.exists())
            reader = RoundCoordinator(audit_root=root / "sessions",
                                      wall_clock=lambda: now[0],
                                      retention_ledger_path=root / "round-retention-ledger.json")
            summary = reader.retention_cleanup_summaries()
            self.assertEqual(len(summary), 1)
            self.assertEqual(summary[0].retention_days, 365)
            self.assertEqual(summary[0].deleted_round_ids, (round_id,),
                             (summary[0], list((root / "sessions").rglob("*"))))
            for path, contents in protected_files.items():
                self.assertEqual(path.read_bytes(), contents)
            self.assertEqual(json.loads((root / "round-retention-ledger.json").read_text())[
                "schema_version"], 2)

    def test_deadline_is_inclusive_and_a_round_before_deadline_is_preserved(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            now = [datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc)]
            writer, round_id = self.make_archived_round(root, now)
            archive = writer.archive_status(round_id)
            archived_at = datetime.fromisoformat(archive.archived_at)
            rounds = RoundCoordinator(audit_root=root / "sessions", wall_clock=lambda: now[0])

            now[0] = archived_at + timedelta(days=365) - timedelta(seconds=1)
            rounds.request_retention_cleanup(365)
            self.wait_until(lambda: rounds.retention_cleanup_status().status == "complete")
            self.assertTrue(archive.path.parent.exists())
            self.assertEqual(rounds.retention_cleanup_summaries()[-1].results[0].outcome, "skipped")

            previous_count = len(rounds.retention_cleanup_summaries())
            now[0] = archived_at + timedelta(days=365)
            rounds.request_retention_cleanup(365)
            self.wait_until(lambda: len(rounds.retention_cleanup_summaries()) == previous_count + 1 and
                            rounds.retention_cleanup_status().status == "complete")
            self.assertFalse(archive.path.parent.exists())

    def test_partial_delete_progress_resumes_from_fresh_coordinator(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            now = [datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc)]
            writer, _round_id = self.make_archived_round(root, now)
            archived = next(item for item in writer.archive_statuses() if item.cleanup_eligible)
            audit_path = next(item.path for item in archived.components if item.name == "audit.jsonl")
            session_path = next(item.path.parent for item in archived.components if item.name == "session.json")
            separate_audit_dir = root / "sessions" / "separate-audit" / archived.round_id
            separate_audit_dir.mkdir(parents=True)
            separate_audit = separate_audit_dir / "audit.jsonl"
            audit_path.replace(separate_audit)
            archived.path.unlink()
            archived = write_round_archive(
                separate_audit, session_path, datetime.fromisoformat(archived.archived_at),
                archived.round_id)
            now[0] = datetime.fromisoformat(archived.archived_at) + timedelta(days=366)
            rounds = RoundCoordinator(audit_root=root / "sessions", wall_clock=lambda: now[0])
            original_replace = round_retention.os.replace
            calls = [0]

            def fail_after_first_unlink(source, destination):
                calls[0] += 1
                if calls[0] == 4:
                    raise OSError("injected progress ledger failure")
                return original_replace(source, destination)

            with patch.object(round_retention.os, "replace", side_effect=fail_after_first_unlink):
                rounds.request_retention_cleanup(365)
                self.wait_until(lambda: rounds.retention_cleanup_status().status == "failed")
            self.assertTrue((root / "round-retention-ledger.json").exists())

            recovered = RoundCoordinator(audit_root=root / "sessions", wall_clock=lambda: now[0])
            previous_count = len(recovered.retention_cleanup_summaries())
            recovered.request_retention_cleanup(365)
            self.wait_until(lambda: len(recovered.retention_cleanup_summaries()) > previous_count and
                            recovered.retention_cleanup_status().status in {"complete", "failed"})
            self.assertEqual(recovered.retention_cleanup_status().status, "complete",
                             recovered.retention_cleanup_status())
            self.assertFalse(session_path.exists())
            self.assertFalse(separate_audit_dir.exists())
            self.assertTrue(any(item.outcome == "deleted" for item in
                                recovered.retention_cleanup_summaries()[-1].results))

    def test_final_summary_failure_keeps_completed_plan_for_fresh_reader(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            now = [datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc)]
            writer, round_id = self.make_archived_round(root, now)
            archive = writer.archive_status(round_id)
            now[0] = datetime.fromisoformat(archive.archived_at) + timedelta(days=366)
            rounds = RoundCoordinator(audit_root=root / "sessions", wall_clock=lambda: now[0])
            original_write = round_retention.RoundRetentionStore._write_ledger
            failed = []

            def fail_final_summary(store, payload):
                final = payload["runs"][-1]
                if (final.get("status") == "complete" and
                        any(item.get("outcome") == "deleted"
                            for item in final.get("results", [])) and not failed):
                    failed.append(True)
                    raise OSError("injected final summary failure")
                return original_write(store, payload)

            with patch.object(round_retention.RoundRetentionStore, "_write_ledger",
                              fail_final_summary):
                rounds.request_retention_cleanup(365)
                self.wait_until(lambda: rounds.retention_cleanup_status().status == "failed")

            self.assertFalse(archive.path.parent.exists())
            ledger = json.loads((root / "round-retention-ledger.json").read_text())
            self.assertTrue(ledger["active_plans"][round_id]["deletion_complete"])
            recovered = RoundCoordinator(audit_root=root / "sessions", wall_clock=lambda: now[0])
            before = len(recovered.retention_cleanup_summaries())
            recovered.request_retention_cleanup(365)
            self.wait_until(lambda: len(recovered.retention_cleanup_summaries()) > before and
                            recovered.retention_cleanup_status().status == "complete")

            self.assertEqual(recovered.retention_cleanup_summaries()[-1].deleted_round_ids,
                             (round_id,))
            ledger = json.loads((root / "round-retention-ledger.json").read_text())
            self.assertNotIn(round_id, ledger["active_plans"])

    def test_new_unknown_file_after_partial_delete_blocks_resume(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            now = [datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc)]
            writer, round_id = self.make_archived_round(root, now)
            archive = writer.archive_status(round_id)
            session_path = next(item.path.parent for item in archive.components
                                if item.name == "session.json")
            now[0] = datetime.fromisoformat(archive.archived_at) + timedelta(days=366)
            rounds = RoundCoordinator(audit_root=root / "sessions", wall_clock=lambda: now[0])
            original_unlink = round_retention.RoundRetentionStore._unlink_managed_file
            created = []

            def inject_unknown_after_unlink(store, path, expected, archived_at=None):
                original_unlink(store, path, expected, archived_at)
                if not created:
                    unknown = session_path / "new-operator-data.json"
                    unknown.write_text('{"keep": true}', encoding="utf-8")
                    created.append(unknown)
                    raise OSError("injected interruption after one deletion")

            with patch.object(round_retention.RoundRetentionStore, "_unlink_managed_file",
                              inject_unknown_after_unlink):
                rounds.request_retention_cleanup(365)
                self.wait_until(lambda: rounds.retention_cleanup_status().status == "failed")

            recovered = RoundCoordinator(audit_root=root / "sessions", wall_clock=lambda: now[0])
            previous_count = len(recovered.retention_cleanup_summaries())
            recovered.request_retention_cleanup(365)
            self.wait_until(lambda: len(recovered.retention_cleanup_summaries()) > previous_count and
                            recovered.retention_cleanup_status().status == "failed")

            self.assertEqual(recovered.retention_cleanup_status().status, "failed")
            self.assertTrue(created[0].exists())
            self.assertEqual(created[0].read_text(encoding="utf-8"), '{"keep": true}')
            self.assertTrue(archive.path.exists())
            ledger = json.loads((root / "round-retention-ledger.json").read_text())
            self.assertIn(round_id, ledger["active_plans"])

    def test_new_retention_days_stop_inflight_cleanup_before_first_unlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            now = [datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc)]
            writer, round_id = self.make_archived_round(root, now)
            archive = writer.archive_status(round_id)
            now[0] = datetime.fromisoformat(archive.archived_at) + timedelta(days=200)
            rounds = RoundCoordinator(audit_root=root / "sessions", wall_clock=lambda: now[0])
            entered = threading.Event()
            release = threading.Event()
            original_unlink = round_retention.RoundRetentionStore._unlink_managed_file

            def controlled_unlink(store, path, expected, archived_at=None):
                if not entered.is_set():
                    entered.set()
                    if not release.wait(3):
                        raise RuntimeError("test did not release cleanup")
                return original_unlink(store, path, expected, archived_at)

            previous_count = len(rounds.retention_cleanup_summaries())
            with patch.object(round_retention.RoundRetentionStore, "_unlink_managed_file",
                              controlled_unlink):
                rounds.request_retention_cleanup(180)
                self.assertTrue(entered.wait(2))
                rounds.retention_setting_changed(365)
                release.set()
                self.wait_until(lambda: len(rounds.retention_cleanup_summaries()) >= previous_count + 2 and
                                rounds.retention_cleanup_status().status in {"complete", "failed"})

            self.assertTrue(archive.path.parent.exists())
            self.assertEqual(rounds.retention_cleanup_summaries()[-1].retention_days, 365)
            self.assertIn("保存期限", rounds.retention_cleanup_summaries()[0].results[0].reason)

    def test_failed_partial_round_keeps_progress_while_next_candidate_is_cleaned(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            now = [datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc)]
            writer, first_id = self.make_archived_round(root, now)
            first = writer.archive_status(first_id)
            now[0] += timedelta(seconds=1)
            second_writer, second_id = self.make_archived_round(root, now)
            second = second_writer.archive_status(second_id)
            now[0] = datetime.fromisoformat(second.archived_at) + timedelta(days=366)
            rounds = RoundCoordinator(audit_root=root / "sessions", wall_clock=lambda: now[0])
            original_replace = round_retention.os.replace
            calls = [0]

            def fail_first_round_progress(source, destination):
                calls[0] += 1
                if calls[0] == 4:
                    raise OSError("injected first-round progress failure")
                return original_replace(source, destination)

            with patch.object(round_retention.os, "replace", side_effect=fail_first_round_progress):
                rounds.request_retention_cleanup(365)
                self.wait_until(lambda: rounds.retention_cleanup_status().status == "failed")

            ledger = json.loads((root / "round-retention-ledger.json").read_text())
            self.assertEqual(len(ledger["active_plans"]), 1)
            retained_id = next(iter(ledger["active_plans"]))
            self.assertIn(retained_id, {first_id, second_id})
            deleted_path = second.path.parent if retained_id == first_id else first.path.parent
            self.assertFalse(deleted_path.exists())

            resumed = RoundCoordinator(audit_root=root / "sessions", wall_clock=lambda: now[0])
            resumed.request_retention_cleanup(365)
            self.wait_until(lambda: resumed.retention_cleanup_status().status == "complete")
            remaining_path = first.path.parent if retained_id == first_id else second.path.parent
            self.assertFalse(remaining_path.exists())
            self.assertEqual(json.loads((root / "round-retention-ledger.json").read_text())[
                "active_plans"], {})

    def test_startup_and_full_24_hour_schedule_use_current_retention_value(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            now = [datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc)]
            mono = [5.0]
            writer, round_id = self.make_archived_round(root, now)
            archive = writer.archive_status(round_id)
            now[0] = datetime.fromisoformat(archive.archived_at) + timedelta(days=364)
            rounds = RoundCoordinator(audit_root=root / "sessions", wall_clock=lambda: now[0],
                                      monotonic=lambda: mono[0])

            rounds.start_retention_schedule(365)
            self.wait_until(lambda: rounds.retention_cleanup_status().status == "complete")
            self.assertTrue(archive.path.parent.exists())
            self.assertEqual(rounds.retention_cleanup_summaries()[-1].trigger, "app-startup")

            now[0] = datetime.fromisoformat(archive.archived_at) + timedelta(days=365)
            mono[0] += 24 * 60 * 60
            before = len(rounds.retention_cleanup_summaries())
            rounds.poll_retention_schedule(365)
            self.wait_until(lambda: len(rounds.retention_cleanup_summaries()) == before + 1)
            self.assertEqual(rounds.retention_cleanup_summaries()[-1].trigger, "24-hour-schedule")
            self.assertFalse(archive.path.parent.exists())

    def test_current_run_round_is_protected_and_close_suppresses_new_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            now = [datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc)]
            rounds, round_id = self.make_archived_round(root, now)
            archive = rounds.archive_status(round_id)
            now[0] = datetime.fromisoformat(archive.archived_at) + timedelta(days=366)
            rounds.request_retention_cleanup(365)
            self.wait_until(lambda: rounds.retention_cleanup_status().status == "complete")
            self.assertTrue(archive.path.parent.exists())
            self.assertEqual(rounds.retention_cleanup_summaries()[-1].results[0].outcome, "skipped")

            rounds.request_close()
            self.wait_until(lambda: rounds.close_status().status == "complete")
            before = len(rounds.retention_cleanup_summaries())
            blocked = rounds.request_retention_cleanup(365)
            self.assertEqual(blocked.status, "skipped")
            self.assertEqual(len(rounds.retention_cleanup_summaries()), before)

    def test_required_parts_split_across_directories_are_removed_as_one_round(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            now = [datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc)]
            writer, round_id = self.make_archived_round(root, now)
            original = writer.archive_status(round_id)
            audit_path = next(item.path for item in original.components if item.name == "audit.jsonl")
            session_path = next(item.path.parent for item in original.components if item.name == "session.json")
            audit_directory = root / "sessions" / "separate-audit" / round_id
            audit_directory.mkdir(parents=True)
            split_audit = audit_directory / "audit.jsonl"
            audit_path.replace(split_audit)
            original.path.unlink()
            split = write_round_archive(split_audit, session_path,
                                       datetime.fromisoformat(original.archived_at), round_id)
            self.assertEqual(split.status, "archived")
            now[0] = datetime.fromisoformat(split.archived_at) + timedelta(days=366)
            rounds = RoundCoordinator(audit_root=root / "sessions", wall_clock=lambda: now[0])

            rounds.request_retention_cleanup(365)
            self.wait_until(lambda: rounds.retention_cleanup_status().status in {"complete", "failed"})

            self.assertEqual(rounds.retention_cleanup_status().status, "complete",
                             rounds.retention_cleanup_status())
            self.assertFalse(session_path.exists())
            self.assertFalse(audit_directory.exists())
            self.assertEqual(rounds.retention_cleanup_summaries()[-1].deleted_round_ids, (round_id,))

    def test_same_named_unknown_file_in_other_round_directory_blocks_deletion(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            now = [datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc)]
            writer, round_id = self.make_archived_round(root, now)
            archive = writer.archive_status(round_id)
            audit_path = next(item.path for item in archive.components if item.name == "audit.jsonl")
            session_path = next(item.path.parent for item in archive.components
                                if item.name == "session.json")
            audit_directory = root / "sessions" / "separate-audit" / round_id
            audit_directory.mkdir(parents=True)
            separate_audit = audit_directory / "audit.jsonl"
            audit_path.replace(separate_audit)
            archive.path.unlink()
            archive = write_round_archive(separate_audit, session_path,
                                          datetime.fromisoformat(archive.archived_at), round_id)
            unknown = separate_audit.parent / "session.json"
            unknown.write_text('{"unowned": true}', encoding="utf-8")
            now[0] = datetime.fromisoformat(archive.archived_at) + timedelta(days=366)
            rounds = RoundCoordinator(audit_root=root / "sessions", wall_clock=lambda: now[0])

            rounds.request_retention_cleanup(365)
            self.wait_until(lambda: rounds.retention_cleanup_status().status == "complete")

            self.assertTrue(archive.path.exists())
            self.assertTrue(session_path.exists())
            self.assertEqual(unknown.read_text(encoding="utf-8"), '{"unowned": true}')
            result = next(item for item in rounds.retention_cleanup_summaries()[-1].results
                          if item.round_id == round_id)
            self.assertEqual(result.outcome, "skipped")

    def test_symlinked_component_to_external_data_is_preserved_and_reported(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            now = [datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc)]
            writer, round_id = self.make_archived_round(root, now)
            archive = writer.archive_status(round_id)
            result_path = next(item.path for item in archive.components if item.name == "results.csv")
            external = root / "external-results.csv"
            external.write_bytes(result_path.read_bytes())
            result_path.unlink()
            result_path.symlink_to(external)
            now[0] = datetime.fromisoformat(archive.archived_at) + timedelta(days=366)
            rounds = RoundCoordinator(audit_root=root / "sessions", wall_clock=lambda: now[0])

            rounds.request_retention_cleanup(365)
            self.wait_until(lambda: rounds.retention_cleanup_status().status == "complete")

            self.assertTrue(external.exists())
            self.assertTrue(result_path.is_symlink())
            self.assertTrue(archive.path.exists())
            self.assertEqual(rounds.retention_cleanup_summaries()[-1].results[0].outcome, "skipped")

    def test_parent_replaced_with_external_symlink_during_unlink_cannot_delete_external_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            now = [datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc)]
            writer, round_id = self.make_archived_round(root, now)
            archive = writer.archive_status(round_id)
            managed_session_dir = next(item.path.parent for item in archive.components
                                       if item.name == "session.json")
            external_dir = root / "external-copy"
            shutil.copytree(str(managed_session_dir), str(external_dir))
            external_audit = external_dir / "audit.jsonl"
            original_external_bytes = external_audit.read_bytes()
            now[0] = datetime.fromisoformat(archive.archived_at) + timedelta(days=366)
            rounds = RoundCoordinator(audit_root=root / "sessions", wall_clock=lambda: now[0])
            entered = threading.Event()
            release = threading.Event()
            original_unlinkat = round_retention._unlinkat

            def controlled_unlinkat(directory_fd, name, flags=0):
                if name in {"audit.jsonl", "events.log", "results.csv", "session.json"} and not entered.is_set():
                    entered.set()
                    if not release.wait(3):
                        raise RuntimeError("test did not release directory-handle race")
                return original_unlinkat(directory_fd, name, flags)

            with patch.object(round_retention, "_unlinkat", side_effect=controlled_unlinkat):
                rounds.request_retention_cleanup(365)
                self.assertTrue(entered.wait(2))
                detached = root / "detached-managed-round"
                managed_session_dir.replace(detached)
                managed_session_dir.symlink_to(external_dir, target_is_directory=True)
                release.set()
                self.wait_until(lambda: rounds.retention_cleanup_status().status in {"complete", "failed"})

            self.assertEqual(external_audit.read_bytes(), original_external_bytes)
            self.assertTrue((managed_session_dir / "audit.jsonl").is_symlink() or
                            managed_session_dir.is_symlink())
            self.assertEqual(rounds.retention_cleanup_summaries()[-1].status, "failed")

    def test_corrupt_round_is_skipped_and_summary_write_failure_prevents_deletion(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            now = [datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc)]
            writer, round_id = self.make_archived_round(root, now)
            archive = writer.archive_status(round_id)
            results_path = next(item.path for item in archive.components if item.name == "results.csv")
            now[0] = datetime.fromisoformat(archive.archived_at) + timedelta(days=366)
            rounds = RoundCoordinator(audit_root=root / "sessions", wall_clock=lambda: now[0])
            results_path.write_text("tampered\n", encoding="utf-8")

            rounds.request_retention_cleanup(365)
            self.wait_until(lambda: rounds.retention_cleanup_status().status == "complete")
            self.assertTrue(archive.path.parent.exists())
            self.assertEqual(rounds.retention_cleanup_summaries()[-1].results[0].outcome, "skipped")

            intact_root = root / "intact"
            intact_now = [datetime(2024, 1, 1, 8, 0, tzinfo=timezone.utc)]
            intact_writer, intact_id = self.make_archived_round(intact_root, intact_now)
            intact_archive = intact_writer.archive_status(intact_id)
            now[0] = datetime.fromisoformat(intact_archive.archived_at) + timedelta(days=366)
            failing = RoundCoordinator(audit_root=intact_root / "sessions",
                                       wall_clock=lambda: now[0])
            with patch.object(round_retention.os, "replace", side_effect=OSError("ledger unavailable")):
                failing.request_retention_cleanup(365)
                self.wait_until(lambda: failing.retention_cleanup_status().status == "failed")
            self.assertIn("未刪除資料", failing.retention_cleanup_status().message)
            self.assertTrue(intact_archive.path.parent.exists())

    def test_corrupt_round_does_not_stop_another_safe_candidate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            now = [datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc)]
            writer, first_id = self.make_archived_round(root, now)
            first = writer.archive_status(first_id)
            now[0] += timedelta(seconds=1)
            second_writer, second_id = self.make_archived_round(root, now)
            second = second_writer.archive_status(second_id)
            first_results = next(item.path for item in first.components if item.name == "results.csv")
            first_results.write_text("corrupt\n", encoding="utf-8")
            now[0] = datetime.fromisoformat(second.archived_at) + timedelta(days=366)
            rounds = RoundCoordinator(audit_root=root / "sessions", wall_clock=lambda: now[0])

            rounds.request_retention_cleanup(365)
            self.wait_until(lambda: rounds.retention_cleanup_status().status == "complete")

            self.assertTrue(first.path.parent.exists())
            self.assertFalse(second.path.parent.exists())
            results = {item.round_id: item.outcome for item in
                       rounds.retention_cleanup_summaries()[-1].results}
            self.assertEqual(results[first_id], "skipped")
            self.assertEqual(results[second_id], "deleted")

    def test_corrupt_persistent_progress_is_visible_and_prevents_deletion(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            now = [datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc)]
            writer, round_id = self.make_archived_round(root, now)
            archive = writer.archive_status(round_id)
            now[0] = datetime.fromisoformat(archive.archived_at) + timedelta(days=366)
            ledger = root / "round-retention-ledger.json"
            ledger.write_text("not-json", encoding="utf-8")
            rounds = RoundCoordinator(audit_root=root / "sessions", wall_clock=lambda: now[0],
                                      retention_ledger_path=ledger)

            self.assertEqual(rounds.retention_cleanup_status().status, "failed")
            self.assertIn("無法讀取", rounds.retention_cleanup_status().message)
            rounds.request_retention_cleanup(365)
            self.wait_until(lambda: rounds.retention_cleanup_status().status == "failed")

            self.assertTrue(archive.path.exists())
            self.assertTrue(archive.path.parent.exists())

    def test_successful_retention_setting_change_rechecks_all_trusted_rounds(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            now = [datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc)]
            writer, round_id = self.make_archived_round(root, now)
            archive = writer.archive_status(round_id)
            now[0] = datetime.fromisoformat(archive.archived_at) + timedelta(days=200)
            rounds = RoundCoordinator(audit_root=root / "sessions", wall_clock=lambda: now[0])

            rounds.start_retention_schedule(365)
            self.wait_until(lambda: rounds.retention_cleanup_status().status == "complete")
            self.assertTrue(archive.path.parent.exists())
            before = len(rounds.retention_cleanup_summaries())
            rounds.retention_setting_changed(180)
            self.wait_until(lambda: len(rounds.retention_cleanup_summaries()) == before + 1 and
                            rounds.retention_cleanup_status().status == "complete")

            self.assertFalse(archive.path.parent.exists())
            self.assertEqual(rounds.retention_cleanup_summaries()[-1].retention_days, 180)
            self.assertEqual(rounds.retention_cleanup_summaries()[-1].trigger, "setting-changed")

    def test_cleanup_already_scanning_is_coordinated_with_close(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            now = [datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc)]
            writer, round_id = self.make_archived_round(root, now)
            archive = writer.archive_status(round_id)
            now[0] = datetime.fromisoformat(archive.archived_at) + timedelta(days=366)
            rounds = RoundCoordinator(audit_root=root / "sessions", wall_clock=lambda: now[0])
            entered = threading.Event()
            release = threading.Event()
            original_read = round_retention.read_round_archive

            def controlled_read(path, expected_round_id=None):
                if Path(path).name == "round-archive.json" and not entered.is_set():
                    entered.set()
                    self.assertTrue(release.wait(2))
                return original_read(path, expected_round_id)

            with patch.object(round_retention, "read_round_archive", side_effect=controlled_read):
                rounds.request_retention_cleanup(365)
                self.assertTrue(entered.wait(2))
                closing = rounds.request_close()
                self.assertIn(closing.status, {"saving", "waiting"})
                release.set()
                self.wait_until(lambda: rounds.close_status().status == "complete")
                self.wait_until(lambda: rounds.retention_cleanup_status().status == "complete")

            self.assertTrue(archive.path.parent.exists())
            self.assertEqual(rounds.retention_cleanup_summaries()[-1].results[0].outcome, "skipped")

    def test_triggers_during_cleanup_coalesce_into_one_follow_up_run(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            now = [datetime(2026, 10, 7, 8, 0, tzinfo=timezone.utc)]
            writer, round_id = self.make_archived_round(root, now)
            archive = writer.archive_status(round_id)
            now[0] = datetime.fromisoformat(archive.archived_at) + timedelta(days=366)
            rounds = RoundCoordinator(audit_root=root / "sessions", wall_clock=lambda: now[0])
            entered = threading.Event()
            release = threading.Event()
            original_read = round_retention.read_round_archive

            def controlled_read(path, expected_round_id=None):
                if Path(path).name == "round-archive.json" and not entered.is_set():
                    entered.set()
                    self.assertTrue(release.wait(2))
                return original_read(path, expected_round_id)

            with patch.object(round_retention, "read_round_archive", side_effect=controlled_read):
                rounds.request_retention_cleanup(365, "app-startup")
                self.assertTrue(entered.wait(2))
                rounds.request_retention_cleanup(180, "setting-changed")
                rounds.request_retention_cleanup(90, "setting-changed")
                release.set()
                self.wait_until(lambda: len(rounds.retention_cleanup_summaries()) == 2 and
                                rounds.retention_cleanup_status().status == "complete")

            summaries = rounds.retention_cleanup_summaries()
            self.assertEqual(len(summaries), 2)
            self.assertEqual(summaries[0].retention_days, 365)
            self.assertEqual(summaries[1].retention_days, 90)
            self.assertFalse(archive.path.parent.exists())
