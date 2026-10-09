import json
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from app_event_store import AppEventStore, read_app_event_store


class AppEventStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "app-events.json"
        self.now = [datetime(2026, 10, 8, 1, 2, 3, tzinfo=timezone.utc)]
        self.store = AppEventStore(self.path, clock=lambda: self.now[0])
        self.addCleanup(self.store.stop)

    def wait_until(self, predicate, timeout=2):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(.01)
        self.assertTrue(predicate())

    def test_app_event_is_one_versioned_bilingual_record_without_round_identity(self):
        parameters = {"profile": "ATE", "nested": {"path": "/tmp/a"}}
        event = self.store.record("app.hotkey.unavailable", parameters, "OS permission denied")
        parameters["nested"]["path"] = "/tmp/changed"

        self.assertTrue(self.store.flush())
        rebuilt = read_app_event_store(self.path)
        self.assertEqual(rebuilt["schema_version"], 1)
        self.assertEqual(len(rebuilt["events"]), 1)
        record = rebuilt["events"][0]
        self.assertEqual(record["event_id"], event.event_id)
        self.assertEqual(record["occurred_at"], "2026-10-08T01:02:03.000000+00:00")
        self.assertEqual(record["sequence"], 1)
        self.assertNotIn("round_id", record)
        self.assertEqual(record["localized_message"]["version"], 1)
        self.assertEqual(record["localized_message"]["message_id"], "app.hotkey.unavailable")
        self.assertEqual(record["localized_message"]["parameters"]["nested"]["path"], "/tmp/a")
        self.assertEqual(record["localized_message"]["en"], "Global hotkey is unavailable")
        self.assertEqual(record["localized_message"]["zh-TW"], "全域快捷鍵無法使用")
        self.assertEqual(record["diagnostic"], "OS permission denied")

    def test_public_revision_changes_when_events_are_captured_not_when_pending_drains(self):
        initial_revision = self.store.revision
        event = self.store.record("app.hotkey.unavailable", {}, "permission denied")
        captured_revision = self.store.revision
        self.assertGreater(captured_revision, initial_revision)
        self.assertTrue(self.store.flush())
        self.assertEqual(self.store.revision, captured_revision)
        self.assertEqual(self.store.records[-1]["event_id"], event.event_id)

    def test_failed_write_keeps_same_event_for_ordered_retry_and_disk_rebuild(self):
        entered = threading.Event()
        release = threading.Event()
        from app_event_store import _atomic_replace

        def blocked_replace(path, content):
            if not entered.is_set():
                entered.set()
                release.wait(10)
                raise OSError("disk full")
            return _atomic_replace(path, content)

        with patch("app_event_store._atomic_replace", side_effect=blocked_replace):
            first = self.store.record("app.profile.save_failed", {"reason": "read-only"}, "read-only")
            second = self.store.record("app.hotkey.unavailable", {}, "permission")
            self.assertTrue(entered.wait(2))
            self.wait_until(lambda: self.store.status().pending_count == 2)
            release.set()
            self.wait_until(lambda: self.store.status().status == "failed")
            self.assertFalse(self.store.flush(.05))
            protected = self.store.cleanup_expired(
                self.now[0] + timedelta(days=30), Path(self.temp.name))
            self.assertEqual(protected.status, "skipped")
            self.assertEqual(protected.skipped_count, 1)
        self.assertEqual(self.store.status().pending_count, 2)
        self.assertTrue(self.store.retry())
        self.assertTrue(self.store.flush())

        events = read_app_event_store(self.path)["events"]
        self.assertEqual([item["event_id"] for item in events], [first.event_id,
                         second.event_id])
        self.assertEqual([item["sequence"] for item in events], [1, 2])
        self.assertEqual(len({item["event_id"] for item in events}), 2)
        self.assertEqual(events[0]["localized_message"]["message_id"], "app.profile.save_failed")
        self.assertEqual(events[0]["diagnostic"], "read-only")

    def test_initialization_failure_retains_diagnostic_and_recovers_after_directory_repair(self):
        blocked = Path(self.temp.name) / "not-a-directory"
        blocked.write_text("occupied", encoding="utf-8")
        store = AppEventStore(blocked / "events.json", clock=lambda: self.now[0])
        self.addCleanup(store.stop)
        event = store.record("app.event_store.write_failed", {"reason": "blocked"}, "blocked")
        self.wait_until(lambda: store.status().status == "failed")
        self.assertEqual(store.status().status, "failed")
        self.assertEqual(store.status().pending_count, 1)
        self.assertFalse(store.flush(.05))

        blocked.unlink()
        self.assertTrue(store.retry())
        self.assertTrue(store.flush())
        rebuilt = read_app_event_store(blocked / "events.json")
        self.assertEqual(rebuilt["events"][0]["event_id"], event.event_id)
        self.assertEqual(rebuilt["events"][0]["diagnostic"], "blocked")

    def test_replace_that_succeeds_then_reports_failure_is_not_duplicated_on_retry(self):
        from app_event_store import _atomic_replace
        event = self.store.record("app.profile.save_failed", {"reason": "late error"}, "late error")
        did_report = [False]

        def replace_then_report_error(path, content):
            _atomic_replace(path, content)
            if not did_report[0]:
                did_report[0] = True
                raise OSError("replace completed but acknowledgement failed")

        with patch("app_event_store._atomic_replace", side_effect=replace_then_report_error):
            self.wait_until(lambda: self.store.status().status == "failed")
            self.assertEqual([item["event_id"] for item in
                              read_app_event_store(self.path)["events"]], [event.event_id])
            self.assertTrue(self.store.retry())
            self.assertTrue(self.store.flush())
        rebuilt = read_app_event_store(self.path)["events"]
        self.assertEqual([item["event_id"] for item in rebuilt], [event.event_id])
        self.assertEqual([item["sequence"] for item in rebuilt], [1])

    def test_retention_removes_only_expired_events_and_preserves_live_identity_and_sequence(self):
        expired = self.store.record("app.hotkey.unavailable", {}, "old permission")
        self.assertTrue(self.store.flush())
        self.now[0] += timedelta(days=10)
        retained = self.store.record("app.profile.save_failed", {"reason": "new"}, "new failure")
        self.assertTrue(self.store.flush())

        result = self.store.cleanup_expired(
            self.now[0] - timedelta(days=5), Path(self.temp.name))

        rebuilt = read_app_event_store(self.path)
        self.assertEqual(result.deleted_count, 1)
        self.assertEqual(result.skipped_count, 1)
        self.assertEqual([item["event_id"] for item in rebuilt["events"]], [retained.event_id])
        self.assertEqual([item["sequence"] for item in rebuilt["events"]], [2])
        self.assertEqual(rebuilt["events"][0]["diagnostic"], "new failure")
        self.assertEqual(rebuilt["retired_sequences"], [[1, 1]])
        self.assertEqual(rebuilt["schema_version"], 2)

        next_event = self.store.record("app.hotkey.unavailable", {}, "later")
        self.assertTrue(self.store.flush())
        rebuilt = read_app_event_store(self.path)
        self.assertEqual(next_event.sequence, 3)
        self.assertEqual([item["sequence"] for item in rebuilt["events"]], [2, 3])

    def test_retention_keeps_corrupt_or_unknown_journal_bytes(self):
        self.store.record("app.hotkey.unavailable", {}, "diagnostic")
        self.assertTrue(self.store.flush())
        original = self.path.read_bytes()
        self.path.write_bytes(original + b"corruption")
        corrupt = self.path.read_bytes()

        result = self.store.cleanup_expired(
            self.now[0] + timedelta(days=30), Path(self.temp.name))

        self.assertEqual(result.status, "failed")
        self.assertEqual(self.path.read_bytes(), corrupt)

    def test_retention_uses_absolute_instant_for_deadline_comparison(self):
        old = self.store.record("app.hotkey.unavailable", {}, "old")
        self.assertTrue(self.store.flush())
        same_instant_other_offset = datetime(2026, 10, 8, 9, 2, 3,
                                             tzinfo=timezone(timedelta(hours=8)))

        result = self.store.cleanup_expired(
            same_instant_other_offset, Path(self.temp.name))

        self.assertEqual(result.deleted_count, 1)
        self.assertEqual(read_app_event_store(self.path)["events"], [])
        self.assertEqual(result.status, "complete")

    def test_retention_deadline_is_inclusive_and_preserves_event_just_before_cutoff(self):
        event = self.store.record("app.hotkey.unavailable", {}, "boundary")
        self.assertTrue(self.store.flush())
        event_time = datetime.fromisoformat(event.occurred_at)

        before = self.store.cleanup_expired(
            event_time - timedelta(microseconds=1), Path(self.temp.name))
        self.assertEqual(before.deleted_count, 0)
        self.assertEqual(len(read_app_event_store(self.path)["events"]), 1)

        at_deadline = self.store.cleanup_expired(event_time, Path(self.temp.name))
        self.assertEqual(at_deadline.deleted_count, 1)
        self.assertEqual(read_app_event_store(self.path)["events"], [])

    def test_retention_refuses_event_journal_symlink_to_external_file(self):
        self.store.record("app.hotkey.unavailable", {}, "protected")
        self.assertTrue(self.store.flush())
        outside = Path(self.temp.name) / "outside.json"
        outside.write_bytes(self.path.read_bytes())
        original = outside.read_bytes()
        self.path.unlink()
        self.path.symlink_to(outside)

        result = self.store.cleanup_expired(
            self.now[0] + timedelta(days=30), Path(self.temp.name))

        self.assertEqual(result.status, "skipped")
        self.assertEqual(outside.read_bytes(), original)
        self.assertTrue(self.path.is_symlink())

    def test_retention_parent_swap_cannot_redirect_replace_outside_managed_directory(self):
        parent = Path(self.temp.name) / "managed"
        parent.mkdir()
        managed_store_path = parent / "app-events.json"
        store = AppEventStore(managed_store_path, clock=lambda: self.now[0])
        self.addCleanup(store.stop)
        store.record("app.hotkey.unavailable", {}, "protected")
        self.assertTrue(store.flush())
        original_managed_bytes = managed_store_path.read_bytes()
        outside_dir = Path(self.temp.name) / "outside"
        outside_dir.mkdir()
        outside = outside_dir / managed_store_path.name
        outside.write_bytes(b"external sentinel")
        original_external_bytes = outside.read_bytes()
        moved_parent = Path(self.temp.name) / "managed-moved"

        def replace_after_swap(instant, commit):
            parent.rename(moved_parent)
            parent.symlink_to(outside_dir, target_is_directory=True)
            commit()

        result = store.cleanup_expired(
            self.now[0] + timedelta(days=30), Path(self.temp.name),
            before_replace=replace_after_swap)

        self.assertEqual(result.status, "failed")
        self.assertEqual(outside.read_bytes(), original_external_bytes)
        self.assertEqual((moved_parent / managed_store_path.name).read_bytes(), original_managed_bytes)

    def test_retention_ancestor_swap_before_managed_root_pin_cannot_reach_external_journal(self):
        base = Path(self.temp.name) / "managed-parent"
        managed_root = base / "app"
        managed_root.mkdir(parents=True)
        managed_store_path = managed_root / "app-events.json"
        store = AppEventStore(managed_store_path, clock=lambda: self.now[0])
        self.addCleanup(store.stop)
        store.record("app.hotkey.unavailable", {}, "protected")
        self.assertTrue(store.flush())

        external_parent = Path(self.temp.name) / "external-parent"
        external_root = external_parent / "app"
        external_root.mkdir(parents=True)
        external_journal = external_root / managed_store_path.name
        external_store = AppEventStore(external_journal, clock=lambda: self.now[0])
        external_store.record("app.hotkey.unavailable", {}, "external sentinel")
        self.assertTrue(external_store.flush())
        external_store.stop()
        external_bytes = external_journal.read_bytes()
        moved_base = Path(self.temp.name) / "managed-parent-moved"

        from app_event_store import _open_managed_directory as real_open_managed_directory
        swapped = [False]

        def swap_ancestor_before_pin(root, parts):
            if not swapped[0]:
                swapped[0] = True
                base.rename(moved_base)
                base.symlink_to(external_parent, target_is_directory=True)
            return real_open_managed_directory(root, parts)

        with patch("app_event_store._open_managed_directory",
                   side_effect=swap_ancestor_before_pin):
            result = store.cleanup_expired(
                self.now[0] + timedelta(days=30), managed_root)

        self.assertEqual(result.status, "failed")
        self.assertEqual(external_journal.read_bytes(), external_bytes)
        self.assertTrue((moved_base / "app" / managed_store_path.name).exists())

    def test_directory_fsync_failure_keeps_event_pending_until_retry_confirms_durability(self):
        real_fsync = __import__("os").fsync
        calls = [0]

        def fail_directory_fsync_once(descriptor):
            calls[0] += 1
            # _atomic_replace fsyncs the file first and its parent directory second.
            if calls[0] == 2:
                raise OSError("directory fsync unavailable")
            return real_fsync(descriptor)

        with patch("app_event_store.os.fsync", side_effect=fail_directory_fsync_once):
            event = self.store.record("app.profile.save_failed", {"reason": "test"}, "test")
            self.wait_until(lambda: self.store.status().status == "failed")
            status = self.store.status()
            self.assertEqual(status.pending_count, 1)
            self.assertIn("directory fsync unavailable", status.error)
            self.assertFalse(status.complete)
            self.assertEqual([item["event_id"] for item in
                              read_app_event_store(self.path)["events"]], [event.event_id])

            self.assertTrue(self.store.retry())
            self.assertTrue(self.store.flush())

        self.assertTrue(self.store.status().complete)
        self.assertEqual([item["event_id"] for item in
                          read_app_event_store(self.path)["events"]], [event.event_id])

    def test_reader_rejects_unknown_version_and_round_linkage(self):
        payload = {"record_type": "app_event_store", "schema_version": 77, "events": []}
        self.path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "不受支援"):
            read_app_event_store(self.path)

    def test_reader_rejects_invalid_or_timezone_naive_event_time(self):
        event = self.store.record("app.startup.started")
        self.assertTrue(self.store.flush())
        original = read_app_event_store(self.path)
        self.assertEqual(original["events"][0]["event_id"], event.event_id)
        for timestamp in ("not-a-time", "2026-10-09T12:00:00"):
            malformed = json.loads(json.dumps(original))
            malformed["events"][0]["occurred_at"] = timestamp
            self.path.write_text(json.dumps(malformed), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "時間"):
                read_app_event_store(self.path)


if __name__ == "__main__":
    unittest.main()
