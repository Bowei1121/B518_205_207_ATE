"""Durable, versioned records for App events that do not belong to a round."""

from __future__ import annotations

import json
import os
import stat
import tempfile
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Deque, Optional, Tuple

from language_catalog import BilingualMessage, make_bilingual_message


APP_EVENT_STORE_VERSION = 1
_IDLE_WORKER_TIMEOUT_SECONDS = 0.2


@dataclass(frozen=True)
class AppEvent:
    """An immutable App-owned event; it intentionally has no round_id."""

    event_id: str
    sequence: int
    occurred_at: str
    kind: str
    message: BilingualMessage
    diagnostic: str = ""

    def as_record(self) -> dict:
        return {
            "record_type": "app_event",
            "schema_version": APP_EVENT_STORE_VERSION,
            "event_id": self.event_id,
            "sequence": self.sequence,
            "occurred_at": self.occurred_at,
            "kind": self.kind,
            "message": self.message.english,
            "localized_message": self.message.as_record(),
            "diagnostic": self.diagnostic,
        }


@dataclass(frozen=True)
class AppEventSaveStatus:
    status: str = "complete"
    pending_count: int = 0
    error: str = ""
    error_history: Tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        return self.status == "complete" and self.pending_count == 0


@dataclass(frozen=True)
class AppEventCleanupResult:
    """Outcome of pruning eligible records from the managed App journal."""

    status: str
    deleted_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    reason: str = ""


def _json_bytes(payload: object) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _fsync_directory(directory: Path) -> None:
    descriptor = os.open(str(directory), os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_replace(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".{}-".format(path.name), dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, str(path))
        _fsync_directory(path.parent)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def read_app_event_store(path: Path) -> dict:
    """Read and validate a fresh App event store without mutating old data."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("App 事件紀錄無法讀取：{}".format(error))
    if (not isinstance(payload, dict) or payload.get("record_type") != "app_event_store" or
            type(payload.get("schema_version")) is not int or
            payload["schema_version"] != APP_EVENT_STORE_VERSION or
            not isinstance(payload.get("events"), list)):
        raise ValueError("App 事件紀錄格式或版本不受支援")
    retired = payload.get("retired_sequences")
    next_sequence = payload.get("next_sequence")
    if "retired_sequences" not in payload and "next_sequence" not in payload:
        retired = []
        next_sequence = len(payload["events"]) + 1
    elif "retired_sequences" not in payload or "next_sequence" not in payload:
        raise ValueError("App 事件紀錄序號保留資訊不完整")
    if (not isinstance(retired, list) or type(next_sequence) is not int or
            next_sequence < 1):
        raise ValueError("App 事件紀錄序號保留資訊無效")
    retired_ranges = []
    previous_end = 0
    for item in retired:
        if (not isinstance(item, list) or len(item) != 2 or
                type(item[0]) is not int or type(item[1]) is not int or
                item[0] <= previous_end or item[1] < item[0] or
                item[1] >= next_sequence):
            raise ValueError("App 事件紀錄序號保留範圍無效")
        retired_ranges.append((item[0], item[1]))
        previous_end = item[1]
    seen = set()
    previous_sequence = 0
    live_sequences = set()
    for event in payload["events"]:
        if (not isinstance(event, dict) or event.get("record_type") != "app_event" or
                event.get("schema_version") != APP_EVENT_STORE_VERSION or
                type(event.get("sequence")) is not int or event["sequence"] <= previous_sequence or
                event["sequence"] >= next_sequence or
                not isinstance(event.get("event_id"), str) or not event["event_id"] or
                event["event_id"] in seen or "round_id" in event or
                not isinstance(event.get("occurred_at"), str) or
                not isinstance(event.get("kind"), str) or
                not isinstance(event.get("localized_message"), dict) or
                event["localized_message"].get("version") != 1 or
                not isinstance(event["localized_message"].get("message_id"), str) or
                not isinstance(event["localized_message"].get("parameters"), dict) or
                not isinstance(event["localized_message"].get("en"), str) or
                not isinstance(event["localized_message"].get("zh-TW"), str) or
                not isinstance(event.get("diagnostic", ""), str)):
            raise ValueError("App 事件紀錄內容不完整或序號不連續")
        try:
            occurred_at = datetime.fromisoformat(event["occurred_at"])
        except ValueError:
            raise ValueError("App 事件時間格式無效")
        if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
            raise ValueError("App 事件時間缺少時區")
        seen.add(event["event_id"])
        live_sequences.add(event["sequence"])
        previous_sequence = event["sequence"]
    if "retired_sequences" not in payload and [item["sequence"] for item in payload["events"]] != list(
            range(1, next_sequence)):
        raise ValueError("App 事件紀錄內容不完整或序號不連續")
    retired_count = sum(end - start + 1 for start, end in retired_ranges)
    if len(live_sequences) + retired_count != next_sequence - 1:
        raise ValueError("App 事件紀錄存在未解釋的序號缺口")
    for start, end in retired_ranges:
        if any(start <= sequence <= end for sequence in live_sequences):
            raise ValueError("App 事件紀錄已刪除序號仍有事件")
    return payload


class AppEventStore:
    """Capture bilingual App events and append them in order on a worker."""

    def __init__(self, path: Path, clock: Callable[[], datetime] = None):
        self.path = Path(path)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._condition = threading.Condition()
        self._io_lock = threading.Lock()
        self._pending: Deque[AppEvent] = deque()
        self._events = []
        self._next_sequence = 1
        self._retired_sequences = []
        self._revision = 0
        self._error = ""
        self._error_history = []
        self._worker_active = False
        self._stopped = False
        try:
            if self.path.exists():
                payload = read_app_event_store(self.path)
                self._events = payload["events"]
                self._next_sequence = payload.get("next_sequence", len(self._events) + 1)
                self._retired_sequences = payload.get("retired_sequences", [])
                self._revision = len(self._events)
        except Exception as error:
            self._error = str(error)
            self._error_history.append(self._error)

    @staticmethod
    def _payload(events, next_sequence=None, retired_sequences=()) -> dict:
        payload = {"record_type": "app_event_store", "schema_version": APP_EVENT_STORE_VERSION,
                   "events": list(events)}
        if retired_sequences:
            payload["retired_sequences"] = [list(item) for item in retired_sequences]
            payload["next_sequence"] = next_sequence
        return payload

    @property
    def events(self) -> Tuple[AppEvent, ...]:
        with self._condition:
            return tuple(self._pending)

    @property
    def revision(self) -> int:
        """Return a cheap token that changes when a new event is captured."""
        with self._condition:
            return self._revision

    @property
    def records(self) -> Tuple[dict, ...]:
        """Return persisted and pending immutable snapshots for diagnostics UI."""
        with self._condition:
            persisted = list(self._events)
            pending = [event.as_record() for event in self._pending]
        known = {item["event_id"] for item in persisted}
        persisted.extend(item for item in pending if item["event_id"] not in known)
        return tuple(json.loads(json.dumps(item, ensure_ascii=False)) for item in persisted)

    def record(self, message_id: str, parameters=None, diagnostic: str = "",
               kind: str = "app_diagnostic") -> AppEvent:
        captured = json.loads(json.dumps(parameters or {}, ensure_ascii=False, sort_keys=True))
        message = make_bilingual_message(message_id, captured, diagnostic)
        moment = self._clock()
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        with self._condition:
            sequence = self._next_sequence
            self._next_sequence += 1
            event = AppEvent(uuid.uuid4().hex, sequence, moment.isoformat(timespec="microseconds"),
                             kind, message, diagnostic)
            self._pending.append(event)
            self._revision += 1
            self._ensure_worker_locked()
            return event

    def cleanup_expired(self, cutoff: datetime, managed_root: Path,
                        before_replace: Callable[[datetime, Callable[[], None]], None] = None
                        ) -> AppEventCleanupResult:
        """Delete only fully persisted, timezone-valid App events at or before cutoff.

        This runs inside the existing background retention worker. It rewrites only
        the App-owned journal, records retired sequence ranges, and refuses links,
        corrupt input, pending writes, or journals outside the managed root.
        """
        if (cutoff.tzinfo is None or cutoff.utcoffset() is None):
            return AppEventCleanupResult("skipped", skipped_count=1,
                                          reason="期限時間缺少時區")
        try:
            requested_root = Path(managed_root).absolute()
            if requested_root.is_symlink() or not requested_root.is_dir():
                raise ValueError("App 事件管理根目錄不是實體目錄")
            root = requested_root.resolve()
            requested_path = self.path.absolute()
            if requested_path.is_symlink():
                raise ValueError("App 事件清理拒絕符號連結")
            resolved_path = requested_path.resolve()
            resolved_path.relative_to(root)
            self._validate_managed_path(root)
            relative = resolved_path.relative_to(root)
            if not relative.parts or any(part in {".", ".."} for part in relative.parts):
                raise ValueError("App 事件檔不在管理根目錄")
            for part in relative.parts[:-1]:
                root = root / part
                self._validate_managed_path(root)
            self._validate_managed_path(resolved_path)
        except (OSError, ValueError) as error:
            return AppEventCleanupResult("skipped", skipped_count=1, reason=str(error))

        with self._io_lock:
            with self._condition:
                if self._pending or self._worker_active or self._error:
                    return AppEventCleanupResult(
                        "skipped", skipped_count=1,
                        reason="App 事件保存待補存或狀態尚未確認完整")
            if not self.path.exists():
                return AppEventCleanupResult("complete")
            try:
                original_stat = self.path.lstat()
                if not stat.S_ISREG(original_stat.st_mode):
                    raise ValueError("App 事件目標不是一般檔案")
                original_bytes = self.path.read_bytes()
                payload = read_app_event_store(self.path)
                cutoff_utc = cutoff.astimezone(timezone.utc)
                retained = []
                expired_sequences = []
                expired_times = []
                for event in payload["events"]:
                    occurred_at = datetime.fromisoformat(event["occurred_at"])
                    if occurred_at.astimezone(timezone.utc) <= cutoff_utc:
                        expired_sequences.append(event["sequence"])
                        expired_times.append(occurred_at)
                    else:
                        retained.append(event)
                if not expired_sequences:
                    return AppEventCleanupResult("complete")
                retired = list(payload.get("retired_sequences", []))
                retired.extend([[sequence, sequence] for sequence in expired_sequences])
                merged = []
                for start, end in sorted((item[0], item[1]) for item in retired):
                    if merged and start <= merged[-1][1] + 1:
                        merged[-1][1] = max(merged[-1][1], end)
                    else:
                        merged.append([start, end])
                updated = self._payload(retained, payload.get("next_sequence", max(
                    (item["sequence"] for item in payload["events"]), default=0) + 1), merged)
                # Refuse a path/content swap discovered after qualification.
                self._validate_managed_path(self.path.absolute())
                if self.path.read_bytes() != original_bytes:
                    raise ValueError("App 事件紀錄在清理期間已變更")
                replace = lambda: _atomic_replace(self.path, _json_bytes(updated))
                if before_replace is not None:
                    before_replace(max(expired_times), replace)
                else:
                    replace()
                with self._condition:
                    self._events = retained
                    self._retired_sequences = merged
                    self._revision += 1
                    self._error = ""
                return AppEventCleanupResult("complete", deleted_count=len(expired_sequences))
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
                return AppEventCleanupResult("failed", failed_count=1, reason=str(error))

    @staticmethod
    def _validate_managed_path(path: Path) -> None:
        if path.is_symlink():
            raise ValueError("App 事件清理拒絕符號連結")
        if path.exists() and path != path.parent and not (path.is_dir() or path.is_file()):
            raise ValueError("App 事件清理目標不是一般檔案或目錄")

    def status(self) -> AppEventSaveStatus:
        with self._condition:
            if self._error:
                state = "failed"
            elif self._pending or self._worker_active:
                state = "saving"
            else:
                state = "complete"
            return AppEventSaveStatus(state, len(self._pending), self._error,
                                      tuple(self._error_history))

    def retry(self) -> bool:
        """Start at most one nonblocking retry; the captured events are unchanged."""
        with self._condition:
            if not self._pending:
                return True
            if self._worker_active:
                return False
            self._error = ""
            self._ensure_worker_locked()
            self._condition.notify_all()
            return True

    def flush(self, timeout: Optional[float] = 10.0) -> bool:
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._condition:
            while self._pending or self._worker_active:
                if self._error:
                    return False
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    return False
                self._condition.wait(remaining)
            return not self._error

    def stop(self) -> None:
        """Stop an idle worker after successful close; pending recovery stays intact."""
        with self._condition:
            self._stopped = True
            self._condition.notify_all()

    def _ensure_worker_locked(self) -> None:
        if self._worker_active or self._error or self._stopped or not self._pending:
            return
        self._worker_active = True
        threading.Thread(target=self._write_worker, daemon=True).start()

    def _write_worker(self) -> None:
        try:
            while True:
                with self._condition:
                    if not self._pending:
                        self._worker_active = False
                        self._condition.notify_all()
                        return
                    event = self._pending[0]
                try:
                    with self._io_lock:
                        disk_payload = (read_app_event_store(self.path)
                                        if self.path.exists() else self._payload([]))
                        disk_events = list(disk_payload["events"])
                        disk_next_sequence = disk_payload.get("next_sequence", len(disk_events) + 1)
                        if not any(item["event_id"] == event.event_id for item in disk_events):
                            record = event.as_record()
                            if record["sequence"] != disk_next_sequence:
                                raise ValueError("App 事件待補存序號與磁碟進度不一致")
                            next_sequence = disk_next_sequence + 1
                            _atomic_replace(self.path, _json_bytes(self._payload(
                                disk_events + [record], next_sequence,
                                disk_payload.get("retired_sequences", []))))
                            disk_events.append(record)
                        else:
                            # A prior replace may have succeeded before directory fsync failed.
                            # Reconfirm the directory entry before reporting durable completion.
                            _fsync_directory(self.path.parent)
                            next_sequence = disk_next_sequence
                        with self._condition:
                            self._events = disk_events
                            self._next_sequence = max(self._next_sequence, next_sequence)
                            self._retired_sequences = disk_payload.get("retired_sequences", [])
                            if self._pending and self._pending[0].event_id == event.event_id:
                                self._pending.popleft()
                            self._error = ""
                            self._condition.notify_all()
                except Exception as error:
                    with self._condition:
                        self._error = str(error)
                        self._error_history.append(self._error)
                        self._worker_active = False
                        self._condition.notify_all()
                    return
        finally:
            with self._condition:
                if self._worker_active and not self._pending:
                    self._worker_active = False
                self._condition.notify_all()
