import json
import queue
import tkinter as tk
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from tkinter import ttk
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from b518_log_solution import (
    B518LogSolutionApp, MAIN_FONT_SIZE, ROW_HEIGHT, STATUS_COLOURS, configured_directory,
    STATUS_TEMPLATE_STATES, UNAVAILABLE_COLOUR, WINDOW_WIDTH, KVM_BLOCK_COUNT, kvm_block_colour, slot_count, sn_font_size, window_height,
)
from global_hotkey import COMMAND_SHIFT_M_KEYCODE, COMMAND_SHIFT_MODIFIERS, GlobalHotkeyError, UnavailableHotkey, create_global_hotkey
from log_monitoring import MonitorEvent


class FakeHotkey:
    available = True
    message = "available"

    def __init__(self, callback):
        self.callback = callback
        self.closed = False

    def close(self):
        self.closed = True


class LogSolutionUiTests(unittest.TestCase):
    def test_station_specific_slot_counts_and_heights(self):
        self.assertEqual(slot_count("DFU"), 7)
        self.assertEqual(slot_count("FCT"), 6)
        self.assertEqual(slot_count("BT"), 4)
        self.assertEqual(window_height("DFU"), 612)
        self.assertEqual(window_height("FCT"), 565)
        self.assertEqual(window_height("BT"), 471)
        self.assertEqual(WINDOW_WIDTH, 360)

    def test_all_display_statuses_have_explicit_colours(self):
        for status in ("PASS", "FAIL", "TESTING", "NOTEST", "WAITING", "COMPLETING", "STALLED", "STOPPED", "TIMEOUT"):
            self.assertRegex(STATUS_COLOURS[status], r"^#[0-9a-fA-F]{6}$")
        self.assertRegex(UNAVAILABLE_COLOUR, r"^#[0-9a-fA-F]{6}$")
        self.assertEqual(KVM_BLOCK_COUNT, 7)

    def test_kvm_result_band_keeps_seven_fixed_slot_positions(self):
        self.assertEqual(kvm_block_colour("DFU", 7, "WAITING"), STATUS_COLOURS["WAITING"])
        self.assertEqual(kvm_block_colour("FCT", 6, "NOTEST"), STATUS_COLOURS["NOTEST"])
        self.assertEqual(kvm_block_colour("FCT", 7, "PASS"), UNAVAILABLE_COLOUR)
        self.assertEqual(kvm_block_colour("BT", 4, "FAIL"), STATUS_COLOURS["FAIL"])
        self.assertEqual(kvm_block_colour("BT", 5, "TESTING"), UNAVAILABLE_COLOUR)
        self.assertEqual(kvm_block_colour("BT", 7, "NOTEST"), UNAVAILABLE_COLOUR)

    def test_all_serial_numbers_use_fixed_fourteen_point_font(self):
        self.assertEqual(MAIN_FONT_SIZE, 14)
        self.assertEqual(sn_font_size("HK5HUX6STQ800003YV"), 14)
        self.assertEqual(sn_font_size("X" * 128), 14)

    def test_global_hotkey_success_delivers_callback_and_can_close(self):
        fired = []
        registration = create_global_hotkey(lambda: fired.append(True), platform_name="darwin", implementation=FakeHotkey)
        self.assertTrue(registration.available)
        registration.callback()
        self.assertEqual(fired, [True])
        registration.close()
        self.assertTrue(registration.closed)

    def test_global_hotkey_uses_command_shift_m(self):
        self.assertEqual(COMMAND_SHIFT_M_KEYCODE, 46)
        self.assertEqual(COMMAND_SHIFT_MODIFIERS, 0x0100 | 0x0200)

    def test_global_hotkey_conflict_is_a_safe_fallback(self):
        def conflict(_callback):
            raise GlobalHotkeyError("shortcut already used")

        registration = create_global_hotkey(lambda: None, platform_name="darwin", implementation=conflict)
        self.assertIsInstance(registration, UnavailableHotkey)
        self.assertFalse(registration.available)
        self.assertIn("already used", registration.message)

    def test_non_macos_is_a_safe_local_only_fallback(self):
        registration = create_global_hotkey(lambda: None, platform_name="linux", implementation=FakeHotkey)
        self.assertIsInstance(registration, UnavailableHotkey)
        self.assertFalse(registration.available)

    def test_dashboard_row_cells_fill_the_full_row_geometry(self):
        root = tk.Tk()
        root.withdraw()
        app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey)
        root.update_idletasks()
        try:
            for row in app.status_rows.values():
                self.assertGreaterEqual(row["slot"].winfo_width(), 59)
                self.assertGreaterEqual(row["status"].winfo_width(), 93)
                self.assertGreaterEqual(row["sn"].winfo_width(), 188)
                for cell in row.values():
                    self.assertGreaterEqual(cell.winfo_height(), ROW_HEIGHT)
                    self.assertEqual(int(cell.cget("font").split()[1]), MAIN_FONT_SIZE)
            self.assertEqual(tuple(app.template_labels), STATUS_TEMPLATE_STATES)
            for status, label in app.template_labels.items():
                self.assertEqual(label.cget("text"), status)
                self.assertEqual(label.cget("background"), STATUS_COLOURS[status])
        finally:
            app.hotkey.close()
            root.destroy()

    def test_empty_paths_are_rejected_before_monitor_creation(self):
        root = tk.Tk()
        root.withdraw()
        app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey)
        app.station.set("DFU")
        app.paths["DFU"]["active"].set("")
        app.paths["DFU"]["final"].set("")
        try:
            with patch("b518_log_solution.AtlasActiveArchiveMonitor") as monitor_type, \
                    patch("b518_log_solution.messagebox.showerror") as show_error:
                app.start_monitor()
            monitor_type.assert_not_called()
            show_error.assert_called_once()
            self.assertIsNone(app.monitor)
        finally:
            app.hotkey.close()
            root.destroy()

    def test_configured_directory_never_treats_blank_as_current_directory(self):
        self.assertIsNone(configured_directory(""))
        self.assertIsNone(configured_directory("   "))
        self.assertEqual(configured_directory("."), Path("."))

    def test_monitor_creation_error_is_visible_and_returns_to_standby(self):
        root = tk.Tk()
        root.withdraw()
        app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey)
        app.station.set("DFU")
        app.paths["DFU"]["active"].set(".")
        app.paths["DFU"]["final"].set(".")
        try:
            with patch("b518_log_solution.AtlasActiveArchiveMonitor", side_effect=PermissionError("denied")), \
                    patch("b518_log_solution.messagebox.showerror") as show_error:
                app.start_monitor()
            self.assertIsNone(app.monitor)
            self.assertEqual(app.monitor_state.cget("text"), "待命")
            self.assertIn("denied", app.event_lines[-1])
            show_error.assert_called_once()
        finally:
            app.hotkey.close()
            root.destroy()

    def test_explicit_light_theme_keeps_dark_mode_controls_readable(self):
        root = tk.Tk()
        root.withdraw()
        app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey)
        app.open_settings()
        root.update_idletasks()
        try:
            style = ttk.Style(root)
            self.assertEqual(style.theme_use(), "clam")
            self.assertEqual(style.lookup("TLabel", "foreground"), "#111827")
            self.assertEqual(style.lookup("TEntry", "fieldbackground"), "#ffffff")
            self.assertEqual(style.lookup("TButton", "foreground"), "#111827")
            self.assertEqual(app.settings_window.cget("background"), "#f3f4f6")
            self.assertEqual(app.settings_log.cget("background"), "#ffffff")
            self.assertEqual(app.settings_log.cget("foreground"), "#111827")

            def descendants(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from descendants(child)

            main_labels = [widget for widget in descendants(root) if isinstance(widget, tk.Label)]
            self.assertTrue(main_labels)
            for label in main_labels:
                self.assertTrue(label.cget("foreground"))
        finally:
            app._close_settings()
            app.hotkey.close()
            root.destroy()

    def test_save_settings_persists_all_station_paths_and_restores_station(self):
        saved_paths = {
            "DFU": {"active": "/logs/dfu/active", "final": "/logs/dfu/final", "caseinfo": ""},
            "FCT": {"active": "/logs/fct/active", "final": "/logs/fct/final", "caseinfo": ""},
            "BT": {"active": "", "final": "/logs/bt/testdata", "caseinfo": "/logs/bt/caseinfo"},
        }
        saved_timeouts = {
            "DFU": {"start": "30", "test": "480"},
            "FCT": {"start": "30", "test": "480"},
            "BT": {"start": "30", "test": "240"},
        }
        with TemporaryDirectory() as temporary_directory:
            app_root = Path(temporary_directory) / "B518LogSolution"
            prefs_path = app_root / "preferences.json"
            with patch("b518_log_solution.APP_ROOT", app_root), patch("b518_log_solution.PREFS_PATH", prefs_path):
                interpreter = tk.Tcl()
                app = object.__new__(B518LogSolutionApp)
                app.station = tk.StringVar(master=interpreter, value="DFU")
                app.paths = {station: {field: tk.StringVar(master=interpreter, value="")
                                       for field in ("active", "final", "caseinfo")}
                             for station in ("DFU", "FCT", "BT")}
                app.timeouts = {station: {field: tk.StringVar(master=interpreter, value="")
                                          for field in ("start", "test")}
                                for station in ("DFU", "FCT", "BT")}
                app.settings_station = tk.StringVar(master=interpreter, value="BT")
                app.settings_paths = {
                    station: {field: tk.StringVar(master=interpreter, value=value)
                              for field, value in fields.items()}
                    for station, fields in saved_paths.items()
                }
                app.settings_timeouts = {
                    station: {field: tk.StringVar(master=interpreter, value=value)
                              for field, value in fields.items()}
                    for station, fields in saved_timeouts.items()
                }
                app._render_rows = lambda: None
                app._close_settings = lambda: None

                app._save_settings()
                self.assertEqual(app.station.get(), "BT")
                for station, fields in saved_paths.items():
                    for field, value in fields.items():
                        self.assertEqual(app.paths[station][field].get(), value)
                self.assertEqual(json.loads(prefs_path.read_text(encoding="utf-8")), {
                    "station": "BT", "paths": saved_paths, "timeouts": saved_timeouts,
                })

                restored_app = object.__new__(B518LogSolutionApp)
                restored_app.prefs = restored_app._load_preferences()
                self.assertEqual(restored_app.prefs["station"], "BT")
                self.assertEqual(restored_app.prefs["paths"], saved_paths)
                self.assertEqual(restored_app.prefs["timeouts"], saved_timeouts)

    def test_timeout_values_require_positive_integers(self):
        interpreter = tk.Tcl()
        app = object.__new__(B518LogSolutionApp)
        app.timeouts = {"BT": {
            "start": tk.StringVar(master=interpreter, value="30"),
            "test": tk.StringVar(master=interpreter, value="0"),
        }}
        with self.assertRaisesRegex(ValueError, "正整數"):
            app._timeout_seconds("BT")

    def test_cancel_settings_does_not_change_saved_path_values(self):
        interpreter = tk.Tcl()
        app = object.__new__(B518LogSolutionApp)
        app.paths = {"DFU": {"active": tk.StringVar(master=interpreter, value="/before")}}
        app.settings_paths = {"DFU": {"active": tk.StringVar(master=interpreter, value="/after")}}
        app.settings_window = None
        app.settings_log = None
        app._close_settings()
        self.assertEqual(app.paths["DFU"]["active"].get(), "/before")

    def test_monitor_lifecycle_never_changes_window_topmost_attribute(self):
        monitor = MagicMock()
        app = object.__new__(B518LogSolutionApp)
        app.root = MagicMock()
        app.events = queue.Queue()
        app.monitor = None
        app.station = SimpleNamespace(get=lambda: "DFU")
        app.paths = {"DFU": {
            "active": SimpleNamespace(get=lambda: "."),
            "final": SimpleNamespace(get=lambda: "."),
        }}
        app.timeouts = {"DFU": {
            "start": SimpleNamespace(get=lambda: "30"),
            "test": SimpleNamespace(get=lambda: "480"),
        }}
        app.start_button = MagicMock()
        app.monitor_state = MagicMock()
        app.event_lines = []
        app.settings_log = None
        app._save_preferences = MagicMock()
        app._reset_rows = MagicMock()
        app._set_monitor_controls = MagicMock()
        with patch("b518_log_solution.AtlasActiveArchiveMonitor", return_value=monitor):
            app.start_monitor()

        monitor.start.assert_called_once()
        app.root.attributes.assert_not_called()

        app._handle_event(MonitorEvent("finished", "monitor ended"))
        app.root.attributes.assert_not_called()
        self.assertIsNone(app.monitor)

    def test_result_does_not_change_window_layer_or_keyboard_focus(self):
        app = object.__new__(B518LogSolutionApp)
        app.root = MagicMock()
        app.monitor = SimpleNamespace(results={1: SimpleNamespace(sn="SN123", status="PASS")})
        app.event_lines = []
        app.settings_log = None
        app._set_row = MagicMock()
        app._set_monitor_controls = MagicMock()

        app._handle_event(MonitorEvent("result", "slot1 PASS", 1, "SN123", "PASS"))

        app._set_row.assert_called_once_with(1, "SN123", "PASS")
        app.root.attributes.assert_not_called()
        app.root.focus_force.assert_not_called()

    def test_timeout_event_returns_dashboard_to_timeout_stopped_state(self):
        app = object.__new__(B518LogSolutionApp)
        app.root = MagicMock()
        app.monitor = SimpleNamespace(results={1: SimpleNamespace(sn="SN123", status="TIMEOUT")})
        app.event_lines = []
        app.settings_log = None
        app._set_row = MagicMock()
        app._set_monitor_controls = MagicMock()

        app._handle_event(MonitorEvent("timeout", "FCT slot1 測試逾時", 1, status="TIMEOUT"))

        app._set_row.assert_called_once_with(1, "SN123", "TIMEOUT")
        self.assertIsNone(app.monitor)
        app._set_monitor_controls.assert_called_once_with(False, "逾時停止")

    def test_stopped_event_does_not_change_window_topmost_attribute(self):
        app = object.__new__(B518LogSolutionApp)
        app.root = MagicMock()
        app.monitor = MagicMock()
        app.event_lines = []
        app.settings_log = None
        app._set_monitor_controls = MagicMock()

        app._handle_event(MonitorEvent("stopped", "monitor ended"))

        app.root.attributes.assert_not_called()
        self.assertIsNone(app.monitor)
        app._set_monitor_controls.assert_called_once_with(False)

    def test_close_does_not_change_window_topmost_attribute(self):
        app = object.__new__(B518LogSolutionApp)
        app.root = MagicMock()
        app.hotkey = MagicMock()
        app.monitor = None
        app._save_preferences = MagicMock()

        app.close()

        app.root.attributes.assert_not_called()
        app.root.destroy.assert_called_once()


if __name__ == "__main__":
    unittest.main()
