import tempfile
import os
import json
import sqlite3
import shutil
import threading
import time
import unittest
import unittest.mock
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from audit_records import AuditEvent, RoundAuditStore
from app_event_store import AppEventStore
from historical_event_query import (HistoricalEventDateError, HistoricalEventDateRange,
                                    HistoricalEventQueryResult,
                                    HistoricalEventDetailService,
                                    HistoricalEventQueryService,
                                    parse_historical_event_date_range,
                                    query_historical_events,
                                    recent_historical_event_date_range)
import historical_event_query


class HistoricalEventQueryTests(unittest.TestCase):
    def _write_audit(self, sessions, events):
        audit = RoundAuditStore(
            sessions, "round-1", "FCT", "2026-10-13T00:00:00+08:00", 0.0)
        for sequence, occurred_at in enumerate(events, 1):
            audit.append_event(AuditEvent(sequence, "round_ready", "FCT 來源已就緒", None),
                               occurred_at, float(sequence))
        self.assertTrue(audit.flush())
        return audit

    def test_public_query_returns_latest_hundred_in_stable_order(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sessions = root / "sessions"
            audit = RoundAuditStore(
                sessions, "round-1", "FCT", "2026-10-13T00:00:00+08:00", 0.0)
            for sequence in range(1, 102):
                audit.append_event(
                    AuditEvent(sequence, "round_ready", "FCT 來源已就緒", None,
                               detail={"raw_diagnostic": "original " + str(sequence)}),
                    (datetime(2026, 10, 13, 10, 0, tzinfo=timezone(
                        timedelta(hours=8))) + timedelta(seconds=sequence)).isoformat(),
                    float(sequence),
                )
            self.assertTrue(audit.flush())
            before = audit.audit_path.read_bytes()

            result = query_historical_events(
                sessions, None, HistoricalEventDateRange(date(2026, 10, 13),
                                                         date(2026, 10, 13)))

            self.assertEqual(result.total_count, 101)
            self.assertEqual(len(result.events), 100)
            self.assertEqual(result.events[0].sequence, 101)
            self.assertEqual(result.events[-1].sequence, 2)
            self.assertEqual(result.events[0].key, "round:round-1:101")
            self.assertEqual(result.events[-1].key, "round:round-1:2")
            self.assertEqual(audit.audit_path.read_bytes(), before)

    def test_persistent_index_is_reused_by_a_new_query_service(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sessions = root / "sessions"
            audit = self._write_audit(sessions, ["2026-10-13T08:00:00+08:00"])
            source_before = audit.audit_path.read_bytes()
            index_path = root / "historical-event-query-index.sqlite3"
            date_range = HistoricalEventDateRange(date(2026, 10, 13),
                                                  date(2026, 10, 13))

            first = query_historical_events(sessions, None, date_range,
                                            index_path=index_path)
            try:
                expected_keys = tuple(row.key for row in first.get_page(1).events)
                self.assertEqual(first.total_count, 1)
                self.assertEqual(first.index_metrics.parsed_source_count, 1)
                self.assertGreater(first.index_metrics.source_bytes_read, 0)
            finally:
                first.close()

            fresh_service = HistoricalEventQueryService(
                sessions, None, index_path=index_path)
            generation = fresh_service.submit(date_range)
            deadline = time.monotonic() + 5
            completion = None
            while completion is None and time.monotonic() < deadline:
                completion = fresh_service.take_result(generation)
                if completion is None:
                    time.sleep(0.01)
            self.assertIsNotNone(completion)
            self.assertTrue(completion.succeeded, completion.error)
            fresh_service_result = completion.result
            try:
                self.assertEqual(
                    tuple(row.key for row in fresh_service_result.get_page(1).events),
                    expected_keys)
                self.assertEqual(fresh_service_result.index_metrics.parsed_source_count, 0)
                self.assertEqual(fresh_service_result.index_metrics.reused_source_count, 1)
                self.assertEqual(fresh_service_result.index_metrics.source_bytes_read, 0)
                self.assertTrue(index_path.is_file())
                self.assertEqual(audit.audit_path.read_bytes(), source_before)
            finally:
                fresh_service_result.close()
                fresh_service.shutdown()

    def test_official_app_event_cleanup_keeps_snapshot_but_not_unloaded_detail(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            now = datetime(2026, 10, 14, 8, 0, tzinfo=timezone.utc)
            store = AppEventStore(root / "app-events.json", clock=lambda: now)
            first = store.record("app.hotkey.unavailable", {}, "first raw diagnostic")
            second = store.record("app.profile.save_failed", {"reason": "disk"},
                                  "second raw diagnostic")
            self.assertTrue(store.flush())
            source_before = store.path.read_bytes()
            index_path = root / "historical-event-query-index.sqlite3"
            date_range = HistoricalEventDateRange(date(2026, 10, 14), date(2026, 10, 14))
            result = query_historical_events(
                root / "sessions", store.path, date_range, index_path=index_path)
            try:
                page = result.get_page(1)
                keys = {event.key for event in page.events}
                self.assertEqual(keys, {"app:{}".format(first.event_id),
                                        "app:{}".format(second.event_id)})
                previously_loaded = result.get_detail("app:{}".format(first.event_id))
                self.assertEqual(previously_loaded.raw_record["diagnostic"],
                                 "first raw diagnostic")

                cleanup = store.cleanup_expired(
                    now + timedelta(seconds=1), root)

                self.assertEqual(cleanup.status, "complete", cleanup)
                self.assertEqual(result.total_count, 2)
                self.assertEqual({event.key for event in result.get_page(1).events}, keys)
                self.assertEqual(previously_loaded.raw_record["diagnostic"],
                                 "first raw diagnostic")
                self.assertIsNone(result.get_detail("app:{}".format(second.event_id)))
                self.assertNotEqual(store.path.read_bytes(), source_before)
                self.assertEqual(store.records, ())
            finally:
                result.close()
                store.stop()

    def test_official_cleanup_completes_while_selected_detail_read_is_in_flight(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            now = datetime(2026, 10, 14, 8, 0, tzinfo=timezone.utc)
            store = AppEventStore(root / "app-events.json", clock=lambda: now)
            event = store.record("app.hotkey.unavailable", {}, "detail removed mid-read")
            self.assertTrue(store.flush())
            result = query_historical_events(
                root / "sessions", store.path,
                HistoricalEventDateRange(date(2026, 10, 14), date(2026, 10, 14)),
                index_path=root / "historical-event-query-index.sqlite3")
            detail_service = HistoricalEventDetailService()
            entered, release = threading.Event(), threading.Event()
            original_get_detail = HistoricalEventQueryResult.get_detail

            def hold_public_detail(query_result, event_key):
                entered.set()
                if not release.wait(5):
                    raise RuntimeError("controlled detail read gate timed out")
                return original_get_detail(query_result, event_key)

            try:
                with unittest.mock.patch.object(HistoricalEventQueryResult, "get_detail",
                                                 hold_public_detail):
                    request_id = detail_service.submit(
                        result, "app:{}".format(event.event_id))
                    self.assertTrue(entered.wait(2))
                    cleanup = store.cleanup_expired(now + timedelta(seconds=1), root)
                    self.assertEqual(cleanup.status, "complete", cleanup)
                    self.assertEqual(store.records, ())
                    self.assertTrue(detail_service.is_pending(request_id))
                    release.set()
                    completion = None
                    deadline = time.monotonic() + 3
                    while completion is None and time.monotonic() < deadline:
                        completion = detail_service.take_result(request_id)
                        if completion is None:
                            time.sleep(0.01)

                self.assertIsNotNone(completion)
                self.assertFalse(completion.succeeded)
                self.assertIsNone(completion.event)
                self.assertIsNone(completion.error)
                self.assertIsNone(result.get_detail("app:{}".format(event.event_id)))
            finally:
                release.set()
                detail_service.shutdown()
                result.close()
                store.stop()

    def test_formal_app_save_stays_out_of_fixed_result_until_requery_without_flush(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            now = datetime(2026, 10, 14, 8, 0, tzinfo=timezone.utc)
            store = AppEventStore(root / "app-events.json", clock=lambda: now)
            original = store.record("app.hotkey.unavailable", {}, "saved before query")
            self.assertTrue(store.flush())
            original_bytes = store.path.read_bytes()
            index_path = root / "historical-event-query-index.sqlite3"
            date_range = HistoricalEventDateRange(date(2026, 10, 14), date(2026, 10, 14))
            result = query_historical_events(
                root / "sessions", store.path, date_range, index_path=index_path)
            entered, release = threading.Event(), threading.Event()
            from app_event_store import _atomic_replace

            def blocked_save(path, content):
                entered.set()
                if not release.wait(5):
                    raise RuntimeError("controlled save gate timed out")
                return _atomic_replace(path, content)

            try:
                with unittest.mock.patch("app_event_store._atomic_replace",
                                         side_effect=blocked_save):
                    pending = store.record("app.profile.save_failed", {"reason": "late"},
                                           "saved after query")
                    self.assertTrue(entered.wait(2))
                    self.assertEqual(store.path.read_bytes(), original_bytes)
                    self.assertGreater(store.status().pending_count, 0)

                    self.assertEqual(result.total_count, 1)
                    self.assertEqual([item.key for item in result.get_page(1).events],
                                     ["app:{}".format(original.event_id)])
                    self.assertTrue(entered.is_set())
                    self.assertEqual(store.path.read_bytes(), original_bytes)

                    release.set()
                    self.assertTrue(store.flush())

                self.assertEqual(result.total_count, 1)
                self.assertEqual([item.key for item in result.get_page(1).events],
                                 ["app:{}".format(original.event_id)])
                self.assertIsNone(result.get_detail("app:{}".format(original.event_id)))
                refreshed = query_historical_events(
                    root / "sessions", store.path, date_range, index_path=index_path)
                try:
                    self.assertEqual(refreshed.total_count, 2)
                    self.assertEqual({item.key for item in refreshed.get_page(1).events}, {
                        "app:{}".format(original.event_id),
                        "app:{}".format(pending.event_id),
                    })
                finally:
                    refreshed.close()
            finally:
                release.set()
                result.close()
                store.stop()

    def test_same_size_content_change_with_restored_mtime_refreshes_only_changed_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sessions = root / "sessions"
            audits = []
            for round_id, message in (("round-a", "first"), ("round-b", "steady")):
                audit = RoundAuditStore(
                    sessions, round_id, "FCT", "2026-10-13T00:00:00+08:00", 0.0)
                audit.append_event(AuditEvent(1, "round_ready", message, None),
                                   "2026-10-13T08:00:00+08:00", 1.0)
                self.assertTrue(audit.flush())
                audits.append(audit)
            index_path = root / "historical-event-query-index.sqlite3"
            date_range = HistoricalEventDateRange(date(2026, 10, 13),
                                                  date(2026, 10, 13))
            initial = query_historical_events(sessions, None, date_range,
                                              index_path=index_path)
            self.assertEqual(initial.total_count, 2)
            initial.close()

            changed_path = audits[0].audit_path
            unchanged_source_bytes = audits[1].audit_path.read_bytes()
            original_stat = changed_path.stat()
            original_bytes = changed_path.read_bytes()
            changed_bytes = original_bytes.replace(b'"first"', b'"other"')
            self.assertEqual(len(changed_bytes), len(original_bytes))
            changed_path.write_bytes(changed_bytes)
            os.utime(changed_path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))

            refreshed = query_historical_events(sessions, None, date_range,
                                                index_path=index_path)
            try:
                self.assertEqual(refreshed.total_count, 2)
                self.assertEqual(refreshed.index_metrics.parsed_source_count, 1)
                self.assertEqual(refreshed.index_metrics.reused_source_count, 1)
                self.assertGreater(refreshed.index_metrics.source_bytes_read, 0)
                rows = refreshed.get_page(1).events
                self.assertIn("other", [row.message for row in rows])
                self.assertEqual(audits[1].audit_path.read_bytes(), unchanged_source_bytes)
            finally:
                refreshed.close()

    def test_source_addition_replacement_move_deletion_and_app_rewrite_refresh_incrementally(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sessions = root / "sessions"
            app_path = root / "app-events.json"
            app_store = AppEventStore(
                app_path, clock=lambda: datetime(2026, 10, 13, 1, tzinfo=timezone.utc))
            app_store.record("app.startup.started", {})
            self.assertTrue(app_store.flush())
            first_audit = RoundAuditStore(
                sessions, "round-a", "FCT", "2026-10-13T00:00:00+08:00", 0.0)
            first_audit.append_event(AuditEvent(1, "round_ready", "original", None),
                                     "2026-10-13T08:00:00+08:00", 1.0)
            self.assertTrue(first_audit.flush())
            index_path = root / "historical-event-query-index.sqlite3"
            day = HistoricalEventDateRange(date(2026, 10, 13), date(2026, 10, 13))

            initial = query_historical_events(sessions, app_path, day, index_path=index_path)
            try:
                self.assertEqual(initial.total_count, 2)
                self.assertEqual(initial.index_metrics.parsed_source_count, 2)
            finally:
                initial.close()

            replacement_root = root / "replacement"
            replacement = RoundAuditStore(
                replacement_root, "round-a", "FCT", "2026-10-13T00:00:00+08:00", 0.0)
            replacement.append_event(AuditEvent(1, "round_ready", "replaced", None),
                                     "2026-10-13T08:00:00+08:00", 1.0)
            self.assertTrue(replacement.flush())
            os.replace(str(replacement.audit_path), str(first_audit.audit_path))
            replaced = query_historical_events(sessions, app_path, day, index_path=index_path)
            try:
                self.assertEqual(replaced.total_count, 2)
                self.assertEqual(replaced.index_metrics.parsed_source_count, 1)
                self.assertEqual(replaced.index_metrics.reused_source_count, 1)
                self.assertIn("replaced", [row.message for row in replaced.get_page(1).events])
            finally:
                replaced.close()

            moved_directory = sessions / "moved-round"
            os.replace(str(first_audit.audit_path.parent), str(moved_directory))
            moved = query_historical_events(sessions, app_path, day, index_path=index_path)
            try:
                self.assertEqual(moved.total_count, 2)
                self.assertEqual(moved.index_metrics.parsed_source_count, 1)
                self.assertEqual(moved.index_metrics.reused_source_count, 1)
            finally:
                moved.close()

            second_audit = RoundAuditStore(
                sessions, "round-b", "FCT", "2026-10-13T00:00:00+08:00", 0.0)
            second_audit.append_event(AuditEvent(1, "round_ready", "added", None),
                                      "2026-10-13T09:00:00+08:00", 1.0)
            self.assertTrue(second_audit.flush())
            added = query_historical_events(sessions, app_path, day, index_path=index_path)
            try:
                self.assertEqual(added.total_count, 3)
                self.assertEqual(added.index_metrics.parsed_source_count, 1)
                self.assertEqual(added.index_metrics.reused_source_count, 2)
            finally:
                added.close()

            before_app_change = app_path.stat().st_ino
            app_store.record("app.startup.started", {})
            self.assertTrue(app_store.flush())
            self.assertNotEqual(app_path.stat().st_ino, before_app_change)
            app_changed = query_historical_events(sessions, app_path, day,
                                                 index_path=index_path)
            try:
                self.assertEqual(app_changed.total_count, 4)
                self.assertEqual(app_changed.index_metrics.parsed_source_count, 1)
                self.assertEqual(app_changed.index_metrics.reused_source_count, 2)
            finally:
                app_changed.close()
                app_store.stop()

            shutil.rmtree(moved_directory)
            deleted = query_historical_events(sessions, app_path, day, index_path=index_path)
            try:
                self.assertEqual(deleted.total_count, 3)
                self.assertEqual(deleted.index_metrics.parsed_source_count, 0)
                self.assertEqual(deleted.index_metrics.reused_source_count, 2)
            finally:
                deleted.close()

    def test_source_append_before_version_confirmation_is_not_indexed_as_reliable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sessions = root / "sessions"
            audit = self._write_audit(sessions, ["2026-10-13T08:00:00+08:00"])
            index_path = root / "historical-event-query-index.sqlite3"
            date_range = HistoricalEventDateRange(date(2026, 10, 13),
                                                  date(2026, 10, 13))
            original_reader = historical_event_query.iter_historical_source_events
            scan_finished = threading.Event()
            allow_confirmation = threading.Event()
            results = []
            failures = []

            def paused_after_source_read(source, read_observer=None):
                yield from original_reader(source, read_observer=read_observer)
                if not scan_finished.is_set():
                    scan_finished.set()
                    if not allow_confirmation.wait(5):
                        raise RuntimeError("source-version confirmation gate timed out")

            def run_query():
                try:
                    results.append(query_historical_events(
                        sessions, None, date_range, index_path=index_path))
                except BaseException as error:
                    failures.append(error)

            with unittest.mock.patch.object(
                    historical_event_query, "iter_historical_source_events",
                    side_effect=paused_after_source_read):
                worker = threading.Thread(target=run_query)
                worker.start()
                self.assertTrue(scan_finished.wait(5))
                audit.append_event(
                    AuditEvent(2, "round_ready", "arrived during scan", None),
                    "2026-10-13T09:00:00+08:00", 2.0)
                self.assertTrue(audit.flush())
                allow_confirmation.set()
                worker.join(5)

            self.assertFalse(worker.is_alive())
            self.assertFalse(failures, failures)
            unstable = results.pop()
            try:
                self.assertEqual(unstable.total_count, 0)
                self.assertEqual(unstable.source_issue_count, 1)
                self.assertTrue(unstable.diagnostics)
            finally:
                unstable.close()

            recovered = query_historical_events(sessions, None, date_range,
                                                index_path=index_path)
            try:
                self.assertEqual(recovered.total_count, 2)
                self.assertEqual(recovered.index_metrics.parsed_source_count, 1)
                self.assertEqual([item.sequence for item in recovered.get_page(1).events], [2, 1])
            finally:
                recovered.close()

    def test_unsupported_index_version_is_rebuilt_from_unchanged_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sessions = root / "sessions"
            audit = self._write_audit(sessions, ["2026-10-13T08:00:00+08:00"])
            source_before = audit.audit_path.read_bytes()
            index_path = root / "historical-event-query-index.sqlite3"
            date_range = HistoricalEventDateRange(date(2026, 10, 13),
                                                  date(2026, 10, 13))
            initial = query_historical_events(sessions, None, date_range,
                                              index_path=index_path)
            expected_keys = tuple(row.key for row in initial.get_page(1).events)
            initial.close()
            with sqlite3.connect(str(index_path)) as connection:
                connection.execute("PRAGMA user_version=999")

            rebuilt = query_historical_events(sessions, None, date_range,
                                              index_path=index_path)
            try:
                self.assertEqual(tuple(row.key for row in rebuilt.get_page(1).events),
                                 expected_keys)
                self.assertEqual(rebuilt.index_metrics.parsed_source_count, 1)
                self.assertEqual(rebuilt.index_metrics.reused_source_count, 0)
                self.assertTrue(rebuilt.index_degraded)
                self.assertEqual(audit.audit_path.read_bytes(), source_before)
            finally:
                rebuilt.close()

    def test_pre_h6_index_without_source_versions_is_rebuilt_before_detail_reuse(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sessions = root / "sessions"
            audit = self._write_audit(sessions, ["2026-10-13T08:00:00+08:00"])
            index_path = root / "historical-event-query-index.sqlite3"
            date_range = HistoricalEventDateRange(date(2026, 10, 13), date(2026, 10, 13))
            initial = query_historical_events(
                sessions, None, date_range, index_path=index_path)
            event_key = initial.get_page(1).events[0].key
            initial.close()
            with sqlite3.connect(str(index_path)) as connection:
                row = connection.execute(
                    "SELECT source_key, source_ordinal, event_json FROM history_events"
                ).fetchone()
                payload = json.loads(row[2])
                payload.pop("source_path", None)
                payload.pop("source_version", None)
                connection.execute(
                    "UPDATE history_events SET event_json=? WHERE source_key=? AND source_ordinal=?",
                    (json.dumps(payload), row[0], row[1]))
                connection.execute("PRAGMA user_version=1")

            rebuilt = query_historical_events(
                sessions, None, date_range, index_path=index_path)
            try:
                self.assertTrue(rebuilt.index_degraded)
                self.assertEqual(rebuilt.index_metrics.parsed_source_count, 1)
                detail = rebuilt.get_detail(event_key)
                self.assertIsNotNone(detail)
                self.assertEqual(Path(detail.source_path), audit.audit_path)
                self.assertIsNotNone(detail.source_version)
            finally:
                rebuilt.close()

    def test_cancelled_partial_index_refresh_is_rolled_back_before_retry(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sessions = root / "sessions"
            audit = self._write_audit(
                sessions, ["2026-10-13T08:00:00+08:00", "2026-10-13T08:01:00+08:00"])
            index_path = root / "historical-event-query-index.sqlite3"
            date_range = HistoricalEventDateRange(date(2026, 10, 13),
                                                  date(2026, 10, 13))
            cancellation = threading.Event()
            original_reader = historical_event_query.iter_historical_source_events

            def cancel_after_first_event(source, read_observer=None):
                for event in original_reader(source, read_observer=read_observer):
                    yield event
                    cancellation.set()

            with unittest.mock.patch.object(
                    historical_event_query, "iter_historical_source_events",
                    side_effect=cancel_after_first_event):
                with self.assertRaisesRegex(RuntimeError, "cancelled"):
                    query_historical_events(sessions, None, date_range,
                                            cancellation_event=cancellation,
                                            index_path=index_path)

            retried = query_historical_events(sessions, None, date_range,
                                              index_path=index_path)
            try:
                self.assertEqual(retried.total_count, 2)
                self.assertEqual(retried.index_metrics.parsed_source_count, 1)
            finally:
                retried.close()

    def test_reused_index_reinterprets_offset_events_in_each_submitted_local_timezone(self):
        if not hasattr(time, "tzset"):
            self.skipTest("requires process-local timezone control")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sessions = root / "sessions"
            self._write_audit(sessions, ["2026-01-02T02:00:00+00:00"])
            index_path = root / "historical-event-query-index.sqlite3"
            previous_tz = os.environ.get("TZ")
            try:
                os.environ["TZ"] = "America/New_York"
                time.tzset()
                new_york = query_historical_events(
                    sessions, None,
                    HistoricalEventDateRange(date(2026, 1, 1), date(2026, 1, 1)),
                    index_path=index_path)
                try:
                    self.assertEqual(new_york.total_count, 1)
                    expected_key = new_york.get_page(1).events[0].key
                finally:
                    new_york.close()

                os.environ["TZ"] = "Asia/Tokyo"
                time.tzset()
                tokyo = query_historical_events(
                    sessions, None,
                    HistoricalEventDateRange(date(2026, 1, 2), date(2026, 1, 2)),
                    index_path=index_path)
                try:
                    self.assertEqual(tokyo.total_count, 1)
                    self.assertEqual(tokyo.get_page(1).events[0].key, expected_key)
                    self.assertEqual(tokyo.index_metrics.parsed_source_count, 0)
                    self.assertEqual(tokyo.index_metrics.reused_source_count, 1)
                finally:
                    tokyo.close()
            finally:
                if previous_tz is None:
                    os.environ.pop("TZ", None)
                else:
                    os.environ["TZ"] = previous_tz
                time.tzset()

    def test_new_audit_source_supersedes_indexed_legacy_events_log(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sessions = root / "sessions"
            legacy_dir = sessions / "round-legacy"
            legacy_dir.mkdir(parents=True)
            legacy_path = legacy_dir / "events.log"
            legacy_path.write_text(json.dumps({
                "timestamp": "2026-10-13T08:00:00+08:00",
                "message": "legacy message",
                "round_id": "round-legacy",
                "sequence": 1,
            }) + "\n", encoding="utf-8")
            index_path = root / "historical-event-query-index.sqlite3"
            date_range = HistoricalEventDateRange(date(2026, 10, 13),
                                                  date(2026, 10, 13))
            legacy_result = query_historical_events(sessions, None, date_range,
                                                    index_path=index_path)
            try:
                self.assertEqual(legacy_result.total_count, 1)
                self.assertEqual(legacy_result.get_page(1).events[0].source, "legacy_session")
            finally:
                legacy_result.close()

            audit = RoundAuditStore(
                sessions, "round-legacy", "FCT", "2026-10-13T00:00:00+08:00", 0.0)
            audit.append_event(AuditEvent(1, "round_ready", "audit message", None),
                               "2026-10-13T08:00:01+08:00", 1.0)
            self.assertTrue(audit.flush())
            audit_result = query_historical_events(sessions, None, date_range,
                                                   index_path=index_path)
            try:
                self.assertEqual(audit_result.total_count, 1)
                self.assertEqual(audit_result.get_page(1).events[0].source, "round")
                self.assertEqual(audit_result.get_page(1).events[0].message, "audit message")
                self.assertEqual(audit_result.index_metrics.parsed_source_count, 1)
                self.assertEqual(audit_result.index_metrics.reused_source_count, 0)
                self.assertTrue(legacy_path.is_file())
            finally:
                audit_result.close()

    def test_persistent_index_path_cannot_overwrite_or_live_inside_sources(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sessions = root / "sessions"
            audit = self._write_audit(sessions, ["2026-10-13T08:00:00+08:00"])
            source_before = audit.audit_path.read_bytes()
            date_range = HistoricalEventDateRange(date(2026, 10, 13),
                                                  date(2026, 10, 13))

            with self.assertRaises(ValueError):
                query_historical_events(sessions, None, date_range,
                                        index_path=audit.audit_path)
            with self.assertRaises(ValueError):
                query_historical_events(sessions, None, date_range,
                                        index_path=sessions / "historical-index.sqlite3")
            self.assertEqual(audit.audit_path.read_bytes(), source_before)

    def test_unavailable_index_falls_back_to_original_sources_and_retries(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sessions = root / "sessions"
            audit = self._write_audit(sessions, ["2026-10-13T08:00:00+08:00"])
            source_before = audit.audit_path.read_bytes()
            index_path = root / "historical-event-query-index.sqlite3"
            # A directory at the index path is a real SQLite open failure. It is
            # removable after the first query, which models repair and public retry.
            index_path.mkdir()
            date_range = HistoricalEventDateRange(date(2026, 10, 13),
                                                  date(2026, 10, 13))

            degraded = query_historical_events(sessions, None, date_range,
                                               index_path=index_path)
            try:
                self.assertEqual(degraded.total_count, 1)
                self.assertTrue(degraded.index_degraded)
                self.assertEqual(degraded.index_metrics.parsed_source_count, 1)
                self.assertGreater(degraded.index_metrics.source_bytes_read, 0)
                self.assertEqual(degraded.events[0].key, "round:round-1:1")
                self.assertTrue(index_path.is_dir())
                self.assertEqual(audit.audit_path.read_bytes(), source_before)
            finally:
                degraded.close()

            index_path.rmdir()
            recovered = query_historical_events(sessions, None, date_range,
                                                index_path=index_path)
            try:
                self.assertFalse(recovered.index_degraded)
                self.assertEqual(recovered.total_count, 1)
                self.assertTrue(index_path.is_file())
                self.assertEqual(audit.audit_path.read_bytes(), source_before)
            finally:
                recovered.close()

    def test_read_only_index_falls_back_without_changing_its_permissions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sessions = root / "sessions"
            audit = self._write_audit(sessions, ["2026-10-13T08:00:00+08:00"])
            source_before = audit.audit_path.read_bytes()
            index_path = root / "historical-event-query-index.sqlite3"
            date_range = HistoricalEventDateRange(date(2026, 10, 13),
                                                  date(2026, 10, 13))
            initial = query_historical_events(sessions, None, date_range,
                                              index_path=index_path)
            initial.close()
            audit.append_event(AuditEvent(2, "round_ready", "new source event", None),
                               "2026-10-13T08:01:00+08:00", 2.0)
            self.assertTrue(audit.flush())
            source_before = audit.audit_path.read_bytes()
            index_path.chmod(0o400)
            try:
                degraded = query_historical_events(sessions, None, date_range,
                                                   index_path=index_path)
                try:
                    self.assertTrue(degraded.index_degraded)
                    self.assertEqual(degraded.total_count, 2)
                    self.assertEqual(index_path.stat().st_mode & 0o777, 0o400)
                    self.assertEqual(audit.audit_path.read_bytes(), source_before)
                finally:
                    degraded.close()
            finally:
                index_path.chmod(0o600)

            recovered = query_historical_events(sessions, None, date_range,
                                                index_path=index_path)
            try:
                self.assertFalse(recovered.index_degraded)
                self.assertEqual(recovered.index_metrics.parsed_source_count, 1)
            finally:
                recovered.close()

    def test_corrupt_index_is_rejected_rebuilt_and_reported_without_source_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sessions = root / "sessions"
            audit = self._write_audit(sessions, ["2026-10-13T08:00:00+08:00"])
            source_before = audit.audit_path.read_bytes()
            index_path = root / "historical-event-query-index.sqlite3"
            index_path.write_bytes(b"corrupt derivative index")

            result = query_historical_events(
                sessions, None,
                HistoricalEventDateRange(date(2026, 10, 13), date(2026, 10, 13)),
                index_path=index_path)
            try:
                self.assertTrue(result.index_degraded)
                self.assertEqual(result.total_count, 1)
                self.assertEqual(result.index_metrics.parsed_source_count, 1)
                with sqlite3.connect(str(index_path)) as connection:
                    self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 2)
                self.assertEqual(audit.audit_path.read_bytes(), source_before)
            finally:
                result.close()

    def test_corrupt_audit_is_not_repaired_or_reported_as_confirmed_empty(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sessions = root / "sessions"
            audit = self._write_audit(sessions, ["2026-10-13T08:00:00+08:00"])
            audit_bytes = audit.audit_path.read_bytes()
            audit.audit_path.write_bytes(b"corrupted audit fixture\n")
            corrupt_bytes = audit.audit_path.read_bytes()
            index_path = root / "historical-event-query-index.sqlite3"
            date_range = HistoricalEventDateRange(date(2026, 10, 13),
                                                  date(2026, 10, 13))

            result = query_historical_events(sessions, None, date_range,
                                             index_path=index_path)
            try:
                self.assertEqual(result.total_count, 0)
                self.assertEqual(result.source_issue_count, 1)
                self.assertEqual(result.diagnostic_count, 1)
                diagnostic = result.get_diagnostic_detail(
                    result.get_diagnostic_page(1).events[0].key)
                self.assertIn(str(audit.audit_path), str(diagnostic.raw_record))
                self.assertEqual(audit.audit_path.read_bytes(), corrupt_bytes)
            finally:
                result.close()

            # Restore the fixture explicitly, then use the public query again.
            audit.audit_path.write_bytes(audit_bytes)
            recovered = query_historical_events(sessions, None, date_range,
                                                index_path=index_path)
            try:
                self.assertEqual(recovered.total_count, 1)
                self.assertEqual(recovered.source_issue_count, 0)
                self.assertEqual(recovered.get_page(1).events[0].key,
                                 "round:round-1:1")
            finally:
                recovered.close()

    def test_each_corrupt_history_source_is_reported_by_the_public_query(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sessions = root / "sessions"
            audit_path = sessions / "audit-round" / "audit.jsonl"
            audit_path.parent.mkdir(parents=True)
            audit_path.write_bytes(b"not-json\\n")
            legacy_path = sessions / "legacy-round" / "events.log"
            legacy_path.parent.mkdir(parents=True)
            legacy_path.write_bytes(bytes((0xff, 0xfe, 0xfd)))
            app_path = root / "app-events.json"
            app_path.write_bytes(b"not-json\\n")
            source_bytes = {path: path.read_bytes()
                            for path in (audit_path, legacy_path, app_path)}

            result = query_historical_events(
                sessions, app_path,
                HistoricalEventDateRange(date(2026, 10, 13), date(2026, 10, 13)),
                index_path=root / "history-index.sqlite3")
            try:
                self.assertEqual(result.total_count, 0)
                self.assertEqual(result.source_issue_count, 3)
                self.assertEqual(result.unclassified_count, 0)
                self.assertEqual(result.diagnostic_count, 3)
                details = [result.get_diagnostic_detail(summary.key)
                           for summary in result.get_diagnostic_page(1).events]
                details_by_path = {
                    str(detail.raw_record.get("path", detail.raw_record.get("source_path"))):
                    detail for detail in details}
                for path in (audit_path, legacy_path, app_path):
                    self.assertIn(str(path), details_by_path)
                    self.assertEqual(path.read_bytes(), source_bytes[path])
                    self.assertIn(str(path), str(details_by_path[str(path)].raw_record))
            finally:
                result.close()

            fallback = query_historical_events(
                sessions, app_path,
                HistoricalEventDateRange(date(2026, 10, 13), date(2026, 10, 13)))
            try:
                self.assertEqual(fallback.total_count, 0)
                self.assertEqual(fallback.source_issue_count, 3)
                self.assertEqual(fallback.unclassified_count, 0)
                self.assertEqual(fallback.diagnostic_count, 3)
            finally:
                fallback.close()

    def test_fallback_scan_excludes_source_replaced_during_read(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sessions = root / "sessions"
            audit = self._write_audit(sessions, ["2026-10-13T08:00:00+08:00"])
            replacement = RoundAuditStore(
                root / "replacement", "round-1", "FCT",
                "2026-10-13T00:00:00+08:00", 0.0)
            replacement.append_event(
                AuditEvent(1, "round_ready", "new source version", None),
                "2026-10-13T09:00:00+08:00", 1.0)
            self.assertTrue(replacement.flush())
            replacement_bytes = replacement.audit_path.read_bytes()
            real_reader = historical_event_query.iter_historical_events

            def replace_after_read(*args, **kwargs):
                events = list(real_reader(*args, **kwargs))
                os.replace(str(replacement.audit_path), str(audit.audit_path))
                return iter(events)

            with unittest.mock.patch(
                    "historical_event_query.iter_historical_events",
                    side_effect=replace_after_read):
                result = query_historical_events(
                    sessions, None,
                    HistoricalEventDateRange(date(2026, 10, 13), date(2026, 10, 13)))
            try:
                self.assertEqual(result.total_count, 0)
                self.assertEqual(result.source_issue_count, 1)
                self.assertEqual(result.diagnostic_count, 1)
                anomaly = result.get_diagnostic_detail(
                    result.get_diagnostic_page(1).events[0].key)
                self.assertEqual(anomaly.source, "read_warning")
                self.assertIn("changed", anomaly.message.lower())
                self.assertEqual(anomaly.raw_record["path"], str(audit.audit_path))
                self.assertEqual(audit.audit_path.read_bytes(), replacement_bytes)
            finally:
                result.close()

    def test_unreadable_legacy_events_log_alone_is_a_source_issue(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            legacy_path = root / "sessions" / "legacy-round" / "events.log"
            legacy_path.parent.mkdir(parents=True)
            legacy_path.write_bytes(bytes((0xff, 0xfe, 0xfd)))
            before = legacy_path.read_bytes()

            result = query_historical_events(
                root / "sessions", None,
                HistoricalEventDateRange(date(2026, 10, 13), date(2026, 10, 13)))
            try:
                self.assertEqual(result.total_count, 0)
                self.assertEqual(result.source_issue_count, 1)
                self.assertEqual(result.unclassified_count, 0)
                detail = result.get_diagnostic_detail(result.get_diagnostic_page(1).events[0].key)
                self.assertEqual(detail.raw_record["path"], str(legacy_path))
                self.assertIn("utf-8", detail.message)
                self.assertEqual(legacy_path.read_bytes(), before)
            finally:
                result.close()

    def test_indexed_partial_legacy_read_matches_raw_prefix_without_caching_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            legacy_path = root / "sessions" / "legacy-round" / "events.log"
            legacy_path.parent.mkdir(parents=True)
            lines = [json.dumps({
                "timestamp": "2026-10-13T08:00:00+08:00",
                "message": "legacy event {} {}".format(index, "x" * 80),
            }) + chr(10) for index in range(200)]
            readable_prefix = "".join(lines).encode("utf-8")
            legacy_path.write_bytes(readable_prefix + bytes((0xff,)))
            index_path = root / "history-index.sqlite3"
            day = HistoricalEventDateRange(date(2026, 10, 12), date(2026, 10, 13))

            raw = query_historical_events(root / "sessions", None, day)
            try:
                expected = tuple(summary.key for page in range(1, raw.page_count + 1)
                                 for summary in raw.get_page(page).events)
                self.assertGreater(raw.total_count, 0)
                self.assertLess(raw.total_count, 200)
                self.assertEqual(raw.source_issue_count, 1)
            finally:
                raw.close()

            indexed = query_historical_events(root / "sessions", None, day,
                                              index_path=index_path)
            try:
                actual = tuple(summary.key for page in range(1, indexed.page_count + 1)
                               for summary in indexed.get_page(page).events)
                self.assertEqual(actual, expected)
                self.assertEqual(indexed.source_issue_count, 1)
                with sqlite3.connect(str(index_path)) as connection:
                    self.assertEqual(connection.execute(
                        "SELECT COUNT(*) FROM history_sources WHERE source_path=?",
                        (str(legacy_path.resolve()),)).fetchone()[0], 0)
            finally:
                indexed.close()

            legacy_path.write_bytes(readable_prefix)
            recovered = query_historical_events(root / "sessions", None, day,
                                                index_path=index_path)
            try:
                self.assertEqual(recovered.total_count, 200)
                self.assertEqual(recovered.source_issue_count, 0)
                self.assertEqual(recovered.index_metrics.parsed_source_count, 1)
            finally:
                recovered.close()

    def test_mixed_sources_publish_normal_events_with_lazy_source_diagnostic(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sessions = root / "sessions"
            audit = self._write_audit(sessions, ["2026-10-13T08:00:00+08:00"])
            audit_before = audit.audit_path.read_bytes()
            app_path = root / "app-events.json"
            app_path.write_text("not-json\n", encoding="utf-8")
            index_path = root / "historical-event-query-index.sqlite3"
            date_range = HistoricalEventDateRange(date(2026, 10, 13),
                                                  date(2026, 10, 13))

            partial = query_historical_events(sessions, app_path, date_range,
                                              index_path=index_path)
            try:
                self.assertEqual(partial.total_count, 1)
                self.assertEqual(partial.source_issue_count, 1)
                self.assertEqual(partial.diagnostic_count, 1)
                diagnostic_key = partial.get_diagnostic_page(1).events[0].key
                detail = partial.get_diagnostic_detail(diagnostic_key)
                self.assertEqual(detail.source, "read_error")
                self.assertIn(str(app_path), str(detail.raw_record))
                self.assertEqual(audit.audit_path.read_bytes(), audit_before)
            finally:
                partial.close()

            app_path.unlink()
            app_store = AppEventStore(
                app_path, clock=lambda: datetime(2026, 10, 13, 1, tzinfo=timezone.utc))
            app_store.record("app.startup.started", {})
            self.assertTrue(app_store.flush())
            recovered = query_historical_events(sessions, app_path, date_range,
                                                index_path=index_path)
            try:
                self.assertEqual(recovered.total_count, 2)
                self.assertEqual(recovered.source_issue_count, 0)
                self.assertEqual(recovered.index_metrics.parsed_source_count, 1)
                self.assertEqual(recovered.index_metrics.reused_source_count, 1)
            finally:
                recovered.close()

    def test_unknown_date_diagnostics_are_paged_and_details_are_selected_lazily(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            legacy_dir = root / "sessions" / "round-legacy"
            legacy_dir.mkdir(parents=True)
            legacy_path = legacy_dir / "events.log"
            raw_lines = []
            for index in range(23):
                raw_lines.append(json.dumps({
                    "timestamp": "unknown-date-{}".format(index),
                    "message": "legacy event {}".format(index),
                    "detail": {"raw_diagnostic": "original diagnostic {}".format(index)},
                }) + "\n")
            legacy_path.write_text("".join(raw_lines), encoding="utf-8")
            result = query_historical_events(
                root / "sessions", None,
                HistoricalEventDateRange(date(2026, 10, 13), date(2026, 10, 13)),
                limit=7, index_path=root / "history-index.sqlite3")
            try:
                self.assertEqual(result.total_count, 0)
                self.assertEqual(result.unclassified_count, 23)
                self.assertEqual(result.diagnostic_count, 23)
                self.assertLessEqual(len(result.diagnostics), 20)
                first_page = result.get_diagnostic_page(1)
                second_page = result.get_diagnostic_page(2)
                self.assertEqual(len(first_page.events), 7)
                self.assertEqual(len(second_page.events), 7)
                selected = first_page.events[3]
                detail = result.get_diagnostic_detail(selected.key)
                self.assertEqual(detail.key, selected.key)
                self.assertIn("original diagnostic", detail.diagnostic)
                self.assertEqual(legacy_path.read_text(encoding="utf-8"), "".join(raw_lines))
            finally:
                result.close()

    def test_persistent_query_result_stays_fixed_until_a_new_query(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sessions = root / "sessions"
            audit = self._write_audit(sessions, ["2026-10-13T08:00:00+08:00"])
            index_path = root / "historical-event-query-index.sqlite3"
            date_range = HistoricalEventDateRange(date(2026, 10, 13),
                                                  date(2026, 10, 13))
            active = query_historical_events(sessions, None, date_range,
                                             index_path=index_path)
            try:
                original_keys = tuple(row.key for row in active.get_page(1).events)
                audit.append_event(AuditEvent(2, "round_ready", "later", None),
                                   "2026-10-13T09:00:00+08:00", 2.0)
                self.assertTrue(audit.flush())
                self.assertEqual(active.total_count, 1)
                self.assertEqual(tuple(row.key for row in active.get_page(1).events),
                                 original_keys)
                refreshed = query_historical_events(sessions, None, date_range,
                                                    index_path=index_path)
                try:
                    self.assertEqual(refreshed.total_count, 2)
                    self.assertEqual(refreshed.index_metrics.parsed_source_count, 1)
                    self.assertEqual(refreshed.get_page(1).events[0].sequence, 2)
                finally:
                    refreshed.close()
            finally:
                active.close()

    def test_query_snapshot_pages_all_events_and_loads_detail_only_on_request(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sessions = root / "sessions"
            audit = RoundAuditStore(
                sessions, "round-page-1", "FCT", "2026-10-13T00:00:00+08:00", 0.0)
            long_diagnostic = "large raw diagnostic evidence " * 2000
            for sequence in range(1, 206):
                audit.append_event(
                    AuditEvent(
                        sequence, "round_ready", "FCT 來源已就緒", None,
                        detail={"raw_diagnostic": long_diagnostic if sequence == 103 else ""}),
                    "2026-10-13T10:00:00+08:00", float(sequence))
            self.assertTrue(audit.flush())
            source_bytes = audit.audit_path.read_bytes()

            result = query_historical_events(
                sessions, None,
                HistoricalEventDateRange(date(2026, 10, 13), date(2026, 10, 13)))
            try:
                self.assertEqual(result.total_count, 205)
                self.assertEqual(result.page_count, 3)
                self.assertEqual(len(result.get_page(1).events), 100)
                self.assertEqual(len(result.get_page(2).events), 100)
                final_page = result.get_page(3)
                self.assertEqual(len(final_page.events), 5)
                all_summaries = (result.get_page(1).events + result.get_page(2).events +
                                 final_page.events)
                self.assertEqual([item.sequence for item in all_summaries],
                                 list(range(1, 206)))
                self.assertEqual(len({item.key for item in all_summaries}), 205)
                self.assertFalse(hasattr(all_summaries[0], "raw_record"))
                self.assertFalse(hasattr(all_summaries[0], "diagnostic"))
                self.assertFalse(hasattr(all_summaries[0], "detail"))

                selected = next(item for item in result.get_page(2).events
                                if item.sequence == 103)
                detailed = result.get_detail(selected.key)
                self.assertEqual(detailed.key, selected.key)
                self.assertEqual(detailed.sequence, 103)
                self.assertEqual(detailed.detail["raw_diagnostic"], long_diagnostic)
                self.assertEqual(audit.audit_path.read_bytes(), source_bytes)
                audit.append_event(
                    AuditEvent(206, "round_ready", "later saved event", None),
                    "2026-10-13T10:00:00+08:00", 206.0)
                self.assertTrue(audit.flush())
                bytes_after_append = audit.audit_path.read_bytes()
                self.assertEqual(result.total_count, 205)
                self.assertEqual(len(result.get_page(3).events), 5)
                self.assertEqual(audit.audit_path.read_bytes(), bytes_after_append)
                refreshed = query_historical_events(
                    sessions, None,
                    HistoricalEventDateRange(date(2026, 10, 13), date(2026, 10, 13)))
                try:
                    self.assertEqual(refreshed.total_count, 206)
                finally:
                    refreshed.close()
                snapshot_path = result._store_path
            finally:
                result.close()
            self.assertFalse(snapshot_path.exists())
            with self.assertRaisesRegex(RuntimeError, "snapshot is closed"):
                result.get_page(1)

    def test_closing_snapshot_during_page_open_never_recreates_temporary_database(self):
        with tempfile.TemporaryDirectory() as temporary:
            sessions = Path(temporary) / "sessions"
            self._write_audit(sessions, ["2026-10-13T10:00:00+00:00"])
            result = query_historical_events(
                sessions, None,
                HistoricalEventDateRange(date(2026, 10, 13), date(2026, 10, 13)))
            snapshot_path = result._store_path
            connect_entered, continue_connect = threading.Event(), threading.Event()
            original_connect = sqlite3.connect
            connect_failure = []

            def blocked_connect(*args, **kwargs):
                connect_entered.set()
                if not continue_connect.wait(2):
                    raise RuntimeError("connect gate timed out")
                return original_connect(*args, **kwargs)

            def read_page():
                try:
                    result.get_page(1)
                except BaseException as error:
                    connect_failure.append(error)

            with unittest.mock.patch.object(historical_event_query.sqlite3, "connect",
                                            side_effect=blocked_connect):
                worker = threading.Thread(target=read_page)
                worker.start()
                self.assertTrue(connect_entered.wait(2))
                result.close()
                self.assertFalse(snapshot_path.exists())
                continue_connect.set()
                worker.join(2)

            self.assertFalse(worker.is_alive())
            self.assertEqual(len(connect_failure), 1)
            self.assertIsInstance(connect_failure[0], sqlite3.OperationalError)
            self.assertFalse(snapshot_path.exists())

    def test_detail_service_coalesces_selection_and_discards_late_detail(self):
        from historical_event_query import HistoricalEventDetailService

        with tempfile.TemporaryDirectory() as temporary:
            sessions = Path(temporary) / "sessions"
            self._write_audit(sessions, [
                "2026-10-13T10:00:00+00:00", "2026-10-13T10:00:01+00:00"])
            result = query_historical_events(
                sessions, None,
                HistoricalEventDateRange(date(2026, 10, 13), date(2026, 10, 13)))
            first_key, latest_key = (item.key for item in result.events)
            entered, release = threading.Event(), threading.Event()
            original_get_detail = result.get_detail

            def blocked_detail(event_key):
                if event_key == first_key:
                    entered.set()
                    if not release.wait(5):
                        raise RuntimeError("detail gate timed out")
                return original_get_detail(event_key)

            result.get_detail = blocked_detail
            service = HistoricalEventDetailService()
            try:
                stale_request = service.submit(result, first_key)
                self.assertTrue(entered.wait(2))
                latest_request = service.submit(result, latest_key)
                self.assertTrue(service.is_pending(latest_request))
                self.assertIsNone(service.take_result(stale_request))
                release.set()
                deadline = time.monotonic() + 3
                completion = None
                while time.monotonic() < deadline:
                    completion = service.take_result(latest_request)
                    if completion is not None:
                        break
                    time.sleep(0.005)
                self.assertIsNotNone(completion)
                self.assertTrue(completion.succeeded)
                self.assertEqual(completion.event.key, latest_key)
                self.assertFalse(service.is_pending(latest_request))
            finally:
                release.set()
                service.shutdown()
                result.close()

    def test_page_reads_run_off_ui_and_latest_page_replaces_blocked_request(self):
        from historical_event_query import HistoricalEventDetailService

        with tempfile.TemporaryDirectory() as temporary:
            sessions = Path(temporary) / "sessions"
            self._write_audit(sessions, [
                "2026-10-13T10:00:00+00:00"] * 205)
            result = query_historical_events(
                sessions, None,
                HistoricalEventDateRange(date(2026, 10, 13), date(2026, 10, 13)))
            entered, release = threading.Event(), threading.Event()
            original_get_page = result.get_page
            page_reader_threads = []

            def blocked_page(page_number):
                page_reader_threads.append(threading.get_ident())
                if page_number == 2:
                    entered.set()
                    if not release.wait(5):
                        raise RuntimeError("page gate timed out")
                return original_get_page(page_number)

            result.get_page = blocked_page
            service = HistoricalEventDetailService()
            try:
                first_request = service.submit_page(result, 2)
                self.assertTrue(entered.wait(2))
                latest_request = service.submit_page(result, 3)
                self.assertTrue(service.is_pending(latest_request))
                release.set()
                deadline = time.monotonic() + 3
                completion = None
                while time.monotonic() < deadline:
                    completion = service.take_result(latest_request)
                    if completion is not None:
                        break
                    time.sleep(0.005)
                self.assertIsNone(service.take_result(first_request))
                self.assertIsNotNone(completion)
                self.assertTrue(completion.succeeded)
                self.assertEqual(completion.page.page_number, 3)
                self.assertEqual(len(completion.page.events), 5)
                self.assertTrue(page_reader_threads)
                self.assertTrue(all(thread_id != threading.get_ident()
                                    for thread_id in page_reader_threads))
            finally:
                release.set()
                service.shutdown()
                result.close()

    def test_exactly_one_hundred_events_stay_on_one_full_page(self):
        with tempfile.TemporaryDirectory() as temporary:
            sessions = Path(temporary) / "sessions"
            self._write_audit(sessions, ["2026-10-13T10:00:00+00:00"] * 100)

            result = query_historical_events(
                sessions, None,
                HistoricalEventDateRange(date(2026, 10, 13), date(2026, 10, 13)))
            try:
                self.assertEqual(result.total_count, 100)
                self.assertEqual(result.page_count, 1)
                self.assertEqual(len(result.get_page(1).events), 100)
                with self.assertRaises(IndexError):
                    result.get_page(2)
            finally:
                result.close()

    def test_single_result_is_returned_without_claiming_a_later_page(self):
        with tempfile.TemporaryDirectory() as temporary:
            sessions = Path(temporary) / "sessions"
            self._write_audit(sessions, ["2026-10-13T10:00:00+00:00"])

            result = query_historical_events(
                sessions, None,
                HistoricalEventDateRange(date(2026, 10, 13), date(2026, 10, 13)))

            self.assertEqual(result.total_count, 1)
            self.assertEqual(len(result.events), 1)
            self.assertFalse(result.is_limited)

    def test_equal_instants_use_round_identity_then_numeric_sequence(self):
        with tempfile.TemporaryDirectory() as temporary:
            sessions = Path(temporary) / "sessions"
            audit = RoundAuditStore(
                sessions, "round-1", "FCT", "2026-10-13T00:00:00+08:00", 0.0)
            same_instant = "2026-10-13T10:00:00+00:00"
            for sequence in range(1, 11):
                audit.append_event(AuditEvent(sequence, "round_ready", "ready", None),
                                   same_instant, float(sequence))
            self.assertTrue(audit.flush())

            result = query_historical_events(
                sessions, None,
                HistoricalEventDateRange(date(2026, 10, 13), date(2026, 10, 13)))

            self.assertEqual([event.sequence for event in result.events],
                             list(range(1, 11)))
            self.assertEqual(len({event.round_id for event in result.events}), 1)

    def test_naive_fall_back_wall_time_is_not_assigned_an_absolute_fold(self):
        original_tz = os.environ.get("TZ")
        os.environ["TZ"] = "America/New_York"
        time.tzset()
        try:
            with tempfile.TemporaryDirectory() as temporary:
                sessions = Path(temporary) / "sessions"
                self._write_audit(sessions, [
                    "2026-11-01T05:30:00+00:00",  # first 01:30, daylight time
                    "2026-11-01T01:30:00",        # naive wall time, fold unknown
                    "2026-11-01T06:30:00+00:00",  # second 01:30, standard time
                ])

                result = query_historical_events(
                    sessions, None,
                    HistoricalEventDateRange(date(2026, 11, 1), date(2026, 11, 1)))

            # Both known instants are ordered by their actual instant. The naive record
            # remains a wall-time record and is placed by a deterministic tie policy.
            self.assertEqual([event.sequence for event in result.events], [3, 1, 2])
        finally:
            if original_tz is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = original_tz
            time.tzset()

    def test_query_uses_timezone_captured_when_date_range_was_submitted(self):
        original_tz = os.environ.get("TZ")
        os.environ["TZ"] = "America/New_York"
        time.tzset()
        try:
            with tempfile.TemporaryDirectory() as temporary:
                sessions = Path(temporary) / "sessions"
                self._write_audit(sessions, [
                    "2026-11-01T05:30:00+00:00",  # NY 01:30 daylight time
                    "2026-11-01T06:15:00+00:00",  # NY 01:15 standard time
                ])
                submitted_range = HistoricalEventDateRange(
                    date(2026, 11, 1), date(2026, 11, 1))
                os.environ["TZ"] = "Asia/Tokyo"
                time.tzset()

                result = query_historical_events(sessions, None, submitted_range)

            self.assertEqual([event.sequence for event in result.events], [1, 2])
        finally:
            if original_tz is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = original_tz
            time.tzset()

    def test_unreadable_source_is_counted_separately_from_an_empty_date_range(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            broken_app_store = root / "app-events.json"
            broken_app_store.write_text("not-json\n", encoding="utf-8")

            result = query_historical_events(
                root / "sessions", broken_app_store,
                HistoricalEventDateRange(date(2026, 10, 13), date(2026, 10, 13)))

            self.assertEqual(result.total_count, 0)
            self.assertEqual(result.source_issue_count, 1)
            self.assertEqual(result.diagnostics[0].source, "read_error")

    def test_query_service_coalesces_pending_work_and_only_publishes_latest_result(self):
        first_entered = threading.Event()
        release_first = threading.Event()
        latest_entered = threading.Event()
        first_cancellation = []
        calls = []
        active_calls = 0
        max_active_calls = 0
        calls_lock = threading.Lock()

        def controlled_query(_sessions, _app_events, date_range, cancellation_event=None):
            nonlocal active_calls, max_active_calls
            with calls_lock:
                calls.append(date_range.start)
                active_calls += 1
                max_active_calls = max(max_active_calls, active_calls)
            try:
                if date_range.start == date(2026, 1, 1):
                    first_cancellation.append(cancellation_event)
                    first_entered.set()
                    release_first.wait(2)
                    raise RuntimeError("obsolete query failure")
                latest_entered.set()
                return SimpleNamespace(date_range=date_range)
            finally:
                with calls_lock:
                    active_calls -= 1

        service = HistoricalEventQueryService(Path("/unused/sessions"), None,
                                              query_function=controlled_query)
        first_range = HistoricalEventDateRange(date(2026, 1, 1), date(2026, 1, 1))
        middle_range = HistoricalEventDateRange(date(2026, 2, 1), date(2026, 2, 1))
        latest_range = HistoricalEventDateRange(date(2026, 3, 1), date(2026, 3, 1))
        try:
            first_generation = service.submit(first_range)
            self.assertTrue(first_entered.wait(1))
            service.submit(middle_range)
            latest_generation = service.submit(latest_range)

            self.assertTrue(first_cancellation[0].is_set())
            self.assertEqual(calls, [first_range.start])
            release_first.set()
            self.assertTrue(latest_entered.wait(1))

            deadline = time.monotonic() + 1
            completion = None
            while completion is None and time.monotonic() < deadline:
                completion = service.take_result(latest_generation)
                time.sleep(0.005)

            self.assertIsNotNone(completion)
            self.assertTrue(completion.succeeded)
            self.assertEqual(completion.date_range, latest_range)
            self.assertEqual(calls, [first_range.start, latest_range.start])
            self.assertEqual(max_active_calls, 1)
            self.assertIsNone(service.take_result(first_generation))
        finally:
            release_first.set()
            service.shutdown()

    def test_offset_and_local_wall_times_use_inclusive_local_calendar_dates(self):
        original_tz = os.environ.get("TZ")
        os.environ["TZ"] = "America/Los_Angeles"
        time.tzset()
        try:
            with tempfile.TemporaryDirectory() as temporary:
                sessions = Path(temporary) / "sessions"
                audit = self._write_audit(sessions, [
                    "2026-10-08T00:01:00",       # naive old record: local wall time
                    "2026-10-08T00:30:00-07:00", # first local day
                    "2026-10-09T06:59:59+00:00", # last second of local day
                    "2026-10-09T07:00:00+00:00", # next local midnight, excluded
                ])
                before = audit.audit_path.read_bytes()

                result = query_historical_events(
                    sessions, None,
                    HistoricalEventDateRange(date(2026, 10, 8), date(2026, 10, 8)))

                self.assertEqual(result.total_count, 3)
                self.assertEqual([event.sequence for event in result.events], [3, 2, 1])
                self.assertEqual(audit.audit_path.read_bytes(), before)
        finally:
            if original_tz is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = original_tz
            time.tzset()

    def test_local_calendar_day_boundaries_follow_dst_length(self):
        original_tz = os.environ.get("TZ")
        os.environ["TZ"] = "America/New_York"
        time.tzset()
        try:
            with tempfile.TemporaryDirectory() as temporary:
                index_path = Path(temporary) / "historical-event-query-index.sqlite3"
                spring_sessions = Path(temporary) / "spring"
                spring = self._write_audit(spring_sessions, [
                    "2026-03-08T05:00:00+00:00", # local midnight
                    "2026-03-09T03:30:00+00:00", # 23:30 after spring-forward
                    "2026-03-09T04:00:00+00:00", # next local midnight
                ])
                spring_result = query_historical_events(
                    spring_sessions, None,
                    HistoricalEventDateRange(date(2026, 3, 8), date(2026, 3, 8)),
                    index_path=index_path)
                self.assertEqual([event.sequence for event in spring_result.events], [2, 1])
                self.assertEqual(
                    HistoricalEventDateRange(date(2026, 3, 8), date(2026, 3, 8))._end_epoch
                    - HistoricalEventDateRange(date(2026, 3, 8), date(2026, 3, 8))._start_epoch,
                    23 * 60 * 60,
                )
                self.assertTrue(spring.flush())

                fall_sessions = Path(temporary) / "fall"
                self._write_audit(fall_sessions, [
                    "2026-11-01T04:00:00+00:00", # local midnight
                    "2026-11-02T04:59:59+00:00", # last second of 25-hour day
                    "2026-11-02T05:00:00+00:00", # next local midnight
                ])
                fall_result = query_historical_events(
                    fall_sessions, None,
                    HistoricalEventDateRange(date(2026, 11, 1), date(2026, 11, 1)),
                    index_path=index_path)
                self.assertEqual([event.sequence for event in fall_result.events], [2, 1])
                self.assertEqual(
                    HistoricalEventDateRange(date(2026, 11, 1), date(2026, 11, 1))._end_epoch
                    - HistoricalEventDateRange(date(2026, 11, 1), date(2026, 11, 1))._start_epoch,
                    25 * 60 * 60,
                )
                self.assertEqual(fall_result.index_metrics.parsed_source_count, 1)
        finally:
            if original_tz is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = original_tz
            time.tzset()

    def test_date_input_rejects_missing_invalid_and_reversed_ranges(self):
        with self.assertRaises(HistoricalEventDateError) as missing:
            parse_historical_event_date_range("", "2026-10-13")
        self.assertEqual(missing.exception.field_name, "start")
        with self.assertRaises(HistoricalEventDateError) as missing_end:
            parse_historical_event_date_range("2026-10-13", "")
        self.assertEqual(missing_end.exception.field_name, "end")
        with self.assertRaises(HistoricalEventDateError) as invalid:
            parse_historical_event_date_range("2026-02-30", "2026-10-13")
        self.assertEqual(invalid.exception.field_name, "start")
        with self.assertRaises(HistoricalEventDateError) as invalid_end:
            parse_historical_event_date_range("2026-10-13", "2026-02-30")
        self.assertEqual(invalid_end.exception.field_name, "end")
        with self.assertRaises(HistoricalEventDateError) as reversed_range:
            parse_historical_event_date_range("2026-10-14", "2026-10-13")
        self.assertEqual(reversed_range.exception.field_name, "end")
        recent = recent_historical_event_date_range(date(2026, 10, 13), 90)
        self.assertEqual(recent.start, date(2026, 7, 16))
        self.assertEqual(recent.end, date(2026, 10, 13))

    def test_custom_range_crossing_month_and_year_keeps_both_calendar_days(self):
        original_tz = os.environ.get("TZ")
        os.environ["TZ"] = "UTC"
        time.tzset()
        try:
            with tempfile.TemporaryDirectory() as temporary:
                sessions = Path(temporary) / "sessions"
                self._write_audit(sessions, [
                    "2026-12-31T23:59:59+00:00", "2027-01-01T00:00:00+00:00"])

                result = query_historical_events(
                    sessions, None,
                    HistoricalEventDateRange(date(2026, 12, 31), date(2027, 1, 1)))

            self.assertEqual(result.total_count, 2)
            self.assertEqual([event.sequence for event in result.events], [2, 1])
        finally:
            if original_tz is None:
                os.environ.pop("TZ", None)
            else:
                os.environ["TZ"] = original_tz
            time.tzset()

    def test_empty_single_day_and_mixed_sources_keep_existing_source_precedence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sessions = root / "sessions"
            audit = self._write_audit(sessions, [
                "2026-10-13T10:00:00+00:00", "2026-10-13T10:01:00+00:00"])
            legacy_path = audit.audit_path.parent / "events.log"
            legacy_path.write_text(
                '{"timestamp":"2026-10-13T10:00:30","message":"must not duplicate audit"}\n',
                encoding="utf-8")
            app_store = AppEventStore(
                root / "app-events.json",
                clock=lambda: datetime(2026, 10, 13, 10, 0, 30, tzinfo=timezone.utc),
            )
            app_store.record("app.startup.started")
            self.assertTrue(app_store.flush())
            before = (audit.audit_path.read_bytes(), legacy_path.read_bytes(),
                      app_store.path.read_bytes())

            selected_day = HistoricalEventDateRange(date(2026, 10, 13), date(2026, 10, 13))
            result = query_historical_events(sessions, app_store.path, selected_day)
            empty = query_historical_events(
                sessions, app_store.path,
                HistoricalEventDateRange(date(2026, 10, 14), date(2026, 10, 14)))

            self.assertEqual(result.total_count, 3)
            self.assertEqual([event.source for event in result.events], ["round", "app", "round"])
            self.assertEqual([event.sequence for event in result.events], [2, 1, 1])
            self.assertEqual(empty.total_count, 0)
            self.assertEqual(empty.events, ())
            self.assertEqual((audit.audit_path.read_bytes(), legacy_path.read_bytes(),
                              app_store.path.read_bytes()), before)
            app_store.stop()


if __name__ == "__main__":
    unittest.main()
