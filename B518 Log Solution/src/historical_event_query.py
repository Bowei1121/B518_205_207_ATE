"""Date-bounded, paged snapshots over the existing read-only history sources."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import threading
import time
import weakref
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

from historical_event_display import (HistoricalEvent, iter_historical_events,
                                      legacy_historical_event_message_record)


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
class HistoricalEventSummary:
    """Small list-row data; source diagnostics and raw details stay in the snapshot."""

    key: str
    source: str
    occurred_at: str
    message: str
    kind: str = ""
    round_id: Optional[str] = None
    sequence: Optional[int] = None
    localized_message: Optional[dict] = None
    station: str = ""
    platform: str = ""
    unrecognized: bool = False
    source_order: int = 0


@dataclass(frozen=True)
class HistoricalEventQueryPage:
    date_range: HistoricalEventDateRange
    page_number: int
    page_size: int
    total_count: int
    events: Tuple[HistoricalEventSummary, ...]


class HistoricalEventQueryResult:
    """A fixed, temporary query snapshot with bounded pages and lazy detail reads."""

    def __init__(self, date_range: HistoricalEventDateRange, total_count: int,
                 unclassified_count: int, source_issue_count: int,
                 diagnostics: Tuple[HistoricalEvent, ...], store_path: Path,
                 page_size: int = HISTORICAL_EVENT_QUERY_PAGE_SIZE):
        self.date_range = date_range
        self.total_count = total_count
        self.unclassified_count = unclassified_count
        self.source_issue_count = source_issue_count
        self.diagnostics = diagnostics
        self._store_path = Path(store_path)
        self.page_size = page_size
        self._first_page = ()
        self._closed = False
        self._finalizer = weakref.finalize(self, _remove_snapshot, self._store_path)

    @property
    def events(self) -> Tuple[HistoricalEventSummary, ...]:
        """Compatibility view of the first bounded page."""
        self._ensure_open()
        return self._first_page

    @property
    def page_count(self) -> int:
        if self.total_count == 0:
            return 0
        return (self.total_count + self.page_size - 1) // self.page_size

    def get_page(self, page_number: int) -> HistoricalEventQueryPage:
        """Read at most one page from the immutable query snapshot, never the sources."""
        if type(page_number) is not int or page_number < 1:
            raise ValueError("page_number must be a positive integer")
        self._ensure_open()
        if self.page_count and page_number > self.page_count:
            raise IndexError("page_number is outside this query snapshot")
        if not self.page_count and page_number != 1:
            raise IndexError("an empty query only has its empty first page")
        offset = (page_number - 1) * self.page_size
        connection = self._connect_snapshot_readonly()
        try:
            rows = connection.execute(
                "SELECT summary_json FROM matching_events "
                "ORDER BY local_wall_order DESC, aware_rank ASC, epoch DESC, "
                "stable_identity ASC, sequence_number ASC, event_key ASC, "
                "source_order ASC LIMIT ? OFFSET ?",
                (self.page_size, offset),
            ).fetchall()
        finally:
            connection.close()
        summaries = tuple(_summary_from_json(row[0]) for row in rows)
        return HistoricalEventQueryPage(
            self.date_range, page_number, self.page_size,
            self.total_count, summaries)

    def get_detail(self, event_key: str) -> Optional[HistoricalEvent]:
        """Load the original event only for the selected identity."""
        if not isinstance(event_key, str) or not event_key:
            raise ValueError("event_key must be a non-empty string")
        self._ensure_open()
        connection = self._connect_snapshot_readonly()
        try:
            row = connection.execute(
                "SELECT event_json FROM matching_events WHERE event_key = ?",
                (event_key,),
            ).fetchone()
        finally:
            connection.close()
        return _event_from_json(row[0]) if row is not None else None

    def close(self) -> None:
        """Release this query's temporary snapshot; safe to call more than once."""
        if self._closed:
            return
        self._closed = True
        if self._finalizer.alive:
            self._finalizer()

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("historical query snapshot is closed")

    def _connect_snapshot_readonly(self) -> sqlite3.Connection:
        """Never recreate a snapshot if close races this read's open."""
        self._ensure_open()
        return sqlite3.connect(self._store_path.as_uri() + "?mode=ro", uri=True)

    @property
    def is_limited(self) -> bool:
        """Whether the first page alone omits matching rows (legacy H1 indicator)."""
        return self.total_count > self.page_size


def _remove_snapshot(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _summary_from_json(value: str) -> HistoricalEventSummary:
    return HistoricalEventSummary(**json.loads(value))


def _event_from_json(value: str) -> HistoricalEvent:
    return HistoricalEvent(**json.loads(value))


def _event_summary_json(event: HistoricalEvent) -> str:
    localized_message = event.localized_message
    if localized_message is None:
        localized_message = legacy_historical_event_message_record(event)
    return json.dumps({
        "key": event.key, "source": event.source, "occurred_at": event.occurred_at,
        "message": event.message, "kind": event.kind, "round_id": event.round_id,
        "sequence": event.sequence, "localized_message": localized_message,
        "station": event.station, "platform": event.platform,
        "unrecognized": event.unrecognized, "source_order": event.source_order,
    }, ensure_ascii=False, separators=(",", ":"))


def _event_json(event: HistoricalEvent) -> str:
    return json.dumps({
        "key": event.key, "source": event.source, "occurred_at": event.occurred_at,
        "message": event.message, "kind": event.kind, "round_id": event.round_id,
        "sequence": event.sequence, "localized_message": event.localized_message,
        "diagnostic": event.diagnostic, "detail": event.detail,
        "raw_record": event.raw_record, "station": event.station,
        "platform": event.platform, "unrecognized": event.unrecognized,
        "source_order": event.source_order,
    }, ensure_ascii=False, separators=(",", ":"))


@dataclass(frozen=True)
class HistoricalEventDetailCompletion:
    request_id: int
    event_key: Optional[str]
    succeeded: bool
    event: Optional[HistoricalEvent] = None
    error: Optional[Exception] = None
    page: Optional[HistoricalEventQueryPage] = None


@dataclass
class _HistoricalEventDetailRequest:
    request_id: int
    result: HistoricalEventQueryResult
    event_key: Optional[str]
    page_number: Optional[int] = None
    cancellation_event: threading.Event = field(default_factory=threading.Event)


class HistoricalEventDetailService:
    """Load only the currently selected detail on one bounded background worker."""

    def __init__(self):
        self._condition = threading.Condition()
        self._next_request_id = 0
        self._latest_request_id = None
        self._active: Optional[_HistoricalEventDetailRequest] = None
        self._pending: Optional[_HistoricalEventDetailRequest] = None
        self._worker: Optional[threading.Thread] = None
        self._completed: Optional[HistoricalEventDetailCompletion] = None
        self._closed = False

    def submit(self, result: HistoricalEventQueryResult, event_key: str) -> int:
        if not isinstance(event_key, str) or not event_key:
            raise ValueError("event_key must be a non-empty string")
        return self._submit(result, event_key, None)

    def submit_page(self, result: HistoricalEventQueryResult, page_number: int) -> int:
        if type(page_number) is not int or page_number < 1:
            raise ValueError("page_number must be a positive integer")
        return self._submit(result, None, page_number)

    def _submit(self, result: HistoricalEventQueryResult, event_key: Optional[str],
                page_number: Optional[int]) -> int:
        if not isinstance(result, HistoricalEventQueryResult):
            raise TypeError("result must be a HistoricalEventQueryResult")
        with self._condition:
            if self._closed:
                raise RuntimeError("historical detail service is closed")
            self._next_request_id += 1
            request = _HistoricalEventDetailRequest(
                self._next_request_id, result, event_key, page_number)
            self._invalidate_work_locked()
            self._pending = request
            self._latest_request_id = request.request_id
            self._completed = None
            if self._worker is None:
                self._worker = threading.Thread(
                    target=self._run, name="HistoricalEventDetail", daemon=True)
                self._worker.start()
            self._condition.notify_all()
            return request.request_id

    def cancel(self, request_id: Optional[int] = None) -> None:
        with self._condition:
            if request_id is not None and request_id != self._latest_request_id:
                return
            self._latest_request_id = None
            self._invalidate_work_locked()
            self._completed = None
            self._condition.notify_all()

    def take_result(self, request_id: int) -> Optional[HistoricalEventDetailCompletion]:
        with self._condition:
            if self._closed or request_id != self._latest_request_id:
                return None
            completion = self._completed
            if completion is not None and completion.request_id == request_id:
                self._completed = None
                self._latest_request_id = None
                return completion
            return None

    def is_pending(self, request_id: int) -> bool:
        with self._condition:
            return (not self._closed and self._latest_request_id == request_id and
                    (self._completed is not None or
                     (self._active is not None and self._active.request_id == request_id) or
                     (self._pending is not None and self._pending.request_id == request_id)))

    def shutdown(self) -> None:
        with self._condition:
            self._closed = True
            self._latest_request_id = None
            self._invalidate_work_locked()
            self._completed = None
            self._condition.notify_all()

    def _invalidate_work_locked(self) -> None:
        if self._active is not None:
            self._active.cancellation_event.set()
        if self._pending is not None:
            self._pending.cancellation_event.set()
            self._pending = None

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
                if request.page_number is not None:
                    page = request.result.get_page(request.page_number)
                    completion = HistoricalEventDetailCompletion(
                        request.request_id, None, True, page=page)
                else:
                    event = request.result.get_detail(request.event_key)
                    completion = HistoricalEventDetailCompletion(
                        request.request_id, request.event_key, event is not None, event=event)
            except Exception as error:
                completion = HistoricalEventDetailCompletion(
                    request.request_id, request.event_key, False, error=error)
            with self._condition:
                if self._active is request:
                    self._active = None
                if (not self._closed and self._latest_request_id == request.request_id and
                        not request.cancellation_event.is_set()):
                    self._completed = completion
                if self._closed or self._pending is None:
                    self._worker = None
                    self._condition.notify_all()
                    return
                self._condition.notify_all()


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
            for completion in self._completed.values():
                _discard_query_completion(completion)
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
            completion = self._completed.pop(generation, None)
            if completion is not None:
                _discard_query_completion(completion)
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
            for completion in self._completed.values():
                _discard_query_completion(completion)
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
                else:
                    _discard_query_completion(completion)
                if self._closed or self._pending is None:
                    self._worker = None
                    self._condition.notify_all()
                    return
                self._condition.notify_all()


def _discard_query_completion(completion: HistoricalEventQueryCompletion) -> None:
    if (completion.succeeded and
            isinstance(completion.result, HistoricalEventQueryResult)):
        completion.result.close()


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
    """Freeze matching source events into a temporary, disk-backed query snapshot.

    The retained in-memory page contains only summaries. Original records and large
    diagnostics remain in the temporary snapshot until a selected key requests detail.
    """
    if not isinstance(date_range, HistoricalEventDateRange):
        raise TypeError("date_range must be a HistoricalEventDateRange")
    if type(limit) is not int or limit < 1:
        raise ValueError("limit must be a positive integer")
    page_size = min(limit, HISTORICAL_EVENT_QUERY_PAGE_SIZE)
    descriptor, raw_path = tempfile.mkstemp(prefix="b518-history-query-", suffix=".sqlite3")
    os.close(descriptor)
    store_path = Path(raw_path)
    connection = None
    total_count = 0
    unclassified_count = 0
    source_issue_count = 0
    diagnostics = []
    try:
        connection = sqlite3.connect(str(store_path))
        connection.execute("PRAGMA journal_mode=OFF")
        connection.execute("PRAGMA synchronous=OFF")
        connection.execute(
            "CREATE TABLE matching_events ("
            "event_key TEXT NOT NULL, local_wall_order INTEGER NOT NULL, "
            "aware_rank INTEGER NOT NULL, epoch REAL, stable_identity TEXT NOT NULL, "
            "sequence_number INTEGER NOT NULL, source_order INTEGER NOT NULL, "
            "summary_json TEXT NOT NULL, event_json TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE INDEX event_key_lookup ON matching_events(event_key)")

        _raise_if_query_cancelled(cancellation_event)
        for event in iter_historical_events(session_root, app_event_path):
            _raise_if_query_cancelled(cancellation_event)
            if event.source in {"read_error", "read_warning"}:
                source_issue_count += 1
            occurred_at = _parse_occurred_at(
                event.occurred_at, date_range._local_timezone)
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

            sequence = event.sequence if type(event.sequence) is int else event.source_order
            stable_identity = event.round_id or event.key
            connection.execute(
                "INSERT INTO matching_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (event.key, local_wall_order, 0 if epoch is not None else 1, epoch,
                 stable_identity, sequence, event.source_order,
                 _event_summary_json(event), _event_json(event)))
            total_count += 1

        _raise_if_query_cancelled(cancellation_event)
        connection.execute("CREATE INDEX event_order_lookup ON matching_events("
                           "local_wall_order DESC, aware_rank ASC, epoch DESC, "
                           "stable_identity ASC, sequence_number ASC, event_key ASC, "
                           "source_order ASC)")
        connection.commit()
        connection.close()
        connection = None
        result = HistoricalEventQueryResult(
            date_range, total_count, unclassified_count, source_issue_count,
            tuple(diagnostics), store_path, page_size)
        result._first_page = result.get_page(1).events
        return result
    except Exception:
        if connection is not None:
            connection.close()
        _remove_snapshot(store_path)
        raise


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
        wall_order = ((local_wall.toordinal() * 86400 + local_wall.hour * 3600 +
                       local_wall.minute * 60 + local_wall.second) * 1000000 +
                      local_wall.microsecond)
        return parsed, epoch, wall_order
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _local_midnight_epoch(value: date) -> float:
    local_midnight = datetime.combine(value, datetime.min.time())
    return time.mktime(local_midnight.timetuple())
