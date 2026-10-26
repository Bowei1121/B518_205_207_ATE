import os
import json
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from types import SimpleNamespace
from pathlib import Path

from kvm_display_contract import (
    CONTRACT_VERSION,
    GUTTER_POINTS, GUTTER_MIN, LAYOUT_MARKER_SIZE,
    HEARTBEAT_MARKER_ORIGIN,
    HEARTBEAT_PATTERNS,
    KVM_FIRST_ROW_Y,
    KVM_CELL_STEP,
    KVM_CELL_WIDTH,
    KVM_CELL_HEIGHT,
    KVM_COLUMN_COUNT,
    KVM_ROW_STEP,
    LOCATOR_LEFT,
    LOCATOR_RIGHT,
    LOCATOR_SIZE,
    LOCATOR_WHITE_SIZE,
    LAYOUT_MARKER_ORIGIN,
    MARKER_PATTERNS,
    MARKER_SIZE,
    STATE_MARKER_ORIGIN,
    MarkerState,
    classify_kvm_frame_samples,
    state_for_round_snapshot,
)
from monitoring_round import RoundSnapshot, RoundState


class KvmDisplayContractTests(unittest.TestCase):
    def snapshot(self, state, *, available=False, conflicts=(), alarm=None,
                 collection_stopped=False, completion_reason="", cancel_available=False):
        return RoundSnapshot(
            round_id="sample-round", station="FCT", state=state, results=(),
            result_available=available, event_sequence=0, events=(),
            collection_stopped=collection_stopped, completion_reason=completion_reason,
            pending_conflicts=conflicts, round_alarm=alarm,
            cancellation_available=cancel_available,
        )

    def test_gutter_points_match_kvm_reader_and_stay_clear_of_locators_markers_and_cells(self):
        # B518_KVM_Log host-app/log_solution_reader.py @76686df.
        self.assertEqual(GUTTER_POINTS, ((6, 29), (17, 29), (28, 29)))
        self.assertEqual(GUTTER_MIN, 232)
        areas = [(p, (LOCATOR_SIZE, LOCATOR_SIZE)) for p in (LOCATOR_LEFT, LOCATOR_RIGHT)]
        areas += [(p, (MARKER_SIZE, MARKER_SIZE))
                  for p in (STATE_MARKER_ORIGIN, HEARTBEAT_MARKER_ORIGIN)]
        areas.append((LAYOUT_MARKER_ORIGIN, LAYOUT_MARKER_SIZE))
        areas += [((col * KVM_CELL_STEP, KVM_FIRST_ROW_Y + row * KVM_ROW_STEP),
                   (KVM_CELL_WIDTH, KVM_CELL_HEIGHT))
                  for row in range(2) for col in range(KVM_COLUMN_COUNT)]
        for px, py in GUTTER_POINTS:
            for (x, y), (w, h) in areas:
                with self.subTest(point=(px, py), area=(x, y, w, h)):
                    self.assertTrue(px + 1.2 < x or px - 1.2 > x + w or
                                    py + 1.2 < y or py - 1.2 > y + h)

    def test_kvm_background_and_waiting_colour_respect_gutter_minimum(self):
        from b518_log_solution import LIGHT_BACKGROUND, STATUS_COLOURS

        def channels(colour):
            return tuple(int(colour[i:i + 2], 16) for i in (1, 3, 5))

        self.assertTrue(all(c >= GUTTER_MIN for c in channels(LIGHT_BACKGROUND)))
        self.assertTrue(any(c < GUTTER_MIN for c in channels(STATUS_COLOURS["WAITING"])))
        for status, colour in STATUS_COLOURS.items():
            with self.subTest(status=status):
                self.assertTrue(any(c < GUTTER_MIN for c in channels(colour)))

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_real_tk_kvm_gutter_points_stay_bright_across_capacity_and_states(self):
        import tkinter as tk
        from b518_log_solution import B518LogSolutionApp, LIGHT_BACKGROUND, STATUS_COLOURS
        from test_log_solution_ui import FakeHotkey
        from language_catalog import ENGLISH, TRADITIONAL_CHINESE

        with TemporaryDirectory() as temporary, patch(
                "b518_log_solution.APP_ROOT", Path(temporary)), patch(
                "b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.deiconify()
            app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey,
                                     session_root=Path(temporary) / "sessions",
                                     app_event_path=Path(temporary) / "events.json")
            try:
                app._configure_appearance()  # Startup's forced-light appearance helper.
                for capacity in (1, 10, 11, 20):
                    with patch.object(app, "_display_capacity", return_value=capacity):
                        for language in (ENGLISH, TRADITIONAL_CHINESE):
                            app._select_language(language)
                            app._render_rows()
                            for state, snapshot in (
                                    ("standby", None),
                                    ("monitoring", self.snapshot(RoundState.RUNNING)),
                                    ("complete", self.snapshot(RoundState.COMPLETED,
                                                              available=True,
                                                              collection_stopped=True))):
                                with self.subTest(capacity=capacity, language=language, state=state):
                                    app._render_state_marker(snapshot)
                                    statuses = tuple(STATUS_COLOURS)
                                    for slot in range(1, capacity + 1):
                                        status = ("WAITING" if state == "standby" else
                                                  "PASS" if state == "complete" else
                                                  statuses[(slot - 1) % len(statuses)])
                                        app._set_kvm_result_block(slot, status)
                                    root.update_idletasks()
                                    band = app.kvm_results
                                    self.assertEqual(band.cget("background"), LIGHT_BACKGROUND)
                                    self.assertTrue(all(c // 257 >= GUTTER_MIN for c in
                                                        band.winfo_rgb(band.cget("background"))))
                                    for x, y in GUTTER_POINTS:
                                        # Existing Tk geometry tests use screen units directly.
                                        self.assertIs(root.winfo_containing(
                                            band.winfo_rootx() + x, band.winfo_rooty() + y), band)
            finally:
                app.hotkey.close()
                root.destroy()

    def test_round_snapshot_maps_preparing_and_existing_machine_states(self):
        cases = (
            (self.snapshot(RoundState.READY), MarkerState.STANDBY),
            (self.snapshot(RoundState.PREPARING), MarkerState.PREPARING),
            (self.snapshot(RoundState.RUNNING), MarkerState.MONITORING),
            (self.snapshot(RoundState.AWAITING_REVIEW), MarkerState.REVIEW),
            (self.snapshot(RoundState.COMPLETED, available=True,
                           collection_stopped=True), MarkerState.COMPLETE),
            (self.snapshot(RoundState.COMPLETED, available=False,
                           collection_stopped=True), MarkerState.STANDBY),
            (self.snapshot(RoundState.STOPPED, available=True, completion_reason="manual_stop",
                           collection_stopped=True), MarkerState.MANUAL_STOP_COMPLETE),
            (self.snapshot(RoundState.STOPPED, completion_reason="start_failed",
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

    def test_pending_confirmation_cannot_be_hidden_by_a_released_snapshot(self):
        snapshot = self.snapshot(
            RoundState.COMPLETED, available=True, conflicts=(object(),),
            collection_stopped=True,
        )
        self.assertEqual(state_for_round_snapshot(snapshot), MarkerState.REVIEW)

    def test_locally_cancellable_round_remains_in_review_until_operator_cancels(self):
        snapshot = self.snapshot(
            RoundState.COMPLETED, available=True, collection_stopped=True,
            completion_reason="round_deadline", cancel_available=True,
        )
        self.assertEqual(state_for_round_snapshot(snapshot), MarkerState.REVIEW)

    def test_six_fixed_black_white_patterns_are_unique_and_decodable(self):
        self.assertEqual(CONTRACT_VERSION, "1.3")
        self.assertEqual(len(set(MARKER_PATTERNS.values())), 6)
        self.assertEqual(MARKER_SIZE, 26)
        self.assertEqual(MARKER_PATTERNS[MarkerState.PREPARING],
                         ((False, True), (False, True)))
        self.assertEqual(MARKER_PATTERNS[MarkerState.MANUAL_STOP_COMPLETE],
                         ((False, False), (True, True)))
        for state, pattern in MARKER_PATTERNS.items():
            samples = tuple(0 if bit else 255 for row in pattern for bit in row)
            with self.subTest(state=state):
                self.assertEqual(classify_kvm_frame_samples((255, 0, 0, 255), samples), state)

    def test_independent_heartbeat_contract_covers_all_binary_states_in_order(self):
        expected = (
            ((False, False), (False, False)),
            ((False, False), (False, True)),
            ((False, False), (True, False)),
            ((False, False), (True, True)),
            ((False, True), (False, False)),
            ((False, True), (False, True)),
            ((False, True), (True, False)),
            ((False, True), (True, True)),
            ((True, False), (False, False)),
            ((True, False), (False, True)),
            ((True, False), (True, False)),
            ((True, False), (True, True)),
            ((True, True), (False, False)),
            ((True, True), (False, True)),
            ((True, True), (True, False)),
            ((True, True), (True, True)),
        )
        self.assertEqual(HEARTBEAT_PATTERNS, expected)
        self.assertEqual(len(set(HEARTBEAT_PATTERNS)), 16)
        self.assertTrue(all(len(row) == 2 for pattern in HEARTBEAT_PATTERNS for row in pattern))

    def test_state_and_heartbeat_markers_are_adjacent_without_moving_locators_or_results(self):
        self.assertEqual(STATE_MARKER_ORIGIN, (250, 0))
        self.assertEqual(HEARTBEAT_MARKER_ORIGIN, (278, 0))
        self.assertEqual(HEARTBEAT_MARKER_ORIGIN[0] -
                         (STATE_MARKER_ORIGIN[0] + MARKER_SIZE), 2)
        self.assertLess(HEARTBEAT_MARKER_ORIGIN[0] + MARKER_SIZE, LOCATOR_RIGHT[0])
        self.assertEqual(LOCATOR_LEFT, (0, 2))
        self.assertEqual(LOCATOR_RIGHT, (320, 2))
        self.assertEqual(KVM_FIRST_ROW_Y, 34)

    def test_low_contrast_missing_or_unknown_marker_is_not_recognized(self):
        self.assertIsNone(classify_kvm_frame_samples((255, 0, 0, 255), (110, 145, 130, 120)))
        self.assertIsNone(classify_kvm_frame_samples((255, 0, 0, 255), (0, 0, 0, 0)))
        self.assertIsNone(classify_kvm_frame_samples((255, 0, 0, 255), (0, 0, 255)))
        self.assertIsNone(classify_kvm_frame_samples((255, 0, 0, 255), (20, 20, 20, 20)))

    def test_wrong_or_unknown_locator_orientation_never_classifies_a_marker(self):
        complete = (255, 0, 0, 255)
        self.assertIsNone(classify_kvm_frame_samples((0, 255, 255, 0), complete))
        self.assertIsNone(classify_kvm_frame_samples((255, 0, 110, 255), complete))
        self.assertIsNone(classify_kvm_frame_samples((255, 0, 0), complete))

    def test_locator_and_two_row_geometry_keep_marker_separate_from_result_cells(self):
        self.assertEqual(LOCATOR_SIZE, 22)
        self.assertEqual(LOCATOR_LEFT, (0, 2))
        self.assertEqual(LOCATOR_RIGHT, (320, 2))
        self.assertEqual(LOCATOR_RIGHT[0] - LOCATOR_LEFT[0], 320)
        self.assertEqual(LOCATOR_RIGHT[0] + LOCATOR_SIZE - LOCATOR_LEFT[0], 342)
        self.assertEqual(LOCATOR_WHITE_SIZE, 8)
        self.assertGreater(KVM_FIRST_ROW_Y, MARKER_SIZE)
        self.assertEqual(KVM_ROW_STEP, 27)
        self.assertEqual(KVM_CELL_STEP, KVM_CELL_WIDTH)
        self.assertEqual(KVM_COLUMN_COUNT, 10)

    def test_formal_contract_document_matches_the_shipped_1_3_display_contract(self):
        contract = (Path(__file__).resolve().parents[1] / "docs" / "refactoring" /
                    "KVM_DISPLAY_CONTRACT.md").read_text(encoding="utf-8")
        self.assertIn("# KVM display contract 1.3", contract)
        self.assertIn("(0, 2)", contract)
        self.assertIn("(320, 2)", contract)
        self.assertIn("(250, 0)", contract)
        self.assertIn("(278, 0)", contract)
        self.assertIn("(130, 2)", contract)
        for text in ("(6, 29)", "(17, 29)", "(28, 29)", "232",
                     "locator_orientation_or_contrast_invalid"):
            self.assertIn(text, contract)

    def test_ls7_machine_readable_handoff_matches_app_contract_constants(self):
        path = (Path(__file__).resolve().parents[1] / "docs" / "refactoring" /
                "evidence" / "ls7-kvm" / "contract.json")
        contract = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(contract["contract_version"], CONTRACT_VERSION)
        self.assertEqual(tuple(contract["markers"]["state"]["origin"]),
                         STATE_MARKER_ORIGIN)
        self.assertEqual(tuple(contract["markers"]["heartbeat"]["origin"]),
                         HEARTBEAT_MARKER_ORIGIN)
        self.assertEqual(contract["markers"]["heartbeat"]["interval_ms"], 500)
        self.assertEqual(tuple(contract["locators"]["left_origin"]), LOCATOR_LEFT)
        self.assertEqual(tuple(contract["locators"]["right_origin"]), LOCATOR_RIGHT)
        self.assertEqual(tuple(contract["row_rail"]["origin"]), LAYOUT_MARKER_ORIGIN)
        self.assertEqual(tuple(contract["result_strip"]["first_cell_origin"]),
                         (0, KVM_FIRST_ROW_Y))
        self.assertEqual(contract["result_strip"]["cell_size"],
                         [KVM_CELL_WIDTH, KVM_CELL_HEIGHT])
        self.assertEqual(contract["sampling_handoff"]["expected_heartbeat_delta_per_sample"], 2)
        self.assertTrue(contract["remote_measurement"][
            "local_pixel_scale_must_not_be_used_as_remote_scale"])
        self.assertNotIn("KVM RESULT", contract)
        self.assertIn("MANUAL_STOP_COMPLETE",
                      contract["markers"]["state"]["state_names"])

    def test_handoff_labels_local_monitoring_and_external_activity_owners(self):
        handoff = (Path(__file__).resolve().parents[2] / "docs" / "refactoring" /
                   "KVM_DISPLAY_CONTRACT_1.2_HANDOFF.md").read_text(encoding="utf-8")
        self.assertIn("monitor_start", handoff)
        self.assertIn("KVM_Log", handoff)
        self.assertIn("Log Solution 不新增 TCP", handoff)
        self.assertNotIn("新左定位點的精確幾何仍未定", handoff)

    def test_li8_story_matrix_covers_every_story_once_with_ticket_and_evidence(self):
        matrix = (Path(__file__).resolve().parents[2] / "docs" / "refactoring" /
                  "log-instrument-tickets" / "LI8_STORY_EVIDENCE_MATRIX.md").read_text(
                      encoding="utf-8")
        rows = [line for line in matrix.splitlines()
                if line.startswith("|") and line.count("|") == 5
                and line.split("|")[1].strip().isdigit()]
        story_ids = [int(line.split("|")[1].strip()) for line in rows]
        self.assertEqual(story_ids, list(range(1, 89)))
        self.assertTrue(all(line.split("|")[2].strip().startswith("LI") and
                            line.split("|")[4].strip() for line in rows))


if __name__ == "__main__":
    unittest.main()
