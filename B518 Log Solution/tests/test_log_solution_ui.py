import csv
import io
import json
import queue
import tkinter as tk
import time
import unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from tkinter import ttk
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from b518_log_solution import (
    B518LogSolutionApp, MAIN_FONT_SIZE, ROW_HEIGHT, STATUS_COLOURS, configured_directory,
    STATUS_TEMPLATE_STATES, UNAVAILABLE_COLOUR, WINDOW_WIDTH, KVM_BLOCK_COUNT, kvm_block_colour,
    slot_count, sn_font_size, visible_detail_rows, window_height,
)
from global_hotkey import COMMAND_SHIFT_M_KEYCODE, COMMAND_SHIFT_MODIFIERS, GlobalHotkeyError, UnavailableHotkey, create_global_hotkey
from log_monitoring import MonitorEvent
from monitoring_round import RoundCoordinator, RoundEvent
from machine_profiles import MachineProfileStore, ProfileCatalog, migrate_legacy_preferences


class FakeHotkey:
    available = True
    message = "available"

    def __init__(self, callback):
        self.callback = callback
        self.closed = False

    def close(self):
        self.closed = True


class LogSolutionUiTests(unittest.TestCase):
    def wait_for(self, predicate, timeout=3):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.01)
        self.fail("Timed out waiting for asynchronous monitor preparation")

    def test_running_round_keeps_its_capacity_and_mapping_after_profile_update(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.withdraw()
            active = Path(temporary) / "active"
            final = Path(temporary) / "final"
            active.mkdir()
            final.mkdir()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey, session_root=Path(temporary) / "sessions")
            try:
                app.open_settings()
                app.profile_editor_capacity.set("3")
                app.profile_editor_mapping.set("1:3, 2:2, 3:1")
                app.profile_editor_paths["active"].set(str(active))
                app.profile_editor_paths["final"].set(str(final))
                app._apply_profile_editor()
                app.start_monitor()

                preparation_deadline = time.monotonic() + 3
                while app.monitor is None and time.monotonic() < preparation_deadline:
                    root.update()
                    time.sleep(0.01)

                self.assertIsNotNone(app.monitor)
                self.assertEqual(app.active_profile_snapshot.capacity, 3)
                self.assertEqual(len(app.status_rows), 3)
                self.assertEqual(app.monitor.session.settings["profile_snapshot"]["profile"]["mapping"], [
                    {"source": 1, "display": 3},
                    {"source": 2, "display": 2},
                    {"source": 3, "display": 1},
                ])

                app.profile_editor_capacity.set("12")
                app.profile_editor_mapping.set(", ".join("{}:{}".format(slot, slot)
                                                            for slot in range(1, 13)))
                app._apply_profile_editor()
                self.assertEqual(app.profiles.get("B518", "FCT").capacity, 12)
                self.assertEqual(len(app.status_rows), 3)
                self.assertEqual(app.active_profile_snapshot.capacity, 3)

                record = active / "group0-slot1" / "system" / "records.csv"
                record.parent.mkdir(parents=True)
                record.write_text("MLB_SN,status\nSERIAL00000001,Pass\n", encoding="utf-8")
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    root.update()
                    snapshot = app.rounds.snapshot()
                    if any(event.event.kind == "sn_locked" for event in snapshot.events):
                        break
                    time.sleep(0.05)
                else:
                    self.fail("The running Atlas round did not report the controlled source position")

                result = next(result for result in app.rounds.snapshot().results if result.slot == 3)
                self.assertEqual((result.sn, result.status), ("SERIAL00000001", "TESTING"))
                self.assertEqual(app.kvm_result_blocks[4].cget("background"), UNAVAILABLE_COLOUR)

                archive_stamp = app.monitor.started.strftime("%Y%m%d_%H-%M-%S")
                archive = final / "SERIAL00000001" / archive_stamp / "system" / "records.csv"
                archive.parent.mkdir(parents=True)
                archive.write_text("MLB_SN,status\nSERIAL00000001,Pass\n", encoding="utf-8")
                record.unlink()
                record.parent.rmdir()
                (active / "group0-slot1").rmdir()
                deadline = time.monotonic() + 4
                while time.monotonic() < deadline:
                    root.update()
                    snapshot = app.rounds.snapshot()
                    result = next(result for result in snapshot.results if result.slot == 3)
                    if result.status == "PASS":
                        break
                    time.sleep(0.05)
                else:
                    self.fail("The Atlas final result did not reach its configured display position")

                app._drain_events()
                self.assertEqual(app.status_rows[3]["status"].cget("text"), "PASS")
                self.assertEqual(app.kvm_result_blocks[3].cget("background"), STATUS_COLOURS["PASS"])
                self.assertEqual(app.kvm_result_blocks[4].cget("background"), UNAVAILABLE_COLOUR)
            finally:
                if app.monitor:
                    app.rounds.stop()
                app._close_settings()
                app.hotkey.close()
                root.destroy()

    def test_twenty_position_profile_renders_two_fixed_bands_and_scrollable_details(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.withdraw()
            app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey)
            try:
                app.open_settings()
                app.profile_editor_capacity.set("10")
                app.profile_editor_mapping.set(", ".join("{}:{}".format(source, source)
                                                            for source in range(1, 11)))
                app._apply_profile_editor()
                root.deiconify()
                root.update()
                self.assertTrue(app.kvm_result_blocks[10].winfo_ismapped())
                self.assertFalse(app.kvm_result_blocks[11].winfo_ismapped())
                self.assertEqual(root.winfo_height(), window_height(10, root.winfo_screenheight()))

                app.profile_editor_capacity.set("11")
                app.profile_editor_mapping.set(", ".join("{}:{}".format(source, source)
                                                            for source in range(1, 12)))
                app._apply_profile_editor()
                root.update()
                self.assertTrue(app.kvm_result_blocks[11].winfo_ismapped())
                self.assertGreater(app.kvm_result_blocks[11].winfo_y(),
                                   app.kvm_result_blocks[10].winfo_y())
                self.assertEqual(root.winfo_height(), window_height(11, root.winfo_screenheight()))

                app.profile_editor_capacity.set("20")
                app.profile_editor_mapping.set(", ".join("{}:{}".format(source, source)
                                                            for source in range(1, 21)))
                app._apply_profile_editor()
                root.update_idletasks()
                root.update()

                self.assertTrue(root.winfo_ismapped())
                self.assertEqual(root.winfo_width(), WINDOW_WIDTH)
                self.assertEqual(root.winfo_height(), window_height(20, root.winfo_screenheight()))
                self.assertLessEqual(root.winfo_height(), root.winfo_screenheight())
                self.assertEqual(len(app.status_rows), 20)
                self.assertEqual(len(app.kvm_result_blocks), 20)
                self.assertEqual(app.kvm_result_blocks[1].winfo_y(), app.kvm_result_blocks[10].winfo_y())
                self.assertGreater(app.kvm_result_blocks[11].winfo_y(), app.kvm_result_blocks[10].winfo_y())
                self.assertEqual(app.kvm_result_blocks[11].winfo_x(), app.kvm_result_blocks[1].winfo_x())
                self.assertEqual(app.kvm_result_blocks[20].winfo_y(), app.kvm_result_blocks[11].winfo_y())
                self.assertEqual(app.kvm_result_blocks[20].cget("background"), STATUS_COLOURS["WAITING"])
                self.assertLess(app.rows_canvas.winfo_height(), len(app.status_rows) * ROW_HEIGHT)

                original_scaling = float(root.tk.call("tk", "scaling"))
                root.tk.call("tk", "scaling", 1.5)
                root.update_idletasks()
                self.assertLessEqual(app.rows_panel.winfo_rooty() + app.rows_panel.winfo_height(),
                                     root.winfo_rooty() + root.winfo_height())
                for label in app.template_labels.values():
                    self.assertLessEqual(label.winfo_reqheight(), label.winfo_height())
                for row in app.status_rows.values():
                    self.assertLessEqual(row["status"].winfo_reqheight(), ROW_HEIGHT)
                root.tk.call("tk", "scaling", original_scaling)
                root.update_idletasks()

                marker_y = app.kvm_result_blocks[1].winfo_rooty()
                app.rows_canvas.yview_scroll(100, "units")
                root.update_idletasks()
                self.assertEqual(app.kvm_result_blocks[1].winfo_rooty(), marker_y)
                self.assertEqual(app.rows_canvas.yview()[1], 1.0)
            finally:
                app._close_settings()
                app.hotkey.close()
                root.destroy()

    def test_engineer_can_apply_and_cancel_a_complete_profile_draft(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.withdraw()
            app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey)
            try:
                app.open_settings()
                app.profile_editor_project.set("Demo")
                app.profile_editor_machine.set("DFU")
                app.profile_editor_platform.set("atlas")
                app.profile_editor_capacity.set("2")
                app.profile_editor_paths["active"].set("/deployment/active")
                app.profile_editor_paths["final"].set("/deployment/final")
                app.profile_editor_mapping.set("1:2, 2:1")
                app.profile_editor_timeouts["start"].set("45")
                app._apply_profile_editor()

                saved = app.profiles.get("Demo", "DFU")
                self.assertEqual(saved.mapping, ((1, 2), (2, 1)))
                self.assertEqual(saved.timeouts["start"], 45)
                self.assertIn("Demo", app.project_choice.cget("values"))
                self.assertEqual(MachineProfileStore(Path(temporary) / "preferences.json").load()[0]
                                 .get("Demo", "DFU"), saved)

                app.profile_editor_project.set("Unsaved")
                app.profile_editor_capacity.set("3")
                app._cancel_profile_editor()

                self.assertEqual(app.profile_editor_project.get(), "Demo")
                self.assertEqual(app.profile_editor_capacity.get(), "2")
                self.assertNotIn("Unsaved", app.profiles.projects)
            finally:
                app._close_settings()
                app.hotkey.close()
                root.destroy()

    def test_engineer_can_load_an_existing_profile_before_editing_it(self):
        root = tk.Tk()
        root.withdraw()
        app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey)
        try:
            app.open_settings()
            app.profile_editor_project.set("B482")
            app.profile_editor_machine.set("BT")
            app._load_profile_editor_selection()

            self.assertEqual(app.profile_editor_platform.get(), "b482")
            self.assertEqual(app.profile_editor_capacity.get(), "4")
            self.assertEqual(app.profile_editor_mapping.get(), "1:1, 2:2, 3:3, 4:4")
            app._cancel_profile_editor()
            self.assertEqual(app.profile_editor_project.get(), "B482")
            self.assertEqual(app.profile_editor_machine.get(), "BT")
            self.assertEqual(app.profile_editor_capacity.get(), "4")
        finally:
            app._close_settings()
            app.hotkey.close()
            root.destroy()

    def test_failed_profile_save_keeps_the_active_catalog_and_selected_configuration(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.withdraw()
            app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey)
            try:
                app.open_settings()
                original_catalog = app.profiles.to_dict()
                original_selection = (app.project.get(), app.station.get())
                app.profile_editor_project.set("Unsaved")
                with patch.object(app.profile_store, "save", side_effect=OSError("disk full")):
                    app._apply_profile_editor()

                self.assertEqual(app.profiles.to_dict(), original_catalog)
                self.assertEqual((app.project.get(), app.station.get()), original_selection)
                self.assertIn("原配置仍有效", app.profile_editor_status.get())
            finally:
                app._close_settings()
                app.hotkey.close()
                root.destroy()

    def test_legacy_settings_save_cannot_overwrite_a_newly_applied_profile(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.withdraw()
            app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey)
            try:
                app.open_settings()
                app.profile_editor_project.set("B518")
                app.profile_editor_machine.set("FCT")
                app._load_profile_editor_selection()
                app.profile_editor_paths["active"].set("/deployment/new-active")
                app.profile_editor_paths["final"].set("/deployment/new-final")
                app._apply_profile_editor()
                app._save_settings()

                saved = app.profiles.get("B518", "FCT")
                self.assertEqual(saved.paths["active"], "/deployment/new-active")
                self.assertEqual(saved.paths["final"], "/deployment/new-final")
            finally:
                app.hotkey.close()
                root.destroy()

    def test_engineer_import_export_and_reload_preserve_a_deployable_catalog(self):
        with TemporaryDirectory() as temporary:
            source_preferences = Path(temporary) / "source.json"
            deployment_preferences = Path(temporary) / "deployed" / "preferences.json"
            exported = Path(temporary) / "deployment-profile.json"
            single_profile_export = Path(temporary) / "single-profile.json"
            with patch("b518_log_solution.PREFS_PATH", source_preferences):
                root = tk.Tk()
                root.withdraw()
                source = B518LogSolutionApp(root, hotkey_factory=FakeHotkey)
                try:
                    source.open_settings()
                    source.profile_editor_project.set("Demo")
                    source.profile_editor_machine.set("DFU")
                    source.profile_editor_platform.set("atlas")
                    source.profile_editor_capacity.set("2")
                    source.profile_editor_paths["active"].set("/deployment/active")
                    source.profile_editor_paths["final"].set("/deployment/final")
                    source.profile_editor_mapping.set("1:2, 2:1")
                    source.profile_editor_timeouts["start"].set("45")
                    source._apply_profile_editor()
                    with patch("b518_log_solution.filedialog.asksaveasfilename", return_value=str(exported)):
                        source._export_profiles()
                    MachineProfileStore.export_document(
                        single_profile_export,
                        ProfileCatalog((source.profiles.get("Demo", "DFU"),)),
                    )
                finally:
                    source._close_settings()
                    source.hotkey.close()
                    root.destroy()

            with patch("b518_log_solution.PREFS_PATH", deployment_preferences):
                deploy_root = tk.Tk()
                deploy_root.withdraw()
                deployed = B518LogSolutionApp(deploy_root, hotkey_factory=FakeHotkey)
                try:
                    deployed.open_settings()
                    with patch("b518_log_solution.filedialog.askopenfilename",
                               return_value=str(single_profile_export)):
                        deployed._import_profiles()
                    self.assertEqual(deployed.profiles.get("Demo", "DFU").paths["active"],
                                     "/deployment/active")
                    self.assertEqual((deployed.project.get(), deployed.station.get()), ("Demo", "DFU"))
                    self.assertIn("原選擇不存在", deployed.profile_editor_status.get())
                    original = deployed.profiles.to_dict()
                    invalid_export = Path(temporary) / "invalid.json"
                    invalid_export.write_text("{", encoding="utf-8")
                    with patch("b518_log_solution.filedialog.askopenfilename",
                               return_value=str(invalid_export)):
                        deployed._import_profiles()
                    self.assertEqual(deployed.profiles.to_dict(), original)
                    self.assertIn("原配置保留", deployed.profile_editor_status.get())

                    replacement = deployed.profiles.with_profile(replace(
                        deployed.profiles.get("Demo", "DFU"),
                        paths={"active": "/updated/active", "final": "/updated/final"},
                    ))
                    deployed.project.set("Demo")
                    deployed.station.set("DFU")
                    deployed.profile_store.save(replacement, "Demo", "DFU")
                    deployed.settings_paths["DFU"]["active"].set("/stale/active")
                    deployed._reload_profiles()

                    self.assertEqual(deployed.profiles.get("Demo", "DFU").paths["active"],
                                     "/updated/active")
                    self.assertEqual(deployed.profile_editor_project.get(), "Demo")
                    deployed._save_settings()
                    self.assertEqual(deployed.profiles.get("Demo", "DFU").paths["active"],
                                     "/updated/active")
                finally:
                    deployed._close_settings()
                    deployed.hotkey.close()
                    deploy_root.destroy()

    def test_app_completes_rswmt_final_only_round_through_shared_entry(self):
        with TemporaryDirectory() as temporary:
            output = Path(temporary) / "output" / "SmtCal"
            output.mkdir(parents=True)
            app = object.__new__(B518LogSolutionApp)
            app.root = MagicMock()
            app.events = queue.Queue()
            app.rounds = RoundCoordinator(app.events.put)
            app.active_round_id = None
            app.monitor = None
            app.station = SimpleNamespace(get=lambda: "BT")
            app.bt_format = SimpleNamespace(get=lambda: "B518 RS-WMT")
            app.paths = {name: {
                "active": SimpleNamespace(get=lambda: ""),
                "final": SimpleNamespace(get=lambda: str(output)),
                "caseinfo": SimpleNamespace(get=lambda: ""),
            } for name in ("DFU", "FCT", "BT")}
            app.timeouts = {name: {
                "start": SimpleNamespace(get=lambda: "240"),
                "test": SimpleNamespace(get=lambda: "480"),
            } for name in ("DFU", "FCT", "BT")}
            app.start_button = MagicMock()
            app.monitor_state = MagicMock()
            app.event_lines = []
            app.settings_log = None
            app._save_preferences = MagicMock()
            app._reset_rows = MagicMock()
            app._set_monitor_controls = MagicMock()

            with patch("log_monitoring.SessionStore"):
                app.start_monitor()
                prepare_deadline = time.monotonic() + 3
                while app.rounds.monitor is None and time.monotonic() < prepare_deadline:
                    time.sleep(0.01)
                monitor = app.rounds.monitor
                self.assertIsNotNone(monitor)
                start = monitor.started.replace(microsecond=0)
                stop = start + timedelta(seconds=5)
                headers = ['Serial Number', 'Test Pass/Fail Status', 'List of Failing Tests',
                           'Error Description', 'Test Start Time', 'Test Stop Time', 'PRODUCT',
                           'tc=Slot:tech=None:band=None;subtc=None:rate=None:freq=None:pwr=None;']
                for slot in range(1, 5):
                    name = "SERIAL{:06d}".format(slot)
                    result_dir = output / stop.strftime("%Y-%m-%d_%H-%M-%S")
                    result_dir.mkdir(exist_ok=True)
                    content = io.StringIO()
                    writer = csv.writer(content)
                    writer.writerow(["Overlay", "SmtCal"] + [""] * 6)
                    writer.writerow(headers)
                    writer.writerow([name, "Pass", "[]", "", start.strftime("%Y/%d/%m %H:%M:%S"),
                                     stop.strftime("%Y/%d/%m %H:%M:%S"), "B518", slot])
                    (result_dir / (name + "_" + stop.strftime("%Y-%m-%d_%H-%M-%S") + ".csv")).write_text(
                        content.getvalue(), encoding="utf-8",
                    )

                deadline = time.monotonic() + 12
                while time.monotonic() < deadline:
                    snapshot = app.rounds.snapshot()
                    if snapshot.result_available:
                        break
                    time.sleep(0.1)
                else:
                    app.rounds.stop()
                    self.fail("RS-WMT final-only files did not complete the App round")
                app.rounds.stop()

            snapshot = app.rounds.snapshot()
            self.assertEqual(snapshot.station, "BT")
            self.assertEqual([result.status for result in snapshot.results], ["PASS"] * 4)
            self.assertFalse(any(event.event.status == "TESTING" for event in snapshot.events))

    def test_station_specific_slot_counts_and_heights(self):
        # Existing migrated profiles retain their configured capacities.
        self.assertEqual(slot_count("DFU"), 7)
        self.assertEqual(slot_count("FCT"), 6)
        self.assertEqual(slot_count("BT"), 4)
        self.assertEqual(window_height(4), 502)
        self.assertEqual(window_height(6), 596)
        self.assertEqual(window_height(7), 643)
        self.assertEqual(window_height(20), 670)
        self.assertEqual(visible_detail_rows(20, 500), 2)
        self.assertGreaterEqual(WINDOW_WIDTH, 342 + 2 + 12)

    def test_all_display_statuses_have_explicit_colours(self):
        for status in ("PASS", "FAIL", "TESTING", "NOTEST", "WAITING", "COMPLETING", "STALLED", "STOPPED", "TIMEOUT"):
            self.assertRegex(STATUS_COLOURS[status], r"^#[0-9a-fA-F]{6}$")
        self.assertRegex(UNAVAILABLE_COLOUR, r"^#[0-9a-fA-F]{6}$")
        self.assertEqual(KVM_BLOCK_COUNT, 20)

    def test_kvm_band_separates_capacity_colours_from_unavailable_positions(self):
        self.assertEqual(kvm_block_colour(20, 20, "PASS"), STATUS_COLOURS["PASS"])
        self.assertEqual(kvm_block_colour(12, 12, "NOTEST"), STATUS_COLOURS["NOTEST"])
        self.assertEqual(kvm_block_colour(12, 13, "PASS"), UNAVAILABLE_COLOUR)
        self.assertEqual(kvm_block_colour(4, 4, "FAIL"), STATUS_COLOURS["FAIL"])
        self.assertEqual(kvm_block_colour(4, 5, "TESTING"), UNAVAILABLE_COLOUR)

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
        self.assertIsNone(configured_directory("/path/that/does/not/exist"))
        self.assertEqual(configured_directory("."), Path("."))

    def test_configured_directory_rejects_a_directory_without_read_access(self):
        with patch("b518_log_solution.os.access", return_value=False):
            self.assertIsNone(configured_directory("."))

    def test_operator_selects_project_and_machine_and_choice_survives_restart(self):
        with TemporaryDirectory() as temporary:
            app_root = Path(temporary) / "B518LogSolution"
            prefs = app_root / "preferences.json"
            with patch("b518_log_solution.APP_ROOT", app_root), patch("b518_log_solution.PREFS_PATH", prefs):
                root = tk.Tk()
                root.withdraw()
                app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey)
                try:
                    self.assertEqual(app.project_choice.cget("values"), ("B518", "B482"))
                    app.project.set("B482")
                    app._project_changed()
                    self.assertEqual(app.machine_choice.cget("values"), ("BT",))
                    profile = app.profiles.get(app.project.get(), app.station.get())
                    self.assertEqual(profile.platform, "b482")
                    profile_paths = dict(profile.paths)
                    profile_paths["final"] = temporary
                    profile_timeouts = dict(profile.timeouts)
                    profile_timeouts["round"] = 6300
                    app.profiles = app.profiles.with_profile(
                        replace(profile, paths=profile_paths, timeouts=profile_timeouts),
                    )
                    app._load_selected_profile_values()
                    self.assertEqual(app._timeout_seconds("BT")["round"], 6300)
                    app._save_preferences()
                finally:
                    app.hotkey.close()
                    root.destroy()

                restarted_root = tk.Tk()
                restarted_root.withdraw()
                restarted = B518LogSolutionApp(restarted_root, hotkey_factory=FakeHotkey)
                try:
                    self.assertEqual((restarted.project.get(), restarted.station.get()), ("B482", "BT"))
                    self.assertEqual(restarted._timeout_seconds("BT")["round"], 6300)
                    with patch("b518_log_solution.BtLogMonitor") as monitor_factory:
                        restarted.start_monitor()
                    self.assertEqual(monitor_factory.call_args.kwargs["round_timeout_seconds"], 6300)
                finally:
                    restarted.hotkey.close()
                    restarted_root.destroy()

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
                deadline = time.monotonic() + 3
                while not show_error.called and time.monotonic() < deadline:
                    root.update()
                    time.sleep(0.01)
            self.assertIsNone(app.monitor)
            self.assertEqual(app.monitor_state.cget("text"), "啟動失敗")
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

    def test_save_settings_persists_selected_project_machine_profile(self):
        saved_paths = {
            "DFU": {"active": "/logs/dfu/active", "final": "/logs/dfu/final", "caseinfo": ""},
            "FCT": {"active": "/logs/fct/active", "final": "/logs/fct/final", "caseinfo": ""},
            "BT": {"active": "", "final": "/logs/bt/testdata", "caseinfo": "/logs/bt/caseinfo"},
        }
        saved_timeouts = {
            "DFU": {"start": "30", "test": "480", "round": "7200"},
            "FCT": {"start": "30", "test": "480", "round": "7200"},
            "BT": {"start": "30", "test": "240", "round": "6300"},
        }
        with TemporaryDirectory() as temporary_directory:
            app_root = Path(temporary_directory) / "B518LogSolution"
            prefs_path = app_root / "preferences.json"
            with patch("b518_log_solution.APP_ROOT", app_root), patch("b518_log_solution.PREFS_PATH", prefs_path):
                interpreter = tk.Tcl()
                app = object.__new__(B518LogSolutionApp)
                app.station = tk.StringVar(master=interpreter, value="DFU")
                app.project = tk.StringVar(master=interpreter, value="B518")
                app.bt_format = tk.StringVar(master=interpreter, value="B482 TestData")
                app.settings_bt_format = tk.StringVar(master=interpreter, value="B518 RS-WMT")
                app.settings_project = tk.StringVar(master=interpreter, value="B518")
                app.profiles, _project, _machine = migrate_legacy_preferences({})
                app.profile_store = MachineProfileStore(prefs_path)
                app.profile_error = None
                app.paths = {station: {field: tk.StringVar(master=interpreter, value="")
                                       for field in ("active", "final", "caseinfo")}
                             for station in ("DFU", "FCT", "BT")}
                app.timeouts = {station: {field: tk.StringVar(master=interpreter, value="")
                                          for field in ("start", "test", "round")}
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
                app._refresh_machine_choices = lambda: None

                app._save_settings()
                self.assertEqual(app.station.get(), "BT")
                self.assertEqual(app.project.get(), "B518")
                for field, value in saved_paths["BT"].items():
                    self.assertEqual(app.paths["BT"][field].get(), value)
                saved = json.loads(prefs_path.read_text(encoding="utf-8"))
                self.assertEqual(saved["schema_version"], 1)
                self.assertEqual((saved["project"], saved["machine"]), ("B518", "BT"))
                restored = MachineProfileStore(prefs_path).load()
                self.assertEqual((restored[1], restored[2]), ("B518", "BT"))
                self.assertEqual(restored[0].get("B518", "BT").platform, "rswmt")
                self.assertEqual(restored[0].get("B518", "BT").paths["final"], saved_paths["BT"]["final"])
                self.assertEqual(restored[0].get("B518", "BT").timeouts["round"], 6300)

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
        app.bt_format = tk.StringVar(master=interpreter, value="B482 TestData")
        app.settings_bt_format = tk.StringVar(master=interpreter, value="B518 RS-WMT")
        app.settings_window = None
        app.settings_log = None
        app._close_settings()
        self.assertEqual(app.paths["DFU"]["active"].get(), "/before")
        self.assertEqual(app.bt_format.get(), "B482 TestData")

    def test_rswmt_selection_updates_draft_timeout_and_routes_monitor(self):
        root = tk.Tk()
        root.withdraw()
        with TemporaryDirectory() as folder, patch("b518_log_solution.PREFS_PATH", Path(folder) / 'prefs.json'):
            app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey)
            try:
                app.open_settings()
                app.settings_station.set('BT')
                app.settings_bt_format.set('B518 RS-WMT')
                app._bt_format_changed()
                self.assertEqual(app.settings_timeouts['BT']['start'].get(), '240')
                self.assertEqual(app.bt_format.get(), 'B482 TestData')
                app.settings_paths['BT']['final'].set(folder)
                with patch.object(app, '_save_preferences'):
                    app._save_settings()
                    with patch('b518_log_solution.RsWmtLogMonitor') as factory:
                        app.start_monitor()
                        self.wait_for(lambda: factory.called)
                        factory.assert_called_once()
                        self.assertEqual(factory.call_args.kwargs['start_timeout_seconds'], 240)
                        factory.return_value.start.assert_called_once()
                        app.rounds.stop()
            finally:
                app._close_settings()
                app.hotkey.close()
                root.destroy()

    def test_monitor_lifecycle_never_changes_window_topmost_attribute(self):
        monitor = MagicMock()
        app = object.__new__(B518LogSolutionApp)
        app.root = MagicMock()
        app.events = queue.Queue()
        app.rounds = RoundCoordinator(app.events.put)
        app.active_round_id = None
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
            self.wait_for(lambda: monitor.start.called)

        monitor.start.assert_called_once()
        self.assertIsNotNone(app.rounds.snapshot())
        self.assertEqual(app.rounds.snapshot().station, "DFU")
        app.root.attributes.assert_not_called()

        app._handle_event(MonitorEvent("finished", "monitor ended"))
        app.root.attributes.assert_not_called()
        app.rounds.stop()
        self.assertIsNone(app.monitor)

    def test_existing_monitor_sources_start_through_the_shared_round_entry(self):
        scenarios = (
            ("DFU", "B482 TestData", "AtlasActiveArchiveMonitor"),
            ("FCT", "B482 TestData", "AtlasActiveArchiveMonitor"),
            ("BT", "B482 TestData", "BtLogMonitor"),
            ("BT", "B518 RS-WMT", "RsWmtLogMonitor"),
        )
        for station, bt_format, factory_name in scenarios:
            with self.subTest(station=station, bt_format=bt_format):
                app = object.__new__(B518LogSolutionApp)
                app.root = MagicMock()
                app.events = queue.Queue()
                app.rounds = RoundCoordinator(app.events.put)
                app.active_round_id = None
                app.monitor = None
                app.station = SimpleNamespace(get=lambda: station)
                app.bt_format = SimpleNamespace(get=lambda: bt_format)
                app.paths = {name: {
                    "active": SimpleNamespace(get=lambda: "."),
                    "final": SimpleNamespace(get=lambda: "."),
                    "caseinfo": SimpleNamespace(get=lambda: ""),
                } for name in ("DFU", "FCT", "BT")}
                app.timeouts = {name: {
                    "start": SimpleNamespace(get=lambda: "30"),
                    "test": SimpleNamespace(get=lambda: "480"),
                } for name in ("DFU", "FCT", "BT")}
                app.start_button = MagicMock()
                app.monitor_state = MagicMock()
                app.event_lines = []
                app.settings_log = None
                app._save_preferences = MagicMock()
                app._reset_rows = MagicMock()
                app._set_monitor_controls = MagicMock()
                with patch("b518_log_solution." + factory_name) as factory:
                    app.start_monitor()
                    self.wait_for(lambda: factory.called)

                snapshot = app.rounds.snapshot()
                self.assertEqual(snapshot.station, station)
                self.assertEqual(snapshot.state, "RUNNING")
                factory.assert_called_once()
                factory.return_value.start.assert_called_once()
                app.rounds.stop()

    def test_repeated_app_start_keeps_the_round_and_does_not_reset_rows(self):
        app = object.__new__(B518LogSolutionApp)
        app.root = MagicMock()
        app.events = queue.Queue()
        app.rounds = RoundCoordinator(app.events.put)
        app.active_round_id = None
        app.monitor = None
        app.station = SimpleNamespace(get=lambda: "DFU")
        app.paths = {"DFU": {
            "active": SimpleNamespace(get=lambda: "."),
            "final": SimpleNamespace(get=lambda: "."),
            "caseinfo": SimpleNamespace(get=lambda: ""),
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
        with patch("b518_log_solution.AtlasActiveArchiveMonitor") as factory:
            app.start_monitor()
            first_round_id = app.active_round_id
            self.wait_for(lambda: factory.called)
            app.start_monitor()

        self.assertEqual(app.active_round_id, first_round_id)
        self.assertEqual(app.rounds.snapshot().state, "RUNNING")
        factory.assert_called_once()
        factory.return_value.start.assert_called_once()
        app._reset_rows.assert_called_once()
        app.rounds.stop()

    def test_queued_prior_round_event_cannot_change_the_new_round_ui(self):
        app = object.__new__(B518LogSolutionApp)
        app.root = MagicMock()
        app.events = queue.Queue()
        app.rounds = RoundCoordinator(app.events.put)
        app.active_round_id = None
        app.monitor = None
        app.station = SimpleNamespace(get=lambda: "DFU")
        app.paths = {"DFU": {
            "active": SimpleNamespace(get=lambda: "."),
            "final": SimpleNamespace(get=lambda: "."),
            "caseinfo": SimpleNamespace(get=lambda: ""),
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
        app._set_row = MagicMock()
        with patch("b518_log_solution.AtlasActiveArchiveMonitor") as factory:
            app.start_monitor()
            old_round_id = app.active_round_id
            self.wait_for(lambda: factory.called)
            app.rounds.stop()
            app.start_monitor()
            new_round_id = app.active_round_id
            self.wait_for(lambda: factory.call_count == 2)
            before = app.rounds.snapshot()
            messages_before_stale_event = list(app.event_lines)
            app._handle_event(RoundEvent(old_round_id, 99, MonitorEvent(
                "result", "stale PASS", 1, "TESTSERIAL0001", "PASS")))

        after = app.rounds.snapshot()
        self.assertNotEqual(old_round_id, new_round_id)
        self.assertEqual(after.results, before.results)
        self.assertEqual(after.result_available, before.result_available)
        self.assertEqual(app.event_lines, messages_before_stale_event)
        app._set_row.assert_not_called()
        self.assertEqual(factory.call_count, 2)
        app.rounds.stop()

    def test_final_result_brings_dashboard_to_front_without_permanent_topmost(self):
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
        app.root.deiconify.assert_called_once()
        app.root.lift.assert_called_once()
        app.root.focus_force.assert_called_once()

    def test_timeout_event_returns_dashboard_to_timeout_stopped_state(self):
        app = object.__new__(B518LogSolutionApp)
        app.root = MagicMock()
        app.monitor = SimpleNamespace(results={1: SimpleNamespace(sn="SN123", status="TIMEOUT")})
        app.event_lines = []
        app.settings_log = None
        app._set_row = MagicMock()
        app._set_monitor_controls = MagicMock()

        app._handle_event(MonitorEvent("timeout", "FCT 尚未開始測試逾時", status="TIMEOUT",
                                       detail={"kind": "start"}))

        app._set_row.assert_not_called()
        self.assertIsNone(app.monitor)
        app._set_monitor_controls.assert_called_once_with(False, "逾時停止")

    def test_test_timeout_keeps_monitoring_other_slots(self):
        app = object.__new__(B518LogSolutionApp)
        app.root = MagicMock()
        monitor = SimpleNamespace(results={2: SimpleNamespace(sn="SN123", status="TIMEOUT")})
        app.monitor = monitor
        app.event_lines = []
        app.settings_log = None
        app._set_row = MagicMock()
        app._set_monitor_controls = MagicMock()

        app._handle_event(MonitorEvent("timeout", "FCT slot2 測試逾時", 2, status="TIMEOUT",
                                       detail={"kind": "test"}))

        app._set_row.assert_called_once_with(2, "SN123", "TIMEOUT")
        self.assertIs(app.monitor, monitor)
        app._set_monitor_controls.assert_not_called()

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
