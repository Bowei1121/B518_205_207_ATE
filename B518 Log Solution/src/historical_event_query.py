"""Date-bounded, paged snapshots over the existing read-only history sources."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import threading
import time
import uuid
import weakref
from dataclasses import dataclass, field
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

from historical_event_display import (HistoricalEvent, HistoricalEventSource,
                                      iter_historical_event_sources,
                                      iter_historical_events,
                                      iter_historical_source_events,
                                      legacy_historical_event_message_record)


HISTORICAL_EVENT_QUERY_PAGE_SIZE = 100
_DIAGNOSTIC_SAMPLE_LIMIT = 20
_HISTORY_INDEX_VERSION = 4
_HISTORY_INDEX_APPLICATION_ID = 0x42353138
_HISTORY_INDEX_LOCK = threading.RLock()


@dataclass(frozen=True)
class HistoricalEventIndexMetrics:
    parsed_source_count: int = 0
    reused_source_count: int = 0
    source_bytes_read: int = 0
    source_version_check_count: int = 0
    query_content_copy_bytes: int = 0
    query_content_copy_count: int = 0
    indexed_content_write_bytes: int = 0
    indexed_content_write_count: int = 0


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
                 page_size: int = HISTORICAL_EVENT_QUERY_PAGE_SIZE,
                 index_metrics: Optional[HistoricalEventIndexMetrics] = None,
                 index_degraded: bool = False, index_issue: str = "",
                 diagnostic_count: Optional[int] = None,
                 index_path: Optional[Path] = None, query_id: Optional[str] = None):
        self.date_range = date_range
        self.total_count = total_count
        self.unclassified_count = unclassified_count
        self.source_issue_count = source_issue_count
        self.diagnostics = diagnostics
        self._store_path = Path(store_path)
        self.page_size = page_size
        self.index_metrics = index_metrics or HistoricalEventIndexMetrics()
        self.index_degraded = index_degraded
        self.index_issue = index_issue
        self.diagnostic_count = (len(diagnostics) if diagnostic_count is None
                                 else diagnostic_count)
        self._index_path = Path(index_path) if index_path is not None else None
        self._query_id = query_id
        self._first_page = ()
        self._closed = False
        if self._index_path is not None and self._query_id is not None:
            self._finalizer = weakref.finalize(
                self, _release_indexed_snapshot, self._store_path,
                self._index_path, self._query_id)
        else:
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
            if self._index_path is None:
                rows = connection.execute(
                    "SELECT summary_json FROM matching_events "
                    "ORDER BY local_wall_order DESC, aware_rank ASC, epoch DESC, "
                    "stable_identity ASC, sequence_number ASC, event_key ASC, "
                    "source_order ASC LIMIT ? OFFSET ?",
                    (self.page_size, offset),
                ).fetchall()
            else:
                self._attach_content_index(connection)
                rows = connection.execute(
                    "SELECT content.summary_json FROM matching_events AS matching "
                    "JOIN history_index.history_contents AS content "
                    "ON content.content_id=matching.content_id "
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
            if self._index_path is None:
                row = connection.execute(
                    "SELECT event_json FROM matching_events WHERE event_key = ?",
                    (event_key,),
                ).fetchone()
            else:
                self._attach_content_index(connection)
                row = connection.execute(
                    "SELECT content.event_json FROM matching_events AS matching "
                    "JOIN history_index.history_contents AS content "
                    "ON content.content_id=matching.content_id WHERE matching.event_key = ?",
                    (event_key,),
                ).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        # H3's owned temporary snapshot contains the complete original record.
        # Once captured there, it is acquired content and remains readable even
        # if retention removes or replaces the backing source. Never reopen the
        # current path here: it may now identify a different event version.
        return _event_from_json(row[0])

    def get_diagnostic_page(self, page_number: int) -> HistoricalEventQueryPage:
        """Read one bounded page of source/date anomalies from the frozen snapshot."""
        if type(page_number) is not int or page_number < 1:
            raise ValueError("page_number must be a positive integer")
        self._ensure_open()
        page_count = ((self.diagnostic_count + self.page_size - 1) // self.page_size)
        if page_number > page_count:
            raise IndexError("diagnostic page is outside this query snapshot")
        connection = self._connect_snapshot_readonly()
        try:
            if self._index_path is None:
                rows = connection.execute(
                    "SELECT summary_json FROM diagnostic_events ORDER BY diagnostic_ordinal "
                    "LIMIT ? OFFSET ?", (self.page_size, (page_number - 1) * self.page_size)
                ).fetchall()
            else:
                self._attach_content_index(connection)
                rows = connection.execute(
                    "SELECT content.summary_json FROM diagnostic_events AS diagnostic "
                    "JOIN history_index.history_contents AS content "
                    "ON content.content_id=diagnostic.content_id "
                    "ORDER BY diagnostic_ordinal LIMIT ? OFFSET ?",
                    (self.page_size, (page_number - 1) * self.page_size)
                ).fetchall()
        finally:
            connection.close()
        return HistoricalEventQueryPage(
            self.date_range, page_number, self.page_size, self.diagnostic_count,
            tuple(_summary_from_json(row[0]) for row in rows))

    def get_diagnostic_detail(self, event_key: str) -> Optional[HistoricalEvent]:
        """Load one source anomaly's raw record only after the user selects it."""
        if not isinstance(event_key, str) or not event_key:
            raise ValueError("event_key must be a non-empty string")
        self._ensure_open()
        connection = self._connect_snapshot_readonly()
        try:
            if self._index_path is None:
                row = connection.execute(
                    "SELECT event_json FROM diagnostic_events WHERE event_key=? "
                    "ORDER BY diagnostic_ordinal LIMIT 1", (event_key,)).fetchone()
            else:
                self._attach_content_index(connection)
                row = connection.execute(
                    "SELECT content.event_json FROM diagnostic_events AS diagnostic "
                    "JOIN history_index.history_contents AS content "
                    "ON content.content_id=diagnostic.content_id "
                    "WHERE diagnostic.event_key=? ORDER BY diagnostic_ordinal LIMIT 1",
                    (event_key,)).fetchone()
        finally:
            connection.close()
        if row is None:
            return None
        # Diagnostic detail is also frozen in the query-owned snapshot.
        return _event_from_json(row[0])

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

    def _attach_content_index(self, connection: sqlite3.Connection) -> None:
        if self._index_path is None:
            raise RuntimeError("query content index is unavailable")
        connection.execute("ATTACH DATABASE ? AS history_index", (str(self._index_path),))

    @property
    def is_limited(self) -> bool:
        """Whether the first page alone omits matching rows (legacy H1 indicator)."""
        return self.total_count > self.page_size


def _remove_snapshot(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def _reclaim_unreferenced_contents(connection: sqlite3.Connection) -> None:
    # A live query may refer to any historical content generation. Conservatively
    # retain orphaned generations until the last query closes instead of writing
    # one durable reference row for every event in every query.
    if connection.execute("SELECT 1 FROM history_queries LIMIT 1").fetchone():
        return
    connection.execute(
        "DELETE FROM history_contents WHERE content_id NOT IN "
        "(SELECT content_id FROM history_events)")


def _reclaim_abandoned_query_contents(connection: sqlite3.Connection) -> None:
    """Drop references left by a process that no longer owns its query results."""
    for (query_id, process_id) in connection.execute(
            "SELECT query_id, process_id FROM history_queries").fetchall():
        try:
            os.kill(process_id, 0)
        except ProcessLookupError:
            connection.execute("DELETE FROM history_queries WHERE query_id=?", (query_id,))
        except (PermissionError, OSError):
            continue
    _reclaim_unreferenced_contents(connection)
    connection.commit()


def _release_indexed_snapshot(snapshot_path: Path, index_path: Path, query_id: str) -> None:
    try:
        with _HISTORY_INDEX_LOCK:
            connection = sqlite3.connect(str(index_path), timeout=30.0)
            try:
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("BEGIN IMMEDIATE")
                connection.execute("DELETE FROM history_queries WHERE query_id=?", (query_id,))
                _reclaim_unreferenced_contents(connection)
                connection.commit()
            finally:
                connection.close()
    except (OSError, sqlite3.Error):
        # The next successful index open reclaims abandoned query references.
        pass
    _remove_snapshot(snapshot_path)


def _event_content_id(summary_json: str, event_json: str) -> str:
    digest = hashlib.sha256()
    digest.update(summary_json.encode("utf-8"))
    digest.update(b"\0")
    digest.update(event_json.encode("utf-8"))
    return digest.hexdigest()


def _summary_from_json(value: str) -> HistoricalEventSummary:
    return HistoricalEventSummary(**json.loads(value))


def _event_from_json(value: str) -> HistoricalEvent:
    record = json.loads(value)
    if record.get("source_version") is not None:
        record["source_version"] = tuple(record["source_version"])
    return HistoricalEvent(**record)


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
        "source_order": event.source_order, "source_path": event.source_path,
        "source_version": event.source_version,
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
    diagnostic_key: Optional[str] = None
    diagnostic_page_number: Optional[int] = None
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

    def submit_diagnostic(self, result: HistoricalEventQueryResult,
                          event_key: str) -> int:
        if not isinstance(event_key, str) or not event_key:
            raise ValueError("event_key must be a non-empty string")
        return self._submit(result, None, None, diagnostic_key=event_key)

    def submit_diagnostic_page(self, result: HistoricalEventQueryResult,
                               page_number: int) -> int:
        if type(page_number) is not int or page_number < 1:
            raise ValueError("page_number must be a positive integer")
        return self._submit(result, None, None,
                            diagnostic_page_number=page_number)

    def _submit(self, result: HistoricalEventQueryResult, event_key: Optional[str],
                page_number: Optional[int], diagnostic_key: Optional[str] = None,
                diagnostic_page_number: Optional[int] = None) -> int:
        if not isinstance(result, HistoricalEventQueryResult):
            raise TypeError("result must be a HistoricalEventQueryResult")
        with self._condition:
            if self._closed:
                raise RuntimeError("historical detail service is closed")
            self._next_request_id += 1
            request = _HistoricalEventDetailRequest(
                self._next_request_id, result, event_key, page_number,
                diagnostic_key, diagnostic_page_number)
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
                elif request.diagnostic_page_number is not None:
                    page = request.result.get_diagnostic_page(
                        request.diagnostic_page_number)
                    completion = HistoricalEventDetailCompletion(
                        request.request_id, None, True, page=page)
                elif request.diagnostic_key is not None:
                    event = request.result.get_diagnostic_detail(request.diagnostic_key)
                    completion = HistoricalEventDetailCompletion(
                        request.request_id, request.diagnostic_key,
                        event is not None, event=event)
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
                 query_function: Optional[Callable] = None,
                 index_path: Optional[Path] = None):
        self._session_root = Path(session_root)
        self._app_event_path = Path(app_event_path) if app_event_path else None
        self._query_function = query_function or query_historical_events
        self._index_path = Path(index_path) if index_path is not None else None
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
                query_options = {"cancellation_event": request.cancellation_event}
                if self._index_path is not None:
                    query_options["index_path"] = self._index_path
                result = self._query_function(self._session_root, self._app_event_path,
                                              request.date_range, **query_options)
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
                            cancellation_event: Optional[threading.Event] = None,
                            index_path: Optional[Path] = None
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
    if index_path is not None:
        try:
            return _query_historical_events_with_index(
                Path(session_root), Path(app_event_path) if app_event_path else None,
                date_range, page_size, Path(index_path), cancellation_event)
        except (OSError, sqlite3.Error) as error:
            _raise_if_query_cancelled(cancellation_event)
            result = query_historical_events(
                session_root, app_event_path, date_range, page_size,
                cancellation_event=cancellation_event)
            result.index_degraded = True
            result.index_issue = str(error)
            return result
    descriptor, raw_path = tempfile.mkstemp(prefix="b518-history-query-", suffix=".sqlite3")
    os.close(descriptor)
    store_path = Path(raw_path)
    connection = None
    total_count = 0
    unclassified_count = 0
    source_issue_count = 0
    diagnostic_count = 0
    diagnostics = []
    fallback_source_count = [0]
    fallback_bytes_read = [0]
    fallback_source_versions = {}

    def observe_source(path):
        fallback_source_count[0] += 1
        path = Path(path)
        try:
            fallback_source_versions[str(path)] = _history_source_signature(path)
        except OSError:
            fallback_source_versions[str(path)] = None

    def observe_bytes(count):
        fallback_bytes_read[0] += count
    try:
        connection = sqlite3.connect(str(store_path))
        connection.execute("PRAGMA journal_mode=OFF")
        connection.execute("PRAGMA synchronous=OFF")
        connection.execute(
            "CREATE TABLE matching_events ("
            "event_key TEXT NOT NULL, local_wall_order INTEGER NOT NULL, "
            "aware_rank INTEGER NOT NULL, epoch REAL, stable_identity TEXT NOT NULL, "
            "sequence_number INTEGER NOT NULL, source_order INTEGER NOT NULL, "
            "source_path TEXT NOT NULL, summary_json TEXT NOT NULL, event_json TEXT NOT NULL)"
        )
        connection.execute(
            "CREATE INDEX event_key_lookup ON matching_events(event_key)")
        connection.execute(
            "CREATE TABLE diagnostic_events (diagnostic_ordinal INTEGER PRIMARY KEY, "
            "event_key TEXT NOT NULL, source_path TEXT NOT NULL, "
            "summary_json TEXT NOT NULL, event_json TEXT NOT NULL)")
        connection.execute("CREATE INDEX diagnostic_event_key ON diagnostic_events(event_key)")

        _raise_if_query_cancelled(cancellation_event)
        for event in iter_historical_events(
                session_root, app_event_path, read_observer=observe_bytes,
                source_observer=observe_source):
            _raise_if_query_cancelled(cancellation_event)
            source_issue = event.source in {"read_error", "read_warning"}
            if source_issue:
                source_issue_count += 1
            occurred_at = _parse_occurred_at(
                event.occurred_at, date_range._local_timezone)
            if source_issue or occurred_at is None:
                diagnostic_count += 1
                connection.execute(
                    "INSERT INTO diagnostic_events VALUES (?, ?, ?, ?, ?)",
                    (diagnostic_count, event.key, event.source_path or "",
                     _event_summary_json(event),
                     _event_json(event)))
            if occurred_at is None:
                if not source_issue:
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
                "INSERT INTO matching_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (event.key, local_wall_order, 0 if epoch is not None else 1, epoch,
                 stable_identity, sequence, event.source_order,
                 event.source_path or "",
                 _event_summary_json(event), _event_json(event)))
            total_count += 1

        for source_path, captured_version in fallback_source_versions.items():
            try:
                current_version = _history_source_signature(Path(source_path))
            except OSError:
                current_version = None
            if captured_version == current_version:
                continue
            removed_events = connection.execute(
                "DELETE FROM matching_events WHERE source_path=?", (source_path,))
            total_count -= removed_events.rowcount
            removed_diagnostics = connection.execute(
                "DELETE FROM diagnostic_events WHERE source_path=?", (source_path,))
            diagnostic_count -= removed_diagnostics.rowcount
            source_issue_count += 1
            diagnostic_count += 1
            warning = HistoricalEvent(
                "warning:changed:{}".format(source_path), "read_warning", "",
                "Historical source changed while being read",
                diagnostic="Source version could not be confirmed",
                raw_record={"path": source_path,
                            "reason": "Historical source changed while being read"})
            connection.execute(
                "INSERT INTO diagnostic_events VALUES (?, ?, ?, ?, ?)",
                (diagnostic_count, warning.key, source_path,
                 _event_summary_json(warning), _event_json(warning)))
            if len(diagnostics) < _DIAGNOSTIC_SAMPLE_LIMIT:
                diagnostics.append(warning)

        captured_source_paths = set(fallback_source_versions)
        confirmed_source_paths = {
            str(Path(source.path)) for source in
            iter_historical_event_sources(session_root, app_event_path)}
        for source_path in sorted(confirmed_source_paths - captured_source_paths):
            source_issue_count += 1
            diagnostic_count += 1
            reason = "Historical source appeared while query was running"
            warning = HistoricalEvent(
                "warning:source-added:{}".format(source_path), "read_warning", "",
                reason, diagnostic=reason,
                raw_record={"path": source_path, "reason": reason})
            connection.execute(
                "INSERT INTO diagnostic_events VALUES (?, ?, ?, ?, ?)",
                (diagnostic_count, warning.key, source_path,
                 _event_summary_json(warning), _event_json(warning)))
            if len(diagnostics) < _DIAGNOSTIC_SAMPLE_LIMIT:
                diagnostics.append(warning)

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
            tuple(diagnostics), store_path, page_size,
            HistoricalEventIndexMetrics(
                parsed_source_count=fallback_source_count[0],
                source_bytes_read=fallback_bytes_read[0]),
            diagnostic_count=diagnostic_count)
        result._first_page = result.get_page(1).events
        return result
    except Exception:
        if connection is not None:
            connection.close()
        _remove_snapshot(store_path)
        raise


def _query_historical_events_with_index(session_root: Path,
                                        app_event_path: Optional[Path],
                                        date_range: HistoricalEventDateRange,
                                        page_size: int, index_path: Path,
                                        cancellation_event: Optional[threading.Event]
                                        ) -> HistoricalEventQueryResult:
    index_path = index_path.expanduser().absolute()
    descriptor, raw_path = tempfile.mkstemp(prefix="b518-history-query-", suffix=".sqlite3")
    os.close(descriptor)
    snapshot_path = Path(raw_path)
    connection = None
    snapshot_staging = None
    parsed_sources = 0
    reused_sources = 0
    source_bytes_read = 0
    source_version_checks = 0
    content_write_counts = []
    content_write_bytes = []
    unavailable_keys = set()
    transient_errors = []
    try:
        with _HISTORY_INDEX_LOCK:
            sources = tuple(iter_historical_event_sources(session_root, app_event_path))
            _validate_history_index_path(index_path, session_root, sources)
            index_path.parent.mkdir(parents=True, exist_ok=True)
            connection, rebuilt_index = _open_history_index(index_path)
            snapshot_staging = sqlite3.connect(str(snapshot_path))
            snapshot_staging.execute(
                "CREATE TABLE partial_events ("
                "source_key TEXT NOT NULL, source_ordinal INTEGER NOT NULL, "
                "event_key TEXT NOT NULL, occurred_at TEXT NOT NULL, time_kind INTEGER NOT NULL, "
                "aware_epoch REAL, naive_order INTEGER, stable_identity TEXT NOT NULL, "
                "sequence_number INTEGER NOT NULL, source_order INTEGER NOT NULL, "
                "source TEXT NOT NULL, summary_json TEXT NOT NULL, event_json TEXT NOT NULL)")
            _raise_if_query_cancelled(cancellation_event)
            current_keys = {source.key for source in sources}
            connection.execute("BEGIN IMMEDIATE")
            stale_keys = [row[0] for row in connection.execute(
                "SELECT source_key FROM history_sources") if row[0] not in current_keys]
            for stale_key in stale_keys:
                connection.execute("DELETE FROM history_events WHERE source_key=?",
                                   (stale_key,))
                connection.execute("DELETE FROM history_sources WHERE source_key=?",
                                   (stale_key,))
            for source in sources:
                _raise_if_query_cancelled(cancellation_event)
                try:
                    source_version_checks += 1
                    signature = _history_source_signature(source.path)
                except OSError as error:
                    unavailable_keys.add(source.key)
                    transient_errors.append(_history_read_error(source, str(error)))
                    continue
                cached = connection.execute(
                    "SELECT source_path, device, inode, byte_size, modified_ns, changed_ns, "
                    "event_count FROM history_sources WHERE source_key=?", (source.key,)
                ).fetchone()
                if cached is not None:
                    if (cached[0] == str(Path(source.path).resolve()) and
                            tuple(cached[1:6]) == signature):
                        reused_sources += 1
                        continue

                connection.execute("SAVEPOINT refresh_source")
                connection.execute("DELETE FROM history_events WHERE source_key=?",
                                   (source.key,))
                connection.execute("DELETE FROM history_sources WHERE source_key=?",
                                   (source.key,))
                connection.execute(
                    "INSERT INTO history_sources VALUES (?, ?, ?, ?, ?, ?, ?, 0)",
                    (source.key, str(Path(source.path).resolve())) + signature)
                snapshot_staging.execute("BEGIN")
                read_count = [0]
                source_events = 0
                indexed_content_bytes = 0
                indexed_content_count = 0
                read_error = None
                confirmed_signature = None

                def observe_read(count):
                    read_count[0] += count

                try:
                    for ordinal, event in enumerate(iter_historical_source_events(
                            source, read_observer=observe_read), 1):
                        _raise_if_query_cancelled(cancellation_event)
                        if event.source == "read_error":
                            line_diagnostic = (source.kind == "legacy" and
                                               isinstance(event.raw_record, dict) and
                                               "line_number" in event.raw_record)
                            if not line_diagnostic:
                                read_error = event
                                continue
                        time_kind, aware_epoch, naive_order = _history_event_time(
                            event.occurred_at)
                        sequence = (event.sequence if type(event.sequence) is int
                                    else event.source_order)
                        stable_identity = event.round_id or event.key
                        summary_json = _event_summary_json(event)
                        event_json = _event_json(event)
                        content_id = _event_content_id(summary_json, event_json)
                        inserted = connection.execute(
                            "INSERT OR IGNORE INTO history_contents VALUES (?, ?, ?)",
                            (content_id, summary_json, event_json)).rowcount
                        if inserted:
                            indexed_content_bytes += len(event_json.encode("utf-8"))
                            indexed_content_count += 1
                        event_row = (
                            source.key, ordinal, event.key, event.occurred_at, time_kind,
                            aware_epoch, naive_order, stable_identity, sequence,
                            event.source_order, event.source, content_id)
                        connection.execute(
                            "INSERT INTO history_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            event_row)
                        snapshot_staging.execute(
                            "INSERT INTO partial_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            event_row[:-1] + (summary_json, event_json))
                        source_events += 1
                    confirmed_signature = _history_source_signature(source.path)
                    source_version_checks += 1
                    if confirmed_signature != signature:
                        raise OSError("Historical source changed while it was being indexed: {}".format(
                            source.path))
                    if read_error is not None:
                        raise OSError(read_error.message)
                    connection.execute(
                        "UPDATE history_sources SET event_count=? WHERE source_key=?",
                        (source_events, source.key))
                    connection.execute("RELEASE refresh_source")
                    snapshot_staging.execute(
                        "DELETE FROM partial_events WHERE source_key=?", (source.key,))
                    snapshot_staging.commit()
                    parsed_sources += 1
                    source_bytes_read += read_count[0]
                    # Metrics are accumulated only for committed source versions.
                    content_write_counts.append(indexed_content_count)
                    content_write_bytes.append(indexed_content_bytes)
                except Exception as error:
                    connection.execute("ROLLBACK TO refresh_source")
                    connection.execute("RELEASE refresh_source")
                    if read_error is not None and confirmed_signature == signature:
                        # Keep only this query's verified readable prefix. It stays
                        # outside the durable index so the failed source is retryable.
                        snapshot_staging.commit()
                    else:
                        snapshot_staging.rollback()
                    source_bytes_read += read_count[0]
                    if cancellation_event is not None and cancellation_event.is_set():
                        raise
                    unavailable_keys.add(source.key)
                    transient_errors.append(_history_read_error(source, str(error)))
            confirmed_sources = tuple(iter_historical_event_sources(
                session_root, app_event_path))
            confirmed_by_key = {source.key: source for source in confirmed_sources}
            if current_keys != set(confirmed_by_key):
                changed_keys = current_keys.symmetric_difference(confirmed_by_key)
                for source_key in sorted(changed_keys):
                    source = next((item for item in sources if item.key == source_key),
                                  confirmed_by_key.get(source_key))
                    if source_key not in confirmed_by_key:
                        connection.execute(
                            "DELETE FROM history_events WHERE source_key=?", (source_key,))
                        connection.execute(
                            "DELETE FROM history_sources WHERE source_key=?", (source_key,))
                    if source_key in unavailable_keys:
                        continue
                    source_path = (str(source.path) if source is not None else
                                   str(session_root))
                    reason = "Historical source set changed while query was running"
                    transient_errors.append(HistoricalEvent(
                        "warning:source-boundary:{}".format(source_key), "read_warning", "",
                        reason, diagnostic=reason,
                        raw_record={"source_path": source_path, "reason": reason}))
            _raise_if_query_cancelled(cancellation_event)
            connection.commit()
            snapshot_staging.commit()
            snapshot_staging.close()
            snapshot_staging = None

            snapshot = _create_indexed_query_snapshot(
                connection, snapshot_path, date_range, page_size, unavailable_keys,
                transient_errors, cancellation_event, HistoricalEventIndexMetrics(
                    parsed_sources, reused_sources, source_bytes_read,
                    source_version_checks,
                    indexed_content_write_bytes=sum(content_write_bytes),
                    indexed_content_write_count=sum(content_write_counts)), index_path)
            connection.close()
            connection = None
            if rebuilt_index:
                snapshot.index_degraded = True
                snapshot.index_issue = "The historical query index was rebuilt."
            return snapshot
    except Exception:
        if snapshot_staging is not None:
            snapshot_staging.close()
        if connection is not None:
            connection.rollback()
            connection.close()
        _remove_snapshot(snapshot_path)
        raise


def _validate_history_index_path(index_path: Path, session_root: Path,
                                 sources: Tuple[HistoricalEventSource, ...]) -> None:
    if index_path.is_symlink():
        raise ValueError("Historical event index path cannot be a symbolic link")
    index_real_path = index_path.resolve()
    source_paths = {Path(source.path).resolve() for source in sources}
    if index_real_path in source_paths:
        raise ValueError("Historical event index cannot replace a source file")
    root = Path(session_root).resolve()
    try:
        if os.path.commonpath((str(root), str(index_real_path))) == str(root):
            raise ValueError("Historical event index must remain outside session sources")
    except ValueError as error:
        if str(error) == "Historical event index must remain outside session sources":
            raise


def _history_source_signature(path: Path) -> Tuple[int, int, int, int, int]:
    details = Path(path).stat()
    return (details.st_dev, details.st_ino, details.st_size,
            details.st_mtime_ns, details.st_ctime_ns)


def _history_event_time(value: str):
    if not value:
        return 2, None, None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            naive_order = ((parsed.toordinal() * 86400 + parsed.hour * 3600 +
                            parsed.minute * 60 + parsed.second) * 1000000 +
                           parsed.microsecond)
            return 1, None, naive_order
        return 0, parsed.timestamp(), None
    except (TypeError, ValueError, OverflowError, OSError):
        return 2, None, None


def _history_read_error(source: HistoricalEventSource, reason: str) -> HistoricalEvent:
    source_name = "app" if source.kind == "app" else "round"
    return HistoricalEvent("error:{}:{}".format(source_name, source.path), "read_error", "",
                           reason, diagnostic=reason,
                           raw_record={"source_path": str(source.path)})


def _open_history_index(index_path: Path):
    def create_database():
        database = sqlite3.connect(str(index_path), timeout=30.0)
        os.chmod(str(index_path), 0o600)
        database.execute("PRAGMA journal_mode=DELETE")
        database.execute("PRAGMA synchronous=FULL")
        database.execute("PRAGMA foreign_keys=ON")
        database.execute("PRAGMA application_id={}".format(_HISTORY_INDEX_APPLICATION_ID))
        database.execute("PRAGMA user_version={}".format(_HISTORY_INDEX_VERSION))
        database.executescript(
            "CREATE TABLE history_sources ("
            "source_key TEXT PRIMARY KEY, source_path TEXT NOT NULL, device INTEGER NOT NULL, "
            "inode INTEGER NOT NULL, byte_size INTEGER NOT NULL, modified_ns INTEGER NOT NULL, "
            "changed_ns INTEGER NOT NULL, event_count INTEGER NOT NULL);"
            "CREATE TABLE history_contents ("
            "content_id TEXT PRIMARY KEY, summary_json TEXT NOT NULL, event_json TEXT NOT NULL);"
            "CREATE TABLE history_queries (query_id TEXT PRIMARY KEY, process_id INTEGER NOT NULL);"
            "CREATE TABLE history_events ("
            "source_key TEXT NOT NULL, source_ordinal INTEGER NOT NULL, event_key TEXT NOT NULL, "
            "occurred_at TEXT NOT NULL, time_kind INTEGER NOT NULL, aware_epoch REAL, "
            "naive_order INTEGER, stable_identity TEXT NOT NULL, sequence_number INTEGER NOT NULL, "
            "source_order INTEGER NOT NULL, source TEXT NOT NULL, content_id TEXT NOT NULL, "
            "PRIMARY KEY(source_key, source_ordinal), "
            "FOREIGN KEY(source_key) REFERENCES history_sources(source_key) ON DELETE CASCADE);"
            "CREATE INDEX history_aware_time ON history_events(time_kind, aware_epoch);"
            "CREATE INDEX history_naive_time ON history_events(time_kind, naive_order);"
            "CREATE INDEX history_event_identity ON history_events(event_key);"
            "CREATE INDEX history_unclassified ON history_events("
            "time_kind, source_key, source_ordinal);"
            "CREATE INDEX history_source_issues ON history_events(source, source_key);")
        database.commit()
        return database

    if not index_path.exists():
        return create_database(), False
    database = None
    try:
        database = sqlite3.connect(str(index_path), timeout=30.0)
        database.execute("PRAGMA synchronous=FULL")
        database.execute("PRAGMA foreign_keys=ON")
        version = database.execute("PRAGMA user_version").fetchone()[0]
        application_id = database.execute("PRAGMA application_id").fetchone()[0]
        if (version != _HISTORY_INDEX_VERSION or
                application_id != _HISTORY_INDEX_APPLICATION_ID):
            raise sqlite3.DatabaseError("unsupported historical event index version")
        source_columns = {row[1] for row in database.execute(
            "PRAGMA table_info(history_sources)")}
        event_columns = {row[1] for row in database.execute(
            "PRAGMA table_info(history_events)")}
        if not {"source_key", "source_path", "device", "inode", "byte_size", "modified_ns",
                "changed_ns", "event_count"}.issubset(source_columns) or not {
                "source_key", "source_ordinal", "event_key", "occurred_at", "time_kind",
                "aware_epoch", "naive_order", "stable_identity", "sequence_number",
                "source_order", "source", "content_id"}.issubset(
                    event_columns):
            raise sqlite3.DatabaseError("unsupported historical event index version")
        _reclaim_abandoned_query_contents(database)
        return database, False
    except sqlite3.DatabaseError as error:
        if database is not None:
            database.close()
        error_text = str(error).lower()
        if not any(marker in error_text for marker in (
                "unsupported historical event index version", "file is not a database",
                "database disk image is malformed", "no such table")):
            raise
        index_path.unlink(missing_ok=True)
        for suffix in ("-journal", "-wal", "-shm"):
            Path(str(index_path) + suffix).unlink(missing_ok=True)
        return create_database(), True


def _create_indexed_query_snapshot(connection: sqlite3.Connection, snapshot_path: Path,
                                   date_range: HistoricalEventDateRange, page_size: int,
                                   unavailable_keys, transient_errors,
                                   cancellation_event, index_metrics, index_path: Path):
    snapshot = sqlite3.connect(str(snapshot_path))
    query_id = uuid.uuid4().hex
    try:
        # Hold one consistent content generation until every snapshot reference
        # is registered; a second process cannot prune content mid-publication.
        connection.execute("BEGIN IMMEDIATE")
        snapshot.execute("PRAGMA journal_mode=OFF")
        snapshot.execute("PRAGMA synchronous=OFF")
        snapshot.execute(
            "CREATE TABLE matching_events ("
            "event_key TEXT NOT NULL, local_wall_order INTEGER NOT NULL, "
            "aware_rank INTEGER NOT NULL, epoch REAL, stable_identity TEXT NOT NULL, "
            "sequence_number INTEGER NOT NULL, source_order INTEGER NOT NULL, "
            "content_id TEXT NOT NULL)")
        snapshot.execute("CREATE INDEX event_key_lookup ON matching_events(event_key)")
        snapshot.execute(
            "CREATE TABLE diagnostic_events (diagnostic_ordinal INTEGER PRIMARY KEY, "
            "event_key TEXT NOT NULL, content_id TEXT NOT NULL)")
        snapshot.execute("CREATE INDEX diagnostic_event_key ON diagnostic_events(event_key)")
        start_naive = _naive_wall_order(datetime.combine(date_range.start, datetime_time.min))
        end_naive = _naive_wall_order(
            datetime.combine(date_range.end + timedelta(days=1), datetime_time.min))
        sql = ("SELECT event_key, occurred_at, time_kind, aware_epoch, naive_order, "
               "stable_identity, sequence_number, source_order, content_id "
               "FROM history_events WHERE ")
        parameters = []
        if unavailable_keys:
            sql += "source_key NOT IN ({}) AND ".format(
                ",".join("?" for _ in unavailable_keys))
            parameters.extend(sorted(unavailable_keys))
        sql += ("((time_kind=0 AND aware_epoch>=? AND aware_epoch<?) OR "
                "(time_kind=1 AND naive_order>=? AND naive_order<?)) ")
        parameters.extend((date_range._start_epoch, date_range._end_epoch,
                           start_naive, end_naive))

        total_count = 0
        cursor = connection.execute(sql, parameters)
        while True:
            _raise_if_query_cancelled(cancellation_event)
            rows = cursor.fetchmany(HISTORICAL_EVENT_QUERY_PAGE_SIZE)
            if not rows:
                break
            for row in rows:
                event_key, value, time_kind, aware_epoch, naive_order, stable_identity, \
                    sequence, source_order, content_id = row
                parsed = _parse_occurred_at(value, date_range._local_timezone)
                if parsed is None:
                    continue
                parsed_value, epoch, local_wall_order = parsed
                if epoch is None:
                    in_range = date_range.start <= parsed_value.date() <= date_range.end
                else:
                    in_range = date_range._start_epoch <= epoch < date_range._end_epoch
                if not in_range:
                    continue
                snapshot.execute(
                    "INSERT INTO matching_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (event_key, local_wall_order, 0 if epoch is not None else 1, epoch,
                     stable_identity, sequence, source_order, content_id))
                total_count += 1

        if unavailable_keys:
            placeholders = ",".join("?" for _ in unavailable_keys)
            source_filter = "source_key NOT IN ({}) AND ".format(placeholders)
            source_params = tuple(sorted(unavailable_keys))
        else:
            source_filter = ""
            source_params = ()
        unclassified_count = connection.execute(
            "SELECT COUNT(*) FROM history_events WHERE {}time_kind=2 AND source NOT IN "
            "('read_warning', 'read_error')".format(source_filter),
            source_params).fetchone()[0]
        source_issue_count = connection.execute(
            "SELECT COUNT(*) FROM history_events WHERE {}source IN "
            "('read_warning', 'read_error')".format(source_filter),
            source_params).fetchone()[0]
        diagnostic_rows = connection.execute(
            "SELECT event_key, content_id FROM history_events WHERE {}"
            "(time_kind=2 OR source IN ('read_warning', 'read_error')) "
            "ORDER BY source_key, source_ordinal".format(source_filter), source_params)
        diagnostic_count = 0
        diagnostics = []
        for row in diagnostic_rows:
            diagnostic_count += 1
            snapshot.execute("INSERT INTO diagnostic_events VALUES (?, ?, ?)",
                             (diagnostic_count, row[0], row[1]))
            if len(diagnostics) < _DIAGNOSTIC_SAMPLE_LIMIT:
                diagnostics.append(_event_from_json(connection.execute(
                    "SELECT event_json FROM history_contents WHERE content_id=?",
                    (row[1],)).fetchone()[0]))
        partial_rows = snapshot.execute(
            "SELECT event_key, occurred_at, time_kind, aware_epoch, naive_order, "
            "stable_identity, sequence_number, source_order, source, summary_json, event_json "
            "FROM partial_events ORDER BY source_key, source_ordinal")
        for row in partial_rows:
            _raise_if_query_cancelled(cancellation_event)
            (event_key, value, _time_kind, _aware_epoch, _naive_order,
             stable_identity, sequence, source_order, source, summary_json, event_json) = row
            event = _event_from_json(event_json)
            source_issue = source in {"read_error", "read_warning"}
            if source_issue:
                source_issue_count += 1
            parsed = _parse_occurred_at(value, date_range._local_timezone)
            if source_issue or parsed is None:
                diagnostic_count += 1
                content_id = _event_content_id(summary_json, event_json)
                connection.execute("INSERT OR IGNORE INTO history_contents VALUES (?, ?, ?)",
                                   (content_id, summary_json, event_json))
                snapshot.execute("INSERT INTO diagnostic_events VALUES (?, ?, ?)",
                                 (diagnostic_count, event_key, content_id))
                if len(diagnostics) < _DIAGNOSTIC_SAMPLE_LIMIT:
                    diagnostics.append(event)
            if parsed is None:
                if not source_issue:
                    unclassified_count += 1
                continue
            parsed_value, epoch, local_wall_order = parsed
            if epoch is None:
                in_range = date_range.start <= parsed_value.date() <= date_range.end
            else:
                in_range = date_range._start_epoch <= epoch < date_range._end_epoch
            if in_range:
                content_id = _event_content_id(summary_json, event_json)
                connection.execute("INSERT OR IGNORE INTO history_contents VALUES (?, ?, ?)",
                                   (content_id, summary_json, event_json))
                snapshot.execute(
                    "INSERT INTO matching_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (event_key, local_wall_order, 0 if epoch is not None else 1, epoch,
                     stable_identity, sequence, source_order, content_id))
                total_count += 1
        snapshot.execute("DROP TABLE partial_events")
        source_issue_count += len(transient_errors)
        for event in transient_errors:
            diagnostic_count += 1
            summary_json = _event_summary_json(event)
            event_json = _event_json(event)
            content_id = _event_content_id(summary_json, event_json)
            connection.execute("INSERT OR IGNORE INTO history_contents VALUES (?, ?, ?)",
                               (content_id, summary_json, event_json))
            snapshot.execute("INSERT INTO diagnostic_events VALUES (?, ?, ?)",
                             (diagnostic_count, event.key, content_id))
            if len(diagnostics) < _DIAGNOSTIC_SAMPLE_LIMIT:
                diagnostics.append(event)
        snapshot.execute("CREATE INDEX event_order_lookup ON matching_events("
                         "local_wall_order DESC, aware_rank ASC, epoch DESC, "
                         "stable_identity ASC, sequence_number ASC, event_key ASC, "
                         "source_order ASC)")
        snapshot.commit()
        connection.execute("INSERT INTO history_queries VALUES (?, ?)",
                           (query_id, os.getpid()))
        _reclaim_unreferenced_contents(connection)
        connection.commit()
        snapshot.close()
        result = HistoricalEventQueryResult(
            date_range, total_count, unclassified_count, source_issue_count,
            tuple(diagnostics), snapshot_path, page_size, index_metrics,
            diagnostic_count=diagnostic_count, index_path=index_path, query_id=query_id)
        result._first_page = result.get_page(1).events
        return result
    except Exception:
        connection.rollback()
        if query_id:
            connection.execute("DELETE FROM history_queries WHERE query_id=?", (query_id,))
            connection.commit()
        snapshot.close()
        _remove_snapshot(snapshot_path)
        raise


def _naive_wall_order(value: datetime) -> int:
    return ((value.toordinal() * 86400 + value.hour * 3600 + value.minute * 60 +
             value.second) * 1000000 + value.microsecond)


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
