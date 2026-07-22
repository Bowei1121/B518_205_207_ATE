import base64
import csv
import os
import tempfile
import threading
import time
import unittest
from datetime import datetime
from pathlib import Path

from bump_build_version import bump_version
from atlas_agent import AgentError, BtStatusRow, FolderMonitor, OcrText, Preferences, SerialLineFramer, SerialLink, VISUAL_PROFILES, absolute_click_commands, absolute_hid_report_coordinate, arduino_ip_reply, batch_result_report, bt_completed_results, bt_statuses_from_screen, click_commands, cv2, delete_screenshots, dfu_ok_each_commands, dfu_tab_slot_commands, hid_coordinate, hid_success_reply, incoming_barcode_payload, latest_screenshot, locate_records, nearest_timestamp_folder, new_screenshots, normalize_ocr_sn, opencv_image_to_tk_png, pair_bt_sn_text, parse_barcodes, parse_records, parse_test_command, png_retina_scale, preview_geometry, resolve_template_path, screenshot_scale_for_displays, template_center, template_match, template_matches, vision_rectangle_components, write_local_demo_results, write_match_overlay
from hid_calibration import delta_command, direction_delta, parse_step


class AtlasAgentTests(unittest.TestCase):
    def test_build_version_bumps_patch_without_touching_other_values(self):
        updated, version = bump_version('VERSION = "3.14.15"\n')
        self.assertEqual(version, "3.14.16")
        self.assertEqual(updated, 'VERSION = "3.14.16"\n')

    def test_barcodes(self):
        self.assertEqual(parse_barcodes("DATA:A, B,C"), ["A", "B", "C"])
        with self.assertRaises(Exception): parse_barcodes("A,B,C,D,E")

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

    def test_agent_sends_crlf_for_labview_terminated_tcp_mode(self):
        class FakeSerial:
            def __init__(self): self.written = b""
            def write(self, payload): self.written += payload
            def flush(self): pass
        link = SerialLink(lambda _: None)
        link.connection = FakeSerial()
        link.send("RESULT:SN001,PASS,ok\n")
        self.assertEqual(link.connection.written, b"RESULT:SN001,PASS,ok\r\n")

    def test_arduino_network_replies_update_the_same_ip_display(self):
        self.assertEqual(arduino_ip_reply("IP:192.168.1.100"), "192.168.1.100")
        self.assertEqual(arduino_ip_reply("OK:NET_SET:192.168.1.101"), "192.168.1.101")
        self.assertEqual(arduino_ip_reply("EVT: IP=192.168.1.102"), "192.168.1.102")
        self.assertIsNone(arduino_ip_reply("OK:NET_SET:999.1.1.1"))

    def test_dfu_each_sn_returns_to_origin_before_input_and_ok(self):
        self.assertEqual(
            dfu_ok_each_commands(["SN001", "SN002"], (100, 200), (300, 400)),
            ["M_RESET", "M_MOVE:100,200", "M_CLICK:L", "K_WRITE:SN001", "M_RESET", "M_MOVE:300,400", "M_CLICK:L",
             "M_RESET", "M_MOVE:100,200", "M_CLICK:L", "K_WRITE:SN002", "M_RESET", "M_MOVE:300,400", "M_CLICK:L"])

    def test_generic_dfu_tabs_over_unpopulated_slots(self):
        self.assertEqual(dfu_tab_slot_commands([(1, "SN001"), (3, "SN003"), (4, "SN004")]),
                         ["K_WRITE:SN001", "K_KEY:TAB", "K_KEY:TAB", "K_WRITE:SN003",
                          "K_KEY:TAB", "K_WRITE:SN004"])

    def test_absolute_click_returns_to_origin_before_relative_hid_move(self):
        self.assertEqual(absolute_click_commands((80, 55)), ["M_RESET", "M_MOVE:80,55", "M_CLICK:L"])

    def test_absolute_hid_mode_uses_raw_absolute_report_without_mouse_reset(self):
        self.assertEqual(absolute_hid_report_coordinate((0, 0), 1440, 900), (0, 0))
        self.assertEqual(absolute_hid_report_coordinate((1439, 899), 1440, 900), (32767, 32767))
        self.assertEqual(click_commands((4915, 22632), "absolute"), ["M_ABS:4915,22632", "M_CLICK:L"])
        self.assertEqual(dfu_ok_each_commands(["SN1"], (10, 20), (30, 40), "absolute"),
                         ["M_ABS:10,20", "M_CLICK:L", "K_WRITE:SN1", "M_ABS:30,40", "M_CLICK:L"])
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

    def test_station_job_command_preserves_sparse_slots(self):
        command = parse_test_command("FCT:JOB=20260722-001;1=SN001,3=SN003,4=SN004")
        self.assertEqual(command.station, "FCT")
        self.assertEqual(command.job_id, "20260722-001")
        self.assertEqual(command.slots, [1, 3, 4])
        self.assertEqual(command.sns, ["SN001", "SN003", "SN004"])
        with self.assertRaises(AgentError):
            parse_test_command("BT:JOB=X;1=SN001,1=SN002")

    def test_bt_ignores_stale_final_status_until_testing_has_been_seen(self):
        seen = set()
        self.assertEqual(bt_completed_results(["SN001", "SN002"], [1, 2], ["PASS", "FAIL", "NOTSET", "NOTSET"], seen), {})
        self.assertEqual(bt_completed_results(["SN001", "SN002"], [1, 2], ["TESTING", "TESTING", "NOTSET", "NOTSET"], seen), {})
        self.assertEqual(seen, {"SN001", "SN002"})
        self.assertEqual(bt_completed_results(["SN001", "SN002"], [1, 2], ["PASS", "TESTING", "NOTSET", "NOTSET"], seen), {})
        self.assertEqual(bt_completed_results(["SN001", "SN002"], [1, 2], ["PASS", "FAIL", "NOTSET", "NOTSET"], seen),
                         {"SN001": "PASS", "SN002": "FAIL"})

    def test_bt_ocr_sn_text_is_matched_to_the_corresponding_status_row(self):
        rows = [BtStatusRow("TESTING", (800, 100 + index * 60, 120, 30)) for index in range(4)]
        text = [OcrText(f" bt-abcd-00{index + 1} ", (550, 102 + index * 60, 150, 26)) for index in range(4)]
        self.assertEqual(pair_bt_sn_text(rows, text), ["BT-ABCD-001", "BT-ABCD-002", "BT-ABCD-003", "BT-ABCD-004"])
        self.assertEqual(normalize_ocr_sn(" sn O01 "), "SN001")

    def test_vision_ocr_rectangle_accepts_legacy_and_current_pyobjc_shapes(self):
        self.assertEqual(vision_rectangle_components((.1, .2, .3, .4)), (.1, .2, .3, .4))
        self.assertEqual(vision_rectangle_components(((.1, .2), (.3, .4))), (.1, .2, .3, .4))
        with self.assertRaises(AgentError):
            vision_rectangle_components((.1, .2))

    def test_bt_ocr_sn_pairing_keeps_missing_slot_empty_for_manual_review(self):
        rows = [BtStatusRow("TESTING", (800, 100, 120, 30)), BtStatusRow("TESTING", (800, 160, 120, 30))]
        self.assertEqual(pair_bt_sn_text(rows, [OcrText("SN001", (550, 102, 150, 26))]), ["SN001", ""])

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
            expected = Preferences("/dev/cu.usbmodem1", "/csv", "/log", "/templates", "BT", "b482_dfu2", "/shots")
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
    def test_bt_status_templates_read_four_rows_in_slot_order(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            screen = np.full((180, 180, 3), 255, dtype=np.uint8)
            colors = {"PASS": (0, 239, 0), "FAIL": (0, 0, 255), "TESTING": (0, 255, 255), "NOTSET": (241, 75, 240)}
            statuses = ["TESTING", "PASS", "FAIL", "NOTSET"]
            templates = {}
            for index, status in enumerate(statuses):
                y = 20 + index * 35
                screen[y:y + 20, 80:130] = colors[status]
                screen[y + 4:y + 16, 96:114] = (255, 255, 255)  # non-uniform crop detail
                template = root / f"{status}.png"
                cv2.imwrite(str(template), screen[y:y + 20, 80:130])
                templates[status] = template
            image = root / "screen.png"; cv2.imwrite(str(image), screen)
            self.assertEqual(bt_statuses_from_screen(image, templates), statuses)
            self.assertEqual(len(template_matches(image, templates["PASS"])), 1)

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
        self.assertEqual(template_center(ui / "B482_DFU_2.jpg", b482 / "dfu2_window.png"), (175, 34))
        self.assertEqual(template_center(ui / "B482_DFU_2.jpg", b482 / "dfu2_sn_input.png"), (200, 550))
        self.assertEqual(template_center(ui / "B482_DFU_2.jpg", b482 / "dfu2_ok.png"), (951, 552))
        self.assertEqual(template_center(ui / "B482_BT.jpg", b482 / "bt_start_all.png"), (824, 690))
        self.assertEqual(VISUAL_PROFILES["b482_dfu2"]["input_mode"], "ok_each")


if __name__ == "__main__": unittest.main()
