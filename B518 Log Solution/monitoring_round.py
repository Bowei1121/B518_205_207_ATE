"""Shared lifecycle, event and snapshot boundary for one monitoring round."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, Optional, Tuple

from log_monitoring import MonitorEvent, SlotResult


@dataclass(frozen=True)
class RoundEvent:
    round_id: str
    sequence: int
    event: MonitorEvent


class RoundState(str, Enum):
    READY = "READY"
    RUNNING = "RUNNING"
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


class MonitoringRound:
    """Own the lifecycle semantics while a platform monitor owns file parsing."""

    def __init__(self, station: str, monitor_factory: Callable[[Callable[[MonitorEvent], None]], object],
                 on_event: Callable[[RoundEvent], None]):
        self.round_id = uuid.uuid4().hex
        self.station = station
        self._monitor = monitor_factory(self._receive_monitor_event)
        self._on_event = on_event
        self._lock = threading.RLock()
        self._state = RoundState.READY
        self._events = []  # type: list[RoundEvent]
        self._started = False

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
                self._monitor.start()
            return self.snapshot()

    def stop(self) -> RoundSnapshot:
        with self._lock:
            if self._state == RoundState.RUNNING:
                self._monitor.stop()
                if self._state == RoundState.RUNNING:
                    self._state = RoundState.STOPPED
            return self.snapshot()

    def snapshot(self) -> RoundSnapshot:
        with self._lock:
            results = tuple(
                RoundResult(result.slot, result.sn, result.status, result.source, result.updated_at)
                for result in sorted(self._monitor.results.values(), key=lambda result: result.slot)
            )
            return RoundSnapshot(
                self.round_id, self.station, self._state, results,
                self._state == RoundState.COMPLETED, self._events[-1].sequence if self._events else 0,
                tuple(self._events),
            )

    def events_since(self, sequence: int = 0) -> Tuple[RoundEvent, ...]:
        with self._lock:
            return tuple(event for event in self._events if event.sequence > sequence)

    def _receive_monitor_event(self, event: MonitorEvent) -> None:
        with self._lock:
            if event.kind == "finished":
                self._state = RoundState.COMPLETED
            elif event.kind == "stopped" or (
                event.kind == "timeout" and event.detail.get("kind") == "start"
            ):
                self._state = RoundState.STOPPED
            round_event = RoundEvent(self.round_id, len(self._events) + 1, event)
            self._events.append(round_event)
        self._on_event(round_event)


class RoundCoordinator:
    """Provide one application entry point and reject events from prior rounds."""

    def __init__(self, on_event: Optional[Callable[[RoundEvent], None]] = None):
        self._lock = threading.RLock()
        self._current: Optional[MonitoringRound] = None
        self._events = []  # type: list[RoundEvent]
        self._on_event = on_event

    def start(self, station: str,
              monitor_factory: Callable[[Callable[[MonitorEvent], None]], object],
              run_async: bool = True) -> RoundSnapshot:
        with self._lock:
            if self._current is not None and self._current.snapshot().state == RoundState.RUNNING:
                return self._current.snapshot()
            session = MonitoringRound(station, monitor_factory, self._record_current_event)
            self._current = session
            self._events = []
            try:
                return session.start(run_async=run_async)
            except Exception:
                self._current = None
                raise

    def stop(self) -> Optional[RoundSnapshot]:
        with self._lock:
            return self._current.stop() if self._current is not None else None

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
