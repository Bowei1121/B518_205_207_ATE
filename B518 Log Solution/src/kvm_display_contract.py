"""Versioned, text-independent display contract for the KVM status marker."""

from enum import Enum
from typing import Optional, Tuple


CONTRACT_VERSION = "1.0"
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
LOCATOR_LEFT = (82, 2)
LOCATOR_RIGHT = (320, 2)
STATE_MARKER_ORIGIN = (278, 0)
KVM_FIRST_ROW_Y = 34
KVM_ROW_STEP = 27
KVM_CELL_WIDTH = 34
KVM_CELL_HEIGHT = 26


class MarkerState(str, Enum):
    STANDBY = "standby"
    MONITORING = "monitoring"
    REVIEW = "review"
    COMPLETE = "complete"


# True denotes black. Samples are ordered top-left, top-right, bottom-left,
# bottom-right; locator geometry establishes the screen orientation first.
MARKER_PATTERNS = {
    MarkerState.STANDBY: ((True, False), (False, True)),
    MarkerState.MONITORING: ((True, True), (False, False)),
    MarkerState.REVIEW: ((True, False), (True, False)),
    MarkerState.COMPLETE: ((False, True), (True, False)),
}


def state_for_round_snapshot(snapshot) -> MarkerState:
    """Map one public round snapshot to the KVM state without UI-owned flags."""
    if snapshot is None:
        return MarkerState.STANDBY
    if snapshot.result_available and snapshot.state.value == "COMPLETED":
        return MarkerState.COMPLETE
    alarm = snapshot.round_alarm
    alarm_pending = alarm is not None and not alarm.acknowledged_at
    if (snapshot.state.value == "AWAITING_REVIEW" or snapshot.pending_conflicts
            or alarm_pending):
        return MarkerState.REVIEW
    if snapshot.state.value == "RUNNING":
        return MarkerState.MONITORING
    return MarkerState.STANDBY


def classify_marker_cells(samples: Tuple[int, ...], threshold: int = MARKER_SAMPLE_THRESHOLD,
                          min_contrast: int = MARKER_MIN_CONTRAST) -> Optional[MarkerState]:
    """Classify four grayscale cell averages; return None for weak/unknown input."""
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
