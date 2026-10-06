"""Versioned, append-only round audit records and disk-only reconstruction."""

from __future__ import annotations

import json
import math
import os
import tempfile
import threading
import queue
import weakref
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional


AUDIT_SCHEMA_VERSION = 1
_IDLE_WORKER_TIMEOUT_SECONDS = 0.2
_LOCKS = weakref.WeakValueDictionary()  # type: Dict[str, threading.RLock]
_LOCKS_GUARD = threading.Lock()


class AuditRecordError(ValueError):
    """A round audit log is missing, unsupported, or incomplete."""


@dataclass(frozen=True)
class AuditEvent:
    """One shared-round event captured with the values needed for durable audit."""

    sequence: int
    kind: str
    message: str
    display_position: Optional[int]
    sn: str = ""
    status: str = ""
    source: str = ""
    detail: Dict[str, object] = field(default_factory=dict)


def _lock_for(path: Path):
    key = str(path.resolve())
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.RLock())


def _json_bytes(payload) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str) + "\n").encode("utf-8")


def _replace_file(path: Path, content: bytes) -> None:
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
            # The file itself is durable; some filesystems do not fsync directories.
            pass
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


class RoundAuditStore:
    """Keep a recoverable event journal beside each round's existing Session files."""

    def __init__(self, root: Path, round_id: str, station: str,
                 accepted_start_at: str, accepted_start_monotonic: float,
                 config: Optional[dict] = None, on_error=None):
        self.path = Path(root) / round_id
        self.round_id = round_id
        self.station = station
        self._lock = _lock_for(self.path / "audit.jsonl")
        self._queue = queue.Queue()
        self._pending = 0
        self._condition = threading.Condition()
        self._last_enqueued_sequence = 0
        self._error = None
        self._on_error = on_error
        self._header = {
            "record_type": "round",
            "schema_version": AUDIT_SCHEMA_VERSION,
            "round_id": round_id,
            "station": station,
            "accepted_start_at": accepted_start_at,
            "accepted_start_monotonic": accepted_start_monotonic,
            "config": config or {},
            "time_contract": {
                "accepted_start_at": "app wall-clock observation time",
                "source_time": "platform-provided source time; null when unavailable",
                "observed_at": "app wall-clock observation time",
                "operation_at": "operator action wall-clock time",
                "elapsed_seconds": "monotonic elapsed time from accepted start",
            },
            "legacy_session_path": None,
        }
        with self._lock:
            path = self.path / "audit.jsonl"
            if path.exists():
                existing = read_round_audit(path)
                if existing["round"]["round_id"] != round_id:
                    raise AuditRecordError("輪次紀錄識別不符")
                self._last_enqueued_sequence = (existing["events"][-1]["sequence"]
                                                if existing["events"] else 0)
            else:
                self._pending += 1
                self._queue.put(self._header)
        self._writer = None
        with self._condition:
            self._ensure_worker_locked()

    @property
    def audit_path(self) -> Path:
        return self.path / "audit.jsonl"

    def attach_session(self, session_path: Path) -> None:
        """Move early preparation records into the conventional Session folder."""
        self.flush()
        destination = Path(session_path)
        destination_lock = _lock_for(destination / "audit.jsonl")
        source_lock = self._lock
        first_lock, second_lock = sorted((source_lock, destination_lock), key=id)
        with first_lock:
            with second_lock:
                current = self.audit_path
                if current.parent.resolve() == destination.resolve():
                    return
                destination.mkdir(parents=True, exist_ok=True)
                payload = read_round_audit(current)
                header = dict(payload["round"])
                header["legacy_session_path"] = str(destination)
                events = payload["events"]
                _replace_file(destination / "audit.jsonl",
                              b"".join(_json_bytes(item) for item in [header] + events))
                try:
                    current.unlink()
                    self.path.rmdir()
                except OSError:
                    pass
                self.path = destination
                self._header = header
                self._lock = destination_lock

    def append_event(self, event: AuditEvent, observed_at: str,
                     elapsed_seconds: float) -> None:
        detail = dict(event.detail)
        record = {
            "record_type": "event",
            "schema_version": AUDIT_SCHEMA_VERSION,
            "round_id": self.round_id,
            "sequence": event.sequence,
            "kind": event.kind,
            "message": event.message,
            "observed_at": observed_at,
            "elapsed_seconds": max(0.0, elapsed_seconds),
            "display_position": event.display_position,
            "source_position": _first(detail, "source_position", "source_slot", "thread", "slot"),
            "sn": event.sn or None,
            "status": event.status or None,
            "source": event.source or None,
            "source_id": _first(detail, "source_id", "source_identifier"),
            "source_time": _first(detail, "source_time", "source_timestamp"),
            "operation_at": _first(detail, "operation_at", "selected_at", "acknowledged_at", "operator_at"),
            "date_evidence": _first(detail, "date", "date_evidence", "caseinfo_date"),
            "batch_evidence": _first(detail, "batch_id", "batch", "round_evidence_id"),
            "detail": detail or {},
        }
        with self._condition:
            previous_sequence = self._last_enqueued_sequence
            if event.sequence <= previous_sequence:
                raise AuditRecordError("輪次事件序號未遞增：前筆 {}，收到 {}".format(
                    previous_sequence, event.sequence))
            self._last_enqueued_sequence = event.sequence
            self._pending += 1
            self._queue.put(record)
            self._ensure_worker_locked()

    @property
    def pending(self) -> bool:
        with self._condition:
            return self._pending > 0

    @property
    def error(self) -> Optional[str]:
        with self._condition:
            return self._error

    def flush(self, timeout: Optional[float] = 10.0) -> bool:
        """Wait until enqueued events are durable; return false on timeout or error."""
        import time
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._condition:
            while self._pending:
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    return False
                self._condition.wait(remaining)
            return self._error is None

    def _write_worker(self) -> None:
        while True:
            try:
                record = self._queue.get(timeout=_IDLE_WORKER_TIMEOUT_SECONDS)
            except queue.Empty:
                with self._condition:
                    if self._pending == 0:
                        self._writer = None
                        return
                continue
            try:
                if record.get("record_type") == "round":
                    self.path.mkdir(parents=True, exist_ok=True)
                    with self._lock:
                        _replace_file(self.audit_path, _json_bytes(record))
                else:
                    self._append_complete_line(record)
            except (OSError, AuditRecordError, TypeError, ValueError) as error:
                message = "輪次稽核紀錄保存失敗：{}".format(error)
                with self._condition:
                    if self._error is None:
                        self._error = message
                if self._on_error is not None:
                    self._on_error(record, message)
            finally:
                with self._condition:
                    self._pending -= 1
                    self._condition.notify_all()
                self._queue.task_done()

    def _ensure_worker_locked(self) -> None:
        """Start a writer while holding the condition that protects pending work."""
        if self._writer is not None and self._writer.is_alive():
            return
        worker = threading.Thread(target=self._write_worker,
                                  name="round-audit-{}".format(self.round_id), daemon=True)
        self._writer = worker
        worker.start()

    def _append_complete_line(self, record: dict) -> None:
        content = _json_bytes(record)
        with self._lock:
            descriptor = os.open(str(self.audit_path), os.O_WRONLY | os.O_APPEND)
            original_size = os.fstat(descriptor).st_size
            try:
                written = os.write(descriptor, content)
                if written != len(content):
                    raise OSError("輪次稽核紀錄未完整寫入")
                os.fsync(descriptor)
            except Exception:
                try:
                    os.ftruncate(descriptor, original_size)
                    os.fsync(descriptor)
                except OSError:
                    pass
                raise
            finally:
                os.close(descriptor)

    def mark_legacy_session_path(self, session_path: Path) -> None:
        self.flush()
        with self._lock:
            payload = read_round_audit(self.audit_path)
            header = dict(payload["round"])
            header["legacy_session_path"] = str(session_path)
            _replace_file(self.audit_path, b"".join(
                _json_bytes(item) for item in [header] + payload["events"]))
            self._header = header


def _first(detail: dict, *names):
    for name in names:
        value = detail.get(name)
        if value not in (None, ""):
            return value
    return None


def read_round_audit(path: Path) -> dict:
    """Read and reconstruct a round from disk without live monitor or UI state."""
    path = Path(path)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise AuditRecordError("無法讀取輪次紀錄：{}".format(error))
    if not lines:
        raise AuditRecordError("輪次紀錄是空檔")
    try:
        records = [json.loads(line) for line in lines]
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise AuditRecordError("輪次紀錄截斷或格式損壞：{}".format(error))
    header, events = records[0], records[1:]
    if not isinstance(header, dict):
        raise AuditRecordError("輪次紀錄標頭格式不正確")
    if header.get("record_type") != "round" or header.get("schema_version") != AUDIT_SCHEMA_VERSION:
        raise AuditRecordError("不支援的輪次紀錄格式")
    if not isinstance(header.get("round_id"), str) or not header["round_id"]:
        raise AuditRecordError("輪次紀錄缺少有效 round_id")
    if not isinstance(header.get("config"), dict) or not isinstance(header.get("time_contract"), dict):
        raise AuditRecordError("輪次紀錄缺少有效配置或時間契約")
    previous_sequence = 0
    for event in events:
        if not isinstance(event, dict):
            raise AuditRecordError("輪次事件記錄格式不正確")
        sequence = event.get("sequence")
        if (event.get("record_type") != "event" or event.get("schema_version") != AUDIT_SCHEMA_VERSION
                or event.get("round_id") != header["round_id"]
                or not isinstance(sequence, int) or isinstance(sequence, bool)
                or sequence <= previous_sequence
                or not isinstance(event.get("kind"), str) or not event["kind"]
                or not isinstance(event.get("message"), str)
                or not isinstance(event.get("detail"), dict)
                or not isinstance(event.get("observed_at"), str)
                or not isinstance(event.get("elapsed_seconds"), (int, float))
                or isinstance(event.get("elapsed_seconds"), bool)
                or not math.isfinite(event["elapsed_seconds"])):
            raise AuditRecordError("輪次事件格式、識別或順序不正確")
        display_position = event.get("display_position")
        if (display_position is not None and
                (not isinstance(display_position, int) or isinstance(display_position, bool)
                 or display_position < 1)):
            raise AuditRecordError("輪次事件顯示位置格式不正確")
        if event["kind"] == "result" and (
                display_position is None or not isinstance(event.get("status"), str)
                or not event["status"] or "sn" not in event):
            raise AuditRecordError("結果事件缺少有效顯示位置、狀態或 SN 欄位")
        previous_sequence = sequence

    results = {}
    collection_stopped = False
    released = False
    manual_stop = False
    state = "READY"
    completion_reason = ""
    alarms = {}
    conflicts = {}
    for event in events:
        kind = event["kind"]
        slot = event.get("display_position")
        if kind == "round_started":
            state = "RUNNING"
        elif kind == "conflict_detected":
            state = "AWAITING_REVIEW"
        elif kind == "conflict_resolved":
            state = "AWAITING_REVIEW" if any(
                conflict.get("resolution") is None for conflict in conflicts.values()) else state
        elif kind == "result" and slot is not None:
            results[slot] = {"display_position": slot, "source_position": event.get("source_position"),
                             "sn": event.get("sn"), "status": event.get("status"),
                             "source": event.get("source"), "source_time": event.get("source_time"),
                             "detail": event.get("detail", {})}
        elif kind == "conflict_detected":
            conflict_id = event.get("detail", {}).get("conflict_id")
            if conflict_id:
                conflicts[conflict_id] = event.get("detail", {})
        elif kind == "conflict_resolved":
            detail = event.get("detail", {})
            slot = event.get("display_position")
            if slot is not None and slot in results:
                results[slot].update({"sn": detail.get("result_after_sn"),
                                      "status": detail.get("result_after_status"),
                                      "source": detail.get("result_after_source"),
                                      "source_position": detail.get("chosen_source_position")})
            if detail.get("conflict_id") in conflicts:
                conflicts[detail["conflict_id"]]["resolution"] = detail
        elif kind == "round_alarm_created":
            alarm_id = event.get("detail", {}).get("alarm_id")
            if alarm_id:
                alarms[alarm_id] = {"created": event}
        elif kind == "round_alarm_acknowledged":
            alarm_id = event.get("detail", {}).get("alarm_id")
            if alarm_id:
                alarms.setdefault(alarm_id, {})["acknowledged"] = event
        elif kind == "collection_stopped":
            collection_stopped = True
            completion_reason = event.get("detail", {}).get("reason", "")
        elif kind == "stopped":
            collection_stopped = True
            manual_stop = True
            state = "STOPPED"
            completion_reason = "manual_stop"
        elif kind == "start_failed":
            state = "STOPPED"
            completion_reason = "start_failed"
        elif kind == "finished":
            released = True
            state = "COMPLETED"
            completion_reason = event.get("detail", {}).get("completion_reason", "")
    return {"round": header, "events": events, "results": results,
            "collection_stopped": collection_stopped, "manual_stop": manual_stop,
            "result_available": released, "state": state, "completion_reason": completion_reason,
            "alarms": alarms, "conflicts": conflicts,
            "audit_complete": all(event["sequence"] == index
                                  for index, event in enumerate(events, 1))
            and not any(event["kind"] in {"audit_write_failed", "session_write_failed"}
                        for event in events)}
