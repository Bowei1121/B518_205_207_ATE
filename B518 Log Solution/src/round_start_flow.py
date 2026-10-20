"""Coordinate one accepted start request across configuration and round layers."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

from machine_profiles import MachineProfile
from monitoring_round import RoundCoordinator, RoundSnapshot, RoundState
from round_start_preparation import RoundStartPreparation


class StartFailurePhase(Enum):
    PROFILE_VALIDATION = "profile_validation"
    PREFERENCE_SAVE = "preference_save"
    SOURCE_START = "source_start"


class StartFlowStatus(Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    FAILED = "failed"


@dataclass(frozen=True)
class StartFlowFailure:
    phase: StartFailurePhase
    diagnostic: str
    snapshot: Optional[RoundSnapshot] = None


@dataclass(frozen=True)
class StartFlowResult:
    status: StartFlowStatus
    snapshot: Optional[RoundSnapshot] = None
    failure: Optional[StartFlowFailure] = None
    profile: Optional[MachineProfile] = None


class RoundStartFlow:
    """Apply the shared admission rules and run the non-UI start sequence once."""

    _BUSY_STATES = frozenset({
        RoundState.PREPARING,
        RoundState.RUNNING,
        RoundState.AWAITING_REVIEW,
    })

    def __init__(self, preparation: RoundStartPreparation):
        self._preparation = preparation
        self._lock = threading.Lock()
        self._in_progress = False

    def _claim(self, coordinator: RoundCoordinator, closing: bool) -> bool:
        with self._lock:
            if closing or self._in_progress:
                return False
            if coordinator.start_failure_snapshot() is not None:
                return False
            snapshot = coordinator.snapshot()
            if snapshot is not None and (
                    snapshot.cancellation_available or snapshot.state in self._BUSY_STATES):
                return False
            self._in_progress = True
            return True

    def run(self, coordinator: RoundCoordinator,
            select_profile: Callable[[], MachineProfile], session_root: Path,
            save_preferences: Callable[[], None],
            closing: bool = False) -> StartFlowResult:
        """Select, validate, persist and accept a round under one admission claim."""
        if not self._claim(coordinator, closing):
            return StartFlowResult(StartFlowStatus.REJECTED)

        try:
            profile = None
            try:
                profile = select_profile()
                prepared = self._preparation.prepare(
                    profile, session_root, async_session_writes=True,
                )
            except Exception as error:
                return StartFlowResult(StartFlowStatus.FAILED, failure=StartFlowFailure(
                    StartFailurePhase.PROFILE_VALIDATION, str(error),
                ), profile=profile)

            try:
                save_preferences()
            except Exception as error:
                return StartFlowResult(StartFlowStatus.FAILED, failure=StartFlowFailure(
                    StartFailurePhase.PREFERENCE_SAVE, str(error),
                ), profile=prepared.profile)

            try:
                snapshot = prepared.start(coordinator, run_async=True)
            except Exception as error:
                return StartFlowResult(StartFlowStatus.FAILED, failure=StartFlowFailure(
                    StartFailurePhase.SOURCE_START, str(error), coordinator.snapshot(),
                ), profile=prepared.profile)
            return StartFlowResult(
                StartFlowStatus.ACCEPTED, snapshot=snapshot, profile=prepared.profile,
            )
        finally:
            with self._lock:
                self._in_progress = False
