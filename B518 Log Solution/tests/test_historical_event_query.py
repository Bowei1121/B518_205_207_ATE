import tempfile
import os
import time
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from audit_records import AuditEvent, RoundAuditStore
from historical_event_query import (HistoricalEventDateError, HistoricalEventDateRange,
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
        with self.assertRaises(HistoricalEventDateError) as invalid:
            parse_historical_event_date_range("2026-02-30", "2026-10-13")
        self.assertEqual(invalid.exception.field_name, "start")
        with self.assertRaises(HistoricalEventDateError) as reversed_range:
            parse_historical_event_date_range("2026-10-14", "2026-10-13")
        self.assertEqual(reversed_range.exception.field_name, "end")
        recent = recent_historical_event_date_range(date(2026, 10, 13), 90)
        self.assertEqual(recent.start, date(2026, 7, 16))
        self.assertEqual(recent.end, date(2026, 10, 13))


if __name__ == "__main__":
    unittest.main()
