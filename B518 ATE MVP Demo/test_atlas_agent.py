import base64
import csv
import os
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import atlas_agent as atlas_agent_module
from bump_build_version import bump_version
from bump_hid_calibration_version import bump_version as bump_hid_calibration_version
from b482_demo_server import Simulator
from atlas_agent import AgentError, AtlasAgentApp, BtAutoLogMonitor, DfuHmiNotReadyError, FctAutoLogMonitor, FolderMonitor, MatchTraceRecorder, Preferences, ScreenshotPreviewGuard, SerialLineFramer, SerialLink, TestCommand, VISUAL_PROFILES, absolute_click_commands, absolute_hid_report_coordinate, activate_atlas_window, active_log_progress, arduino_info_reply, arduino_ip_reply, arduino_protocol_warning, batch_result_report, bounded_template_preview_size, bt_result_directories, checkbox_state_evidence_in_region, click_commands, cv2, delete_screenshots, demo_slot_assignments, dfu_enter_each_ok_once_commands, dfu7_checkbox_search_regions, dfu7_slot_anchor_order, dfu_ok_each_commands, dfu_tab_slot_commands, discover_bt_csv_results, fct_record_candidates, fct_result_row_sort_key, focused_template_capture_message, hid_coordinate, hid_success_reply, hide_visible_atlas_windows, incoming_barcode_payload, latest_screenshot, locate_records, nearest_timestamp_folder, new_screenshots, next_dfu_demo_slot_index, opencv_image_to_tk_png, parse_barcodes, parse_bt_result_csv, parse_records, parse_test_command, parse_timestamp_folder, png_retina_scale, preview_geometry, resolve_fct_monitor_roots, resolve_template_path, restore_atlas_windows, screenshot_scale_for_displays, should_send_start_failed_nack, slot_checkbox_states, template_center, template_match, template_matches, visual_control_search_region, wait_for_new_stable_screenshots, window_focus_commands, write_local_demo_results, write_match_overlay
from hid_calibration import (SCREENSHOT_COMMAND, delta_command, direction_delta,
                             expected_success_reply, keyboard_write_command,
                             is_hid_progress_reply, is_nonfatal_cdc_diagnostic, normalize_cdc_line,
                             parse_delay_seconds, parse_firmware_info, parse_step)


class AtlasAgentTests(unittest.TestCase):
    def test_directory_chooser_does_not_enter_raw_appkit_modal_loop(self):
        """Tk must own the modal loop; raw NSOpenPanel crashes old macOS."""
        class FakeOpenPanel:
            calls = 0

            @classmethod
            def openPanel(cls):
                cls.calls += 1
                raise AssertionError("raw AppKit modal dialog must not be opened")

        original_appkit = atlas_agent_module.AppKit
        original_askdirectory = atlas_agent_module.filedialog.askdirectory
        captured = {}
        parent = object()
        atlas_agent_module.AppKit = type(
            "FakeAppKit", (), {"NSOpenPanel": FakeOpenPanel}
        )
        atlas_agent_module.filedialog.askdirectory = (
            lambda **options: captured.update(options) or "/vault/B482_RFTEST/TestData"
        )
        try:
            with tempfile.TemporaryDirectory() as initial:
                selected = atlas_agent_module.choose_directory_showing_hidden(
                    initial, parent
                )
                selected_initial = captured["initialdir"]
        finally:
            atlas_agent_module.AppKit = original_appkit
            atlas_agent_module.filedialog.askdirectory = original_askdirectory

        self.assertEqual(FakeOpenPanel.calls, 0)
        self.assertEqual(selected, "/vault/B482_RFTEST/TestData")
        self.assertIs(captured["parent"], parent)
        self.assertEqual(selected_initial, initial)
        self.assertTrue(captured["mustexist"])
        self.assertIn("Command + Shift + .", captured["title"])

    def test_dfu7_requires_exactly_seven_lower_slot_labels(self):
        anchors = [(index * 100, 300, 50, 20, .95) for index in range(6)]
        with self.assertRaises(DfuHmiNotReadyError) as raised:
            dfu7_slot_anchor_order(anchors, 100)
        self.assertEqual(raised.exception.slot_count, 6)
        self.assertIn("DFU_HMI_NOT_READY", str(raised.exception))

    def test_match_trace_keeps_failure_source_before_cleanup(self):
        if cv2 is None:
            self.skipTest("OpenCV unavailable")
        import numpy as np
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "capture.png"
            self.assertTrue(cv2.imwrite(str(source), np.zeros((20, 30, 3), dtype=np.uint8)))
            recorder = MatchTraceRecorder(root / "sessions", limit=1)
            session = recorder.start("DEMO-1")
            recorder.record("window_match", source, success=False, message="not found")
            entry = recorder.read_entries(session)[0]
            self.assertFalse(entry["success"])
            self.assertTrue((session / entry["source"]).is_file())
            self.assertTrue((session / entry["overlay"]).is_file())

    def test_screenshot_preview_guard_is_noop_off_macos(self):
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "restore.json"
            guard = ScreenshotPreviewGuard(marker, platform="linux")
            self.assertIsNone(guard.disable_for_session())
            self.assertFalse(marker.exists())
            self.assertIsNone(guard.restore())

    def test_focused_template_capture_instruction_requires_manual_hmi_focus(self):
        message = focused_template_capture_message(5)
        self.assertIn("5 秒", message)
        self.assertIn("手動點擊測試 HMI", message)
        self.assertIn("標題列或空白安全區", message)
        self.assertIn("請勿點擊 checkbox", message)

    def test_template_capture_hides_only_visible_atlas_windows_and_restores_order(self):
        class FakeWindow:
            def __init__(self, name, state="normal", visible=True, top_level=False):
                self.name, self._state, self.visible, self.top_level = name, state, visible, top_level
                self.withdrawn = self.deiconified = self.lifted = 0
            def winfo_class(self): return "Toplevel" if self.top_level else "Frame"
            def state(self, value=None):
                if value is not None: self._state = value
                return self._state
            def winfo_viewable(self): return self.visible
            def winfo_exists(self): return True
            def withdraw(self): self.withdrawn += 1; self._state = "withdrawn"; self.visible = False
            def deiconify(self): self.deiconified += 1; self._state = "normal"; self.visible = True
            def lift(self): self.lifted += 1

        root = FakeWindow("root")
        settings = FakeWindow("settings", top_level=True)
        maker = FakeWindow("maker", state="zoomed", top_level=True)
        minimized = FakeWindow("minimized", state="iconic", visible=False, top_level=True)
        hidden = FakeWindow("hidden", state="withdrawn", visible=False, top_level=True)
        ordinary_child = FakeWindow("frame")
        root.winfo_children = lambda: [settings, maker, minimized, hidden, ordinary_child]

        saved = hide_visible_atlas_windows(root)
        self.assertEqual([window.name for window, _ in saved], ["root", "settings", "maker"])
        self.assertEqual(minimized.withdrawn, 0)
        self.assertEqual(hidden.withdrawn, 0)
        restore_atlas_windows(saved)
        self.assertEqual((root.deiconified, settings.deiconified, maker.deiconified), (1, 1, 1))
        self.assertEqual(maker.state(), "zoomed")
        self.assertEqual((root.lifted, settings.lifted, maker.lifted), (1, 1, 1))

    def test_activate_atlas_window_restores_foreground_and_modal_grab(self):
        class FakeWindow:
            def __init__(self):
                self.calls = []
            def winfo_exists(self): return True
            def deiconify(self): self.calls.append("deiconify")
            def lift(self): self.calls.append("lift")
            def focus_force(self): self.calls.append("focus")
            def grab_set(self): self.calls.append("grab")

        window = FakeWindow()
        activate_atlas_window(window, modal=True)
        self.assertEqual(window.calls, ["deiconify", "lift", "focus", "grab"])

    def test_dfu_seven_slot_hmi_has_compact_mode_and_preserves_input_controls(self):
        hmi = Path(__file__).with_name("b482_demo_hmi.html").read_text(encoding="utf-8")
        self.assertIn("body.dfu-seven-mode .top", hmi)
        self.assertIn("#dfu.dfu-seven .cards", hmi)
        self.assertIn("function updateDfuCompactMode()", hmi)
        self.assertIn('id="snInput"', hmi)
        self.assertIn("OK（開始測試）", hmi)

    def test_build_version_bumps_patch_without_touching_other_values(self):
        updated, version = bump_version('VERSION = "3.14.15"\n')
        self.assertEqual(version, "3.14.16")
        self.assertEqual(updated, 'VERSION = "3.14.16"\n')

    def test_hid_calibration_build_version_has_an_independent_patch_counter(self):
        updated, version = bump_hid_calibration_version('VERSION = "0.1.9"\n')
        self.assertEqual(version, "0.1.10")
        self.assertEqual(updated, 'VERSION = "0.1.10"\n')

    def test_barcodes(self):
        self.assertEqual(parse_barcodes("DATA:A, B,C"), ["A", "B", "C"])
        with self.assertRaises(Exception): parse_barcodes("A,B,C,D,E")

    def test_demo_slot_assignments_supports_sparse_dfu_seven_and_fct_six(self):
        self.assertEqual(demo_slot_assignments("DFU", ["SN001", "", "SN003", "", "", "", "SN007"]),
                         ((1, "SN001"), (3, "SN003"), (7, "SN007")))
        self.assertEqual(demo_slot_assignments("FCT", ["SN001", "", "", "SN004", "", "SN006"]),
                         ((1, "SN001"), (4, "SN004"), (6, "SN006")))
        with self.assertRaises(AgentError):
            demo_slot_assignments("FCT", ["SN001"] * 7)
        with self.assertRaises(AgentError):
            demo_slot_assignments("DFU", ["SN001"] * 7)

    def test_dfu_demo_scanner_return_advances_and_wraps_slots(self):
        self.assertEqual([next_dfu_demo_slot_index(index) for index in range(7)],
                         [1, 2, 3, 4, 5, 6, 0])
        with self.assertRaises(ValueError):
            next_dfu_demo_slot_index(7)

    def test_dfu7_controls_search_full_screenshot_when_window_is_only_an_anchor(self):
        anchor = (100, 50, 111, 58)
        self.assertIsNone(visual_control_search_region("DFU", VISUAL_PROFILES["b482_dfu2_7slot"], anchor, False))
        self.assertEqual(visual_control_search_region("DFU", VISUAL_PROFILES["b482_dfu2"], anchor, True),
                         (100, 50, 1011, 600))

    def test_dfu_demo_accepts_slots_five_through_seven_only_for_demo_job(self):
        class Value:
            def __init__(self, value): self.value = value
            def get(self): return self.value

        with tempfile.TemporaryDirectory() as directory:
            app = object.__new__(AtlasAgentApp)
            app.csv_path, app.station = Value(directory), Value("DFU")
            command = TestCommand("DFU", "DEMO-20260806-120000", ((1, "SN001"), (7, "SN007")))
            self.assertEqual(AtlasAgentApp.validate_command(app, command)[1], command)
            with self.assertRaises(AgentError):
                AtlasAgentApp.validate_command(app, TestCommand("DFU", "JOB-1", command.assignments))

    def test_html_simulator_accepts_seven_dfu_sns_but_not_fct(self):
        with tempfile.TemporaryDirectory() as directory:
            simulator = Simulator(Path(directory), duration_seconds=.01)
            seven = [f"SN{i}" for i in range(1, 8)]
            self.assertEqual(simulator._assignments("DFU", {"sns": seven}), list(enumerate(seven, start=1)))
            with self.assertRaises(ValueError):
                simulator._assignments("FCT", {"sns": seven})

    def test_fct_jobs_always_start_monitor_without_visual_or_checkbox_work(self):
        for job_id, assignments in (
                ("JOB-1", ((1, "SN001"), (3, "SN003"), (4, "SN004"))),
                ("DEMO-20260806-120000", tuple((slot, f"SN{slot:03d}") for slot in range(1, 7)))):
            app = object.__new__(AtlasAgentApp)
            calls, logs = [], []
            app.start_monitor = lambda *args: calls.append(args)
            app.start_visual_worker = lambda *args: self.fail("FCT must not start visual/HID work")
            app.append = logs.append
            command = TestCommand("FCT", job_id, assignments)
            prepared = (Path("/tmp/fct"), command, 9, 123.0, 300.0)
            self.assertEqual(AtlasAgentApp.start_prepared(app, prepared), command.sns)
            self.assertEqual(calls, [(Path("/tmp/fct"), command.sns, 9, 123.0, 300.0)])
            self.assertIn("FCT 由儀器自動偵測 slot；Agent 已直接開始監聽。", logs)

    def test_transparent_tcp_barcode_payload_is_accepted_without_control_replies(self):
        self.assertEqual(incoming_barcode_payload("SN1,SN2"), "SN1,SN2")
        self.assertEqual(incoming_barcode_payload("DATA:SN1,SN2"), "DATA:SN1,SN2")
        self.assertIsNone(incoming_barcode_payload("OK:SCREENSHOT"))
        self.assertIsNone(incoming_barcode_payload("IP:192.168.1.100"))

    def test_serial_framer_waits_for_complete_line_across_stream_fragments(self):
        framer = SerialLineFramer()
        self.assertEqual(framer.feed(b"SN001,S"), [])
        self.assertEqual(framer.feed(b"N002\r\nOK:SCREEN"), ["SN001,SN002"])
        self.assertEqual(framer.feed(b"SHOT\n"), ["OK:SCREENSHOT"])

    def test_serial_framer_discards_only_cdc_boundary_noise(self):
        framer = SerialLineFramer()
        self.assertEqual(framer.feed(b"\x00\r\nOK:M_RESET\x00\r\n"), ["OK:M_RESET"])
        self.assertEqual(framer.feed(b"  RESULT:SN001,PASS  \r\n"), ["  RESULT:SN001,PASS  "])

    def test_agent_separates_usb_control_lf_from_tcp_payload_crlf(self):
        class FakeSerial:
            def __init__(self): self.written = b""; self.input_resets = 0; self.output_resets = 0
            def write(self, payload): self.written += payload
            def flush(self): pass
            def reset_input_buffer(self): self.input_resets += 1
            def reset_output_buffer(self): self.output_resets += 1
        link = SerialLink(lambda _: None)
        link.connection = FakeSerial()
        link.send_control("M_RESET\r\n")
        link.send_tcp_payload("RESULT:SN001,PASS,ok\n")
        self.assertEqual(link.connection.written, b"M_RESET\nRESULT:SN001,PASS,ok\r\n")
        self.assertEqual((link.connection.input_resets, link.connection.output_resets), (0, 0))

    def test_calibration_normalizes_framing_and_ignores_only_tcp_bridge_diagnostic(self):
        self.assertEqual(normalize_cdc_line("\x00\r\nOK:M_RESET\r\n"), "OK:M_RESET")
        self.assertEqual(normalize_cdc_line("  RESULT:SN001,PASS  \r\n"), "  RESULT:SN001,PASS  ")
        self.assertTrue(is_nonfatal_cdc_diagnostic("ERR:TCP_NOT_CONNECTED"))
        self.assertFalse(is_nonfatal_cdc_diagnostic("ERR:M_DELTA_FORMAT"))
        self.assertTrue(is_hid_progress_reply("M_RESET", "ACK:M_RESET"))
        self.assertTrue(is_hid_progress_reply("M_DELTA:0,5", "ACK:M_DELTA"))
        self.assertTrue(is_hid_progress_reply("SCREENSHOT", "ACK:SCREENSHOT"))
        self.assertFalse(is_hid_progress_reply("M_RESET", "OK:M_RESET"))

    def test_arduino_network_replies_update_the_same_ip_display(self):
        self.assertEqual(arduino_ip_reply("IP:192.168.1.100"), "192.168.1.100")
        self.assertEqual(arduino_ip_reply("OK:NET_SET:192.168.1.101"), "192.168.1.101")
        self.assertEqual(arduino_ip_reply("EVT: IP=192.168.1.102"), "192.168.1.102")
        self.assertIsNone(arduino_ip_reply("OK:NET_SET:999.1.1.1"))

    def test_arduino_info_reply_parses_identity_without_becoming_job_data(self):
        identity = arduino_info_reply("INFO:PRODUCT=B518_ARDUINO_MVP;FW=1.0.0;PROTO=1;BOARD=UNO_R4_MINIMA")
        self.assertIsNotNone(identity)
        self.assertEqual(identity.firmware_version, "1.0.0")
        self.assertEqual(identity.protocol_version, 1)
        self.assertEqual(identity.board, "UNO_R4_MINIMA")
        self.assertIsNone(incoming_barcode_payload("INFO:PRODUCT=B518_ARDUINO_MVP;FW=1.0.0;PROTO=1;BOARD=UNO_R4_MINIMA"))

    def test_arduino_info_reply_rejects_missing_or_invalid_fields(self):
        self.assertIsNone(arduino_info_reply("INFO:PRODUCT=B518_ARDUINO_MVP;FW=1.0;PROTO=1;BOARD=UNO_R4_MINIMA"))
        self.assertIsNone(arduino_info_reply("INFO:PRODUCT=B518_ARDUINO_MVP;FW=1.0.0;PROTO=x;BOARD=UNO_R4_MINIMA"))
        self.assertIsNone(arduino_info_reply("INFO:PRODUCT=B518_ARDUINO_MVP;FW=1.0.0;PROTO=1"))
        self.assertIsNone(arduino_info_reply("IP:192.168.1.100"))

    def test_arduino_protocol_mismatch_only_produces_a_warning(self):
        current = arduino_info_reply("INFO:PRODUCT=B518_ARDUINO_MVP;FW=1.0.0;PROTO=1;BOARD=UNO_R4_WIFI")
        old = arduino_info_reply("INFO:PRODUCT=B518_ARDUINO_MVP;FW=0.9.9;PROTO=0;BOARD=UNO_R4_MINIMA")
        self.assertIsNone(arduino_protocol_warning(current))
        self.assertIn("將繼續執行測試", arduino_protocol_warning(old))

    def test_dfu_each_sn_returns_to_origin_before_input_and_ok(self):
        self.assertEqual(
            dfu_ok_each_commands(["SN001", "SN002"], (100, 200), (300, 400)),
            ["M_RESET", "M_MOVE:100,200", "M_CLICK:L", "K_WRITE:SN001", "M_RESET", "M_MOVE:300,400", "M_CLICK:L",
             "M_RESET", "M_MOVE:100,200", "M_CLICK:L", "K_WRITE:SN002", "M_RESET", "M_MOVE:300,400", "M_CLICK:L"])

    def test_dfu7_enters_each_sn_then_clicks_ok_once(self):
        self.assertEqual(
            dfu_enter_each_ok_once_commands(["SN001", "SN003", "SN007"], (100, 200), (300, 400)),
            ["M_RESET", "M_MOVE:100,200", "M_CLICK:L", "K_TYPE:SN001",
             "M_RESET", "M_MOVE:100,200", "M_CLICK:L", "K_TYPE:SN003",
             "M_RESET", "M_MOVE:100,200", "M_CLICK:L", "K_TYPE:SN007",
             "M_RESET", "M_MOVE:300,400", "M_CLICK:L"])

    def test_demo_start_failed_does_not_send_nack(self):
        self.assertFalse(should_send_start_failed_nack("DEMO-20260806-120000", True))
        self.assertTrue(should_send_start_failed_nack("20260806-001", True))
        self.assertFalse(should_send_start_failed_nack("20260806-001", False))

    def test_dfu7_slot_anchor_order_requires_four_then_three_lower_labels(self):
        anchors = [(10, 100, 20, 10, .9), (100, 100, 20, 10, .9), (200, 100, 20, 10, .9),
                   (300, 100, 20, 10, .9), (10, 180, 20, 10, .9), (100, 180, 20, 10, .9),
                   (200, 180, 20, 10, .9), (10, 20, 20, 10, .9)]
        self.assertEqual(dfu7_slot_anchor_order(anchors, 50),
                         [(10, 100, 20, 10), (100, 100, 20, 10), (200, 100, 20, 10),
                          (300, 100, 20, 10), (10, 180, 20, 10), (100, 180, 20, 10),
                          (200, 180, 20, 10)])

    def test_dfu7_checkbox_regions_extend_to_card_right_edge_without_crossing_next_label(self):
        anchors = [(10, 100, 20, 10), (110, 100, 20, 10), (210, 100, 20, 10),
                   (310, 100, 20, 10), (10, 180, 20, 10), (110, 180, 20, 10),
                   (210, 180, 20, 10)]
        regions = dfu7_checkbox_search_regions(anchors)
        self.assertEqual(regions[0], (30, 90, 80, 40))
        self.assertEqual(regions[3], (330, 90, 80, 40))
        self.assertEqual(regions[6], (230, 170, 80, 40))

    def test_generic_dfu_tabs_over_unpopulated_slots(self):
        self.assertEqual(dfu_tab_slot_commands([(1, "SN001"), (3, "SN003"), (4, "SN004")]),
                         ["K_WRITE:SN001", "K_KEY:TAB", "K_KEY:TAB", "K_WRITE:SN003",
                          "K_KEY:TAB", "K_WRITE:SN004"])

    def test_absolute_click_returns_to_origin_before_relative_hid_move(self):
        self.assertEqual(absolute_click_commands((80, 55)), ["M_RESET", "M_MOVE:80,55", "M_CLICK:L"])

    def test_absolute_hid_mode_uses_raw_absolute_report_without_mouse_reset(self):
        self.assertEqual(absolute_hid_report_coordinate((0, 0), 1440, 900), (0, 0))
        self.assertEqual(absolute_hid_report_coordinate((1439, 899), 1440, 900), (32767, 32767))
        self.assertEqual(click_commands((4915, 22632), "absolute"),
                         ["M_ABS:4915,22632", "M_CLICK:L"])
        self.assertEqual(window_focus_commands((500, 300)),
                         ["M_RESET", "M_MOVE:500,300", "M_CLICK:L"])
        self.assertEqual(window_focus_commands((500, 300), (11385, 10934), "absolute"),
                         ["M_ABS:11385,10934", "M_DELTA:1,0", "M_DELTA:-1,0", "M_CLICK:L"])
        with self.assertRaises(AgentError):
            window_focus_commands((500, 300), mode="absolute")
        self.assertEqual(dfu_ok_each_commands(["SN1"], (10, 20), (30, 40), "absolute"),
                         ["M_ABS:10,20", "M_CLICK:L", "K_WRITE:SN1",
                          "M_ABS:30,40", "M_CLICK:L"])
        with self.assertRaises(AgentError):
            absolute_hid_report_coordinate((1440, 0), 1440, 900)

    def test_hid_command_completion_replies(self):
        self.assertEqual(hid_success_reply("M_RESET"), "OK:M_RESET")
        self.assertEqual(hid_success_reply("M_MOVE:100,200"), "OK:M_MOVE")
        self.assertEqual(hid_success_reply("M_CLICK:L"), "OK:M_CLICK:L")
        self.assertEqual(hid_success_reply("K_WRITE:SN001"), "OK:K_WRITE")
        self.assertEqual(hid_success_reply("M_ABS_CLICK:L"), "OK:M_ABS_CLICK:L")

    def test_hid_coordinate_supports_retina_scale_and_monitor_offset(self):
        self.assertEqual(hid_coordinate((1440, 900), .5, .5), (720, 450))
        self.assertEqual(hid_coordinate((100, 200), 1, 1, 1440, 0), (1540, 200))
        with self.assertRaises(AgentError):
            hid_coordinate((1, 1), 0, 1)

    def test_auto_scale_uses_matching_retina_display_pixel_dimensions(self):
        displays = [(1440, 900, 2.0), (1920, 1080, 1.0)]
        self.assertEqual(screenshot_scale_for_displays((2880, 1800), displays), (.5, .5))
        self.assertEqual(screenshot_scale_for_displays((1920, 1080), displays), (1.0, 1.0))
        self.assertIsNone(screenshot_scale_for_displays((1000, 1000), displays))

    def test_png_retina_scale_reads_macos_phys_dpi_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "retina.png"
            # Signature + pHYs (5669 pixels/meter is approximately 144 DPI).
            payload = (5669).to_bytes(4, "big") + (5669).to_bytes(4, "big") + b"\x01"
            image.write_bytes(b"\x89PNG\r\n\x1a\n" + len(payload).to_bytes(4, "big") + b"pHYs" + payload + b"\0\0\0\0")
            scale_x, scale_y = png_retina_scale(image)
            self.assertAlmostEqual(scale_x, .5, places=3)
            self.assertAlmostEqual(scale_y, .5, places=3)

    def test_calibration_arrow_keys_generate_signed_relative_hid_delta(self):
        self.assertEqual(parse_step("5"), 5)
        self.assertEqual(delta_command("Right", 5), "M_DELTA:5,0")
        self.assertEqual(delta_command("Left", 5), "M_DELTA:-5,0")
        self.assertEqual(delta_command("Up", 5), "M_DELTA:0,-5")
        self.assertEqual(delta_command("Down", 5), "M_DELTA:0,5")
        self.assertEqual(direction_delta("Left", 5), (-5, 0))
        with self.assertRaises(ValueError):
            parse_step("0")

    def test_calibration_screenshot_uses_agent_protocol_command(self):
        self.assertEqual(SCREENSHOT_COMMAND, "SCREENSHOT")

    def test_calibration_delayed_keyboard_write_validates_protocol_payload(self):
        self.assertEqual(keyboard_write_command("Test 123"), "K_WRITE:Test 123")
        self.assertEqual(parse_delay_seconds("0.5"), .5)
        with self.assertRaises(ValueError):
            keyboard_write_command("測試")
        with self.assertRaises(ValueError):
            keyboard_write_command("line1\nline2")
        with self.assertRaises(ValueError):
            parse_delay_seconds("120.5")

    def test_calibration_requires_canonical_firmware_identity(self):
        self.assertEqual(
            parse_firmware_info(
                "INFO:PRODUCT=B518_ARDUINO_MVP;FW=1.0.2;PROTO=1;BOARD=UNO_R4_MINIMA;FAULT=1;LAST=M_DELTA_FORMAT"),
            ("B518_ARDUINO_MVP", "1.0.2", 1, "UNO_R4_MINIMA"),
        )
        self.assertIsNone(parse_firmware_info("IP:192.168.1.100"))
        self.assertIsNone(parse_firmware_info("INFO:PRODUCT=B518_ARDUINO_MVP;FW=1.0;PROTO=1"))

    def test_calibration_knows_terminal_hid_success_replies(self):
        self.assertEqual(expected_success_reply("M_RESET"), "OK:M_RESET")
        self.assertEqual(expected_success_reply("M_DELTA:-5,0"), "OK:M_DELTA")
        self.assertEqual(expected_success_reply("SCREENSHOT"), "OK:SCREENSHOT")
        self.assertEqual(expected_success_reply("K_WRITE:TEST"), "OK:K_WRITE")
        self.assertEqual(expected_success_reply("UNKNOWN"), "")

    @unittest.skipIf(cv2 is None, "OpenCV is not installed")
    def test_match_overlay_is_saved_with_match_annotations(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, overlay = root / "source.png", root / "overlay.png"
            cv2.imwrite(str(source), np.zeros((60, 80, 3), dtype=np.uint8))
            self.assertEqual(write_match_overlay(source, [("OK", (10, 20, 20, 10), (20, 25))], overlay), overlay)
            self.assertTrue(overlay.is_file())

    def test_root_level_template_is_compatible_with_b482_subfolder_name(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            root.joinpath("dfu2_window.png").touch()
            self.assertEqual(resolve_template_path(root, "b482/dfu2_window.png"), root / "dfu2_window.png")

    def test_batch_result_report_is_compact_and_preserves_sn_order(self):
        report = batch_result_report("BT", "20260722-001", [(1, "SN001"), (3, "SN003"), (4, "SN004")],
                                     {"SN004": "FAIL", "SN001": "PASS", "SN003": "PASS"})
        self.assertEqual(report, "RESULT:BT:JOB=20260722-001;1=SN001,PASS;3=SN003,PASS;4=SN004,FAIL")
        fct_report = batch_result_report(
            "FCT", "DEMO-20260731", [(1, "FCT001"), (4, "FCT004"), (6, "FCT006")],
            {"FCT001": "PASS", "FCT004": "PASS", "FCT006": "FAIL"})
        self.assertEqual(
            fct_report,
            "RESULT:FCT:JOB=DEMO-20260731;1=FCT001,PASS;4=FCT004,PASS;6=FCT006,FAIL")

    def test_station_job_command_preserves_sparse_slots(self):
        command = parse_test_command("FCT:JOB=20260722-001;1=SN001,3=SN003,4=SN004")
        self.assertEqual(command.station, "FCT")
        self.assertEqual(command.job_id, "20260722-001")
        self.assertEqual(command.slots, [1, 3, 4])
        self.assertEqual(command.sns, ["SN001", "SN003", "SN004"])
        with self.assertRaises(AgentError):
            parse_test_command("BT:JOB=X;1=SN001,1=SN002")
        with self.assertRaises(AgentError):
            parse_test_command("DFU:JOB=LIVE;1=SN001,2=SN002,3=SN003,4=SN004,5=SN005")

    @staticmethod
    def write_bt_result(root, thread, sn, status, started, *, unit=None, csv_status=None, folder_status=None):
        folder_status = folder_status or status
        directory = root / started.date().isoformat() / folder_status
        directory.mkdir(parents=True, exist_ok=True)
        filename = f"[Thread{thread}][B482_BT-COND][{sn}][{status}][{started:%Y%m%d%H%M%S}].csv"
        path = directory / filename
        with path.open("w", newline="", encoding="utf-8") as target:
            writer = csv.writer(target)
            writer.writerow(["SerialNumber", "Unit Number", "Test Pass/Fail Status", "StartTime", "EndTime"])
            writer.writerow([sn, thread if unit is None else unit, csv_status or status,
                             started.strftime("%Y/%m/%d %H:%M:%S"),
                             (started + timedelta(seconds=20)).strftime("%Y/%m/%d %H:%M:%S")])
        return path

    def test_bt_csv_monitor_discovers_four_sample_shaped_results_in_thread_order(self):
        started = datetime(2025, 8, 20, 18, 13, 38)
        sample_sns = ["HK5HKH3YJN000003YV", "HK5HKH3YJN300003YV", "HK5HKH3YJMY00003YV", "HK5HKH3YJN100003YV"]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for thread, sn in enumerate(sample_sns):
                self.write_bt_result(root, thread, sn, "PASSED", started)
            results, errors = discover_bt_csv_results(root, [1, 2, 3, 4], started)
            self.assertEqual(errors, [])
            self.assertEqual([(results[slot].sn, results[slot].status) for slot in (1, 2, 3, 4)],
                             list(zip(sample_sns, ["PASS"] * 4)))

    def test_bt_csv_monitor_handles_sparse_slots_and_failed_results(self):
        started = datetime(2026, 7, 30, 15, 0, 0)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_bt_result(root, 0, "SN001", "PASSED", started)
            self.write_bt_result(root, 2, "SN003", "FAILED", started)
            self.write_bt_result(root, 3, "SN004", "PASSED", started)
            results, errors = discover_bt_csv_results(root, [1, 3, 4], started)
            self.assertEqual(errors, [])
            self.assertEqual({slot: result.status for slot, result in results.items()}, {1: "PASS", 3: "FAIL", 4: "PASS"})

    def test_bt_csv_monitor_rejects_stale_and_inconsistent_files(self):
        started = datetime(2026, 7, 30, 15, 0, 10)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_bt_result(root, 0, "OLD", "PASSED", started - timedelta(seconds=3))
            invalid = self.write_bt_result(root, 1, "SN002", "PASSED", started, unit=3)
            results, errors = discover_bt_csv_results(root, [1, 2], started)
            self.assertEqual(results, {})
            self.assertIn((invalid, "Thread 與 CSV Unit Number 不一致"), errors)

    def test_bt_csv_monitor_searches_start_and_current_dates_for_midnight(self):
        started = datetime(2026, 7, 30, 23, 59, 59)
        next_day = started + timedelta(seconds=2)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_bt_result(root, 0, "SN001", "PASSED", next_day)
            directories = bt_result_directories(root, started, next_day)
            self.assertEqual(directories, [root / "2026-07-31" / "PASSED"])
            results, errors = discover_bt_csv_results(root, [1], started, next_day)
            self.assertEqual(errors, [])
            self.assertEqual(results[1].sn, "SN001")

    def test_fct_auto_log_demo_ignores_baseline_and_reports_latched_active_sn(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); active_root = root / "active"; final_root = root / "unit-archive"
            active_root.mkdir(); final_root.mkdir()
            stamp = datetime.now().strftime("%Y%m%d_%H-%M-%S.demo")
            old = final_root / "OLD" / stamp / "system"
            old.mkdir(parents=True)
            (old / "records.csv").write_text("case,status\na,PASS\n", encoding="utf-8")
            results, stop = [], threading.Event()
            monitor = FctAutoLogMonitor(final_root, active_root, time.time(), lambda _: None,
                                        results.append, stop, timeout_seconds=2)
            monitor.start()
            active = active_root / "group0-slot1" / "system"
            active.mkdir(parents=True)
            serial = "NEW00001"
            (active / "records.csv").write_text(f"MLB_SN,{serial}\n", encoding="utf-8")
            time.sleep(.6)
            current = final_root / serial / datetime.now().strftime("%Y%m%d_%H-%M-%S.demo") / "system"
            current.mkdir(parents=True)
            (current / "device.log").write_text("TEST COMPLETE\n", encoding="utf-8")
            (current / "records.csv").write_text("case,status\na,FAIL\n", encoding="utf-8")
            monitor.join(1.2); stop.set(); monitor.join(1)
            self.assertEqual([(item.sn, item.status) for item in results], [(serial, "FAIL")])

    def test_fct_active_records_reveal_barcode_without_using_timestamp_tokens(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            active = root / "active" / "group0-slot3" / "system"
            active.mkdir(parents=True)
            (active / "records.csv").write_text(
                "MLB_SN,HK5HUX6STQ800003YV\nPrimaryIdentity,HK5HUX6STQ800003YV\n", encoding="utf-8")
            log = active / "device.log"
            log.write_text("2026/07/28 slot_num: 2022\ncalling amIOK with sn HK5HUX6STQ800003YV\n", encoding="utf-8")
            sn, detail = active_log_progress(log, active.parent)
            self.assertEqual(sn, "HK5HUX6STQ800003YV")
            self.assertIn("等待", detail)

    def test_fct_active_log_does_not_treat_number_sof0_as_a_barcode(self):
        with tempfile.TemporaryDirectory() as directory:
            active = Path(directory) / "active" / "group0-slot6"
            active.mkdir(parents=True)
            log = active / "device.log"
            log.write_text("FCT active slot3: NUMBER_SOF0 COMPLETING - active\n", encoding="utf-8")
            sn, _ = active_log_progress(log, active)
            self.assertEqual(sn, "")

    def test_fct_monitor_roots_requires_explicit_active_and_final_selections(self):
        with tempfile.TemporaryDirectory() as directory:
            atlas = Path(directory) / "Logs" / "Atlas"
            active, unitest, archive = atlas / "active", atlas / "unitest", atlas / "unit-archive"
            active.mkdir(parents=True); unitest.mkdir(); archive.mkdir()
            roots = resolve_fct_monitor_roots(archive, active)
            self.assertEqual(roots.active_root, active)
            self.assertEqual(roots.final_root, archive)
            with self.assertRaisesRegex(AgentError, "直接選擇 active"):
                resolve_fct_monitor_roots(archive)
            with self.assertRaisesRegex(AgentError, "unit-archive"):
                resolve_fct_monitor_roots(atlas, active)

    def test_fct_latches_active_sn_when_records_are_cleared_before_final_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            atlas = Path(directory) / "Atlas"
            active_root, archive_root = atlas / "active", atlas / "unit-archive"
            active_system = active_root / "group0-slot2" / "system"
            active_root.mkdir(parents=True); archive_root.mkdir()
            serial = "HK5HUX6STQ800003YV"
            progress, results, completed, stop = [], [], threading.Event(), threading.Event()
            monitor = FctAutoLogMonitor(archive_root, active_root, time.time(), lambda _: None,
                                        results.append, stop, on_progress=progress.append,
                                        on_complete=completed.set, completion_settle_seconds=0)
            monitor.start()
            active_system.mkdir(parents=True)
            active_records = active_system / "records.csv"
            active_records.write_text(f"MLB_SN,{serial}\n", encoding="utf-8")
            # The monitor polls every 0.5 seconds; allow a full poll to latch
            # the barcode before reproducing Atlas' active-folder cleanup.
            time.sleep(.7)
            # The real instrument can clear active records while moving final
            # data.  The session must retain the earlier valid barcode.
            active_records.unlink()
            time.sleep(.35)
            final_system = archive_root / serial / datetime.now().strftime("%Y%m%d_%H-%M-%S.demo") / "system"
            final_system.mkdir(parents=True)
            # Actual FCT records include metadata rows with empty statuses.
            # Those rows must not keep a completed test at COMPLETING.
            (final_system / "records.csv").write_text(
                "attributeName,testName,status\nSwName,,\n,Fixture,PASS\n",
                encoding="utf-8")
            (active_system / "device.log").unlink(missing_ok=True)
            active_system.rmdir(); active_system.parent.rmdir()
            monitor.join(2); stop.set(); monitor.join(1)
            self.assertTrue(completed.is_set())
            self.assertIn((serial, "PASS"), [(item.sn, item.status) for item in results])
            slot2 = [(item.sn, item.status) for item in progress if item.slot == 2]
            self.assertIn((serial, "COMPLETING"), slot2)
            self.assertNotIn(("", "FAIL"), slot2)

    def test_fct_final_result_locks_slot_against_later_active_progress(self):
        """A late TESTING/COMPLETING update must not erase final PASS/FAIL."""
        with tempfile.TemporaryDirectory() as directory:
            atlas = Path(directory) / "Atlas"
            active_root, archive_root = atlas / "active", atlas / "unit-archive"
            active_system = active_root / "group0-slot1" / "system"
            active_root.mkdir(parents=True); archive_root.mkdir()
            serial = "HK5HUX6STQ800003YV"
            progress, results, stop = [], [], threading.Event()
            monitor = FctAutoLogMonitor(archive_root, active_root, time.time(), lambda _: None,
                                        results.append, stop, on_progress=progress.append)
            monitor.start()
            active_system.mkdir(parents=True)
            (active_system / "records.csv").write_text(f"MLB_SN,{serial}\n", encoding="utf-8")
            time.sleep(.7)
            final_system = archive_root / serial / datetime.now().strftime("%Y%m%d_%H-%M-%S.demo") / "system"
            final_system.mkdir(parents=True)
            (final_system / "records.csv").write_text("case,status\nRF,PASS\n", encoding="utf-8")
            time.sleep(.8)
            # Keep active alive and alter it after the archive is accepted.
            # A non-terminal update must no longer be emitted for slot1.
            (active_system / "device.log").write_text("StartTest: RF\n", encoding="utf-8")
            time.sleep(.7)
            stop.set(); monitor.join(1)
            self.assertEqual([(item.sn, item.status) for item in results], [(serial, "PASS")])
            self.assertIn(1, monitor.finalized_slots)
            self.assertEqual(
                [(item.status, item.sn) for item in progress if item.slot == 1][-1],
                ("TESTING", serial),
            )

    def test_fct_final_archive_accepts_new_timestamp_when_move_preserves_csv_mtime(self):
        """Atlas may preserve records.csv mtime when moving active data to unit-archive."""
        with tempfile.TemporaryDirectory() as directory:
            atlas = Path(directory) / "Atlas"
            active_root, archive_root = atlas / "active", atlas / "unit-archive"
            active_root.mkdir(parents=True); archive_root.mkdir()
            serial = "HK5HUX6STQ800003YV"
            results, completed, stop = [], threading.Event(), threading.Event()
            monitor = FctAutoLogMonitor(archive_root, active_root, time.time(), lambda _: None,
                                        results.append, stop, on_complete=completed.set,
                                        completion_settle_seconds=0)
            monitor.start()
            active_system = active_root / "group0-slot1" / "system"
            active_system.mkdir(parents=True)
            (active_system / "records.csv").write_text(f"MLB_SN,{serial}\n", encoding="utf-8")
            time.sleep(.7)
            final_system = archive_root / serial / datetime.now().strftime("%Y%m%d_%H-%M-%S.demo") / "system"
            final_system.mkdir(parents=True)
            final_records = final_system / "records.csv"
            final_records.write_text("case,status\nRF,PASS\n", encoding="utf-8")
            # Simulate a filesystem move which preserves an older file mtime.
            preserved_time = time.time() - 300
            os.utime(final_records, (preserved_time, preserved_time))
            (active_system / "records.csv").unlink()
            active_system.rmdir(); active_system.parent.rmdir()
            monitor.join(2); stop.set(); monitor.join(1)
            self.assertTrue(completed.is_set())
            self.assertEqual([(item.sn, item.status) for item in results], [(serial, "PASS")])

    def test_fct_archive_folder_timestamp_accepts_one_digit_hour_and_milliseconds(self):
        with tempfile.TemporaryDirectory() as directory:
            root, serial = Path(directory), "HK5HUX6STQ800003YV"
            for name, filename in (
                ("20220618_2-28-01.374-04426F", "records.csv"),
                ("20220618_02-28-02.005-any-station-id", "record.csv"),
            ):
                system = root / serial / name / "system"
                system.mkdir(parents=True)
                (system / filename).write_text("case,status\nRF,PASS\n", encoding="utf-8")
            candidates = fct_record_candidates(root, serial)
            self.assertEqual([item[0] for item in candidates], [
                datetime(2022, 6, 18, 2, 28, 1, 374000),
                datetime(2022, 6, 18, 2, 28, 2, 5000),
            ])
            self.assertEqual(parse_timestamp_folder("20220618_2-28-01.374-04426F"), candidates[0][0])

    def test_fct_archive_timestamp_grace_uses_folder_name_not_csv_mtime(self):
        with tempfile.TemporaryDirectory() as directory:
            atlas = Path(directory) / "Atlas"
            active_root, archive_root = atlas / "active", atlas / "unit-archive"
            active_root.mkdir(parents=True); archive_root.mkdir()
            serial = "HK5HUX6STQ800003YV"
            started = datetime(2022, 6, 18, 2, 28, 31).timestamp()
            results, completed, stop = [], threading.Event(), threading.Event()
            monitor = FctAutoLogMonitor(archive_root, active_root, started, lambda _: None,
                                        results.append, stop, on_complete=completed.set,
                                        completion_settle_seconds=0)
            monitor.start()
            active_system = active_root / "group0-slot1" / "system"
            active_system.mkdir(parents=True)
            (active_system / "records.csv").write_text(f"MLB_SN,{serial}\n", encoding="utf-8")
            time.sleep(.7)
            final_system = archive_root / serial / "20220618_2-28-01.374-04426F" / "system"
            final_system.mkdir(parents=True)
            final_records = final_system / "records.csv"
            final_records.write_text("case,status\nRF,PASS\n", encoding="utf-8")
            os.utime(final_records, (1, 1))
            (active_system / "records.csv").unlink(); active_system.rmdir(); active_system.parent.rmdir()
            monitor.join(2); stop.set(); monitor.join(1)
            self.assertTrue(completed.is_set())
            self.assertEqual([(item.sn, item.status) for item in results], [(serial, "PASS")])

    def test_fct_archive_rejects_folder_older_than_thirty_second_grace(self):
        with tempfile.TemporaryDirectory() as directory:
            atlas = Path(directory) / "Atlas"
            active_root, archive_root = atlas / "active", atlas / "unit-archive"
            active_root.mkdir(parents=True); archive_root.mkdir()
            serial = "HK5HUX6STQ800003YV"
            started_wall = datetime.now().replace(microsecond=0)
            logs, results, stop = [], [], threading.Event()
            monitor = FctAutoLogMonitor(archive_root, active_root, started_wall.timestamp(), logs.append,
                                        results.append, stop, completion_settle_seconds=0)
            monitor.start()
            active_system = active_root / "group0-slot1" / "system"
            active_system.mkdir(parents=True)
            (active_system / "records.csv").write_text(f"MLB_SN,{serial}\n", encoding="utf-8")
            time.sleep(.7)
            old_time = started_wall - timedelta(seconds=31)
            old_stamp = (
                f"{old_time:%Y%m%d}_{old_time.hour}-{old_time:%M-%S}.000-old"
            )
            final_system = archive_root / serial / old_stamp / "system"
            final_system.mkdir(parents=True)
            (final_system / "records.csv").write_text("case,status\nRF,PASS\n", encoding="utf-8")
            (active_system / "records.csv").unlink(); active_system.rmdir(); active_system.parent.rmdir()
            time.sleep(.8); stop.set(); monitor.join(1)
            self.assertEqual(results, [])
            self.assertTrue(any("早於門檻" in message for message in logs))

    def test_fct_active_session_does_not_hit_total_timeout_while_active_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            atlas = Path(directory) / "Atlas"
            active_root, archive_root = atlas / "active", atlas / "unit-archive"
            active_system = active_root / "group0-slot1" / "system"
            active_root.mkdir(parents=True); archive_root.mkdir(parents=True)
            timed_out, stop = threading.Event(), threading.Event()
            monitor = FctAutoLogMonitor(archive_root, active_root, time.time(), lambda _: None,
                                        lambda _: None, stop, timeout_seconds=.2,
                                        on_timeout=timed_out.set)
            monitor.start()
            active_system.mkdir(parents=True)
            (active_system / "records.csv").write_text("MLB_SN,HK5HUX6STQ800003YV\n", encoding="utf-8")
            time.sleep(.8)
            stop.set(); monitor.join(1)
            self.assertFalse(timed_out.is_set())

    def test_records_ignores_empty_metadata_statuses_but_requires_test_status(self):
        with tempfile.TemporaryDirectory() as directory:
            records = Path(directory) / "records.csv"
            records.write_text(
                "attributeName,testName,status\nSwName,,\nSwVersion,,\n,Fixture,PASS\n,RF,PASS\n",
                encoding="utf-8")
            self.assertEqual(parse_records(records)[0], "PASS")
            records.write_text(
                "attributeName,testName,status\nSwName,,\n,Fixture,PASS\n,RF,FAIL\n",
                encoding="utf-8")
            self.assertEqual(parse_records(records)[0], "FAIL")
            records.write_text(
                "attributeName,testName,status\nSwName,,\nSwVersion,,\n",
                encoding="utf-8")
            self.assertEqual(parse_records(records)[0], "UNKNOWN")

    def test_fct_no_sn_slot_fails_only_after_active_is_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            atlas = Path(directory) / "Atlas"
            active_root, final_root = atlas / "active", atlas / "unitest"
            active = active_root / "group0-slot6"
            active_root.mkdir(parents=True); final_root.mkdir()
            progress, completed, stop = [], threading.Event(), threading.Event()
            monitor = FctAutoLogMonitor(final_root, active_root, time.time(), lambda _: None,
                                        lambda _: None, stop, on_progress=progress.append,
                                        on_complete=completed.set, completion_settle_seconds=0)
            monitor.start()
            active.mkdir(); (active / "device.log").write_text("NUMBER_SOF0 COMPLETING\n", encoding="utf-8")
            time.sleep(.6)
            (active / "device.log").unlink(); active.rmdir()
            monitor.join(1.5); stop.set(); monitor.join(1)
            self.assertTrue(completed.is_set())
            self.assertIn((6, "", "FAIL"), [(item.slot, item.sn, item.status) for item in progress])

    def test_fct_result_rows_sort_by_physical_slot(self):
        self.assertEqual(sorted(["fct-active:6", "fct-active:2", "fct:SN001", "fct-active:1"],
                                key=fct_result_row_sort_key),
                         ["fct-active:1", "fct-active:2", "fct-active:6", "fct:SN001"])

    def test_bt_auto_log_demo_ignores_baseline_and_keeps_thread_slot(self):
        started = datetime.now().replace(microsecond=0)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_bt_result(root, 0, "OLD", "PASSED", started)
            results, stop = [], threading.Event()
            monitor = BtAutoLogMonitor(root, started, lambda _: None, results.append, stop, timeout_seconds=1)
            monitor.start()
            self.write_bt_result(root, 2, "NEW003", "FAILED", started)
            monitor.join(.8); stop.set(); monitor.join(1)
            self.assertEqual([(item.slot, item.sn, item.status) for item in results], [(3, "NEW003", "FAIL")])

    def test_local_demo_writes_atlas_files_for_four_sns(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records = write_local_demo_results(root, ["SN001", "SN002", "SN003", "SN004"], "DFU", True, threading.Event(), delay=0)
            self.assertEqual([parse_records(item)[0] for item in records], ["PASS", "PASS", "PASS", "FAIL"])
            self.assertTrue(all(item.parent.joinpath("device.log").is_file() for item in records))

    @unittest.skipIf(cv2 is None, "OpenCV is not installed")
    def test_template_preview_keeps_opencv_bgr_colour_channels(self):
        import numpy as np
        bgr = np.array([[[200, 178, 156]]], dtype=np.uint8)
        encoded = base64.b64decode(opencv_image_to_tk_png(bgr))
        decoded = cv2.imdecode(np.frombuffer(encoded, dtype=np.uint8), cv2.IMREAD_COLOR)
        self.assertEqual(tuple(decoded[0, 0]), (200, 178, 156))

    def test_template_preview_geometry_is_bounded_and_never_upscaled(self):
        scale, width, height = preview_geometry(2000, 1562, 900, 520)
        self.assertEqual((scale, width, height), (520 / 1562, 666, 520))
        scale, width, height = preview_geometry(100, 50, 900, 520)
        self.assertEqual((scale, width, height), (1.0, 100, 50))

    def test_template_preview_reserves_footer_on_short_screens(self):
        self.assertEqual(bounded_template_preview_size(1200, 700, 1440, 900), (1200, 600))
        self.assertEqual(bounded_template_preview_size(1200, 700, 1280, 1024), (1200, 700))
        self.assertEqual(bounded_template_preview_size(900, 520, 1024, 768), (900, 468))

    def test_nearest_timestamp_folder_uses_system_time(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "20250809_14-52-53.927-81ED0A").mkdir()
            (root / "20250810_14-52-53.deadbeef").mkdir()
            chosen = nearest_timestamp_folder(root, datetime(2025, 8, 10, 14, 53))
            self.assertEqual(chosen.name, "20250810_14-52-53.deadbeef")

    def test_records_any_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "records.csv"
            with filename.open("w", newline="") as file: csv.writer(file).writerows([["test", "status"], ["one", "PASS"], ["two", "FAIL"]])
            self.assertEqual(parse_records(filename)[0], "FAIL")

    def test_legacy_singular_record_csv_is_found(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory) / "20260715_14-30-00.demo"
            system = run / "system"
            system.mkdir(parents=True)
            legacy = system / "record.csv"
            legacy.write_text("case,status\na,PASS\n", encoding="utf-8")
            self.assertEqual(locate_records(run), legacy)

    def test_monitor_renders_log_and_reports_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            system = root / "SN001" / datetime.now().strftime("%Y%m%d_%H-%M-%S.demo") / "system"
            system.mkdir(parents=True)
            (system / "device.log").write_text("running\n", encoding="utf-8")
            (system / "records.csv").write_text("case,status\na,PASS\n", encoding="utf-8")
            logs, results = [], []
            stop = threading.Event()
            monitor = FolderMonitor(root, root, ["SN001"], logs.append, results.append, stop)
            monitor.start()
            monitor.join(0.2)
            stop.set(); monitor.join(1)
            self.assertIn("running", logs)
            self.assertEqual([(item.sn, item.status) for item in results], [("SN001", "PASS")])

    def test_monitor_reads_log_from_separate_log_root(self):
        with tempfile.TemporaryDirectory() as csv_dir, tempfile.TemporaryDirectory() as log_dir:
            stamp = datetime.now().strftime("%Y%m%d_%H-%M-%S.demo")
            csv_system = Path(csv_dir) / "SN001" / stamp / "system"
            log_system = Path(log_dir) / "SN001" / stamp / "system"
            csv_system.mkdir(parents=True); log_system.mkdir(parents=True)
            (csv_system / "records.csv").write_text("case,status\na,PASS\n", encoding="utf-8")
            (log_system / "device.log").write_text("separate root log\n", encoding="utf-8")
            logs, results, stop = [], [], threading.Event()
            monitor = FolderMonitor(Path(csv_dir), Path(log_dir), ["SN001"], logs.append, results.append, stop)
            monitor.start(); monitor.join(0.2); stop.set(); monitor.join(1)
            self.assertIn("separate root log", logs)
            self.assertEqual([item.status for item in results], ["PASS"])

    def test_monitor_ignores_records_created_before_batch_start(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            system = root / "SN001" / datetime.now().strftime("%Y%m%d_%H-%M-%S.demo") / "system"
            system.mkdir(parents=True)
            record = system / "records.csv"
            record.write_text("case,status\na,PASS\n", encoding="utf-8")
            old_time = time.time() - 10
            os.utime(system.parent, (old_time, old_time)); os.utime(record, (old_time, old_time))
            results, stop = [], threading.Event()
            monitor = FolderMonitor(root, root, ["SN001"], lambda _: None, results.append, stop, created_after=time.time())
            monitor.start(); monitor.join(.2); stop.set(); monitor.join(1)
            self.assertEqual(results, [])

    def test_monitor_reports_pending_sns_as_timeout(self):
        with tempfile.TemporaryDirectory() as directory:
            timed_out, stop = [], threading.Event()
            monitor = FolderMonitor(Path(directory), Path(directory), ["SN001", "SN002"], lambda _: None,
                                    lambda _: None, stop, timeout_seconds=.05, on_timeout=timed_out.append)
            monitor.start(); monitor.join(1)
            self.assertEqual(timed_out, [["SN001", "SN002"]])

    def test_delete_screenshots_only_removes_given_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selected, other = root / "截圖 one.png", root / "other.png"
            selected.touch(); other.touch()
            deleted, failed = delete_screenshots([selected])
            self.assertEqual(deleted, [selected]); self.assertEqual(failed, [])
            self.assertFalse(selected.exists()); self.assertTrue(other.exists())

    def test_screenshot_accepts_macos_screen_shot_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            shot = Path(directory) / "Screen Shot 2026-07-15 at 10.00.00.png"
            shot.touch()
            self.assertEqual(latest_screenshot(Path(directory), 0), shot)

    def test_screenshot_accepts_chinese_macos_filename(self):
        with tempfile.TemporaryDirectory() as directory:
            shot = Path(directory) / "截圖 2026-07-15 13.52.04.png"
            shot.touch()
            self.assertEqual(latest_screenshot(Path(directory), 0), shot)

    def test_all_new_multi_display_screenshots_are_returned_newest_first(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = root / "Screen Shot left.png", root / "Screen Shot right.png"
            first.touch(); second.touch()
            os.utime(first, (10, 10)); os.utime(second, (20, 20))
            self.assertEqual(new_screenshots(root, 1), [second, first])

    def test_preferences_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = Path(directory) / "preferences.json"
            expected = Preferences("/dev/cu.usbmodem1", "/csv", "/log", "/templates", "BT", "b482_dfu2", "/shots", auto_slot_sync=True)
            expected.save(filename)
            self.assertEqual(Preferences.load(filename), expected)

    @unittest.skipIf(cv2 is None, "OpenCV is not installed")
    def test_template_match_returns_center(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as directory:
            screen = np.full((120, 160, 3), 255, dtype=np.uint8)
            # A non-uniform symbol avoids false matches from a flat template.
            screen[40:70, 60:100] = (0, 0, 0)
            screen[45:65, 70:90] = (0, 255, 0)
            screen_file, template_file = Path(directory) / "shot.png", Path(directory) / "button.png"
            cv2.imwrite(str(screen_file), screen)
            cv2.imwrite(str(template_file), screen[40:70, 60:100])
            self.assertEqual(template_center(screen_file, template_file), (80, 55))

    @unittest.skipIf(cv2 is None, "OpenCV is not installed")
    def test_slot_checkbox_states_returns_four_left_to_right_states(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            screen = np.full((80, 240, 3), 255, dtype=np.uint8)
            checked = np.zeros((14, 14, 3), dtype=np.uint8); checked[2:12, 2:12] = (0, 160, 0)
            unchecked = np.zeros((14, 14, 3), dtype=np.uint8); unchecked[2:12, 2:12] = (0, 0, 180)
            expected = [True, False, True, False]
            for index, value in enumerate(expected):
                x = 15 + index * 55
                screen[30:44, x:x + 14] = checked if value else unchecked
            image, checked_file, unchecked_file = root / "screen.png", root / "checked.png", root / "unchecked.png"
            cv2.imwrite(str(image), screen); cv2.imwrite(str(checked_file), checked); cv2.imwrite(str(unchecked_file), unchecked)
            self.assertEqual([value for value, _ in slot_checkbox_states(image, checked_file, unchecked_file)], expected)

    @unittest.skipIf(cv2 is None, "OpenCV is not installed")
    def test_checkbox_edge_state_ignores_focus_colour_and_normalizes_margins(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            checked = np.full((38, 36, 3), 180, dtype=np.uint8)
            cv2.rectangle(checked, (8, 8), (28, 28), (245, 245, 245), -1)
            cv2.rectangle(checked, (8, 8), (28, 28), (80, 80, 80), 1)
            cv2.line(checked, (12, 18), (17, 24), (20, 20, 20), 3)
            cv2.line(checked, (17, 24), (26, 12), (20, 20, 20), 3)
            unchecked = np.full((31, 31, 3), 240, dtype=np.uint8)
            cv2.rectangle(unchecked, (5, 5), (25, 25), (255, 255, 255), -1)
            cv2.rectangle(unchecked, (5, 5), (25, 25), (80, 80, 80), 1)
            checked_file, unchecked_file = root / "checked.png", root / "unchecked.png"
            cv2.imwrite(str(checked_file), checked); cv2.imwrite(str(unchecked_file), unchecked)

            for expected in (True, False):
                screen = np.full((80, 80, 3), 245, dtype=np.uint8)
                if expected:
                    cv2.rectangle(screen, (28, 28), (48, 48), (0, 180, 0), -1)
                    cv2.rectangle(screen, (28, 28), (48, 48), (30, 80, 30), 1)
                    cv2.line(screen, (32, 38), (37, 44), (255, 255, 255), 3)
                    cv2.line(screen, (37, 44), (46, 32), (255, 255, 255), 3)
                else:
                    cv2.rectangle(screen, (28, 28), (48, 48), (255, 255, 255), -1)
                    cv2.rectangle(screen, (28, 28), (48, 48), (80, 80, 80), 1)
                screen_file = root / f"screen-{expected}.png"
                cv2.imwrite(str(screen_file), screen)
                evidence = checkbox_state_evidence_in_region(
                    screen_file, checked_file, unchecked_file, (20, 20, 40, 40))
                self.assertEqual(evidence.checked, expected)
                self.assertGreater(max(evidence.checked_score, evidence.unchecked_score), .4)

    @unittest.skipIf(cv2 is None, "OpenCV is not installed")
    def test_group_checkbox_can_be_located_without_trusting_ambiguous_state(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control = np.full((24, 24, 3), 255, dtype=np.uint8)
            cv2.rectangle(control, (3, 3), (20, 20), (70, 70, 70), 2)
            screen = np.full((60, 60, 3), 240, dtype=np.uint8)
            screen[18:42, 18:42] = control
            image = root / "screen.png"
            checked = root / "checked.png"
            unchecked = root / "unchecked.png"
            cv2.imwrite(str(image), screen)
            # Equal templates deliberately make the visual state ambiguous.
            cv2.imwrite(str(checked), control)
            cv2.imwrite(str(unchecked), control)
            with self.assertRaisesRegex(AgentError, "狀態不明確"):
                checkbox_state_evidence_in_region(image, checked, unchecked, (10, 10, 40, 40))
            evidence = checkbox_state_evidence_in_region(
                image, checked, unchecked, (10, 10, 40, 40), require_confidence=False)
            self.assertGreater(evidence.checked_score, .9)
            self.assertEqual(evidence.rectangle[:2], (18, 18))

    @unittest.skipIf(cv2 is None, "OpenCV is not installed")
    def test_template_larger_than_search_region_has_actionable_error(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as directory:
            screen_file, template_file = Path(directory) / "screen.png", Path(directory) / "template.png"
            cv2.imwrite(str(screen_file), np.zeros((50, 50, 3), dtype=np.uint8))
            cv2.imwrite(str(template_file), np.zeros((60, 20, 3), dtype=np.uint8))
            with self.assertRaisesRegex(AgentError, "大於搜尋區域"):
                template_match(screen_file, template_file)

    @unittest.skipIf(cv2 is None, "OpenCV is not installed")
    def test_b482_templates_locate_provided_ui(self):
        demo = Path(__file__).parent
        ui = demo.parent / "Atlas UI"
        b482 = demo / "templates" / "b482"
        reference_images = (ui / "B482_DFU_2.jpg", ui / "B482_BT.jpg")
        if not all(image.is_file() for image in reference_images):
            self.skipTest("Optional Atlas UI reference screenshots are not present in this checkout")
        self.assertEqual(template_center(ui / "B482_DFU_2.jpg", b482 / "dfu2_window.png"), (175, 34))
        self.assertEqual(template_center(ui / "B482_DFU_2.jpg", b482 / "dfu2_sn_input.png"), (200, 550))
        self.assertEqual(template_center(ui / "B482_DFU_2.jpg", b482 / "dfu2_ok.png"), (951, 552))
        self.assertEqual(template_center(ui / "B482_BT.jpg", b482 / "bt_start_all.png"), (824, 690))
        self.assertEqual(VISUAL_PROFILES["b482_dfu2"]["input_mode"], "ok_each")
        self.assertIn("checkbox_checked", VISUAL_PROFILES["b482_dfu2"])


if __name__ == "__main__": unittest.main()
