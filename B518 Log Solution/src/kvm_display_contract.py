"""Versioned, text-independent display contract for the KVM status marker."""

from enum import Enum
from typing import Optional, Tuple

from monitoring_round import RoundSnapshot, RoundState


CONTRACT_VERSION = "1.3"
# Mirror the existing KVM_Log reader blank-gutter checks.
GUTTER_POINTS = ((6, 29), (17, 29), (28, 29))
GUTTER_MIN = 232
MARKER_CELL_SIZE = 10
MARKER_CELL_GAP = 2
MARKER_QUIET_ZONE = 2
MARKER_SIZE = MARKER_QUIET_ZONE * 2 + MARKER_CELL_SIZE * 2 + MARKER_CELL_GAP
MARKER_SAMPLE_THRESHOLD = 128
MARKER_MIN_CONTRAST = 96
LOCATOR_SIZE = 22
LOCATOR_WHITE_SIZE = 8
LOCATOR_NEAR_INSET = 3
LOCATOR_FAR_INSET = 11
LOCATOR_LEFT = (0, 2)
LOCATOR_RIGHT = (320, 2)
STATE_MARKER_ORIGIN = (250, 0)
HEARTBEAT_MARKER_ORIGIN = (278, 0)
HEARTBEAT_INTERVAL_MS = 500
HEARTBEAT_PATTERNS = tuple(
    tuple(
        tuple(bool(state & (1 << (3 - (row * 2 + column)))) for column in range(2))
        for row in range(2)
    )
    for state in range(16)
)
LAYOUT_MARKER_ORIGIN = (130, 2)
LAYOUT_MARKER_SIZE = (MARKER_SIZE, MARKER_CELL_SIZE + MARKER_QUIET_ZONE * 2)
# The independent two-cell rail encodes visible rows, not result availability.
LAYOUT_MARKER_PATTERNS = {1: (True, False), 2: (False, True)}
KVM_FIRST_ROW_Y = 34
KVM_ROW_STEP = 27
KVM_CELL_WIDTH = 34
KVM_CELL_HEIGHT = 26
KVM_CELL_STEP = KVM_CELL_WIDTH
KVM_COLUMN_COUNT = 10


class MarkerState(str, Enum):
    STANDBY = "standby"
    PREPARING = "preparing"
    MONITORING = "monitoring"
    REVIEW = "review"
    COMPLETE = "complete"
    MANUAL_STOP_COMPLETE = "manual_stop_complete"


# True denotes black. Samples are ordered top-left, top-right, bottom-left,
# bottom-right; locator geometry establishes the screen orientation first.
MARKER_PATTERNS = {
    MarkerState.STANDBY: ((True, False), (False, True)),
    MarkerState.PREPARING: ((False, True), (False, True)),
    MarkerState.MONITORING: ((True, True), (False, False)),
    MarkerState.REVIEW: ((True, False), (True, False)),
    MarkerState.COMPLETE: ((False, True), (True, False)),
    MarkerState.MANUAL_STOP_COMPLETE: ((False, False), (True, True)),
}


def state_for_round_snapshot(snapshot: Optional[RoundSnapshot]) -> MarkerState:
    """Map one public round snapshot to the KVM state without UI-owned flags."""
    if snapshot is None:
        return MarkerState.STANDBY
    alarm = snapshot.round_alarm
    alarm_pending = alarm is not None and not alarm.acknowledged_at
    if (snapshot.state == RoundState.AWAITING_REVIEW or snapshot.pending_conflicts
            or snapshot.cancellation_available
            or alarm_pending):
        return MarkerState.REVIEW
    if snapshot.state == RoundState.COMPLETED and snapshot.result_available:
        return MarkerState.COMPLETE
    if (snapshot.state == RoundState.STOPPED and snapshot.result_available and
            snapshot.completion_reason == "manual_stop"):
        return MarkerState.MANUAL_STOP_COMPLETE
    if snapshot.state == RoundState.PREPARING:
        return MarkerState.PREPARING
    if snapshot.state == RoundState.RUNNING:
        return MarkerState.MONITORING
    return MarkerState.STANDBY


def _classify_marker_cells(samples: Tuple[int, ...], threshold: int,
                           min_contrast: int) -> Optional[MarkerState]:
    if len(samples) != 4:
        return None
    bits = []
    for sample in samples:
        if sample < 0 or sample > 255:
            return None
        if sample <= threshold - min_contrast // 2:
            bits.append(True)
        elif sample >= threshold + min_contrast // 2:
            bits.append(False)
        else:
            return None
    observed = ((bits[0], bits[1]), (bits[2], bits[3]))
    return next((state for state, pattern in MARKER_PATTERNS.items()
                 if pattern == observed), None)


def classify_kvm_frame_samples(locator_samples: Tuple[int, ...],
                               marker_samples: Tuple[int, ...],
                               threshold: int = MARKER_SAMPLE_THRESHOLD,
                               min_contrast: int = MARKER_MIN_CONTRAST) -> Optional[MarkerState]:
    """Classify oriented samples only when both asymmetric locators confirm direction.

    Locator values are sampled in this order: left locator's near white inset,
    left far black area, right near black area, right locator's far white inset.
    """
    if len(locator_samples) != 4 or any(
            sample < 0 or sample > 255 for sample in locator_samples):
        return None
    white_minimum = threshold + min_contrast // 2
    black_maximum = threshold - min_contrast // 2
    left_near, left_far, right_near, right_far = locator_samples
    if not (left_near >= white_minimum and left_far <= black_maximum
            and right_near <= black_maximum and right_far >= white_minimum):
        return None
    return _classify_marker_cells(marker_samples, threshold, min_contrast)
