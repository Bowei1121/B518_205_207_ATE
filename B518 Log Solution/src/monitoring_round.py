"""Shared lifecycle, deadline and snapshot boundary for one monitoring round."""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Callable, Dict, Optional, Tuple

from log_monitoring import MonitorEvent, SlotResult, TERMINAL


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
        self._poll_started_at: Optional[float] = None
        self._run_thread: Optional[threading.Thread] = None
        self._monitor_factory = monitor_factory
        self._monitor = None

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
                if self._state != RoundState.RUNNING or self._collection_stopped:
                    return self.snapshot()
                if self._monitor is None:
                    return self.snapshot()
            poll_time = self._monotonic()
            self._apply_deadlines(poll_time)
            self._finish_if_terminal()
            with self._lock:
                if self._state != RoundState.RUNNING or self._collection_stopped:
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
            if self._state == RoundState.RUNNING:
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

    def resolve_review(self, choice: str) -> RoundSnapshot:
        """Resolve captured review evidence, then apply the normal release rule."""
        with self._poll_lock:
            with self._lock:
                monitor = self._monitor
                if monitor is None or self._state not in {
                        RoundState.RUNNING, RoundState.AWAITING_REVIEW}:
                    return self.snapshot()
            resolver = getattr(monitor, "resolve_review", None)
            if not callable(resolver):
                return self.snapshot()
            resolver(choice)
            if self._collection_stopped:
                self._finish_if_terminal()
            return self.snapshot()

    def snapshot(self) -> RoundSnapshot:
        with self._lock:
            results = tuple(
                RoundResult(result.slot, result.sn, result.status, result.source, result.updated_at)
                for result in sorted(self._monitor.results.values(), key=lambda result: result.slot)
            ) if self._monitor is not None else ()
            return RoundSnapshot(
                self.round_id, self.station, self._state, results,
                self._state == RoundState.COMPLETED, self._events[-1].sequence if self._events else 0,
                tuple(self._events), self._collection_stopped, self._completion_reason,
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
            self._publish_round_event(MonitorEvent("start_failed", "無法準備監控來源：{}".format(error)))
            return
        self._run()

    def _prepare_monitor(self) -> None:
        monitor = self._monitor_factory(self._receive_monitor_event)
        with self._lock:
            self._monitor = monitor
            stop_requested = self._stop_requested
        session = getattr(monitor, "session", None)
        if session is not None:
            session.update_settings({"accepted_start_at": self._accepted_start_at})
        if stop_requested:
            monitor.stop()
            return
        monitor.start()
        self._publish_round_event(MonitorEvent("round_ready", "{} 監控來源準備就緒".format(self.station)))

    def _run(self) -> None:
        while True:
            with self._lock:
                if self._state != RoundState.RUNNING or self._collection_stopped:
                    return
            self.poll_once()
            with self._lock:
                if self._state != RoundState.RUNNING or self._collection_stopped:
                    return
            time.sleep(0.5)

    def _apply_deadlines(self, at: float) -> None:
        if self._monitor is None:
            return
        elapsed = max(0.0, at - self._started_monotonic)
        round_limit = self._timeout_limit("round_timeout_seconds", 7200)
        if elapsed >= round_limit:
            for slot, result in sorted(self._monitor.results.items()):
                if result.status in TERMINAL:
                    continue
                status = "TIMEOUT" if result.status in {"TESTING", "COMPLETING"} else "NOTEST"
                self._set_deadline_result(slot, status, "round_deadline", round_limit, elapsed)
            self._emit_timeout("round", None, round_limit, elapsed)
            self._stop_collection("round_deadline")
            with self._lock:
                self._state = RoundState.AWAITING_REVIEW
            return

        start_limit = self._timeout_limit("start_timeout_seconds", 30)
        if elapsed >= start_limit:
            for slot, result in sorted(self._monitor.results.items()):
                if result.status != "WAITING" or slot in self._activity_slots:
                    continue
                self._set_deadline_result(slot, "NOTEST", "start_deadline_no_activity", start_limit, elapsed)

        test_limit = self._timeout_limit("test_timeout_seconds", 480)
        for slot, started_at in sorted(self._test_started.items()):
            result = self._monitor.results.get(slot)
            if result is None or result.status in TERMINAL or slot in self._deadline_slots:
                continue
            test_elapsed = max(0.0, at - started_at)
            if test_elapsed >= test_limit:
                self._set_deadline_result(slot, "TIMEOUT", "test_deadline", test_limit, test_elapsed)

    def _timeout_limit(self, name: str, fallback: int) -> int:
        value = getattr(self._monitor, name, fallback)
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
        self._monitor.set_result(slot, status, detail=detail, lock_terminal=True)
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
        if hasattr(self._monitor, "emit_display_event"):
            self._monitor.emit_display_event(event)
        elif hasattr(self._monitor, "emit"):
            self._monitor.emit(event)
        else:
            self._receive_monitor_event(event)

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
        if not self._monitor.results or any(result.status not in TERMINAL
                                            for result in self._monitor.results.values()):
            return
        self._stop_collection("results_terminal")
        if getattr(self._monitor, "review_pending", None) is not None:
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
        with self._lock:
            if event.kind == "result" and event.slot is not None:
                result = self._monitor.results.get(event.slot) if self._monitor is not None else None
                if result is not None and result.status in {"TESTING", "COMPLETING"}:
                    self._activity_slots.add(event.slot)
                    if event.status == "TESTING" or event.detail.get("trusted_activity") == "true":
                        started_at = self._poll_started_at
                        if started_at is None:
                            started_at = self._monotonic()
                        self._test_started.setdefault(event.slot, started_at)
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

    def resolve_review(self, choice: str) -> Optional[RoundSnapshot]:
        with self._lock:
            current = self._current
        return current.resolve_review(choice) if current is not None else None

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
