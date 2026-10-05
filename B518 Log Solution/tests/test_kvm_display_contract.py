import unittest
from types import SimpleNamespace

from kvm_display_contract import (
    CONTRACT_VERSION,
    KVM_FIRST_ROW_Y,
    KVM_ROW_STEP,
    LOCATOR_SIZE,
    MARKER_PATTERNS,
    MARKER_SIZE,
    MarkerState,
    classify_marker_cells,
    state_for_round_snapshot,
)
from monitoring_round import RoundSnapshot, RoundState


class KvmDisplayContractTests(unittest.TestCase):
    def snapshot(self, state, *, available=False, conflicts=(), alarm=None,
                 collection_stopped=False, completion_reason=""):
        return RoundSnapshot(
            round_id="sample-round", station="FCT", state=state, results=(),
            result_available=available, event_sequence=0, events=(),
            collection_stopped=collection_stopped, completion_reason=completion_reason,
            pending_conflicts=conflicts, round_alarm=alarm,
        )

    def test_round_snapshot_maps_to_four_machine_readable_states(self):
        cases = (
            (self.snapshot(RoundState.READY), MarkerState.STANDBY),
            (self.snapshot(RoundState.RUNNING), MarkerState.MONITORING),
            (self.snapshot(RoundState.AWAITING_REVIEW), MarkerState.REVIEW),
            (self.snapshot(RoundState.COMPLETED, available=True,
                           collection_stopped=True), MarkerState.COMPLETE),
            (self.snapshot(RoundState.STOPPED, completion_reason="manual_stop",
                           collection_stopped=True), MarkerState.STANDBY),
        )
        for snapshot, expected in cases:
            with self.subTest(state=snapshot.state):
                self.assertEqual(state_for_round_snapshot(snapshot), expected)

    def test_pending_confirmations_take_priority_over_collection_state(self):
        conflict = object()
        alarm = SimpleNamespace(acknowledged_at="")
        for snapshot in (
            self.snapshot(RoundState.RUNNING, conflicts=(conflict,)),
            self.snapshot(RoundState.RUNNING, alarm=alarm),
            self.snapshot(RoundState.STOPPED, conflicts=(conflict,), collection_stopped=True),
        ):
            with self.subTest(state=snapshot.state):
                self.assertEqual(state_for_round_snapshot(snapshot), MarkerState.REVIEW)

    def test_four_fixed_black_white_patterns_are_unique_and_decodable(self):
        self.assertEqual(CONTRACT_VERSION, "1.0")
        self.assertEqual(len(set(MARKER_PATTERNS.values())), 4)
        self.assertEqual(MARKER_SIZE, 26)
        for state, pattern in MARKER_PATTERNS.items():
            samples = tuple(0 if bit else 255 for row in pattern for bit in row)
            with self.subTest(state=state):
                self.assertEqual(classify_marker_cells(samples), state)

    def test_low_contrast_missing_or_unknown_marker_is_not_recognized(self):
        self.assertIsNone(classify_marker_cells((110, 145, 130, 120)))
        self.assertIsNone(classify_marker_cells((0, 0, 0, 0)))
        self.assertIsNone(classify_marker_cells((0, 0, 255)))
        self.assertIsNone(classify_marker_cells((20, 20, 20, 20)))

    def test_locator_and_two_row_geometry_keep_marker_separate_from_result_cells(self):
        self.assertEqual(LOCATOR_SIZE, 22)
        self.assertGreater(KVM_FIRST_ROW_Y, MARKER_SIZE)
        self.assertEqual(KVM_ROW_STEP, 27)


if __name__ == "__main__":
    unittest.main()
