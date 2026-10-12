"""Source-App acceptance at the real Tk, shared-round and disk boundaries."""
import os
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
    def pump(self, root, predicate, timeout=5):
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
