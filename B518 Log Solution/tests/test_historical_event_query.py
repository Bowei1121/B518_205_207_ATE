import tempfile
import os
import threading
import time
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from audit_records import AuditEvent, RoundAuditStore
from app_event_store import AppEventStore
from historical_event_query import (HistoricalEventDateError, HistoricalEventDateRange,
                                    HistoricalEventQueryResult,
                                    HistoricalEventQueryService,
                                    parse_historical_event_date_range,
                                    query_historical_events,
                                    recent_historical_event_date_range)


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
                return HistoricalEventQueryResult(date_range, (), 0, 0, 0, ())
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
                spring_sessions = Path(temporary) / "spring"
                spring = self._write_audit(spring_sessions, [
                    "2026-03-08T05:00:00+00:00", # local midnight
                    "2026-03-09T03:30:00+00:00", # 23:30 after spring-forward
                    "2026-03-09T04:00:00+00:00", # next local midnight
                ])
                spring_result = query_historical_events(
                    spring_sessions, None,
                    HistoricalEventDateRange(date(2026, 3, 8), date(2026, 3, 8)))
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
                    HistoricalEventDateRange(date(2026, 11, 1), date(2026, 11, 1)))
                self.assertEqual([event.sequence for event in fall_result.events], [2, 1])
                self.assertEqual(
                    HistoricalEventDateRange(date(2026, 11, 1), date(2026, 11, 1))._end_epoch
                    - HistoricalEventDateRange(date(2026, 11, 1), date(2026, 11, 1))._start_epoch,
                    25 * 60 * 60,
                )
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
