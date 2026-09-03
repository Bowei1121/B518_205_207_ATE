import unittest
import tkinter as tk
from pathlib import Path
from unittest.mock import patch

from b518_log_solution import (
    B518LogSolutionApp, MAIN_FONT_SIZE, ROW_HEIGHT, STATUS_COLOURS, configured_directory,
    STATUS_TEMPLATE_STATES, WINDOW_WIDTH, slot_count, sn_font_size, window_height,
)
from global_hotkey import COMMAND_SHIFT_M_KEYCODE, COMMAND_SHIFT_MODIFIERS, GlobalHotkeyError, UnavailableHotkey, create_global_hotkey


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
        self.assertEqual(window_height("DFU"), 560)
        self.assertEqual(window_height("FCT"), 513)
        self.assertEqual(window_height("BT"), 419)
        self.assertEqual(WINDOW_WIDTH, 360)

    def test_all_display_statuses_have_explicit_colours(self):
        for status in ("PASS", "FAIL", "TESTING", "NOTEST", "WAITING", "COMPLETING", "STALLED", "STOPPED"):
            self.assertRegex(STATUS_COLOURS[status], r"^#[0-9a-fA-F]{6}$")

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


if __name__ == "__main__":
    unittest.main()
