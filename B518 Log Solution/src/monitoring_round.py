"""Shared lifecycle, deadline and snapshot boundary for one monitoring round."""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, Optional, Protocol, Tuple

from log_monitoring import MonitorEvent, SlotResult, TERMINAL


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


class MonitoringRound:
    """Apply common deadlines and lifecycle rules to platform observations."""

    def __init__(self, station: str, monitor_factory: Callable[[Callable[[MonitorEvent], None]], object],
                 on_event: Callable[[RoundEvent], None], monotonic: Callable[[], float]):
        self.round_id = uuid.uuid4().hex
        self.station = station
        self._monotonic = monotonic
        # Capture the accepted start before a monitor snapshots or prepares sources.
        self._started_monotonic = monotonic()
        self._accepted_start_at = datetime.now().isoformat(timespec="seconds")
        self._lock = threading.RLock()
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
        self._poll_started_at: Optional[float] = None
        self._run_thread: Optional[threading.Thread] = None
        self._monitor_factory = monitor_factory
        self._monitor: Optional[RoundMonitor] = None

    @property
    def monitor(self):
        """Compatibility access for existing platform-specific review actions."""
        return self._monitor

    def start(self, run_async: bool = True) -> RoundSnapshot:
        with self._lock:
            if self._started or self._state != RoundState.READY:
                return self.snapshot()
            self._started = True
            self._state = RoundState.RUNNING
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
                if self._monitor is None:
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
        with self._lock:
            if self._state in {RoundState.RUNNING, RoundState.AWAITING_REVIEW}:
                self._stop_requested = True
                if self._monitor is not None:
                    self._monitor.stop()
                    if self._state == RoundState.RUNNING:
                        self._state = RoundState.STOPPED
                        self._collection_stopped = True
                        self._completion_reason = "manual_stop"
                else:
                    self._state = RoundState.STOPPED
                    self._collection_stopped = True
                    self._completion_reason = "manual_stop"
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
                    "original_sn": conflict.original.sn or "unknown",
                    "original_status": conflict.original.status,
                    "candidate_sn": conflict.candidate.sn or "unknown",
                    "candidate_status": conflict.candidate.status,
                    "candidate_source_id": conflict.candidate.source_id or "unknown",
                    "candidate_source_time": conflict.candidate.source_time or "unknown",
                    "selected_at": datetime.now().isoformat(timespec="seconds"),
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

    def snapshot(self) -> RoundSnapshot:
        with self._lock:
            results = tuple(
                RoundResult(result.slot, result.sn, result.status, result.source, result.updated_at)
                for result in sorted(self._monitor.round_results(), key=lambda result: result.slot)
            ) if self._monitor is not None else ()
            return RoundSnapshot(
                self.round_id, self.station, self._state, results,
                self._state == RoundState.COMPLETED, self._events[-1].sequence if self._events else 0,
                tuple(self._events), self._collection_stopped, self._completion_reason,
                tuple(self._pending_conflicts.values()),
            )

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
            self._receive_monitor_event(
                MonitorEvent("start_failed", "無法準備監控來源：{}".format(error))
            )
            return
        self._run()

    def _prepare_monitor(self) -> None:
        monitor = self._monitor_factory(self._receive_monitor_event)
        with self._lock:
            self._monitor = monitor
            stop_requested = self._stop_requested
        monitor.update_round_settings({"accepted_start_at": self._accepted_start_at,
                                       "round_candidate_mode": True})
        if stop_requested:
            monitor.stop()
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
            return
        elapsed = max(0.0, at - self._started_monotonic)
        round_limit = self._timeout_limit("round", 7200)
        if elapsed >= round_limit:
            for result in self._monitor.round_results():
                slot = result.slot
                if result.status in TERMINAL:
                    continue
                status = "TIMEOUT" if result.status in {"TESTING", "COMPLETING"} else "NOTEST"
                self._set_deadline_result(slot, status, "round_deadline", round_limit, elapsed)
            self._emit_timeout("round", None, round_limit, elapsed)
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
        value = self._monitor.timeout_seconds(kind)
        return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else fallback

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

    def _emit_timeout(self, kind: str, slot: Optional[int], deadline_seconds: int, elapsed: float) -> None:
        self._publish_round_event(MonitorEvent(
            "timeout", "{} 整輪監控逾時：{} 秒（經過 {} 秒）".format(
                self.station, deadline_seconds, int(elapsed),
            ), slot=slot, status="TIMEOUT",
            detail={"kind": kind, "reason": "round_deadline", "deadline_seconds": str(deadline_seconds),
                    "elapsed_seconds": str(int(elapsed))},
        ))

    def _publish_round_event(self, event: MonitorEvent) -> None:
        self._monitor.publish_round_event(event)

    def _stop_collection(self, reason: str) -> None:
        if self._collection_stopped:
            return
        if self._monitor is None:
            return
        self._monitor.stop_collection()
        with self._lock:
            self._collection_stopped = True
            self._completion_reason = reason

    def _finish_if_terminal(self) -> None:
        if self._monitor is None:
            return
        with self._lock:
            if self._state not in {RoundState.RUNNING, RoundState.AWAITING_REVIEW}:
                return
            if self._state == RoundState.AWAITING_REVIEW and self._completion_reason == "round_deadline":
                return
        results = self._monitor.round_results()
        if not results or any(result.status not in TERMINAL for result in results):
            return
        self._stop_collection("results_terminal")
        if self._pending_conflicts:
            with self._lock:
                self._state = RoundState.AWAITING_REVIEW
                self._completion_reason = "review_pending"
            return
        with self._lock:
            if self._state not in {RoundState.RUNNING, RoundState.AWAITING_REVIEW}:
                return
            self._state = RoundState.COMPLETED
            self._completion_reason = "results_terminal"
        self._monitor.finish()
        self._publish_round_event(MonitorEvent("finished", "{} 本輪完成".format(self.station)))

    def _receive_monitor_event(self, event: MonitorEvent) -> None:
        if event.kind == "result_candidate":
            return self._consider_result_candidate(event)
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
                self._completion_reason = "results_terminal"
            elif event.kind == "stopped":
                self._state = RoundState.STOPPED
                self._collection_stopped = True
                self._completion_reason = "manual_stop"
            round_event = RoundEvent(self.round_id, len(self._events) + 1, event)
            self._events.append(round_event)
        self._on_event(round_event)

    def _consider_result_candidate(self, event: MonitorEvent) -> str:
        """Admit source facts, queue confirmed contradictions, and retain uncertainty."""
        outbound_event = None
        decision = "ignore"
        with self._lock:
            current = next((item for item in self._monitor.round_results()
                            if item.slot == event.slot), None) if self._monitor else None
            current_detail = self._result_evidence.get(event.slot or -1, {})
            candidate_detail = dict(event.detail)
            evidence_id = candidate_detail.get("round_evidence_id", "")
            current_evidence_id = current_detail.get("round_evidence_id", "")
            if current is None or current.status == "WAITING":
                return "accept"
            same_round = bool(evidence_id and current_evidence_id and evidence_id == current_evidence_id)
            same_value = current.status == event.status and current.sn == event.sn
            if same_value:
                if current.source != event.source:
                    outbound_event = MonitorEvent(
                        "duplicate_source", "slot{} 一致重複來源已記錄".format(event.slot),
                        event.slot, event.sn, event.status, event.source,
                        {"original_source": current.source, "source_id": candidate_detail.get("source_id", "unknown"),
                         "source_time": candidate_detail.get("source_time", "unknown")},
                    )
            else:
                terminal_conflict = current.status in TERMINAL and event.status in TERMINAL
                identity_conflict = bool(current.sn and event.sn and current.sn != event.sn)
                evidence_conflict = terminal_conflict or identity_conflict
                if not evidence_conflict:
                    return "accept"
                if not same_round:
                    outbound_event = MonitorEvent(
                        "unresolved_source_conflict",
                        "slot{} 出現無法確認同輪的矛盾來源；保留證據待後續政策處理".format(event.slot),
                        event.slot, event.sn, event.status, event.source,
                        {"original_sn": current.sn or "unknown", "original_status": current.status,
                         "original_source": current.source, "candidate_sn": event.sn or "unknown",
                         "candidate_status": event.status,
                         "candidate_source_id": candidate_detail.get("source_id", "unknown"),
                         "candidate_source_time": candidate_detail.get("source_time", "unknown"),
                         **candidate_detail},
                    )
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
                            datetime.now().isoformat(timespec="seconds"),
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
                             "candidate_sn": candidate.sn or "unknown", "candidate_status": candidate.status,
                             "candidate_source_id": candidate.source_id or "unknown",
                             "candidate_source_time": candidate.source_time or "unknown",
                             "same_round_evidence_id": evidence_id or "unknown"},
                        )
                        decision = "defer"
        if outbound_event is not None:
            self._append_event(outbound_event)
        return decision

    @staticmethod
    def _conflict_side(sn: str, status: str, source: str, detail: Dict[str, str]) -> ConflictSide:
        return ConflictSide(sn, status, source, detail.get("source_id", ""), detail.get("source_time", ""),
                            tuple(sorted(detail.items())))

    def _append_event(self, event: MonitorEvent) -> None:
        # Route common decisions through the adapter's public event seam so
        # round snapshots, the Tk queue, and the persistent session share one
        # ordered record, including the source path when one is available.
        if self._monitor is not None:
            self._monitor.publish_round_event(event)


class RoundCoordinator:
    """Provide the application entry point for one profile-backed round."""

    def __init__(self, on_event: Optional[Callable[[RoundEvent], None]] = None,
                 monotonic: Callable[[], float] = time.monotonic):
        self._lock = threading.RLock()
        self._current: Optional[MonitoringRound] = None
        self._events = []  # type: list[RoundEvent]
        self._on_event = on_event
        self._monotonic = monotonic

    def start(self, station: str,
              monitor_factory: Callable[[Callable[[MonitorEvent], None]], object],
              run_async: bool = True) -> RoundSnapshot:
        with self._lock:
            if self._current is not None and self._current.snapshot().state in {
                    RoundState.RUNNING, RoundState.AWAITING_REVIEW}:
                return self._current.snapshot()
            session = MonitoringRound(station, monitor_factory, self._record_current_event, self._monotonic)
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

    def stop(self) -> Optional[RoundSnapshot]:
        with self._lock:
            return self._current.stop() if self._current is not None else None

    def resolve_review(self, conflict_id: str, choice: str) -> Optional[RoundSnapshot]:
        with self._lock:
            current = self._current
        return current.resolve_review(conflict_id, choice) if current is not None else None

    def snapshot(self) -> Optional[RoundSnapshot]:
        with self._lock:
            return self._current.snapshot() if self._current is not None else None

    def events_since(self, sequence: int = 0) -> Tuple[RoundEvent, ...]:
        with self._lock:
            return tuple(event for event in self._events if event.sequence > sequence)

    @property
    def monitor(self):
        with self._lock:
            return self._current.monitor if self._current is not None else None

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
