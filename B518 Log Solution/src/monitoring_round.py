"""Shared lifecycle, deadline and snapshot boundary for one monitoring round."""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, Optional, Protocol, Tuple

from log_monitoring import MonitorEvent, SlotResult, TERMINAL
from audit_records import AuditEvent, AuditRecordError, RoundAuditStore


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
        self._audit_store = None
        self._audit_condition = threading.Condition()
        self._audit_next_sequence = 1
        if audit_root is not None:
            try:
                self._audit_store = RoundAuditStore(
                    Path(audit_root), self.round_id, station, self._accepted_start_at,
                    self._started_monotonic, audit_context, on_error=self._audit_write_failed,
                )
            except (OSError, AuditRecordError, TypeError, ValueError) as error:
                self._audit_errors.append(str(error))

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
                self._prepare_monitor()
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
        with self._lock:
            results = tuple(
                RoundResult(result.slot, result.sn, result.status, result.source, result.updated_at)
                for result in sorted(self._monitor.round_results(), key=lambda result: result.slot)
            ) if self._monitor is not None and self._monitor_persistence_ready else self._preparation_results
            return RoundSnapshot(
                self.round_id, self.station, self._state, results,
                self._state == RoundState.COMPLETED, self._events[-1].sequence if self._events else 0,
                tuple(self._events), self._collection_stopped, self._completion_reason,
                tuple(self._pending_conflicts.values()), self._round_alarm, self._round_alarm_ready,
                not self._monitor_persistence_ready,
                self._audit_store is not None and not self._audit_errors and
                self._audit_store.error is None and not self._audit_store.pending,
                tuple(self._audit_errors),
                self._audit_store.pending if self._audit_store is not None else False,
            )

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

    def flush_session(self, timeout: Optional[float] = 10.0) -> bool:
        """Wait for the current adapter Session writer at read/close boundaries."""
        with self._lock:
            monitor = self._monitor
        session = getattr(monitor, "session", None)
        flush = getattr(session, "flush", None)
        return flush(timeout) if callable(flush) else True

    def _audit_write_failed(self, record: dict, message: str) -> None:
        with self._lock:
            if message not in self._audit_errors:
                self._audit_errors.append(message)
            failure = RoundEvent(
                self.round_id, len(self._events) + 1,
                MonitorEvent("audit_write_failed", message,
                             detail={"round_id": self.round_id,
                                     "failed_event_sequence": str(record.get("sequence", "unknown")),
                                     "audit_complete": "false"}),
            )
            self._events.append(failure)
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
            self._append_event(MonitorEvent(
                "collection_stopped", "{} 啟動失敗後停止收集".format(self.station),
                detail={"round_id": self.round_id, "reason": "start_failed",
                        "collection_stopped_at": self._collection_stopped_at},
            ))
            self._receive_monitor_event(
                MonitorEvent("start_failed", "無法準備監控來源：{}".format(error))
            )
            return
        self._run()

    def _prepare_monitor(self) -> None:
        monitor = self._monitor_factory(self._receive_monitor_event)
        with self._lock:
            self._monitor = monitor
            self._monitor_persistence_ready = False
            stop_requested = self._stop_requested
        session_path = getattr(getattr(monitor, "session", None), "path", None)
        if self._audit_store is not None and isinstance(session_path, (str, Path)):
            try:
                self._audit_store.attach_session(Path(session_path))
            except (OSError, AuditRecordError) as error:
                self._audit_errors.append("無法關聯傳統 Session 紀錄：{}".format(error))
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
        if event.kind == "session_write_failed":
            message = event.message
            if message not in self._audit_errors:
                self._audit_errors.append(message)
        with self._lock:
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
                self._completion_reason = "manual_stop"
            round_event = RoundEvent(self.round_id, len(self._events) + 1, event)
            self._events.append(round_event)
        self._persist_audit_event(round_event)
        self._on_event(round_event)

    def _persist_audit_event(self, round_event: RoundEvent) -> None:
        store = self._audit_store
        if store is None:
            return
        event = round_event.event
        failure_message = None
        with self._audit_condition:
            while round_event.sequence != self._audit_next_sequence:
                self._audit_condition.wait()
            try:
                store.append_event(
                    AuditEvent(round_event.sequence, event.kind, event.message, event.slot,
                               event.sn, event.status, event.source, dict(event.detail)),
                    self._wall_clock().isoformat(timespec="seconds"),
                    self._monotonic() - self._started_monotonic,
                )
            except (OSError, AuditRecordError, TypeError, ValueError) as error:
                failure_message = "輪次稽核紀錄保存失敗：{}".format(error)
                if failure_message not in self._audit_errors:
                    self._audit_errors.append(failure_message)
            # Actual I/O errors are reported by the writer callback, outside Tk.
            self._audit_next_sequence = round_event.sequence + (2 if failure_message else 1)
            self._audit_condition.notify_all()
        if failure_message:
            self._publish_audit_failure(round_event, failure_message)

    def _publish_audit_failure(self, failed_event: RoundEvent, message: str) -> None:
        with self._lock:
            failure = RoundEvent(
                self.round_id, len(self._events) + 1,
                MonitorEvent("audit_write_failed", message,
                             detail={"round_id": self.round_id,
                                     "failed_event_sequence": str(failed_event.sequence),
                                     "audit_complete": "false"}),
            )
            self._events.append(failure)
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
                    source_time = candidate_detail.get("source_time", "").strip().lower()
                    if not evidence_id or source_time in {"", "unknown", "none", "null"}:
                        self._fail_unconfirmed_candidate(event, current=current)
                        return "ignore"
                return "accept"
            else:
                terminal_conflict = current.status in TERMINAL and event.status in TERMINAL
                identity_conflict = bool(current.sn and event.sn and current.sn != event.sn)
                evidence_conflict = terminal_conflict or identity_conflict
                if not evidence_conflict:
                    return "accept"
                source_time = candidate_detail.get("source_time", "").strip().lower()
                if not same_round or source_time in {"", "unknown", "none", "null"}:
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
                 wall_clock: Callable[[], datetime] = datetime.now):
        self._lock = threading.RLock()
        self._current: Optional[MonitoringRound] = None
        self._events = []  # type: list[RoundEvent]
        self._on_event = on_event
        self._monotonic = monotonic
        self._audit_root = Path(audit_root) if audit_root is not None else None
        self._wall_clock = wall_clock

    def start(self, station: str,
              monitor_factory: Callable[[Callable[[MonitorEvent], None]], object],
              run_async: bool = True, round_timeout_seconds: Optional[int] = None,
              capacity: Optional[int] = None, audit_context: Optional[dict] = None) -> RoundSnapshot:
        with self._lock:
            if self._current is not None and self._current.snapshot().state in {
                    RoundState.RUNNING, RoundState.AWAITING_REVIEW}:
                return self._current.snapshot()
            session = MonitoringRound(station, monitor_factory, self._record_current_event, self._monotonic,
                                      round_timeout_seconds, capacity, self._audit_root, audit_context,
                                      self._wall_clock)
            self._current = session
            self._events = []
            try:
                return session.start(run_async=run_async)
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

    def _record_current_event(self, event: RoundEvent) -> None:
        with self._lock:
            if self._current is None or event.round_id != self._current.round_id:
                return
            self._events.append(event)
        if self._on_event:
            self._on_event(event)
