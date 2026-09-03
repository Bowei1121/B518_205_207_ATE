import unittest
import tkinter as tk

from b518_log_solution import B518LogSolutionApp, STATUS_COLOURS, slot_count, sn_font_size, window_height
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
        self.assertEqual(window_height("DFU"), 620)
        self.assertEqual(window_height("FCT"), 556)
        self.assertEqual(window_height("BT"), 428)

    def test_all_display_statuses_have_explicit_colours(self):
        for status in ("PASS", "FAIL", "TESTING", "NOTEST", "WAITING", "COMPLETING", "STALLED", "STOPPED"):
            self.assertRegex(STATUS_COLOURS[status], r"^#[0-9a-fA-F]{6}$")

    def test_serial_number_font_stays_readable_without_truncation_policy(self):
        self.assertEqual(sn_font_size("HK5HUX6STQ800003YV"), 20)
        self.assertGreaterEqual(sn_font_size("X" * 128), 12)
        self.assertEqual(sn_font_size("X" * 1000), 12)

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
                self.assertGreaterEqual(row["slot"].winfo_width(), 60)
                self.assertGreaterEqual(row["status"].winfo_width(), 120)
                self.assertGreaterEqual(row["sn"].winfo_width(), 240)
                for cell in row.values():
                    self.assertGreaterEqual(cell.winfo_height(), 64)
        finally:
            app.hotkey.close()
            root.destroy()


if __name__ == "__main__":
    unittest.main()
