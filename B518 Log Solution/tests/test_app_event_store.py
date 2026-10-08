import json
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
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
