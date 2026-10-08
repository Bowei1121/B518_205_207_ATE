"""Durable, versioned records for App events that do not belong to a round."""

from __future__ import annotations

import json
import os
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


def _json_bytes(payload: object) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _atomic_replace(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".{}-".format(path.name), dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, str(path))
        try:
            directory_fd = os.open(str(path.parent), os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            pass
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
    seen = set()
    for expected, event in enumerate(payload["events"], 1):
        if (not isinstance(event, dict) or event.get("record_type") != "app_event" or
                event.get("schema_version") != APP_EVENT_STORE_VERSION or
                event.get("sequence") != expected or
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
    return payload


class AppEventStore:
    """Capture bilingual App events and append them in order on a worker."""

    def __init__(self, path: Path, clock: Callable[[], datetime] = None):
        self.path = Path(path)
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._condition = threading.Condition()
        self._pending: Deque[AppEvent] = deque()
        self._events = []
        self._error = ""
        self._error_history = []
        self._worker_active = False
        self._stopped = False
        try:
            if self.path.exists():
                self._events = read_app_event_store(self.path)["events"]
        except Exception as error:
            self._error = str(error)
            self._error_history.append(self._error)

    @staticmethod
    def _payload(events) -> dict:
        return {"record_type": "app_event_store", "schema_version": APP_EVENT_STORE_VERSION,
                "events": list(events)}

    @property
    def events(self) -> Tuple[AppEvent, ...]:
        with self._condition:
            return tuple(self._pending)

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
            sequence = len(self._events) + len(self._pending) + 1
            event = AppEvent(uuid.uuid4().hex, sequence, moment.isoformat(timespec="microseconds"),
                             kind, message, diagnostic)
            self._pending.append(event)
            self._ensure_worker_locked()
            return event

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
                    current = list(self._events)
                try:
                    # Detect a replace that succeeded before a filesystem wrapper reported failure.
                    disk_events = (read_app_event_store(self.path)["events"]
                                   if self.path.exists() else [])
                    if not any(item["event_id"] == event.event_id for item in disk_events):
                        record = event.as_record()
                        if record["sequence"] != len(disk_events) + 1:
                            record["sequence"] = len(disk_events) + 1
                            event = AppEvent(event.event_id, record["sequence"], event.occurred_at,
                                             event.kind, event.message, event.diagnostic)
                        _atomic_replace(self.path, _json_bytes(self._payload(disk_events + [record])))
                        disk_events.append(record)
                    with self._condition:
                        self._events = disk_events
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
