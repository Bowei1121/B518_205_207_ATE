"""Durable, versioned records for App events that do not belong to a round."""

from __future__ import annotations

import json
import errno
import os
import stat
import tempfile
import threading
import time
import uuid
import ctypes
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Deque, Iterable, Optional, Tuple

from language_catalog import BilingualMessage, make_bilingual_message
from cleanup_reasons import capture_cleanup_reason


APP_EVENT_RECORD_VERSION = 1
APP_EVENT_STORE_VERSION = 1
APP_EVENT_STORE_RETENTION_VERSION = 2
_IDLE_WORKER_TIMEOUT_SECONDS = 0.2
_LIBC = ctypes.CDLL(None, use_errno=True)
_HAS_RELATIVE_FILE_OPERATIONS = all(
    hasattr(_LIBC, name) for name in ("openat", "renameat", "unlinkat"))
if _HAS_RELATIVE_FILE_OPERATIONS:
    # openat has three fixed arguments; mode is variadic. Apple arm64
    # passes variadic arguments differently from fixed arguments.
    _LIBC.openat.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int)
    _LIBC.openat.restype = ctypes.c_int
    _LIBC.renameat.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p)
    _LIBC.renameat.restype = ctypes.c_int
    _LIBC.unlinkat.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int)
    _LIBC.unlinkat.restype = ctypes.c_int


def _at_call(result: int, operation: str, path: str) -> int:
    if result < 0:
        error_number = ctypes.get_errno()
        raise OSError(error_number, "{} failed: {}".format(operation, os.strerror(error_number)),
                      path)
    return result


def _openat(directory_fd: int, name: str, flags: int, mode: int = 0) -> int:
    if not _HAS_RELATIVE_FILE_OPERATIONS:
        raise OSError("Secure directory-relative cleanup is unavailable on this platform")
    return _at_call(_LIBC.openat(directory_fd, os.fsencode(name), flags, ctypes.c_uint(mode)), "openat", name)


def _renameat(source_fd: int, source: str, target_fd: int, target: str) -> None:
    if not _HAS_RELATIVE_FILE_OPERATIONS:
        raise OSError("Secure directory-relative cleanup is unavailable on this platform")
    _at_call(_LIBC.renameat(source_fd, os.fsencode(source), target_fd,
                            os.fsencode(target)), "renameat", target)


def _unlinkat(directory_fd: int, name: str) -> None:
    if not _HAS_RELATIVE_FILE_OPERATIONS:
        raise OSError("Secure directory-relative cleanup is unavailable on this platform")
    _at_call(_LIBC.unlinkat(directory_fd, os.fsencode(name), 0), "unlinkat", name)


def _absolute_managed_path(path: Path) -> Path:
    """Normalize only standard macOS /var and /tmp aliases, never user links."""
    absolute = Path(os.path.abspath(os.fspath(path)))
    if len(absolute.parts) > 2:
        alias, remainder = absolute.parts[1], absolute.parts[2:]
        expected = {"var": "private/var", "tmp": "private/tmp"}.get(alias)
        alias_path = "/" + alias
        if (expected and os.path.islink(alias_path) and
                os.readlink(alias_path) == expected):
            return Path("/").joinpath(*expected.split("/"), *remainder)
    return absolute


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
            "schema_version": APP_EVENT_RECORD_VERSION,
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
    reason_message: Optional[dict] = None
    deleted_sequences: Tuple[int, ...] = ()


class _AppEventCleanupError(ValueError):
    """Validation error with a stable reason chosen by its producer."""

    def __init__(self, message_id: str, detail: str, outcome: str = "failed"):
        super().__init__(detail)
        self.message_id = message_id
        self.outcome = outcome


AppEventCleanupError = _AppEventCleanupError


def _cleanup_reason(suffix: str, parameters=None, diagnostic: str = "") -> dict:
    return capture_cleanup_reason(
        "app.settings.retention.reason." + suffix, parameters or {}, diagnostic)


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


def _open_managed_directory(root: Path, parts: Tuple[str, ...]) -> int:
    """Open a managed directory component-by-component without following links."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    absolute_root = _absolute_managed_path(root)
    descriptor = os.open(os.path.abspath(os.sep), flags)
    try:
        for part in absolute_root.parts[1:] + tuple(parts):
            next_descriptor = _openat(descriptor, part, flags)
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _read_at(directory_fd: int, name: str) -> Tuple[bytes, os.stat_result]:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = _openat(directory_fd, name, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise _AppEventCleanupError("app_events_not_regular", "App 事件目標不是一般檔案")
        chunks = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks), metadata
    finally:
        os.close(descriptor)


def _same_file_entry(left: os.stat_result, right: os.stat_result) -> bool:
    return (left.st_dev, left.st_ino, left.st_size, left.st_mtime_ns) == (
        right.st_dev, right.st_ino, right.st_size, right.st_mtime_ns)


def _same_directory(left: os.stat_result, right: os.stat_result) -> bool:
    return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


def _atomic_replace_at(directory_fd: int, name: str, content: bytes,
                       expected: os.stat_result,
                       commit_gate: Callable[[Callable[[], None]], None]) -> None:
    """Atomically replace one journal entry through its already-pinned directory."""
    temporary_name = ".{}-{}".format(name, uuid.uuid4().hex)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = _openat(directory_fd, temporary_name, flags, 0o600)
    replaced = False
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())

        def replace_entry() -> None:
            nonlocal replaced
            current_fd = _openat(directory_fd, name,
                                 os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            try:
                current = os.fstat(current_fd)
            finally:
                os.close(current_fd)
            if not stat.S_ISREG(current.st_mode) or not _same_file_entry(current, expected):
                raise _AppEventCleanupError("app_events_changed", "App 事件紀錄在清理期間已變更")
            _renameat(directory_fd, temporary_name, directory_fd, name)
            replaced = True

        commit_gate(replace_entry)
        if not replaced:
            raise RuntimeError("App 事件清理提交閘門未完成原子替換")
        os.fsync(directory_fd)
    except Exception:
        if not replaced:
            try:
                _unlinkat(directory_fd, temporary_name)
            except OSError:
                pass
        raise


def read_app_event_store(path: Path) -> dict:
    """Read and validate a fresh App event store without mutating old data."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise _AppEventCleanupError(
            "app_events_read_failed", "App 事件紀錄無法讀取：{}".format(error))
    return _validate_app_event_store_payload(payload)


def _validate_app_event_store_payload(payload: object) -> dict:
    if (not isinstance(payload, dict) or payload.get("record_type") != "app_event_store" or
            type(payload.get("schema_version")) is not int or
            payload["schema_version"] not in {APP_EVENT_STORE_VERSION,
                                                APP_EVENT_STORE_RETENTION_VERSION} or
            not isinstance(payload.get("events"), list)):
        raise _AppEventCleanupError("app_events_unknown_format", "App 事件紀錄格式或版本不受支援")
    store_version = payload["schema_version"]
    retired = payload.get("retired_sequences")
    next_sequence = payload.get("next_sequence")
    if store_version == APP_EVENT_STORE_VERSION:
        if "retired_sequences" in payload or "next_sequence" in payload:
            raise _AppEventCleanupError("app_events_sequence_invalid", "App 事件紀錄序號保留資訊需要新版格式")
        retired = []
        next_sequence = len(payload["events"]) + 1
    elif "retired_sequences" not in payload or "next_sequence" not in payload:
        raise _AppEventCleanupError("app_events_sequence_missing", "App 事件紀錄序號保留資訊不完整")
    if (not isinstance(retired, list) or type(next_sequence) is not int or
            next_sequence < 1):
        raise _AppEventCleanupError("app_events_sequence_invalid", "App 事件紀錄序號保留資訊無效")
    retired_ranges = []
    previous_end = 0
    for item in retired:
        if (not isinstance(item, list) or len(item) != 2 or
                type(item[0]) is not int or type(item[1]) is not int or
                item[0] <= previous_end or item[1] < item[0] or
                item[1] >= next_sequence):
            raise _AppEventCleanupError("app_events_sequence_invalid", "App 事件紀錄序號保留範圍無效")
        retired_ranges.append((item[0], item[1]))
        previous_end = item[1]
    seen = set()
    previous_sequence = 0
    live_sequences = set()
    for event in payload["events"]:
        if (not isinstance(event, dict) or event.get("record_type") != "app_event" or
                event.get("schema_version") != APP_EVENT_RECORD_VERSION or
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
            raise _AppEventCleanupError("app_events_invalid", "App 事件紀錄內容不完整或序號不連續")
        try:
            occurred_at = datetime.fromisoformat(event["occurred_at"])
        except ValueError:
            raise _AppEventCleanupError("app_events_time_invalid", "App 事件時間格式無效")
        if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
            raise _AppEventCleanupError("app_events_time_missing", "App 事件時間缺少時區")
        seen.add(event["event_id"])
        live_sequences.add(event["sequence"])
        previous_sequence = event["sequence"]
    if store_version == APP_EVENT_STORE_VERSION and [
            item["sequence"] for item in payload["events"]] != list(range(1, next_sequence)):
        raise _AppEventCleanupError("app_events_invalid", "App 事件紀錄內容不完整或序號不連續")
    retired_count = sum(end - start + 1 for start, end in retired_ranges)
    if len(live_sequences) + retired_count != next_sequence - 1:
        raise _AppEventCleanupError("app_events_sequence_gap", "App 事件紀錄存在未解釋的序號缺口")
    for start, end in retired_ranges:
        if any(start <= sequence <= end for sequence in live_sequences):
            raise _AppEventCleanupError("app_events_sequence_invalid", "App 事件紀錄已刪除序號仍有事件")
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
        self._error_message_id = ""
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
            self._error_message_id = getattr(error, "message_id", "app_events_read_failed")
            self._error_history.append(self._error)

    @staticmethod
    def _payload(events, next_sequence=None, retired_sequences=()) -> dict:
        retained_ranges = [list(item) for item in retired_sequences]
        payload = {"record_type": "app_event_store",
                   "schema_version": (APP_EVENT_STORE_RETENTION_VERSION if retained_ranges
                                      else APP_EVENT_STORE_VERSION),
                   "events": list(events)}
        if retained_ranges:
            payload["retired_sequences"] = retained_ranges
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

    def cleanup_commit_is_durable(self, deleted_sequences: Iterable[int],
                                  managed_root: Path) -> bool:
        """Confirm a prepared intent and sync its pinned journal directory on recovery."""
        sequences = tuple(deleted_sequences)
        if not sequences:
            return False
        root = _absolute_managed_path(managed_root)
        requested_path = _absolute_managed_path(self.path)
        try:
            relative = requested_path.relative_to(root)
        except ValueError:
            raise _AppEventCleanupError(
                "app_events_outside", "App 事件檔不在管理根目錄")
        if not relative.parts or any(part in {".", ".."} for part in relative.parts):
            raise _AppEventCleanupError(
                "app_events_outside", "App 事件檔不在管理根目錄")

        root_fd = parent_fd = current_root_fd = current_parent_fd = None
        try:
            root_fd = _open_managed_directory(root, ())
            parent_fd = _open_managed_directory(root, relative.parts[:-1])
            data, _metadata = _read_at(parent_fd, relative.parts[-1])
            payload = _validate_app_event_store_payload(json.loads(data.decode("utf-8")))

            def contains_retirement(candidate):
                present = {item["sequence"] for item in candidate["events"]}
                retired = tuple(tuple(item) for item in candidate.get("retired_sequences", []))
                return all(sequence not in present and any(start <= sequence <= end
                                                           for start, end in retired)
                           for sequence in sequences)

            if not contains_retirement(payload):
                return False

            # The journal rename may have succeeded even though its original
            # directory fsync failed. A fresh reader seeing the retired serials
            # is not enough; sync the pinned containing directory before crediting
            # the old cleanup run with a durable deletion.
            os.fsync(parent_fd)
            current_root_fd = _open_managed_directory(root, ())
            current_parent_fd = _open_managed_directory(root, relative.parts[:-1])
            if (not _same_directory(os.fstat(root_fd), os.fstat(current_root_fd)) or
                    not _same_directory(os.fstat(parent_fd), os.fstat(current_parent_fd))):
                raise _AppEventCleanupError(
                    "app_events_path_changed",
                    "App 事件管理路徑在清理恢復期間已變更")
            confirmed_data, _metadata = _read_at(current_parent_fd, relative.parts[-1])
            confirmed = _validate_app_event_store_payload(
                json.loads(confirmed_data.decode("utf-8")))
            return contains_retirement(confirmed)
        finally:
            for descriptor in (current_parent_fd, current_root_fd, parent_fd, root_fd):
                if descriptor is not None:
                    os.close(descriptor)

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
                        before_replace: Callable[[datetime, Callable[[], None]], None] = None,
                        before_commit: Callable[[dict], None] = None
                        ) -> AppEventCleanupResult:
        """Delete only fully persisted, timezone-valid App events at or before cutoff.

        This runs inside the existing background retention worker. It rewrites only
        the App-owned journal, records retired sequence ranges, and refuses links,
        corrupt input, pending writes, or journals outside the managed root.
        """
        if (cutoff.tzinfo is None or cutoff.utcoffset() is None):
            reason = "期限時間缺少時區"
            return AppEventCleanupResult("skipped", skipped_count=1,
                                          reason=reason,
                                          reason_message=_cleanup_reason("app_events_timezone"))
        pin_stage = "root"
        try:
            # Keep the caller's lexical root. Resolving first would follow an
            # already-present symlink in any ancestor and bless its target as
            # managed data. Pin every component from `/` with O_NOFOLLOW.
            root = _absolute_managed_path(managed_root)
            requested_path = _absolute_managed_path(self.path)
            try:
                relative = requested_path.relative_to(root)
            except ValueError:
                raise _AppEventCleanupError("app_events_outside", "App 事件檔不在管理根目錄")
            if not relative.parts or any(part in {".", ".."} for part in relative.parts):
                raise _AppEventCleanupError("app_events_outside", "App 事件檔不在管理根目錄")
            root_probe = _open_managed_directory(root, ())
            try:
                pin_stage = "path"
                parent_probe = _open_managed_directory(root, relative.parts[:-1])
                try:
                    try:
                        entry_fd = _openat(parent_probe, relative.parts[-1],
                                           os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
                    except FileNotFoundError:
                        entry_fd = None
                    except OSError as error:
                        if error.errno in {errno.ELOOP, errno.EMLINK}:
                            reason = "App 事件清理拒絕符號連結"
                            return AppEventCleanupResult(
                                "skipped", skipped_count=1, reason=reason,
                                reason_message=capture_cleanup_reason(
                                    "app.settings.retention.reason.app_events_symlink", {}))
                        raise
                    if entry_fd is not None:
                        os.close(entry_fd)
                finally:
                    os.close(parent_probe)
            finally:
                os.close(root_probe)
        except (OSError, ValueError) as error:
            reason_id = getattr(error, "message_id", None)
            if reason_id is None:
                reason_id = ("app_events_symlink" if isinstance(error, OSError) and
                             error.errno in {errno.ELOOP, errno.EMLINK} else
                             "app_events_root_invalid" if pin_stage == "root" else
                             "app_events_path_invalid")
            return AppEventCleanupResult(
                "skipped", skipped_count=1, reason=str(error),
                reason_message=_cleanup_reason(reason_id, diagnostic=str(error)))

        with self._io_lock:
            with self._condition:
                if self._pending or self._worker_active:
                    reason = self._error or "App 事件保存待補存或狀態尚未確認完整"
                    reason_id = (self._error_message_id or "app_events_pending")
                    parameters = {"diagnostic": reason} if reason_id in {
                        "app_events_read_failed", "app_events_persistence_failed"} else {}
                    return AppEventCleanupResult(
                        "skipped", skipped_count=1,
                        reason=reason,
                        reason_message=_cleanup_reason(reason_id, parameters, self._error))
                if self._error:
                    reason_id = self._error_message_id or "app_events_pending"
                    parameters = {"diagnostic": self._error} if reason_id in {
                        "app_events_read_failed", "app_events_persistence_failed"} else {}
                    return AppEventCleanupResult(
                        "skipped", skipped_count=1, reason=self._error,
                        reason_message=_cleanup_reason(reason_id, parameters, self._error))
            root_fd = parent_fd = None
            stage = "read"
            try:
                root_fd = _open_managed_directory(root, ())
                parent_fd = _open_managed_directory(root, relative.parts[:-1])
                try:
                    try:
                        original_bytes, original_stat = _read_at(parent_fd, relative.parts[-1])
                    except OSError as error:
                        if error.errno in {errno.ELOOP, errno.EMLINK}:
                            raise _AppEventCleanupError(
                                "app_events_path_changed",
                                "App 事件目標在安全檢查後變成符號連結") from error
                        raise
                except FileNotFoundError:
                    return AppEventCleanupResult(
                        "complete", reason="沒有 App 事件需要清理",
                        reason_message=_cleanup_reason("app_events_no_events"))
                try:
                    payload = _validate_app_event_store_payload(
                        json.loads(original_bytes.decode("utf-8")))
                except (UnicodeError, json.JSONDecodeError) as error:
                    raise _AppEventCleanupError(
                        "app_events_read_failed", "App 事件紀錄無法讀取：{}".format(error))
                except _AppEventCleanupError:
                    raise
                except ValueError:
                    raise
                stage = "validate"
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
                    # A previous replace may have committed the shortened journal
                    # before its directory fsync reported failure. Reconfirm the
                    # pinned directory entry before treating this retry as complete.
                    stage = "durability"
                    os.fsync(parent_fd)
                    next_sequence = payload.get("next_sequence", max(
                        (item["sequence"] for item in payload["events"]), default=0) + 1)
                    with self._condition:
                        if (self._events != payload["events"] or
                                self._retired_sequences != payload.get("retired_sequences", []) or
                                self._next_sequence != next_sequence):
                            self._revision += 1
                        self._events = list(payload["events"])
                        self._retired_sequences = payload.get("retired_sequences", [])
                        self._next_sequence = next_sequence
                    no_events = not retained
                    reason_message = _cleanup_reason(
                        "app_events_no_events" if no_events else "app_events_not_expired")
                    return AppEventCleanupResult(
                        "complete", skipped_count=len(retained),
                        reason="沒有 App 事件需要清理" if no_events else "尚未到保存期限",
                        reason_message=reason_message)
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
                content = _json_bytes(updated)
                deleted_sequences = tuple(expired_sequences)
                reason_message = capture_cleanup_reason(
                    "app.settings.retention.reason.app_events_deleted",
                    {"deleted_count": len(expired_sequences),
                     "skipped_count": len(retained)})
                commit_intent = {
                    "outcome": "complete",
                    "deleted_count": len(expired_sequences),
                    "skipped_count": len(retained),
                    "failed_count": 0,
                    "reason": "已刪除到期 App 事件",
                    "reason_message": reason_message,
                    "deleted_sequences": list(deleted_sequences),
                }
                stage = "commit"
                def commit_gate(commit):
                    def verify_then_commit():
                        current_root_fd = None
                        current_parent_fd = None
                        try:
                            try:
                                current_root_fd = _open_managed_directory(root, ())
                                current_parent_fd = _open_managed_directory(
                                    root, relative.parts[:-1])
                            except OSError as error:
                                raise _AppEventCleanupError(
                                    "app_events_path_changed",
                                    "App 事件管理路徑在清理期間已變更：{}".format(error))
                            if (not _same_directory(os.fstat(current_root_fd), os.fstat(root_fd)) or
                                    not _same_directory(os.fstat(current_parent_fd),
                                                        os.fstat(parent_fd))):
                                raise _AppEventCleanupError(
                                    "app_events_path_changed",
                                    "App 事件管理路徑在清理期間已變更")
                            commit()
                        finally:
                            if current_parent_fd is not None:
                                os.close(current_parent_fd)
                            if current_root_fd is not None:
                                os.close(current_root_fd)

                    if before_replace is not None:
                        if before_commit is not None:
                            before_commit(commit_intent)
                        before_replace(max(expired_times), verify_then_commit)
                    else:
                        if before_commit is not None:
                            before_commit(commit_intent)
                        verify_then_commit()

                _atomic_replace_at(parent_fd, relative.parts[-1], content,
                                   original_stat, commit_gate)
                with self._condition:
                    self._events = retained
                    self._retired_sequences = merged
                    self._revision += 1
                    self._error = ""
                    self._error_message_id = ""
                return AppEventCleanupResult("complete", deleted_count=len(expired_sequences),
                                             skipped_count=len(retained),
                                             reason="已刪除到期 App 事件",
                                             reason_message=reason_message,
                                             deleted_sequences=deleted_sequences)
            except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
                if isinstance(error, _AppEventCleanupError) and error.outcome == "skipped":
                    return AppEventCleanupResult(
                        "skipped", skipped_count=len(payload["events"]), reason=str(error),
                        reason_message=_cleanup_reason(error.message_id, diagnostic=str(error)))
                reason_id = getattr(error, "message_id", None)
                if reason_id is None:
                    reason_id = ("app_events_persistence_failed" if stage in
                                 {"durability", "commit"} else "app_events_read_failed")
                diagnostic = str(error)
                parameters = {"diagnostic": diagnostic} if reason_id in {
                    "app_events_read_failed", "app_events_persistence_failed"} else {}
                return AppEventCleanupResult(
                    "failed", failed_count=1, reason=diagnostic,
                    reason_message=_cleanup_reason(reason_id, parameters, diagnostic))
            finally:
                if parent_fd is not None:
                    os.close(parent_fd)
                if root_fd is not None:
                    os.close(root_fd)

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
            self._error_message_id = ""
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
                            self._error_message_id = ""
                            self._condition.notify_all()
                except Exception as error:
                    with self._condition:
                        self._error = str(error)
                        self._error_message_id = "app_events_persistence_failed"
                        self._error_history.append(self._error)
                        self._worker_active = False
                        self._condition.notify_all()
                    return
        finally:
            with self._condition:
                if self._worker_active and not self._pending:
                    self._worker_active = False
                self._condition.notify_all()
