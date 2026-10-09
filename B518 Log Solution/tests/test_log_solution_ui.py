import csv
import io
import json
import os
import shutil
import tkinter as tk
import time
import threading
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from tkinter import font as tkfont, ttk
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from b518_log_solution import (
    B518LogSolutionApp, MAIN_FONT_SIZE, ROW_HEIGHT, STATUS_COLOURS,
    STATUS_TEMPLATE_STATES, UNAVAILABLE_COLOUR, WINDOW_WIDTH, KVM_BLOCK_COUNT, kvm_block_colour,
    sn_font_size, visible_detail_rows, window_height,
)
from global_hotkey import COMMAND_SHIFT_M_KEYCODE, COMMAND_SHIFT_MODIFIERS, GlobalHotkeyError, UnavailableHotkey, create_global_hotkey
from log_monitoring import MonitorEvent
from log_monitoring import BaseMonitor, SessionStore, SlotResult
from monitoring_round import (
    ConflictSide, RoundConflict, RoundCoordinator, RoundEvent, RoundSnapshot, RoundState,
)
import audit_records
import app_event_store
from audit_records import read_round_audit
from app_event_store import AppEventStore, read_app_event_store
from machine_profiles import MachineProfile, MachineProfileStore, ProfileCatalog, migrate_legacy_preferences
from language_catalog import DEFAULT_LANGUAGE, ENGLISH, TRADITIONAL_CHINESE


class FakeHotkey:
    available = True
    message = "available"

    def __init__(self, callback):
        self.callback = callback
        self.closed = False

    def close(self):
        self.closed = True


class ControlledConflictMonitor:
    """Publish same-round candidates through the real RoundCoordinator seam."""

    def __init__(self, callback):
        self.callback = callback
        self.results = {1: SlotResult(1), 2: SlotResult(2)}
        self.round_id = ""
        self.collection_stopped = False
        self.finished = False

    def update_round_settings(self, settings):
        self.round_id = settings["round_id"]

    def start(self):
        evidence = self._evidence("base", "2026-10-08T10:00:00")
        self.apply_round_result(1, "PASS", "SN-BASE", "/controlled/slot1/base.csv", evidence)
        self.apply_round_result(2, "TESTING", "SN-OTHER", "/controlled/slot2/active.csv",
                                self._evidence("other", "2026-10-08T10:00:01"))

    def _evidence(self, source_id, source_time):
        return {"round_evidence_id": "controlled-round-evidence",
                "source_id": source_id, "source_time": source_time,
                "source_position": "{}".format(source_id)}

    def offer_candidate(self, slot, sn, status, source, source_id, source_time):
        detail = self._evidence(source_id, source_time)
        event = MonitorEvent("result_candidate", "controlled candidate", slot, sn, status,
                             source, detail)
        decision = self.callback(event)
        if decision == "accept":
            self.apply_round_result(slot, status, sn, source, detail)
        return decision

    def round_results(self):
        return tuple(self.results.values())

    def timeout_seconds(self, _kind):
        return 3600

    def has_pending_review(self):
        return False

    def resolve_review(self, _choice):
        return None

    def publish_round_event(self, event):
        self.callback(event)

    def set_result(self, slot, status, detail=None, lock_terminal=False):
        self.apply_round_result(slot, status, self.results[slot].sn,
                                self.results[slot].source, detail, lock_terminal)

    def apply_round_result(self, slot, status, sn="", source="", detail=None, lock_terminal=False):
        result = self.results[slot]
        result.sn = sn or result.sn
        result.status = status
        result.source = source
        result.updated_at = "2026-10-08T10:00:00"
        self.callback(MonitorEvent("result", "controlled result", slot, result.sn, status,
                                   source, detail or {}))

    def poll_once(self):
        return None

    def stop_collection(self):
        self.collection_stopped = True

    def finish(self):
        self.collection_stopped = True
        self.finished = True

    def stop(self):
        if self.finished:
            return
        self.collection_stopped = True
        self.finished = True
        for result in self.results.values():
            if result.status not in {"PASS", "FAIL", "NOTEST", "STOPPED", "TIMEOUT"}:
                self.apply_round_result(result.slot, "STOPPED", result.sn, result.source)
        self.callback(MonitorEvent("stopped", "controlled source stopped"))


def install_snapshot_results(app, results):
    snapshot = SimpleNamespace(
        round_id="round-under-test", results=tuple(results), audit_complete=True,
        audit_errors=(), state=SimpleNamespace(value="RUNNING"),
    )
    app.active_round_id = snapshot.round_id
    app.rounds = MagicMock()
    app.rounds.snapshot.return_value = snapshot
    app._apply_round_snapshot = MagicMock()


def conflict_summary_rows(app):
    lines = app.conflict_comparison.get("1.0", "end-1c").splitlines()
    return [tuple(line.split("\t")[:3]) for line in lines]


class LogSolutionUiTests(unittest.TestCase):
    def setUp(self):
        self._isolated_app_root = TemporaryDirectory()
        self._app_event_stores = []
        app_root = Path(self._isolated_app_root.name)
        app_root_patcher = patch("b518_log_solution.APP_ROOT", app_root)
        preferences_patcher = patch("b518_log_solution.PREFS_PATH", app_root / "preferences.json")
        real_store = AppEventStore

        def create_store(*args, **kwargs):
            store = real_store(*args, **kwargs)
            self._app_event_stores.append(store)
            return store

        store_patcher = patch("b518_log_solution.AppEventStore", side_effect=create_store)
        app_root_patcher.start()
        preferences_patcher.start()
        store_patcher.start()
        self.addCleanup(app_root_patcher.stop)
        self.addCleanup(preferences_patcher.stop)
        self.addCleanup(store_patcher.stop)
        self.addCleanup(self._isolated_app_root.cleanup)
        self.addCleanup(self._settle_app_event_writes)

    def _settle_app_event_writes(self):
        for store in self._app_event_stores:
            deadline = time.monotonic() + 5
            while store.status().status == "saving" and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertNotEqual(store.status().status, "saving",
                                "App event write must finish before temporary data cleanup")
            store.stop()

    def wait_for(self, predicate, timeout=3):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.01)
        self.fail("Timed out waiting for asynchronous monitor preparation")

    def wait_for_archive_checks(self, coordinator, timeout=5):
        terminal_states = {"archived", "protected", "failed"}
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            statuses = coordinator.archive_statuses()
            if all(status.status in terminal_states for status in statuses):
                return statuses
            time.sleep(0.01)
        self.fail("Timed out waiting for public round archive statuses: {}".format(
            coordinator.archive_statuses()))

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_real_tk_app_diagnostic_is_bilingual_inspectable_and_saved_before_close(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            preferences = Path(temporary) / "preferences.json"
            profile_store = MachineProfileStore(preferences)
            profile_store.load()
            profile_store.save_language(ENGLISH)
            app_path = Path(temporary) / "app-events.json"
            root = tk.Tk()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey, session_root=Path(temporary) / "sessions",
                app_event_path=app_path,
                app_event_clock=lambda: datetime(2026, 10, 9, 2, 3, 4, tzinfo=timezone.utc),
            )

            def pump_until(predicate, timeout=5):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    root.update()
                    if predicate():
                        return
                    time.sleep(.01)
                self.fail("Timed out while pumping App event save UI")

            def root_destroyed():
                try:
                    return not root.winfo_exists()
                except tk.TclError:
                    return True

            try:
                root.update()
                original_preferences = preferences.read_bytes()
                x, y = app.language_button.winfo_width() // 2, app.language_button.winfo_height() // 2
                app.language_button.event_generate("<ButtonPress-1>", x=x, y=y)
                app.language_button.event_generate("<ButtonRelease-1>", x=x, y=y)
                root.update()
                chinese_index = next(
                    index for index in range(app.language_menu.index("end") + 1)
                    if app.language_menu.entrycget(index, "label") == "繁體中文")
                with patch("machine_profiles._atomic_write_text", side_effect=OSError("preference disk full")), \
                        patch("b518_log_solution.messagebox.showerror"):
                    app.language_menu.invoke(chinese_index)
                root.update()
                self.assertEqual(app.current_language, TRADITIONAL_CHINESE)
                self.assertIn("繁體中文", app.language_button.cget("text"))
                self.assertEqual(preferences.read_bytes(), original_preferences)
                self.assertIn("preference disk full", app.event_lines[-1])

                pump_until(lambda: app.rounds.app_event_status().complete)
                app.app_diagnostics_button.invoke()
                root.update()
                self.assertIsNotNone(app.app_diagnostics_window)
                detail_text = app.app_diagnostics_detail.get("1.0", "end-1c")
                self.assertIn("原始診斷", detail_text)
                self.assertIn("preference disk full", detail_text)
                saved = read_app_event_store(app_path)["events"]
                language_failure = next(item for item in saved
                                        if item["localized_message"]["message_id"] ==
                                        "app.language.preference_save_failed")
                self.assertEqual(language_failure["localized_message"]["en"],
                                 "Language changed for this session but could not be saved: preference disk full")
                self.assertEqual(language_failure["localized_message"]["zh-TW"],
                                 "語言已切換供本次使用，但保存失敗：preference disk full")
                self.assertNotIn("round_id", language_failure)

                app.close()
                pump_until(lambda: app.rounds.close_status().status == "complete")
                pump_until(root_destroyed)
                self.assertTrue(root_destroyed())
                rebuilt = read_app_event_store(app_path)
                self.assertTrue(any(item["event_id"] == language_failure["event_id"]
                                    for item in rebuilt["events"]))
            finally:
                if not root_destroyed():
                    app.hotkey.close()
                    app.app_events.stop()
                    root.destroy()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_real_tk_close_keeps_app_write_failure_open_and_retries_it(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            app_path = Path(temporary) / "app-events.json"
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey, session_root=Path(temporary) / "sessions",
                app_event_path=app_path,
            )

            def pump_until(predicate, timeout=5):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    root.update()
                    if predicate():
                        return
                    time.sleep(.01)
                self.fail("Timed out while pumping App save-before-close UI")

            def root_destroyed():
                try:
                    return not root.winfo_exists()
                except tk.TclError:
                    return True

            try:
                root.update()
                pump_until(lambda: app.rounds.app_event_status().complete)
                def fail_app_store(_path, _content):
                    raise OSError("app journal unavailable")

                with patch("app_event_store._atomic_replace", side_effect=fail_app_store):
                    x, y = app.language_button.winfo_width() // 2, app.language_button.winfo_height() // 2
                    app.language_button.event_generate("<ButtonPress-1>", x=x, y=y)
                    app.language_button.event_generate("<ButtonRelease-1>", x=x, y=y)
                    root.update()
                    chinese_index = next(
                        index for index in range(app.language_menu.index("end") + 1)
                        if app.language_menu.entrycget(index, "label") == "繁體中文")
                    with patch("machine_profiles._atomic_write_text",
                               side_effect=OSError("preference disk full")), \
                            patch("b518_log_solution.messagebox.showerror"):
                        app.language_menu.invoke(chinese_index)
                    event_record = next(item for item in app.rounds.app_event_records()
                                        if item["localized_message"]["message_id"] ==
                                        "app.language.preference_save_failed")
                    pump_until(lambda: app.rounds.app_event_status().status == "failed")
                    app.close()
                    pump_until(lambda: app.rounds.close_status().status == "failed")
                    pump_until(lambda: "app journal unavailable" in
                               app._close_error_label.cget("text"))
                    self.assertIn("App 診斷", app._close_status_label.cget("text"))
                    self.assertTrue(root.winfo_exists())
                    self.assertTrue(app._close_window.winfo_exists())

                button = app._close_retry_button
                x, y = button.winfo_width() // 2, button.winfo_height() // 2
                button.event_generate("<ButtonPress-1>", x=x, y=y)
                button.event_generate("<ButtonRelease-1>", x=x, y=y)
                pump_until(lambda: app.rounds.close_status().status == "complete")
                pump_until(root_destroyed)
                self.assertTrue(root_destroyed())
                events = read_app_event_store(app_path)["events"]
                self.assertEqual([item["localized_message"]["message_id"] for item in events],
                                 ["app.startup.started", "app.language.preference_save_failed"])
                self.assertEqual(events[1]["event_id"], event_record["event_id"])
                self.assertEqual(events[1]["diagnostic"], "preference disk full")
            finally:
                if not root_destroyed():
                    app.hotkey.close()
                    app.app_events.stop()
                    root.destroy()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_real_tk_hotkey_and_profile_failures_are_saved_and_inspectable(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            app_path = Path(temporary) / "app-events.json"
            app = B518LogSolutionApp(
                root, hotkey_factory=lambda _callback: UnavailableHotkey("shortcut already used"),
                session_root=Path(temporary) / "sessions", app_event_path=app_path,
            )

            def pump_until(predicate, timeout=5):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    root.update()
                    if predicate():
                        return
                    time.sleep(.01)
                self.fail("Timed out while pumping App diagnostic UI")

            def click(widget):
                x, y = widget.winfo_width() // 2, widget.winfo_height() // 2
                widget.event_generate("<ButtonPress-1>", x=x, y=y)
                widget.event_generate("<ButtonRelease-1>", x=x, y=y)
                root.update()

            def find_button(parent, label):
                for child in parent.winfo_children():
                    if isinstance(child, ttk.Button) and child.cget("text") == label:
                        return child
                    found = find_button(child, label)
                    if found is not None:
                        return found
                return None

            def root_destroyed():
                try:
                    return not root.winfo_exists()
                except tk.TclError:
                    return True

            try:
                with patch("b518_log_solution.messagebox.showwarning") as warning:
                    pump_until(lambda: warning.called)
                self.assertEqual(app.current_language, ENGLISH)
                self.assertTrue(any(
                    item.get("localized_message", {}).get("message_id") == "app.hotkey.unavailable"
                    for item in app.rounds.app_event_records()
                ))

                click(app.settings_button)
                app.profile_editor_project.set("Unsaved")
                with patch.object(app.profile_store, "save", side_effect=OSError("profile disk full")):
                    apply_button = find_button(app.settings_window, "Apply and Save")
                    self.assertIsNotNone(apply_button)
                    click(apply_button)
                self.assertIn("active configuration remains unchanged",
                              app.profile_editor_status.get())

                original_catalog = app.profiles.to_dict()
                original_selection = (app.project.get(), app.station.get())
                invalid_import = Path(temporary) / "invalid-profile.json"
                invalid_import.write_text("{", encoding="utf-8")
                import_button = find_button(app.settings_window, "Import Configuration")
                export_button = find_button(app.settings_window, "Export Configuration")
                self.assertIsNotNone(import_button)
                self.assertIsNotNone(export_button)
                pump_until(lambda: app.rounds.app_event_status().complete)
                with patch("b518_log_solution.filedialog.askopenfilename",
                           return_value=str(invalid_import)), \
                        patch("b518_log_solution.messagebox.showerror"):
                    click(import_button)
                self.assertEqual(app.profiles.to_dict(), original_catalog)
                self.assertEqual((app.project.get(), app.station.get()), original_selection)
                self.assertIn("saved configuration remains unchanged",
                              app.profile_editor_status.get())
                with patch("b518_log_solution.filedialog.asksaveasfilename",
                           return_value=str(Path(temporary) / "missing" / "export.json")), \
                        patch("b518_log_solution.messagebox.showerror"):
                    click(export_button)
                self.assertIn("could not be exported", app.profile_editor_status.get())
                app.language_button.event_generate("<Button-1>")
                root.update()
                chinese_index = next(
                    index for index in range(app.language_menu.index("end") + 1)
                    if app.language_menu.entrycget(index, "label") == "繁體中文"
                )
                app.language_menu.invoke(chinese_index)
                root.update()
                self.assertIn("無法匯出配置", app.profile_editor_status.get())
                self.assertIn("No such file or directory", app.profile_editor_status.get())
                app.language_button.event_generate("<Button-1>")
                root.update()
                app.language_menu.invoke(0)
                root.update()
                self.assertIn("could not be exported", app.profile_editor_status.get())
                self.assertIn("No such file or directory", app.profile_editor_status.get())
                app._close_settings()

                pump_until(lambda: app.rounds.app_event_status().complete)
                click(app.app_diagnostics_button)
                self.assertIsNotNone(app.app_diagnostics_window)
                rows = tuple(app.app_diagnostics_list.get(0, "end"))
                self.assertTrue(any("Global hotkey is unavailable" in row for row in rows), rows)
                self.assertTrue(any("active configuration remains unchanged" in row
                                    for row in rows), rows)
                stored = read_app_event_store(app_path)["events"]
                ids = [item["localized_message"]["message_id"] for item in stored]
                self.assertIn("app.startup.started", ids)
                self.assertIn("app.hotkey.unavailable", ids)
                self.assertIn("app.profile.save_failed", ids)
                self.assertIn("app.profile.import_failed", ids)
                self.assertIn("app.profile.export_failed", ids)
                self.assertTrue(all("round_id" not in item for item in stored))

                profile_index = next(index for index, row in enumerate(rows)
                                     if "active configuration remains unchanged" in row)
                app.app_diagnostics_list.selection_clear(0, "end")
                app.app_diagnostics_list.selection_set(profile_index)
                app.app_diagnostics_list.event_generate("<<ListboxSelect>>")
                root.update()
                detail = app.app_diagnostics_detail.get("1.0", "end-1c")
                self.assertIn("Configuration preferences could not be saved", detail)
                self.assertIn("profile disk full", detail)

                import_index = next(index for index, row in enumerate(rows)
                                    if "Configuration could not be imported" in row)
                app.app_diagnostics_list.selection_clear(0, "end")
                app.app_diagnostics_list.selection_set(import_index)
                app.app_diagnostics_list.event_generate("<<ListboxSelect>>")
                root.update()
                import_detail = app.app_diagnostics_detail.get("1.0", "end-1c")
                self.assertIn("Configuration could not be imported", import_detail)
                self.assertIn("JSON", import_detail)

                export_index = next(index for index, row in enumerate(rows)
                                    if "Configuration could not be exported" in row)
                app.app_diagnostics_list.selection_clear(0, "end")
                app.app_diagnostics_list.selection_set(export_index)
                app.app_diagnostics_list.event_generate("<<ListboxSelect>>")
                root.update()
                export_detail = app.app_diagnostics_detail.get("1.0", "end-1c")
                self.assertIn("Configuration could not be exported", export_detail)
                self.assertIn("missing", export_detail)

                # The journal's own failure is exposed in the real diagnostics window
                # after recovery, while complete remains the current save state.
                app._close_settings()
                click(app.settings_button)
                export_button = find_button(app.settings_window, "Export Configuration")
                with patch("b518_log_solution.filedialog.asksaveasfilename",
                           return_value=str(Path(temporary) / "missing-again" / "export.json")), \
                        patch("b518_log_solution.messagebox.showerror"), \
                        patch("app_event_store._atomic_replace",
                              side_effect=OSError("diagnostic journal disk full")):
                    click(export_button)
                    pump_until(lambda: app.rounds.app_event_status().status == "failed")
                pump_until(lambda: "diagnostic journal disk full" in
                           app.app_diagnostics_history.cget("text"))
                click(app.app_diagnostics_retry_button)
                pump_until(lambda: "diagnostic journal disk full" in
                           app.app_diagnostics_history.cget("text"))
                pump_until(lambda: app.rounds.app_event_status().complete and
                           "current status: complete" in
                           app.app_diagnostics_history.cget("text").lower())
                self.assertIn("complete", app.app_diagnostics_history.cget("text").lower())

                app.close()

                app.close()
                pump_until(lambda: app.rounds.close_status().status == "complete")
                pump_until(root_destroyed)
                rebuilt = read_app_event_store(app_path)["events"]
                self.assertEqual([item["sequence"] for item in rebuilt],
                                 list(range(1, len(rebuilt) + 1)))
            finally:
                if not root_destroyed():
                    app.hotkey.close()
                    app.app_events.stop()
                    root.destroy()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_real_tk_language_and_profile_controls_fit_fixed_hmi_width(self):
        for language in (ENGLISH, TRADITIONAL_CHINESE):
            with self.subTest(language=language), TemporaryDirectory() as temporary, \
                    patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
                store = MachineProfileStore(Path(temporary) / "preferences.json")
                store.load()
                store.save_language(language)
                root = tk.Tk()
                app = B518LogSolutionApp(
                    root, hotkey_factory=FakeHotkey, session_root=Path(temporary) / "sessions",
                    app_event_path=Path(temporary) / "app-events.json",
                )
                try:
                    root.update()
                    self.assertEqual(root.winfo_width(), WINDOW_WIDTH)
                    for widget in (app.language_button, app.project_label, app.project_choice,
                                   app.machine_label, app.machine_choice):
                        self.assertTrue(widget.winfo_ismapped(), widget.cget("text")
                                        if "text" in widget.keys() else str(widget))
                        self.assertGreaterEqual(widget.winfo_width(), widget.winfo_reqwidth())
                        self.assertGreaterEqual(widget.winfo_rootx(), root.winfo_rootx())
                        self.assertLessEqual(widget.winfo_rootx() + widget.winfo_width(),
                                             root.winfo_rootx() + root.winfo_width())
                        self.assertLessEqual(widget.winfo_rooty() + widget.winfo_height(),
                                             app.kvm_results.winfo_rooty())
                    x = app.language_button.winfo_rootx() + app.language_button.winfo_width() // 2
                    y = app.language_button.winfo_rooty() + app.language_button.winfo_height() // 2
                    self.assertEqual(root.winfo_containing(x, y), app.language_button)
                    self.assertEqual(app.kvm_state_marker.winfo_x(), 278)
                    self.assertEqual(app.kvm_state_marker.winfo_y(), 0)
                finally:
                    app.rounds.request_close()
                    self.wait_for(lambda: app.rounds.close_status().status == "complete")
                    app.hotkey.close()
                    root.destroy()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_real_tk_language_menu_switches_main_page_and_persists_across_app_instances(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            preferences = Path(temporary) / "preferences.json"
            source = Path(temporary) / "source"
            source.mkdir()
            events_path = source / "events.jsonl"
            events_path.write_text("", encoding="utf-8")
            root = tk.Tk()
            root.deiconify()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey, session_root=Path(temporary) / "sessions",
                app_event_path=Path(temporary) / "app-events.json",
            )
            try:
                profile = replace(
                    app.profiles.get("B518", "FCT"), project="SAMPLE", platform="sample-json",
                    capacity=2, paths={"active": str(source)}, mapping=((20, 1), (4, 2)),
                )
                app.profiles = app.profiles.with_profile(profile)
                app.project_choice.configure(values=app.profiles.projects)
                app.project.set("SAMPLE")
                app._project_changed()
                app.station.set("FCT")
                app._profile_changed()
                root.update()
                self.assertEqual(app.current_language, DEFAULT_LANGUAGE)
                self.assertEqual(app.language_button.cget("text"), "English ▾")
                self.assertEqual(
                    [app.language_menu.entrycget(index, "label")
                     for index in range(app.language_menu.index("end") + 1)],
                    ["English", "繁體中文"],
                )
                self.assertEqual(app.language_choice.get(), ENGLISH)
                self.assertEqual(app.settings_button.cget("text"), "Settings")
                self.assertEqual(app.project_label.cget("text"), "Project")
                self.assertEqual(app.kvm_result_title.cget("text"), "KVM RESULT")
                self.assertLessEqual(
                    app.language_button.winfo_x() + app.language_button.winfo_width(),
                    app.language_button.master.winfo_width(),
                )
                self.assertLess(app.language_button.winfo_rooty(), app.kvm_result_title.winfo_rooty())

                app.start_button.invoke()
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    root.update()
                    snapshot = app.rounds.snapshot()
                    if snapshot is not None and not snapshot.source_preparation_pending:
                        break
                    time.sleep(0.01)
                snapshot = app.rounds.snapshot()
                self.assertIsNotNone(snapshot)
                self.assertFalse(snapshot.source_preparation_pending)
                round_id = snapshot.round_id
                deadline = time.monotonic() + 2
                while (not any("FCT round start accepted" in line for line in app.event_lines)
                       and time.monotonic() < deadline):
                    root.update()
                    time.sleep(0.01)
                self.assertTrue(any("FCT round start accepted" in line
                                    for line in app.event_lines), app.event_lines)
                app.open_settings()
                root.update()
                self.assertIn("FCT round start accepted",
                              app.settings_log.get("1.0", "end-1c"))
                with events_path.open("a", encoding="utf-8") as event_file:
                    event_file.write(json.dumps({
                        "kind": "activity", "position": 20, "sn": "LANG000001",
                        "source_time": "2026-10-08T10:00:00+08:00", "batch_id": "language-ui",
                    }) + "\n")
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    root.update()
                    if (app.rounds.snapshot().results[0].status == "TESTING" and
                            app.status_rows[1]["status"].cget("text") == "TESTING"):
                        break
                    time.sleep(0.01)
                before_switch = app.rounds.snapshot()
                self.assertEqual(before_switch.results[0].status, "TESTING")
                session_path = app.rounds.session_path
                self.assertTrue(app.rounds.flush_session(timeout=3))
                self.assertTrue(app.rounds.flush_audit(timeout=3))
                audit_before_switch = (session_path / "audit.jsonl").read_bytes()
                audit_events = [json.loads(line) for line in audit_before_switch.decode(
                    "utf-8").splitlines() if json.loads(line).get("record_type") == "event"]
                session_events = [json.loads(line) for line in
                                  (session_path / "events.log").read_text(
                                      encoding="utf-8").splitlines()]
                audit_started = next(item for item in audit_events
                                     if item["kind"] == "round_started")
                session_started = next(item for item in session_events
                                       if item["message"] == audit_started["message"])
                self.assertEqual(session_started["localized_message"],
                                 audit_started["localized_message"])
                self.assertEqual(audit_started["localized_message"]["message_id"],
                                 "round.started")
                self.assertEqual(audit_started["round_id"], round_id)
                round_files_before_switch = tuple(sorted(
                    (path.relative_to(session_path), path.read_bytes())
                    for path in session_path.rglob("*") if path.is_file()
                ))

                # Exercise the visible menu button and the actual native menu entry.
                app.language_button.event_generate("<Button-1>")
                root.update()
                chinese_index = next(
                    index for index in range(app.language_menu.index("end") + 1)
                    if app.language_menu.entrycget(index, "label") == "繁體中文"
                )
                app.language_menu.invoke(chinese_index)
                root.update()
                deadline = time.monotonic() + 2
                while (not any("FCT 已接受開始本輪" in line for line in app.event_lines)
                       and time.monotonic() < deadline):
                    root.update()
                    time.sleep(0.01)
                self.assertEqual(app.current_language, TRADITIONAL_CHINESE)
                self.assertEqual(app.language_button.cget("text"), "繁體中文 ▾")
                self.assertEqual(app.settings_button.cget("text"), "設定")
                self.assertEqual(app.project_label.cget("text"), "專案")
                self.assertEqual(app.status_rows[1]["slot"].cget("text"), "通道 1")
                self.assertEqual(app.kvm_result_title.cget("text"), "KVM RESULT")
                self.assertTrue(any("FCT 已接受開始本輪" in line
                                    for line in app.event_lines),
                              (app.current_language, [
                                  (record[0], getattr(record[1], "message_id", None),
                                   app._render_event_record(record))
                                  for record in app._event_records
                              ], [(item.sequence, item.event.kind,
                                   getattr(item.event.localized_message, "message_id", None))
                                  for item in app.rounds.snapshot().events]))
                self.assertIn("FCT 已接受開始本輪",
                              app.settings_log.get("1.0", "end-1c"))
                after_switch = app.rounds.snapshot()
                self.assertEqual(after_switch.round_id, round_id)
                self.assertEqual(after_switch.results, before_switch.results)
                self.assertEqual(after_switch.events, before_switch.events)
                self.assertEqual(app.status_rows[1]["status"].cget("text"), "TESTING")
                self.assertEqual((session_path / "audit.jsonl").read_bytes(), audit_before_switch)
                self.assertEqual(round_files_before_switch, tuple(sorted(
                    (path.relative_to(session_path), path.read_bytes())
                    for path in session_path.rglob("*") if path.is_file()
                )))

                with events_path.open("a", encoding="utf-8") as event_file:
                    event_file.write("{invalid json}\n")
                deadline = time.monotonic() + 3
                while (not any("Sample JSON 來源記錄無效" in line for line in app.event_lines)
                       and time.monotonic() < deadline):
                    root.update()
                    time.sleep(0.01)
                self.assertTrue(any("Sample JSON 來源記錄無效" in line
                                    for line in app.event_lines), app.event_lines)
                self.assertTrue(any("Expecting property name" in line
                                    for line in app.event_lines), app.event_lines)
                self.assertTrue(app.rounds.flush_session(timeout=3))
                self.assertTrue(app.rounds.flush_audit(timeout=3))
                platform_audit_bytes = (session_path / "audit.jsonl").read_bytes()
                platform_audit = read_round_audit(session_path / "audit.jsonl")
                platform_warning = next(event for event in platform_audit["events"]
                                        if event.get("localized_message", {}).get("message_id") ==
                                        "platform.sample_json.invalid_record")
                self.assertEqual(platform_warning["round_id"], round_id)
                self.assertEqual(platform_warning["localized_message"]["diagnostic"],
                                 platform_warning["detail"]["raw_diagnostic"])
                self.assertIn("Expecting property name", platform_warning["detail"]["raw_diagnostic"])
                platform_session_warning = next(
                    event for event in (json.loads(line) for line in
                                        (session_path / "events.log").read_text(
                                            encoding="utf-8").splitlines())
                    if event.get("localized_message", {}).get("message_id") ==
                    "platform.sample_json.invalid_record")
                self.assertEqual(platform_session_warning["localized_message"],
                                 platform_warning["localized_message"])

                with events_path.open("a", encoding="utf-8") as event_file:
                    event_file.write(json.dumps({
                        "kind": "activity", "position": 4, "sn": "LANG000002",
                        "source_time": "2026-10-08T10:00:01+08:00", "batch_id": "language-ui",
                    }) + "\n")
                    event_file.write(json.dumps({
                        "kind": "final", "position": 20, "sn": "LANG000001", "status": "PASS",
                        "source_time": "2026-10-08T10:00:02+08:00", "batch_id": "language-ui",
                    }) + "\n")
                    event_file.write(json.dumps({
                        "kind": "final", "position": 20, "sn": "LANG-CANDIDATE", "status": "FAIL",
                        "source_time": "2026-10-08T10:00:03+08:00", "batch_id": "language-ui",
                    }) + "\n")
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    root.update()
                    if app.rounds.snapshot().state == RoundState.AWAITING_REVIEW:
                        break
                    time.sleep(0.01)
                self.assertEqual(app.rounds.snapshot().round_id, round_id)
                deadline = time.monotonic() + 2
                while (not any("same-round result conflict" in line
                               for line in app.event_lines) and time.monotonic() < deadline):
                    root.update()
                    time.sleep(0.01)
                conflicts_before_switch = app.rounds.snapshot().pending_conflicts
                self.assertEqual(len(conflicts_before_switch), 1)
                conflict_id = conflicts_before_switch[0].conflict_id
                self.assertEqual(preferences.exists(), True)

                saved = MachineProfileStore(preferences)
                saved.load()
                self.assertEqual(saved.language, TRADITIONAL_CHINESE)
                app._save_preferences()
                reloaded = MachineProfileStore(preferences)
                reloaded.load()
                self.assertEqual(reloaded.language, TRADITIONAL_CHINESE)

                platform_audit_before_language_refresh = (session_path / "audit.jsonl").read_bytes()
                app.language_button.event_generate("<space>")
                root.update()
                app.language_menu.event_generate("<Escape>")
                root.update()
                self.assertEqual(app.current_language, TRADITIONAL_CHINESE)
                app.language_button.event_generate("<space>")
                root.update()
                app.language_menu.invoke(0)
                root.update()
                self.assertEqual(app.current_language, ENGLISH)
                self.assertEqual(app.rounds.snapshot().state, RoundState.AWAITING_REVIEW)
                self.assertTrue(any("same-round result conflict" in line
                                    for line in app.event_lines), app.event_lines)
                self.assertTrue(any("Sample JSON source record is invalid" in line
                                    for line in app.event_lines), app.event_lines)
                self.assertTrue(any("Expecting property name" in line
                                    for line in app.event_lines), app.event_lines)
                self.assertEqual((session_path / "audit.jsonl").read_bytes(),
                                 platform_audit_before_language_refresh)
                self.assertEqual(app.status_rows[1]["slot"].cget("text"), "Slot 1")
                self.assertEqual(app.rounds.snapshot().pending_conflicts[0].conflict_id, conflict_id)
                saved_bytes = preferences.read_bytes()
                app.language_menu.invoke(0)
                self.assertEqual(preferences.read_bytes(), saved_bytes)
                with patch("machine_profiles._atomic_write_text", side_effect=OSError("disk full")), \
                        patch("b518_log_solution.messagebox.showerror") as show_error:
                    app.language_menu.invoke(chinese_index)
                self.assertEqual(app.current_language, TRADITIONAL_CHINESE)
                self.assertIn("繁體中文", app.language_button.cget("text"))
                self.assertIn("disk full", show_error.call_args.args[1])
                failed_write = MachineProfileStore(preferences)
                failed_write.load()
                self.assertEqual(failed_write.language, ENGLISH)
                app.conflict_window.deiconify()
                root.update()
                decision_button = app.resolve_conflict_candidate_button
                x, y = decision_button.winfo_width() // 2, decision_button.winfo_height() // 2
                decision_button.event_generate("<Enter>", x=x, y=y)
                decision_button.event_generate("<ButtonPress-1>", x=x, y=y)
                decision_button.event_generate("<ButtonRelease-1>", x=x, y=y)
                deadline = time.monotonic() + 2
                while (app.rounds.snapshot().pending_conflicts and time.monotonic() < deadline):
                    root.update()
                    time.sleep(0.01)
                self.assertFalse(app.rounds.snapshot().pending_conflicts)
                self.assertEqual(app.rounds.snapshot().results[0].status, "FAIL")
                self.assertTrue(app.rounds.flush_session(timeout=3))
                self.assertTrue(app.rounds.flush_audit(timeout=3))
                rebuilt_after_decision = read_round_audit(session_path / "audit.jsonl")
                decision = next(event for event in rebuilt_after_decision["events"]
                                if event["kind"] == "conflict_resolved")
                self.assertEqual(decision["localized_message"]["message_id"],
                                 "round.conflict.accepted_candidate")
                self.assertEqual(sum(event["kind"] == "conflict_resolved"
                                     for event in rebuilt_after_decision["events"]), 1)
                session_after_decision = [json.loads(line) for line in
                                          (session_path / "events.log").read_text(
                                              encoding="utf-8").splitlines()]
                session_decision = next(event for event in session_after_decision
                                        if event["message"] == decision["message"])
                self.assertEqual(session_decision["localized_message"],
                                 decision["localized_message"])
                second_root = tk.Tk()
                second_root.withdraw()
                second_app = B518LogSolutionApp(
                    second_root, hotkey_factory=FakeHotkey,
                    session_root=Path(temporary) / "sessions-2",
                )
                try:
                    self.assertEqual(second_app.current_language, ENGLISH)
                    self.assertEqual(second_app.language_button.cget("text"), "English ▾")
                finally:
                    second_app.rounds.request_close()
                    self.wait_for(lambda: second_app.rounds.close_status().status == "complete")
                    second_app.hotkey.close()
                    second_root.destroy()
            finally:
                snapshot = app.rounds.snapshot()
                if snapshot is not None:
                    for conflict in snapshot.pending_conflicts:
                        app.rounds.resolve_review(conflict.conflict_id, "keep_original")
                app.rounds.stop()
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    root.update()
                    snapshot = app.rounds.snapshot()
                    if snapshot is not None and snapshot.state == RoundState.STOPPED:
                        break
                    time.sleep(0.01)
                app.rounds.flush_session(timeout=3)
                app.rounds.flush_audit(timeout=3)
                self.wait_for_archive_checks(app.rounds)
                app.rounds.request_close()
                self.wait_for(lambda: app.rounds.close_status().status == "complete")
                self.wait_for(lambda: app.rounds.app_event_status().complete)
                self.wait_for(lambda: app.rounds.retention_cleanup_status().status in
                              {"complete", "failed"})
                self.wait_for_archive_checks(app.rounds)
                app.hotkey.close()
                app.app_events.stop()
                root.destroy()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_real_tk_unknown_saved_language_uses_english_and_shows_diagnostic(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"), \
                patch("b518_log_solution.messagebox.showwarning") as show_warning:
            preferences = Path(temporary) / "preferences.json"
            store = MachineProfileStore(preferences)
            catalog, project, machine, _error = store.load()
            store.save(catalog, project, machine)
            payload = json.loads(preferences.read_text(encoding="utf-8"))
            payload["language"] = "fr"
            preferences.write_text(json.dumps(payload), encoding="utf-8")
            root = tk.Tk()
            root.deiconify()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey, session_root=Path(temporary) / "sessions",
            )
            try:
                deadline = time.monotonic() + 2
                while not show_warning.called and time.monotonic() < deadline:
                    root.update()
                    time.sleep(0.01)
                self.assertEqual(app.current_language, ENGLISH)
                self.assertIsNone(app.profile_error)
                self.assertEqual(app.language_button.cget("text"), "English ▾")
                self.assertIn("unavailable", show_warning.call_args.args[1])
                self.assertEqual(
                    [app.language_menu.entrycget(index, "label")
                     for index in range(app.language_menu.index("end") + 1)],
                    ["English", "繁體中文"],
                )
            finally:
                app.rounds.request_close()
                self.wait_for(lambda: app.rounds.close_status().status == "complete")
                app.hotkey.close()
                root.destroy()

    def test_real_tk_global_retention_setting_validates_persists_and_preserves_round_files(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.withdraw()
            session_root = Path(temporary) / "sessions"
            round_path = session_root / "existing-round" / "session.json"
            round_path.parent.mkdir(parents=True)
            round_path.write_text('{"result": "preserve"}', encoding="utf-8")
            original_round_data = round_path.read_bytes()
            app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey, session_root=session_root)
            try:
                app.open_settings()
                self.assertEqual(app.retention_days_var.get(), "365")
                help_text = app.retention_help_label.cget("text")
                self.assertIn("full 24 hours", help_text)
                self.assertIn("next background cleanup", help_text)

                app.retention_days_var.set("730")
                app.retention_save_button.invoke()
                second_value = MachineProfileStore(Path(temporary) / "preferences.json")
                second_value.load()
                self.assertEqual(second_value.retention_days, 730)

                app.retention_days_var.set("180")
                app.retention_save_button.invoke()
                persisted = MachineProfileStore(Path(temporary) / "preferences.json")
                persisted.load()
                self.assertEqual(persisted.retention_days, 180)
                self.assertIn("next background cleanup", app.retention_status.get())

                valid_preferences = Path(temporary, "preferences.json").read_bytes()
                for invalid in ("", "not-a-number", "0", "-1"):
                    app.retention_days_var.set(invalid)
                    app.retention_save_button.invoke()
                    rejected = MachineProfileStore(Path(temporary) / "preferences.json")
                    rejected.load()
                    self.assertEqual(rejected.retention_days, 180)
                    self.assertEqual(Path(temporary, "preferences.json").read_bytes(), valid_preferences)
                    self.assertIn("positive integer", app.retention_status.get())

                app.retention_days_var.set("730")
                with patch.object(app.profile_store, "save_retention_days",
                                  side_effect=OSError("disk full")):
                    app.retention_save_button.invoke()
                failed = MachineProfileStore(Path(temporary) / "preferences.json")
                failed.load()
                self.assertEqual(failed.retention_days, 180)
                self.assertEqual(app.retention_effective_label.cget("text"),
                                 "Effective setting: 180 days")
                self.assertIn("Could not save", app.retention_status.get())
                self.assertEqual(round_path.read_bytes(), original_round_data)
                self.assertEqual(tuple(session_root.rglob("*")), (round_path.parent, round_path))
            finally:
                app._close_settings()
                app.rounds.request_close()
                self.wait_for(lambda: app.rounds.close_status().status == "complete")
                app.hotkey.close()
                root.destroy()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_real_tk_shows_startup_cleanup_summary_after_disk_deletion(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            session_root = Path(temporary) / "sessions"
            root = tk.Tk()
            root.withdraw()
            archived_at = datetime.now(timezone.utc) - timedelta(days=200)
            writer = RoundCoordinator(audit_root=session_root, wall_clock=lambda: archived_at)

            class OldRoundMonitor(BaseMonitor):
                def __init__(self, callback):
                    super().__init__("FCT", {}, (1,), callback=callback, session_root=session_root,
                                     now=lambda: archived_at, round_timeout_seconds=3600)
                    self.done = False

                def poll_once(self):
                    if not self.done:
                        self.done = True
                        self.set_result(1, "PASS", "SERIAL000001", "source.csv", {
                            "round_evidence_id": "tk-retention", "source_time": "2024-01-01T08:01:00",
                        })

            archived_round = writer.start("FCT", OldRoundMonitor, run_async=False)
            writer.poll_once()
            self.wait_for(lambda: writer.archive_status(archived_round.round_id) is not None and
                          writer.archive_status(archived_round.round_id).cleanup_eligible)
            archive_path = writer.archive_status(archived_round.round_id).path
            protected_files = {
                Path(temporary) / "manual-export.json": b'{"keep": true}',
                Path(temporary) / "source-log.txt": b"external source log",
            }
            for path, contents in protected_files.items():
                path.write_bytes(contents)

            app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey, session_root=session_root)
            try:
                app.open_settings()
                heartbeat = [0]

                def pump_ui():
                    heartbeat[0] += 1
                    root.after(10, pump_ui)

                root.after(0, pump_ui)
                deadline = time.monotonic() + 5
                while (time.monotonic() < deadline and
                       app.rounds.retention_cleanup_status().status not in {"complete", "failed"}):
                    root.update()
                    time.sleep(0.01)
                root.update()
                self.assertEqual(app.rounds.retention_cleanup_status().status, "complete",
                                 app.rounds.retention_cleanup_status())
                app._refresh_retention_cleanup_status()
                self.assertEqual(app.retention_cleanup_heading.cget("text"), "Background Cleanup Summary")
                self.assertIn("retained 1", app.retention_cleanup_status.get())
                self.assertTrue(archive_path.parent.exists())

                previous_count = len(app.rounds.retention_cleanup_summaries())
                app.retention_days_var.set("180")
                app.retention_save_button.invoke()
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    root.update()
                    summaries = app.rounds.retention_cleanup_summaries()
                    status = app.rounds.retention_cleanup_status()
                    if (len(summaries) > previous_count and status.status in {"complete", "failed"}):
                        break
                    time.sleep(0.01)
                root.update()
                self.assertEqual(app.rounds.retention_cleanup_status().status, "complete",
                                 app.rounds.retention_cleanup_status())
                self.assertFalse(archive_path.parent.exists())
                app._refresh_retention_cleanup_status()
                self.assertIn("deleted 1 rounds", app.retention_cleanup_status.get())
                persisted = MachineProfileStore(Path(temporary) / "preferences.json")
                persisted.load()
                self.assertEqual(persisted.retention_days, 180)
                for path, contents in protected_files.items():
                    self.assertEqual(path.read_bytes(), contents)
                self.assertFalse(archive_path.parent.exists())
                self.assertGreater(heartbeat[0], 1)
            finally:
                app._close_settings()
                app.rounds.request_close()
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline and app.rounds.close_status().status != "complete":
                    root.update()
                    time.sleep(0.01)
                app.hotkey.close()
                root.destroy()

    def test_real_tk_distinguishes_unsaved_saved_and_archived_round_states(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.withdraw()
            session_root = Path(temporary) / "sessions"
            app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey, session_root=session_root)
            now = datetime(2026, 10, 7, 10, 0, tzinfo=timezone(timedelta(hours=8)))
            rounds = RoundCoordinator(app.events.put, audit_root=session_root, wall_clock=lambda: now)

            class OneResultMonitor(BaseMonitor):
                def __init__(self, callback):
                    super().__init__("FCT", {}, (1,), callback=callback, session_root=session_root,
                                     now=lambda: now)
                    self.done = False

                def poll_once(self):
                    if not self.done:
                        self.done = True
                        self.set_result(1, "PASS", "SERIAL000001", "source.csv", {
                            "round_evidence_id": "tk-archive-round",
                            "source_time": "2026-10-07T10:01:00",
                        })

            try:
                app.rounds = rounds
                self.assertIn("0 unsaved", app.archive_status_label.cget("text"))
                started = rounds.start("FCT", OneResultMonitor, run_async=False)
                app.active_round_id = started.round_id
                app._apply_round_snapshot(rounds.snapshot())
                app._refresh_archive_statuses()
                self.assertIn("1 unsaved", app.archive_status_label.cget("text"))

                import round_archival
                original_replace = round_archival.os.replace

                def fail_archive_replace(source, destination):
                    if str(destination).endswith("round-archive.json"):
                        raise OSError("temporary archive fault")
                    return original_replace(source, destination)

                with patch.object(round_archival.os, "replace", side_effect=fail_archive_replace):
                    rounds.poll_once()
                    def archive_failure_visible():
                        app._refresh_archive_statuses()
                        return (rounds.archive_status(started.round_id).status == "failed" and
                                str(app.archive_retry_button["state"]) == "normal" and
                                "temporary archive fault" in app.archive_round_detail.cget("text"))
                    self.wait_for(archive_failure_visible)
                    self.assertIn("temporary archive fault", app.archive_round_detail.cget("text"))

                app.archive_retry_button.invoke()
                self.wait_for(lambda: rounds.archive_status(started.round_id).status == "archived")
                root.update()

                app._refresh_archive_statuses()
                self.assertIn(started.round_id, app.archive_round_detail.cget("text"))
                self.assertIn("Trusted Archive", app.archive_round_detail.cget("text"))
                self.assertIn("2026-10-07T10:00:00+08:00", app.archive_round_detail.cget("text"))
                self.assertEqual(app.status_rows[1]["status"].cget("text"), "PASS")
            finally:
                root.destroy()

    def test_real_tk_retry_button_recovers_disk_record_once_without_blocking_ui(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.withdraw()
            app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey,
                                     session_root=Path(temporary) / "sessions")
            coordinator = RoundCoordinator(app.events.put, audit_root=Path(temporary) / "sessions")
            holder = {}

            class Monitor:
                def __init__(self, callback):
                    self.callback = callback
                    self.session = SessionStore("tk-round", {}, Path(temporary) / "sessions")
                    self.results = (SlotResult(1),)

                def round_results(self):
                    return self.results

                def timeout_seconds(self, kind):
                    return {"start": 30, "test": 60, "round": 10}[kind]

                def update_round_settings(self, settings):
                    self.session.update_settings(settings)

                def publish_round_event(self, event):
                    self.session.enqueue_event(event.message, event.detail)
                    self.callback(event)

                def start(self):
                    pass

                def stop_collection(self):
                    pass

                def finish(self):
                    self.session.enqueue_finish()

                def stop(self):
                    self.callback(MonitorEvent("stopped", "stopped"))

                def poll_once(self):
                    pass

            try:
                self.assertEqual(app.save_status.cget("text"), "Waiting to save")
                app.rounds = coordinator
                started = coordinator.start("FCT", lambda callback: holder.setdefault(
                    "monitor", Monitor(callback)), run_async=False, capacity=1)
                app.active_round_id = started.round_id
                app._apply_round_snapshot(coordinator.snapshot())
                monitor = holder["monitor"]
                original_write = audit_records.os.write
                failed = threading.Event()
                retry_entered = threading.Event()
                release_retry = threading.Event()
                write_number = [0]

                def inject_fault(descriptor, content):
                    if b"tk_retry_probe" in content:
                        write_number[0] += 1
                        if write_number[0] == 1:
                            failed.set()
                            raise OSError("temporary disk fault")
                        if write_number[0] == 2:
                            retry_entered.set()
                            release_retry.wait(2)
                            raise OSError("disk still unavailable")
                    return original_write(descriptor, content)

                with patch.object(audit_records.os, "write", side_effect=inject_fault):
                    monitor.callback(MonitorEvent("tk_retry_probe", "persist from Tk"))
                    self.assertTrue(failed.wait(2))
                    deadline = time.monotonic() + 2
                    while (coordinator.snapshot().save_state != "failed" or
                           str(app.retry_save_button["state"]) != "normal") and time.monotonic() < deadline:
                        root.update()
                    self.assertEqual(coordinator.snapshot().save_state, "failed")
                    self.assertEqual(str(app.retry_save_button["state"]), "normal")
                    self.assertTrue(any("temporary disk fault" in line for line in app.event_lines))
                    coordinator.stop()

                    app.retry_save_button.invoke()
                    self.assertTrue(retry_entered.wait(2))
                    self.assertEqual(str(app.retry_save_button["state"]), "disabled")
                    ui_tick = threading.Event()
                    root.after(0, ui_tick.set)
                    root.update()
                    self.assertTrue(ui_tick.is_set())
                    app.retry_save_button.invoke()
                    self.assertEqual(write_number[0], 2)
                    release_retry.set()
                    deadline = time.monotonic() + 3
                    while (coordinator.snapshot().save_state != "failed" or
                           str(app.retry_save_button["state"]) != "normal") and time.monotonic() < deadline:
                        root.update()
                        time.sleep(0.01)
                    self.assertEqual(coordinator.snapshot().save_state, "failed")
                    self.assertEqual(str(app.retry_save_button["state"]), "normal")
                    ui_tick.clear()
                    root.after(0, ui_tick.set)
                    root.update()
                    self.assertTrue(ui_tick.is_set())
                    app.retry_save_button.invoke()
                    deadline = time.monotonic() + 3
                    while (coordinator.snapshot().save_state != "complete" or
                           "Saved Completely" not in app.save_status.cget("text")) and time.monotonic() < deadline:
                        root.update()
                        time.sleep(0.01)

                self.assertEqual(coordinator.snapshot().save_state, "complete")
                self.assertIn("Saved Completely", app.save_status.cget("text"))
                self.assertTrue(coordinator.flush_session(timeout=2))
                rebuilt = read_round_audit(coordinator.session_path / "audit.jsonl")
                self.assertEqual(len([event for event in rebuilt["events"]
                                      if event["kind"] == "tk_retry_probe"]), 1)
                recovery = next(event for event in rebuilt["events"]
                                if event["kind"] == "save_recovered")
                self.assertTrue(recovery["detail"]["recovered_errors"])
                self.assertTrue(rebuilt["audit_complete"])
                session_events = [json.loads(line) for line in
                                  (coordinator.session_path / "events.log").read_text(
                                      encoding="utf-8").splitlines()]
                self.assertTrue(any("保存復原" in event["message"] for event in session_events))
                self.assertTrue(coordinator.snapshot().save_history)
            finally:
                app.hotkey.close()
                root.destroy()

    def test_real_tk_can_select_and_retry_previous_round_without_changing_current_board(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.withdraw()
            session_root = Path(temporary) / "sessions"
            app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey, session_root=session_root)
            coordinator = RoundCoordinator(app.events.put, audit_root=session_root)
            app.rounds = coordinator
            monitors = []

            class Monitor:
                def __init__(self, callback, index):
                    self.callback = callback
                    self.session = SessionStore("tk-round-{}".format(index), {}, session_root)
                    self.results = (SlotResult(1),)

                def round_results(self):
                    return self.results

                def timeout_seconds(self, kind):
                    return {"start": 30, "test": 60, "round": 10}[kind]

                def update_round_settings(self, settings):
                    self.session.update_settings(settings)

                def publish_round_event(self, event):
                    self.session.enqueue_event(event.message, event.detail)
                    self.callback(event)

                def start(self):
                    pass

                def stop_collection(self):
                    pass

                def finish(self):
                    self.session.enqueue_finish()

                def stop(self):
                    self.callback(MonitorEvent("stopped", "stopped"))

                def poll_once(self):
                    pass

            def create(callback):
                monitor = Monitor(callback, len(monitors))
                monitors.append(monitor)
                return monitor

            def pump_until(predicate, timeout=4):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    root.update()
                    if predicate():
                        return True
                    time.sleep(0.01)
                return predicate()

            try:
                previous = coordinator.start("FCT", create, run_async=False, capacity=1)
                app.active_round_id = previous.round_id
                app._apply_round_snapshot(previous)
                self.assertTrue(coordinator.flush_audit())
                self.assertTrue(coordinator.flush_session())
                original_write = audit_records.os.write
                first_failure = threading.Event()

                def fail_once(descriptor, content):
                    if b"cross_round_ui_probe" in content:
                        first_failure.set()
                        raise OSError("temporary previous round UI fault")
                    return original_write(descriptor, content)

                with patch.object(audit_records.os, "write", side_effect=fail_once):
                    monitors[0].callback(MonitorEvent("cross_round_ui_probe", "old result only"))
                    self.assertTrue(first_failure.wait(2))
                    self.assertTrue(pump_until(lambda: coordinator.round_snapshot(
                        previous.round_id).save_state == "failed"))

                coordinator.stop()
                current = coordinator.start("FCT", create, run_async=False, capacity=1)
                app.active_round_id = current.round_id
                app._apply_round_snapshot(current)
                app._refresh_unsaved_rounds()
                self.assertEqual(
                    app._unsaved_round_ids[app.unsaved_round_choice.get()], previous.round_id,
                )
                label = next(label for label, round_id in app._unsaved_round_ids.items()
                             if round_id == previous.round_id)
                app.unsaved_round_choice.set(label)
                app._update_selected_round_retry()
                self.assertEqual(str(app.unsaved_round_retry_button["state"]), "normal")
                self.assertIn("temporary previous round UI fault",
                              app.unsaved_round_detail.cget("text"))

                retry_entered = threading.Event()
                release_retry = threading.Event()
                attempts = []

                def pause_old_retry(descriptor, content):
                    if b"cross_round_ui_probe" in content:
                        attempts.append(content)
                        retry_entered.set()
                        release_retry.wait(3)
                    return original_write(descriptor, content)

                with patch.object(audit_records.os, "write", side_effect=pause_old_retry):
                    app.unsaved_round_retry_button.invoke()
                    self.assertTrue(retry_entered.wait(2))
                    self.assertEqual(str(app.unsaved_round_retry_button["state"]), "disabled")
                    ui_tick = threading.Event()
                    root.after(0, ui_tick.set)
                    root.update()
                    self.assertTrue(ui_tick.is_set())
                    app.unsaved_round_retry_button.invoke()
                    self.assertEqual(len(attempts), 1)
                    release_retry.set()
                    self.assertTrue(pump_until(
                        lambda: coordinator.round_snapshot(previous.round_id) is None and
                        previous.round_id not in app._unsaved_round_ids.values()))

                rebuilt = read_round_audit(monitors[0].session.path / "audit.jsonl")
                probe = [event for event in rebuilt["events"]
                         if event["kind"] == "cross_round_ui_probe"]
                self.assertTrue(rebuilt["audit_complete"])
                self.assertEqual(len(probe), 1)
                self.assertEqual(probe[0]["round_id"], previous.round_id)
                self.assertEqual(app.active_round_id, current.round_id)
                self.assertEqual(coordinator.snapshot().round_id, current.round_id)
                self.assertTrue(all(result.status == "WAITING"
                                    for result in coordinator.snapshot().results))
                self.assertNotIn(previous.round_id, app._unsaved_round_ids.values())
            finally:
                coordinator.stop()
                coordinator.flush_audit()
                coordinator.flush_session()
                app.hotkey.close()
                root.destroy()

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
            round_id = None
            try:
                app.open_settings()
                app.profile_editor_capacity.set("3")
                app.profile_editor_mapping.set("1:3, 2:2, 3:1")
                app.profile_editor_paths["active"].set(str(active))
                app.profile_editor_paths["final"].set(str(final))
                app._apply_profile_editor()
                app.start_button.invoke()

                preparation_deadline = time.monotonic() + 3
                while app.rounds.session_path is None and time.monotonic() < preparation_deadline:
                    root.update()
                    time.sleep(0.01)

                self.assertIsNotNone(app.rounds.session_path)
                round_id = app.rounds.snapshot().round_id
                while (app.rounds.snapshot().source_preparation_pending and
                       time.monotonic() < preparation_deadline):
                    root.update()
                    time.sleep(0.01)
                self.assertFalse(app.rounds.snapshot().source_preparation_pending)
                while (not (app.rounds.session_path / "audit.jsonl").is_file() and
                       time.monotonic() < preparation_deadline):
                    root.update()
                    time.sleep(0.01)
                self.assertEqual(app.active_profile_snapshot.capacity, 3)
                self.assertEqual(len(app.status_rows), 3)
                session_metadata = json.loads((app.rounds.session_path / "session.json").read_text(
                    encoding="utf-8"))
                self.assertEqual(session_metadata["settings"]["profile_snapshot"]["profile"]["mapping"], [
                    {"source": 1, "display": 3},
                    {"source": 2, "display": 2},
                    {"source": 3, "display": 1},
                ])
                self.assertTrue(app.rounds.flush_audit(timeout=3))
                rebuilt_audit = read_round_audit(app.rounds.session_path / "audit.jsonl")
                self.assertTrue(rebuilt_audit["audit_complete"])
                profile_snapshot = session_metadata["settings"]["profile_snapshot"]["profile"]
                audit_config = rebuilt_audit["round"]["config"]
                self.assertEqual(audit_config["config_snapshot"], profile_snapshot)
                self.assertEqual(audit_config["mapping"], [
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

                archive_stamp = (datetime.now() + timedelta(seconds=1)).strftime("%Y%m%d_%H-%M-%S")
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

                ui_deadline = time.monotonic() + 2
                while time.monotonic() < ui_deadline:
                    root.update()
                    if app.status_rows[3]["status"].cget("text") == "PASS":
                        break
                    time.sleep(0.02)
                self.assertEqual(app.status_rows[3]["status"].cget("text"), "PASS")
                self.assertEqual(app.kvm_result_blocks[3].cget("background"), STATUS_COLOURS["PASS"])
                self.assertEqual(app.kvm_result_blocks[4].cget("background"), UNAVAILABLE_COLOUR)

                app.stop_monitor()
                stop_deadline = time.monotonic() + 2
                while time.monotonic() < stop_deadline:
                    root.update()
                    if app.rounds.snapshot().state == "STOPPED":
                        break
                    time.sleep(0.02)
                self.assertEqual(app.rounds.snapshot().state, "STOPPED")
                app._drain_events()
                root.update_idletasks()
                self.assertEqual(app._display_capacity(), 3)
                self.assertEqual(app.kvm_result_blocks[4].cget("background"), UNAVAILABLE_COLOUR)
            finally:
                if app._round_is_active():
                    app.rounds.stop()
                app.rounds.flush_session(timeout=3)
                app.rounds.flush_audit(timeout=3)
                statuses = self.wait_for_archive_checks(app.rounds)
                if round_id is not None:
                    self.assertEqual(app.rounds.archive_status(round_id).status, "archived", statuses)
                app._close_settings()
                app.hotkey.close()
                root.destroy()

    def test_real_tk_shortcuts_start_rounds_with_session_and_audit_profile_evidence(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.deiconify()
            active = Path(temporary) / "active"
            final = Path(temporary) / "final"
            active.mkdir()
            final.mkdir()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey, session_root=Path(temporary) / "sessions",
            )
            app.open_settings()
            app.profile_editor_machine.set("FCT")
            app.profile_editor_paths["active"].set(str(active))
            app.profile_editor_paths["final"].set(str(final))
            app._apply_profile_editor()
            app._close_settings()
            started_round_ids = []

            def pump_until(predicate, timeout=5):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    root.update()
                    if predicate():
                        return
                    time.sleep(0.01)
                self.fail("Timed out waiting for the Tk start entry")

            def verify_started_round(previous_round_id):
                pump_until(lambda: app.rounds.snapshot() is not None and
                           app.rounds.snapshot().round_id != previous_round_id and
                           app.rounds.session_path is not None)
                pump_until(lambda: not app.rounds.snapshot().source_preparation_pending and
                           (app.rounds.session_path / "audit.jsonl").is_file())
                snapshot = app.rounds.snapshot()
                started_round_ids.append(snapshot.round_id)
                session_path = app.rounds.session_path
                session_metadata = json.loads((session_path / "session.json").read_text(
                    encoding="utf-8"))
                self.assertEqual(snapshot.station, "FCT")
                self.assertEqual(app._display_capacity(), 6)
                self.assertTrue(app.rounds.flush_audit(timeout=3))
                rebuilt = read_round_audit(session_path / "audit.jsonl")
                self.assertTrue(rebuilt["audit_complete"])
                session_profile = session_metadata["settings"]["profile_snapshot"]["profile"]
                audit_config = rebuilt["round"]["config"]
                self.assertEqual(audit_config["config_snapshot"], session_profile)
                self.assertEqual(audit_config["mapping"], session_profile["mapping"])
                return snapshot.round_id

            try:
                root.focus_force()
                root.update()
                self.assertEqual(root.focus_get(), root)
                prior = app.rounds.snapshot()
                previous_round_id = prior.round_id if prior else None
                root.event_generate("<Command-Shift-M>")
                first_round_id = verify_started_round(previous_round_id)
                app.rounds.stop()
                pump_until(lambda: app.rounds.snapshot().state == RoundState.STOPPED)
                self.assertTrue(app.rounds.flush_session(timeout=3))
                self.assertTrue(app.rounds.flush_audit(timeout=3))

                app.hotkey.callback()
                second_round_id = verify_started_round(first_round_id)
                self.assertNotEqual(first_round_id, second_round_id)
                app.rounds.stop()
                pump_until(lambda: app.rounds.snapshot().state == RoundState.STOPPED)
                self.assertTrue(app.rounds.flush_session(timeout=3))
                self.assertTrue(app.rounds.flush_audit(timeout=3))
            finally:
                app.rounds.stop()
                app.rounds.flush_session(timeout=3)
                app.rounds.flush_audit(timeout=3)
                self.wait_for_archive_checks(app.rounds)
                for round_id in started_round_ids:
                    self.assertEqual(app.rounds.archive_status(round_id).status, "archived")
                app._close_settings()
                app.hotkey.close()
                root.destroy()

    def test_real_tk_start_button_prepares_every_registered_platform_profile(self):
        with TemporaryDirectory() as temporary:
            scenarios = (
                ("B518", "DFU", "atlas", {"active": "active", "final": "final"}),
                ("B518", "FCT", "atlas", {"active": "active", "final": "final"}),
                ("B482", "BT", "b482", {"final": "final", "caseinfo": "caseinfo"}),
                ("B518", "BT", "rswmt", {"final": "final", "caseinfo": ""}),
                ("SAMPLE", "FCT", "sample-json", {"active": "active"}),
            )
            for index, (project, machine, platform, configured_paths) in enumerate(scenarios):
                with self.subTest(project=project, machine=machine, platform=platform):
                    case_root = Path(temporary) / str(index)
                    paths = {}
                    for field, relative in configured_paths.items():
                        if not relative:
                            paths[field] = relative
                            continue
                        path = case_root / relative
                        path.mkdir(parents=True)
                        if platform == "sample-json":
                            (path / "events.jsonl").write_text("", encoding="utf-8")
                        paths[field] = str(path)
                    with patch("b518_log_solution.PREFS_PATH", case_root / "preferences.json"):
                        root = tk.Tk()
                        root.deiconify()
                        app = B518LogSolutionApp(
                            root, hotkey_factory=FakeHotkey, session_root=case_root / "sessions",
                        )
                        if platform == "sample-json":
                            app.profiles = app.profiles.with_profile(replace(
                                app.profiles.get("B518", "FCT"), project=project,
                                platform=platform, capacity=2, paths=paths,
                                mapping=((20, 1), (4, 2)),
                            ))
                            app.project_choice.configure(values=app.profiles.projects)
                        else:
                            existing = app.profiles.get(project, machine)
                            updates = {"paths": paths}
                            if platform == "b482":
                                updates["mapping"] = ((1, 3), (2, 2), (3, 1), (4, 4))
                            app.profiles = app.profiles.with_profile(replace(
                                existing, **updates,
                            ))
                        app.project.set(project)
                        app._project_changed()
                        app.station.set(machine)
                        app._profile_changed()
                        root.update_idletasks()
                        round_id = None

                        def pump_until(predicate, timeout=5):
                            deadline = time.monotonic() + timeout
                            while time.monotonic() < deadline:
                                root.update()
                                if predicate():
                                    return
                                time.sleep(0.01)
                            self.fail("Timed out preparing {} / {} through Tk; snapshot={!r}; "
                                      "events={!r}; profile_error={!r}".format(
                                          project, machine, app.rounds.snapshot(), app.event_lines,
                                          app.profile_error))

                        def select_language(label):
                            app.language_button.event_generate("<Button-1>")
                            root.update()
                            menu_index = next(
                                item for item in range(app.language_menu.index("end") + 1)
                                if app.language_menu.entrycget(item, "label") == label
                            )
                            app.language_menu.invoke(menu_index)
                            root.update()

                        def verify_round_event_language_refresh(event_record):
                            localized = event_record["localized_message"]
                            pump_until(lambda: any(localized["en"] in line
                                                   for line in app.event_lines))
                            state_before = app.rounds.snapshot()
                            audit_before = (session_path / "audit.jsonl").read_bytes()
                            select_language("繁體中文")
                            self.assertTrue(any(localized["zh-TW"] in line
                                                for line in app.event_lines), app.event_lines)
                            self.assertEqual(app.rounds.snapshot().round_id, state_before.round_id)
                            self.assertEqual(app.rounds.snapshot().results, state_before.results)
                            self.assertEqual(app.rounds.snapshot().events, state_before.events)
                            self.assertEqual((session_path / "audit.jsonl").read_bytes(), audit_before)
                            select_language("English")
                            self.assertTrue(any(localized["en"] in line
                                                for line in app.event_lines), app.event_lines)
                            self.assertEqual(app.rounds.snapshot().events, state_before.events)
                            self.assertEqual((session_path / "audit.jsonl").read_bytes(), audit_before)

                        try:
                            selected_profile = app.profiles.get(project, machine)
                            self.assertEqual(app._display_capacity(), selected_profile.capacity)
                            app.start_button.invoke()
                            pump_until(lambda: app.rounds.snapshot() is not None and
                                       app.rounds.session_path is not None and
                                       not app.rounds.snapshot().source_preparation_pending)
                            snapshot = app.rounds.snapshot()
                            round_id = snapshot.round_id
                            session_path = app.rounds.session_path
                            session_metadata = json.loads((session_path / "session.json").read_text(
                                encoding="utf-8"))
                            session_profile = session_metadata["settings"]["profile_snapshot"]["profile"]
                            self.assertEqual(session_profile["platform"], platform)
                            self.assertEqual(snapshot.station, machine)
                            self.assertEqual(app._display_capacity(), session_profile["capacity"])
                            self.assertEqual(tuple(app.status_rows),
                                             tuple(range(1, session_profile["capacity"] + 1)))
                            self.assertTrue(app.rounds.flush_audit(timeout=3))
                            pump_until(lambda: (session_path / "audit.jsonl").is_file())
                            rebuilt = read_round_audit(session_path / "audit.jsonl")
                            self.assertTrue(rebuilt["audit_complete"])
                            audit_config = rebuilt["round"]["config"]
                            self.assertEqual(audit_config["config_snapshot"], session_profile)
                            self.assertEqual(audit_config["platform"], platform)
                            self.assertEqual(audit_config["mapping"], session_profile["mapping"])
                            if platform in {"atlas", "b482", "rswmt", "sample-json"}:
                                diagnostic = "controlled {} source diagnostic".format(platform)
                                if platform == "atlas":
                                    import monitoring_files

                                    source_file = (Path(paths["active"]) / "group0-slot1" /
                                                   "system" / "records.csv")
                                    source_file.parent.mkdir(parents=True)
                                    source_file.write_text("MLB_SN,status\n", encoding="utf-8")
                                    failure = patch.object(
                                        monitoring_files.csv, "DictReader",
                                        side_effect=csv.Error(diagnostic),
                                    )
                                    expected_message_id = "platform.atlas.source_error"
                                elif platform == "b482":
                                    import b482_source_adapter

                                    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
                                    source_file = (Path(paths["final"]) /
                                                   datetime.now().strftime("%Y-%m-%d") /
                                                   "PASSED" /
                                                   "[Thread0][cfg][B482SAMPLE0001]"
                                                   "[PASSED][{}].csv".format(stamp))
                                    source_file.parent.mkdir(parents=True)
                                    source_file.write_text(
                                        "SerialNumber,Unit Number,Test Pass/Fail Status,"
                                        "StartTime,EndTime\n"
                                        "B482SAMPLE0001,0,PASSED,start,end\n",
                                        encoding="utf-8",
                                    )
                                    original_signature = b482_source_adapter.file_signature

                                    def fail_b482_signature(path):
                                        if path == source_file:
                                            raise OSError(diagnostic)
                                        return original_signature(path)

                                    failure = patch(
                                        "b482_source_adapter.file_signature",
                                        side_effect=fail_b482_signature,
                                    )
                                    expected_message_id = "platform.b482.source_error"
                                elif platform == "rswmt":
                                    source_file = Path(paths["final"]) / "controlled-source.log"
                                    source_file.write_text("controlled source\n", encoding="utf-8")
                                    original_read_text = Path.read_text

                                    def fail_rswmt_diagnostic(path, *args, **kwargs):
                                        if path == source_file:
                                            raise OSError(diagnostic)
                                        return original_read_text(path, *args, **kwargs)

                                    failure = patch.object(
                                        Path, "read_text", fail_rswmt_diagnostic,
                                    )
                                    expected_message_id = "platform.rswmt.warning"
                                else:
                                    source_file = Path(paths["active"]) / "events.jsonl"
                                    original_open = Path.open

                                    def fail_sample_json_read(path, *args, **kwargs):
                                        mode = kwargs.get("mode", args[0] if args else "r")
                                        if path == source_file and mode == "rb":
                                            raise OSError(diagnostic)
                                        return original_open(path, *args, **kwargs)

                                    failure = patch.object(Path, "open", fail_sample_json_read)
                                    expected_message_id = "platform.sample_json.unreadable"

                                with failure:
                                    pump_until(lambda: any(
                                        diagnostic in line for line in app.event_lines
                                    ))
                                self.assertTrue(app.rounds.flush_session(timeout=3))
                                self.assertTrue(app.rounds.flush_audit(timeout=3))
                                event_records = read_round_audit(
                                    session_path / "audit.jsonl")["events"]
                                platform_event = next(
                                    event for event in event_records
                                    if event.get("localized_message", {}).get("message_id") ==
                                    expected_message_id
                                )
                                self.assertEqual(platform_event["round_id"], round_id)
                                self.assertIn(
                                    diagnostic,
                                    platform_event["localized_message"]["diagnostic"],
                                )
                                raw_diagnostic = platform_event["detail"].get(
                                    "raw_diagnostic", platform_event["detail"].get("raw_error", ""),
                                )
                                self.assertIn(diagnostic, raw_diagnostic)
                                self.assertTrue(any(
                                    platform_event["localized_message"]["en"] in line
                                    for line in app.event_lines
                                ), app.event_lines)
                                session_event = next(
                                    event for event in (json.loads(line) for line in
                                        (session_path / "events.log").read_text(
                                            encoding="utf-8").splitlines())
                                    if event.get("localized_message", {}).get("message_id") ==
                                    expected_message_id
                                )
                                self.assertEqual(
                                    session_event["localized_message"],
                                    platform_event["localized_message"],
                                )
                                before_language_refresh = (
                                    session_path / "audit.jsonl").read_bytes()
                                state_before_language_refresh = app.rounds.snapshot()
                                app.language_button.event_generate("<Button-1>")
                                root.update()
                                chinese_index = next(
                                    menu_index for menu_index in range(
                                        app.language_menu.index("end") + 1)
                                    if app.language_menu.entrycget(menu_index, "label") ==
                                    "繁體中文"
                                )
                                app.language_menu.invoke(chinese_index)
                                root.update()
                                self.assertEqual(
                                    app.rounds.snapshot().round_id, round_id,
                                )
                                self.assertEqual(
                                    app.rounds.snapshot().results,
                                    state_before_language_refresh.results,
                                )
                                self.assertEqual(
                                    app.rounds.snapshot().events,
                                    state_before_language_refresh.events,
                                )
                                self.assertTrue(any(
                                    platform_event["localized_message"]["zh-TW"] in line
                                    for line in app.event_lines
                                ), app.event_lines)
                                self.assertEqual(
                                    (session_path / "audit.jsonl").read_bytes(),
                                    before_language_refresh,
                                )
                                app.language_button.event_generate("<Button-1>")
                                root.update()
                                english_index = next(
                                    menu_index for menu_index in range(
                                        app.language_menu.index("end") + 1)
                                    if app.language_menu.entrycget(menu_index, "label") ==
                                    "English"
                                )
                                app.language_menu.invoke(english_index)
                                root.update()
                                self.assertTrue(any(
                                    platform_event["localized_message"]["en"] in line
                                    for line in app.event_lines
                                ), app.event_lines)
                                self.assertEqual(
                                    app.rounds.snapshot().events,
                                    state_before_language_refresh.events,
                                )
                                self.assertEqual(
                                    (session_path / "audit.jsonl").read_bytes(),
                                    before_language_refresh,
                                )
                            if platform == "b482":
                                created_at = datetime.now().replace(microsecond=0)
                                stamp = created_at.strftime("%Y%m%d%H%M%S")
                                date_folder = created_at.strftime("%Y-%m-%d")
                                result = (Path(paths["final"]) / date_folder / "PASSED" /
                                          "[Thread0][cfg][B482SAMPLE0001][PASSED][{}].csv".format(stamp))
                                result.parent.mkdir(parents=True, exist_ok=True)
                                result.write_text(
                                    "SerialNumber,Unit Number,Test Pass/Fail Status,StartTime,EndTime\n"
                                    "B482SAMPLE0001,0,PASSED,start,end\n", encoding="utf-8",
                                )
                                pump_until(lambda: app.rounds.snapshot().results[2].status == "PASS" and
                                           app.status_rows[3]["status"].cget("text") == "PASS" and
                                           app.status_rows[3]["sn"].cget("text") == "B482SAMPLE0001",
                                           timeout=10)
                                self.assertEqual(app.status_rows[3]["sn"].cget("text"),
                                                 "B482SAMPLE0001")
                                self.assertEqual(app.status_rows[3]["status"].cget("text"), "PASS")
                                self.assertTrue(app.rounds.flush_session(timeout=3))
                                self.assertTrue(app.rounds.flush_audit(timeout=3))
                                rebuilt = read_round_audit(session_path / "audit.jsonl")
                                self.assertEqual(rebuilt["results"][3]["status"], "PASS")
                            if platform == "atlas":
                                active_record = (Path(paths["active"]) / "group0-slot1" /
                                                 "system" / "records.csv")
                                active_record.parent.mkdir(parents=True, exist_ok=True)
                                active_record.write_text("MLB_SN,status\n", encoding="utf-8")
                                pump_until(lambda: app.rounds.snapshot().results[0].status == "TESTING")
                                active_record.write_text(
                                    "MLB_SN,status\nATLAS00000001,PASS\n", encoding="utf-8",
                                )
                                pump_until(lambda: app.rounds.snapshot().results[0].sn ==
                                           "ATLAS00000001")
                                shutil.rmtree(active_record.parents[1])
                                archive = (Path(paths["final"]) / "ATLAS00000001" /
                                           datetime.now().strftime("%Y%m%d_%H-%M-%S.000-round") /
                                           "system" / "records.csv")
                                archive.parent.mkdir(parents=True)
                                archive.write_text(
                                    "MLB_SN,status\nATLAS00000001,PASS\n", encoding="utf-8",
                                )
                                pump_until(lambda: app.rounds.snapshot().results[0].status == "PASS" and
                                           app.status_rows[1]["status"].cget("text") == "PASS")
                                self.assertEqual(app.status_rows[1]["status"].cget("text"), "PASS")
                                self.assertTrue(app.rounds.flush_session(timeout=3))
                                self.assertTrue(app.rounds.flush_audit(timeout=3))
                                rebuilt = read_round_audit(session_path / "audit.jsonl")
                                result_event = next(event for event in rebuilt["events"]
                                                    if event["kind"] == "result")
                                self.assertEqual(result_event["round_id"], round_id)
                                self.assertEqual(result_event["localized_message"]["message_id"],
                                                 "round.result")
                                verify_round_event_language_refresh(result_event)
                                audit_bytes = (session_path / "audit.jsonl").read_bytes()
                                state = app.rounds.snapshot()
                                select_language("繁體中文")
                                self.assertTrue(any("結果：PASS" in line for line in app.event_lines))
                                self.assertEqual(app.rounds.snapshot().results, state.results)
                                self.assertEqual((session_path / "audit.jsonl").read_bytes(),
                                                 audit_bytes)
                                select_language("English")
                            if platform == "b482":
                                caseinfo_path = Path(paths["caseinfo"]) / (
                                    "thread2CaseInfo_{}.txt".format(datetime.now().strftime("%Y-%m-%d"))
                                )
                                caseinfo_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S:100")
                                prefix = ("{}, 4,InitResource,SNRead,--,SNRead,"
                                          "B482PARTIAL0001").format(caseinfo_time)
                                caseinfo_path.write_text(prefix, encoding="utf-8")
                                root.update()
                                app.rounds.poll_once()
                                self.assertEqual(app.rounds.snapshot().results[1].status, "WAITING")
                                with caseinfo_path.open("a", encoding="utf-8") as caseinfo_file:
                                    caseinfo_file.write(",NA,NA,NA,Passed,11.94\r\n")
                                pump_until(lambda: any(
                                    event.event.kind == "result" and
                                    event.event.sn == "B482PARTIAL0001"
                                    for event in app.rounds.snapshot().events
                                ))
                                self.assertTrue(app.rounds.flush_session(timeout=3))
                                self.assertTrue(app.rounds.flush_audit(timeout=3))
                                rebuilt = read_round_audit(session_path / "audit.jsonl")
                                partial_event = next(
                                    event for event in rebuilt["events"]
                                    if event.get("sn") == "B482PARTIAL0001"
                                )
                                self.assertEqual(partial_event["round_id"], round_id)
                                self.assertEqual(partial_event["localized_message"]["message_id"],
                                                 "round.result")
                                verify_round_event_language_refresh(partial_event)
                            if platform == "sample-json":
                                sample_time = datetime.now().isoformat(timespec="seconds")
                                event_path = Path(paths["active"]) / "events.jsonl"
                                sample_line = json.dumps({
                                    "kind": "final", "position": 20,
                                    "sn": "SAMPLE000020", "status": "PASS",
                                    "source_time": sample_time, "batch_id": "tk-round-fixture",
                                })
                                event_path.write_text(sample_line, encoding="utf-8")
                                root.update()
                                app.rounds.poll_once()
                                self.assertEqual(app.rounds.snapshot().results[0].status, "WAITING")
                                event_path.write_text(sample_line + "\n", encoding="utf-8")
                                pump_until(lambda: app.rounds.snapshot().results[0].status == "PASS" and
                                           app.status_rows[1]["status"].cget("text") == "PASS")
                                running_round_id = app.rounds.snapshot().round_id
                                self.assertTrue(app.rounds.flush_session(timeout=3))
                                self.assertTrue(app.rounds.flush_audit(timeout=3))
                                rebuilt = read_round_audit(session_path / "audit.jsonl")
                                sample_event = next(
                                    event for event in rebuilt["events"]
                                    if event.get("sn") == "SAMPLE000020"
                                )
                                self.assertEqual(sample_event["round_id"], running_round_id)
                                self.assertEqual(sample_event["localized_message"]["message_id"],
                                                 "round.result")
                                verify_round_event_language_refresh(sample_event)
                                app.start_button.invoke()
                                root.event_generate("<Command-Shift-M>")
                                app.hotkey.callback()
                                root.update()
                                pump_until(lambda: app.rounds.snapshot().round_id == running_round_id and
                                           app.rounds.snapshot().results[0].status == "PASS" and
                                           app.status_rows[1]["status"].cget("text") == "PASS")
                            if platform == "rswmt":
                                partial_log = Path(paths["final"]) / "partial-live.log"
                                log_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S,%f")[:-3]
                                partial_log.write_text(
                                    "{} STATE:TestRunner Add-in 'initialize'...".format(log_time),
                                    encoding="utf-8",
                                )
                                root.update()
                                app.rounds.poll_once()
                                self.assertEqual(app.rounds.snapshot().results[0].status, "WAITING")
                                partial_log.write_text(
                                    "{} STATE:TestRunner Add-in 'initialize'...\n"
                                    "{} VARiable:DEFine \"instance_active_1\", 1\n"
                                    "{} DEBUG:HciCommunication << MLB#.."
                                    "RSWMT000001 05 5B\n".format(log_time, log_time, log_time),
                                    encoding="utf-8",
                                )
                                pump_until(lambda: app.rounds.snapshot().results[0].status == "TESTING")
                                created_at = datetime.strptime(
                                    log_time, "%Y-%m-%d %H:%M:%S,%f",
                                ).replace(microsecond=0)
                                start = created_at.strftime("%Y/%d/%m %H:%M:%S")
                                stopped = (created_at + timedelta(seconds=1)).strftime(
                                    "%Y/%d/%m %H:%M:%S",
                                )
                                filename_time = (created_at + timedelta(seconds=1)).strftime(
                                    "%Y-%m-%d_%H-%M-%S",
                                )
                                result = Path(paths["final"]) / (
                                    "RSWMT000001_{}.csv".format(filename_time)
                                )
                                result.write_text(
                                    "Overlay,SmtCal,,,,,,\n"
                                    "Serial Number,Test Pass/Fail Status,List of Failing Tests,"
                                    "Error Description,Test Start Time,Test Stop Time,PRODUCT,"
                                    "tc=Slot:tech=None:band=None;subtc=None:rate=None:freq=None;pwr=None;\n"
                                    "RSWMT000001,Pass,[],{}, {},{},B518,1\n".format(
                                        "", start, stopped,
                                    ),
                                    encoding="utf-8",
                                )
                                pump_until(lambda: app.rounds.snapshot().results[0].status == "PASS" and
                                           app.status_rows[1]["status"].cget("text") == "PASS",
                                           timeout=12)
                                self.assertEqual(app.status_rows[1]["status"].cget("text"), "PASS")
                                self.assertTrue(app.rounds.flush_session(timeout=3))
                                self.assertTrue(app.rounds.flush_audit(timeout=3))
                                rebuilt = read_round_audit(session_path / "audit.jsonl")
                                self.assertTrue(rebuilt["audit_complete"])
                                self.assertEqual(rebuilt["results"][1]["sn"], "RSWMT000001")
                                rswmt_result = next(
                                    event for event in rebuilt["events"]
                                    if event.get("sn") == "RSWMT000001" and
                                    event.get("status") == "PASS"
                                )
                                verify_round_event_language_refresh(rswmt_result)
                        finally:
                            app.rounds.stop()
                            app.rounds.flush_session(timeout=3)
                            app.rounds.flush_audit(timeout=3)
                            statuses = self.wait_for_archive_checks(app.rounds)
                            if round_id is not None:
                                self.assertEqual(app.rounds.archive_status(round_id).status,
                                                 "archived", statuses)
                            cleanup_deadline = time.monotonic() + 5
                            while (app.rounds.retention_cleanup_status().status not in {"complete", "failed"}
                                   and time.monotonic() < cleanup_deadline):
                                root.update()
                                time.sleep(0.01)
                            app.hotkey.close()
                            root.destroy()

    def test_conflict_review_disables_resolution_when_selection_is_cleared(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.deiconify()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey, session_root=Path(temporary) / "sessions",
            )
            app.current_language = TRADITIONAL_CHINESE
            app._apply_main_language()
            sources = []

            def source_factory(callback):
                source = ControlledConflictMonitor(callback)
                sources.append(source)
                return source

            def pump_until(predicate, timeout=5):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    root.update()
                    if predicate():
                        return
                    time.sleep(0.01)
                self.fail("Timed out waiting for controlled conflict review UI")

            try:
                started = app.rounds.start("FCT", source_factory, run_async=True, capacity=2)
                app.active_round_id = started.round_id
                pump_until(lambda: sources and app.rounds.snapshot()
                           and app.rounds.snapshot().results
                           and app.rounds.snapshot().results[0].status == "PASS")
                self.assertEqual(sources[0].offer_candidate(
                    1, "SN-CANDIDATE", "FAIL", "/controlled/slot1/candidate.csv",
                    "candidate", "2026-10-08T10:01:00"), "defer")
                pump_until(lambda: app.conflict_window is not None and
                           app.conflict_window.winfo_viewable())
                self.assertEqual(len(app.rounds.snapshot().pending_conflicts), 1)
                self.assertEqual(str(app.resolve_conflict_original_button["state"]), "normal")
                self.assertEqual(str(app.resolve_conflict_candidate_button["state"]), "normal")

                app.conflict_list.selection_clear(0, "end")
                pump_until(lambda: app.conflict_details.get("1.0", "end-1c") ==
                           app._t("conflict.empty") and
                           str(app.resolve_conflict_original_button["state"]) == "disabled")

                self.assertFalse(app.conflict_list.curselection())
                self.assertEqual(app.conflict_position_label.cget("text"), "顯示位置：未知")
                self.assertEqual(app.conflict_details.get("1.0", "end-1c"), "目前沒有待確認項目。")
                self.assertEqual(str(app.resolve_conflict_original_button["state"]), "disabled")
                self.assertEqual(str(app.resolve_conflict_candidate_button["state"]), "disabled")
                self.assertEqual(len(app.rounds.snapshot().pending_conflicts), 1)
                english_index = next(
                    index for index in range(app.language_menu.index("end") + 1)
                    if app.language_menu.entrycget(index, "label") == "English")
                app.language_menu.invoke(english_index)
                root.update_idletasks()
                self.assertEqual(app.conflict_details.get("1.0", "end-1c"),
                                 app._t("conflict.empty"))
                self.assertEqual(app.conflict_position_label.cget("text"), app._t(
                    "conflict.position", position=app._t("conflict.unknown"),
                ))
                chinese_index = next(
                    index for index in range(app.language_menu.index("end") + 1)
                    if app.language_menu.entrycget(index, "label") == "繁體中文")
                app.language_menu.invoke(chinese_index)
                root.update_idletasks()
            finally:
                if app.rounds.snapshot() and app.rounds.snapshot().state in {
                        RoundState.RUNNING, RoundState.AWAITING_REVIEW}:
                    app.rounds.stop()
                app.rounds.flush_session(timeout=3)
                app.rounds.flush_audit(timeout=3)
                app.hotkey.close()
                root.destroy()

    def test_conflict_review_tracks_same_slot_candidates_through_refresh_resolution_and_reopen(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.deiconify()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey, session_root=Path(temporary) / "sessions",
            )
            app.current_language = TRADITIONAL_CHINESE
            app._apply_main_language()
            sources = []

            def source_factory(callback):
                source = ControlledConflictMonitor(callback)
                sources.append(source)
                return source

            def pump_until(predicate, timeout=5):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    root.update()
                    if predicate():
                        return
                    time.sleep(0.01)
                self.fail("Timed out waiting for controlled multi-candidate review UI")

            try:
                started = app.rounds.start("FCT", source_factory, run_async=True, capacity=2)
                app.active_round_id = started.round_id
                pump_until(lambda: sources and app.rounds.snapshot()
                           and app.rounds.snapshot().results
                           and app.rounds.snapshot().results[0].status == "PASS")
                source = sources[0]
                for sn, name, stamp in (
                        ("SN-CANDIDATE-1", "candidate-1.csv", "10:01:00"),
                        ("SN-CANDIDATE-2", "candidate-2.csv", "10:02:00")):
                    self.assertEqual(source.offer_candidate(
                        1, sn, "FAIL", "/controlled/slot1/" + name, name,
                        "2026-10-08T" + stamp), "defer")
                self.assertEqual(source.offer_candidate(
                    2, "SN-OTHER-CANDIDATE", "FAIL", "/controlled/slot2/other.csv",
                    "slot2-candidate", "2026-10-08T10:03:00"), "defer")
                pump_until(lambda: len(app.rounds.snapshot().pending_conflicts) == 3
                           and app.conflict_window is not None
                           and app.conflict_window.winfo_viewable())

                captured = app.rounds.snapshot().pending_conflicts
                second_id = captured[1].conflict_id
                app.conflict_list.selection_clear(0, "end")
                app.conflict_list.selection_set(1)
                app.conflict_list.event_generate("<<ListboxSelect>>")
                root.update_idletasks()
                self.assertEqual(conflict_summary_rows(app)[2][2], "SN-CANDIDATE-2")
                self.assertIn(second_id, app.conflict_details.get("1.0", "end"))
                self.assertEqual(app.conflict_position_label.cget("text"), "顯示位置：1")

                candidate_started = threading.Event()
                candidate_release = threading.Event()
                candidate_done = threading.Event()
                candidate_errors = []

                def add_candidate_during_refresh():
                    candidate_started.set()
                    if not candidate_release.wait(3):
                        candidate_errors.append("candidate release timed out")
                        return
                    try:
                        decision = source.offer_candidate(
                            1, "SN-CANDIDATE-3", "FAIL", "/controlled/slot1/candidate-3.csv",
                            "candidate-3", "2026-10-08T10:04:00")
                        if decision != "defer":
                            candidate_errors.append("unexpected candidate decision: " + decision)
                    except Exception as error:
                        candidate_errors.append(str(error))
                    finally:
                        candidate_done.set()

                candidate_thread = threading.Thread(target=add_candidate_during_refresh)
                candidate_thread.start()
                self.assertTrue(candidate_started.wait(2))
                candidate_release.set()
                pump_until(lambda: len(app.rounds.snapshot().pending_conflicts) == 4
                           and app.conflict_list.size() == 4 and candidate_done.is_set())
                candidate_thread.join(timeout=2)
                self.assertFalse(candidate_thread.is_alive())
                self.assertEqual(candidate_errors, [])
                self.assertEqual(app.conflict_list.curselection(), (1,))
                self.assertEqual(conflict_summary_rows(app)[2][2], "SN-CANDIDATE-2")
                self.assertIn(second_id, app.conflict_details.get("1.0", "end"))
                candidate_result = app.conflict_comparison.search("FAIL", "1.0")
                self.assertTrue(candidate_result)
                self.assertIn("comparison_difference",
                              app.conflict_comparison.tag_names(candidate_result))

                app.conflict_close_button.invoke()
                root.update_idletasks()
                self.assertFalse(app.conflict_window.winfo_viewable())
                self.assertEqual(source.offer_candidate(
                    2, "SN-OTHER-CANDIDATE-2", "FAIL", "/controlled/slot2/other-2.csv",
                    "slot2-candidate-2", "2026-10-08T10:05:00"), "defer")
                pump_until(lambda: len(app.rounds.snapshot().pending_conflicts) == 5)
                self.assertEqual(app.conflict_list.curselection(), (1,))
                app.review_button.invoke()
                root.update_idletasks()
                self.assertTrue(app.conflict_window.winfo_viewable())
                self.assertIn(second_id, app.conflict_details.get("1.0", "end"))

                app.resolve_conflict_candidate_button.invoke()
                pump_until(lambda: len(app.rounds.snapshot().pending_conflicts) == 4
                           and second_id not in {item.conflict_id
                                                 for item in app.rounds.snapshot().pending_conflicts})
                self.assertEqual(app.conflict_list.curselection(), (0,))
                first_id = captured[0].conflict_id
                self.assertIn(first_id, app.conflict_details.get("1.0", "end"))
                self.assertEqual(conflict_summary_rows(app)[2][2], "SN-CANDIDATE-1")

                while app.rounds.snapshot().pending_conflicts:
                    app.resolve_conflict_original_button.invoke()
                    root.update_idletasks()
                self.assertFalse(app.conflict_list.curselection())
                self.assertEqual(app.conflict_position_label.cget("text"), "顯示位置：未知")
                self.assertEqual(app.conflict_details.get("1.0", "end-1c"),
                                 "目前沒有待確認項目。")
                self.assertEqual(str(app.resolve_conflict_original_button["state"]), "disabled")
                self.assertEqual(str(app.resolve_conflict_candidate_button["state"]), "disabled")

                app.rounds.stop()
                self.assertTrue(app.rounds.flush_session(timeout=3))
                self.assertTrue(app.rounds.flush_audit(timeout=3))
                audit_path = Path(temporary) / "sessions" / started.round_id / "audit.jsonl"
                rebuilt = read_round_audit(audit_path)
                self.assertTrue(rebuilt["audit_complete"])
                detected = [event for event in rebuilt["events"]
                            if event["kind"] == "conflict_detected"]
                resolved = [event for event in rebuilt["events"]
                            if event["kind"] == "conflict_resolved"]
                self.assertEqual(len(detected), 5)
                self.assertEqual(len(resolved), 5)
                self.assertEqual({event["detail"]["conflict_id"] for event in resolved},
                                 {event["detail"]["conflict_id"] for event in detected})
                self.assertEqual([event["detail"]["choice"] for event in resolved].count(
                    "accept_candidate"), 1)
            finally:
                if app.rounds.snapshot() and app.rounds.snapshot().state in {
                        RoundState.RUNNING, RoundState.AWAITING_REVIEW}:
                    app.rounds.stop()
                app.rounds.flush_session(timeout=3)
                app.rounds.flush_audit(timeout=3)
                app.hotkey.close()
                root.destroy()

    def test_sample_platform_conflicts_stay_consistent_through_real_tk_and_disk_rebuild(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.deiconify()
            source_root = Path(temporary) / "source"
            source_root.mkdir()
            source_file = source_root / "events.jsonl"
            source_file.write_text("", encoding="utf-8")
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey, session_root=Path(temporary) / "sessions",
            )
            app.current_language = TRADITIONAL_CHINESE
            app._apply_main_language()

            def wait_ui(predicate, timeout=8):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    root.update()
                    if predicate():
                        return
                    time.sleep(0.01)
                self.fail("Timed out waiting for sample-platform conflict review")

            def append_source_event(kind, position, sn, status, second):
                event = {
                    "kind": kind, "position": position, "sn": sn, "status": status,
                    "source_time": "2026-10-08T10:00:{:02d}".format(second),
                    "batch_id": "c3-controlled-batch",
                }
                with source_file.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(event) + "\n")

            try:
                app.open_settings()
                app.profile_editor_project.set("B518")
                app.profile_editor_machine.set("FCT")
                app.profile_editor_platform.set("sample-json")
                app.profile_editor_capacity.set("3")
                app.profile_editor_mapping.set("1:1, 2:2, 3:3")
                app.profile_editor_paths["active"].set(str(source_root))
                app._apply_profile_editor()
                app._close_settings()
                app.start_monitor()
                wait_ui(lambda: app.rounds.session_path is not None)

                append_source_event("activity", 3, "", "TESTING", 0)
                append_source_event("final", 1, "SN-ORIGINAL", "PASS", 1)
                wait_ui(lambda: any(result.slot == 1 and result.status == "PASS"
                                    for result in app.rounds.snapshot().results))
                append_source_event("final", 1, "SN-CANDIDATE-1", "FAIL", 2)
                wait_ui(lambda: len(app.rounds.snapshot().pending_conflicts) == 1
                         and app.conflict_window is not None
                         and app.conflict_window.winfo_viewable())
                first_conflict = app.rounds.snapshot().pending_conflicts[0]
                self.assertEqual((first_conflict.slot, first_conflict.original.status,
                                  first_conflict.candidate.status), (1, "PASS", "FAIL"))

                append_source_event("final", 1, "SN-CANDIDATE-2", "NOTEST", 3)
                wait_ui(lambda: len(app.rounds.snapshot().pending_conflicts) == 2
                         and app.conflict_list.size() == 2)
                conflicts = app.rounds.snapshot().pending_conflicts
                second_conflict = conflicts[1]
                self.assertEqual(second_conflict.slot, 1)
                self.assertEqual(app.conflict_list.curselection(), (0,))
                self.assertIn(first_conflict.conflict_id, app.conflict_details.get("1.0", "end"))
                app.conflict_list.selection_clear(0, "end")
                app.conflict_list.selection_set(1)
                app.conflict_list.event_generate("<<ListboxSelect>>")
                root.update_idletasks()
                self.assertIn(second_conflict.conflict_id, app.conflict_details.get("1.0", "end"))
                self.assertEqual(conflict_summary_rows(app)[2][1:],
                                 ("SN-ORIGINAL", "SN-CANDIDATE-2"))
                captured_source = source_file.read_text(encoding="utf-8")
                source_file.write_text(captured_source.replace(
                    "SN-CANDIDATE-2", "SN-CHANGED-AFTER-CAPTURE").replace(
                    '"NOTEST"', '"PASS"'), encoding="utf-8")
                root.update_idletasks()
                self.assertEqual(len(app.rounds.snapshot().pending_conflicts), 2)

                append_source_event("final", 2, "SN-SECOND", "PASS", 4)
                wait_ui(lambda: any(result.slot == 2 and result.status == "PASS"
                                    for result in app.rounds.snapshot().results))
                append_source_event("final", 2, "SN-SECOND-CANDIDATE", "FAIL", 5)
                wait_ui(lambda: len(app.rounds.snapshot().pending_conflicts) == 3
                         and app.conflict_list.size() == 3)
                cross_position_conflict = app.rounds.snapshot().pending_conflicts[2]
                self.assertEqual(cross_position_conflict.slot, 2)
                self.assertEqual(app.conflict_list.curselection(), (1,))
                self.assertEqual(app.conflict_position_label.cget("text"), "顯示位置：1")
                self.assertIn(second_conflict.conflict_id, app.conflict_details.get("1.0", "end"))
                self.assertEqual(conflict_summary_rows(app)[2][1:],
                                 ("SN-ORIGINAL", "SN-CANDIDATE-2"))
                candidate_index = app.conflict_comparison.search("NOTEST", "1.0")
                self.assertTrue(candidate_index)
                self.assertIn("comparison_difference",
                              app.conflict_comparison.tag_names(candidate_index))
                self.assertEqual(app.conflict_comparison.tag_cget(
                    "comparison_difference", "foreground"), "#b00020")
                difference_font = tkfont.Font(
                    root=root,
                    font=app.conflict_comparison.tag_cget("comparison_difference", "font"),
                )
                self.assertEqual(difference_font.actual("weight"), "bold")

                self.assertTrue(app.rounds.flush_audit(timeout=3))
                audit_path = app.rounds.session_path / "audit.jsonl"
                audit_bytes_before_refresh = audit_path.read_bytes()
                state_before_refresh = app.rounds.snapshot()
                selected_conflict_id = second_conflict.conflict_id
                app.language_button.event_generate("<Button-1>")
                root.update()
                chinese_index = next(
                    index for index in range(app.language_menu.index("end") + 1)
                    if app.language_menu.entrycget(index, "label") == "繁體中文"
                )
                app.language_menu.invoke(chinese_index)
                root.update()
                self.assertTrue(any(
                    event.event.localized_message and
                    event.event.localized_message.traditional_chinese in line
                    for event in state_before_refresh.events for line in app.event_lines
                ), app.event_lines)
                self.assertEqual(app.rounds.snapshot().pending_conflicts,
                                 state_before_refresh.pending_conflicts)
                self.assertEqual(app.conflict_list.curselection(), (1,))
                self.assertEqual(app.conflict_position_label.cget("text"), "顯示位置：1")
                self.assertIn(selected_conflict_id, app.conflict_details.get("1.0", "end"))
                self.assertEqual(conflict_summary_rows(app)[2][1:],
                                 ("SN-ORIGINAL", "SN-CANDIDATE-2"))
                self.assertEqual(audit_path.read_bytes(), audit_bytes_before_refresh)

                app.language_button.event_generate("<Button-1>")
                root.update()
                english_index = next(
                    index for index in range(app.language_menu.index("end") + 1)
                    if app.language_menu.entrycget(index, "label") == "English"
                )
                app.language_menu.invoke(english_index)
                root.update()
                self.assertEqual(app.rounds.snapshot().pending_conflicts,
                                 state_before_refresh.pending_conflicts)
                self.assertEqual(audit_path.read_bytes(), audit_bytes_before_refresh)
                chinese_index = next(
                    index for index in range(app.language_menu.index("end") + 1)
                    if app.language_menu.entrycget(index, "label") == "繁體中文"
                )
                app.language_menu.invoke(chinese_index)
                root.update()

                app.conflict_close_button.invoke()
                root.update_idletasks()
                self.assertFalse(app.conflict_window.winfo_viewable())
                app.review_button.invoke()
                root.update_idletasks()
                self.assertTrue(app.conflict_window.winfo_viewable())
                self.assertIn(second_conflict.conflict_id, app.conflict_details.get("1.0", "end"))

                app.resolve_conflict_candidate_button.invoke()
                wait_ui(lambda: len(app.rounds.snapshot().pending_conflicts) == 2
                         and second_conflict.conflict_id not in {
                             item.conflict_id for item in app.rounds.snapshot().pending_conflicts
                         })
                self.assertEqual(app.conflict_list.curselection(), (0,))
                self.assertIn(first_conflict.conflict_id, app.conflict_details.get("1.0", "end"))
                remaining_result = app.conflict_comparison.search("FAIL", "1.0")
                self.assertTrue(remaining_result)
                self.assertIn("comparison_difference",
                              app.conflict_comparison.tag_names(remaining_result))
                app.resolve_conflict_original_button.invoke()
                wait_ui(lambda: len(app.rounds.snapshot().pending_conflicts) == 1)
                self.assertEqual(app.conflict_position_label.cget("text"), "顯示位置：2")
                self.assertIn(cross_position_conflict.conflict_id,
                              app.conflict_details.get("1.0", "end"))
                self.assertEqual(conflict_summary_rows(app)[2][1:],
                                 ("SN-SECOND", "SN-SECOND-CANDIDATE"))
                remaining_index = app.conflict_comparison.search("FAIL", "1.0")
                self.assertTrue(remaining_index)
                self.assertEqual(app.conflict_comparison.tag_cget(
                    "comparison_difference", "foreground"), "#b00020")
                difference_font = tkfont.Font(
                    root=root,
                    font=app.conflict_comparison.tag_cget("comparison_difference", "font"),
                )
                self.assertEqual(difference_font.actual("weight"), "bold")
                app.resolve_conflict_original_button.invoke()
                wait_ui(lambda: not app.rounds.snapshot().pending_conflicts)
                self.assertFalse(app.conflict_list.curselection())
                self.assertEqual(app.conflict_details.get("1.0", "end-1c"),
                                 "目前沒有待確認項目。")
                self.assertEqual(str(app.resolve_conflict_original_button["state"]), "disabled")
                self.assertEqual(str(app.resolve_conflict_candidate_button["state"]), "disabled")

                append_source_event("final", 3, "SN-THIRD", "PASS", 6)
                wait_ui(lambda: app.rounds.snapshot().collection_stopped
                         and app.rounds.snapshot().result_available)
                self.assertTrue(app.rounds.flush_session(timeout=3))
                self.assertTrue(app.rounds.flush_audit(timeout=3))
                audit_path = app.rounds.session_path / "audit.jsonl"
                rebuilt = read_round_audit(audit_path)
                self.assertTrue(rebuilt["audit_complete"])
                self.assertTrue(rebuilt["result_available"])
                self.assertEqual([rebuilt["results"][slot]["status"] for slot in (1, 2, 3)],
                                 ["PASS", "PASS", "PASS"])
                detected = [event for event in rebuilt["events"]
                            if event["kind"] == "conflict_detected"]
                resolved = [event for event in rebuilt["events"]
                            if event["kind"] == "conflict_resolved"]
                self.assertEqual(len(detected), 3)
                self.assertEqual(len(resolved), 3)
                self.assertEqual({event["detail"]["conflict_id"] for event in detected},
                                 {event["detail"]["conflict_id"] for event in resolved})
                with (app.rounds.session_path / "results.csv").open(encoding="utf-8") as handle:
                    session_results = list(csv.DictReader(handle))
                self.assertEqual([(int(row["slot"]), row["status"]) for row in session_results],
                                 [(1, "PASS"), (2, "PASS"), (3, "PASS")])
            finally:
                if app._round_is_active():
                    app.rounds.stop()
                app.rounds.flush_session(timeout=3)
                app.rounds.flush_audit(timeout=3)
                app.rounds.request_close()
                self.wait_for(lambda: app.rounds.close_status().status in {"complete", "failed"})
                close_status = app.rounds.close_status().status
                app._close_settings()
                app.hotkey.close()
                root.destroy()
                self.assertEqual(close_status, "complete")

    def test_atlas_round_shows_nonblocking_conflict_and_releases_after_other_slot_finishes(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.deiconify()
            active = Path(temporary) / "active"
            final = Path(temporary) / "final"
            active.mkdir()
            final.mkdir()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey, session_root=Path(temporary) / "sessions")
            app.current_language = TRADITIONAL_CHINESE
            app._apply_main_language()
            def wait_ui(predicate, timeout=5):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    root.update()
                    if predicate():
                        return
                    time.sleep(0.02)
                self.fail("Timed out waiting for the controlled Atlas conflict flow")
            try:
                app.open_settings()
                app.profile_editor_project.set("B518")
                app.profile_editor_machine.set("FCT")
                app.profile_editor_platform.set("atlas")
                app.profile_editor_capacity.set("2")
                app.profile_editor_mapping.set("1:2, 2:1")
                app.profile_editor_paths["active"].set(str(active))
                app.profile_editor_paths["final"].set(str(final))
                app._apply_profile_editor()
                app._close_settings()
                app.start_monitor()
                wait_ui(lambda: app.rounds.session_path is not None)

                def write_records(path, serial, status="Pass"):
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("MLB_SN,status\n{},{}\n".format(serial, status), encoding="utf-8")

                first_sn, second_sn = "SERIAL00000001", "SERIAL00000002"
                first_active = active / "group0-slot1" / "system" / "records.csv"
                second_active = active / "group0-slot2" / "system" / "records.csv"
                write_records(first_active, first_sn)
                write_records(second_active, second_sn)
                wait_ui(lambda: len(app.rounds.snapshot().results) == 2 and all(
                    result.status == "TESTING" for result in app.rounds.snapshot().results))

                stamp = (datetime.now() + timedelta(seconds=1)).strftime("%Y%m%d_%H-%M-%S.000-run")
                first_archive = final / first_sn / stamp / "system" / "records.csv"
                first_active.unlink()
                first_active.parent.rmdir()
                (active / "group0-slot1").rmdir()
                write_records(first_archive, first_sn)
                wait_ui(lambda: any(result.slot == 2 and result.status == "PASS"
                                    for result in app.rounds.snapshot().results), timeout=5)
                write_records(first_archive, first_sn, "FAIL")
                wait_ui(lambda: len(app.rounds.snapshot().pending_conflicts) == 1, timeout=5)
                wait_ui(lambda: app.conflict_window is not None, timeout=5)
                root.update_idletasks()

                self.assertIsNotNone(app.conflict_window, app.event_lines)
                self.assertTrue(app.conflict_window.winfo_exists())
                self.assertTrue(app.conflict_window.winfo_viewable())
                self.assertEqual((app.conflict_window.winfo_width(), app.conflict_window.winfo_height()),
                                 (820, 430))
                self.assertLessEqual(app.conflict_window.winfo_rootx() + app.conflict_window.winfo_width(),
                                     root.winfo_rootx())
                self.assertEqual(app._display_capacity(), 2)
                self.assertEqual(app.rounds.snapshot().results[0].status, "TESTING")
                self.assertEqual(app.rounds.snapshot().results[1].status, "PASS")
                conflict = app.rounds.snapshot().pending_conflicts[0]
                self.assertEqual(conflict.slot, 2)
                self.assertEqual(conflict.original.status, "PASS")
                self.assertEqual(conflict.candidate.status, "FAIL")

                comparison_rows = conflict_summary_rows(app)
                self.assertEqual(comparison_rows[0], ("項目", "原結果", "新候選"))
                self.assertEqual([row[0] for row in comparison_rows[1:]],
                                 ["結果", "SN", "來源時間", "來源檔名"])
                self.assertEqual(comparison_rows[1][1:], ("PASS", "FAIL"))
                self.assertEqual(comparison_rows[2][1:],
                                 (conflict.original.sn, conflict.candidate.sn))
                self.assertEqual(comparison_rows[3][1:],
                                 (conflict.original.source_time, conflict.candidate.source_time))
                self.assertEqual(comparison_rows[4][1:],
                                 (Path(conflict.original.source).name,
                                  Path(conflict.candidate.source).name))
                for field, expected in (("結果", [True, True]), ("SN", [False, False]),
                                        ("來源時間", [False, False]),
                                        ("來源檔名", [False, False])):
                    self.assertEqual(["comparison_difference" in
                                      app.conflict_comparison.tag_names(start)
                                      for start, _end in app._conflict_value_ranges[field]],
                                     expected, field)
                self.assertEqual(app.conflict_comparison.tag_cget(
                    "comparison_difference", "foreground"), "#b00020")
                actual_difference_font = tkfont.Font(
                    root=root,
                    font=app.conflict_comparison.tag_cget("comparison_difference", "font"),
                )
                self.assertEqual(actual_difference_font.actual("weight"), "bold")
                self.assertEqual(app.conflict_position_label.cget("text"), "顯示位置：2")
                detail_text = app.conflict_details.get("1.0", "end")
                self.assertIn(conflict.round_id, detail_text)
                self.assertIn(conflict.conflict_id, detail_text)
                self.assertIn(conflict.original.source, detail_text)
                self.assertIn(conflict.candidate.source, detail_text)
                selected_conflict_id = app._conflict_ids[app.conflict_list.curselection()[0]]
                marker_position = (app.kvm_state_marker.winfo_rootx(),
                                   app.kvm_state_marker.winfo_rooty(),
                                   app.kvm_state_marker.winfo_width(),
                                   app.kvm_state_marker.winfo_height())
                english_index = next(
                    index for index in range(app.language_menu.index("end") + 1)
                    if app.language_menu.entrycget(index, "label") == "English")
                app.language_menu.invoke(english_index)
                root.update_idletasks()
                self.assertEqual(conflict_summary_rows(app)[0], (
                    "Item", "Original Result", "New Candidate",
                ))
                self.assertEqual(app._conflict_ids[app.conflict_list.curselection()[0]],
                                 selected_conflict_id)
                self.assertEqual(app.kvm_state_marker.winfo_viewable(), 1)
                self.assertEqual((app.kvm_state_marker.winfo_rootx(),
                                  app.kvm_state_marker.winfo_rooty(),
                                  app.kvm_state_marker.winfo_width(),
                                  app.kvm_state_marker.winfo_height()), marker_position)
                root.update_idletasks()
                pane_height = app.conflict_panes.winfo_height()
                initial_sash = app.conflict_panes.sashpos(0)
                self.assertGreater(pane_height, 0)
                self.assertGreater(initial_sash / float(pane_height), 0.32)
                self.assertLess(initial_sash / float(pane_height), 0.48)
                app.conflict_panes.event_generate(
                    "<ButtonPress-1>", x=app.conflict_panes.winfo_width() - 8,
                    y=initial_sash + 2,
                )
                app.conflict_panes.event_generate(
                    "<B1-Motion>", x=app.conflict_panes.winfo_width() - 8,
                    y=initial_sash + 32,
                )
                app.conflict_panes.event_generate(
                    "<ButtonRelease-1>", x=app.conflict_panes.winfo_width() - 8,
                    y=initial_sash + 32,
                )
                root.update_idletasks()
                self.assertGreater(app.conflict_panes.sashpos(0), initial_sash)

                app.conflict_window.geometry("720x360")
                root.update_idletasks()
                self.assertGreaterEqual(app.conflict_window.winfo_width(), 720)
                self.assertGreaterEqual(app.conflict_window.winfo_height(), 360)
                self.assertGreater(app.conflict_list.winfo_height(), 0)
                self.assertGreater(app.conflict_comparison.winfo_width(), 0)
                self.assertEqual(str(app.resolve_conflict_original_button["state"]), "normal")
                self.assertEqual(str(app.resolve_conflict_candidate_button["state"]), "normal")

                second_stamp = (datetime.now() + timedelta(seconds=2)).strftime("%Y%m%d_%H-%M-%S.000-run")
                second_archive = final / second_sn / second_stamp / "system" / "records.csv"
                second_active.unlink()
                second_active.parent.rmdir()
                (active / "group0-slot2").rmdir()
                write_records(second_archive, second_sn)
                wait_ui(lambda: app.rounds.snapshot().collection_stopped
                        and next(result for result in app.rounds.snapshot().results
                                 if result.slot == 1).status == "PASS", timeout=5)
                self.assertFalse(app.rounds.snapshot().result_available)
                self.assertEqual(len(app.rounds.snapshot().pending_conflicts), 1)
                self.assertTrue(app.conflict_window.winfo_viewable())
                self.assertEqual(app._conflict_ids[app.conflict_list.curselection()[0]],
                                 selected_conflict_id)
                self.assertEqual(app.rounds.snapshot().results[0].status, "PASS")
                self.assertEqual(app.rounds.snapshot().pending_conflicts[0].conflict_id,
                                 selected_conflict_id)

                chinese_index = next(
                    index for index in range(app.language_menu.index("end") + 1)
                    if app.language_menu.entrycget(index, "label") == "繁體中文")
                app.language_menu.invoke(chinese_index)
                root.update_idletasks()
                self.assertEqual(conflict_summary_rows(app)[0], ("項目", "原結果", "新候選"))

                app.conflict_close_button.invoke()
                root.update_idletasks()
                self.assertFalse(app.conflict_window.winfo_viewable())
                self.assertEqual(len(app.rounds.snapshot().pending_conflicts), 1)

                captured_candidate_path = Path(conflict.candidate.source)
                self.assertTrue(captured_candidate_path.is_file())
                changed_source_path = captured_candidate_path.with_name("changed-after-capture.csv")
                captured_candidate_path.rename(changed_source_path)
                app._open_conflict_review()
                app.conflict_list.selection_set(0)
                root.update_idletasks()
                selected_source_row = conflict_summary_rows(app)[4][1:]
                self.assertEqual(selected_source_row[1], captured_candidate_path.name)
                self.assertIn(conflict.candidate.source,
                              app.conflict_details.get("1.0", "end"))
                app.resolve_conflict_original_button.invoke()
                self.assertFalse(app.rounds.snapshot().pending_conflicts)
                self.assertEqual(app.rounds.snapshot().results[1].status, "PASS")
                self.assertTrue(app.rounds.snapshot().result_available)
                self.assertEqual([result.status for result in app.rounds.snapshot().results], ["PASS", "PASS"])
                self.assertEqual(app.rounds.snapshot().state.value, "COMPLETED")
                app._drain_events()
                self.assertEqual(app.status_rows[1]["status"].cget("text"), "PASS")
                self.assertEqual(app.status_rows[2]["status"].cget("text"), "PASS")
                self.assertTrue(app.rounds.flush_session(timeout=3))
                self.assertTrue(app.rounds.flush_audit(timeout=3))
                rebuilt = read_round_audit(app.rounds.session_path / "audit.jsonl")
                resolved = [event for event in rebuilt["events"]
                            if event["kind"] == "conflict_resolved"]
                self.assertTrue(rebuilt["audit_complete"])
                self.assertEqual(len(resolved), 1)
                self.assertEqual(resolved[0]["detail"]["choice"], "keep_original")
                self.assertEqual(resolved[0]["detail"]["conflict_id"], conflict.conflict_id)
            finally:
                if app._round_is_active():
                    app.rounds.stop()
                app.rounds.flush_session(timeout=3)
                app.rounds.flush_audit(timeout=3)
                app._close_settings()
                app.hotkey.close()
                root.destroy()

    def test_real_tk_conflict_selection_keeps_both_sections_on_same_snapshot(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.deiconify()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey, session_root=Path(temporary) / "sessions",
            )
            app.current_language = TRADITIONAL_CHINESE
            app._apply_main_language()
            coordinator = app.rounds

            def side(sn, status, source, source_id, source_time, evidence):
                return ConflictSide(sn, status, source, source_id, source_time,
                                    tuple(sorted(evidence.items())))

            first = RoundConflict(
                "conflict-first", "round-first", 1,
                side("SN-FIRST", "PASS", "/capture/original/first.csv", "original-id",
                     "", {"round_evidence_id": "evidence-first"}),
                side("", "FAIL", "", "candidate-id-must-not-become-a-path", "",
                     {"round_evidence_id": "evidence-first"}),
                (("round_evidence_id", "evidence-first"),), "2026-10-08T10:00:00",
            )
            second = RoundConflict(
                "conflict-second", "round-first", 2,
                side("SN-SECOND", "FAIL", "/capture/second/original.csv", "second-original",
                     "2026-10-08T10:01:00", {"round_evidence_id": "evidence-second"}),
                side("SN-SECOND-NEW", "PASS",
                     "/capture/second/" + ("long-candidate-" * 12) + ".csv", "second-new",
                     "2026-10-08T10:02:00", {"round_evidence_id": "evidence-second"}),
                (("round_evidence_id", "evidence-second"),), "2026-10-08T10:03:00",
            )
            third = RoundConflict(
                "conflict-third", "round-first", 3,
                side("SN-SAME", "PASS", "/line-A/group0-slot1/system/records.csv",
                     "third-original", "2026-10-08T10:04:00",
                     {"round_evidence_id": "evidence-third"}),
                side("SN-SAME", "PASS", "/line-B/group0-slot1/system/records.csv",
                     "third-candidate", "2026-10-08T10:04:00",
                     {"round_evidence_id": "evidence-third"}),
                (("round_evidence_id", "evidence-third"),), "2026-10-08T10:04:01",
            )
            fourth = RoundConflict(
                "conflict-fourth", "round-first", 4,
                side("SN-SHARED", "PASS", "/same/source/records.csv", "fourth-original",
                     "2026-10-08T10:05:00", {"round_evidence_id": "evidence-fourth"}),
                side("SN-SHARED", "FAIL", "/same/source/records.csv", "fourth-candidate",
                     "2026-10-08T10:05:00", {"round_evidence_id": "evidence-fourth"}),
                (("round_evidence_id", "evidence-fourth"),), "2026-10-08T10:05:01",
            )
            fifth = RoundConflict(
                "conflict-fifth", "round-first", 5,
                side("SN-OLD", "PASS", "/same/sn/source.csv", "fifth-original",
                     "2026-10-08T10:06:00", {"round_evidence_id": "evidence-fifth"}),
                side("SN-NEW", "PASS", "/same/sn/source.csv", "fifth-candidate",
                     "2026-10-08T10:06:00", {"round_evidence_id": "evidence-fifth"}),
                (("round_evidence_id", "evidence-fifth"),), "2026-10-08T10:06:01",
            )
            sixth = RoundConflict(
                "conflict-sixth", "round-first", 6,
                side("SN-TIME", "PASS", "/same/time/source.csv", "sixth-original",
                     "", {"round_evidence_id": "evidence-sixth"}),
                side("SN-TIME", "PASS", "/same/time/source.csv", "sixth-candidate",
                     "2026-10-08T10:08:00", {"round_evidence_id": "evidence-sixth"}),
                (("round_evidence_id", "evidence-sixth"),), "2026-10-08T10:08:01",
            )
            snapshot = RoundSnapshot(
                "round-first", "FCT", RoundState.AWAITING_REVIEW, (), False, 0, (),
                pending_conflicts=(first, second, third, fourth, fifth, sixth),
            )

            class SnapshotCoordinator:
                def __getattr__(self, name):
                    return getattr(coordinator, name)

                def snapshot(self):
                    return snapshot

            app.rounds = SnapshotCoordinator()
            app.active_round_id = snapshot.round_id
            try:
                app.events.put(RoundEvent(snapshot.round_id, 1, MonitorEvent(
                    "conflict_detected", "controlled conflict", detail={"round_id": snapshot.round_id},
                )))
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    root.update()
                    if app.conflict_window and app.conflict_window.winfo_exists():
                        break
                    time.sleep(0.01)
                self.assertTrue(app.conflict_window and app.conflict_window.winfo_exists())
                root.update_idletasks()
                self.assertEqual(app.conflict_position_label.cget("text"), "顯示位置：1")
                first_rows = conflict_summary_rows(app)
                self.assertEqual(first_rows[1], ("結果", "PASS", "FAIL"))
                self.assertEqual(first_rows[2], ("SN", "SN-FIRST", "未知"))
                self.assertEqual(first_rows[3], ("來源時間", "未知", "未知"))
                self.assertEqual(first_rows[4], ("來源檔名", "first.csv", "未知"))
                result_ranges = app._conflict_value_ranges["結果"]
                self.assertEqual(["comparison_difference" in
                                  app.conflict_comparison.tag_names(start)
                                  for start, _end in result_ranges], [True, True])
                self.assertEqual(app.conflict_comparison.tag_cget(
                    "comparison_difference", "foreground"), "#b00020")
                difference_font = tkfont.Font(
                    root=root,
                    font=app.conflict_comparison.tag_cget("comparison_difference", "font"),
                )
                self.assertEqual(difference_font.actual("weight"), "bold")
                same_unknown_time = app._conflict_value_ranges["來源時間"]
                self.assertEqual(["comparison_difference" in
                                  app.conflict_comparison.tag_names(start)
                                  for start, _end in same_unknown_time], [False, False])
                first_detail = app.conflict_details.get("1.0", "end")
                self.assertIn("candidate-id-must-not-become-a-path", first_detail)
                self.assertIn("/capture/original/first.csv", first_detail)
                self.assertNotIn("candidate-id-must-not-become-a-path.csv", first_rows[3][1])

                app.conflict_list.selection_clear(0, "end")
                app.conflict_list.selection_set(1)
                app.conflict_list.event_generate("<<ListboxSelect>>")
                root.update_idletasks()
                second_rows = conflict_summary_rows(app)
                self.assertEqual(app.conflict_position_label.cget("text"), "顯示位置：2")
                self.assertEqual(second_rows[1], ("結果", "FAIL", "PASS"))
                self.assertEqual(second_rows[2], ("SN", "SN-SECOND", "SN-SECOND-NEW"))
                self.assertEqual(second_rows[3],
                                 ("來源時間", "2026-10-08T10:01:00", "2026-10-08T10:02:00"))
                self.assertEqual(second_rows[4],
                                 ("來源檔名", "original.csv", ("long-candidate-" * 12) + ".csv"))
                for field in ("結果", "SN", "來源時間", "來源檔名"):
                    self.assertEqual(["comparison_difference" in
                                      app.conflict_comparison.tag_names(start)
                                      for start, _end in app._conflict_value_ranges[field]],
                                     [True, True], field)
                self.assertLess(app.conflict_comparison.xview()[1], 1.0)
                second_detail = app.conflict_details.get("1.0", "end")
                self.assertIn("conflict-second", second_detail)
                self.assertNotIn("conflict-first", second_detail)
                app.conflict_comparison.xview_moveto(1)
                self.assertGreater(app.conflict_comparison.xview()[0], 0.0)
                selected_conflict_id = app._conflict_ids[app.conflict_list.curselection()[0]]
                saved_xview = app.conflict_comparison.xview()[0]
                english_index = next(
                    index for index in range(app.language_menu.index("end") + 1)
                    if app.language_menu.entrycget(index, "label") == "English")
                app.language_menu.invoke(english_index)
                root.update_idletasks()
                self.assertEqual(app._conflict_ids[app.conflict_list.curselection()[0]],
                                 selected_conflict_id)
                self.assertEqual(conflict_summary_rows(app)[0], (
                    "Item", "Original Result", "New Candidate",
                ))
                self.assertIn("conflict-second", app.conflict_details.get("1.0", "end"))
                self.assertAlmostEqual(app.conflict_comparison.xview()[0], saved_xview, places=2)
                chinese_index = next(
                    index for index in range(app.language_menu.index("end") + 1)
                    if app.language_menu.entrycget(index, "label") == "繁體中文")
                app.language_menu.invoke(chinese_index)
                root.update_idletasks()
                self.assertEqual(app._conflict_ids[app.conflict_list.curselection()[0]],
                                 selected_conflict_id)
                self.assertEqual(conflict_summary_rows(app)[0], ("項目", "原結果", "新候選"))
                self.assertAlmostEqual(app.conflict_comparison.xview()[0], saved_xview, places=2)
                app.conflict_list.selection_clear(0, "end")
                app.conflict_list.selection_set(2)
                app.conflict_list.event_generate("<<ListboxSelect>>")
                root.update_idletasks()
                third_rows = conflict_summary_rows(app)
                self.assertEqual(third_rows[4], (
                    "來源檔名",
                    "records.csv · line-A/group0-slot1/system",
                    "records.csv · line-B/group0-slot1/system",
                ))
                self.assertTrue(all("comparison_difference" in
                                    app.conflict_comparison.tag_names(start)
                                    for start, _end in app._conflict_value_ranges["來源檔名"]))
                third_detail = app.conflict_details.get("1.0", "end")
                self.assertIn("/line-A/group0-slot1/system/records.csv", third_detail)
                self.assertIn("/line-B/group0-slot1/system/records.csv", third_detail)
                app.conflict_list.selection_clear(0, "end")
                app.conflict_list.selection_set(3)
                app.conflict_list.event_generate("<<ListboxSelect>>")
                root.update_idletasks()
                fourth_rows = conflict_summary_rows(app)
                self.assertEqual(fourth_rows[4], ("來源檔名", "records.csv", "records.csv"))
                self.assertEqual(["comparison_difference" in
                                  app.conflict_comparison.tag_names(start)
                                  for start, _end in app._conflict_value_ranges["來源檔名"]],
                                 [False, False])
                self.assertEqual(["comparison_difference" in
                                  app.conflict_comparison.tag_names(start)
                                  for start, _end in app._conflict_value_ranges["結果"]],
                                 [True, True])
                app.conflict_list.selection_clear(0, "end")
                app.conflict_list.selection_set(4)
                app.conflict_list.event_generate("<<ListboxSelect>>")
                root.update_idletasks()
                self.assertEqual(conflict_summary_rows(app)[2], ("SN", "SN-OLD", "SN-NEW"))
                for field, expected in (("結果", [False, False]), ("SN", [True, True]),
                                        ("來源時間", [False, False]),
                                        ("來源檔名", [False, False])):
                    self.assertEqual(["comparison_difference" in
                                      app.conflict_comparison.tag_names(start)
                                      for start, _end in app._conflict_value_ranges[field]],
                                     expected, field)
                app.conflict_list.selection_clear(0, "end")
                app.conflict_list.selection_set(5)
                app.conflict_list.event_generate("<<ListboxSelect>>")
                root.update_idletasks()
                self.assertEqual(conflict_summary_rows(app)[3], (
                    "來源時間", "未知", "2026-10-08T10:08:00",
                ))
                for field, expected in (("結果", [False, False]), ("SN", [False, False]),
                                        ("來源時間", [True, True]),
                                        ("來源檔名", [False, False])):
                    self.assertEqual(["comparison_difference" in
                                      app.conflict_comparison.tag_names(start)
                                      for start, _end in app._conflict_value_ranges[field]],
                                     expected, field)
                app.conflict_list.selection_clear(0, "end")
                app.conflict_list.selection_set(0)
                app.conflict_list.event_generate("<<ListboxSelect>>")
                root.update_idletasks()
                self.assertEqual(app.conflict_comparison.xview()[0], 0.0)
                self.assertEqual(app.conflict_position_label.cget("text"), "顯示位置：1")
                for field, expected in (("結果", [True, True]), ("SN", [True, True]),
                                        ("來源時間", [False, False]),
                                        ("來源檔名", [True, True])):
                    self.assertEqual(["comparison_difference" in
                                      app.conflict_comparison.tag_names(start)
                                      for start, _end in app._conflict_value_ranges[field]],
                                     expected, field)
                app.conflict_window.geometry("720x360")
                root.update_idletasks()
                self.assertTrue(app.conflict_comparison_scrollbar.winfo_viewable())
                self.assertTrue(app.conflict_close_button.winfo_viewable())
                first_detail = app.conflict_details.get("1.0", "end")
                self.assertIn("conflict-first", first_detail)
                self.assertNotIn("conflict-second", first_detail)
            finally:
                app.rounds = coordinator
                app.hotkey.close()
                coordinator.request_close()
                root.destroy()

    def test_atlas_conflict_with_same_filename_from_new_archive_path_shows_real_tk_hint(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.deiconify()
            active = Path(temporary) / "active"
            final = Path(temporary) / "final"
            active.mkdir()
            final.mkdir()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey, session_root=Path(temporary) / "sessions",
            )
            app.current_language = TRADITIONAL_CHINESE
            app._apply_main_language()

            def wait_ui(predicate, timeout=6):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    root.update()
                    if predicate():
                        return
                    time.sleep(0.02)
                self.fail("Timed out waiting for the controlled Atlas path-conflict flow: {} / {}"
                          .format(app.rounds.snapshot(), app.event_lines[-8:]))

            def write_records(path, serial, status):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("MLB_SN,status\n{},{}\n".format(serial, status),
                                encoding="utf-8")

            try:
                app.open_settings()
                app.profile_editor_project.set("B518")
                app.profile_editor_machine.set("FCT")
                app.profile_editor_platform.set("atlas")
                app.profile_editor_capacity.set("2")
                app.profile_editor_mapping.set("1:1, 2:2")
                app.profile_editor_paths["active"].set(str(active))
                app.profile_editor_paths["final"].set(str(final))
                app._apply_profile_editor()
                app._close_settings()
                app.start_monitor()
                wait_ui(lambda: app.rounds.session_path is not None)

                serial = "SERIAL00000091"
                active_record = active / "group0-slot1" / "system" / "records.csv"
                second_active_record = active / "group0-slot2" / "system" / "records.csv"
                write_records(active_record, serial, "Pass")
                write_records(second_active_record, "SERIAL00000092", "Pass")
                wait_ui(lambda: len(app.rounds.snapshot().results) == 2 and all(
                    result.status == "TESTING" for result in app.rounds.snapshot().results))
                first_stamp = (datetime.now() + timedelta(seconds=1)).strftime(
                    "%Y%m%d_%H-%M-%S.000-run",
                )
                first_archive = final / serial / first_stamp / "system" / "records.csv"
                active_record.unlink()
                active_record.parent.rmdir()
                (active / "group0-slot1").rmdir()
                write_records(first_archive, serial, "Pass")
                wait_ui(lambda: app.rounds.snapshot().results and
                        app.rounds.snapshot().results[0].status == "PASS")

                second_stamp = (datetime.now() + timedelta(seconds=3)).strftime(
                    "%Y%m%d_%H-%M-%S.000-run",
                )
                second_archive = final / serial / second_stamp / "system" / "records.csv"
                write_records(second_archive, serial, "Fail")
                wait_ui(lambda: app.rounds.snapshot().pending_conflicts, timeout=8)
                wait_ui(lambda: app.conflict_window and app.conflict_window.winfo_viewable())
                root.update_idletasks()

                conflict = app.rounds.snapshot().pending_conflicts[0]
                self.assertEqual(conflict.original.source, str(first_archive))
                self.assertEqual(conflict.candidate.source, str(second_archive))
                self.assertEqual(Path(conflict.original.source).name,
                                 Path(conflict.candidate.source).name)
                rows = conflict_summary_rows(app)
                self.assertEqual(rows[4], (
                    "來源檔名", "records.csv · {}/system".format(first_stamp),
                    "records.csv · {}/system".format(second_stamp),
                ))
                self.assertEqual(["comparison_difference" in
                                  app.conflict_comparison.tag_names(start)
                                  for start, _end in app._conflict_value_ranges["來源檔名"]],
                                 [True, True])
                detail = app.conflict_details.get("1.0", "end")
                self.assertIn(str(first_archive), detail)
                self.assertIn(str(second_archive), detail)
                self.assertEqual(app.conflict_comparison.tag_cget(
                    "comparison_difference", "foreground"), "#b00020")
                difference_font = tkfont.Font(
                    root=root,
                    font=app.conflict_comparison.tag_cget("comparison_difference", "font"),
                )
                self.assertEqual(difference_font.actual("weight"), "bold")
            finally:
                if app._round_is_active():
                    app.rounds.stop()
                app.rounds.flush_session(timeout=3)
                app.rounds.flush_audit(timeout=3)
                app._close_settings()
                app.hotkey.close()
                app.rounds.request_close()
                root.destroy()

    def test_unknown_atlas_identity_change_is_visible_as_fail_and_audited_without_reason(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.deiconify()
            active = Path(temporary) / "active"
            final = Path(temporary) / "final"
            active.mkdir()
            final.mkdir()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey, session_root=Path(temporary) / "sessions")

            def wait_ui(predicate, timeout=5):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    root.update()
                    if predicate():
                        return
                    time.sleep(0.02)
                self.fail("Timed out waiting for the unknown-source FAIL flow")

            try:
                app.open_settings()
                app.profile_editor_project.set("B518")
                app.profile_editor_machine.set("FCT")
                app.profile_editor_platform.set("atlas")
                app.profile_editor_capacity.set("1")
                app.profile_editor_mapping.set("1:1")
                app.profile_editor_paths["active"].set(str(active))
                app.profile_editor_paths["final"].set(str(final))
                app._apply_profile_editor()
                app._close_settings()
                app.start_monitor()
                wait_ui(lambda: app.rounds.session_path is not None)

                record = active / "group0-slot1" / "system" / "records.csv"
                record.parent.mkdir(parents=True)
                record.write_text("MLB_SN,status\nSERIAL00000001,Pass\n", encoding="utf-8")
                wait_ui(lambda: len(app.rounds.snapshot().results) == 1 and
                        app.rounds.snapshot().results[0].status == "TESTING")
                record.write_text("MLB_SN,status\nSERIAL00000002,Pass\n", encoding="utf-8")
                wait_ui(lambda: app.rounds.snapshot().results[0].status == "FAIL")
                wait_ui(lambda: app.status_rows[1]["status"].cget("text") == "FAIL")

                snapshot = app.rounds.snapshot()
                self.assertTrue(snapshot.result_available)
                self.assertEqual(snapshot.results[0].sn, "SERIAL00000001")
                rejected = next(item.event for item in snapshot.events
                                if item.event.kind == "unknown_round_candidate_rejected")
                self.assertEqual(rejected.detail["operation"], "fail_unconfirmed_candidate")
                self.assertNotIn("reason", rejected.detail)
                self.assertTrue(app.rounds.flush_audit(timeout=3))
                from audit_records import read_round_audit
                stored = read_round_audit(app.rounds.session_path / "audit.jsonl")
                audit_event = next(item for item in stored["events"]
                                   if item["kind"] == "unknown_round_candidate_rejected")
                self.assertEqual(audit_event["status"], "TESTING")
                self.assertTrue(audit_event["operation_at"])
                self.assertEqual(audit_event["detail"]["candidate_sn"], "SERIAL00000002")
                self.assertNotIn("reason", audit_event["detail"])
                self.assertIsNotNone(rejected.localized_message)
                audit_bytes_before_refresh = (app.rounds.session_path / "audit.jsonl").read_bytes()
                state_before_refresh = app.rounds.snapshot()

                app.language_button.event_generate("<Button-1>")
                root.update()
                chinese_index = next(
                    index for index in range(app.language_menu.index("end") + 1)
                    if app.language_menu.entrycget(index, "label") == "繁體中文"
                )
                app.language_menu.invoke(chinese_index)
                root.update()

                self.assertTrue(any(
                    rejected.localized_message.traditional_chinese in line
                    for line in app.event_lines
                ), app.event_lines)
                self.assertEqual(app.rounds.snapshot().round_id, state_before_refresh.round_id)
                self.assertEqual(app.rounds.snapshot().results, state_before_refresh.results)
                self.assertEqual(app.rounds.snapshot().events, state_before_refresh.events)
                self.assertEqual((app.rounds.session_path / "audit.jsonl").read_bytes(),
                                 audit_bytes_before_refresh)

                app.language_button.event_generate("<Button-1>")
                root.update()
                english_index = next(
                    index for index in range(app.language_menu.index("end") + 1)
                    if app.language_menu.entrycget(index, "label") == "English"
                )
                app.language_menu.invoke(english_index)
                root.update()
                self.assertTrue(any(
                    rejected.localized_message.english in line for line in app.event_lines
                ), app.event_lines)
                self.assertEqual(app.rounds.snapshot().events, state_before_refresh.events)
                self.assertEqual((app.rounds.session_path / "audit.jsonl").read_bytes(),
                                 audit_bytes_before_refresh)
            finally:
                if app._round_is_active():
                    app.rounds.stop()
                app.rounds.flush_session(timeout=3)
                app.rounds.flush_audit(timeout=3)
                app._close_settings()
                app.hotkey.close()
                root.destroy()

    def test_real_tk_timeout_event_language_refresh_preserves_round_and_audit(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.deiconify()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey, session_root=Path(temporary) / "sessions",
            )
            sources = []

            class ControlledTimeoutMonitor(BaseMonitor):
                def poll_once(self):
                    return

            def source_factory(callback):
                source = ControlledTimeoutMonitor(
                    "FCT", {}, (1, 2), callback=callback,
                    session_root=Path(temporary) / "sessions",
                )
                sources.append(source)
                return source

            def pump_until(predicate, timeout=5):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    root.update()
                    if predicate():
                        return
                    time.sleep(0.01)
                self.fail("Timed out waiting for the shared timeout event: {} {}".format(
                    app.current_language, (app.event_lines, [
                        (record[0], getattr(record[1], "message_id", None))
                        for record in app._event_records
                    ], [(item.sequence, item.event.kind,
                         getattr(item.event.localized_message, "message_id", None))
                        for item in app.rounds.snapshot().events])))

            try:
                started = app.rounds.start("FCT", source_factory, run_async=True, capacity=2)
                app.active_round_id = started.round_id
                pump_until(lambda: sources and app.rounds.session_path is not None)
                pump_until(lambda: any(
                    event.event.kind == "round_ready"
                    for event in app.rounds.snapshot().events
                ))
                sources[0].publish_round_event(MonitorEvent(
                    "timeout", "FCT 尚未開始測試逾時", status="TIMEOUT",
                    detail={"kind": "start"},
                ))
                def timeout_is_visible():
                    event = next((event.event for event in app.rounds.snapshot().events
                                  if event.event.kind == "timeout"), None)
                    return (event is not None and event.localized_message is not None and
                            any(event.localized_message.english in line
                                for line in app.event_lines))

                pump_until(timeout_is_visible)
                self.assertTrue(app.rounds.flush_audit(timeout=3))
                session_path = app.rounds.session_path
                audit_path = session_path / "audit.jsonl"
                pump_until(audit_path.is_file)
                audit_bytes_before_refresh = audit_path.read_bytes()
                state_before_refresh = app.rounds.snapshot()
                timeout_event = next(event.event for event in state_before_refresh.events
                                     if event.event.kind == "timeout")
                self.assertIsNotNone(timeout_event.localized_message)

                app.language_button.event_generate("<Button-1>")
                root.update()
                chinese_index = next(
                    index for index in range(app.language_menu.index("end") + 1)
                    if app.language_menu.entrycget(index, "label") == "繁體中文"
                )
                app.language_menu.invoke(chinese_index)
                pump_until(lambda: any(
                    timeout_event.localized_message.traditional_chinese in line
                    for line in app.event_lines
                ))
                self.assertEqual(app.rounds.snapshot().round_id, started.round_id)
                self.assertEqual(app.rounds.snapshot().results, state_before_refresh.results)
                self.assertEqual(app.rounds.snapshot().events, state_before_refresh.events)
                self.assertEqual(audit_path.read_bytes(), audit_bytes_before_refresh)

                app.language_button.event_generate("<Button-1>")
                root.update()
                english_index = next(
                    index for index in range(app.language_menu.index("end") + 1)
                    if app.language_menu.entrycget(index, "label") == "English"
                )
                app.language_menu.invoke(english_index)
                pump_until(lambda: any(
                    timeout_event.localized_message.english in line for line in app.event_lines
                ))
                self.assertEqual(app.rounds.snapshot().events, state_before_refresh.events)
                self.assertEqual(audit_path.read_bytes(), audit_bytes_before_refresh)
            finally:
                if app._round_is_active():
                    app.rounds.stop()
                app.rounds.flush_session(timeout=3)
                app.rounds.flush_audit(timeout=3)
                self.wait_for_archive_checks(app.rounds)
                self.wait_for(lambda: app.rounds.app_event_status().complete)
                app.rounds.request_close()
                self.wait_for(lambda: app.rounds.close_status().status in {"complete", "failed"})
                close_status = app.rounds.close_status().status
                app.hotkey.close()
                app.app_events.stop()
                root.destroy()
                self.assertEqual(close_status, "complete", app.rounds.close_status())

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
                self.assertEqual([app.kvm_layout_marker.itemcget(cell, "fill") for cell in
                                  app.kvm_layout_marker.find_withtag("layout-cell")],
                                 ["#000000", "#ffffff"])
                self.assertEqual(root.winfo_height(), window_height(10, root.winfo_screenheight()))

                app.profile_editor_capacity.set("11")
                app.profile_editor_mapping.set(", ".join("{}:{}".format(source, source)
                                                            for source in range(1, 12)))
                app._apply_profile_editor()
                root.update()
                self.assertTrue(app.kvm_result_blocks[11].winfo_ismapped())
                self.assertEqual([app.kvm_layout_marker.itemcget(cell, "fill") for cell in
                                  app.kvm_layout_marker.find_withtag("layout-cell")],
                                 ["#ffffff", "#000000"])
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
                self.assertEqual(app.kvm_state_marker.winfo_x(), 278)
                self.assertEqual(app.kvm_state_marker.winfo_y(), 0)
                self.assertEqual(app.kvm_state_marker.winfo_width(), 26)
                self.assertGreater(app.kvm_result_blocks[1].winfo_y(),
                                   app.kvm_state_marker.winfo_y() + app.kvm_state_marker.winfo_height())
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
                app.rounds.request_close()
                self.wait_for(lambda: app.rounds.close_status().status == "complete")
                self.wait_for(lambda: app.rounds.app_event_status().complete)
                self.wait_for(lambda: app.rounds.retention_cleanup_status().status in
                              {"complete", "failed"})
                self.wait_for_archive_checks(app.rounds)
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
                app.rounds.request_close()
                self.wait_for(lambda: app.rounds.close_status().status == "complete")
                self.wait_for(lambda: app.rounds.app_event_status().complete)
                self.wait_for(lambda: app.rounds.retention_cleanup_status().status in
                              {"complete", "failed"})
                self.wait_for_archive_checks(app.rounds)
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
                self.assertIn("active configuration remains unchanged",
                              app.profile_editor_status.get())
            finally:
                app._close_settings()
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
                    source._select_language(TRADITIONAL_CHINESE)
                    source.retention_days_var.set("180")
                    source.retention_save_button.invoke()
                    source.profile_editor_project.set("Demo")
                    source.profile_editor_machine.set("DFU")
                    source.profile_editor_platform.set("atlas")
                    source.profile_editor_capacity.set("2")
                    source.profile_editor_paths["active"].set("/deployment/active")
                    source.profile_editor_paths["final"].set("/deployment/final")
                    source.profile_editor_mapping.set("1:2, 2:1")
                    source.profile_editor_timeouts["start"].set("45")
                    source._apply_profile_editor()
                    persisted_source = MachineProfileStore(source_preferences)
                    persisted_source.load()
                    self.assertEqual(persisted_source.language, TRADITIONAL_CHINESE)
                    self.assertEqual(persisted_source.retention_days, 180)
                    with patch("b518_log_solution.filedialog.asksaveasfilename", return_value=str(exported)):
                        source._export_profiles()
                    self.assertNotIn("retention_days", json.loads(exported.read_text(encoding="utf-8")))
                    source_ids = {
                        item["localized_message"]["message_id"]
                        for item in source.rounds.app_event_records()
                    }
                    self.assertIn("app.settings.event.profile.saved", source_ids)
                    self.assertIn("app.settings.event.profile.exported", source_ids)
                    self.assertIn("app.settings.event.retention.saved", source_ids)
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
                    deployed.retention_days_var.set("730")
                    deployed.retention_save_button.invoke()
                    deployed._select_language(TRADITIONAL_CHINESE)
                    with patch("b518_log_solution.filedialog.askopenfilename",
                               return_value=str(single_profile_export)):
                        deployed._import_profiles()
                    reloaded = MachineProfileStore(deployment_preferences)
                    reloaded.load()
                    self.assertEqual(reloaded.retention_days, 730)
                    self.assertEqual(reloaded.language, TRADITIONAL_CHINESE)
                    self.assertEqual(deployed.profiles.get("Demo", "DFU").paths["active"],
                                     "/deployment/active")
                    self.assertEqual((deployed.project.get(), deployed.station.get()), ("Demo", "DFU"))
                    self.assertIn("匯入後原選擇不存在",
                                  deployed.profile_editor_status.get())
                    original = deployed.profiles.to_dict()
                    invalid_export = Path(temporary) / "invalid.json"
                    invalid_export.write_text("{", encoding="utf-8")
                    with patch("b518_log_solution.filedialog.askopenfilename",
                               return_value=str(invalid_export)):
                        deployed._import_profiles()
                    self.assertEqual(deployed.profiles.to_dict(), original)
                    self.assertIn("原配置仍有效",
                                  deployed.profile_editor_status.get())
                    failed_import = next(
                        item for item in deployed.rounds.app_event_records()
                        if item["localized_message"]["message_id"] == "app.profile.import_failed")
                    self.assertIn("Expecting property name", failed_import["diagnostic"])
                    self.assertTrue(failed_import["localized_message"]["en"])
                    self.assertTrue(failed_import["localized_message"]["zh-TW"])

                    replacement = deployed.profiles.with_profile(replace(
                        deployed.profiles.get("Demo", "DFU"),
                        paths={"active": "/updated/active", "final": "/updated/final"},
                    ))
                    deployed.project.set("Demo")
                    deployed.station.set("DFU")
                    deployed.profile_store.save(replacement, "Demo", "DFU")
                    deployed._reload_profiles()

                    self.assertEqual(deployed.profiles.get("Demo", "DFU").paths["active"],
                                     "/updated/active")
                    self.assertEqual(deployed.profile_editor_project.get(), "Demo")
                    self.assertEqual(deployed.profiles.get("Demo", "DFU").paths["active"],
                                     "/updated/active")
                finally:
                    deployed._close_settings()
                    deployed.hotkey.close()
                    deploy_root.destroy()

    def test_app_completes_rswmt_final_only_round_through_shared_entry(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            output = Path(temporary) / "output" / "SmtCal"
            output.mkdir(parents=True)
            root = tk.Tk()
            root.deiconify()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey, session_root=Path(temporary) / "sessions",
            )
            round_ids = []
            try:
                app.open_settings()
                app.profile_editor_project.set("B518")
                app.profile_editor_machine.set("BT")
                app._load_profile_editor_selection()
                app.profile_editor_paths["final"].set(str(output))
                app.profile_editor_timeouts["start"].set("240")
                app._apply_profile_editor()
                app._close_settings()
                app.station.set("BT")
                app._profile_changed()
                app.start_button.invoke()

                prepare_deadline = time.monotonic() + 5
                while (app.rounds.session_path is None and time.monotonic() < prepare_deadline):
                    root.update()
                    time.sleep(0.01)
                self.assertIsNotNone(app.rounds.session_path)
                start = datetime.now().replace(microsecond=0)
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
                    root.update()
                    snapshot = app.rounds.snapshot()
                    if (snapshot.result_available and all(
                            app.status_rows[slot]["status"].cget("text") == "PASS"
                            for slot in range(1, 5))):
                        break
                    time.sleep(0.1)
                else:
                    app.rounds.stop()
                    self.fail("RS-WMT final-only files did not complete the App round")
                app.rounds.stop()
                app.rounds.flush_session(timeout=3)
                app.rounds.flush_audit(timeout=3)

                snapshot = app.rounds.snapshot()
                round_ids.append(snapshot.round_id)
                self.assertEqual(snapshot.station, "BT")
                self.assertEqual([result.status for result in snapshot.results], ["PASS"] * 4)
                self.assertTrue(all(app.status_rows[slot]["status"].cget("text") == "PASS"
                                    for slot in range(1, 5)))
                self.assertFalse(any(event.event.status == "TESTING" for event in snapshot.events))
                session_path = app.rounds.session_path
                session_metadata = json.loads((session_path / "session.json").read_text(
                    encoding="utf-8"))
                rebuilt = read_round_audit(session_path / "audit.jsonl")
                self.assertTrue(rebuilt["audit_complete"])
                self.assertEqual(rebuilt["round"]["config"]["config_snapshot"],
                                 session_metadata["settings"]["profile_snapshot"]["profile"])
            finally:
                app.rounds.stop()
                app.rounds.flush_session(timeout=3)
                app.rounds.flush_audit(timeout=3)
                statuses = self.wait_for_archive_checks(app.rounds)
                for round_id in round_ids:
                    self.assertEqual(app.rounds.archive_status(round_id).status, "archived",
                                     statuses)
                deadline = time.monotonic() + 5
                while (app.rounds.retention_cleanup_status().status not in {"complete", "failed"}
                       and time.monotonic() < deadline):
                    root.update()
                    time.sleep(0.01)
                app.hotkey.close()
                root.destroy()

    def test_awaiting_review_start_entrypoints_preserve_their_existing_side_effects(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.deiconify()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey, session_root=Path(temporary) / "sessions",
            )
            dfu_profile = app.profiles.get("B518", "DFU")
            app.profiles = app.profiles.with_profile(replace(
                dfu_profile, paths={"active": temporary, "final": temporary, "caseinfo": ""},
            ))
            sources = []

            def source_factory(callback):
                source = ControlledConflictMonitor(callback)
                sources.append(source)
                return source

            def pump_until(predicate, timeout=5):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    root.update()
                    if predicate():
                        return
                    time.sleep(0.01)
                self.fail("Timed out waiting for the controlled awaiting-review round")

            try:
                app.rounds.start("FCT", source_factory, run_async=True, capacity=2)
                pump_until(lambda: bool(sources) and app.rounds.snapshot().state == RoundState.RUNNING)
                sources[0].offer_candidate(
                    1, "SN-BASE", "FAIL", "/controlled/slot1/candidate.csv",
                    "base-candidate", "2026-10-08T10:00:02",
                )
                pump_until(lambda: app.rounds.snapshot().state == RoundState.AWAITING_REVIEW)
                original_round_id = app.rounds.snapshot().round_id

                # The direct start method historically saves the newly selected profile
                # and resets the board before RoundCoordinator returns the existing round.
                app.station.set("DFU")
                app._profile_changed()
                app.start_monitor()
                saved = json.loads((Path(temporary) / "preferences.json").read_text(encoding="utf-8"))
                self.assertEqual(saved["machine"], "DFU")
                self.assertEqual(app.rounds.snapshot().round_id, original_round_id)

                # Both shortcut paths reject AWAITING_REVIEW before saving preferences.
                app.station.set("FCT")
                root.event_generate("<Command-Shift-M>")
                root.update()
                self.assertEqual(app.rounds.snapshot().round_id, original_round_id)
                unchanged = json.loads((Path(temporary) / "preferences.json").read_text(
                    encoding="utf-8"))
                self.assertEqual(unchanged["machine"], "DFU")

                app.station.set("DFU")
                app.hotkey.callback()
                root.update()
                unchanged = json.loads((Path(temporary) / "preferences.json").read_text(
                    encoding="utf-8"))
                self.assertEqual(unchanged["machine"], "DFU")
                self.assertEqual(app.rounds.snapshot().state, RoundState.AWAITING_REVIEW)
            finally:
                app.rounds.stop()
                app.rounds.flush_audit(timeout=3)
                app._close_settings()
                app.hotkey.close()
                root.destroy()

    def test_legacy_profile_migration_preserves_valid_default_capacities(self):
        profiles, _project, _machine = migrate_legacy_preferences({})
        self.assertEqual(profiles.get("B518", "DFU").capacity, 7)
        self.assertEqual(profiles.get("B518", "FCT").capacity, 6)
        self.assertEqual(profiles.get("B482", "BT").capacity, 4)
        # The second profile-selection row reserves 26 pixels above the KVM band.
        self.assertEqual(window_height(4), 540)
        self.assertEqual(window_height(6), 634)
        self.assertEqual(window_height(7), 681)
        self.assertEqual(window_height(20), 708)
        self.assertEqual(visible_detail_rows(20, 500), 1)
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
            cleanup_deadline = time.monotonic() + 5
            while (app.rounds.retention_cleanup_status().status not in {"complete", "failed"}
                   and time.monotonic() < cleanup_deadline):
                root.update()
                time.sleep(.01)
            self.assertIn(app.rounds.retention_cleanup_status().status, {"complete", "failed"})
            app.hotkey.close()
            root.destroy()

    def test_empty_paths_are_rejected_before_monitor_creation(self):
        root = tk.Tk()
        root.withdraw()
        app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey)
        app.station.set("DFU")
        profile = app.profiles.get("B518", "DFU")
        app.profiles = app.profiles.with_profile(replace(profile, paths={"active": "", "final": ""}))
        try:
            with patch("b518_log_solution.DEFAULT_PLATFORM_REGISTRY.create_monitor") as monitor_type, \
                    patch("b518_log_solution.messagebox.showerror") as show_error:
                app.start_monitor()
            monitor_type.assert_not_called()
            show_error.assert_called_once()
            self.assertEqual(show_error.call_args.args[:2], (
                "Configuration Error",
                "The selected configuration is invalid: 請設定存在且可讀取的Atlas 即時 Log 路徑。",
            ))
            self.assertIsNone(app.rounds.snapshot())
        finally:
            cleanup_deadline = time.monotonic() + 5
            while (app.rounds.retention_cleanup_status().status not in {"complete", "failed"}
                   and time.monotonic() < cleanup_deadline):
                root.update()
                time.sleep(.01)
            self.assertIn(app.rounds.retention_cleanup_status().status, {"complete", "failed"})
            app.hotkey.close()
            root.destroy()

    def test_real_tk_preference_replace_failure_does_not_accept_round_or_leave_start_busy(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.deiconify()
            active = Path(temporary) / "active"
            final = Path(temporary) / "final"
            active.mkdir()
            final.mkdir()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey, session_root=Path(temporary) / "sessions",
            )
            try:
                app.open_settings()
                app.profile_editor_machine.set("FCT")
                app.profile_editor_paths["active"].set(str(active))
                app.profile_editor_paths["final"].set(str(final))
                app._apply_profile_editor()
                app._close_settings()
                preferences_before = app.profile_store.path.read_bytes()

                with patch("machine_profiles._atomic_write_text", side_effect=OSError("disk full")), \
                        patch("b518_log_solution.messagebox.showerror") as show_error:
                    app.start_button.invoke()

                self.assertIsNone(app.rounds.snapshot())
                self.assertEqual(str(app.start_button.cget("state")), "normal")
                self.assertEqual(app.monitor_state.cget("text"), "Standby")
                self.assertEqual(app.profile_store.path.read_bytes(), preferences_before)
                self.assertEqual(show_error.call_args.args[:2], (
                    "Configuration Save Failed",
                    "Configuration preferences could not be saved; the active configuration remains unchanged: disk full",
                ))
                self.assertFalse((Path(temporary) / "sessions").exists())
            finally:
                deadline = time.monotonic() + 5
                while (app.rounds.retention_cleanup_status().status not in {"complete", "failed"}
                       and time.monotonic() < deadline):
                    root.update()
                    time.sleep(0.01)
                app.hotkey.close()
                root.destroy()

    def test_operator_selects_project_and_machine_and_choice_survives_restart(self):
        with TemporaryDirectory() as temporary:
            app_root = Path(temporary) / "B518LogSolution"
            prefs = app_root / "preferences.json"
            session_root = app_root / "sessions"
            final = Path(temporary) / "b482-final"
            final.mkdir()
            with patch("b518_log_solution.APP_ROOT", app_root), \
                    patch("b518_log_solution.PREFS_PATH", prefs):
                root = tk.Tk()
                root.withdraw()
                app = B518LogSolutionApp(
                    root, hotkey_factory=FakeHotkey, session_root=session_root,
                )
                try:
                    self.assertEqual(app.project_choice.cget("values"), ("B518", "B482"))
                    app.project.set("B482")
                    app._project_changed()
                    self.assertEqual(app.machine_choice.cget("values"), ("BT",))
                    profile = app.profiles.get(app.project.get(), app.station.get())
                    self.assertEqual(profile.platform, "b482")
                    profile_paths = dict(profile.paths)
                    profile_paths["final"] = str(final)
                    profile_timeouts = dict(profile.timeouts)
                    profile_timeouts["round"] = 6300
                    app.profiles = app.profiles.with_profile(
                        replace(profile, paths=profile_paths, timeouts=profile_timeouts),
                    )
                    self.assertEqual(app.profiles.get("B482", "BT").timeouts["round"], 6300)
                    app._save_preferences()
                finally:
                    self.wait_for(lambda: app.rounds.retention_cleanup_status().status in {
                        "complete", "failed",
                    })
                    app.hotkey.close()
                    root.destroy()

                restarted_root = tk.Tk()
                restarted_root.deiconify()
                restarted = B518LogSolutionApp(
                    restarted_root, hotkey_factory=FakeHotkey, session_root=session_root,
                )

                def pump_until(predicate, timeout=8):
                    deadline = time.monotonic() + timeout
                    while time.monotonic() < deadline:
                        restarted_root.update()
                        if predicate():
                            return
                        time.sleep(0.01)
                    self.fail("Timed out starting the restored configuration: {}".format(
                        restarted.rounds.snapshot()))

                round_id = None
                try:
                    pump_until(lambda: restarted.rounds.retention_cleanup_status().status
                               in {"complete", "failed"})
                    self.assertEqual((restarted.project.get(), restarted.station.get()),
                                     ("B482", "BT"))
                    self.assertEqual(restarted.profiles.get("B482", "BT").timeouts["round"], 6300)
                    restarted.start_button.invoke()
                    pump_until(lambda: restarted.rounds.snapshot() is not None
                               and restarted.rounds.session_path is not None
                               and not restarted.rounds.snapshot().source_preparation_pending)
                    round_id = restarted.rounds.snapshot().round_id
                    session_path = restarted.rounds.session_path
                    session = json.loads((session_path / "session.json").read_text(encoding="utf-8"))
                    profile_snapshot = session["settings"]["profile_snapshot"]["profile"]
                    self.assertEqual(profile_snapshot["platform"], "b482")
                    self.assertEqual(profile_snapshot["timeouts"]["round"], 6300)
                    self.assertEqual(profile_snapshot["paths"]["final"], str(final))
                    self.assertTrue(restarted.rounds.flush_audit(timeout=3))
                    audit = read_round_audit(session_path / "audit.jsonl")
                    self.assertTrue(audit["audit_complete"])
                    self.assertEqual(audit["round"]["config"]["config_snapshot"], profile_snapshot)
                    self.assertEqual(audit["round"]["config"]["platform"], "b482")
                finally:
                    restarted.rounds.stop()
                    closing = restarted.rounds.request_close()
                    if closing.status not in {"complete", "failed"}:
                        pump_until(lambda: restarted.rounds.close_status().status
                                   in {"complete", "failed"})
                    statuses = self.wait_for_archive_checks(restarted.rounds)
                    if round_id is not None:
                        self.assertEqual(restarted.rounds.archive_status(round_id).status,
                                         "archived", statuses)
                    cleanup_deadline = time.monotonic() + 5
                    while (restarted.rounds.retention_cleanup_status().status
                           not in {"complete", "failed"} and time.monotonic() < cleanup_deadline):
                        restarted_root.update()
                        time.sleep(0.01)
                    restarted.hotkey.close()
                    restarted_root.destroy()

    def test_monitor_creation_error_is_visible_and_returns_to_standby(self):
        with TemporaryDirectory() as temporary:
            active = Path(temporary) / "active"
            final = Path(temporary) / "final"
            active.mkdir()
            final.mkdir()
            root = tk.Tk()
            root.withdraw()
            app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey)
            app.station.set("FCT")
            app.open_settings()
            app.profile_editor_machine.set("FCT")
            app.profile_editor_paths["active"].set(str(active))
            app.profile_editor_paths["final"].set(str(final))
            app._apply_profile_editor()
            app._close_settings()
            try:
                with patch("b518_log_solution.DEFAULT_PLATFORM_REGISTRY.create_monitor",
                           side_effect=PermissionError("denied")), \
                        patch("b518_log_solution.messagebox.showerror") as show_error:
                    app.start_monitor()
                    deadline = time.monotonic() + 3
                    while not show_error.called and time.monotonic() < deadline:
                        root.update()
                        time.sleep(0.01)
                self.assertFalse(app._round_is_active())
                self.assertEqual(app.monitor_state.cget("text"), "Start Failed")
                self.assertIn("denied", app.event_lines[-1])
                show_error.assert_called_once()
            finally:
                app.hotkey.close()
                root.destroy()

    def test_settings_expose_profile_editor_and_session_log_without_legacy_monitor_tab(self):
        root = tk.Tk()
        root.withdraw()
        app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey)
        try:
            app.open_settings()
            tabs = tuple(app.settings_notebook.tab(tab, "text")
                         for tab in app.settings_notebook.tabs())
            self.assertEqual(tabs, ("Engineer Configuration", "Events & Session", "Retention"))
        finally:
            app._close_settings()
            app.hotkey.close()
            root.destroy()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_open_settings_refreshes_language_in_place_and_keeps_invalid_draft(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey,
                session_root=Path(temporary) / "sessions",
                app_event_path=Path(temporary) / "app-events.json",
            )

            def click(widget):
                x, y = widget.winfo_width() // 2, widget.winfo_height() // 2
                widget.event_generate("<ButtonPress-1>", x=x, y=y)
                widget.event_generate("<ButtonRelease-1>", x=x, y=y)
                root.update()

            def select_language(language):
                click(app.language_button)
                index = next(
                    item for item in range(app.language_menu.index("end") + 1)
                    if app.language_menu.entrycget(item, "label") ==
                    ("English" if language == ENGLISH else "繁體中文"))
                app.language_menu.invoke(index)
                root.update()

            def find_button(parent, label):
                for child in parent.winfo_children():
                    if isinstance(child, ttk.Button) and child.cget("text") == label:
                        return child
                    found = find_button(child, label)
                    if found is not None:
                        return found
                return None

            try:
                app.open_settings()
                window = app.settings_window
                selected_tab = app.settings_notebook.tabs()[2]
                app.settings_notebook.select(selected_tab)
                app.profile_editor_project.set("Unsaved Project")
                app.profile_editor_capacity.set("not-a-number")
                app.profile_editor_machine.set("BT")
                click(find_button(app.settings_window, "Validate Draft"))
                before_status = app.profile_editor_status.get()
                self.assertIn("Configuration fields are invalid", before_status)
                self.wait_for(lambda: app.rounds.app_event_status().complete)
                event_bytes = app.app_events.path.read_bytes()

                # Change language through the same public selection boundary used by
                # the main language menu; the existing settings Toplevel must survive.
                select_language(TRADITIONAL_CHINESE)
                self.assertIs(app.settings_window, window)
                self.assertTrue(window.winfo_exists())
                self.assertEqual(app.profile_editor_project.get(), "Unsaved Project")
                self.assertEqual(app.profile_editor_capacity.get(), "not-a-number")
                self.assertEqual(app.profile_editor_machine.get(), "BT")
                self.assertIn("配置欄位錯誤", app.profile_editor_status.get())
                self.assertIn("容量必須是正整數", app.profile_editor_status.get())
                self.assertEqual(app.settings_notebook.select(), selected_tab)
                self.assertEqual(
                    tuple(app.settings_notebook.tab(tab, "text")
                          for tab in app.settings_notebook.tabs()),
                    ("工程師配置", "事件與 Session", "保存期限"),
                )

                export_button = find_button(app.settings_window, "匯出配置")
                failed_export_path = Path(temporary) / "missing" / "export.json"
                with patch("b518_log_solution.filedialog.asksaveasfilename",
                           return_value=str(failed_export_path)):
                    click(export_button)
                self.assertIn("無法匯出配置", app.profile_editor_status.get())
                self.wait_for(lambda: app.rounds.app_event_status().complete)
                event_bytes = app.app_events.path.read_bytes()

                select_language(ENGLISH)
                self.assertIs(app.settings_window, window)
                self.assertTrue(window.winfo_exists())
                self.assertEqual(
                    tuple(app.settings_notebook.tab(tab, "text")
                          for tab in app.settings_notebook.tabs()),
                    ("Engineer Configuration", "Events & Session", "Retention"),
                )
                self.assertEqual(app.profile_editor_project.get(), "Unsaved Project")
                self.assertEqual(app.profile_editor_capacity.get(), "not-a-number")
                self.assertIn("Configuration could not be exported", app.profile_editor_status.get())
                self.assertIn("No such file", app.profile_editor_status.get())
                self.assertEqual(app.settings_notebook.select(), selected_tab)
                self.assertEqual(app.app_events.path.read_bytes(), event_bytes)
            finally:
                app._close_settings()
                app.rounds.request_close()
                self.wait_for(lambda: app.rounds.close_status().status == "complete")
                self.wait_for(lambda: app.rounds.app_event_status().complete)
                self.wait_for(lambda: app.rounds.retention_cleanup_status().status in
                              {"complete", "failed"})
                self.wait_for_archive_checks(app.rounds)
                app.hotkey.close()
                app.app_events.stop()
                root.destroy()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_retention_setting_uses_visible_errors_and_persists_bilingual_app_events(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            preferences_path = Path(temporary) / "preferences.json"
            event_path = Path(temporary) / "app-events.json"
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey,
                session_root=Path(temporary) / "sessions", app_event_path=event_path,
            )
            release_write = threading.Event()

            def pump_until(predicate, timeout=5):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    root.update()
                    if predicate():
                        return
                    time.sleep(.01)
                self.fail("Timed out while pumping settings save UI")

            def click(widget):
                x, y = widget.winfo_width() // 2, widget.winfo_height() // 2
                widget.event_generate("<ButtonPress-1>", x=x, y=y)
                widget.event_generate("<ButtonRelease-1>", x=x, y=y)
                root.update()

            try:
                app.open_settings()
                original_days = app.profile_store.retention_days
                app.retention_days_var.set("0")
                click(app.retention_save_button)
                self.assertIn("positive integer", app.retention_status.get())
                self.assertEqual(app.profile_store.retention_days, original_days)
                self.assertIn("positive integer", app.rounds.app_event_records()[-1][
                    "localized_message"]["en"])

                app.retention_days_var.set("180")
                click(app.retention_save_button)
                pump_until(lambda: app.rounds.app_event_status().complete)
                self.assertEqual(app.profile_store.retention_days, 180)
                self.assertIn("180", app.retention_effective_label.cget("text"))
                saved_preferences = preferences_path.read_bytes()
                app.retention_days_var.set("730")
                with patch.object(app.profile_store, "save_retention_days",
                                  side_effect=OSError("preferences disk full")):
                    click(app.retention_save_button)
                self.assertIn("Could not save", app.retention_status.get())
                self.assertEqual(app.profile_store.retention_days, 180)
                self.assertEqual(app.retention_effective_label.cget("text"),
                                 "Effective setting: 180 days")
                self.assertEqual(preferences_path.read_bytes(), saved_preferences)
                pump_until(lambda: app.rounds.app_event_status().complete)
                reloaded = MachineProfileStore(preferences_path)
                reloaded.load()
                self.assertEqual(reloaded.retention_days, 180)
                records = read_app_event_store(event_path)["events"]
                retention_events = [
                    item for item in records
                    if item["localized_message"]["message_id"].startswith(
                        "app.settings.event.retention.")
                ]
                self.assertEqual(len(retention_events), 3)
                self.assertEqual(
                    [item["localized_message"]["message_id"] for item in retention_events],
                    ["app.settings.event.retention.invalid",
                     "app.settings.event.retention.saved",
                     "app.settings.event.retention.save_failed"],
                )
                self.assertTrue(all(item.get("round_id") is None for item in retention_events))
                self.assertTrue(all(item["localized_message"]["en"] and
                                    item["localized_message"]["zh-TW"]
                                    for item in retention_events))
                self.assertEqual(retention_events[-1]["diagnostic"],
                                 "preferences disk full")

                write_entered = threading.Event()
                atomic_replace = app_event_store._atomic_replace

                def hold_event_write(path, content):
                    write_entered.set()
                    if not release_write.wait(5):
                        raise OSError("test write gate timed out")
                    atomic_replace(path, content)

                with patch("app_event_store._atomic_replace", side_effect=hold_event_write):
                    app.rounds.record_app_event("app.settings.event.retention.saved", {"days": 180})
                    self.wait_for(write_entered.is_set)
                    app.rounds.request_close()
                    self.wait_for(lambda: app.rounds.close_status().status in {"saving", "waiting"})
                    app.retention_days_var.set("365")
                    click(app.retention_save_button)
                    self.assertIn(
                        "Cleanup paused while records are being saved for app close.",
                        app.retention_cleanup_status.get())
                    self.assertEqual(
                        app._retention_reason_text("封存資訊版本未知"),
                        "The archive metadata version is not supported.")
                    self.assertEqual(
                        app._retention_reason_text("封存時間無效或缺少時區"),
                        "The archive time is invalid or has no time zone.")
                    self.assertEqual(
                        app._retention_reason_text("封存資訊無法讀取：disk full"),
                        "Archive metadata could not be read: disk full")
                    app.language_button.event_generate("<Button-1>")
                    root.update()
                    chinese_index = next(
                        index for index in range(app.language_menu.index("end") + 1)
                        if app.language_menu.entrycget(index, "label") == "繁體中文"
                    )
                    app.language_menu.invoke(chinese_index)
                    root.update()
                    self.assertIn("關閉保存期間暫停清理", app.retention_cleanup_status.get())
                    self.assertNotIn("Cleanup paused", app.retention_cleanup_status.get())
                    self.assertEqual(
                        app._retention_reason_text("封存資訊版本未知"),
                        "封存資訊版本不受支援。")
                    self.assertEqual(
                        app._retention_reason_text("封存時間無效或缺少時區"),
                        "封存時間無效或缺少時區。")
                    release_write.set()
                    self.wait_for(lambda: app.rounds.app_event_status().complete)
                    self.wait_for(lambda: app.rounds.close_status().status == "complete")
            finally:
                release_write.set()
                app._close_settings()
                app.rounds.request_close()
                self.wait_for(lambda: app.rounds.close_status().status == "complete")
                self.wait_for(lambda: app.rounds.app_event_status().complete)
                self.wait_for(lambda: app.rounds.retention_cleanup_status().status in
                              {"complete", "failed"})
                self.wait_for_archive_checks(app.rounds)
                app.hotkey.close()
                app.app_events.stop()
                root.destroy()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_file_dialog_buttons_use_current_language_and_cancel_without_changes(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey,
                session_root=Path(temporary) / "sessions",
                app_event_path=Path(temporary) / "app-events.json",
            )
            try:
                app.open_settings()
                app.profile_editor_project.set("Unsaved")
                app.profile_editor_paths["active"].set("/draft/active")

                def find_button(parent, label):
                    for child in parent.winfo_children():
                        if isinstance(child, ttk.Button) and child.cget("text") == label:
                            return child
                        found = find_button(child, label)
                        if found is not None:
                            return found
                    return None

                choose_button = find_button(app.settings_window, "Choose Local Folder")
                import_button = find_button(app.settings_window, "Import Configuration")
                export_button = find_button(app.settings_window, "Export Configuration")
                self.assertIsNotNone(choose_button)
                self.assertIsNotNone(import_button)
                self.assertIsNotNone(export_button)

                with patch("b518_log_solution.filedialog.askdirectory", return_value="") as chooser:
                    choose_button.invoke()
                self.assertEqual(chooser.call_args.kwargs["title"], "Choose Configuration Path")
                self.assertTrue(chooser.call_args.kwargs["mustexist"])
                self.assertEqual(app.profile_editor_paths["active"].get(), "/draft/active")

                app._select_language(TRADITIONAL_CHINESE)
                import_button = find_button(app.settings_window, "匯入配置")
                export_button = find_button(app.settings_window, "匯出配置")
                with patch("b518_log_solution.filedialog.askopenfilename", return_value="") as chooser:
                    import_button.invoke()
                self.assertEqual(chooser.call_args.kwargs["title"], "匯入工程師配置")
                self.assertEqual(chooser.call_args.kwargs["filetypes"],
                                 (("JSON 配置", "*.json"), ("所有檔案", "*")))
                with patch("b518_log_solution.filedialog.asksaveasfilename",
                           return_value="") as chooser:
                    export_button.invoke()
                self.assertEqual(chooser.call_args.kwargs["title"], "匯出工程師配置")
                self.assertEqual(chooser.call_args.kwargs["defaultextension"], ".json")
                self.assertEqual(chooser.call_args.kwargs["filetypes"],
                                 (("JSON 配置", "*.json"),))
                self.assertEqual(app.profile_editor_project.get(), "Unsaved")
                self.assertEqual(app.profile_editor_paths["active"].get(), "/draft/active")
            finally:
                app._close_settings()
                app.rounds.request_close()
                self.wait_for(lambda: app.rounds.close_status().status == "complete")
                self.wait_for(lambda: app.rounds.app_event_status().complete)
                self.wait_for(lambda: app.rounds.retention_cleanup_status().status in
                              {"complete", "failed"})
                self.wait_for_archive_checks(app.rounds)
                app.hotkey.close()
                app.app_events.stop()
                root.destroy()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_english_profile_editor_controls_fit_the_existing_minimum_window(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.withdraw()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey, session_root=Path(temporary) / "sessions",
                app_event_path=Path(temporary) / "app-events.json",
            )
            try:
                app.open_settings()
                window = app.settings_window
                window.geometry("680x560")
                app.settings_notebook.select(app.settings_notebook.tabs()[0])
                root.update()
                right_edge = window.winfo_rootx() + window.winfo_width()
                visible_controls = []

                def collect(parent):
                    for child in parent.winfo_children():
                        if isinstance(child, (ttk.Label, ttk.Button, ttk.Entry, ttk.Combobox)) and \
                                child.winfo_ismapped():
                            visible_controls.append(child)
                        collect(child)

                collect(window)
                self.assertTrue(visible_controls)
                outside = [(widget.cget("text") if isinstance(widget, (ttk.Label, ttk.Button))
                            else widget.winfo_class(),
                            widget.winfo_rootx() + widget.winfo_width() - right_edge)
                           for widget in visible_controls
                           if widget.winfo_rootx() + widget.winfo_width() > right_edge]
                self.assertEqual(outside, [],
                                 "Settings controls extend beyond the window: {}".format(outside))
                self.assertTrue(any(isinstance(widget, ttk.Button) and
                                    widget.cget("text") == "Choose Local Folder"
                                    for widget in visible_controls))
                app.settings_notebook.select(app.settings_notebook.tabs()[2])
                root.update()
                visible_controls.clear()
                collect(window)
                outside = [(widget.cget("text") if isinstance(widget, (ttk.Label, ttk.Button))
                            else widget.winfo_class(),
                            widget.winfo_rootx() + widget.winfo_width() - right_edge)
                           for widget in visible_controls
                           if widget.winfo_rootx() + widget.winfo_width() > right_edge]
                self.assertEqual(outside, [],
                                 "Retention controls extend beyond the window: {}".format(outside))
                self.assertGreater(app.retention_help_label.winfo_height(), 42)
                self.assertIn("full 24 hours", app.retention_help_label.cget("text"))
            finally:
                app._close_settings()
                app.rounds.request_close()
                self.wait_for(lambda: app.rounds.close_status().status == "complete")
                self.wait_for(lambda: app.rounds.app_event_status().complete)
                self.wait_for(lambda: app.rounds.retention_cleanup_status().status in {
                    "complete", "failed"
                })
                self.wait_for_archive_checks(app.rounds)
                app.hotkey.close()
                app.app_events.stop()
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





    def test_queued_prior_round_event_cannot_change_the_new_round_ui(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            source = Path(temporary) / "source"
            source.mkdir()
            (source / "events.jsonl").write_text("", encoding="utf-8")
            session_root = Path(temporary) / "sessions"
            root = tk.Tk()
            root.deiconify()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey, session_root=session_root,
            )
            sample_profile = replace(
                app.profiles.get("B518", "FCT"), project="SAMPLE",
                platform="sample-json", capacity=2, paths={"active": str(source)},
                mapping=((1, 1), (2, 2)),
            )
            app.profiles = app.profiles.with_profile(sample_profile)
            app.project_choice.configure(values=app.profiles.projects)
            app.project.set("SAMPLE")
            app._project_changed()
            app.station.set("FCT")
            app._profile_changed()

            def pump_until(predicate, timeout=6):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    root.update()
                    if predicate():
                        return
                    time.sleep(0.01)
                self.fail("Timed out waiting for a Tk round transition: {}".format(
                    app.rounds.snapshot()))

            round_ids = []
            try:
                app.start_button.invoke()
                pump_until(lambda: app.rounds.snapshot() is not None
                           and app.rounds.session_path is not None
                           and not app.rounds.snapshot().source_preparation_pending)
                old_round_id = app.rounds.snapshot().round_id
                round_ids.append(old_round_id)

                app.stop_button.invoke()
                pump_until(lambda: app.rounds.snapshot().state == RoundState.STOPPED
                           and str(app.start_button.cget("state")) == "normal")

                app.start_button.invoke()
                pump_until(lambda: app.rounds.snapshot().round_id != old_round_id
                           and app.rounds.session_path is not None
                           and not app.rounds.snapshot().source_preparation_pending)
                new_round_id = app.rounds.snapshot().round_id
                round_ids.append(new_round_id)
                rows_before = tuple(
                    (app.status_rows[slot]["sn"].cget("text"),
                     app.status_rows[slot]["status"].cget("text"))
                    for slot in app.status_rows
                )
                stale = RoundEvent(old_round_id, 99, MonitorEvent(
                    "result", "stale PASS", 1, "STALE-SERIAL", "PASS",
                ))
                queued = threading.Event()
                root.after(0, lambda: (app.events.put(stale), queued.set()))
                pump_until(queued.is_set)
                drained = threading.Event()
                root.after(250, drained.set)
                pump_until(drained.is_set)

                self.assertEqual(app.rounds.snapshot().round_id, new_round_id)
                self.assertNotIn("stale PASS", app.event_lines)
                self.assertEqual(rows_before, tuple(
                    (app.status_rows[slot]["sn"].cget("text"),
                     app.status_rows[slot]["status"].cget("text"))
                    for slot in app.status_rows
                ))
            finally:
                app.rounds.stop()
                closing = app.rounds.request_close()
                if closing.status not in {"complete", "failed"}:
                    pump_until(lambda: app.rounds.close_status().status in {"complete", "failed"})
                statuses = self.wait_for_archive_checks(app.rounds)
                for round_id in round_ids:
                    self.assertEqual(app.rounds.archive_status(round_id).status, "archived",
                                     statuses)
                cleanup_deadline = time.monotonic() + 5
                while (app.rounds.retention_cleanup_status().status not in {"complete", "failed"}
                       and time.monotonic() < cleanup_deadline):
                    root.update()
                    time.sleep(0.01)
                app.hotkey.close()
                root.destroy()

    def test_final_result_brings_dashboard_to_front_without_permanent_topmost(self):
        app = object.__new__(B518LogSolutionApp)
        app.root = MagicMock()
        install_snapshot_results(app, (SimpleNamespace(slot=1, sn="SN123", status="PASS"),))
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
        install_snapshot_results(app, (SimpleNamespace(slot=1, sn="SN123", status="TIMEOUT"),))
        app.event_lines = []
        app.settings_log = None
        app._set_row = MagicMock()
        app._set_monitor_controls = MagicMock()

        app._handle_event(MonitorEvent("timeout", "FCT 尚未開始測試逾時", status="TIMEOUT",
                                       detail={"kind": "start"}))

        app._set_row.assert_not_called()
        app._set_monitor_controls.assert_called_once_with(False, "逾時停止")

    def test_test_timeout_keeps_monitoring_other_slots(self):
        app = object.__new__(B518LogSolutionApp)
        app.root = MagicMock()
        install_snapshot_results(app, (SimpleNamespace(slot=2, sn="SN123", status="TIMEOUT"),))
        app.event_lines = []
        app.settings_log = None
        app._set_row = MagicMock()
        app._set_monitor_controls = MagicMock()

        app._handle_event(MonitorEvent("timeout", "FCT slot2 測試逾時", 2, status="TIMEOUT",
                                       detail={"kind": "test"}))

        app._set_row.assert_called_once_with(2, "SN123", "TIMEOUT")
        app._set_monitor_controls.assert_not_called()

    def test_stopped_event_does_not_change_window_topmost_attribute(self):
        app = object.__new__(B518LogSolutionApp)
        app.root = MagicMock()
        app.event_lines = []
        app.settings_log = None
        app._set_monitor_controls = MagicMock()

        app._handle_event(MonitorEvent("stopped", "monitor ended"))

        app.root.attributes.assert_not_called()
        app._set_monitor_controls.assert_called_once_with(False)

    def test_close_waits_responsively_and_cancellation_invalidates_old_completion(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.withdraw()
            session_root = Path(temporary) / "sessions"
            app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey, session_root=session_root)
            rounds = RoundCoordinator(app.events.put, audit_root=session_root)
            app.rounds = rounds
            monitor_holder = {}

            class Monitor:
                def __init__(self, callback):
                    self.callback = callback
                    self.session = SessionStore("close-round", {}, session_root)
                    self.results = (SlotResult(1),)
                    self.start_count = 0

                def round_results(self):
                    return self.results

                def timeout_seconds(self, kind):
                    return {"start": 30, "test": 60, "round": 10}[kind]

                def update_round_settings(self, settings):
                    self.session.update_settings(settings)

                def publish_round_event(self, event):
                    self.session.enqueue_event(event.message, event.detail)
                    self.callback(event)

                def start(self):
                    self.start_count += 1

                def stop_collection(self):
                    pass

                def finish(self):
                    self.session.enqueue_finish()

                def stop(self):
                    self.callback(MonitorEvent("stopped", "stopped"))

                def poll_once(self):
                    pass

            def create(callback):
                monitor = Monitor(callback)
                monitor_holder["monitor"] = monitor
                return monitor

            def root_is_alive():
                try:
                    return bool(root.winfo_exists())
                except tk.TclError:
                    return False

            entered = threading.Event()
            release = threading.Event()
            original_write = audit_records.os.write
            blocked = [False]

            def hold_collection_stop(descriptor, content):
                if b"collection_stopped" in content and not blocked[0]:
                    blocked[0] = True
                    entered.set()
                    release.wait(8)
                return original_write(descriptor, content)

            try:
                started = rounds.start("FCT", create, run_async=False, capacity=1)
                app.active_round_id = started.round_id
                with patch.object(audit_records.os, "write", side_effect=hold_collection_stop):
                    app.close()
                    self.assertTrue(entered.wait(2))
                    ticks = []
                    root.after(0, lambda: ticks.append("responsive"))
                    deadline = time.monotonic() + 2.2
                    while time.monotonic() < deadline:
                        root.update()
                        time.sleep(0.01)
                    self.assertTrue(root.winfo_exists())
                    self.assertIn("responsive", ticks)
                    self.assertTrue(app._close_window.winfo_exists())
                    self.assertEqual(str(app.language_button["state"]), "disabled")
                    self.assertEqual(app._close_retry_button.cget("text"), "Retry Save")
                    self.assertEqual(app._close_cancel_button.cget("text"), "Cancel Closing")
                    self.assertIn("Cancel closing to change language",
                                  app._close_language_reason_label.cget("text"))
                    language_before_request = app.current_language
                    app_event_revision = app.app_events.revision
                    queued_language_result = []
                    root.after(0, lambda: queued_language_result.append(
                        app._select_language(TRADITIONAL_CHINESE)
                    ))
                    root.update()
                    app._select_language(TRADITIONAL_CHINESE)
                    self.assertEqual(len(queued_language_result), 1)
                    self.assertEqual(app.current_language, language_before_request)
                    self.assertEqual(app.language_choice.get(), language_before_request)
                    self.assertEqual(app.app_events.revision, app_event_revision)

                    app.cancel_close()
                    self.assertFalse(app.hotkey.closed)
                    self.assertEqual(str(app.language_button["state"]), "normal")
                    app._select_language(TRADITIONAL_CHINESE)
                    self.assertEqual(app.current_language, TRADITIONAL_CHINESE)
                    release.set()
                    self.wait_for(lambda: rounds.round_snapshot(started.round_id).save_state == "complete")
                    self.assertEqual(monitor_holder["monitor"].start_count, 1)
                    self.assertTrue(root.winfo_exists())

                app.close()
                self.assertEqual(app._close_window.title(), "關閉前保存")
                self.assertEqual(app._close_retry_button.cget("text"), "重試保存")
                self.assertEqual(app._close_cancel_button.cget("text"), "取消關閉")
                self.assertIn("取消關閉後即可切換", app._close_language_reason_label.cget("text"))
                self.wait_for(lambda: rounds.close_status().status == "complete")
                deadline = time.monotonic() + 2
                while root_is_alive() and time.monotonic() < deadline:
                    root.update()
                self.assertFalse(root_is_alive())
                self.assertTrue(app.hotkey.closed)
                rebuilt = read_round_audit(monitor_holder["monitor"].session.path / "audit.jsonl")
                self.assertTrue(rebuilt["audit_complete"])
                self.assertTrue(any(event["kind"] == "collection_stopped"
                                    for event in rebuilt["events"]))
            finally:
                release.set()
                if root_is_alive():
                    app.hotkey.close()
                    root.destroy()

    def test_close_failure_keeps_window_open_and_real_retry_rebuilds_complete_audit(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.withdraw()
            session_root = Path(temporary) / "sessions"
            app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey, session_root=session_root)
            rounds = RoundCoordinator(app.events.put, audit_root=session_root)
            app.rounds = rounds
            monitors = []

            class Monitor:
                def __init__(self, callback):
                    self.callback = callback
                    self.session = SessionStore("failed-close-round-{}".format(len(monitors)),
                                                {}, session_root)
                    self.results = (SlotResult(1),)

                def round_results(self):
                    return self.results

                def timeout_seconds(self, kind):
                    return {"start": 30, "test": 60, "round": 10}[kind]

                def update_round_settings(self, settings):
                    self.session.update_settings(settings)

                def publish_round_event(self, event):
                    self.session.enqueue_event(event.message, event.detail)
                    self.callback(event)

                def start(self):
                    pass

                def stop_collection(self):
                    pass

                def finish(self):
                    self.session.enqueue_finish()

                def stop(self):
                    self.callback(MonitorEvent("stopped", "stopped"))

                def poll_once(self):
                    pass

            def create(callback):
                monitor = Monitor(callback)
                monitors.append(monitor)
                return monitor

            original_write = audit_records.os.write
            fault_enabled = [True]
            retry_blocked = [False]
            retry_entered = threading.Event()
            release_retry = threading.Event()

            def persistent_fault(descriptor, content):
                if fault_enabled[0] and b"collection_stopped" in content:
                    if retry_blocked[0]:
                        retry_entered.set()
                        release_retry.wait(4)
                    raise OSError("persistent close audit fault")
                return original_write(descriptor, content)

            def pump_until(predicate, timeout=4):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    try:
                        root.update()
                    except tk.TclError:
                        if predicate():
                            return
                        raise
                    if predicate():
                        return
                    time.sleep(0.01)
                self.fail("Timed out while pumping the Tk close dialog")

            def root_is_alive():
                try:
                    return bool(root.winfo_exists())
                except tk.TclError:
                    return False

            try:
                previous = rounds.start("FCT", create, run_async=False, capacity=1)
                with patch.object(audit_records.os, "write", side_effect=persistent_fault):
                    rounds.stop()
                    pump_until(lambda: rounds.round_snapshot(previous.round_id).save_state == "failed")
                    current = rounds.start("FCT", create, run_async=False, capacity=1)
                    self.assertNotEqual(previous.round_id, current.round_id)
                    app.active_round_id = current.round_id
                    app.close()
                    pump_until(lambda: rounds.close_status().status == "failed" and
                               str(app._close_retry_button["state"]) == "normal")
                    self.assertFalse(rounds.round_snapshot(previous.round_id).audit_complete)
                    self.assertFalse(rounds.round_snapshot(current.round_id).audit_complete)
                    self.assertTrue(root_is_alive())
                    self.assertEqual(str(app._close_retry_button["state"]), "normal")
                    self.assertEqual(str(app.language_button["state"]), "disabled")
                    self.assertIn("Cancel closing to change language",
                                  app._close_language_reason_label.cget("text"))
                    self.assertIn("persistent close audit fault", app._close_error_label.cget("text"))

                    failed_generation = rounds.close_status().generation
                    retry_blocked[0] = True
                    app._close_retry_button.invoke()
                    app._close_retry_button.invoke()
                    pump_until(lambda: rounds.close_status().status == "saving" and
                               rounds.close_status().generation > failed_generation and
                               retry_entered.is_set())
                    app.cancel_close()
                    release_retry.set()
                    cancelled_generation = rounds.close_status().generation
                    self.assertEqual(rounds.close_status().status, "cancelled")
                    self.assertFalse(app.hotkey.closed)
                    self.assertTrue(root_is_alive())
                    pump_until(lambda: all(not rounds.round_snapshot(round_id).retry_in_progress
                                           for round_id in (previous.round_id, current.round_id)))
                    app._select_language(TRADITIONAL_CHINESE)
                    app.close()
                    self.assertEqual(app._close_window.title(), "關閉前保存")
                    pump_until(lambda: rounds.close_status().status == "failed" and
                               rounds.close_status().generation > cancelled_generation and
                               str(app._close_retry_button["state"]) == "normal")
                    self.assertTrue(root_is_alive())
                    self.assertIn("尚未完整保存", app._close_status_label.cget("text"))
                    self.assertIn("暫時無法切換語言",
                                  app._close_language_reason_label.cget("text"))
                    ui_tick = []
                    root.after(0, lambda: ui_tick.append(True))
                    root.update()
                    self.assertEqual(ui_tick, [True])
                    fault_enabled[0] = False

                app._close_retry_button.invoke()
                pump_until(lambda: rounds.close_status().status == "complete")
                pump_until(lambda: not root_is_alive())
                for round_id, monitor in zip((previous.round_id, current.round_id), monitors):
                    rebuilt = read_round_audit(monitor.session.path / "audit.jsonl")
                    self.assertTrue(rebuilt["audit_complete"])
                    self.assertEqual([event["kind"] for event in rebuilt["events"]].count(
                        "collection_stopped"), 1)
                    self.assertTrue(any(event["kind"] == "save_recovered"
                                        for event in rebuilt["events"]))
                    self.assertTrue(all(event["detail"].get("round_id", round_id) == round_id
                                        for event in rebuilt["events"]))
            finally:
                if root_is_alive():
                    app.hotkey.close()
                    root.destroy()

    def test_real_tk_close_waits_for_source_preparation_before_destroy(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.withdraw()
            session_root = Path(temporary) / "sessions"
            app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey, session_root=session_root)
            rounds = RoundCoordinator(app.events.put, audit_root=session_root)
            app.rounds = rounds
            preparation_entered = threading.Event()
            release_preparation = threading.Event()
            stopped = threading.Event()
            monitor_holder = {}

            class Monitor:
                def __init__(self, callback):
                    self.callback = callback
                    self.session = SessionStore("preparing-close-round", {}, session_root)
                    self.results = (SlotResult(1),)

                def round_results(self):
                    return self.results

                def timeout_seconds(self, kind):
                    return {"start": 30, "test": 60, "round": 10}[kind]

                def update_round_settings(self, settings):
                    self.session.update_settings(settings)

                def publish_round_event(self, event):
                    self.session.enqueue_event(event.message, event.detail)
                    self.callback(event)

                def start(self):
                    self.callback(MonitorEvent("round_ready", "ready"))

                def stop_collection(self):
                    pass

                def finish(self):
                    self.session.enqueue_finish()

                def stop(self):
                    stopped.set()
                    self.callback(MonitorEvent("stopped", "stopped"))

                def poll_once(self):
                    pass

            def create(callback):
                preparation_entered.set()
                if not release_preparation.wait(5):
                    raise RuntimeError("test did not release source preparation")
                monitor = Monitor(callback)
                monitor_holder["monitor"] = monitor
                return monitor

            def pump_until(predicate, timeout=5):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    try:
                        root.update()
                    except tk.TclError:
                        if predicate():
                            return
                        raise
                    if predicate():
                        return
                    time.sleep(0.01)
                self.fail("Timed out while pumping the Tk preparation/close flow")

            def root_is_alive():
                try:
                    return bool(root.winfo_exists())
                except tk.TclError:
                    return False

            try:
                started = rounds.start("FCT", create, run_async=True, capacity=1)
                app.active_round_id = started.round_id
                self.assertTrue(preparation_entered.wait(2))
                app.close()
                ticks = []
                root.after(0, lambda: ticks.append("responsive"))
                pump_until(lambda: rounds.close_status().status == "waiting")
                self.assertIn("responsive", ticks)
                self.assertTrue(root_is_alive())
                self.assertTrue(app._close_window.winfo_exists())
                self.assertNotIn("monitor", monitor_holder)

                release_preparation.set()
                pump_until(lambda: rounds.close_status().status == "complete")
                pump_until(lambda: not root_is_alive())
                self.assertTrue(stopped.is_set())
                monitor = monitor_holder["monitor"]
                rebuilt = read_round_audit(monitor.session.path / "audit.jsonl")
                self.assertTrue(rebuilt["audit_complete"])
                self.assertEqual([event["kind"] for event in rebuilt["events"]].count(
                    "collection_stopped"), 1)
                self.assertTrue(app.hotkey.closed)
            finally:
                release_preparation.set()
                if root_is_alive():
                    app.hotkey.close()
                    root.destroy()

    def test_real_tk_close_keeps_conflict_and_alarm_actions_available(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.withdraw()
            session_root = Path(temporary) / "sessions"
            app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey, session_root=session_root)
            elapsed = [0.0]
            rounds = RoundCoordinator(app.events.put, monotonic=lambda: elapsed[0],
                                      audit_root=session_root)
            app.rounds = rounds
            holder = {}

            class Monitor:
                def __init__(self, callback):
                    self.callback = callback
                    self.session = SessionStore("operator-close-round", {}, session_root)
                    self.results = (SlotResult(1), SlotResult(2))

                def round_results(self):
                    return self.results

                def timeout_seconds(self, kind):
                    return {"start": 30, "test": 60, "round": 1}[kind]

                def update_round_settings(self, settings):
                    self.session.update_settings(settings)

                def publish_round_event(self, event):
                    self.session.enqueue_event(event.message, event.detail)
                    self.callback(event)

                def start(self):
                    pass

                def stop_collection(self):
                    pass

                def finish(self):
                    self.session.enqueue_finish()

                def stop(self):
                    self.callback(MonitorEvent("stopped", "stopped"))

                def poll_once(self):
                    pass

                def apply_round_result(self, slot, status, sn="", source="", detail=None,
                                       lock_terminal=False):
                    result = self.results[slot - 1]
                    result.sn = sn or result.sn
                    result.status = status
                    result.source = source or result.source
                    self.session.enqueue_results(self.results)
                    self.publish_round_event(MonitorEvent(
                        "result", "slot{} {}".format(slot, status), slot=slot, sn=result.sn,
                        status=status, source=source, detail=detail or {},
                    ))

                def set_result(self, slot, status, detail=None, lock_terminal=False):
                    self.apply_round_result(slot, status, detail=detail, lock_terminal=lock_terminal)

            def create(callback):
                holder["monitor"] = Monitor(callback)
                return holder["monitor"]

            def pump_until(predicate, timeout=5):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    try:
                        root.update()
                    except tk.TclError:
                        if predicate():
                            return
                        raise
                    if predicate():
                        return
                    time.sleep(0.01)
                self.fail("Timed out while pumping the Tk operator/close flow")

            def root_is_alive():
                try:
                    return bool(root.winfo_exists())
                except tk.TclError:
                    return False

            try:
                started = rounds.start("FCT", create, run_async=False,
                                       round_timeout_seconds=1, capacity=2)
                app.active_round_id = started.round_id
                monitor = holder["monitor"]
                evidence = {"round_evidence_id": "fct:1:run-a",
                            "source_time": "2026-10-07T10:00:00", "source_id": "active.csv"}
                monitor.apply_round_result(1, "PASS", "SERIAL000001", "active.csv", evidence)
                candidate = MonitorEvent(
                    "result_candidate", "conflicting final result", slot=1, sn="SERIAL000001",
                    status="FAIL", source="final.csv",
                    detail=dict(evidence, source_id="final.csv"),
                )
                self.assertEqual(monitor.callback(candidate), "defer")
                elapsed[0] = 2.0
                expired = rounds.poll_once()
                self.assertEqual(len(expired.pending_conflicts), 1)
                self.assertIsNotNone(expired.round_alarm)
                pump_until(lambda: app.conflict_window and app.conflict_window.winfo_exists() and
                           app.round_alarm_window and app.round_alarm_window.winfo_exists())

                app.close()
                pump_until(lambda: rounds.close_status().status == "waiting")
                self.assertTrue(root_is_alive())
                self.assertEqual(str(app.resolve_conflict_original_button["state"]), "normal")
                self.assertEqual(str(app.round_alarm_ack_button["state"]), "normal")
                self.assertIn("Cancel closing to change language",
                              app._close_language_reason_label.cget("text"))
                app._select_language(TRADITIONAL_CHINESE)
                self.assertEqual(app.current_language, ENGLISH)
                self.assertEqual(str(app.language_button["state"]), "disabled")
                self.assertIn("Cancel closing to change language",
                              app._close_language_reason_label.cget("text"))

                selected_conflict_id = app._conflict_ids[app.conflict_list.curselection()[0]]
                alarm_identity = app._shown_round_alarm_identity
                english_index = next(
                    index for index in range(app.language_menu.index("end") + 1)
                    if app.language_menu.entrycget(index, "label") == "English")
                app.language_menu.invoke(english_index)
                root.update_idletasks()
                self.assertEqual(app.current_language, ENGLISH)
                self.assertEqual(app.conflict_window.title(), "Same-Round Result Conflict")
                self.assertEqual(app.round_alarm_window.title(), "Round Monitoring Timeout")
                self.assertEqual(app._conflict_ids[app.conflict_list.curselection()[0]],
                                 selected_conflict_id)
                self.assertEqual(app._shown_round_alarm_identity, alarm_identity)
                self.assertEqual(str(app.resolve_conflict_original_button["state"]), "normal")
                self.assertEqual(str(app.round_alarm_ack_button["state"]), "normal")
                self.assertIn("Round", app.round_alarm_message.cget("text"))
                self.assertFalse(rounds.snapshot().round_alarm.acknowledged_at)
                self.assertNotIn("顯示位置", app.conflict_position_label.cget("text"))
                chinese_index = next(
                    index for index in range(app.language_menu.index("end") + 1)
                    if app.language_menu.entrycget(index, "label") == "繁體中文")
                app.language_menu.invoke(chinese_index)
                root.update_idletasks()
                self.assertEqual(app.current_language, ENGLISH)
                self.assertIn("Round", app.round_alarm_message.cget("text"))
                self.assertIn("Acknowledge this alarm", app.round_alarm_message.cget("text"))
                self.assertFalse(rounds.snapshot().round_alarm.acknowledged_at)

                app.conflict_list.selection_set(0)
                app.resolve_conflict_original_button.invoke()
                self.assertEqual(len(rounds.round_snapshot(started.round_id).pending_conflicts), 0)
                self.assertEqual(rounds.close_status().status, "waiting")
                app.round_alarm_ack_button.invoke()
                pump_until(lambda: rounds.close_status().status == "complete")
                pump_until(lambda: not root_is_alive())

                rebuilt = read_round_audit(monitor.session.path / "audit.jsonl")
                kinds = [event["kind"] for event in rebuilt["events"]]
                self.assertTrue(rebuilt["audit_complete"])
                self.assertEqual(kinds.count("conflict_resolved"), 1)
                self.assertEqual(kinds.count("round_alarm_acknowledged"), 1)
                self.assertTrue(all(event["detail"].get("round_id", started.round_id) ==
                                    started.round_id for event in rebuilt["events"]))
                decisions = [event for event in rebuilt["events"]
                             if event["kind"] in {"conflict_resolved", "round_alarm_acknowledged"}]
                self.assertEqual(len(decisions), 2)
                self.assertEqual({event["kind"] for event in decisions}, {
                    "conflict_resolved", "round_alarm_acknowledged",
                })
                for event in decisions:
                    localized = event["localized_message"]
                    self.assertTrue(localized["en"])
                    self.assertTrue(localized["zh-TW"])
            finally:
                if root_is_alive():
                    app.hotkey.close()
                    root.destroy()


if __name__ == "__main__":
    unittest.main()
