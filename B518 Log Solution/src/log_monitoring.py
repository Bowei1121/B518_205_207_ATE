"""Pure local-file monitoring core for B518 DFU, FCT and BT stations.

This module deliberately has no device-control dependencies.  The Tk UI only
subscribes to events emitted here; the same core is used by unit tests.
"""

from __future__ import annotations

import csv
import json
import os
import queue
import tempfile
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from b482_source_adapter import (
    B482ObservationKind,
    B482SourceAdapter,
    CASEINFO_FILE,
    CASEINFO_TIMESTAMP,
    parse_bt_csv,
    parse_bt_filename,
)
from atlas_source_adapter import (
    AtlasObservationKind,
    AtlasSourceAdapter,
    parse_archive_timestamp,
    records_status,
    trusted_sn_from_records,
)
from language_catalog import BilingualMessage, capture_round_event_message
from monitoring_files import (
    file_signature,
    is_trusted_sn,
    normalise_sn,
    snapshot_files,
)

TERMINAL = {"PASS", "FAIL", "NOTEST", "STOPPED", "TIMEOUT"}
DEFAULT_TIMEOUTS = {
    "DFU": {"start": 30, "test": 480, "round": 7200},
    "FCT": {"start": 30, "test": 480, "round": 7200},
    "BT": {"start": 30, "test": 240, "round": 7200},
}


@dataclass
class MonitorEvent:
    kind: str
    message: str
    slot: Optional[int] = None
    sn: str = ""
    status: str = ""
    source: str = ""
    detail: Dict[str, str] = field(default_factory=dict)
    localized_message: Optional[BilingualMessage] = None
    sequence: Optional[int] = None
    observed_at: Optional[str] = None


@dataclass
class SlotResult:
    slot: int
    sn: str = ""
    status: str = "WAITING"
    source: str = ""
    updated_at: str = ""


class SessionStore:
    def __init__(self, session_id: str, settings: Dict[str, str], root: Optional[Path] = None,
                 on_error: Optional[Callable[[str, OSError], None]] = None,
                 async_writes: bool = False):
        root = root or (Path.home() / "Library" / "Application Support" / "B518LogSolution" / "sessions")
        self.path = root / session_id
        self.settings = settings
        self.started_at = datetime.now().isoformat(timespec="seconds")
        self.sources: Set[str] = set()
        self.finished_at = ""
        self._lock = threading.RLock()
        self._write_queue = queue.Queue()
        self._write_condition = threading.Condition()
        self._write_pending = 0
        self._write_thread = None
        self._write_errors = []  # type: List[str]
        self._write_history = []  # type: List[str]
        self._recovery_writes = deque()
        self._retry_counted_writes = 0
        self._on_write_error = on_error
        self._async_writes = async_writes
        try:
            self.initialize()
        except OSError as error:
            self._remember_failed_write("initialize", (), "Session 初始化保存失敗", error)

    def enqueue_event(self, message: str, detail: Optional[Dict[str, str]] = None,
                      localized_message: Optional[BilingualMessage] = None,
                      timestamp: Optional[str] = None, sequence: Optional[int] = None,
                      round_id: Optional[str] = None) -> None:
        arguments = (message, dict(detail or {}), timestamp or datetime.now().isoformat(
            timespec="seconds"))
        if localized_message is not None:
            arguments += (localized_message,)
        if sequence is not None or round_id is not None:
            if localized_message is None:
                arguments += (None,)
            arguments += (sequence, round_id)
        self._enqueue_write("event", arguments, "Session 事件保存失敗")

    def enqueue_source(self, path: Path) -> None:
        self._enqueue_write("source", (Path(path),), "Session 來源保存失敗")

    def enqueue_results(self, results: Iterable[SlotResult]) -> None:
        snapshot = tuple(replace(result) for result in results)
        self._enqueue_write("update_results", (snapshot,), "Session 結果保存失敗")

    def enqueue_finish(self) -> None:
        self._enqueue_write("finish", (datetime.now().isoformat(timespec="seconds"),),
                            "Session 完成時間保存失敗")

    def _enqueue_write(self, operation: str, arguments: tuple, label: str) -> None:
        if not self._async_writes:
            with self._write_condition:
                worker_active = self._write_thread is not None and self._write_thread.is_alive()
                if self._write_errors or self._recovery_writes:
                    self._recovery_writes.append((operation, arguments, label))
                    if worker_active and not self._write_errors:
                        self._write_pending += 1
                        self._retry_counted_writes += 1
                    return
                if worker_active or self._write_pending:
                    self._write_pending += 1
                    self._write_queue.put((operation, arguments, label))
                    self._ensure_write_worker_locked()
                    return
            try:
                getattr(self, operation)(*arguments)
            except OSError as error:
                self._remember_failed_write(operation, arguments, label, error, notify=False)
                raise
            return
        with self._write_condition:
            self._write_pending += 1
            self._write_queue.put((operation, arguments, label))
            self._ensure_write_worker_locked()

    def _ensure_write_worker_locked(self) -> None:
        if self._write_thread is None or not self._write_thread.is_alive():
            self._write_thread = threading.Thread(target=self._write_worker,
                                                  name="session-store-{}".format(self.path.name),
                                                  daemon=True)
            self._write_thread.start()

    def _write_worker(self) -> None:
        while True:
            with self._write_condition:
                if self._write_errors:
                    self._write_thread = None
                    return
                if self._recovery_writes:
                    operation, arguments, label = self._recovery_writes.popleft()
                    queued = False
                else:
                    operation = None
                    queued = True
            if operation is None:
                try:
                    operation, arguments, label = self._write_queue.get(timeout=0.2)
                except queue.Empty:
                    with self._write_condition:
                        if self._write_pending == 0:
                            self._write_thread = None
                            return
                    continue
            try:
                getattr(self, operation)(*arguments)
            except OSError as error:
                if queued:
                    self._write_queue.task_done()
                message = "{}：{}".format(label, error)
                with self._write_condition:
                    self._write_errors.append(message)
                    self._write_history.append(message)
                    failed_write = (operation, arguments, label)
                    if not queued:
                        self._recovery_writes.appendleft(failed_write)
                    else:
                        self._recovery_writes.append(failed_write)
                    self._write_pending -= 1
                    if not queued:
                        # The current and remaining retained writes are excluded from
                        # pending while a failed recovery waits for the next retry.
                        self._write_pending -= max(0, self._retry_counted_writes - 1)
                        self._retry_counted_writes = 0
                    self._write_thread = None
                    self._write_condition.notify_all()
                if self._on_write_error is not None:
                    self._on_write_error(label, error)
                return
            else:
                if queued:
                    self._write_queue.task_done()
                with self._write_condition:
                    self._write_pending -= 1
                    if not queued and self._retry_counted_writes:
                        self._retry_counted_writes -= 1
                    self._write_condition.notify_all()

    def initialize(self) -> None:
        self.path.mkdir(parents=True, exist_ok=True)
        self._write_metadata()

    def _remember_failed_write(self, operation, arguments, label, error, notify=True,
                               prepend=False):
        message = "{}：{}".format(label, error)
        with self._write_condition:
            self._write_errors.append(message)
            self._write_history.append(message)
            failed_write = (operation, arguments, label)
            if prepend:
                self._recovery_writes.appendleft(failed_write)
            else:
                self._recovery_writes.append(failed_write)
            self._write_condition.notify_all()
        if notify and self._on_write_error is not None:
            self._on_write_error(label, error)

    @property
    def pending(self) -> bool:
        with self._write_condition:
            return bool(self._write_pending or self._recovery_writes)

    @property
    def write_errors(self):
        with self._write_condition:
            return tuple(self._write_errors)

    @property
    def write_history(self):
        with self._write_condition:
            return tuple(self._write_history)

    def retry(self) -> bool:
        """Retry retained Session operations before newer queued work."""
        with self._write_condition:
            if not self._write_errors:
                return True
            self._write_errors = []
            self._retry_counted_writes = len(self._recovery_writes)
            self._write_pending += self._retry_counted_writes
            self._ensure_write_worker_locked()
            self._write_condition.notify_all()
        return True

    def flush(self, timeout: Optional[float] = 10.0) -> bool:
        deadline = None if timeout is None else time.monotonic() + timeout
        with self._write_condition:
            while self._write_pending:
                if self._write_errors:
                    return False
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    return False
                self._write_condition.wait(remaining)
            return not self._write_errors

    @staticmethod
    def _atomic_write(path: Path, content: bytes) -> None:
        descriptor, temporary = tempfile.mkstemp(prefix=".{}-".format(path.name), dir=str(path.parent))
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, str(path))
        except Exception:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise

    def _write_metadata(self) -> None:
        payload = {"schema_version": 1, "settings": self.settings, "started_at": self.started_at,
                   "finished_at": self.finished_at, "sources": sorted(self.sources)}
        encoded = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        with self._lock:
            self._atomic_write(self.path / "session.json", encoded)

    def event(self, message: str, detail: Optional[Dict[str, str]] = None,
              timestamp: Optional[str] = None,
              localized_message: Optional[BilingualMessage] = None,
              sequence: Optional[int] = None, round_id: Optional[str] = None) -> None:
        payload = {
            "timestamp": timestamp or datetime.now().isoformat(timespec="seconds"),
            "message": message,
            "detail": detail or {},
        }
        if sequence is not None:
            payload["sequence"] = sequence
        if round_id is not None:
            payload["round_id"] = round_id
        if localized_message is not None:
            payload["localized_message"] = localized_message.as_record()
        record = json.dumps(payload, ensure_ascii=False) + "\n"
        with self._lock:
            with (self.path / "events.log").open("a", encoding="utf-8") as handle:
                handle.write(record)
                handle.flush()

    def update_results(self, results: Iterable[SlotResult]) -> None:
        temporary = self.path / ".results.csv.tmp"
        with self._lock, temporary.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["slot", "sn", "status", "source", "updated_at"])
            writer.writeheader()
            writer.writerows(asdict(result) for result in sorted(results, key=lambda result: result.slot))
            handle.flush()
            os.fsync(handle.fileno())
            os.replace(str(temporary), str(self.path / "results.csv"))

    def source(self, path: Path) -> None:
        with self._lock:
            self.sources.add(str(path))
            self._write_metadata()

    def update_settings(self, settings: Dict[str, object]) -> None:
        with self._lock:
            self.settings.update(settings)
            try:
                self._write_metadata()
            except OSError as error:
                self._remember_failed_write("_write_metadata", (), "Session 設定保存失敗",
                                            error, notify=False)
                raise

    def finish(self, finished_at: Optional[str] = None) -> None:
        with self._lock:
            self.finished_at = finished_at or datetime.now().isoformat(timespec="seconds")
            self._write_metadata()


class BaseMonitor:
    """Polling monitor with explicit ``poll_once`` for deterministic tests."""
    def __init__(self, station: str, settings: Dict[str, str], slots: Sequence[int],
                 callback: Optional[Callable[[MonitorEvent], None]] = None,
                 session_root: Optional[Path] = None, now: Callable[[], datetime] = datetime.now,
                 monotonic: Callable[[], float] = time.monotonic,
                 start_timeout_seconds: Optional[int] = None,
                 test_timeout_seconds: Optional[int] = None,
                 round_timeout_seconds: Optional[int] = None,
                 async_session_writes: bool = False):
        self.station, self.settings, self.slots = station, settings, tuple(sorted(slots))
        defaults = DEFAULT_TIMEOUTS.get(station.upper(), DEFAULT_TIMEOUTS["FCT"])
        self.start_timeout_seconds = int(start_timeout_seconds or defaults["start"])
        self.test_timeout_seconds = int(test_timeout_seconds or defaults["test"])
        self.round_timeout_seconds = int(round_timeout_seconds or defaults["round"])
        if min(self.start_timeout_seconds, self.test_timeout_seconds, self.round_timeout_seconds) <= 0:
            raise ValueError("逾時秒數必須為正整數")
        self.settings.update({"start_timeout_seconds": str(self.start_timeout_seconds),
                              "test_timeout_seconds": str(self.test_timeout_seconds),
                              "round_timeout_seconds": str(self.round_timeout_seconds)})
        self.callback, self.now, self.monotonic = callback, now, monotonic
        self._event_display_position_mapper = lambda slot: slot
        self.started = now()
        self._deadline_locked_slots: Set[int] = set()
        self.results = {slot: SlotResult(slot=slot) for slot in self.slots}
        session_id = "{}-{}".format(station.lower(), self.started.strftime("%Y%m%d-%H%M%S-%f"))
        self.session = SessionStore(session_id, settings, session_root,
                                    on_error=self._report_session_write_failure,
                                    async_writes=async_session_writes)
        self.finished = False
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._round_candidate_mode = False

    def round_results(self) -> Tuple[SlotResult, ...]:
        """Return a stable view of results for the shared round lifecycle."""
        return tuple(replace(result) for result in self.results.values())

    def set_event_display_position_mapper(self, mapper: Callable[[Optional[int]], Optional[int]]) -> None:
        """Keep captured event labels aligned with the configured display positions."""
        self._event_display_position_mapper = mapper

    def timeout_seconds(self, kind: str) -> int:
        """Expose configured limits through the common round contract."""
        return {
            "start": self.start_timeout_seconds,
            "test": self.test_timeout_seconds,
            "round": self.round_timeout_seconds,
        }[kind]

    def update_round_settings(self, settings: Dict[str, object]) -> None:
        try:
            self.session.update_settings(settings)
        except OSError as error:
            self._report_session_write_failure("Session 設定保存失敗", error)
        self._round_candidate_mode = bool(settings.get("round_candidate_mode", False))

    def publish_round_event(self, event: MonitorEvent) -> None:
        self.emit(event)

    def emit(self, event: MonitorEvent) -> None:
        round_id = getattr(self, "settings", {}).get("round_id")
        if round_id:
            event.detail.setdefault("round_id", str(round_id))
        if event.localized_message is None:
            mapper = getattr(self, "_event_display_position_mapper", lambda slot: slot)
            display_slot = mapper(event.slot)
            event.localized_message = capture_round_event_message(
                event.kind, self.station, event.slot, event.status, event.detail,
                event.message, display_slot,
            )
        # The common-round callback assigns the canonical sequence and time before
        # this Session mirror is queued, so Session and audit can be correlated on disk.
        if event.source:
            try:
                enqueue = getattr(self.session, "enqueue_source", None)
                if callable(enqueue):
                    enqueue(Path(event.source))
                else:
                    self.session.source(Path(event.source))
            except OSError as error:
                self._report_session_write_failure("Session 來源保存失敗", error)
        if self.callback:
            self.callback(event)
        try:
            enqueue = getattr(self.session, "enqueue_event", None)
            if callable(enqueue):
                if event.localized_message is not None:
                    enqueue(event.message, event.detail, event.localized_message,
                            event.observed_at, event.sequence,
                            event.detail.get("round_id"))
                else:
                    enqueue(event.message, event.detail, timestamp=event.observed_at,
                            sequence=event.sequence, round_id=event.detail.get("round_id"))
            elif event.localized_message is not None:
                self.session.event(event.message, event.detail, timestamp=event.observed_at,
                                   localized_message=event.localized_message,
                                   sequence=event.sequence,
                                   round_id=event.detail.get("round_id"))
            else:
                self.session.event(event.message, event.detail, timestamp=event.observed_at,
                                   sequence=event.sequence,
                                   round_id=event.detail.get("round_id"))
        except OSError as error:
            self._report_session_write_failure("Session 事件保存失敗", error)

    def _report_session_write_failure(self, operation: str, error: OSError) -> None:
        if self.callback:
            self.callback(MonitorEvent(
                "session_write_failed", "{}；本輪仍依既有狀態流程繼續".format(operation),
                detail={"error_type": type(error).__name__, "error": str(error),
                        "round_id": self.settings.get("round_id", "unknown")},
            ))

    def set_result(self, slot: int, status: str, sn: Optional[str] = None, source: str = "",
                   detail: Optional[Dict[str, str]] = None, lock_terminal: bool = False) -> None:
        if self._round_candidate_mode and status != "STOPPED":
            candidate = MonitorEvent("result_candidate", "slot{} {} candidate".format(slot, status),
                                     slot, sn or "", status, source, detail or {})
            decision = self.callback(candidate) if self.callback else "accept"
            if decision != "accept":
                return
            self.apply_round_result(slot, status, sn or "", source, detail, lock_terminal)
            return
        self.apply_round_result(slot, status, sn or "", source, detail, lock_terminal)

    def apply_round_result(self, slot: int, status: str, sn: str = "", source: str = "",
                           detail: Optional[Dict[str, str]] = None,
                           lock_terminal: bool = False) -> None:
        if slot in self._deadline_locked_slots:
            return
        result = self.results[slot]
        if result.status in TERMINAL and status not in TERMINAL:
            return
        if sn:
            result.sn = sn
        result.status, result.source = status, source or result.source
        result.updated_at = self.now().isoformat(timespec="seconds")
        try:
            enqueue = getattr(self.session, "enqueue_results", None)
            if callable(enqueue):
                enqueue(self.results.values())
            else:
                self.session.update_results(self.results.values())
        except OSError as error:
            self._report_session_write_failure("Session 結果保存失敗", error)
        self.emit(MonitorEvent("result", "slot{} {}".format(slot, status), slot, result.sn, status,
                               source, detail or {}))
        if lock_terminal:
            self._deadline_locked_slots.add(slot)

    def start(self) -> None:
        """Mark adapter readiness; MonitoringRound owns the polling schedule."""
        return

    def stop_collection(self) -> None:
        """Stop source reads while leaving round result-release policy to the round."""
        self._stop.set()

    def finish(self) -> None:
        self.stop_collection()
        if not self.finished:
            self.finished = True
            try:
                enqueue = getattr(self.session, "enqueue_finish", None)
                if callable(enqueue):
                    enqueue()
                else:
                    self.session.finish()
            except OSError as error:
                self._report_session_write_failure("Session 完成時間保存失敗", error)

    def stop(self) -> None:
        self._stop.set()
        if not self.finished:
            for slot, result in self.results.items():
                if result.status not in TERMINAL:
                    self.set_result(slot, "STOPPED")
            self.finish()
            self.emit(MonitorEvent("stopped", "{} 監控已由人員停止".format(self.station)))

    def poll_once(self) -> None:
        raise NotImplementedError


class AtlasActiveArchiveMonitor(BaseMonitor):
    """DFU/FCT monitor: active/group0-slotN followed by final archive data."""
    def __init__(self, station: str, active_root: Path, final_root: Path, slots: Sequence[int], **kwargs):
        super().__init__(station, {"active_root": str(active_root), "final_root": str(final_root)}, slots, **kwargs)
        self.source = AtlasSourceAdapter(active_root, final_root, slots, self.started, self.now)

    def poll_once(self) -> None:
        if self.finished or self._stop.is_set():
            return
        for observation in self.source.poll():
            if observation.kind == AtlasObservationKind.SOURCE_PREPARED:
                self.emit(MonitorEvent("source_prepared", "Atlas 來源啟動前快照完成，監控準備就緒。"))
            elif observation.kind == AtlasObservationKind.SN_LOCKED:
                self.set_result(observation.slot, observation.status, observation.sn, observation.source,
                                observation.detail)
                self.emit(MonitorEvent(
                    "sn_locked", "slot{} 已鎖定可信 SN".format(observation.slot),
                    observation.slot, observation.sn, observation.status, observation.source,
                    observation.detail or {},
                ))
            elif observation.kind == AtlasObservationKind.ACTIVITY:
                self.set_result(observation.slot, observation.status, observation.sn, observation.source,
                                observation.detail)
            elif observation.kind == AtlasObservationKind.SN_READ_FAILED:
                self.set_result(observation.slot, observation.status, observation.sn)
            elif observation.kind in {AtlasObservationKind.COMPLETING, AtlasObservationKind.NOTEST}:
                self.set_result(observation.slot, observation.status, observation.sn, observation.source,
                                observation.detail)
            elif observation.kind == AtlasObservationKind.FINAL:
                self.set_result(observation.slot, observation.status, observation.sn, observation.source,
                                observation.detail)
                self.emit(MonitorEvent(
                    "final", "slot{} 最終 {}".format(observation.slot, observation.status),
                    observation.slot, observation.sn, observation.status, observation.source,
                    observation.detail or {},
                ))
            elif observation.kind == AtlasObservationKind.UNRESOLVED_CONFLICT:
                self.emit(MonitorEvent(
                    "unresolved_source_conflict",
                    "Atlas slot{} 身分資料改變，但來源證據不足以確認同輪；保留證據且不提供採用選項。"
                    .format(observation.slot),
                    observation.slot, observation.sn, observation.status, observation.source,
                    observation.detail or {},
                ))



class BtLogMonitor(BaseMonitor):
    """BT TestData monitor with timestamp batch locking and optional CaseInfo."""
    def __init__(self, testdata_root: Path, slots: Sequence[int], caseinfo_root: Optional[Path] = None, **kwargs):
        monotonic = kwargs.pop("monotonic", time.monotonic)
        super().__init__("BT", {"testdata_root": str(testdata_root), "caseinfo_root": str(caseinfo_root or "")}, slots,
                         monotonic=monotonic, **kwargs)
        self.testdata_root, self.caseinfo_root = testdata_root, caseinfo_root
        self.source_adapter = B482SourceAdapter(
            testdata_root, caseinfo_root, self.started, self.now, self.monotonic,
        )
        self.batch_stamp = ""

    def poll_once(self) -> None:
        if self.finished or self._stop.is_set():
            return
        for observation in self.source_adapter.poll():
            self._process_observation(observation)

    def _process_observation(self, observation) -> None:
        if observation.kind == B482ObservationKind.CASEINFO_ACTIVITY:
            if observation.slot not in self.results:
                return
            self.set_result(observation.slot, observation.status, observation.sn,
                            observation.source, observation.evidence())
            return
        if not self.batch_stamp:
            self.batch_stamp = observation.batch_id
            self.emit(MonitorEvent(
                "batch", "BT 觀察批次 {}".format(self.batch_stamp), source=observation.source,
                detail=observation.evidence(),
            ))
        elif observation.batch_id != self.batch_stamp:
            self.emit(MonitorEvent(
                "batch_observed", "BT 觀察到不同批次證據，保留來源供共同輪次判定",
                observation.slot, observation.sn, observation.status, observation.source,
                observation.evidence(),
            ))
        slot = observation.slot
        if slot in self.results:
            self.set_result(slot, observation.status, observation.sn, observation.source,
                            observation.evidence())
