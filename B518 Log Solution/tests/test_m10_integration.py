"""Source-App acceptance at the real Tk, shared-round and disk boundaries."""
import os
import json
import time
import tkinter as tk
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from tkinter import ttk
from unittest.mock import patch

from b518_log_solution import B518LogSolutionApp
from language_catalog import ENGLISH, TRADITIONAL_CHINESE
from app_event_store import read_app_event_store
from audit_records import read_round_audit
from machine_profiles import MachineProfileStore
from monitoring_round import RoundCoordinator
from round_start_preparation import RoundStartPreparation


class LocalHotkey:
    available = True
    message = "local test input"

    def __init__(self, callback):
        self.callback = callback

    def close(self):
        pass


def widgets(parent):
    for child in parent.winfo_children():
        yield child
        yield from widgets(child)


@unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1", "requires desktop Tk")
class M10SourceIntegrationTests(unittest.TestCase):
    def pump(self, root, predicate, timeout=20):
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
            time.sleep(.01)
        self.fail("Timed out waiting for public App state")

    def test_real_source_all_windows_switch_cancel_and_single_decisions(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.APP_ROOT", Path(temporary)), \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            base = Path(temporary)
            source = base / "source"
            source.mkdir()
            source_file = source / "events.jsonl"
            source_file.write_text("", encoding="utf-8")
            store = MachineProfileStore(base / "preferences.json")
            catalog, _, _, _ = store.load()
            profile = replace(catalog.get("B518", "FCT"), platform="sample-json", capacity=3,
                              mapping=((1, 1), (2, 2), (3, 3)), paths={"active": str(source)},
                              timeouts={"start": 30, "test": 60, "round": 120})
            store.save(catalog.with_profile(profile), "B518", "FCT")
            elapsed = [0.0]
            root = tk.Tk()
            with patch("b518_log_solution.RoundCoordinator", side_effect=lambda *a, **kw:
                       RoundCoordinator(*a, monotonic=lambda: elapsed[0], **kw)):
                app = B518LogSolutionApp(root, hotkey_factory=LocalHotkey,
                                         session_root=base / "sessions")

            class ClockPreparation(RoundStartPreparation):
                def prepare(self, profile, session_root, **kwargs):
                    return super().prepare(profile, session_root,
                                           monotonic=lambda: elapsed[0], **kwargs)

            app.round_start_preparation = ClockPreparation()

            def append(kind, position, sn, status, second):
                with source_file.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps({"kind": kind, "position": position,
                        "sn": sn, "status": status, "batch_id": "m10-integrated",
                        "source_time": "2026-10-12T10:00:{:02d}".format(second)}) + "\n")

            try:
                app.start_button.invoke()
                self.pump(root, lambda: app.rounds.session_path is not None
                          and len(app.rounds.snapshot().results) == 3
                          and not app.rounds.snapshot().source_preparation_pending)
                self.assertFalse(any("監控已開始" in line for line in app.event_lines))
                append("activity", 3, "", "TESTING", 0)
                append("final", 1, "SN-ORIGINAL", "PASS", 1)
                self.pump(root, lambda: app.rounds.snapshot().results[0].status == "PASS")
                append("final", 1, "SN-NEW", "FAIL", 2)
                self.pump(root, lambda: len(app.rounds.snapshot().pending_conflicts) == 1
                          and app.conflict_window is not None)
                app.settings_button.invoke()
                app.profile_editor_project.set("Unsaved / 未保存")
                app.profile_editor_capacity.set("invalid draft")
                app.open_app_diagnostics()
                app.open_historical_events()
                self.pump(root, lambda: app.rounds.app_event_status().complete)
                app.conflict_list.selection_set(0)
                app.conflict_list.event_generate("<<ListboxSelect>>")
                before = app.rounds.snapshot()
                for index in (1, 0, 1, 0):
                    app.language_menu.invoke(index)
                    root.update()
                    self.assertEqual(app.rounds.snapshot().pending_conflicts, before.pending_conflicts)
                    self.assertEqual(app.profile_editor_capacity.get(), "invalid draft")
                append("final", 2, "SN-OTHER", "PASS", 3)
                self.pump(root, lambda: app.rounds.snapshot().results[1].status == "PASS")
                elapsed[0] = 121.0
                app.rounds.poll_once()
                self.pump(root, lambda: app.round_alarm_window is not None)
                windows = (app.settings_window, app.conflict_window, app.round_alarm_window,
                           app.app_diagnostics_window, app.historical_event_window)
                before = app.rounds.snapshot()
                self.pump(root, lambda: app.rounds.app_event_status().complete
                          and app.rounds.snapshot().save_state == "complete")
                audit_path = app.rounds.session_path / "audit.jsonl"
                journal = base / "app-events.json"
                original_bytes = (audit_path.read_bytes(), journal.read_bytes())
                for index in (1, 0, 1):
                    app.language_menu.invoke(index)
                    root.update()
                    self.assertEqual(windows, (app.settings_window, app.conflict_window,
                        app.round_alarm_window, app.app_diagnostics_window, app.historical_event_window))
                    self.assertTrue(all(w.winfo_viewable() for w in windows))
                    expected_titles = (("B518 Log Solution 設定", "同輪結果衝突",
                        "整輪監控逾時", "App 診斷", "歷史事件") if index else
                        ("B518 Log Solution Settings", "Same-Round Result Conflict",
                         "Round Monitoring Timeout", "App diagnostics", "Historical Events"))
                    self.assertEqual(tuple(w.title() for w in windows), expected_titles)
                    self.assertIn("確認" if index else "Acknowledge",
                                  app.round_alarm_message.cget("text"))
                    self.assertIn("原結果" if index else "Original Result",
                                  app.conflict_comparison.get("1.0", "end"))
                    self.assertTrue(any(("App 已啟動" if index else "Application started") in
                        app.app_diagnostics_list.get(i) for i in range(app.app_diagnostics_list.size())))
                    self.assertTrue(any(("App 已啟動" if index else "Application started") in
                        app.historical_event_list.get(i) for i in range(app.historical_event_list.size())))
                    self.assertEqual(app.rounds.snapshot().pending_conflicts, before.pending_conflicts)
                    self.assertEqual(app.rounds.snapshot().round_alarm, before.round_alarm)
                    self.assertEqual(app.profile_editor_project.get(), "Unsaved / 未保存")
                    self.assertIn("SN-NEW", app.conflict_details.get("1.0", "end"))
                self.assertEqual(original_bytes, (audit_path.read_bytes(), journal.read_bytes()))
                self.assertIn("衝突", app.conflict_window.title())
                app.close()
                self.pump(root, lambda: app.rounds.close_status().status == "waiting")
                self.assertEqual(str(app.language_button["state"]), "disabled")
                app.language_menu.invoke(0)
                self.assertEqual(app.current_language, TRADITIONAL_CHINESE)
                app._close_cancel_button.invoke()
                root.update()
                self.assertEqual(str(app.language_button["state"]), "normal")
                self.assertEqual(app.rounds.snapshot().pending_conflicts, before.pending_conflicts)
                app.language_menu.invoke(0)
                self.assertEqual(app.current_language, ENGLISH)
                app.resolve_conflict_original_button.invoke()
                app.round_alarm_ack_button.invoke()
                self.assertFalse(app.rounds.snapshot().pending_conflicts)
                app.close()
                self.pump(root, lambda: app.rounds.close_status().status == "complete")
                def destroyed():
                    try:
                        return not root.winfo_exists()
                    except tk.TclError:
                        return True
                self.pump(root, destroyed)
                self.assertTrue(destroyed())
                audit = read_round_audit(audit_path)
                operations = [e for e in audit["events"] if e["kind"] in
                              ("conflict_resolved", "round_alarm_acknowledged")]
                self.assertEqual(len(operations), 2)
                self.assertTrue(all(e["localized_message"]["en"] and
                                    e["localized_message"]["zh-TW"] for e in operations))
                self.assertTrue(read_app_event_store(journal)["events"])
            finally:
                if app.rounds.close_status().status != "complete":
                    app.rounds.stop()
                    snapshot = app.rounds.snapshot()
                    if snapshot is not None:
                        for conflict in snapshot.pending_conflicts:
                            app.rounds.resolve_review(conflict.conflict_id, "original")
                        alarm = app.rounds.snapshot().round_alarm
                        if alarm and not alarm.acknowledged_at:
                            app.rounds.acknowledge_round_alarm(snapshot.round_id, alarm.alarm_id)
                    if app.rounds.close_status().status == "cancelled":
                        app.close()
                    elif not app._closing_ui:
                        app.close()
                    self.pump(root, lambda: app.rounds.close_status().status == "complete")
                app.hotkey.close()
                app.app_events.stop()
                try:
                    root.destroy()
                except tk.TclError:
                    pass

    def test_session_directory_failure_is_visible_and_persisted(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.APP_ROOT", Path(temporary)), \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            base = Path(temporary)
            root = tk.Tk()
            app = B518LogSolutionApp(root, hotkey_factory=LocalHotkey,
                                     session_root=base / "sessions")
            callback_errors, observations = [], []
            root.report_callback_exception = lambda *args: callback_errors.append(args)
            original_mkdir = Path.mkdir

            def fail_directory(path, *args, **kwargs):
                if path == app.session_root:
                    raise PermissionError("session directory denied")
                return original_mkdir(path, *args, **kwargs)

            def acknowledge():
                notices = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)
                           and w.title() == "Open Session Records"]
                if notices and notices[0].winfo_viewable():
                    notice = notices[0]
                    body = next(w for w in widgets(notice) if isinstance(w, tk.Text))
                    observations.append(body.get("1.0", "end"))
                    next(w for w in widgets(notice) if isinstance(w, ttk.Button)).invoke()
                elif notices:
                    root.after(10, acknowledge)

            try:
                app.settings_button.invoke()
                open_button = next(w for w in widgets(app.settings_window)
                                   if isinstance(w, ttk.Button) and w.cget("text") == "Open Session Records")
                timer = root.after(50, acknowledge)
                with patch.object(Path, "mkdir", fail_directory):
                    open_button.invoke()
                root.after_cancel(timer)
                self.assertEqual(callback_errors, [])
                self.assertEqual(len(observations), 1)
                self.assertIn("Session records could not be opened", observations[0])
                self.assertIn("Original diagnostic: session directory denied", observations[0])
                app.close()
                self.pump(root, lambda: app.rounds.close_status().status == "complete")
                records = read_app_event_store(base / "app-events.json")["events"]
                failures = [e for e in records if e["localized_message"]["message_id"] ==
                            "app.settings.event.session.open_failed"]
                self.assertEqual(len(failures), 1)
                self.assertEqual(failures[0]["diagnostic"], "session directory denied")
            finally:
                if app.rounds.close_status().status != "complete":
                    app.close()
                    self.pump(root, lambda: app.rounds.close_status().status == "complete")
                app.hotkey.close()
                app.app_events.stop()
                try:
                    root.destroy()
                except tk.TclError:
                    pass

    def test_language_refresh_preserves_event_log_reading_position(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.APP_ROOT", Path(temporary)), \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            app = B518LogSolutionApp(root, hotkey_factory=LocalHotkey,
                                     session_root=Path(temporary) / "sessions")
            try:
                app.settings_button.invoke()
                validate = next(w for w in widgets(app.settings_window)
                                if isinstance(w, ttk.Button) and w.cget("text") == "Validate Draft")
                for index in range(80):
                    validate.invoke()
                app.settings_notebook.select(app.settings_notebook.tabs()[1])
                self.pump(root, lambda: len(app.event_lines) >= 80)
                root.update_idletasks()
                app.settings_log.yview_moveto(.25)
                root.update_idletasks()
                app.settings_log.tag_add("sel", "5.0", "5.10")
                reading = app.settings_log.yview()[0]
                app.rounds.record_app_event("app.startup.started", {}, "\n".join("raw diagnostic {}".format(i) for i in range(80)))
                app.open_app_diagnostics()
                root.update()
                app.app_diagnostics_list.selection_clear(0, "end")
                app.app_diagnostics_list.selection_set(app.app_diagnostics_list.size() - 1)
                app.app_diagnostics_list.event_generate("<<ListboxSelect>>")
                root.update()
                app.app_diagnostics_list.yview_moveto(.25)
                app.app_diagnostics_detail.yview_moveto(.25)
                root.update_idletasks()
                list_reading = app.app_diagnostics_list.yview()[0]
                detail_reading = app.app_diagnostics_detail.yview()[0]
                app.language_menu.invoke(1)
                root.update_idletasks()
                self.assertAlmostEqual(app.settings_log.yview()[0], reading, delta=.03)
                self.assertIn("工程師配置草稿", app.settings_log.get("1.0", "end"))
                self.assertEqual(tuple(map(str, app.settings_log.tag_ranges("sel"))), ("5.0", "5.10"))
                self.assertAlmostEqual(app.app_diagnostics_list.yview()[0], list_reading, delta=.03)
                self.assertAlmostEqual(app.app_diagnostics_detail.yview()[0], detail_reading, delta=.03)
                app.close()
                self.pump(root, lambda: app.rounds.close_status().status == "complete")
            finally:
                if app.rounds.close_status().status != "complete":
                    app.close()
                    self.pump(root, lambda: app.rounds.close_status().status == "complete")
                app.hotkey.close()
                app.app_events.stop()
                try:
                    root.destroy()
                except tk.TclError:
                    pass

    def test_visible_language_write_error_refresh_keeps_original_preferences(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.APP_ROOT", Path(temporary)), \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            base = Path(temporary)
            preferences = base / "preferences.json"
            store = MachineProfileStore(preferences)
            catalog, project, station, _ = store.load()
            store.save(catalog, project, station)
            original_bytes = preferences.read_bytes()
            root = tk.Tk()
            app = B518LogSolutionApp(root, hotkey_factory=LocalHotkey,
                                     session_root=base / "sessions")
            root.update()
            errors, shown = [], []
            original_replace = os.replace

            def fail_preferences(source, destination, *args, **kwargs):
                if Path(destination) == preferences:
                    raise OSError("preference disk full")
                return original_replace(source, destination, *args, **kwargs)

            failure = patch("machine_profiles.os.replace", side_effect=fail_preferences)

            def inspect():
                failure.stop()
                try:
                    notice = next(child for child in root.winfo_children()
                                  if isinstance(child, tk.Toplevel) and child.title() == "語言設定未保存")
                    body = next(child for child in widgets(notice) if isinstance(child, tk.Text))
                    self.assertTrue(notice.winfo_viewable())
                    self.assertIn("保存失敗", body.get("1.0", "end"))
                    self.assertIn("preference disk full", body.get("1.0", "end"))
                    self.assertEqual(preferences.read_bytes(), original_bytes)
                    self.assertEqual(app.current_language, TRADITIONAL_CHINESE)
                    app.language_menu.invoke(0)
                    root.update_idletasks()
                    self.assertEqual(notice.title(), "Language Preference Not Saved")
                    self.assertIn("could not be saved", body.get("1.0", "end"))
                    self.assertIsNone(app.rounds.snapshot())
                    shown.append(notice)
                    next(child for child in widgets(notice) if isinstance(child, ttk.Button)).invoke()
                except Exception as error:
                    errors.append(error)
                    for child in root.winfo_children():
                        if isinstance(child, tk.Toplevel):
                            child.destroy()

            try:
                root.after(50, inspect)
                failure.start()
                with patch("tkinter.messagebox.showerror") as legacy_modal:
                    app.language_menu.invoke(1)
                    self.pump(root, lambda: errors or shown)
                    legacy_modal.assert_not_called()
                self.assertEqual(errors, [])
                self.assertEqual(len(shown), 1)
                app.close()
                self.pump(root, lambda: app.rounds.close_status().status == "complete")
                records = read_app_event_store(base / "app-events.json")["events"]
                failures = [item for item in records if item["localized_message"]["message_id"]
                            == "app.language.preference_save_failed"]
                self.assertEqual(len(failures), 1)
                self.assertNotIn("round_id", failures[0])
                self.assertIn("preference disk full", failures[0]["diagnostic"])
            finally:
                failure.stop()
                app.hotkey.close()
                app.app_events.stop()
                try:
                    root.destroy()
                except tk.TclError:
                    pass

    def test_visible_source_failure_notice_and_fixed_bilingual_audit(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.APP_ROOT", Path(temporary)), \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            base = Path(temporary)
            for name in ("active", "final"):
                (base / name).mkdir()
            store = MachineProfileStore(base / "preferences.json")
            catalog, _, _, _ = store.load()
            profile = replace(catalog.get("B518", "FCT"),
                              paths={name: str(base / name) for name in ("active", "final")})
            store.save(catalog.with_profile(profile), "B518", "FCT")
            root = tk.Tk()
            app = B518LogSolutionApp(root, hotkey_factory=LocalHotkey,
                                     session_root=base / "sessions")
            root.update()
            errors, shown = [], []

            def inspect():
                try:
                    notice = next(child for child in root.winfo_children()
                                  if isinstance(child, tk.Toplevel) and child.title() == "Start Failed")
                    body = next(child for child in widgets(notice) if isinstance(child, tk.Text))
                    self.assertTrue(notice.winfo_viewable())
                    self.assertIn("FCT monitoring source preparation failed", body.get("1.0", "end"))
                    self.assertIn("source access denied", body.get("1.0", "end"))
                    round_id = app.rounds.snapshot().round_id
                    app.language_menu.invoke(1)
                    root.update_idletasks()
                    self.assertEqual(notice.title(), "啟動失敗")
                    self.assertIn("FCT 監控來源準備失敗", body.get("1.0", "end"))
                    self.assertIn("source access denied", body.get("1.0", "end"))
                    self.assertEqual(app.rounds.snapshot().round_id, round_id)
                    shown.append(notice)
                    next(child for child in widgets(notice) if isinstance(child, ttk.Button)).invoke()
                except Exception as error:
                    errors.append(error)
                    for child in root.winfo_children():
                        if isinstance(child, tk.Toplevel):
                            child.destroy()

            try:
                root.after(350, inspect)
                with patch("b518_log_solution.DEFAULT_PLATFORM_REGISTRY.create_monitor",
                           side_effect=PermissionError("source access denied")), \
                        patch("tkinter.messagebox.showerror") as legacy_modal:
                    app.start_button.invoke()
                    self.pump(root, lambda: errors or shown)
                    legacy_modal.assert_not_called()
                self.assertEqual(errors, [])
                self.assertEqual(len(shown), 1)
                round_id = app.rounds.snapshot().round_id
                app.close()
                self.pump(root, lambda: app.rounds.close_status().status == "complete")
                audit = read_round_audit(base / "sessions" / round_id / "audit.jsonl")
                failures = [item for item in audit["events"] if item["kind"] == "start_failed"]
                self.assertEqual(len(failures), 1)
                localized = failures[0]["localized_message"]
                self.assertEqual(localized["en"], "FCT monitoring source preparation failed")
                self.assertEqual(localized["zh-TW"], "FCT 監控來源準備失敗")
                self.assertEqual(localized["diagnostic"], "source access denied")
            finally:
                app.hotkey.close()
                app.app_events.stop()
                try:
                    root.destroy()
                except tk.TclError:
                    pass

    def test_visible_start_validation_notice_refreshes_without_accepting_a_round(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.APP_ROOT", Path(temporary)), \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            app = B518LogSolutionApp(root, hotkey_factory=LocalHotkey,
                                     session_root=Path(temporary) / "sessions")
            root.update()
            observations, errors = [], []

            def inspect_and_acknowledge():
                try:
                    notice = next(child for child in root.winfo_children()
                                  if isinstance(child, tk.Toplevel) and
                                  child.title() == "Configuration Error")
                    body = next(child for child in widgets(notice) if isinstance(child, tk.Text))
                    self.assertTrue(notice.winfo_viewable())
                    self.assertIs(root.grab_current(), notice)
                    self.assertIn("The selected configuration is invalid", body.get("1.0", "end"))
                    self.assertIn("Original diagnostic:", body.get("1.0", "end"))
                    self.assertIn("See the original diagnostic below", body.get("1.0", "end"))
                    app.language_menu.invoke(1)
                    root.update_idletasks()
                    self.assertEqual(notice.title(), "配置錯誤")
                    self.assertIn("所選配置無效", body.get("1.0", "end"))
                    self.assertIsNone(app.rounds.snapshot())
                    button = next(child for child in widgets(notice) if isinstance(child, ttk.Button))
                    self.assertEqual(button.cget("text"), "確定")
                    observations.append(notice)
                    button.invoke()
                except Exception as error:
                    errors.append(error)
                    for child in root.winfo_children():
                        if isinstance(child, tk.Toplevel):
                            child.destroy()

            try:
                root.after(50, inspect_and_acknowledge)
                # Suppress only the legacy OS modal on the red version. The green
                # implementation must display real Tk and never call this boundary.
                with patch("tkinter.messagebox.showerror") as legacy_modal:
                    app.start_button.invoke()
                    self.pump(root, lambda: observations or errors)
                    legacy_modal.assert_not_called()
                self.assertEqual(errors, [])
                self.assertEqual(len(observations), 1)
                self.assertIsNone(app.rounds.snapshot())
                app.close()
                self.pump(root, lambda: app.rounds.close_status().status == "complete")
                saved = read_app_event_store(Path(temporary) / "app-events.json")["events"]
                validation = [item for item in saved if
                              item["localized_message"]["message_id"] == "app.profile.validation_failed"]
                self.assertEqual(len(validation), 1)
                self.assertTrue(validation[0]["localized_message"]["en"])
                self.assertTrue(validation[0]["localized_message"]["zh-TW"])
            finally:
                app.hotkey.close()
                app.app_events.stop()
                try:
                    root.destroy()
                except tk.TclError:
                    pass
