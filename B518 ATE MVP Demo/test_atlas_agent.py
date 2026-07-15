import base64
import csv
import os
import tempfile
import threading
import unittest
from datetime import datetime
from pathlib import Path

from atlas_agent import FolderMonitor, Preferences, SerialLineFramer, SerialLink, VISUAL_PROFILES, accepted_ack, batch_result_report, cv2, incoming_barcode_payload, latest_screenshot, locate_records, nearest_timestamp_folder, new_screenshots, opencv_image_to_tk_png, parse_barcodes, parse_records, preview_geometry, template_center, write_local_demo_results


class AtlasAgentTests(unittest.TestCase):
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

    def test_accepted_batch_ack_has_station_and_sns(self):
        self.assertEqual(accepted_ack("FCT", ["SN001", "SN002"]), "ACK:ACCEPTED,FCT,SN001,SN002")

    def test_batch_result_report_is_compact_and_preserves_sn_order(self):
        report = batch_result_report(["SN001", "SN002", "SN003", "SN004"],
                                     {"SN004": "FAIL", "SN002": "PASS", "SN001": "PASS", "SN003": "PASS"})
        self.assertEqual(report, "RESULT:SN001,PASS;SN002,PASS;SN003,PASS;SN004,FAIL")

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
