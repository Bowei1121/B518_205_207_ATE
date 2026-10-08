"""Shared lifecycle, deadline and snapshot boundary for one monitoring round."""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from queue import Empty, Queue
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, Optional, Protocol, Tuple

from log_monitoring import MonitorEvent, SlotResult, TERMINAL
from audit_records import AuditEvent, AuditRecordError, RoundAuditStore
from language_catalog import capture_round_event_message
from round_archival import (ArchiveLocation, ArchiveSnapshot, normalize_archive_time,
                            write_round_archive)
from round_retention import RetentionStatus, RetentionSummary, RoundRetentionStore


class RoundMonitor(Protocol):
    """Public adapter contract consumed by the shared round lifecycle."""

    def round_results(self) -> Tuple[SlotResult, ...]: ...
    def timeout_seconds(self, kind: str) -> int: ...
    def update_round_settings(self, settings: Dict[str, object]) -> None: ...
    def publish_round_event(self, event: MonitorEvent) -> None: ...
    def set_result(self, slot: int, status: str, detail=None, lock_terminal: bool = False) -> None: ...
    def apply_round_result(self, slot: int, status: str, sn: str = "", source: str = "", detail=None,
                           lock_terminal: bool = False) -> None: ...
    def start(self) -> None: ...
    def poll_once(self) -> None: ...
    def stop_collection(self) -> None: ...
    def finish(self) -> None: ...
    def stop(self) -> None: ...


@dataclass(frozen=True)
class RoundEvent:
    round_id: str
    sequence: int
    event: MonitorEvent


class RoundState(str, Enum):
    READY = "READY"
    RUNNING = "RUNNING"
    AWAITING_REVIEW = "AWAITING_REVIEW"
    COMPLETED = "COMPLETED"
    STOPPED = "STOPPED"


def _has_source_test_time(value: object) -> bool:
    """Accept only parseable platform test timestamps, never observation/file times."""
    if not isinstance(value, str) or not value.strip():
        return False
    normalized = value.strip()
    if normalized.lower() in {"unknown", "none", "null"}:
        return False
    if len(normalized) <= 10 or normalized[10] not in {"T", " "}:
        return False
    try:
        datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


@dataclass(frozen=True)
class RoundResult:
    slot: int
    sn: str
    status: str
    source: str
    updated_at: str


@dataclass(frozen=True)
class ConflictSide:
    sn: str
    status: str
    source: str
    source_id: str
    source_time: str
    evidence: Tuple[Tuple[str, str], ...]


@dataclass(frozen=True)
class RoundConflict:
    conflict_id: str
    round_id: str
    slot: int
    original: ConflictSide
    candidate: ConflictSide
    same_round_evidence: Tuple[Tuple[str, str], ...]
    detected_at: str


@dataclass(frozen=True)
class RoundAlarm:
    alarm_id: str
    round_id: str
    created_at: str
    acknowledged_at: str = ""


@dataclass(frozen=True)
class RoundSnapshot:
    round_id: str
    station: str
    state: RoundState
    results: Tuple[RoundResult, ...]
    result_available: bool
    event_sequence: int
    events: Tuple[RoundEvent, ...]
    collection_stopped: bool = False
    completion_reason: str = ""
    pending_conflicts: Tuple[RoundConflict, ...] = ()
    round_alarm: Optional[RoundAlarm] = None
    round_alarm_ready: bool = True
    source_preparation_pending: bool = False
    audit_complete: bool = True
    audit_errors: Tuple[str, ...] = ()
    audit_pending: bool = False
    save_state: str = "waiting"
    save_errors: Tuple[str, ...] = ()
    save_history: Tuple[str, ...] = ()
    retry_in_progress: bool = False


@dataclass(frozen=True)
class CloseSnapshot:
    """Public progress for the current app-run save-before-close attempt."""
    status: str = "idle"
    generation: int = 0
    round_ids: Tuple[str, ...] = ()
    message: str = ""


def _round_close_complete(round_: "MonitoringRound", snapshot: RoundSnapshot) -> bool:
    session_complete = snapshot.save_state == "complete" or (
        snapshot.completion_reason == "start_failed" and round_.session_path is None)
    return snapshot.audit_complete and session_complete and _round_close_operators_complete(snapshot)


def _round_close_operators_complete(snapshot: RoundSnapshot) -> bool:
    return not snapshot.pending_conflicts and not (
        snapshot.round_alarm is not None and not snapshot.round_alarm.acknowledged_at)


class MonitoringRound:
    """Apply common deadlines and lifecycle rules to platform observations."""

    def __init__(self, station: str, monitor_factory: Callable[[Callable[[MonitorEvent], None]], object],
                 on_event: Callable[[RoundEvent], None], monotonic: Callable[[], float],
                 round_timeout_seconds: Optional[int] = None, capacity: Optional[int] = None,
                 audit_root: Optional[Path] = None, audit_context: Optional[dict] = None,
                 wall_clock: Callable[[], datetime] = datetime.now):
        self.round_id = uuid.uuid4().hex
        self.station = station
        self._monotonic = monotonic
        # Capture the accepted start before a monitor snapshots or prepares sources.
        self._started_monotonic = monotonic()
        self._accepted_start_at = wall_clock().isoformat(timespec="seconds")
        self._wall_clock = wall_clock
        self._lock = threading.RLock()
        self._event_lock = threading.RLock()
        self._poll_lock = threading.Lock()
        self._events = []  # type: list[RoundEvent]
        self._on_event = on_event
        self._state = RoundState.READY
        self._started = False
        self._stop_requested = False
        self._collection_stopped = False
        self._completion_reason = ""
        self._test_started: Dict[int, float] = {}
        self._activity_slots = set()
        self._deadline_slots = set()
        self._result_evidence: Dict[int, Dict[str, str]] = {}
        self._pending_conflicts: Dict[str, RoundConflict] = {}
        self._next_event_sequence = 1
        self._round_alarm: Optional[RoundAlarm] = None
        self._round_alarm_ready = True
        self._configured_round_timeout = round_timeout_seconds
        self._capacity = capacity
        self._preparation_results: Tuple[RoundResult, ...] = ()
        self._preparation_deadline_expired = False
        self._collection_stopped_at = ""
        self._deferred_persist_events = []  # type: list[MonitorEvent]
        self._deferred_event_ids = set()
        self._poll_started_at: Optional[float] = None
        self._run_thread: Optional[threading.Thread] = None
        self._monitor_factory = monitor_factory
        self._monitor: Optional[RoundMonitor] = None
        self._monitor_persistence_ready = False
        self._audit_errors = []  # type: list[str]
        self._save_errors = []  # type: list[str]
        self._save_history = []  # type: list[str]
        self._retry_in_progress = False
        self._audit_attach_target: Optional[Path] = None
        self._audit_store = None
        self._audit_root = Path(audit_root) if audit_root is not None else None
        self._audit_context = audit_context
        self._audit_condition = threading.Condition()
        self._audit_next_sequence = 1
        self._audit_recovery_events = []
        self._audit_recovery_replaying = False
        self._prepared_event = threading.Event()
        self._close_finalized = False
        if self._audit_root is not None:
            try:
                self._audit_store = self._create_audit_store()
            except (OSError, AuditRecordError, TypeError, ValueError) as error:
                message = "稽核紀錄初始化失敗：{}".format(error)
                self._audit_errors.append(message)
                self._save_errors.append(message)
                self._save_history.append(message)

    def _create_audit_store(self) -> RoundAuditStore:
        assert self._audit_root is not None
        return RoundAuditStore(
            self._audit_root, self.round_id, self.station, self._accepted_start_at,
            self._started_monotonic, self._audit_context, on_error=self._audit_write_failed,
        )

    def start(self, run_async: bool = True) -> RoundSnapshot:
        with self._lock:
            if self._started or self._state != RoundState.READY:
                return self.snapshot()
            self._started = True
            self._state = RoundState.RUNNING
            self._publish_round_event(MonitorEvent(
                "round_started", "{} 本輪已接受開始".format(self.station),
                detail={"round_id": self.round_id, "accepted_start_at": self._accepted_start_at,
                        "accepted_start_monotonic": str(self._started_monotonic)},
            ))
            if run_async:
                self._run_thread = threading.Thread(target=self._prepare_and_run, daemon=True)
                self._run_thread.start()
            else:
                try:
                    self._prepare_monitor()
                finally:
                    self._prepared_event.set()
            return self.snapshot()

    def poll_once(self) -> RoundSnapshot:
        """Read one deterministic source batch, then apply due deadlines."""
        with self._poll_lock:
            with self._lock:
                if self._state not in {RoundState.RUNNING, RoundState.AWAITING_REVIEW} or self._collection_stopped:
                    return self.snapshot()
                if self._monitor is None or not self._monitor_persistence_ready:
                    self._apply_preparation_deadline(self._monotonic())
                    return self.snapshot()
            poll_time = self._monotonic()
            self._apply_deadlines(poll_time)
            self._finish_if_terminal()
            with self._lock:
                if self._state not in {RoundState.RUNNING, RoundState.AWAITING_REVIEW} or self._collection_stopped:
                    self._finish_if_terminal()
                    return self.snapshot()
            self._poll_started_at = poll_time
            try:
                self._monitor.poll_once()
            finally:
                self._poll_started_at = None
            self._finish_if_terminal()
            return self.snapshot()

    def wait_until_prepared(self, timeout: Optional[float] = None) -> bool:
        """Wait until source setup has either completed or failed."""
        return self._prepared_event.wait(timeout)

    def stop(self) -> RoundSnapshot:
        with self._poll_lock:
            with self._lock:
                if self._state not in {RoundState.RUNNING, RoundState.AWAITING_REVIEW}:
                    return self.snapshot()
                self._stop_requested = True
                monitor = self._monitor
                if monitor is None:
                    self._state = RoundState.STOPPED
                    self._collection_stopped = True
                    self._completion_reason = "manual_stop"
                    self._collection_stopped_at = self._wall_clock().isoformat(timespec="seconds")
            if monitor is not None:
                # Adapter callbacks can re-enter the round and coordinator. Do
                # not call them while holding the round state lock.
                self._stop_collection("manual_stop")
                monitor.stop()
                with self._lock:
                    if self._state == RoundState.RUNNING:
                        self._state = RoundState.STOPPED
                        self._collection_stopped = True
                        self._completion_reason = "manual_stop"
            else:
                self._append_event(MonitorEvent(
                    "collection_stopped", "{} 已停止讀取本輪來源（manual_stop）".format(self.station),
                    detail={"round_id": self.round_id, "reason": "manual_stop",
                            "collection_stopped_at": self._collection_stopped_at},
                ))
                self._append_event(MonitorEvent(
                    "stopped", "{} 監控已由人員停止".format(self.station),
                    detail={"round_id": self.round_id, "reason": "manual_stop"},
                ))
            return self.snapshot()

    def resolve_review(self, conflict_id: str, choice: str) -> RoundSnapshot:
        """Resolve exactly one captured same-round conflict."""
        with self._poll_lock:
            with self._lock:
                if self._close_finalized:
                    return self.snapshot()
                conflict = self._pending_conflicts.get(conflict_id)
                monitor = self._monitor
                if (monitor is None or conflict is None or self._state not in {
                        RoundState.RUNNING, RoundState.AWAITING_REVIEW, RoundState.STOPPED}):
                    return self.snapshot()
                if choice not in {"keep_original", "accept_candidate"}:
                    raise ValueError("未知衝突選擇：{}".format(choice))
                del self._pending_conflicts[conflict_id]
            selected = conflict.candidate if choice == "accept_candidate" else conflict.original
            monitor.apply_round_result(
                conflict.slot, selected.status, selected.sn, selected.source,
                dict(selected.evidence),
            )
            effective_result = next((item for item in monitor.round_results()
                                     if item.slot == conflict.slot), None)
            event = MonitorEvent(
                "conflict_resolved", "slot{} 衝突已{}".format(
                    conflict.slot, "採用新結果" if choice == "accept_candidate" else "保留原結果",
                ), slot=conflict.slot,
                sn=conflict.candidate.sn, status=conflict.candidate.status,
                source=conflict.candidate.source,
                detail={
                    "round_id": conflict.round_id,
                    "conflict_id": conflict.conflict_id,
                    "choice": choice,
                    "chosen_sn": (conflict.candidate.sn if choice == "accept_candidate"
                                  else conflict.original.sn),
                    "chosen_status": (conflict.candidate.status if choice == "accept_candidate"
                                      else conflict.original.status),
                    "chosen_source": (conflict.candidate.source if choice == "accept_candidate"
                                      else conflict.original.source),
                    "result_after_sn": (effective_result.sn if effective_result else "unknown"),
                    "result_after_status": (effective_result.status if effective_result else "unknown"),
                    "result_after_source": (effective_result.source if effective_result else "unknown"),
                    "chosen_source_position": dict(selected.evidence).get("source_position", "unknown"),
                    "original_sn": conflict.original.sn or "unknown",
                    "original_status": conflict.original.status,
                    "candidate_sn": conflict.candidate.sn or "unknown",
                    "candidate_status": conflict.candidate.status,
                    "candidate_source_id": conflict.candidate.source_id or "unknown",
                    "candidate_source_time": conflict.candidate.source_time or "unknown",
                    "selected_at": self._wall_clock().isoformat(timespec="seconds"),
                },
            )
            self._publish_round_event(event)
            with self._lock:
                if self._state == RoundState.STOPPED:
                    pass
                elif self._pending_conflicts:
                    self._state = RoundState.AWAITING_REVIEW
                elif not self._collection_stopped:
                    self._state = RoundState.RUNNING
            if self._collection_stopped:
                self._finish_if_terminal()
            return self.snapshot()

    def acknowledge_round_alarm(self, round_id: str, alarm_id: str) -> RoundSnapshot:
        """Acknowledge only the identified alarm for this round."""
        with self._poll_lock:
            with self._lock:
                if self._close_finalized:
                    return self.snapshot()
                alarm = self._round_alarm
                if round_id != self.round_id or alarm is None or alarm.alarm_id != alarm_id:
                    reason = "stale_round_or_alarm"
                elif not self._round_alarm_ready:
                    reason = "source_preparation_pending"
                elif alarm.acknowledged_at:
                    reason = "already_acknowledged"
                else:
                    reason = ""
                    alarm = RoundAlarm(alarm.alarm_id, alarm.round_id, alarm.created_at,
                                       self._wall_clock().isoformat(timespec="seconds"))
                    self._round_alarm = alarm
            if reason:
                self._append_event(MonitorEvent(
                    "round_alarm_acknowledgement_ignored", "整輪警報確認已忽略：{}".format(reason),
                    detail={"round_id": round_id or "unknown", "alarm_id": alarm_id or "unknown",
                            "reason": reason},
                ))
                return self.snapshot()
            self._append_event(MonitorEvent(
                "round_alarm_acknowledged", "整輪逾時警報已確認；仍須完成其他待確認事項",
                status="ACKNOWLEDGED",
                detail={"round_id": alarm.round_id, "alarm_id": alarm.alarm_id,
                        "created_at": alarm.created_at, "acknowledged_at": alarm.acknowledged_at},
            ))
            self._finish_if_terminal()
            return self.snapshot()

    def snapshot(self) -> RoundSnapshot:
        with self._audit_condition:
            audit_recovery_pending = bool(self._audit_recovery_events or
                                          self._audit_recovery_replaying)
        with self._lock:
            results = tuple(
                RoundResult(result.slot, result.sn, result.status, result.source, result.updated_at)
                for result in sorted(self._monitor.round_results(), key=lambda result: result.slot)
            ) if self._monitor is not None and self._monitor_persistence_ready else self._preparation_results
            monitor = self._monitor
            session = getattr(monitor, "session", None)
            session_pending = bool(getattr(session, "pending", False))
            session_errors = tuple(getattr(session, "write_errors", ()))
            current_errors = tuple(dict.fromkeys(self._save_errors + list(session_errors)))
            audit_pending = self._audit_store.pending if self._audit_store is not None else False
            if self._retry_in_progress:
                save_state = "saving"
            elif current_errors or audit_recovery_pending or (
                    self._audit_store is not None and self._audit_store.error):
                save_state = "failed"
            elif not self._monitor_persistence_ready:
                save_state = "waiting"
            elif audit_pending or session_pending:
                save_state = "saving"
            elif self._collection_stopped:
                save_state = "complete"
            else:
                save_state = "saving"
            return RoundSnapshot(
                self.round_id, self.station, self._state, results,
                self._state == RoundState.COMPLETED, self._events[-1].sequence if self._events else 0,
                tuple(self._events), self._collection_stopped, self._completion_reason,
                tuple(self._pending_conflicts.values()), self._round_alarm, self._round_alarm_ready,
                not self._monitor_persistence_ready,
                self._audit_store is not None and not self._save_errors and
                not session_errors and not audit_recovery_pending and
                self._audit_store.error is None and not self._audit_store.pending,
                tuple(self._audit_errors),
                audit_pending,
                save_state,
                current_errors + ((self._audit_store.error,) if self._audit_store and
                                  self._audit_store.error else ()),
                tuple(self._save_history),
                self._retry_in_progress,
            )

    def finalize_close_snapshot(self) -> RoundSnapshot:
        """Atomically freeze operator actions once this round is fully durable."""
        with self._poll_lock:
            snapshot = self.snapshot()
            if _round_close_complete(self, snapshot):
                with self._lock:
                    self._close_finalized = True
            return snapshot

    def retry_saves(self) -> bool:
        """Retry retained current-round Session and audit work without blocking the caller."""
        with self._lock:
            if self._retry_in_progress:
                return False
            monitor = self._monitor
            session = getattr(monitor, "session", None)
            self._retry_in_progress = True
        with self._audit_condition:
            self._audit_recovery_replaying = True
        worker = threading.Thread(target=self._retry_saves_worker, args=(session,), daemon=True)
        worker.start()
        return True

    def _retry_saves_worker(self, session) -> None:
        try:
            retry_session = getattr(session, "retry", None)
            if callable(retry_session):
                retry_session()
            store = self._audit_store
            if store is None and self._audit_root is not None:
                store = self._create_audit_store()
                self._audit_store = store
            if store is not None and store.error is not None:
                store.retry()
            while True:
                with self._audit_condition:
                    recovery = (self._audit_recovery_events[0]
                                if self._audit_recovery_events else None)
                if recovery is None:
                    break
                round_event, observed_at, elapsed_seconds = recovery
                event = round_event.event
                store.append_event(
                    AuditEvent(round_event.sequence, event.kind, event.message, event.slot,
                               event.sn, event.status, event.source, dict(event.detail),
                               event.localized_message),
                    observed_at, elapsed_seconds,
                )
                with self._audit_condition:
                    if self._audit_recovery_events and self._audit_recovery_events[0] == recovery:
                        self._audit_recovery_events.pop(0)
                    if self._audit_next_sequence == round_event.sequence:
                        self._audit_next_sequence += 1
                    self._audit_condition.notify_all()
            session_flush = getattr(session, "flush", None)
            session_ok = session_flush(30.0) if callable(session_flush) else True
            audit_ok = store.flush(30.0) if store is not None else True
            target = self._audit_attach_target
            if audit_ok and store is not None and target is not None:
                store.attach_session(target)
                self._audit_attach_target = None
                audit_ok = store.flush(30.0)
            recovered = session_ok and audit_ok and not self._audit_attach_target
            if recovered:
                with self._audit_condition:
                    self._audit_recovery_replaying = False
                    if self._audit_recovery_events:
                        recovered = False
                if recovered:
                    with self._lock:
                        recovered_errors = tuple(self._save_history)
                        self._save_errors.clear()
                        self._audit_errors.clear()
                    self._append_event(MonitorEvent(
                        "save_recovered", "本輪 Session 與稽核紀錄已完成保存復原",
                        detail={"round_id": self.round_id,
                                "recovered_errors": list(recovered_errors)},
                    ))
                session_ok = session_flush(30.0) if callable(session_flush) else True
                audit_ok = store.flush(30.0) if store is not None else True
                recovered = recovered and session_ok and audit_ok
            with self._lock:
                if recovered:
                    self._save_errors.clear()
                elif not self._save_errors:
                    self._save_errors.append("本輪保存仍未完整；請檢查磁碟及保存位置後重試")
                self._save_history.append(
                    "本輪保存復原成功" if recovered else "本輪保存復原未完成")
        except (OSError, AuditRecordError, TypeError, ValueError) as error:
            with self._lock:
                message = "本輪保存復原失敗：{}".format(error)
                self._save_errors.append(message)
                self._save_history.append(message)
        finally:
            with self._lock:
                self._retry_in_progress = False
            with self._audit_condition:
                self._audit_recovery_replaying = False

    def flush_audit(self, timeout: Optional[float] = 10.0) -> bool:
        """Wait for the ordered audit writer at explicit read/close boundaries."""
        store = self._audit_store
        return store.flush(timeout) if store is not None else not self._audit_errors

    @property
    def session_path(self) -> Optional[Path]:
        """Return the current round's durable Session directory, when prepared."""
        with self._lock:
            monitor = self._monitor
        session = getattr(monitor, "session", None)
        return getattr(session, "path", None)

    @property
    def archive_location(self) -> Optional[ArchiveLocation]:
        """Return the durable audit and Session locations needed for revalidation."""
        audit_path = getattr(self._audit_store, "audit_path", None)
        session_path = self.session_path
        if audit_path is None or session_path is None:
            return None
        return ArchiveLocation(Path(audit_path), Path(session_path), self.station)

    def flush_session(self, timeout: Optional[float] = 10.0) -> bool:
        """Wait for the current adapter Session writer at read/close boundaries."""
        with self._lock:
            monitor = self._monitor
        session = getattr(monitor, "session", None)
        flush = getattr(session, "flush", None)
        return flush(timeout) if callable(flush) else True

    def archive_status(self, archived_at: datetime) -> ArchiveSnapshot:
        """Verify and seal this round while serializing against round operations."""
        with self._poll_lock:
            snapshot = self.snapshot()
            def status(state, message):
                return ArchiveSnapshot(self.round_id, state, message=message,
                                       save_state=snapshot.save_state, station=self.station)

            ended_state = snapshot.state in {RoundState.COMPLETED, RoundState.STOPPED} or (
                snapshot.state == RoundState.AWAITING_REVIEW and snapshot.collection_stopped)
            if not ended_state or not snapshot.collection_stopped:
                return status("protected", "輪次尚未結束")
            if snapshot.pending_conflicts:
                return status("protected", "仍有待確認衝突")
            if snapshot.round_alarm is not None and not snapshot.round_alarm.acknowledged_at:
                return status("protected", "仍有未確認警報")
            if snapshot.save_state == "failed":
                return status("failed", snapshot.save_errors[0] if snapshot.save_errors else "輪次保存失敗")
            if snapshot.save_state != "complete":
                return status("saving", "等待 Session 與 audit 完整保存")
            if not snapshot.audit_complete:
                return status("protected", "audit 尚未完整保存")
            audit_path = getattr(self._audit_store, "audit_path", None)
            session_path = self.session_path
            if audit_path is None or session_path is None:
                return status("protected", "缺少可驗證的 Session 或 audit 位置")
            try:
                archived = write_round_archive(
                    audit_path, session_path, archived_at, expected_round_id=self.round_id)
            except OSError as error:
                return ArchiveSnapshot(self.round_id, "failed", message=str(error),
                                       path=Path(audit_path).parent / "round-archive.json",
                                       save_state=snapshot.save_state, station=self.station)
            except (AuditRecordError, TypeError, ValueError) as error:
                return status("protected", str(error))
            return ArchiveSnapshot(archived.round_id, archived.status, archived.archived_at,
                                   archived.message, archived.path, archived.components,
                                   snapshot.save_state, self.station)

    def _audit_write_failed(self, record: dict, message: str) -> None:
        with self._lock:
            if message not in self._audit_errors:
                self._audit_errors.append(message)
            if message not in self._save_errors:
                self._save_errors.append(message)
            self._save_history.append(message)
            failure = RoundEvent(
                self.round_id, 0,
                MonitorEvent("audit_write_failed", message,
                             detail={"round_id": self.round_id,
                                     "failed_event_sequence": str(record.get("sequence", "unknown")),
                                     "audit_complete": "false"}),
            )
        self._capture_bilingual_message(failure.event)
        self._on_event(failure)

    def events_since(self, sequence: int = 0) -> Tuple[RoundEvent, ...]:
        with self._lock:
            return tuple(event for event in self._events if event.sequence > sequence)

    def _prepare_and_run(self) -> None:
        try:
            self._prepare_monitor()
        except Exception as error:
            with self._lock:
                self._state = RoundState.STOPPED
                self._collection_stopped = True
                self._completion_reason = "start_failed"
                self._collection_stopped_at = self._wall_clock().isoformat(timespec="seconds")
                # Source setup has terminated. The round audit store remains the
                # durable record when no Session was created, so close must not
                # wait forever for monitor persistence that cannot become ready.
                self._monitor_persistence_ready = True
            self._append_event(MonitorEvent(
                "collection_stopped", "{} 啟動失敗後停止收集".format(self.station),
                detail={"round_id": self.round_id, "reason": "start_failed",
                        "collection_stopped_at": self._collection_stopped_at},
            ))
            self._receive_monitor_event(
                MonitorEvent("start_failed", "無法準備監控來源：{}".format(error))
            )
            return
        finally:
            self._prepared_event.set()
        self._run()

    def _prepare_monitor(self) -> None:
        monitor = self._monitor_factory(self._receive_monitor_event)
        context_provider = getattr(monitor, "set_event_context_provider", None)
        if callable(context_provider):
            context_provider(self._prepare_monitor_event)
        with self._lock:
            self._monitor = monitor
            self._monitor_persistence_ready = False
            stop_requested = self._stop_requested
        session_path = getattr(getattr(monitor, "session", None), "path", None)
        if self._audit_store is not None and isinstance(session_path, (str, Path)):
            self._audit_attach_target = Path(session_path)
            try:
                self._audit_store.attach_session(Path(session_path))
                self._audit_attach_target = None
            except (OSError, AuditRecordError) as error:
                message = "無法關聯傳統 Session 紀錄：{}".format(error)
                self._audit_errors.append(message)
                self._save_errors.append(message)
                self._save_history.append(message)
        monitor.update_round_settings({"accepted_start_at": self._accepted_start_at,
                                       "accepted_start_monotonic": self._started_monotonic,
                                       "round_id": self.round_id,
                                       "round_audit_schema_version": 1,
                                       "round_candidate_mode": True})
        self._flush_deferred_events(monitor)
        with self._poll_lock:
            if self._preparation_deadline_expired:
                self._finalize_preparation_deadline_locked(monitor)
                return
            if stop_requested:
                self._stop_collection("manual_stop")
                monitor.stop()
                return
            self._apply_deadlines(self._monotonic())
            self._finish_if_terminal()
            with self._lock:
                if self._collection_stopped or self._state not in {
                        RoundState.RUNNING, RoundState.AWAITING_REVIEW}:
                    return
            monitor.start()
            self._publish_round_event(MonitorEvent("round_ready", "{} 監控來源準備就緒".format(self.station)))

    def _run(self) -> None:
        while True:
            with self._lock:
                if self._state not in {RoundState.RUNNING, RoundState.AWAITING_REVIEW} or self._collection_stopped:
                    return
            self.poll_once()
            with self._lock:
                if self._state not in {RoundState.RUNNING, RoundState.AWAITING_REVIEW} or self._collection_stopped:
                    return
            time.sleep(0.5)

    def _apply_deadlines(self, at: float) -> None:
        if self._monitor is None:
            self._apply_preparation_deadline(at)
            return
        elapsed = max(0.0, at - self._started_monotonic)
        round_limit = self._timeout_limit("round", 7200)
        results = self._monitor.round_results()
        if elapsed >= round_limit and any(result.status not in TERMINAL for result in results):
            self._adjudicate_round_deadline(results, round_limit, elapsed)
            with self._lock:
                if self._round_alarm is None:
                    self._round_alarm = RoundAlarm(
                        uuid.uuid4().hex, self.round_id,
                        self._wall_clock().isoformat(timespec="seconds"),
                    )
                    alarm_created = True
                else:
                    alarm_created = False
                alarm = self._round_alarm
            if alarm_created:
                self._publish_round_event(MonitorEvent(
                    "round_alarm_created", "{} 整輪逾時警報已建立".format(self.station),
                    detail={"round_id": self.round_id, "alarm_id": alarm.alarm_id,
                            "created_at": alarm.created_at, "reason": "round_deadline"},
                ))
            self._emit_timeout("round", None, round_limit, elapsed, alarm, at)
            self._stop_collection("round_deadline")
            with self._lock:
                self._state = RoundState.AWAITING_REVIEW
            return

        start_limit = self._timeout_limit("start", 30)
        if elapsed >= start_limit:
            for result in self._monitor.round_results():
                slot = result.slot
                if result.status != "WAITING" or slot in self._activity_slots:
                    continue
                self._set_deadline_result(slot, "NOTEST", "start_deadline_no_activity", start_limit, elapsed)

        test_limit = self._timeout_limit("test", 480)
        for slot, started_at in sorted(self._test_started.items()):
            result = next((item for item in self._monitor.round_results() if item.slot == slot), None)
            if result is None or result.status in TERMINAL or slot in self._deadline_slots:
                continue
            test_elapsed = max(0.0, at - started_at)
            if test_elapsed >= test_limit:
                self._set_deadline_result(slot, "TIMEOUT", "test_deadline", test_limit, test_elapsed)

    def _timeout_limit(self, kind: str, fallback: int) -> int:
        if kind == "round" and self._monitor is None and self._configured_round_timeout:
            return self._configured_round_timeout
        value = self._monitor.timeout_seconds(kind)
        return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else fallback

    def _apply_preparation_deadline(self, at: float) -> None:
        if (self._monitor is not None and self._monitor_persistence_ready) or self._preparation_deadline_expired:
            return
        if not isinstance(self._configured_round_timeout, int) or isinstance(
                self._configured_round_timeout, bool) or self._configured_round_timeout <= 0:
            return
        elapsed = max(0.0, at - self._started_monotonic)
        if elapsed < self._configured_round_timeout:
            return
        created_at = self._wall_clock().isoformat(timespec="seconds")
        with self._lock:
            if self._state != RoundState.RUNNING or (self._monitor is not None and
                                                       self._monitor_persistence_ready):
                return
            self._preparation_deadline_expired = True
            self._collection_stopped = True
            self._completion_reason = "round_deadline"
            self._collection_stopped_at = created_at
            self._state = RoundState.AWAITING_REVIEW
            self._round_alarm_ready = False
            self._round_alarm = RoundAlarm(uuid.uuid4().hex, self.round_id, created_at)
            capacity = self._capacity or 0
            self._preparation_results = tuple(
                RoundResult(slot, "", "NOTEST", "", created_at) for slot in range(1, capacity + 1)
            )
        self._publish_round_event(MonitorEvent(
            "round_alarm_created", "{} 整輪逾時警報已建立".format(self.station),
            detail={"round_id": self.round_id, "alarm_id": self._round_alarm.alarm_id,
                    "created_at": created_at, "reason": "round_deadline"},
        ))
        self._emit_timeout("round", None, self._configured_round_timeout, elapsed,
                           self._round_alarm, at)

    def _finalize_preparation_deadline(self, monitor: RoundMonitor) -> None:
        # Acknowledgement shares this lock, so no result can be released before
        # all deadline statuses, persistence events, and adapter stop are done.
        with self._poll_lock:
            self._finalize_preparation_deadline_locked(monitor)

    def _finalize_preparation_deadline_locked(self, monitor: RoundMonitor) -> None:
        elapsed = max(0.0, self._monotonic() - self._started_monotonic)
        limit = self._configured_round_timeout or self._timeout_limit("round", 7200)
        self._adjudicate_round_deadline(monitor.round_results(), limit, elapsed)
        with self._lock:
            alarm = self._round_alarm
        monitor.stop_collection()
        detail = {"round_id": self.round_id, "reason": "round_deadline",
                  "collection_stopped_at": self._collection_stopped_at or
                  (alarm.created_at if alarm else self._wall_clock().isoformat(timespec="seconds"))}
        if alarm:
            detail["alarm_id"] = alarm.alarm_id
        self._publish_round_event(MonitorEvent(
            "collection_stopped", "{} 已停止讀取本輪來源（round_deadline）".format(self.station),
            detail=detail,
        ))
        with self._lock:
            self._round_alarm_ready = True

    def _adjudicate_round_deadline(self, results, limit: int, elapsed: float) -> None:
        for result in results:
            if result.status in TERMINAL:
                continue
            status = "TIMEOUT" if result.status in {"TESTING", "COMPLETING"} else "NOTEST"
            self._set_deadline_result(result.slot, status, "round_deadline", limit, elapsed)

    def _set_deadline_result(self, slot: int, status: str, reason: str,
                             deadline_seconds: int, elapsed: float) -> None:
        detail = {
            "reason": reason,
            "deadline_seconds": str(deadline_seconds),
            "elapsed_seconds": str(int(elapsed)),
            "accepted_start_monotonic": str(self._started_monotonic),
            "accepted_start_at": self._accepted_start_at,
        }
        self._deadline_slots.add(slot)
        self._monitor.apply_round_result(slot, status, detail=detail, lock_terminal=True)
        event = MonitorEvent(
            "timeout", "{} slot{} {}（期限 {} 秒，經過 {} 秒）".format(
                self.station, slot, "未觀察到測試" if status == "NOTEST" else "測試逾時",
                deadline_seconds, int(elapsed),
            ), slot=slot, status=status, detail=detail,
        )
        self._publish_round_event(event)

    def _emit_timeout(self, kind: str, slot: Optional[int], deadline_seconds: int, elapsed: float,
                      alarm: Optional[RoundAlarm] = None, observed_at: Optional[float] = None) -> None:
        self._publish_round_event(MonitorEvent(
            "timeout", "{} 整輪監控逾時：{} 秒（經過 {} 秒）".format(
                self.station, deadline_seconds, int(elapsed),
            ), slot=slot, status="TIMEOUT",
            detail={"kind": kind, "reason": "round_deadline", "deadline_seconds": str(deadline_seconds),
                    "elapsed_seconds": str(int(elapsed)), "round_id": self.round_id,
                    "alarm_id": alarm.alarm_id if alarm else "unknown",
                    "alarm_created_at": alarm.created_at if alarm else "unknown",
                    "accepted_start_at": self._accepted_start_at,
                    "accepted_start_monotonic": str(self._started_monotonic),
                    "deadline_observed_at_monotonic": str(observed_at if observed_at is not None
                                                          else self._monotonic())},
        ))

    def _publish_round_event(self, event: MonitorEvent) -> None:
        with self._event_lock:
            with self._lock:
                monitor = self._monitor
                defer = monitor is None or not self._monitor_persistence_ready
                if defer:
                    self._deferred_persist_events.append(event)
            if defer:
                self._receive_monitor_event(event)
                return
            monitor.publish_round_event(event)

    def _flush_deferred_events(self, monitor: RoundMonitor) -> None:
        with self._event_lock:
            with self._lock:
                deferred, self._deferred_persist_events = self._deferred_persist_events, []
                self._deferred_event_ids.update(id(event) for event in deferred)
            for event in deferred:
                monitor.publish_round_event(event)
            with self._lock:
                self._monitor_persistence_ready = True

    def _stop_collection(self, reason: str) -> None:
        with self._lock:
            if self._collection_stopped or self._monitor is None:
                return
            self._collection_stopped = True
            self._completion_reason = reason
            self._collection_stopped_at = self._wall_clock().isoformat(timespec="seconds")
            monitor = self._monitor
        monitor.stop_collection()
        detail = {
            "round_id": self.round_id,
            "reason": reason,
            "collection_stopped_at": self._collection_stopped_at,
        }
        if self._round_alarm is not None:
            detail["alarm_id"] = self._round_alarm.alarm_id
        self._append_event(MonitorEvent(
            "collection_stopped", "{} 已停止讀取本輪來源（{}）".format(self.station, reason), detail=detail,
        ))

    def _finish_if_terminal(self) -> None:
        if self._monitor is None:
            return
        with self._lock:
            if self._state not in {RoundState.RUNNING, RoundState.AWAITING_REVIEW}:
                return
            if self._round_alarm is not None and not self._round_alarm.acknowledged_at:
                return
            if self._round_alarm is not None and not self._round_alarm_ready:
                return
        results = self._monitor.round_results()
        if not results or any(result.status not in TERMINAL for result in results):
            return
        self._stop_collection("results_terminal")
        if self._pending_conflicts:
            with self._lock:
                self._state = RoundState.AWAITING_REVIEW
                if self._completion_reason != "round_deadline":
                    self._completion_reason = "review_pending"
            return
        with self._lock:
            if self._state not in {RoundState.RUNNING, RoundState.AWAITING_REVIEW}:
                return
            self._state = RoundState.COMPLETED
            if self._completion_reason != "round_deadline":
                self._completion_reason = "results_terminal"
        self._monitor.finish()
        self._publish_round_event(MonitorEvent(
            "finished", "{} 本輪完成".format(self.station),
            detail={"completion_reason": self._completion_reason or "results_terminal",
                    "round_id": self.round_id,
                    "results_released_at": self._wall_clock().isoformat(timespec="seconds")},
        ))

    def _receive_monitor_event(self, event: MonitorEvent) -> None:
        if id(event) in self._deferred_event_ids:
            self._deferred_event_ids.remove(id(event))
            return
        if event.kind == "result_candidate":
            return self._consider_result_candidate(event)
        if event.kind == "unresolved_source_conflict":
            self._fail_unconfirmed_candidate(event)
            return
        self._capture_bilingual_message(event)
        if event.kind == "session_write_failed":
            message = event.message
            if message not in self._audit_errors:
                self._audit_errors.append(message)
            if message not in self._save_errors:
                self._save_errors.append(message)
            self._save_history.append(message)
        with self._lock:
            self._prepare_monitor_event_locked(event)
            if event.kind == "result" and event.slot is not None:
                result = next((item for item in self._monitor.round_results()
                               if item.slot == event.slot), None) if self._monitor is not None else None
                if result is not None and result.status in {"TESTING", "COMPLETING"}:
                    self._activity_slots.add(event.slot)
                    if event.status == "TESTING" or event.detail.get("trusted_activity") == "true":
                        started_at = self._poll_started_at
                        if started_at is None:
                            started_at = self._monotonic()
                        self._test_started.setdefault(event.slot, started_at)
                self._result_evidence[event.slot] = dict(event.detail)
            if event.kind == "finished":
                self._state = RoundState.COMPLETED
                self._collection_stopped = True
                self._completion_reason = event.detail.get("completion_reason", "results_terminal")
            elif event.kind == "stopped":
                self._state = RoundState.STOPPED
                self._collection_stopped = True
                if self._completion_reason != "start_failed":
                    self._completion_reason = "manual_stop"
            round_event = RoundEvent(self.round_id, event.sequence, event)
            self._events.append(round_event)
            self._events.sort(key=lambda item: item.sequence)
        self._persist_audit_event(round_event)
        self._on_event(round_event)

    def _prepare_monitor_event(self, event: MonitorEvent) -> None:
        with self._lock:
            self._prepare_monitor_event_locked(event)

    def _prepare_monitor_event_locked(self, event: MonitorEvent) -> None:
        if event.sequence is None:
            event.sequence = self._next_event_sequence
            self._next_event_sequence += 1
        else:
            self._next_event_sequence = max(self._next_event_sequence, event.sequence + 1)
        if event.observed_at is None:
            event.observed_at = self._wall_clock().isoformat(timespec="seconds")

    def _capture_bilingual_message(self, event: MonitorEvent) -> None:
        if event.localized_message is not None:
            return
        event.localized_message = capture_round_event_message(
            event.kind, self.station, event.slot, event.status, event.detail, event.message,
            event.slot,
        )

    def _persist_audit_event(self, round_event: RoundEvent) -> None:
        store = self._audit_store
        if store is None and self._audit_root is None:
            return
        event = round_event.event
        failure_message = None
        observed_at = event.observed_at or self._wall_clock().isoformat(timespec="seconds")
        elapsed_seconds = self._monotonic() - self._started_monotonic
        with self._audit_condition:
            while round_event.sequence != self._audit_next_sequence:
                self._audit_condition.wait()
            if store is None:
                failure_message = "稽核紀錄尚未初始化；本筆已依序保留"
            elif self._audit_recovery_events or self._audit_recovery_replaying:
                failure_message = "前筆輪次稽核紀錄尚待復原；本筆已依序保留"
            else:
                try:
                    store.append_event(
                        AuditEvent(round_event.sequence, event.kind, event.message, event.slot,
                                   event.sn, event.status, event.source, dict(event.detail),
                                   event.localized_message),
                        observed_at, elapsed_seconds,
                    )
                except (OSError, AuditRecordError, TypeError, ValueError) as error:
                    failure_message = "輪次稽核紀錄保存失敗：{}".format(error)
            if failure_message:
                if failure_message not in self._audit_errors:
                    self._audit_errors.append(failure_message)
                if failure_message not in self._save_errors:
                    self._save_errors.append(failure_message)
                self._save_history.append(failure_message)
                self._audit_recovery_events.append((round_event, observed_at, elapsed_seconds))
            self._audit_next_sequence = round_event.sequence + 1
            self._audit_condition.notify_all()
        if failure_message:
            self._publish_audit_failure(round_event, failure_message)

    def _publish_audit_failure(self, failed_event: RoundEvent, message: str) -> None:
        failure = RoundEvent(
            self.round_id, 0,
            MonitorEvent("audit_write_failed", message,
                         detail={"round_id": self.round_id,
                                 "failed_event_sequence": str(failed_event.sequence),
                                 "audit_complete": "false"}),
        )
        self._capture_bilingual_message(failure.event)
        self._on_event(failure)

    def _consider_result_candidate(self, event: MonitorEvent) -> str:
        """Admit linked, timed source facts and queue confirmed same-round contradictions."""
        outbound_event = None
        decision = "ignore"
        with self._lock:
            current = next((item for item in self._monitor.round_results()
                            if item.slot == event.slot), None) if self._monitor else None
            current_detail = self._result_evidence.get(event.slot or -1, {})
            candidate_detail = dict(event.detail)
            evidence_id = candidate_detail.get("round_evidence_id", "")
            current_evidence_id = current_detail.get("round_evidence_id", "")
            # SNRead failures are direct product failures when no trusted identity
            # exists. After a valid identity was locked, ignore a later unreadable
            # observation instead of replacing that identity or its active state.
            if event.status == "FAIL" and not event.source and not candidate_detail.get("source_id"):
                if current is not None and current.sn and current.status == "TESTING":
                    return "ignore"
                return "accept"
            same_round = bool(evidence_id and current_evidence_id and evidence_id == current_evidence_id)
            same_value = bool(current and current.status == event.status and current.sn == event.sn)
            if same_value:
                if current.source != event.source:
                    outbound_event = MonitorEvent(
                        "duplicate_source", "slot{} 一致重複來源已記錄".format(event.slot),
                        event.slot, event.sn, event.status, event.source,
                        {"original_source": current.source, "source_id": candidate_detail.get("source_id", "unknown"),
                         "source_time": candidate_detail.get("source_time", "unknown")},
                    )
            elif current is None or current.status == "WAITING":
                if event.status in TERMINAL:
                    if not evidence_id or not _has_source_test_time(candidate_detail.get("source_time")):
                        self._fail_unconfirmed_candidate(event, current=current)
                        return "ignore"
                return "accept"
            else:
                terminal_conflict = current.status in TERMINAL and event.status in TERMINAL
                identity_conflict = bool(current.sn and event.sn and current.sn != event.sn)
                evidence_conflict = terminal_conflict or identity_conflict
                if not evidence_conflict:
                    return "accept"
                if not same_round or not _has_source_test_time(candidate_detail.get("source_time")):
                    self._fail_unconfirmed_candidate(event, current=current)
                    return "ignore"
                else:
                    original = self._conflict_side(current.sn, current.status, current.source, current_detail)
                    candidate = self._conflict_side(event.sn, event.status, event.source, candidate_detail)
                    duplicate = next((pending for pending in self._pending_conflicts.values()
                                      if pending.slot == event.slot and pending.original.sn == original.sn
                                      and pending.original.status == original.status
                                      and pending.candidate.sn == candidate.sn
                                      and pending.candidate.status == candidate.status
                                      and dict(pending.same_round_evidence).get(
                                          "round_evidence_id", "") == evidence_id), None)
                    if duplicate:
                        outbound_event = MonitorEvent(
                            "duplicate_source", "slot{} 重複衝突來源已記錄，沿用既有待確認項目".format(event.slot),
                            event.slot, event.sn, event.status, event.source,
                            {"conflict_id": duplicate.conflict_id,
                             "source_id": candidate.source_id or "unknown",
                             "source_time": candidate.source_time or "unknown"},
                        )
                    else:
                        conflict = RoundConflict(
                            uuid.uuid4().hex, self.round_id, event.slot or 0, original, candidate,
                            tuple(sorted((key, value) for key, value in candidate_detail.items()
                                         if key.endswith("evidence") or key == "round_evidence_id")),
                            self._wall_clock().isoformat(timespec="seconds"),
                        )
                        self._pending_conflicts[conflict.conflict_id] = conflict
                        self._state = RoundState.AWAITING_REVIEW
                        outbound_event = MonitorEvent(
                            "conflict_detected", "slot{} 發現同輪結果衝突，等待人工確認".format(event.slot),
                            event.slot, event.sn, event.status, event.source,
                            {"round_id": self.round_id, "conflict_id": conflict.conflict_id,
                             "original_sn": original.sn or "unknown", "original_status": original.status,
                             "original_source_id": original.source_id or "unknown",
                             "original_source_time": original.source_time or "unknown",
                             "original_source_position": dict(original.evidence).get("source_position", "unknown"),
                             "candidate_sn": candidate.sn or "unknown", "candidate_status": candidate.status,
                             "candidate_source_id": candidate.source_id or "unknown",
                             "candidate_source_time": candidate.source_time or "unknown",
                             "candidate_source_position": dict(candidate.evidence).get("source_position", "unknown"),
                             "source_position": dict(candidate.evidence).get("source_position", "unknown"),
                             "original": {"sn": original.sn or None, "status": original.status,
                                          "source": original.source or None,
                                          "source_id": original.source_id or None,
                                          "source_time": original.source_time or None,
                                          "evidence": dict(original.evidence)},
                             "candidate": {"sn": candidate.sn or None, "status": candidate.status,
                                           "source": candidate.source or None,
                                           "source_id": candidate.source_id or None,
                                           "source_time": candidate.source_time or None,
                                           "evidence": dict(candidate.evidence)},
                             "same_round_evidence_id": evidence_id or "unknown"},
                        )
                        decision = "defer"
        if outbound_event is not None:
            self._append_event(outbound_event)
        return decision

    def _fail_unconfirmed_candidate(self, event: MonitorEvent, current=None) -> None:
        """Audit an unlinked source candidate and make its slot a terminal FAIL."""
        if current is None and self._monitor is not None and event.slot is not None:
            current = next((item for item in self._monitor.round_results()
                            if item.slot == event.slot), None)
        detail = {key: value for key, value in event.detail.items() if key != "reason"}
        original_detail = self._result_evidence.get(event.slot or -1, {})
        source_time = detail.get("source_time", detail.get("candidate_source_time", "unknown"))
        audit_detail = {
            "round_id": self.round_id,
            "operation": "fail_unconfirmed_candidate",
            "operation_at": self._wall_clock().isoformat(timespec="seconds"),
            "original_sn": current.sn if current and current.sn else "unknown",
            "original_status": current.status if current else "WAITING",
            "original_source": current.source if current and current.source else "unknown",
            "original_source_time": original_detail.get("source_time", "unknown"),
            "candidate_sn": event.sn or detail.get("candidate_sn", "unknown"),
            "candidate_status": event.status or detail.get("candidate_status", "unknown"),
            "candidate_source_id": detail.get("source_id", detail.get("candidate_source_id", "unknown")),
            "candidate_source_time": source_time,
            "source_time": source_time,
            **detail,
        }
        self._append_event(MonitorEvent(
            "unknown_round_candidate_rejected",
            "slot{} 無法確認來源屬於本輪；候選未採用並判定 FAIL".format(event.slot),
            event.slot, event.sn, event.status, event.source, audit_detail,
        ))
        if self._monitor is not None and event.slot is not None:
            self._monitor.apply_round_result(
                event.slot, "FAIL", current.sn if current else "", current.source if current else "",
                {"round_id": self.round_id, "policy_outcome": "unknown_round_candidate_rejected"},
            )

    @staticmethod
    def _conflict_side(sn: str, status: str, source: str, detail: Dict[str, str]) -> ConflictSide:
        return ConflictSide(sn, status, source, detail.get("source_id", ""), detail.get("source_time", ""),
                            tuple(sorted(detail.items())))

    def _append_event(self, event: MonitorEvent) -> None:
        # Route common decisions through the adapter's public event seam so
        # round snapshots, the Tk queue, and the persistent session share one
        # ordered record, including the source path when one is available.
        self._publish_round_event(event)


class RoundCoordinator:
    """Provide the application entry point for one profile-backed round."""

    def __init__(self, on_event: Optional[Callable[[RoundEvent], None]] = None,
                 monotonic: Callable[[], float] = time.monotonic,
                 audit_root: Optional[Path] = None,
                 wall_clock: Callable[[], datetime] = datetime.now,
                 retention_ledger_path: Optional[Path] = None):
        self._lock = threading.RLock()
        self._current: Optional[MonitoringRound] = None
        # Keep only rounds whose current-run durable work is not yet complete.
        # This is deliberately in-memory: prior Sessions are never scanned.
        self._tracked_rounds: Dict[str, MonitoringRound] = {}
        self._events = []  # type: list[RoundEvent]
        self._on_event = on_event
        self._monotonic = monotonic
        self._audit_root = Path(audit_root) if audit_root is not None else None
        self._wall_clock = wall_clock
        self._closing = False
        self._close_status = CloseSnapshot()
        self._close_worker_active = False
        self._archive_states: Dict[str, ArchiveSnapshot] = {}
        self._archive_locations: Dict[str, ArchiveLocation] = {}
        self._archive_locks: Dict[str, threading.Lock] = {}
        self._archive_queue = Queue()
        self._archive_queued = set()
        self._archive_dirty = set()
        self._archive_worker_active = False
        self._retention_store = (RoundRetentionStore(
            self._audit_root,
            retention_ledger_path or self._audit_root.parent / "round-retention-ledger.json",
            self._wall_clock, self._protected_round_ids, self._retention_cleanup_allowed,
            self._effective_retention_days, self._delete_if_currently_expired)
            if self._audit_root is not None else None)
        self._retention_worker_active = False
        self._retention_trigger_pending = False
        self._retention_pending_days = 365
        self._retention_pending_trigger = "scheduled"
        self._retention_days = 365
        self._retention_next_due: Optional[float] = None

    def start(self, station: str,
              monitor_factory: Callable[[Callable[[MonitorEvent], None]], object],
              run_async: bool = True, round_timeout_seconds: Optional[int] = None,
              capacity: Optional[int] = None, audit_context: Optional[dict] = None) -> RoundSnapshot:
        with self._lock:
            if self._closing:
                raise RuntimeError("關閉保存進行中，暫時不能開始新輪")
            if self._current is not None and self._current.snapshot().state in {
                    RoundState.RUNNING, RoundState.AWAITING_REVIEW}:
                return self._current.snapshot()
            self._prune_saved_rounds_locked()
            session = MonitoringRound(station, monitor_factory, self._record_round_event, self._monotonic,
                                      round_timeout_seconds, capacity, self._audit_root, audit_context,
                                      self._wall_clock)
            self._current = session
            self._tracked_rounds[session.round_id] = session
            self._archive_states[session.round_id] = ArchiveSnapshot(
                session.round_id, "waiting", message="輪次尚未完成",
                save_state="waiting", station=station)
            self._prune_saved_rounds_locked()
            self._events = []
            try:
                snapshot = session.start(run_async=run_async)
                return snapshot
            except Exception:
                self._current = None
                raise

    def poll_once(self) -> Optional[RoundSnapshot]:
        with self._lock:
            current = self._current
        return current.poll_once() if current is not None else None

    def flush_audit(self, timeout: Optional[float] = 10.0) -> bool:
        """Wait for the current round's append-only journal to become durable."""
        with self._lock:
            current = self._current
        return current.flush_audit(timeout) if current is not None else True

    @property
    def session_path(self) -> Optional[Path]:
        """Return the current round's durable Session directory, when prepared."""
        with self._lock:
            current = self._current
        return current.session_path if current is not None else None

    def flush_session(self, timeout: Optional[float] = 10.0) -> bool:
        """Wait for the current adapter Session writer without exposing its monitor."""
        with self._lock:
            current = self._current
        return current.flush_session(timeout) if current is not None else True

    def retry_saves(self, round_id: Optional[str] = None) -> bool:
        """Start one nonblocking recovery attempt for a tracked round."""
        with self._lock:
            if self._closing:
                return False
            target_id = round_id or (self._current.round_id if self._current is not None else None)
            target = self._tracked_rounds.get(target_id) if target_id is not None else None
        return target.retry_saves() if target is not None else False

    def retry_archival(self, round_id: str) -> bool:
        """Request a nonblocking disk revalidation after storage repair."""
        with self._lock:
            if (round_id not in self._archive_states or
                    (round_id not in self._tracked_rounds and
                     round_id not in self._archive_locations)):
                return False
            self._queue_archive_check_locked(round_id)
        return True

    def archive_status(self, round_id: str) -> Optional[ArchiveSnapshot]:
        """Return the latest shared archive status for a current-run round."""
        with self._lock:
            status = self._archive_states.get(round_id)
            round_ = self._tracked_rounds.get(round_id)
        if status is None:
            return None
        if round_ is None:
            return status
        snapshot = round_.snapshot()
        return ArchiveSnapshot(status.round_id, status.status, status.archived_at,
                               status.message, status.path, status.components,
                               snapshot.save_state, status.station)

    def archive_statuses(self) -> Tuple[ArchiveSnapshot, ...]:
        """Return lightweight archive and protection states for this App run."""
        with self._lock:
            round_ids = tuple(self._archive_states)
        return tuple(status for round_id in round_ids
                     if (status := self.archive_status(round_id)) is not None)

    @property
    def has_unarchived_rounds(self) -> bool:
        return any(not status.cleanup_eligible for status in self.archive_statuses())

    def _queue_archive_check_locked(self, round_id: str) -> None:
        if round_id in self._archive_queued:
            self._archive_dirty.add(round_id)
        else:
            self._archive_queued.add(round_id)
            self._archive_queue.put(round_id)
        if not self._archive_worker_active:
            self._archive_worker_active = True
            threading.Thread(target=self._archive_worker, daemon=True).start()

    def _archive_worker(self) -> None:
        while True:
            try:
                round_id = self._archive_queue.get(timeout=0.1)
            except Empty:
                with self._lock:
                    if self._archive_queue.empty():
                        self._archive_worker_active = False
                        return
                continue
            with self._lock:
                round_ = self._tracked_rounds.get(round_id)
                location = self._archive_locations.get(round_id)
            retry_after_save = False
            if round_ is not None:
                location = round_.archive_location
                if location is not None:
                    with self._lock:
                        self._archive_locations[round_id] = location
                snapshot = round_.snapshot()
                if snapshot.state in {RoundState.COMPLETED, RoundState.STOPPED} and snapshot.collection_stopped:
                    if snapshot.save_state == "saving":
                        status = ArchiveSnapshot(
                            round_id, "saving", message="等待 Session 與 audit 完整保存",
                            save_state=snapshot.save_state, station=round_.station)
                        retry_after_save = True
                    else:
                        status = self._archive_tracked_round(round_id, round_)
                    with self._lock:
                        self._archive_states[round_id] = status
                        self._prune_saved_rounds_locked()
                else:
                    status = self._archive_tracked_round(round_id, round_)
                    with self._lock:
                        self._archive_states[round_id] = status
            elif location is not None:
                status = self._archive_from_location(round_id, location)
                with self._lock:
                    self._archive_states[round_id] = status
            self._archive_queue.task_done()
            if retry_after_save:
                time.sleep(0.05)
            with self._lock:
                self._archive_queued.discard(round_id)
                changed_while_checking = round_id in self._archive_dirty
                self._archive_dirty.discard(round_id)
                if retry_after_save or changed_while_checking:
                    self._queue_archive_check_locked(round_id)

    def _archive_from_location(self, round_id: str,
                               location: ArchiveLocation) -> ArchiveSnapshot:
        """Revalidate a saved round after its live monitor has been released."""
        with self._lock:
            archive_lock = self._archive_locks.setdefault(round_id, threading.Lock())
        with archive_lock:
            return self._write_archive_from_location(round_id, location)

    def _write_archive_from_location(self, round_id: str,
                                     location: ArchiveLocation) -> ArchiveSnapshot:
        audit_path, session_path, station = (
            location.audit_path, location.session_path, location.station)
        now = normalize_archive_time(self._wall_clock())
        try:
            archived = write_round_archive(
                audit_path, session_path, now, expected_round_id=round_id)
        except OSError as error:
            return ArchiveSnapshot(round_id, "failed", message=str(error),
                                   path=audit_path.parent / "round-archive.json",
                                   save_state="complete", station=station)
        except (AuditRecordError, TypeError, ValueError) as error:
            return ArchiveSnapshot(round_id, "protected", message=str(error),
                                   save_state="complete", station=station)
        return ArchiveSnapshot(archived.round_id, archived.status, archived.archived_at,
                               archived.message, archived.path, archived.components,
                               "complete", station)

    def _archive_tracked_round(self, round_id: str, round_: MonitoringRound) -> ArchiveSnapshot:
        """Serialize seal writes for a tracked round against retry and close requests."""
        with self._lock:
            archive_lock = self._archive_locks.setdefault(round_id, threading.Lock())
        with archive_lock:
            return round_.archive_status(normalize_archive_time(self._wall_clock()))

    def request_close(self) -> CloseSnapshot:
        """Stop new rounds and durably flush all current-run records in a worker."""
        with self._lock:
            if self._close_status.status in {"waiting", "saving"}:
                return self._close_status
            self._closing = True
            generation = self._close_status.generation + 1
            round_ids = tuple(self._archive_states)
            self._close_status = CloseSnapshot("saving", generation, round_ids)
            self._start_close_worker_locked(generation)
            return self._close_status

    def start_retention_schedule(self, retention_days: int) -> RetentionStatus:
        """Schedule the required startup cleanup and subsequent 24-hour checks."""
        with self._lock:
            self._retention_days = retention_days
            self._retention_next_due = self._monotonic() + 24 * 60 * 60
        return self.request_retention_cleanup(retention_days, "app-startup")

    def retention_setting_changed(self, retention_days: int) -> RetentionStatus:
        """Schedule cleanup only after the global preference was durably saved."""
        with self._lock:
            self._retention_days = retention_days
            self._retention_next_due = self._monotonic() + 24 * 60 * 60
        return self.request_retention_cleanup(retention_days, "setting-changed")

    def save_retention_setting(self, retention_days: int, persist: Callable[[], None]) -> RetentionStatus:
        """Serialize a durable setting update with the final irreversible delete step."""
        if type(retention_days) is not int or retention_days <= 0:
            raise ValueError("保存天數必須是正整數")
        with self._lock:
            persist()
            self._retention_days = retention_days
            self._retention_next_due = self._monotonic() + 24 * 60 * 60
        return self.request_retention_cleanup(retention_days, "setting-changed")

    def poll_retention_schedule(self, retention_days: int) -> RetentionStatus:
        """Cheap Tk-safe due check; scanning and deletion always run in a worker."""
        with self._lock:
            if retention_days != self._retention_days:
                self._retention_days = retention_days
                self._retention_next_due = self._monotonic() + 24 * 60 * 60
            due = self._retention_next_due is not None and self._monotonic() >= self._retention_next_due
            if due:
                self._retention_next_due = self._monotonic() + 24 * 60 * 60
        if due:
            return self.request_retention_cleanup(retention_days, "24-hour-schedule")
        return self.retention_cleanup_status()

    def request_retention_cleanup(self, retention_days: int, trigger: str = "requested") -> RetentionStatus:
        """Queue/coalesce a cleanup run without blocking the caller."""
        if type(retention_days) is not int or retention_days <= 0:
            return RetentionStatus("failed", "保存天數無效，未執行清理",
                                   self.retention_cleanup_summaries())
        if self._retention_store is None:
            return RetentionStatus("failed", "未設定 App 管理的輪次資料目錄")
        with self._lock:
            self._retention_days = retention_days
            if self._closing:
                self._retention_pending_days = retention_days
                self._retention_pending_trigger = trigger
                self._retention_trigger_pending = True
                return self._retention_store.status.__class__(
                    "skipped", "關閉保存期間不啟動新清理", self._retention_store.summaries)
            self._retention_pending_days = retention_days
            self._retention_pending_trigger = trigger
            if self._retention_worker_active:
                self._retention_trigger_pending = True
                return self._retention_store.status
            self._retention_worker_active = True
            self._retention_trigger_pending = False
            threading.Thread(target=self._run_retention_worker, daemon=True).start()
        return self._retention_store.status

    def retention_cleanup_status(self) -> RetentionStatus:
        if self._retention_store is None:
            return RetentionStatus("idle", "未設定 App 管理的輪次資料目錄")
        return self._retention_store.status

    def retention_cleanup_summaries(self) -> Tuple[RetentionSummary, ...]:
        if self._retention_store is None:
            return ()
        return self._retention_store.summaries

    def _run_retention_worker(self) -> None:
        try:
            while True:
                with self._lock:
                    days = self._retention_pending_days
                    trigger = self._retention_pending_trigger
                    self._retention_trigger_pending = False
                self._retention_store.run(days, trigger)
                with self._lock:
                    if self._closing or not self._retention_trigger_pending:
                        return
        finally:
            with self._lock:
                self._retention_worker_active = False
                if self._retention_trigger_pending and not self._closing:
                    self._retention_worker_active = True
                    threading.Thread(target=self._run_retention_worker, daemon=True).start()

    def _protected_round_ids(self):
        with self._lock:
            protected = set(self._tracked_rounds)
            if self._current is not None:
                protected.add(self._current.round_id)
            return tuple(protected)

    def _retention_cleanup_allowed(self) -> bool:
        with self._lock:
            return not self._closing

    def _effective_retention_days(self) -> int:
        with self._lock:
            return self._retention_days

    def _delete_if_currently_expired(self, archived_at: datetime,
                                     operation: Callable[[], None]) -> None:
        with self._lock:
            if self._closing:
                raise ValueError("關閉保存期間不執行新的輪次刪除")
            if archived_at + timedelta(days=self._retention_days) > normalize_archive_time(
                    self._wall_clock()):
                raise ValueError("保存期限在刪除前已延長，停止刪除並保留剩餘進度")
            operation()

    def retry_close_saves(self) -> CloseSnapshot:
        """Retry failed rounds, then recheck every tracked round before close."""
        with self._lock:
            if self._close_status.status != "failed":
                return self._close_status
            self._closing = True
            generation = self._close_status.generation + 1
            self._close_status = CloseSnapshot(
                "saving", generation, tuple(self._archive_states))
            failed = tuple(round_ for round_ in self._tracked_rounds.values()
                           if round_.snapshot().save_state == "failed")
            failed_archive_ids = tuple(
                round_id for round_id, status in self._archive_states.items()
                if not status.cleanup_eligible)
        for round_ in failed:
            round_.retry_saves()
        with self._lock:
            for round_id in failed_archive_ids:
                self._queue_archive_check_locked(round_id)
            self._start_close_worker_locked(generation)
        return self.close_status()

    def cancel_close(self) -> CloseSnapshot:
        """Invalidate a close attempt without cancelling or discarding any save work."""
        with self._lock:
            if self._close_status.status == "complete":
                return self._close_status
            self._closing = False
            self._close_status = CloseSnapshot(
                "cancelled", self._close_status.generation + 1,
                tuple(self._archive_states), self._close_status.message)
            if self._retention_trigger_pending and not self._retention_worker_active:
                self._retention_worker_active = True
                threading.Thread(target=self._run_retention_worker, daemon=True).start()
            return self._close_status

    def close_status(self) -> CloseSnapshot:
        """Return the shared close-save state without reading historical Sessions."""
        with self._lock:
            return self._close_status

    def _start_close_worker_locked(self, generation: int) -> None:
        if self._close_worker_active:
            return
        self._close_worker_active = True
        threading.Thread(target=self._coordinate_close, args=(generation,), daemon=True).start()

    def _coordinate_close(self, generation: int) -> None:
        try:
            while True:
                if not self._close_attempt_is_current(generation):
                    return
                with self._lock:
                    cleanup_active = self._retention_worker_active
                    round_ids = tuple(self._archive_states)
                if not cleanup_active:
                    break
                self._set_close_waiting(generation, round_ids, "等待已開始的背景清理安全完成")
                threading.Event().wait(0.05)
            with self._lock:
                current = self._current
            if current is not None:
                current.stop()
            while True:
                if not self._close_attempt_is_current(generation):
                    return
                with self._lock:
                    rounds = tuple(self._tracked_rounds.items())
                    round_ids = tuple(self._archive_states)
                waiting_for_preparation = False
                for _round_id, round_ in rounds:
                    if not round_.wait_until_prepared(0.05):
                        waiting_for_preparation = True
                        break
                    if not self._close_attempt_is_current(generation):
                        return
                    round_.flush_session(timeout=None)
                    round_.flush_audit(timeout=None)
                if waiting_for_preparation:
                    self._set_close_waiting(generation, round_ids, "等待來源準備及停止交接完成")
                    continue
                snapshots = tuple(round_.finalize_close_snapshot() for _round_id, round_ in rounds)
                incomplete = tuple(
                    snapshot for (_round_id, round_), snapshot in zip(rounds, snapshots)
                    if not _round_close_complete(round_, snapshot))
                if not incomplete:
                    archive_failures = []
                    if self._audit_root is not None:
                        for round_id in round_ids:
                            with self._lock:
                                round_ = self._tracked_rounds.get(round_id)
                                location = self._archive_locations.get(round_id)
                                prior_archive = self._archive_states.get(round_id)
                                previously_archived = prior_archive is not None and (
                                    prior_archive.cleanup_eligible or prior_archive.status == "failed")
                            if round_ is not None:
                                location = round_.archive_location
                                if location is not None:
                                    with self._lock:
                                        self._archive_locations[round_id] = location
                                archive = self._archive_tracked_round(round_id, round_)
                                with self._lock:
                                    self._archive_states[round_id] = archive
                            elif location is not None:
                                archive = self._archive_from_location(round_id, location)
                                with self._lock:
                                    self._archive_states[round_id] = archive
                            else:
                                continue
                            if (previously_archived and not archive.cleanup_eligible and
                                    location is not None):
                                archive_failures.append("{}：{}".format(
                                    round_id[:10], archive.message or "封存資訊尚未完整保存"))
                    if archive_failures:
                        self._set_close_failure(
                            generation, round_ids,
                            "封存資訊保存失敗；視窗仍保持開啟。" + "; ".join(archive_failures))
                        return
                    with self._lock:
                        if self._closing and self._close_status.generation == generation:
                            self._close_status = CloseSnapshot("complete", generation, round_ids)
                    return
                failed = tuple(snapshot for snapshot in incomplete
                               if snapshot.save_state == "failed")
                if failed:
                    details = "; ".join(
                        "{}：{}".format(snapshot.round_id[:10],
                                        snapshot.save_errors[0] if snapshot.save_errors else "保存尚未完整")
                        for snapshot in failed)
                    self._set_close_failure(generation, round_ids, details)
                    return
                audit_incomplete = tuple(snapshot for snapshot in incomplete
                                         if snapshot.save_state == "complete" and
                                         not snapshot.audit_complete)
                if audit_incomplete:
                    details = "; ".join(
                        "{}：audit_complete 仍為 false".format(snapshot.round_id[:10])
                        for snapshot in audit_incomplete)
                    self._set_close_failure(generation, round_ids, details)
                    return
                operator_pending = tuple(snapshot for snapshot in incomplete
                                         if not _round_close_operators_complete(snapshot))
                if operator_pending:
                    details = "; ".join(
                        "{}：尚有 {} 項人工確認".format(
                            snapshot.round_id[:10],
                            len(snapshot.pending_conflicts) + int(
                                snapshot.round_alarm is not None and
                                not snapshot.round_alarm.acknowledged_at),
                        ) for snapshot in operator_pending)
                    self._set_close_waiting(generation, round_ids, details)
                    threading.Event().wait(0.05)
                    continue
                threading.Event().wait(0.05)
        except Exception as error:
            with self._lock:
                round_ids = tuple(self._tracked_rounds)
            self._set_close_failure(generation, round_ids, str(error))
        finally:
            with self._lock:
                self._close_worker_active = False
                if self._closing and self._close_status.status == "saving":
                    self._start_close_worker_locked(self._close_status.generation)

    def _close_attempt_is_current(self, generation: int) -> bool:
        with self._lock:
            return self._closing and self._close_status.generation == generation

    def _set_close_failure(self, generation: int, round_ids: Tuple[str, ...], error: str) -> None:
        with self._lock:
            if self._closing and self._close_status.generation == generation:
                self._close_status = CloseSnapshot("failed", generation, round_ids, error)

    def _set_close_waiting(self, generation: int, round_ids: Tuple[str, ...], detail: str) -> None:
        with self._lock:
            if self._closing and self._close_status.generation == generation:
                self._close_status = CloseSnapshot("waiting", generation, round_ids, detail)

    def unsaved_rounds(self) -> Tuple[RoundSnapshot, ...]:
        """Return current-run rounds that still need durable saving or protection."""
        with self._lock:
            self._prune_saved_rounds_locked()
            rounds = tuple(self._tracked_rounds.values())
        snapshots = [round_.snapshot() for round_ in rounds]
        snapshots = [snapshot for snapshot in snapshots if snapshot.save_state != "complete"]
        snapshots.sort(key=lambda snapshot: snapshot.round_id)
        return tuple(snapshots)

    @property
    def has_unsaved_rounds(self) -> bool:
        """Expose a shared protection state for save/archive/cleanup callers."""
        return bool(self.unsaved_rounds())

    def round_snapshot(self, round_id: str) -> Optional[RoundSnapshot]:
        """Return a tracked current-run round snapshot by its stable identity."""
        with self._lock:
            self._prune_saved_rounds_locked()
            round_ = self._tracked_rounds.get(round_id)
        return round_.snapshot() if round_ is not None else None

    def _prune_saved_rounds_locked(self) -> None:
        for round_id, round_ in tuple(self._tracked_rounds.items()):
            if round_ is self._current:
                continue
            archive = self._archive_states.get(round_id)
            snapshot = round_.snapshot()
            saved = snapshot.save_state == "complete"
            archival_unavailable = self._audit_root is None
            session_unavailable = round_.session_path is None
            no_operator_work = not snapshot.pending_conflicts and not (
                snapshot.round_alarm is not None and not snapshot.round_alarm.acknowledged_at)
            archive_location_available = round_id in self._archive_locations
            if saved and no_operator_work and (
                    archival_unavailable or session_unavailable or archive_location_available):
                del self._tracked_rounds[round_id]

    def stop(self) -> Optional[RoundSnapshot]:
        with self._lock:
            current = self._current
        return current.stop() if current is not None else None

    def resolve_review(self, conflict_id: str, choice: str) -> Optional[RoundSnapshot]:
        with self._lock:
            current = self._current
        return current.resolve_review(conflict_id, choice) if current is not None else None

    def acknowledge_round_alarm(self, round_id: str, alarm_id: str) -> Optional[RoundSnapshot]:
        with self._lock:
            current = self._current
        return current.acknowledge_round_alarm(round_id, alarm_id) if current is not None else None

    def snapshot(self) -> Optional[RoundSnapshot]:
        with self._lock:
            return self._current.snapshot() if self._current is not None else None

    def events_since(self, sequence: int = 0) -> Tuple[RoundEvent, ...]:
        with self._lock:
            return tuple(event for event in self._events if event.sequence > sequence)

    @property
    def current_round_id(self) -> Optional[str]:
        with self._lock:
            return self._current.round_id if self._current is not None else None

    def _record_round_event(self, event: RoundEvent) -> None:
        with self._lock:
            if event.round_id not in self._tracked_rounds:
                return
            previous = self._archive_states.get(event.round_id)
            if previous is not None and self._audit_root is not None:
                self._archive_states[event.round_id] = ArchiveSnapshot(
                    event.round_id, "saving", message="偵測到輪次紀錄更新，正在重新驗證封存",
                    save_state="saving", station=previous.station or
                    self._tracked_rounds[event.round_id].station)
            if self._audit_root is not None:
                self._queue_archive_check_locked(event.round_id)
            if self._current is not None and event.round_id == self._current.round_id:
                self._events.append(event)
            else:
                old_round = self._tracked_rounds[event.round_id]
                if old_round.snapshot().save_state == "complete":
                    del self._tracked_rounds[event.round_id]
        if self._on_event:
            self._on_event(event)
