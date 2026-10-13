"""Date-bounded first-page queries over the existing read-only history sources."""

from __future__ import annotations

import bisect
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

from historical_event_display import HistoricalEvent, iter_historical_events


HISTORICAL_EVENT_QUERY_PAGE_SIZE = 100
_DIAGNOSTIC_SAMPLE_LIMIT = 20


class _LocalTimezoneSnapshot:
    """Immutable local-zone rules captured when the query is submitted."""

    def __init__(self, zone=None, foundation_zone=None, fallback=None):
        self._zone = zone
        self._foundation_zone = foundation_zone
        self._fallback = fallback

    def wall_time(self, epoch: float) -> datetime:
        if self._zone is not None:
            return datetime.fromtimestamp(epoch, self._zone).replace(tzinfo=None)
        if self._foundation_zone is not None:
            from Foundation import NSDate
            moment = NSDate.dateWithTimeIntervalSince1970_(epoch)
            offset = self._foundation_zone.secondsFromGMTForDate_(moment)
            return datetime.utcfromtimestamp(epoch) + timedelta(seconds=offset)
        return datetime.fromtimestamp(epoch, self._fallback)


def _capture_local_timezone() -> _LocalTimezoneSnapshot:
    """Capture named local timezone rules without consulting process TZ in a worker."""
    zone_name = _local_timezone_name()
    if zone_name:
        try:
            from zoneinfo import ZoneInfo
            return _LocalTimezoneSnapshot(zone=ZoneInfo(zone_name))
        except ImportError:
            pass
        except (KeyError, OSError, ValueError):
            pass
        try:
            from Foundation import NSTimeZone
            zone = NSTimeZone.timeZoneWithName_(zone_name)
            if zone is not None:
                return _LocalTimezoneSnapshot(foundation_zone=zone)
        except ImportError:
            pass
    return _LocalTimezoneSnapshot(fallback=datetime.now().astimezone().tzinfo or timezone.utc)


def _local_timezone_name() -> Optional[str]:
    configured = os.environ.get("TZ", "").lstrip(":")
    if configured and not os.path.isabs(configured) and "/" in configured:
        return configured
    candidates = [configured] if configured else []
    try:
        candidates.append(os.path.realpath("/etc/localtime"))
    except OSError:
        pass
    marker = "zoneinfo/"
    for candidate in candidates:
        if marker in candidate:
            name = candidate.split(marker, 1)[1]
            if name and not name.startswith("posix/") and not name.startswith("right/"):
                return name
        if candidate and "/" not in candidate and not candidate.startswith("<"):
            return candidate
    return None


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
    _local_timezone: _LocalTimezoneSnapshot = field(init=False, repr=False, compare=False)

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
        object.__setattr__(self, "_local_timezone", _capture_local_timezone())


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


@dataclass(frozen=True)
class HistoricalEventQueryCompletion:
    generation: int
    date_range: HistoricalEventDateRange
    succeeded: bool
    result: Optional[HistoricalEventQueryResult] = None
    error: Optional[Exception] = None


@dataclass
class _HistoricalEventQueryRequest:
    generation: int
    date_range: HistoricalEventDateRange
    cancellation_event: threading.Event = field(default_factory=threading.Event)


class HistoricalEventQueryService:
    """Coordinate one active read and keep only the newest pending request.

    Submitting or cancelling never waits for filesystem work. A source reader that
    cannot be interrupted still cannot publish after its request becomes stale.
    """

    def __init__(self, session_root: Path, app_event_path: Optional[Path],
                 query_function: Optional[Callable] = None):
        self._session_root = Path(session_root)
        self._app_event_path = Path(app_event_path) if app_event_path else None
        self._query_function = query_function or query_historical_events
        self._condition = threading.Condition()
        self._next_generation = 0
        self._latest_generation = None
        self._active: Optional[_HistoricalEventQueryRequest] = None
        self._pending: Optional[_HistoricalEventQueryRequest] = None
        self._worker: Optional[threading.Thread] = None
        self._completed: Dict[int, HistoricalEventQueryCompletion] = {}
        self._closed = False

    def submit(self, date_range: HistoricalEventDateRange) -> int:
        if not isinstance(date_range, HistoricalEventDateRange):
            raise TypeError("date_range must be a HistoricalEventDateRange")
        with self._condition:
            if self._closed:
                raise RuntimeError("historical query service is closed")
            self._next_generation += 1
            request = _HistoricalEventQueryRequest(self._next_generation, date_range)
            if self._active is not None:
                self._active.cancellation_event.set()
            if self._pending is not None:
                self._pending.cancellation_event.set()
            self._pending = request
            self._latest_generation = request.generation
            self._completed.clear()
            if self._worker is None:
                self._worker = threading.Thread(
                    target=self._run, name="HistoricalEventDateQuery", daemon=True)
                self._worker.start()
            self._condition.notify_all()
            return request.generation

    def cancel(self, generation: int) -> bool:
        """Invalidate one current request and signal cooperative cancellation."""
        with self._condition:
            if self._closed or self._latest_generation != generation:
                return False
            self._latest_generation = None
            if self._active is not None and self._active.generation == generation:
                self._active.cancellation_event.set()
            if self._pending is not None and self._pending.generation == generation:
                self._pending.cancellation_event.set()
                self._pending = None
            self._completed.pop(generation, None)
            self._condition.notify_all()
            return True

    def take_result(self, generation: int) -> Optional[HistoricalEventQueryCompletion]:
        """Return a completion only while its generation is still current."""
        with self._condition:
            if self._closed or self._latest_generation != generation:
                return None
            completion = self._completed.pop(generation, None)
            if completion is not None:
                self._latest_generation = None
            return completion

    def is_pending(self, generation: int) -> bool:
        """Tell a UI poller whether this generation can still complete."""
        with self._condition:
            if self._closed or self._latest_generation != generation:
                return False
            if generation in self._completed:
                return True
            return ((self._active is not None and self._active.generation == generation) or
                    (self._pending is not None and self._pending.generation == generation))

    def shutdown(self) -> None:
        """Stop accepting work and invalidate results without joining a reader."""
        with self._condition:
            self._closed = True
            self._latest_generation = None
            self._completed.clear()
            if self._active is not None:
                self._active.cancellation_event.set()
            if self._pending is not None:
                self._pending.cancellation_event.set()
                self._pending = None
            self._condition.notify_all()

    def _run(self) -> None:
        while True:
            with self._condition:
                if self._closed or self._pending is None:
                    self._worker = None
                    self._condition.notify_all()
                    return
                request = self._pending
                self._pending = None
                self._active = request

            try:
                result = self._query_function(
                    self._session_root, self._app_event_path, request.date_range,
                    cancellation_event=request.cancellation_event)
                completion = HistoricalEventQueryCompletion(
                    request.generation, request.date_range, True, result=result)
            except Exception as error:
                completion = HistoricalEventQueryCompletion(
                    request.generation, request.date_range, False, error=error)

            with self._condition:
                if self._active is request:
                    self._active = None
                if (not self._closed and
                        self._latest_generation == request.generation and
                        not request.cancellation_event.is_set()):
                    self._completed[request.generation] = completion
                if self._closed or self._pending is None:
                    self._worker = None
                    self._condition.notify_all()
                    return
                self._condition.notify_all()


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
                            limit: int = HISTORICAL_EVENT_QUERY_PAGE_SIZE,
                            cancellation_event: Optional[threading.Event] = None
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

    _raise_if_query_cancelled(cancellation_event)
    for event in iter_historical_events(session_root, app_event_path):
        _raise_if_query_cancelled(cancellation_event)
        if event.source in {"read_error", "read_warning"}:
            source_issue_count += 1
        occurred_at = _parse_occurred_at(event.occurred_at, date_range._local_timezone)
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

    _raise_if_query_cancelled(cancellation_event)

    return HistoricalEventQueryResult(
        date_range, tuple(item[2] for item in ordered), total_count,
        unclassified_count, source_issue_count, tuple(diagnostics))


def _raise_if_query_cancelled(cancellation_event: Optional[threading.Event]) -> None:
    if cancellation_event is not None and cancellation_event.is_set():
        raise RuntimeError("historical event query cancelled")


def _parse_occurred_at(value: str, local_timezone: _LocalTimezoneSnapshot):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            epoch = None
            local_wall = parsed
        else:
            epoch = parsed.timestamp()
            local_wall = local_timezone.wall_time(epoch)
        wall_order = (local_wall.toordinal() * 86400 + local_wall.hour * 3600 +
                      local_wall.minute * 60 + local_wall.second +
                      local_wall.microsecond / 1000000.0)
        return parsed, epoch, wall_order
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _local_midnight_epoch(value: date) -> float:
    local_midnight = datetime.combine(value, datetime.min.time())
    return time.mktime(local_midnight.timetuple())
