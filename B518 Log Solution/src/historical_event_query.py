"""Date-bounded first-page queries over the existing read-only history sources."""

from __future__ import annotations

import bisect
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

from historical_event_display import HistoricalEvent, iter_historical_events


HISTORICAL_EVENT_QUERY_PAGE_SIZE = 100
_DIAGNOSTIC_SAMPLE_LIMIT = 20


class HistoricalEventDateError(ValueError):
    """A date range is missing, invalid, or reversed."""

    def __init__(self, field_name: str, reason: str):
        self.reason = reason
        super().__init__(reason)
        self.field_name = field_name


@dataclass(frozen=True)
class HistoricalEventDateRange:
    start: date
    end: date
    _start_epoch: float = field(init=False, repr=False)
    _end_epoch: float = field(init=False, repr=False)

    def __post_init__(self):
        if not isinstance(self.start, date) or isinstance(self.start, datetime):
            raise HistoricalEventDateError("start", "start_invalid")
        if not isinstance(self.end, date) or isinstance(self.end, datetime):
            raise HistoricalEventDateError("end", "end_invalid")
        if self.start > self.end:
            raise HistoricalEventDateError("end", "reversed")
        try:
            start_epoch = _local_midnight_epoch(self.start)
            end_epoch = _local_midnight_epoch(self.end + timedelta(days=1))
        except (OverflowError, OSError, ValueError) as error:
            raise HistoricalEventDateError("end", "unrepresentable") from error
        object.__setattr__(self, "_start_epoch", start_epoch)
        object.__setattr__(self, "_end_epoch", end_epoch)


@dataclass(frozen=True)
class HistoricalEventQueryResult:
    date_range: HistoricalEventDateRange
    events: Tuple[HistoricalEvent, ...]
    total_count: int
    unclassified_count: int
    source_issue_count: int
    diagnostics: Tuple[HistoricalEvent, ...]

    @property
    def is_limited(self) -> bool:
        return self.total_count > len(self.events)


def parse_historical_event_date_range(start_text: str, end_text: str
                                      ) -> HistoricalEventDateRange:
    """Validate ISO calendar dates without starting a read or changing existing results."""
    if not start_text:
        raise HistoricalEventDateError("start", "start_required")
    if not end_text:
        raise HistoricalEventDateError("end", "end_required")
    try:
        start = date.fromisoformat(start_text)
    except (TypeError, ValueError):
        raise HistoricalEventDateError("start", "start_invalid")
    try:
        end = date.fromisoformat(end_text)
    except (TypeError, ValueError):
        raise HistoricalEventDateError("end", "end_invalid")
    return HistoricalEventDateRange(start, end)


def recent_historical_event_date_range(today: date, days: int = 90) -> HistoricalEventDateRange:
    if type(days) is not int or days < 1:
        raise ValueError("days must be a positive integer")
    return HistoricalEventDateRange(today - timedelta(days=days - 1), today)


def query_historical_events(session_root: Path, app_event_path: Optional[Path],
                            date_range: HistoricalEventDateRange,
                            limit: int = HISTORICAL_EVENT_QUERY_PAGE_SIZE
                            ) -> HistoricalEventQueryResult:
    """Read saved history and retain only the newest bounded result set.

    Existing strict source readers remain authoritative. Raw details are carried only by
    matching first-page records; no display text is built while scanning.
    """
    if not isinstance(date_range, HistoricalEventDateRange):
        raise TypeError("date_range must be a HistoricalEventDateRange")
    if type(limit) is not int or limit < 1:
        raise ValueError("limit must be a positive integer")
    page_size = min(limit, HISTORICAL_EVENT_QUERY_PAGE_SIZE)
    ordered = []
    total_count = 0
    unclassified_count = 0
    source_issue_count = 0
    diagnostics = []

    for event in iter_historical_events(session_root, app_event_path):
        if event.source in {"read_error", "read_warning"}:
            source_issue_count += 1
        occurred_at = _parse_occurred_at(event.occurred_at)
        if occurred_at is None:
            unclassified_count += 1
            if len(diagnostics) < _DIAGNOSTIC_SAMPLE_LIMIT:
                diagnostics.append(event)
            continue
        parsed, epoch, local_wall_order = occurred_at
        if epoch is None:
            in_range = date_range.start <= parsed.date() <= date_range.end
        else:
            in_range = date_range._start_epoch <= epoch < date_range._end_epoch
        if not in_range:
            continue

        total_count += 1
        sequence = event.sequence if type(event.sequence) is int else event.source_order
        stable_identity = event.round_id or event.key
        # Naive records are ordered by their local wall time. Do not guess which
        # occurrence they refer to during a daylight-saving fold; aware timestamps
        # at the same wall time remain ordered by their known instants.
        sort_key = (-local_wall_order, 0 if epoch is not None else 1,
                    -epoch if epoch is not None else 0,
                    stable_identity, sequence, event.key, event.source_order)
        bisect.insort(ordered, (sort_key, event.key, event))
        if len(ordered) > page_size:
            ordered.pop()

    return HistoricalEventQueryResult(
        date_range, tuple(item[2] for item in ordered), total_count,
        unclassified_count, source_issue_count, tuple(diagnostics))


def _parse_occurred_at(value: str):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            epoch = None
            local_wall = parsed
        else:
            epoch = parsed.timestamp()
            local_wall = datetime.fromtimestamp(epoch)
        wall_order = (local_wall.toordinal() * 86400 + local_wall.hour * 3600 +
                      local_wall.minute * 60 + local_wall.second +
                      local_wall.microsecond / 1000000.0)
        return parsed, epoch, wall_order
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _local_midnight_epoch(value: date) -> float:
    local_midnight = datetime.combine(value, datetime.min.time())
    return time.mktime(local_midnight.timetuple())
