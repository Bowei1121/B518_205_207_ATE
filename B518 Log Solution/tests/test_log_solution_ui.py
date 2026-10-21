import csv
import gc
import hashlib
import io
import json
import os
import sqlite3
import shutil
import subprocess
import sys
import textwrap
import traceback
import tkinter as tk
import time
import threading
import unittest
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from tkinter import font as tkfont, ttk
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

try:
    import Quartz
    from AppKit import (NSApplication, NSApplicationActivateIgnoringOtherApps,
                        NSRunningApplication, NSApplicationActivationPolicyRegular)
except ImportError:  # macOS desktop-only acceptance helper
    Quartz = None
    NSApplicationActivateIgnoringOtherApps = None
    NSRunningApplication = None
    NSApplication = None
    NSApplicationActivationPolicyRegular = None

from b518_log_solution import (
    APP_VERSION, B518LogSolutionApp, _LocalizedControlHint, FIELD_BACKGROUND, LIGHT_BACKGROUND,
    format_monitoring_elapsed,
    KVM_BAND_HEIGHT, MAIN_FONT_SIZE, MARKER_SIZE, ROW_HEIGHT, STATUS_COLOURS,
    STATUS_TEMPLATE_STATES, UNAVAILABLE_COLOUR, WINDOW_WIDTH, KVM_BLOCK_COUNT, kvm_block_colour,
    sn_font_size, visible_detail_rows, window_height,
)
from global_hotkey import COMMAND_SHIFT_M_KEYCODE, COMMAND_SHIFT_MODIFIERS, GlobalHotkeyError, UnavailableHotkey, create_global_hotkey
from log_monitoring import MonitorEvent
from log_monitoring import BaseMonitor, SessionStore, SlotResult
from monitoring_round import (
    ConflictSide, RoundConflict, RoundCoordinator, RoundEvent, RoundSnapshot, RoundState,
)
from kvm_display_contract import HEARTBEAT_INTERVAL_MS, HEARTBEAT_PATTERNS, MarkerState
import audit_records
import app_event_store
import historical_event_query
import monitoring_round
import round_retention
from audit_records import read_round_audit
from app_event_store import AppEventStore, read_app_event_store
from historical_event_query import (HistoricalEventDateRange, HistoricalEventQueryResult,
                                    query_historical_events,
                                    recent_historical_event_date_range)
from machine_profiles import MachineProfile, MachineProfileStore, ProfileCatalog, migrate_legacy_preferences
from language_catalog import DEFAULT_LANGUAGE, ENGLISH, TRADITIONAL_CHINESE, language_name


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


def native_window_for_capture(window):
    """Resolve this Tk window even when AppKit retains older same-title windows."""
    from AppKit import NSApplication

    title = window.title()
    token = "{} [capture-{}]".format(title, window.winfo_id())
    try:
        window.title(token)
        window.update_idletasks()
        matches = [item for item in NSApplication.sharedApplication().windows()
                   if item.title() == token and item.isVisible()]
        if len(matches) != 1:
            raise AssertionError("expected one native window for {}: {}".format(
                window, len(matches)))
        return matches[0]
    finally:
        # The rendered capture and returned metadata retain the real App title.
        window.title(title)
        window.update_idletasks()


def capture_tk_window_image(window, native_window):
    """Manual assets may use the live NSView cache without screen recording.

    The default remains WindowServer capture for desktop acceptance. View-cache
    images document app content, not occlusion, native menus or keyboard focus.
    """
    if os.environ.get("B518_TK_CAPTURE_METHOD") == "view-cache":
        from AppKit import NSApplication
        # Aqua needs several frames after a tab/language switch before its
        # contentView cache contains the newly mapped controls.
        def expose(widget):
            if widget.winfo_viewable():
                widget.event_generate("<Expose>")
                for child in widget.winfo_children():
                    expose(child)
        expose(window)
        deadline = time.monotonic() + .25
        while time.monotonic() < deadline:
            window.update()
            time.sleep(.01)
        native = native_window_for_capture(window)
        view = native.contentView()
        rect = view.bounds()
        bitmap = view.bitmapImageRepForCachingDisplayInRect_(rect)
        view.cacheDisplayInRect_toBitmapImageRep_(rect, bitmap)
        return bitmap.CGImage()
    return Quartz.CGWindowListCreateImage(
        Quartz.CGRectNull, Quartz.kCGWindowListOptionIncludingWindow,
        native_window[Quartz.kCGWindowNumber],
        Quartz.kCGWindowImageBoundsIgnoreFraming)


def capture_tk_window_evidence(window, key, language, widgets):
    window.update_idletasks()
    window.lift()
    window.update_idletasks()

    def relative_bounds(widget):
        x = y = 0
        current = widget
        while current is not window:
            x += current.winfo_x()
            y += current.winfo_y()
            current = current.master
        return [x, y, widget.winfo_width(), widget.winfo_height()]

    record = {
        "title": window.title(),
        "geometry": window.geometry(),
        "size": [window.winfo_width(), window.winfo_height()],
        "controls": {
            name: relative_bounds(widget)
            for name, widget in widgets.items()
        },
    }
    evidence_value = os.environ.get("B518_TK_EVIDENCE_DIR")
    if not evidence_value:
        return record

    import Quartz
    from Foundation import NSURL

    native_windows = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID)
    native_number = native_window_for_capture(window).windowNumber()
    native_window = next((item for item in native_windows
                          if item.get(Quartz.kCGWindowOwnerPID) == os.getpid()
                          and item.get(Quartz.kCGWindowNumber) == native_number), None)
    if native_window is None:
        raise AssertionError("missing native window: {}".format(key))
    image = capture_tk_window_image(window, native_window)
    if image is None:
        raise AssertionError("could not capture native window: {}".format(key))
    output_dir = Path(evidence_value)
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = "{}-{}.png".format(key, language)
    output = output_dir / filename
    destination = Quartz.CGImageDestinationCreateWithURL(
        NSURL.fileURLWithPath_(str(output)), "public.png", 1, None)
    Quartz.CGImageDestinationAddImage(destination, image, None)
    if not Quartz.CGImageDestinationFinalize(destination):
        raise AssertionError("could not write screenshot: {}".format(output))
    native_bounds = native_window[Quartz.kCGWindowBounds]
    record.update({
        "native_bounds": {name: float(native_bounds[name])
                          for name in ("X", "Y", "Width", "Height")},
        "image_pixels": {"width": Quartz.CGImageGetWidth(image),
                         "height": Quartz.CGImageGetHeight(image)},
        "screenshot": filename,
        "capture_method": os.environ.get("B518_TK_CAPTURE_METHOD", "window-server"),
    })
    return record


def capture_tk_content_view_evidence(window, key, widgets, output_dir=None):
    """Capture the mapped Tk window's live NSView cache, not a synthetic redraw."""
    from AppKit import NSApplication, NSBitmapImageFileTypePNG

    window.update_idletasks()
    window.lift()
    window.update()
    native_window = native_window_for_capture(window)
    content_view = native_window.contentView()
    deadline = time.monotonic() + 5
    while True:
        window.update()
        content_rect = content_view.bounds()
        native_size = (round(content_rect.size.width), round(content_rect.size.height))
        tk_size = (window.winfo_width(), window.winfo_height())
        if native_size == tk_size:
            break
        if time.monotonic() >= deadline:
            raise AssertionError("Aqua contentView did not settle: native={}, Tk={}".format(
                native_size, tk_size))
        time.sleep(.01)
    bitmap = content_view.bitmapImageRepForCachingDisplayInRect_(content_rect)
    content_view.cacheDisplayInRect_toBitmapImageRep_(content_rect, bitmap)
    png_data = bitmap.representationUsingType_properties_(NSBitmapImageFileTypePNG, {})
    output_dir = Path(output_dir or os.environ["B518_TK_EVIDENCE_DIR"])
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = key + "-view-cache.png"
    output_path = output_dir / filename
    if not png_data.writeToFile_atomically_(str(output_path), True):
        raise AssertionError("could not save Tk NSView cache: {}".format(output_path))

    import Quartz
    windows = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionAll,
                                                Quartz.kCGNullWindowID)
    screen_window = next((item for item in windows
                          if item.get(Quartz.kCGWindowOwnerPID) == os.getpid()
                          and item.get(Quartz.kCGWindowLayer) == 0
                          and item.get(Quartz.kCGWindowNumber) == native_window.windowNumber()
                          and item.get(Quartz.kCGWindowIsOnscreen) == 1), None)
    if screen_window is None:
        raise AssertionError("Tk window has no on-screen Quartz bounds")

    def relative_bounds(widget):
        x = y = 0
        current = widget
        while current is not window:
            x += current.winfo_x()
            y += current.winfo_y()
            current = current.master
        return [x, y, widget.winfo_width(), widget.winfo_height()]

    return {
        "title": window.title(),
        "geometry": window.geometry(),
        "size": [window.winfo_width(), window.winfo_height()],
        "controls": {name: relative_bounds(widget) for name, widget in widgets.items()},
        "native_bounds": {name: float(screen_window[Quartz.kCGWindowBounds][name])
                          for name in ("X", "Y", "Width", "Height")},
        "image_pixels": {"width": bitmap.pixelsWide(), "height": bitmap.pixelsHigh()},
        "screenshot": filename,
        "capture_method": "NSView bitmap cache of the live Tk contentView",
    }


def capture_native_window_with_hint(window, filename):
    """Capture the real App window and its on-screen tooltip in one native frame."""
    evidence_value = os.environ.get("B518_TK_EVIDENCE_DIR")
    if not evidence_value:
        return None
    import Quartz
    from Foundation import NSURL

    window.lift()
    for child in window.winfo_children():
        if isinstance(child, tk.Toplevel) and child.overrideredirect():
            child.lift()
    window.update()
    native_windows = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID)
    native_number = native_window_for_capture(window).windowNumber()
    native_window = next((item for item in native_windows
                          if item.get(Quartz.kCGWindowOwnerPID) == os.getpid()
                          and item.get(Quartz.kCGWindowNumber) == native_number), None)
    if native_window is None:
        raise AssertionError("missing native window: {}".format(window.title()))
    bounds = native_window[Quartz.kCGWindowBounds]
    rect = Quartz.CGRectMake(bounds["X"], bounds["Y"],
                             bounds["Width"], bounds["Height"])
    image = Quartz.CGWindowListCreateImage(
        rect, Quartz.kCGWindowListOptionOnScreenOnly,
        Quartz.kCGNullWindowID, Quartz.kCGWindowImageDefault)
    if image is None:
        raise AssertionError("could not capture native window with hint")
    output_dir = Path(evidence_value)
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / filename
    destination = Quartz.CGImageDestinationCreateWithURL(
        NSURL.fileURLWithPath_(str(output)), "public.png", 1, None)
    Quartz.CGImageDestinationAddImage(destination, image, None)
    if not Quartz.CGImageDestinationFinalize(destination):
        raise AssertionError("could not write screenshot: {}".format(output))
    return {"screenshot": filename,
            "native_bounds": {name: float(bounds[name])
                              for name in ("X", "Y", "Width", "Height")},
            "image_pixels": {"width": Quartz.CGImageGetWidth(image),
                             "height": Quartz.CGImageGetHeight(image)}}


def capture_recovery_evidence(app, key, language, widgets):
    # Language changes and tab selection can leave an Aqua Toplevel's native
    # backing surface stale for a frame. Raise the actual app window and let
    # Tk/Aqua render several frames before asking WindowServer for a capture.
    if os.environ.get("B518_TK_EVIDENCE_DIR"):
        if NSRunningApplication is not None:
            NSRunningApplication.currentApplication().activateWithOptions_(
                NSApplicationActivateIgnoringOtherApps)
        app.recovery_window.deiconify()
        app.recovery_window.lift()
        app.recovery_window.focus_force()
    deadline = time.monotonic() + (.8 if os.environ.get("B518_TK_EVIDENCE_DIR") else .16)
    while time.monotonic() < deadline:
        app.root.update()
        time.sleep(.01)
    assert app.recovery_window.winfo_viewable()
    assert app.recovery_tabs.nametowidget(
        app.recovery_tabs.select()).winfo_viewable()
    for control in widgets.values():
        assert control.winfo_rootx() >= app.recovery_window.winfo_rootx()
        assert control.winfo_rootx() + control.winfo_width() <= (
            app.recovery_window.winfo_rootx() + app.recovery_window.winfo_width())
        assert control.winfo_rooty() + control.winfo_height() <= (
            app.recovery_window.winfo_rooty() + app.recovery_window.winfo_height())
    record = capture_tk_window_evidence(app.recovery_window, key, language, widgets)
    if os.environ.get("B518_TK_EVIDENCE_DIR"):
        output = Path(os.environ["B518_TK_EVIDENCE_DIR"]) / "hf2-window-bounds.json"
        records = json.loads(output.read_text()) if output.exists() else {}
        records[key + "-" + language] = record
        output.write_text(json.dumps(records, ensure_ascii=False, indent=2))
    return record


def capture_main_badge_evidence(app, key, language, widgets):
    root = app.root
    root.deiconify()
    root.lift()
    root.focus_force()
    deadline = time.monotonic() + .18
    while time.monotonic() < deadline:
        root.update()
        time.sleep(.01)
    if not root.winfo_ismapped():
        raise AssertionError("main App window is not mapped for badge evidence")
    record = capture_tk_window_evidence(root, key, language, widgets)
    if os.environ.get("B518_TK_EVIDENCE_DIR"):
        write_tk_bounds_evidence(key + "-" + language, record)
    return record


def write_tk_bounds_evidence(key, value):
    evidence_value = os.environ.get("B518_TK_EVIDENCE_DIR")
    if not evidence_value:
        return
    output = Path(evidence_value) / "window-bounds.json"
    current = json.loads(output.read_text(encoding="utf-8")) if output.exists() else {}
    current[key] = value
    output.write_text(json.dumps(current, ensure_ascii=False, indent=2),
                      encoding="utf-8")


class LogSolutionUiTests(unittest.TestCase):
    def test_monitoring_elapsed_format_keeps_full_minutes(self):
        cases = ((None, "00:00"), (59.9, "00:59"), (60, "01:00"),
                 (901, "15:01"), (36000, "600:00"))
        for elapsed, expected in cases:
            with self.subTest(elapsed=elapsed):
                self.assertEqual(format_monitoring_elapsed(elapsed), expected)

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_real_tk_round_timer_stays_fixed_through_language_and_long_minutes(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.deiconify()
            session_root = Path(temporary) / "sessions"
            active = Path(temporary) / "active"
            final = Path(temporary) / "final"
            active.mkdir()
            final.mkdir()
            app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey,
                                     session_root=session_root)
            elapsed = [500.0]
            rounds = RoundCoordinator(app.events.put, monotonic=lambda: elapsed[0],
                                      audit_root=session_root)

            try:
                app.rounds = rounds
                rounds.register_app_event_store(app.app_events, session_root.parent)
                self.wait_for_ui(root, lambda: app.monitor_elapsed.cget("text") == "00:00")
                self.assertLess(app.monitor_state.winfo_rootx(),
                                app.monitor_elapsed.winfo_rootx())

                app.open_settings()
                app.profile_editor_machine.set("FCT")
                app.profile_editor_paths["active"].set(str(active))
                app.profile_editor_paths["final"].set(str(final))
                app._apply_profile_editor()
                app._close_settings()
                app.start_button.invoke()
                started = rounds.snapshot()
                self.assertIsNotNone(started)
                self.assertEqual(app.active_round_id, started.round_id)
                self.assertEqual(app.monitor_elapsed.cget("text"), "00:00")
                self.wait_for_ui(root, lambda: not rounds.snapshot().source_preparation_pending)

                elapsed[0] = 1401.0
                app._apply_round_snapshot(rounds.snapshot())
                self.assertEqual(app.monitor_elapsed.cget("text"), "15:01")
                app._select_language(ENGLISH)
                root.update_idletasks()
                right_edge = (app.monitor_elapsed.winfo_rootx() +
                              app.monitor_elapsed.winfo_width())

                app._select_language(TRADITIONAL_CHINESE)
                root.update_idletasks()
                self.assertEqual(app.monitor_elapsed.cget("text"), "15:01")
                self.assertEqual(app.monitor_elapsed.winfo_rootx() +
                                 app.monitor_elapsed.winfo_width(), right_edge)

                elapsed[0] = 36500.0
                app._apply_round_snapshot(rounds.snapshot())
                root.update_idletasks()
                self.assertEqual(app.monitor_elapsed.cget("text"), "600:00")
                self.assertGreaterEqual(app.monitor_elapsed.winfo_width(),
                                        app.monitor_elapsed.winfo_reqwidth(),
                                        (app.monitor_elapsed.winfo_width(),
                                         app.monitor_elapsed.winfo_reqwidth(),
                                         app._main_controls.winfo_width(),
                                         app.monitor_elapsed.winfo_width(),
                                         app.monitor_state.winfo_width()))
                self.assertEqual(app.monitor_elapsed.winfo_rootx() +
                                 app.monitor_elapsed.winfo_width(), right_edge)

                stopped = rounds.stop()
                self.assertEqual(stopped.monitoring_elapsed_seconds, 36000.0)
                elapsed[0] = 50000.0
                app._apply_round_snapshot(rounds.snapshot())
                self.assertEqual(app.monitor_elapsed.cget("text"), "600:00")
            finally:
                rounds.stop()
                rounds.flush_audit(timeout=3)
                app.hotkey.close()
                root.destroy()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_real_tk_abort_paths_keep_accepted_round_time_frozen(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.deiconify()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey,
                session_root=Path(temporary) / "sessions",
                app_event_path=Path(temporary) / "app-events.json",
            )
            elapsed = [700.0]
            rounds = RoundCoordinator(app.events.put, monotonic=lambda: elapsed[0],
                                      audit_root=Path(temporary) / "sessions")

            try:
                app.rounds = rounds
                rounds.register_app_event_store(app.app_events, Path(temporary))
                app._show_notice = lambda *_args, **_kwargs: None

                def fail_source(_callback):
                    elapsed[0] = 707.5
                    raise PermissionError("source permission denied")

                started = rounds.start("FCT", fail_source, run_async=False)
                app.active_round_id = started.round_id
                app._apply_round_snapshot(started)
                self.assertEqual(started.completion_reason, "start_failed")
                self.assertEqual(app.monitor_elapsed.cget("text"), "00:07")

                elapsed[0] = 1200.0
                app._apply_round_snapshot(rounds.snapshot())
                self.assertEqual(rounds.snapshot().monitoring_elapsed_seconds, 7.5)
                self.assertEqual(app.monitor_elapsed.cget("text"), "00:07")
                self.assertTrue(rounds.reset_start_failure("source access repaired"))
                self.assertEqual(rounds.round_snapshot(started.round_id).monitoring_elapsed_seconds, 7.5)

                class TimerMonitor:
                    def __init__(self, callback, start_timeout=5, round_timeout=20):
                        self.callback = callback
                        self.results = {1: SlotResult(1)}
                        self.start_timeout = start_timeout
                        self.round_timeout = round_timeout

                    def update_round_settings(self, _settings):
                        return

                    def publish_round_event(self, event):
                        self.callback(event)

                    def start(self):
                        return

                    def timeout_seconds(self, kind):
                        return {"start": self.start_timeout, "test": 60,
                                "round": self.round_timeout}[kind]

                    def round_results(self):
                        return tuple(self.results.values())

                    def apply_round_result(self, slot, status, *args, **_kwargs):
                        self.results[slot].status = status
                        self.callback(MonitorEvent("result", "slot{} {}".format(slot, status),
                                                   slot, status=status))

                    def stop_collection(self):
                        return

                    def has_pending_review(self):
                        return False

                    def resolve_review(self, _choice):
                        return

                    def poll_once(self):
                        return

                    def stop(self):
                        return

                    def finish(self):
                        return

                deadline_round = rounds.start(
                    "FCT", lambda callback: TimerMonitor(callback), run_async=False,
                    start_timeout_seconds=5, round_timeout_seconds=20, capacity=1,
                )
                app.active_round_id = deadline_round.round_id
                app._apply_round_snapshot(deadline_round)
                elapsed[0] = 1205.0
                expired = rounds.poll_once()
                app._apply_round_snapshot(expired)
                self.assertEqual(expired.completion_reason, "start_deadline_no_activity")
                self.assertEqual(app.monitor_elapsed.cget("text"), "00:05")

                elapsed[0] = 1500.0
                app.stop_button.invoke()
                stopped_again = rounds.snapshot()
                app._apply_round_snapshot(stopped_again)
                self.assertEqual(stopped_again.completion_reason, "start_deadline_no_activity")
                self.assertEqual(app.monitor_elapsed.cget("text"), "00:05")
                acknowledged = rounds.acknowledge_round_alarm(
                    deadline_round.round_id, expired.round_alarm.alarm_id)
                self.assertTrue(acknowledged.cancellation_available)
                app._apply_round_snapshot(acknowledged)
                with patch("b518_log_solution.messagebox.askyesno", return_value=True):
                    app.cancel_unverified_round()
                self.assertEqual(rounds.snapshot().completion_reason, "unverified_round_cancelled")
                self.assertEqual(rounds.snapshot().monitoring_elapsed_seconds, 5.0)
                self.assertEqual(app.monitor_elapsed.cget("text"), "00:05")

                round_timeout = rounds.start(
                    "FCT", lambda callback: TimerMonitor(callback, start_timeout=100,
                                                         round_timeout=5),
                    run_async=False, capacity=1,
                )
                app.active_round_id = round_timeout.round_id
                app._apply_round_snapshot(round_timeout)
                elapsed[0] = 1505.0
                expired_round = rounds.poll_once()
                app._apply_round_snapshot(expired_round)
                self.assertEqual(expired_round.completion_reason, "round_deadline")
                self.assertEqual(app.monitor_elapsed.cget("text"), "00:05")

                elapsed[0] = 1800.0
                app.stop_button.invoke()
                stopped_round = rounds.snapshot()
                app._apply_round_snapshot(stopped_round)
                self.assertEqual(stopped_round.completion_reason, "round_deadline")
                self.assertEqual(stopped_round.monitoring_elapsed_seconds, 5.0)
                self.assertEqual(app.monitor_elapsed.cget("text"), "00:05")
                rounds.acknowledge_round_alarm(
                    round_timeout.round_id, expired_round.round_alarm.alarm_id)
            finally:
                rounds.flush_audit(timeout=3)
                rounds.request_close()
                deadline = time.monotonic() + 5
                while rounds.close_status().status != "complete" and time.monotonic() < deadline:
                    root.update()
                    time.sleep(0.01)
                self.assertEqual(rounds.close_status().status, "complete")
                app.hotkey.close()
                root.destroy()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_li7_locator_is_visible_at_first_cell_with_fixed_other_geometry(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.deiconify()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey,
                session_root=Path(temporary) / "sessions",
                app_event_path=Path(temporary) / "app-events.json",
            )
            try:
                self.wait_for_ui(root, lambda: root.winfo_ismapped() and
                                 app.kvm_locator_left.winfo_height() == 22)
                self.assertFalse(hasattr(app, "kvm_result_title"))
                self.assertEqual(
                    (app.kvm_locator_left.winfo_x(), app.kvm_locator_left.winfo_y(),
                     app.kvm_locator_left.winfo_width(), app.kvm_locator_left.winfo_height()),
                    (0, 2, 22, 22),
                )
                self.assertEqual(
                    (app.kvm_result_blocks[1].winfo_x(),
                     app.kvm_result_blocks[1].winfo_y(),
                     app.kvm_result_blocks[1].winfo_width(),
                     app.kvm_result_blocks[1].winfo_height()),
                    (0, 34, 34, 26),
                )
                self.assertEqual(
                    (app.kvm_locator_right.winfo_x(), app.kvm_locator_right.winfo_y(),
                     app.kvm_locator_right.winfo_width(), app.kvm_locator_right.winfo_height()),
                    (320, 2, 22, 22),
                )
                self.assertEqual(
                    (app.kvm_layout_marker.winfo_x(), app.kvm_layout_marker.winfo_y(),
                     app.kvm_layout_marker.winfo_width(), app.kvm_layout_marker.winfo_height()),
                    (130, 2, 26, 14),
                )
                self.assertEqual(
                    (app.kvm_state_marker.winfo_x(), app.kvm_state_marker.winfo_y(),
                     app.kvm_state_marker.winfo_width(), app.kvm_state_marker.winfo_height()),
                    (250, 0, 26, 26),
                )
                self.assertEqual(app.kvm_locator_left.winfo_rootx(),
                                 app.kvm_results.winfo_rootx())
                self.assertEqual(app.kvm_locator_left.winfo_rootx(),
                                 app.kvm_result_blocks[1].winfo_rootx())
                self.assertGreaterEqual(
                    app.kvm_locator_left.winfo_rootx() - root.winfo_rootx(), 2,
                    "the App's white parent area must leave two visible Tk units before the locator",
                )
                self.assertEqual(
                    (app.kvm_locator_left.white_cell.winfo_x(),
                     app.kvm_locator_left.white_cell.winfo_y(),
                     app.kvm_locator_left.white_cell.winfo_width(),
                     app.kvm_locator_left.white_cell.winfo_height()),
                    (3, 3, 8, 8),
                )
                self.assertEqual(
                    (app.kvm_locator_right.white_cell.winfo_x(),
                     app.kvm_locator_right.white_cell.winfo_y()), (11, 11),
                )
                self.assertEqual(app.kvm_locator_left.winfo_width(),
                                 app.kvm_locator_right.winfo_width())
                self.assertEqual(app.kvm_locator_left.winfo_y(),
                                 app.kvm_locator_right.winfo_y())
            finally:
                app.hotkey.close()
                app.rounds.request_close()
                self.wait_for_ui(root, lambda: app.rounds.close_status().status == "complete")
                self.wait_for_ui(root, lambda: app.rounds.app_event_status().complete)
                root.destroy()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_li7_geometry_at_both_scalings_and_all_capacities(self):
        # Scaling belongs to the shared interpreter, not to this Toplevel.
        scaling_before = float(self._desktop_root.tk.call("tk", "scaling"))

        def restore_scaling():
            self._desktop_root.tk.call("tk", "scaling", scaling_before)
            self.assertAlmostEqual(float(self._desktop_root.tk.call("tk", "scaling")),
                                   scaling_before, places=6)

        self.addCleanup(restore_scaling)
        evidence_dir = Path(os.environ.get("B518_TK_EVIDENCE_DIR") or
                            str(Path(self._isolated_app_root.name) / "li7-evidence"))
        evidence_dir.mkdir(parents=True, exist_ok=True)
        matrix = []
        timer_samples = []
        scaling_filter = os.environ.get("B518_LI7_SCALING")
        scalings = (float(scaling_filter),) if scaling_filter else (1.0, 1.5)
        for scaling in scalings:
            with TemporaryDirectory() as temporary, \
                    patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
                root = tk.Tk()
                root.tk.call("tk", "scaling", scaling)
                root.deiconify()
                app = B518LogSolutionApp(
                    root, hotkey_factory=FakeHotkey,
                    session_root=Path(temporary) / "sessions",
                    app_event_path=Path(temporary) / "app-events.json",
                )
                try:
                    self.wait_for_ui(root, lambda: root.winfo_ismapped() and
                                     app.kvm_locator_left.winfo_height() == 22)
                    original_band = (app.kvm_results.winfo_rootx(),
                                     app.kvm_results.winfo_rooty())
                    original_fixed = {
                        "right_locator": (app.kvm_locator_right.winfo_x(),
                                          app.kvm_locator_right.winfo_y(),
                                          app.kvm_locator_right.winfo_width(),
                                          app.kvm_locator_right.winfo_height()),
                        "layout_marker": (app.kvm_layout_marker.winfo_x(),
                                          app.kvm_layout_marker.winfo_y(),
                                          app.kvm_layout_marker.winfo_width(),
                                          app.kvm_layout_marker.winfo_height()),
                        "state_marker": (app.kvm_state_marker.winfo_x(),
                                          app.kvm_state_marker.winfo_y(),
                                          app.kvm_state_marker.winfo_width(),
                                          app.kvm_state_marker.winfo_height()),
                        "first_cell": (app.kvm_result_blocks[1].winfo_x(),
                                       app.kvm_result_blocks[1].winfo_y(),
                                       app.kvm_result_blocks[1].winfo_width(),
                                       app.kvm_result_blocks[1].winfo_height()),
                    }

                    def descendants(widget):
                        for child in widget.winfo_children():
                            yield child
                            yield from descendants(child)

                    def edit_visible_profile_capacity(capacity):
                        app.open_settings()
                        root.update()
                        editor_widgets = list(descendants(app.settings_window))

                        def entry_for(variable):
                            variable_name = str(variable)
                            return next(widget for widget in editor_widgets
                                        if widget.winfo_class() in {"TEntry", "Entry"}
                                        and widget.cget("textvariable") == variable_name)

                        capacity_entry = entry_for(app.profile_editor_capacity)
                        capacity_entry.delete(0, tk.END)
                        capacity_entry.insert(0, str(capacity))
                        mapping_entry = entry_for(app.profile_editor_mapping)
                        mapping_entry.delete(0, tk.END)
                        mapping_entry.insert(
                            0, ", ".join("{}:{}".format(slot, slot)
                                         for slot in range(1, capacity + 1)))
                        apply_button = next(
                            widget for widget in editor_widgets
                            if widget.winfo_class() == "TButton"
                            and widget.cget("text") == app._t("app.settings.profile.apply"))
                        apply_button.invoke()
                        root.update()
                        self.assertEqual(app.profile_editor_status.get(),
                                         app._t("app.settings.profile.status.saved"))
                        self.assertEqual(app._selected_profile().capacity, capacity)
                        persisted, selected_project, selected_machine, error = (
                            MachineProfileStore(Path(temporary) / "preferences.json").load())
                        self.assertIsNone(error)
                        self.assertEqual(persisted.get(selected_project, selected_machine).capacity,
                                         capacity)
                        app._close_settings()
                        root.update()

                    for capacity in (1, 10, 11, 20):
                        edit_visible_profile_capacity(capacity)
                        root.update()
                        left = app.kvm_locator_left
                        right = app.kvm_locator_right
                        parent = app.kvm_results
                        self.assertEqual(app._display_capacity(), capacity)
                        self.assertEqual((left.winfo_x(), left.winfo_y(),
                                          left.winfo_width(), left.winfo_height()),
                                         (0, 2, 22, 22))
                        self.assertEqual((left.winfo_rootx(), left.winfo_rooty()),
                                         (app.kvm_result_blocks[1].winfo_rootx(),
                                          parent.winfo_rooty() + 2))
                        self.assertGreaterEqual(left.winfo_rootx() - root.winfo_rootx(), 2)
                        self.assertEqual((right.winfo_x(), right.winfo_y(),
                                          right.winfo_width(), right.winfo_height()),
                                         original_fixed["right_locator"])
                        self.assertEqual((app.kvm_layout_marker.winfo_x(),
                                          app.kvm_layout_marker.winfo_y(),
                                          app.kvm_layout_marker.winfo_width(),
                                          app.kvm_layout_marker.winfo_height()),
                                         original_fixed["layout_marker"])
                        self.assertEqual((app.kvm_state_marker.winfo_x(),
                                          app.kvm_state_marker.winfo_y(),
                                          app.kvm_state_marker.winfo_width(),
                                          app.kvm_state_marker.winfo_height()),
                                         original_fixed["state_marker"])
                        self.assertEqual((app.kvm_result_blocks[1].winfo_x(),
                                          app.kvm_result_blocks[1].winfo_y(),
                                          app.kvm_result_blocks[1].winfo_width(),
                                          app.kvm_result_blocks[1].winfo_height()),
                                         original_fixed["first_cell"])
                        self.assertEqual((parent.winfo_rootx(), parent.winfo_rooty()),
                                         original_band)
                        expected_parent_height = KVM_BAND_HEIGHT if capacity > 10 else 61
                        self.assertEqual(parent.winfo_height(), expected_parent_height)
                        for slot, block in app.kvm_result_blocks.items():
                            if slot > 10 and capacity <= 10:
                                self.assertFalse(block.winfo_ismapped())
                            else:
                                self.assertTrue(block.winfo_ismapped())
                                self.assertEqual(
                                    block.cget("background"),
                                    UNAVAILABLE_COLOUR if slot > capacity else
                                    STATUS_COLOURS["WAITING"],
                                )
                        scale_readback = float(root.tk.call("tk", "scaling"))
                        self.assertAlmostEqual(scale_readback, scaling, places=2)
                        for language_index, language in ((0, ENGLISH),
                                                         (1, TRADITIONAL_CHINESE)):
                            app.language_menu.invoke(language_index)
                            root.update()
                            self.assertEqual(app.current_language, language)
                            self.assertEqual((app.kvm_locator_left.winfo_x(),
                                              app.kvm_locator_left.winfo_y(),
                                              app.kvm_locator_left.winfo_width(),
                                              app.kvm_locator_left.winfo_height()),
                                             (0, 2, 22, 22))
                            self.assertEqual((app.kvm_locator_right.winfo_x(),
                                              app.kvm_locator_right.winfo_y(),
                                              app.kvm_locator_right.winfo_width(),
                                              app.kvm_locator_right.winfo_height()),
                                             original_fixed["right_locator"])
                            self.assertEqual((app.kvm_layout_marker.winfo_x(),
                                              app.kvm_layout_marker.winfo_y(),
                                              app.kvm_layout_marker.winfo_width(),
                                              app.kvm_layout_marker.winfo_height()),
                                             original_fixed["layout_marker"])
                            self.assertEqual((app.kvm_state_marker.winfo_x(),
                                              app.kvm_state_marker.winfo_y(),
                                              app.kvm_state_marker.winfo_width(),
                                              app.kvm_state_marker.winfo_height()),
                                             original_fixed["state_marker"])
                            self.assertEqual(app._display_capacity(), capacity)
                            self.assertEqual(parent.winfo_height(), expected_parent_height)
                            language_key = "en" if language == ENGLISH else "zh-TW"
                            key = "li7-s{}-capacity-{}-{}".format(
                                str(scaling).replace(".", "p"), capacity, language_key)
                            if NSApplication is not None:
                                NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
                            root.lift()
                            root.update()
                            evidence = capture_tk_content_view_evidence(root, key, {
                                "kvm": parent,
                                "monitor_state": app.monitor_state,
                                "monitor_elapsed": app.monitor_elapsed,
                                "left_locator": app.kvm_locator_left,
                                "left_white_cell": app.kvm_locator_left.white_cell,
                                "right_locator": app.kvm_locator_right,
                                "right_white_cell": app.kvm_locator_right.white_cell,
                                "layout_marker": app.kvm_layout_marker,
                                "state_marker": app.kvm_state_marker,
                                "first_cell": app.kvm_result_blocks[1],
                                "last_configured_cell": app.kvm_result_blocks[capacity],
                                "last_cell": app.kvm_result_blocks[20],
                            }, output_dir=evidence_dir)
                            physical_per_native_unit = (
                                evidence["image_pixels"]["width"] / evidence["size"][0],
                                evidence["image_pixels"]["height"] / evidence["size"][1],
                            )
                            self.assertAlmostEqual(physical_per_native_unit[0], 2.0, places=2)
                            self.assertAlmostEqual(physical_per_native_unit[1], 2.0, places=2)

                            def timer_measurement(sample_text, capture):
                                timer = app.monitor_elapsed
                                bounds = (
                                    timer.winfo_rootx() - root.winfo_rootx(),
                                    timer.winfo_rooty() - root.winfo_rooty(),
                                    timer.winfo_width(),
                                    timer.winfo_height(),
                                )
                                state_right = (app.monitor_state.winfo_rootx() -
                                               root.winfo_rootx() +
                                               app.monitor_state.winfo_width())
                                self.assertEqual(timer.cget("text"), sample_text)
                                self.assertGreaterEqual(timer.winfo_width(),
                                                        timer.winfo_reqwidth())
                                self.assertLessEqual(bounds[0] + bounds[2],
                                                     root.winfo_width())
                                self.assertLessEqual(state_right, bounds[0])
                                scale_x = (capture["image_pixels"]["width"] /
                                           capture["size"][0])
                                scale_y = (capture["image_pixels"]["height"] /
                                           capture["size"][1])
                                roi = [round(bounds[0] * scale_x),
                                       round(bounds[1] * scale_y),
                                       round(bounds[2] * scale_x),
                                       round(bounds[3] * scale_y)]
                                return {
                                    "text": sample_text,
                                    "widget_bounds_tk_relative_to_content_view": list(bounds),
                                    "capture_roi_pixels_relative_to_content_view": roi,
                                    "capture_image": capture["screenshot"],
                                    "capture_dimensions_pixels": [
                                        capture["image_pixels"]["width"],
                                        capture["image_pixels"]["height"]],
                                    "physical_pixels_per_tk_unit": [scale_x, scale_y],
                                    "font": str(timer.cget("font")),
                                    "foreground": app.style.lookup(
                                        "TLabel", "foreground"),
                                    "anchor": str(timer.cget("anchor")),
                                }

                            timer_record = {
                                "tk_scaling": scale_readback,
                                "capacity": capacity,
                                "language": "en" if language == ENGLISH else "zh-TW",
                                "normal": timer_measurement("00:00", evidence),
                            }
                            app._render_monitoring_elapsed(SimpleNamespace(
                                monitoring_elapsed_seconds=36000))
                            root.update_idletasks()
                            long_key = key + "-timer-600m"
                            long_capture = capture_tk_content_view_evidence(
                                root, long_key, {
                                    "monitor_state": app.monitor_state,
                                    "monitor_elapsed": app.monitor_elapsed,
                                }, output_dir=evidence_dir)
                            timer_record["long_minutes"] = timer_measurement(
                                "600:00", long_capture)
                            timer_samples.append(timer_record)
                            app._render_monitoring_elapsed(SimpleNamespace(
                                monitoring_elapsed_seconds=0))
                            root.update_idletasks()
                            record = {
                            "tk_scaling": scale_readback,
                            "capacity": capacity,
                            "language": language,
                            "profile_change_path": (
                                "Settings profile editor entries + Apply button; "
                                "verified persisted profile reload"),
                            "tk_bounds": {
                                "root": [root.winfo_width(), root.winfo_height()],
                                "kvm_parent": [parent.winfo_x(), parent.winfo_y(),
                                               parent.winfo_width(), parent.winfo_height()],
                                "left_locator": [left.winfo_x(), left.winfo_y(), 22, 22],
                                "left_locator_root_offset": [
                                    left.winfo_rootx() - root.winfo_rootx(),
                                    left.winfo_rooty() - root.winfo_rooty()],
                                "first_cell": [app.kvm_result_blocks[1].winfo_x(),
                                               app.kvm_result_blocks[1].winfo_y(), 34, 26],
                                "right_locator": [right.winfo_x(), right.winfo_y(), 22, 22],
                                "locator_origin_distance": right.winfo_x() - left.winfo_x(),
                                "locator_outer_span": right.winfo_x() + 22 - left.winfo_x(),
                                "left_white_cell": [left.white_cell.winfo_x(),
                                                    left.white_cell.winfo_y(), 8, 8],
                                "left_inner_margins": [3, 11, 3, 11],
                                "quiet_margins": {
                                    "left_from_root": left.winfo_rootx() - root.winfo_rootx(),
                                    "top": left.winfo_y(),
                                    "right_within_parent": parent.winfo_width() -
                                    (left.winfo_x() + left.winfo_width()),
                                    "bottom_within_parent": parent.winfo_height() -
                                    (left.winfo_y() + left.winfo_height()),
                                },
                            },
                            "physical_pixels_per_tk_unit": physical_per_native_unit,
                            "native_window_bounds_including_titlebar": evidence["native_bounds"],
                            "window_frame_extra_tk_units": [
                                evidence["native_bounds"]["Width"] - root.winfo_width(),
                                evidence["native_bounds"]["Height"] - root.winfo_height()],
                            "screenshot": evidence["screenshot"],
                            "native_bounds": evidence["native_bounds"],
                            "image_pixels": evidence["image_pixels"],
                            }
                            matrix.append(record)
                            (evidence_dir / (key + ".json")).write_text(
                                json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
                    self.assertEqual((app._display_capacity(), app.kvm_results.winfo_height()),
                                     (20, KVM_BAND_HEIGHT))
                    edit_visible_profile_capacity(1)
                    root.update()
                    self.assertEqual((app._display_capacity(), app.kvm_results.winfo_height()),
                                     (1, 61))
                finally:
                    app.hotkey.close()
                    app.rounds.request_close()
                    self.wait_for_ui(root, lambda: app.rounds.close_status().status == "complete")
                    self.wait_for_ui(root, lambda: app.rounds.app_event_status().complete)
                    root.destroy()
        (evidence_dir / "li7-geometry-matrix.json").write_text(
            json.dumps(matrix, ensure_ascii=False, indent=2), encoding="utf-8")
        (evidence_dir / "timer-crop-matrix.json").write_text(
            json.dumps(timer_samples, ensure_ascii=False, indent=2), encoding="utf-8")

    def set_language_for_test_setup(self, app, root, language):
        """Set a test fixture's locale without opening the modal native Menu."""
        if app.current_language != language:
            app._select_language(language)
            root.update()

    def diagnostics_language_retry(self, app):
        if app.app_diagnostics_window is None or not app.app_diagnostics_window.winfo_exists():
            app.open_app_diagnostics()
        return app.app_diagnostics_language_retry_button

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_settings_and_recovery_actions_explain_bilingual_behavior_without_invoking(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey,
                session_root=Path(temporary) / "sessions",
                app_event_path=Path(temporary) / "app-events.json")
            errors = []
            global_motion_bindings = set()
            root.report_callback_exception = lambda *error: errors.append(error)
            try:
                app.open_settings()
                self.wait_for_ui(root, lambda: app.settings_window.winfo_viewable())
                self.assertEqual(len(app._settings_button_hints), 14)
                global_motion_bindings.update(
                    hint._global_motion_binding
                    for hint in app._settings_button_hints.values())
                evidence_root = os.environ.get("B518_TK_EVIDENCE_DIR")
                target = next(button for button, message_id in app._settings_button_ids.items()
                              if message_id == "app.settings.profile.choose_directory")

                def capture_settings(key, language):
                    record = capture_tk_window_evidence(
                        app.settings_window, key, language,
                        {"browse": target, "save retention": app.retention_save_button})
                    if evidence_root:
                        write_tk_bounds_evidence(key + "-" + language, record)

                root.update()
                capture_settings("st4-settings-configuration", "en")
                hint = app._settings_button_hints[target]
                self.assertIsNotNone(Quartz, "native macOS pointer input is unavailable")

                def post_mouse(widget, event_kind):
                    point = (widget.winfo_rootx() + widget.winfo_width() // 2,
                             widget.winfo_rooty() + widget.winfo_height() // 2)
                    Quartz.CGEventPost(
                        Quartz.kCGSessionEventTap,
                        Quartz.CGEventCreateMouseEvent(
                            None, event_kind, point, Quartz.kCGMouseButtonLeft))
                    root.update()
                    time.sleep(.08)
                    root.update()

                def post_key(keycode, shift=False):
                    flags = Quartz.kCGEventFlagMaskShift if shift else 0
                    for down in (True, False):
                        event = Quartz.CGEventCreateKeyboardEvent(None, keycode, down)
                        Quartz.CGEventSetFlags(event, flags)
                        Quartz.CGEventPostToPid(os.getpid(), event)
                    root.update()
                    time.sleep(.08)
                    root.update()

                previous_control = target.tk_focusPrev()
                previous_control.focus_force()
                root.update()
                post_key(48)
                self.wait_for_ui(root, lambda: root.focus_get() is target)
                self.wait_for_ui(root, lambda: hint._window is not None)
                self.assertIs(root.focus_get(), target)
                self.assertEqual(app.profile_editor_paths["active"].get(), "")
                post_mouse(app.settings_window, Quartz.kCGEventMouseMoved)
                post_key(48)
                self.wait_for_ui(root, lambda: root.focus_get() is not target)
                self.wait_for_ui(root, lambda: hint._window is None)

                post_mouse(target, Quartz.kCGEventMouseMoved)
                self.wait_for_ui(root, lambda: hint._window is not None)
                self.assertIn("Choose the source folder", hint._label.cget("text"))
                self.assertEqual(app.profile_editor_paths["active"].get(), "")
                app._select_language(TRADITIONAL_CHINESE)
                self.assertIn("來源資料夾", hint._label.cget("text"))
                self.assertEqual(app.profile_editor_paths["active"].get(), "")
                root.update()
                capture_settings("st4-settings-configuration", "zh-TW")
                post_mouse(app.settings_window, Quartz.kCGEventMouseMoved)
                self.wait_for_ui(root, lambda: hint._window is None)
                app.settings_notebook.select(1)
                root.update()
                capture_settings("st4-settings-events", "zh-TW")
                app.settings_notebook.select(2)
                root.update()
                capture_settings("st4-settings-retention", "zh-TW")
                app._select_language(ENGLISH)
                app.settings_notebook.select(0)
                root.update()
                capture_settings("st4-settings-configuration", "en")
                app.settings_notebook.select(1)
                root.update()
                capture_settings("st4-settings-events", "en")
                app.settings_notebook.select(2)
                root.update()
                capture_settings("st4-settings-retention", "en")

                app._open_recovery_center()
                self.wait_for_ui(root, lambda: app.recovery_window.winfo_viewable())
                global_motion_bindings.update(
                    hint._global_motion_binding
                    for hint in app._recovery_control_hints.values())
                recovery_controls = {
                    "tabs": app.recovery_tabs,
                    "alarm acknowledgement": app.recovery_alarm_ack_button,
                    "retry save": app.recovery_save_retry_button,
                    "retry archive": app.recovery_archive_retry_button,
                }

                def capture_recovery(key, language):
                    record = capture_tk_window_evidence(
                        app.recovery_window, key, language, recovery_controls)
                    if evidence_root:
                        write_tk_bounds_evidence(key + "-" + language, record)

                def capture_recovery_hover(key):
                    if not evidence_root:
                        return
                    from Foundation import NSURL

                    native_windows = Quartz.CGWindowListCopyWindowInfo(
                        Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID)
                    native_window = next((item for item in native_windows
                                          if item.get(Quartz.kCGWindowOwnerPID) == os.getpid()
                                          and item.get(Quartz.kCGWindowName) ==
                                          app.recovery_window.title()), None)
                    self.assertIsNotNone(native_window)
                    bounds = native_window[Quartz.kCGWindowBounds]
                    rect = Quartz.CGRectMake(bounds["X"], bounds["Y"],
                                             bounds["Width"], bounds["Height"])
                    image = Quartz.CGWindowListCreateImage(
                        rect, Quartz.kCGWindowListOptionOnScreenOnly,
                        Quartz.kCGNullWindowID, Quartz.kCGWindowImageDefault)
                    self.assertIsNotNone(image)
                    output = Path(evidence_root) / (key + ".png")
                    output.parent.mkdir(parents=True, exist_ok=True)
                    destination = Quartz.CGImageDestinationCreateWithURL(
                        NSURL.fileURLWithPath_(str(output)), "public.png", 1, None)
                    Quartz.CGImageDestinationAddImage(destination, image, None)
                    self.assertTrue(Quartz.CGImageDestinationFinalize(destination))

                retry_hint = app._recovery_control_hints[app.recovery_save_retry_button]
                self.assertEqual(str(app.recovery_save_retry_button.cget("state")), "disabled")
                capture_recovery("st4-recovery-alarms", "en")
                app.recovery_tabs.select(1)
                root.update()
                post_mouse(app.recovery_save_retry_button, Quartz.kCGEventMouseMoved)
                self.wait_for_ui(root, lambda: retry_hint._window is not None)
                self.assertIn("Select a round whose save failed", retry_hint._label.cget("text"))
                self.assertEqual(app._recovery_selected_save, None)
                capture_recovery_hover("st4-recovery-disabled-save-tooltip-en")
                with patch.object(app.rounds, "retry_saves", wraps=app.rounds.retry_saves) as retry_saves:
                    for event_kind in (Quartz.kCGEventLeftMouseDown,
                                       Quartz.kCGEventLeftMouseUp):
                        post_mouse(app.recovery_save_retry_button, event_kind)
                    retry_saves.assert_not_called()
                app._select_language(TRADITIONAL_CHINESE)
                self.assertIn("請選取保存失敗的輪次", retry_hint._label.cget("text"))
                self.assertIsNotNone(retry_hint._window)
                root.update()
                time.sleep(.16)
                root.update()
                capture_recovery_hover("st4-recovery-disabled-save-tooltip-zh-TW")
                capture_recovery("st4-recovery-alarms", "zh-TW")
                app.recovery_tabs.select(1)
                root.update()
                capture_recovery("st4-recovery-saves-archives", "zh-TW")
                app._select_language(ENGLISH)
                root.update()
                capture_recovery("st4-recovery-saves-archives", "en")
                self.assertEqual(app._recovery_selected_save, None)

                app.settings_window.withdraw()
                app.recovery_window.withdraw()
                app.root.deiconify()
                app.root.lift()
                app.root.focus_force()
                root.update()
                main_hint = app._main_action_hints[app.start_button]
                post_mouse(app.start_button, Quartz.kCGEventMouseMoved)
                self.wait_for_ui(root, lambda: main_hint._window is not None)
                self.assertIsNone(retry_hint._window)
                self.assertEqual(app.profile_editor_paths["active"].get(), "")
                self.assertEqual(errors, [])
            finally:
                for window in (app.settings_window, app.recovery_window):
                    if window is not None and window.winfo_exists():
                        window.destroy()
                root.update()
                remaining_motion_bindings = str(
                    root.tk.call("bind", "all", "<Motion>"))
                self.assertTrue(all(binding not in remaining_motion_bindings
                                    for binding in global_motion_bindings))
                app.close()
                root.destroy()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_main_page_actions_explain_bilingual_behavior_without_invoking(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey,
                session_root=Path(temporary) / "sessions",
                app_event_path=Path(temporary) / "app-events.json")
            errors = []
            root.report_callback_exception = lambda *error: errors.append(error)
            try:
                self.wait_for_ui(root, lambda: app.start_button.winfo_viewable())
                self.assertIsNone(app.rounds.snapshot())
                hint_controls = (
                    (app.start_button, "Start monitoring", "依所選專案"),
                    (app.stop_button, "Stop collecting", "停止目前監控輪次"),
                    (app.retry_save_button, "Retry saving", "重試保存先前"),
                    (app.app_diagnostics_button, "App diagnostics", "開啟 App 診斷"),
                )
                for button, expected_en, expected_zh in hint_controls:
                    hint = app._main_action_hints[button]
                    button.event_generate("<Enter>")
                    self.wait_for_ui(root, lambda: hint._window is not None)
                    self.assertIn(expected_en, hint._label.cget("text"))
                    self.assertIsNone(app.rounds.snapshot())
                    button.event_generate("<Leave>")
                    root.update()
                    self.assertIsNone(hint._window)
                    app._select_language(TRADITIONAL_CHINESE)
                    button.event_generate("<Enter>")
                    self.wait_for_ui(root, lambda: hint._window is not None)
                    self.assertIn(expected_zh, hint._label.cget("text"))
                    self.assertIsNone(app.rounds.snapshot())
                    button.event_generate("<Leave>")
                    root.update()
                    app._select_language(ENGLISH)

                self.assertTrue(app.retry_save_button.instate(("disabled",)))
                disabled_hint = app._main_action_hints[app.retry_save_button]
                app.retry_save_button.event_generate("<Enter>")
                self.wait_for_ui(root, lambda: disabled_hint._window is not None)
                self.assertIn("No failed save", disabled_hint._label.cget("text"))
                app.retry_save_button.event_generate("<Leave>")
                root.update()
                app._select_language(TRADITIONAL_CHINESE)
                app.retry_save_button.event_generate("<Enter>")
                self.wait_for_ui(root, lambda: disabled_hint._window is not None)
                self.assertIn("目前沒有等待重試", disabled_hint._label.cget("text"))
                app.retry_save_button.event_generate("<Leave>")
                root.update()
                app._select_language(ENGLISH)

                self.assertIsNotNone(Quartz, "native macOS pointer and keyboard input is unavailable")
                kvm_geometry = (app.kvm_results.winfo_x(), app.kvm_results.winfo_y(),
                                app.kvm_results.winfo_width(), app.kvm_results.winfo_height())
                kvm_colours = {slot: widget.cget("background")
                               for slot, widget in app.kvm_result_blocks.items()}
                button_controls = (
                    app.settings_button, app.review_button, app.round_alarm_button,
                    app.language_button, app.start_button, app.stop_button,
                    app.retry_save_button, app.app_diagnostics_button,
                )
                button_geometry = tuple(
                    (widget.winfo_x(), widget.winfo_y(),
                     widget.winfo_width(), widget.winfo_height())
                    for widget in button_controls)
                NSRunningApplication.currentApplication().activateWithOptions_(
                    NSApplicationActivateIgnoringOtherApps)
                root.attributes("-topmost", True)
                root.lift()
                root.focus_force()
                app.app_diagnostics_button.focus_force()
                root.update()
                evidence_dir = os.environ.get("B518_TK_EVIDENCE_DIR")
                controls = {
                    "start": app.start_button,
                    "stop": app.stop_button,
                    "retry": app.retry_save_button,
                    "diagnostics": app.app_diagnostics_button,
                    "kvm": app.kvm_results,
                }
                evidence_records = {}
                if evidence_dir:
                    evidence_records["diagnostics-focus-en"] = capture_tk_window_evidence(
                        root, "st3-main-focus-diagnostics", "en", controls)

                def post_key(keycode, shift=False):
                    flags = Quartz.kCGEventFlagMaskShift if shift else 0
                    for down in (True, False):
                        event = Quartz.CGEventCreateKeyboardEvent(None, keycode, down)
                        Quartz.CGEventSetFlags(event, flags)
                        Quartz.CGEventPostToPid(os.getpid(), event)
                    self.wait_for_ui(root, lambda: root.focus_get() is not None)

                def post_mouse(widget, event_kind, x=None, y=None):
                    point = (
                        widget.winfo_rootx() + (widget.winfo_width() // 2 if x is None else x),
                        widget.winfo_rooty() + (widget.winfo_height() // 2 if y is None else y),
                    )
                    Quartz.CGEventPost(
                        Quartz.kCGSessionEventTap,
                        Quartz.CGEventCreateMouseEvent(
                            None, event_kind, point, Quartz.kCGMouseButtonLeft))
                    root.update()
                    time.sleep(.08)
                    root.update()

                # A real Shift+Tab moves from the diagnostics link to Start; the
                # focus hint must not move focus or execute its command.
                post_key(48, shift=True)
                self.wait_for_ui(root, lambda: root.focus_get() is app.start_button)
                start_hint = app._main_action_hints[app.start_button]
                self.wait_for_ui(root, lambda: start_hint._window is not None)
                hint_window = start_hint._window
                self.assertIs(root.focus_get(), app.start_button)
                self.assertIsNone(app.rounds.snapshot())

                if evidence_dir:
                    evidence_records["start-focus-en"] = capture_tk_window_evidence(
                        root, "st3-main-focus", "en", controls)
                app._select_language(TRADITIONAL_CHINESE)
                self.wait_for_ui(root, lambda: "開始監控" in start_hint._label.cget("text"))
                self.assertIs(start_hint._window, hint_window)
                self.assertIsNone(app.rounds.snapshot())
                if evidence_dir:
                    evidence_records["start-focus-zh-TW"] = capture_tk_window_evidence(
                        root, "st3-main-focus", "zh-TW", controls)

                # Moving the physical pointer away cannot dismiss a hint that is
                # still justified by keyboard focus.
                post_mouse(app.kvm_results, Quartz.kCGEventMouseMoved)
                self.wait_for_ui(root, lambda: start_hint._window is not None)
                self.assertIs(root.focus_get(), app.start_button)
                self.assertIn("開始監控", start_hint._label.cget("text"))
                if evidence_dir:
                    app._select_language(ENGLISH)
                    root.update()
                    evidence_records["start-focus-mouse-out-en"] = capture_tk_window_evidence(
                        root, "st3-main-focus-mouse-out", "en", controls)
                    app._select_language(TRADITIONAL_CHINESE)
                    root.update()

                # Native pointer hover on the enabled button shows its hint;
                # pressing then dragging out cancels, so no monitoring starts.
                post_mouse(app.start_button, Quartz.kCGEventMouseMoved)
                self.wait_for_ui(root, lambda: start_hint._window is not None)
                self.assertIn("開始監控", start_hint._label.cget("text"))
                if evidence_dir:
                    evidence_records["start-hover-zh-TW"] = capture_tk_window_evidence(
                        root, "st3-main-hover", "zh-TW", controls)
                    app._select_language(ENGLISH)
                    root.update()
                    evidence_records["start-hover-en"] = capture_tk_window_evidence(
                        root, "st3-main-hover", "en", controls)
                    app._select_language(TRADITIONAL_CHINESE)
                    root.update()
                post_mouse(app.start_button, Quartz.kCGEventLeftMouseDown)
                self.assertTrue(app.start_button.instate(("pressed",)),
                                "native mouse-down must expose the pressed button state")
                if evidence_dir:
                    capture_tk_window_evidence(root, "st3-main-pressed", "zh-TW", controls)
                post_mouse(app.rows_canvas, Quartz.kCGEventMouseMoved)
                post_mouse(app.rows_canvas, Quartz.kCGEventLeftMouseUp)
                self.assertIsNone(app.rounds.snapshot(), "dragging out must not start monitoring")

                # The disabled Stop control remains hover-readable without
                # acquiring focus or running its command.
                disabled_stop_hint = app._main_action_hints[app.stop_button]
                post_mouse(app.stop_button, Quartz.kCGEventMouseMoved)
                self.wait_for_ui(root, lambda: disabled_stop_hint._window is not None)
                self.assertIn("停止目前監控輪次", disabled_stop_hint._label.cget("text"))
                self.assertTrue(app.stop_button.instate(("disabled",)))
                if evidence_dir:
                    capture_tk_window_evidence(root, "st3-main-disabled-hover", "zh-TW", controls)
                post_mouse(app.stop_button, Quartz.kCGEventLeftMouseDown)
                self.assertFalse(app.stop_button.instate(("pressed",)),
                                 "disabled controls must not enter the pressed state")
                post_mouse(app.stop_button, Quartz.kCGEventLeftMouseUp)
                self.assertIsNone(app.rounds.snapshot(), "a disabled Stop control must not act")
                self.assertEqual(errors, [])
                self.assertEqual(
                    (app.kvm_results.winfo_x(), app.kvm_results.winfo_y(),
                     app.kvm_results.winfo_width(), app.kvm_results.winfo_height()),
                    kvm_geometry, "button states must not move the KVM results band")
                self.assertEqual(
                    {slot: widget.cget("background")
                     for slot, widget in app.kvm_result_blocks.items()},
                    kvm_colours, "button states must not recolour KVM result slots")
                self.assertEqual(
                    tuple((widget.winfo_x(), widget.winfo_y(),
                           widget.winfo_width(), widget.winfo_height())
                          for widget in button_controls),
                    button_geometry, "button feedback must not change control geometry")
                if evidence_dir:
                    evidence_records["stop-disabled-hover-zh-TW"] = capture_tk_window_evidence(
                        root, "st3-main-disabled-hover", "zh-TW", controls)
                    Path(evidence_dir, "st3-window-bounds.json").write_text(
                        json.dumps(evidence_records, ensure_ascii=False, indent=2),
                        encoding="utf-8")
                self.assertEqual(errors, [])
            finally:
                app.rounds.request_close()
                self.wait_for(lambda: app.rounds.close_status().status == "complete")
                app.hotkey.close()
                root.destroy()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_hf4_dashboard_uses_compact_status_and_diagnostic_entry(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.deiconify()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey,
                session_root=Path(temporary) / "sessions",
                app_event_path=Path(temporary) / "app-events.json",
            )
            try:
                self.wait_for_ui(root, lambda: root.winfo_ismapped() and
                                 app.app_diagnostics_button.winfo_ismapped())

                def visible_texts(parent):
                    values = []
                    for child in parent.winfo_children():
                        if not child.winfo_viewable():
                            continue
                        if "text" in child.keys():
                            values.append(str(child.cget("text")))
                        values.extend(visible_texts(child))
                    return values

                main_text = visible_texts(root)
                self.assertNotIn("Retry Selected", main_text)
                self.assertNotIn("Retry Archive", main_text)
                self.assertNotIn("Retry Text", main_text)
                self.assertNotIn("重試所選", main_text)
                self.assertNotIn("重試封存", main_text)
                self.assertNotIn("重試文字", main_text)
                self.assertEqual(app.app_event_status_label.cget("text"), "App events saved")
                self.assertLessEqual(root.winfo_width(), WINDOW_WIDTH)

                root.focus_force()
                app.app_diagnostics_button.focus_set()
                root.update()
                self.assertIs(root.focus_get(), app.app_diagnostics_button)
                app.app_diagnostics_button.event_generate("<KeyPress-Return>")
                root.update()
                self.assertTrue(app.app_diagnostics_window.winfo_viewable())
                self.assertTrue(app.app_diagnostics_language_retry_button.winfo_viewable())
                self.assertTrue(app.app_diagnostics_retry_button.winfo_viewable())
                self.assertEqual(app.app_diagnostics_window.title(),
                                 app._t("app.diagnostic.heading"))
                self.assertEqual(root.winfo_width(), WINDOW_WIDTH)
                self.assertGreater(app.kvm_results.winfo_height(), 0)
                app._close_app_diagnostics_window()
                root.update()

                root.focus_force()
                app.app_diagnostics_button.focus_set()
                root.update()
                app.app_diagnostics_button.event_generate("<KeyPress-space>")
                app.app_diagnostics_button.event_generate("<KeyRelease-space>")
                root.update()
                self.assertTrue(app.app_diagnostics_window.winfo_viewable())
                app._close_app_diagnostics_window()
                root.update()

                self.assertIsNotNone(Quartz, "native macOS input support is unavailable")
                root.lift()
                root.focus_force()
                NSApplication.sharedApplication().setActivationPolicy_(
                    NSApplicationActivationPolicyRegular)
                NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
                NSRunningApplication.currentApplication().activateWithOptions_(
                    NSApplicationActivateIgnoringOtherApps)
                activation_deadline = time.monotonic() + .3
                while time.monotonic() < activation_deadline:
                    root.update()
                    time.sleep(.01)
                point = (app.app_diagnostics_button.winfo_rootx() +
                         app.app_diagnostics_button.winfo_width() // 2,
                         app.app_diagnostics_button.winfo_rooty() +
                         app.app_diagnostics_button.winfo_height() // 2)
                for event_kind in (Quartz.kCGEventMouseMoved,
                                   Quartz.kCGEventLeftMouseDown,
                                   Quartz.kCGEventLeftMouseUp):
                    Quartz.CGEventPost(
                        Quartz.kCGSessionEventTap,
                        Quartz.CGEventCreateMouseEvent(
                            None, event_kind, point, Quartz.kCGMouseButtonLeft))
                    deadline = time.monotonic() + .12
                    while time.monotonic() < deadline:
                        root.update()
                        time.sleep(.01)
                mouse_opened_diagnostics = (
                    app.app_diagnostics_window is not None and
                    app.app_diagnostics_window.winfo_viewable())
                if not mouse_opened_diagnostics:
                    # Keep functional keyboard acceptance independent from Aqua
                    # refusing to activate this test process for native pointer input.
                    app.app_diagnostics_button.focus_set()
                    app.app_diagnostics_button.event_generate("<KeyPress-Return>")
                    root.update()
                self.assertTrue(app.app_diagnostics_window.winfo_viewable())

                self.set_language_for_test_setup(app, root, TRADITIONAL_CHINESE)
                self.assertEqual(app.app_event_status_label.cget("text"),
                                 app._t("main.app_status.saved"))
                self.assertEqual(app.app_diagnostics_button.cget("text"), "App 診斷")
                self.assertTrue(app.app_diagnostics_window.winfo_viewable())

                fail_refresh = [True]
                receiver = ttk.Label(root, text="untranslated")

                def refresh_receiver():
                    if fail_refresh[0]:
                        raise RuntimeError("injected dashboard text failure")
                    receiver.configure(text="已更新")

                unregister = app.register_language_receiver(
                    "Controlled window", refresh_receiver, receiver.winfo_exists)
                app._select_language(ENGLISH)
                root.update()
                self.assertEqual(app.app_event_status_label.cget("text"),
                                 "Text refresh failed")
                self.assertEqual(str(app.app_diagnostics_language_retry_button.cget("state")),
                                 "normal")
                self.wait_for_ui(root, lambda: any(
                    event.get("localized_message", {}).get("message_id") ==
                    "app.language.refresh_failed"
                    for event in app._app_diagnostics_records))
                failure = next(event for event in app.rounds.app_event_records()
                               if event.get("localized_message", {}).get("message_id") ==
                               "app.language.refresh_failed")
                failure_index = next(index for index, event in enumerate(
                    app._app_diagnostics_records) if event["event_id"] == failure["event_id"])
                app.app_diagnostics_list.selection_clear(0, "end")
                app.app_diagnostics_list.selection_set(failure_index)
                app.app_diagnostics_list.event_generate("<<ListboxSelect>>")
                root.update()
                failure_detail = app.app_diagnostics_detail.get("1.0", "end-1c")
                self.assertIn("injected dashboard text failure", failure_detail)
                self.assertIn("app.language.refresh_failed", failure_detail)
                if os.environ.get("B518_TK_EVIDENCE_DIR"):
                    for language, key in ((ENGLISH, "en"),
                                          (TRADITIONAL_CHINESE, "zh-TW")):
                        app._select_language(language)
                        root.update()
                        failure_index = next(index for index, event in enumerate(
                            app._app_diagnostics_records)
                            if event["event_id"] == failure["event_id"])
                        app.app_diagnostics_list.selection_clear(0, "end")
                        app.app_diagnostics_list.selection_set(failure_index)
                        app.app_diagnostics_list.event_generate("<<ListboxSelect>>")
                        root.update()
                        self.assertIn("injected dashboard text failure",
                                      app.app_diagnostics_detail.get("1.0", "end-1c"))
                        self.assertTrue(app.app_diagnostics_language_retry_button.winfo_viewable())
                        self.assertEqual(str(app.app_diagnostics_language_retry_button[
                            "state"]), "normal")
                        capture_tk_window_evidence(
                            app.app_diagnostics_window,
                            "hf4-diagnostics-language-failure", key, {
                                "diagnostic_list": app.app_diagnostics_list,
                                "raw_diagnostic": app.app_diagnostics_detail,
                                "retry_language": app.app_diagnostics_language_retry_button,
                                "retry_app_events": app.app_diagnostics_retry_button,
                            })
                fail_refresh[0] = False
                app.app_diagnostics_language_retry_button.invoke()
                self.wait_for_ui(root, lambda: str(
                    app.app_diagnostics_language_retry_button.cget("state")) == "disabled")
                self.assertEqual(receiver.cget("text"), "已更新")
                self.assertEqual(app.app_event_status_label.cget("text"),
                                 app._t("main.app_status.saved"))
                unregister()

                if os.environ.get("B518_TK_EVIDENCE_DIR"):
                    for language, key in ((ENGLISH, "en"),
                                          (TRADITIONAL_CHINESE, "zh-TW")):
                        app._select_language(language)
                        root.update()
                        self.wait_for_ui(root, lambda: root.winfo_ismapped() and
                                         app.app_diagnostics_button.winfo_viewable())
                        capture_tk_window_evidence(root, "hf4-home", key, {
                            "status": app.app_event_status_label,
                            "diagnostics": app.app_diagnostics_button,
                            "KVM": app.kvm_results,
                            "start": app.start_button,
                        })
                    write_tk_bounds_evidence("hf4-home-status-diagnostics", {
                        "window_width": root.winfo_width(),
                        "KVM_position": [app.kvm_results.winfo_x(),
                                         app.kvm_results.winfo_y(),
                                         app.kvm_results.winfo_width(),
                                         app.kvm_results.winfo_height()],
                        "diagnostic_click": (
                            "native click opened App diagnostics" if mouse_opened_diagnostics
                            else "BLOCKED: Aqua did not activate this process; Return opened diagnostics"
                        ),
                    })
            finally:
                if app.app_diagnostics_window and app.app_diagnostics_window.winfo_exists():
                    app._close_app_diagnostics_window()
                app.hotkey.close()
                app.rounds.request_close()
                self.wait_for_ui(root, lambda: app.rounds.close_status().status == "complete")
                self.wait_for_ui(root, lambda: app.rounds.app_event_status().complete)
                root.destroy()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_hm1_toolbar_title_status_and_kvm_geometry_stay_fixed(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.deiconify()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey,
                session_root=Path(temporary) / "sessions",
                app_event_path=Path(temporary) / "app-events.json",
            )
            try:
                self.wait_for_ui(root, lambda: root.winfo_ismapped() and
                                 app.retry_save_button.winfo_height() > 1)
                self.assertEqual(root.winfo_width(), WINDOW_WIDTH)
                self.assertGreaterEqual(root.winfo_height(), root.winfo_reqheight())
                self.assertGreaterEqual(app.stop_button.winfo_height(),
                                        app.stop_button.winfo_reqheight())
                self.assertGreaterEqual(app.retry_save_button.winfo_height(),
                                        app.retry_save_button.winfo_reqheight())
                self.assertEqual(root.title(), "B518 FCT ATE Log Solution-V{}".format(APP_VERSION))
                self.assertEqual(app.company_logo.width(), 137)
                self.assertEqual(app.company_logo.height(), 35)
                for button, glyph in ((app.settings_button, "⚙️"),
                                      (app.review_button, "⚠️"),
                                      (app.round_alarm_button, "🔔"),
                                      (app.language_button, "🌐")):
                    self.assertEqual(button.cget("text"), glyph)
                    self.assertTrue(button.winfo_viewable())

                footer_buttons = (
                    app.stop_button, app.retry_save_button, app.app_diagnostics_button,
                )
                footer_bounds = []
                for language in (ENGLISH, TRADITIONAL_CHINESE):
                    app._select_language(language)
                    root.update()
                    for button in footer_buttons:
                        self.assertTrue(button.winfo_viewable(), button.cget("text"))
                        self.assertGreaterEqual(button.winfo_width(), button.winfo_reqwidth(),
                                                button.cget("text"))
                        self.assertGreaterEqual(button.winfo_height(), button.winfo_reqheight(),
                                                button.cget("text"))
                        self.assertLessEqual(
                            button.winfo_rootx() - root.winfo_rootx() + button.winfo_width(),
                            root.winfo_width(), button.cget("text"))
                        self.assertLessEqual(
                            button.winfo_rooty() - root.winfo_rooty() + button.winfo_height(),
                            root.winfo_height(), button.cget("text"))
                    footer_bounds.append(tuple(
                        (button.winfo_rootx() - root.winfo_rootx(),
                         button.winfo_rooty() - root.winfo_rooty(),
                         button.winfo_width(), button.winfo_height())
                        for button in footer_buttons))
                self.assertEqual(footer_bounds[0], footer_bounds[1])
                app._select_language(ENGLISH)
                root.update()

                if os.environ.get("B518_TK_EVIDENCE_DIR"):
                    main_page_evidence = {}
                    for language, key in ((ENGLISH, "en"),
                                          (TRADITIONAL_CHINESE, "zh-TW")):
                        app._select_language(language)
                        root.update()
                        main_page_evidence[key] = capture_tk_window_evidence(
                            root, "main-page", key, {
                                "settings": app.settings_button,
                                "logo": app.company_logo_slot,
                                "review": app.review_group,
                                "alarm": app.round_alarm_button,
                                "language": app.language_button,
                                "project": app.project_choice,
                                "station": app.machine_choice,
                                "start": app.start_button,
                                "monitor_state": app.monitor_state,
                                "stop": app.stop_button,
                                "retry_save": app.retry_save_button,
                                "app_status": app.app_event_status_label,
                                "diagnostics": app.app_diagnostics_button,
                                "kvm": app.kvm_results,
                                "kvm_state_marker": app.kvm_state_marker,
                                "kvm_layout_marker": app.kvm_layout_marker,
                            })
                    write_tk_bounds_evidence("main_page", main_page_evidence)
                    app._select_language(ENGLISH)
                    root.update()

                def bounds(widgets):
                    return tuple((widget.winfo_x(), widget.winfo_y(),
                                  widget.winfo_width(), widget.winfo_height())
                                 for widget in widgets)

                toolbar = (app.settings_button, app.review_group,
                           app.round_alarm_button, app.language_button)
                kvm = (app.kvm_results, app.kvm_locator_left, app.kvm_locator_right,
                       app.kvm_state_marker, app.kvm_layout_marker,
                       *app.kvm_result_blocks.values())
                toolbar_bounds, kvm_bounds = bounds(toolbar), bounds(kvm)
                profile_choice_bounds = bounds((app.project_choice, app.machine_choice))
                if os.environ.get("B518_TK_EVIDENCE_DIR"):
                    self.assertEqual(
                        main_page_evidence["en"]["controls"],
                        main_page_evidence["zh-TW"]["controls"],
                    )
                self.assertEqual(app.review_badge.itemcget(app.review_badge_label, "text"), "")
                self.assertFalse(app.review_badge.winfo_ismapped())
                self.assertEqual(str(app.review_button["state"]), "disabled")
                review_group_bounds = bounds((app.review_group,))
                self.assertEqual(bounds(toolbar), toolbar_bounds)
                self.assertEqual(bounds(kvm), kvm_bounds)
                self.assertEqual(bounds((app.review_group,)), review_group_bounds)

                alarm = SimpleNamespace(round_id="hint-round", alarm_id="hint-alarm",
                                        acknowledged_at=None, created_at="2026-10-15T12:00:00")
                # This presentation test substitutes partial snapshots below;
                # stop the periodic live-round renderer before using them.
                for after_id in tuple(app._after_ids):
                    app._cancel_ui_timer(after_id)
                alarm_snapshot = SimpleNamespace(
                    round_alarm=alarm, round_alarm_ready=True, round_id=alarm.round_id,
                    pending_conflicts=(), source_preparation_pending=False,
                    state=SimpleNamespace(value="IDLE"), completion_reason=None,
                )
                original_snapshot = app.rounds.snapshot
                app.rounds.snapshot = lambda: alarm_snapshot
                original_render_conflict_button = app._render_conflict_review_button
                app._render_conflict_review_button = lambda snapshot=None: app.review_button.configure(
                    state="normal")

                tooltip_expectations = (
                    (app.settings_button, app._toolbar_hints[0],
                     "Open settings to edit engineer configuration, review events and Sessions, and manage retention."),
                    (app.language_button, app._toolbar_hints[1],
                     "Open the language list and select a display language. Current: English."),
                    (app.round_alarm_button, app._toolbar_hints[2],
                     "Open notifications and recovery for round alarms, save failures, and archive retries. Opening does not acknowledge an alarm or retry work."),
                    (app.review_button, app._toolbar_hints[3],
                     "Open conflict review. No conflicts are waiting for a decision."),
                )
                for widget, hint, expected in tooltip_expectations:
                    widget.configure(state="normal")
                    widget.event_generate("<Enter>")
                    deadline = time.monotonic() + 1
                    while hint._window is None and time.monotonic() < deadline:
                        root.update()
                        time.sleep(0.01)
                    self.assertIsNotNone(hint._window, expected)
                    self.assertEqual(hint._window.winfo_children()[0].cget("text"), expected)
                    widget.event_generate("<Leave>")
                    root.update()
                    if widget in (app.round_alarm_button, app.review_button):
                        widget.configure(state="disabled")
                language_hint = app._toolbar_hints[1]
                app.language_button.focus_force()
                app.language_button.event_generate("<Enter>")
                self.wait_for_ui(root, lambda: language_hint._window is not None)
                language_hint_window = language_hint._window
                app._select_language(TRADITIONAL_CHINESE)
                self.wait_for_ui(root, lambda:
                                 language_hint_window.winfo_children()[0].cget("text") ==
                                 "開啟語言清單並選擇介面語言。目前：繁體中文。")
                self.assertIs(language_hint._window, language_hint_window)
                self.assertEqual(sum(hint._window is not None
                                     for hint in app._toolbar_hints), 1)
                app.language_button.event_generate("<Leave>")
                root.update()

                disabled_hint = app._toolbar_hints[3]
                app.review_button.configure(state="normal")
                app.review_button.event_generate("<Enter>")
                self.wait_for_ui(root, lambda: disabled_hint._window is not None)
                app._render_conflict_review_button = original_render_conflict_button
                app._render_conflict_review_button(
                    SimpleNamespace(pending_conflicts=()))
                self.assertTrue(app.review_button.instate(("disabled",)))
                self.assertIsNotNone(disabled_hint._window)
                self.assertEqual(
                    disabled_hint._label.cget("text"),
                    "開啟待確認清單。目前沒有等待裁決的衝突。")
                self.assertEqual(app.review_button.invoke(), "")
                self.assertIsNone(app.conflict_window,
                                  "a disabled review control must not open its window")

                app._select_language(ENGLISH)
                root.update()
                settings_hint = app._toolbar_hints[0]
                app.settings_button.focus_force()
                app.settings_button.event_generate("<FocusIn>")
                root.update()
                deadline = time.monotonic() + 1
                while settings_hint._window is None and time.monotonic() < deadline:
                    root.update()
                    time.sleep(0.01)
                self.assertIsNotNone(settings_hint._window)
                self.assertIs(root.focus_get(), app.settings_button,
                              "showing a focus hint must not move keyboard focus")
                self.assertEqual(
                    settings_hint._window.winfo_children()[0].cget("text"),
                    "Open settings to edit engineer configuration, review events and Sessions, and manage retention.")
                settings_hint._hide()

                app.language_button.focus_force()
                root.update()
                for key in ("<space>", "<Return>", "<Down>"):
                    self.assertTrue(app.language_button.bind(key), key)

                app.settings_button.focus_force()
                root.update()
                app.settings_button.event_generate("<KeyPress-space>")
                app.settings_button.event_generate("<KeyRelease-space>")
                root.update()
                self.assertIsNotNone(app.settings_window)
                self.assertEqual(app.settings_window.title(), "Setting")
                app._close_settings()

                app.review_button.configure(state="normal")
                app.review_button.event_generate(
                    "<ButtonPress-1>", x=app.review_button.winfo_width() // 2,
                    y=app.review_button.winfo_height() // 2)
                app.review_button.event_generate(
                    "<ButtonRelease-1>", x=app.review_button.winfo_width() // 2,
                    y=app.review_button.winfo_height() // 2)
                root.update()
                self.assertIsNotNone(app.conflict_window)
                self.assertTrue(app.conflict_window.winfo_viewable())
                app.conflict_window.destroy()

                with patch.object(app.rounds, "snapshot", return_value=alarm_snapshot):
                    app.round_alarm_button.configure(state="normal")
                    app.round_alarm_button.event_generate(
                        "<ButtonPress-1>", x=app.round_alarm_button.winfo_width() // 2,
                        y=app.round_alarm_button.winfo_height() // 2)
                    app.round_alarm_button.event_generate(
                        "<ButtonRelease-1>", x=app.round_alarm_button.winfo_width() // 2,
                        y=app.round_alarm_button.winfo_height() // 2)
                    root.update()
                    self.assertIsNotNone(app.recovery_window)
                    self.assertEqual(app.recovery_window.title(), "Notifications and Recovery")
                    app.recovery_window.destroy()

                conflicts = tuple(SimpleNamespace() for _ in range(20))
                snapshot = SimpleNamespace(
                    round_id=None, pending_conflicts=conflicts, round_alarm=None,
                    source_preparation_pending=False, audit_complete=True, audit_errors=(),
                    results=(),
                    state=SimpleNamespace(value="IDLE"), completion_reason=None,
                )
                with patch.object(app.rounds, "snapshot", return_value=snapshot):
                    app._refresh_main_round_labels()
                    root.update_idletasks()
                    self.assertEqual(app.review_badge.itemcget(
                        app.review_badge_label, "text"), "20")
                    self.assertTrue(app.review_badge.winfo_ismapped())
                    self.assertEqual(str(app.review_button["state"]), "normal")
                    self.assertEqual(bounds(toolbar), toolbar_bounds)
                    self.assertEqual(bounds(kvm), kvm_bounds)
                    app._set_main_monitor_state("monitor.awaiting_conflicts", count=20)
                    app._select_language(TRADITIONAL_CHINESE)
                    root.update_idletasks()
                    self.assertEqual(root.title(), "B518 FCT ATE Log Solution-V{}".format(APP_VERSION))
                    self.assertIn("20", app.monitor_state.cget("text"))
                    self.assertEqual(app.review_badge.itemcget(
                        app.review_badge_label, "text"), "20")
                    self.assertEqual(bounds(toolbar), toolbar_bounds)
                    self.assertEqual(bounds((app.project_choice, app.machine_choice)),
                                     profile_choice_bounds)
                    app.project.set("SAMPLE")
                    app.station.set("BT")
                    app._render_main_title()
                    self.assertEqual(root.title(), "SAMPLE BT ATE Log Solution-V{}".format(APP_VERSION))
                    app._set_main_monitor_state("monitor.idle")
                    self.assertEqual(app.monitor_state.cget("text"), "待命")

                # The HMI is deliberately fixed-size. Give this disposable
                # control its own mapped host rather than packing it below an
                # already full main window, where Aqua drops Enter events.
                scratch_host = tk.Toplevel(root)
                scratch_button = ttk.Button(scratch_host)
                scratch_button.pack()
                scratch_hint = _LocalizedControlHint(scratch_button, lambda: "Scratch")
                self.wait_for_ui(root, lambda: scratch_button.winfo_viewable())
                scratch_button.event_generate("<Enter>")
                self.wait_for_ui(root, lambda: scratch_hint._window is not None)
                scratch_window = scratch_hint._window
                scratch_button.destroy()
                root.update()
                self.assertIsNone(scratch_hint._widget)
                self.assertFalse(scratch_window.winfo_exists())
                scratch_host.destroy()
            finally:
                if "original_snapshot" in locals():
                    app.rounds.snapshot = original_snapshot
                if "original_render_conflict_button" in locals():
                    app._render_conflict_review_button = original_render_conflict_button
                toolbar_hints = tuple(app._toolbar_hints)
                language_hint = toolbar_hints[1]
                root.deiconify()
                root.lift()
                app.language_button.focus_force()
                root.update()
                app.language_button.event_generate("<Enter>")
                self.wait_for_ui(root, lambda: language_hint._window is not None)
                language_hint_window = language_hint._window
                app.rounds.request_close()
                self.wait_for(lambda: app.rounds.close_status().status == "complete")
                app.hotkey.close()
                root.destroy()
                self.assertTrue(all(hint._widget is None for hint in toolbar_hints))
                self.assertFalse(language_hint_window.winfo_exists())

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_toolbar_keyboard_traverses_visual_order_and_leaves_toolbar(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey,
                session_root=Path(temporary) / "sessions",
                app_event_path=Path(temporary) / "app-events.json")
            callback_errors = []
            input_threads = []
            capture_errors = []
            evidence_value = os.environ.get("B518_TK_EVIDENCE_DIR")
            root.report_callback_exception = lambda *error: callback_errors.append(error)
            try:
                self.wait_for_ui(root, lambda: app.project_choice.winfo_ismapped())
                self.assertIsNotNone(Quartz, "native macOS keyboard input is unavailable")
                root.attributes("-topmost", True)
                root.lift()
                root.focus_force()
                NSRunningApplication.currentApplication().activateWithOptions_(
                    NSApplicationActivateIgnoringOtherApps)
                activation_deadline = time.monotonic() + .3
                while time.monotonic() < activation_deadline:
                    root.update()
                    time.sleep(.01)

                def post_key(keycode, shift=False, pump=True):
                    flags = Quartz.kCGEventFlagMaskShift if shift else 0
                    for down in (True, False):
                        event = Quartz.CGEventCreateKeyboardEvent(None, keycode, down)
                        self.assertIsNotNone(
                            event, "Quartz could not create key event {} ({})".format(
                                keycode, "down" if down else "up"))
                        Quartz.CGEventSetFlags(event, flags)
                        Quartz.CGEventPostToPid(os.getpid(), event)
                    if pump:
                        deadline = time.monotonic() + .08
                        while time.monotonic() < deadline:
                            root.update()
                            time.sleep(.01)

                geometry_widgets = (app.settings_button, app.review_group,
                                    app.round_alarm_button, app.language_button,
                                    app.kvm_results, app.kvm_state_marker, app.kvm_layout_marker,
                                    *app.kvm_result_blocks.values())
                def geometry():
                    return tuple((widget.winfo_x(), widget.winfo_y(),
                                  widget.winfo_width(), widget.winfo_height())
                                 for widget in geometry_widgets)
                baseline = geometry()
                for language, key in ((ENGLISH, "en"), (TRADITIONAL_CHINESE, "zh-TW")):
                    app._select_language(language)
                    root.update()
                    controls = (app.settings_button, app.review_button,
                                app.round_alarm_button, app.language_button, app.project_choice)
                    app.settings_button.focus_force()
                    root.update()
                    for source, target in zip(controls, controls[1:]):
                        source.event_generate("<KeyPress-Tab>")
                        root.update()
                        self.assertIs(root.focus_get(), target,
                                      "native Tab from {} reached {} instead of {}".format(
                                          source, root.focus_get(), target))
                    for source, target in zip(reversed(controls), reversed(controls[:-1])):
                        source.event_generate("<KeyPress-Tab>", state=1)
                        root.update()
                        self.assertIs(root.focus_get(), target)
                    app.settings_button.event_generate("<KeyPress-Tab>", state=1)
                    root.update()
                    self.assertNotIn(root.focus_get(), controls[:4])
                    app.round_alarm_button.focus_force()
                    root.update()
                    if root.tk.call("tk", "windowingsystem") == "aqua":
                        app.round_alarm_button.event_generate("<Shift-KeyPress-Tab>")
                    else:
                        app.round_alarm_button.event_generate("<KeyPress-ISO_Left_Tab>")
                    root.update()
                    self.assertIs(root.focus_get(), app.review_button)
                    # Review remains unavailable even when reached for orientation.
                    self.assertTrue(app.review_button.instate(["disabled"]))
                    app.review_button.event_generate("<KeyPress-space>")
                    app.review_button.event_generate("<KeyRelease-space>")
                    root.update()
                    self.assertIsNone(app.conflict_window)
                    for name, control in (
                            ("settings", app.settings_button),
                            ("review", app.review_button),
                            ("bell", app.round_alarm_button),
                            ("language", app.language_button),
                            ("project", app.project_choice)):
                        control.focus_force()
                        root.update()
                        self.assertEqual(geometry(), baseline)
                        self.assertEqual(sorted(controls[:4], key=lambda widget: widget.winfo_rootx()),
                                         list(controls[:4]))
                        capture_tk_window_evidence(root, "toolbar-focus-" + name, key,
                                                   {"focused": control})

                # A real Tab sequence reaches the language entry from the
                # preceding toolbar control; then native key events drive it.
                app.round_alarm_button.focus_force()
                root.update()
                post_key(48)  # Tab
                self.wait_for_ui(root, lambda: root.focus_get() is app.language_button)
                current_language = app.current_language
                process_id = os.getpid()
                app_title = root.title()
                root_bounds = Quartz.CGRectMake(
                    root.winfo_rootx(), root.winfo_rooty(),
                    root.winfo_width(), root.winfo_height())

                def capture_language_menu(screenshot_tag, active=False, delay=None,
                                          wait_for_capture=False):
                    if not evidence_value:
                        return

                    def capture():
                        try:
                            capture_delay = (.48 if active else .35) if delay is None else delay
                            time.sleep(capture_delay)
                            from Foundation import NSURL
                            image = Quartz.CGWindowListCreateImage(
                                root_bounds, Quartz.kCGWindowListOptionOnScreenOnly,
                                Quartz.kCGNullWindowID, Quartz.kCGWindowImageDefault)
                            if image is None:
                                raise AssertionError("native menu screen capture returned no image")
                            output_dir = Path(evidence_value)
                            output_dir.mkdir(parents=True, exist_ok=True)
                            tag = "active" if active else screenshot_tag
                            output = output_dir / "toolbar-language-menu-{}-{}.png".format(
                                key, tag)
                            destination = Quartz.CGImageDestinationCreateWithURL(
                                NSURL.fileURLWithPath_(str(output)), "public.png", 1, None)
                            Quartz.CGImageDestinationAddImage(destination, image, None)
                            if not Quartz.CGImageDestinationFinalize(destination):
                                raise AssertionError("could not save native menu capture {}".format(
                                    output))

                            native_windows = Quartz.CGWindowListCopyWindowInfo(
                                Quartz.kCGWindowListOptionOnScreenOnly,
                                Quartz.kCGNullWindowID)
                            app_window = next((window for window in native_windows
                                               if window.get(Quartz.kCGWindowOwnerPID) == process_id
                                               and window.get(Quartz.kCGWindowName) == app_title), None)
                            if app_window is None:
                                raise AssertionError("B518 root window missing during menu capture")
                            app_image = Quartz.CGWindowListCreateImage(
                                Quartz.CGRectNull,
                                Quartz.kCGWindowListOptionIncludingWindow,
                                app_window[Quartz.kCGWindowNumber],
                                Quartz.kCGWindowImageBoundsIgnoreFraming)
                            if app_image is None:
                                raise AssertionError("B518 root-window capture returned no image")
                            app_tag = "active" if active else screenshot_tag
                            app_output = output_dir / (
                                "toolbar-language-menu-{}-{}-app.png".format(key, app_tag))
                            app_destination = Quartz.CGImageDestinationCreateWithURL(
                                NSURL.fileURLWithPath_(str(app_output)), "public.png", 1, None)
                            Quartz.CGImageDestinationAddImage(app_destination, app_image, None)
                            if not Quartz.CGImageDestinationFinalize(app_destination):
                                raise AssertionError("could not save B518 window capture {}".format(
                                    app_output))
                        except Exception as error:
                            capture_errors.append("{}: {!r}".format(screenshot_tag, error))

                    thread = threading.Thread(target=capture, daemon=True)
                    input_threads.append(thread)
                    thread.start()
                    if wait_for_capture:
                        thread.join(timeout=3)
                        if thread.is_alive():
                            capture_errors.append(
                                "{}: timed out capturing native menu".format(screenshot_tag))

                popup_entered = threading.Event()
                popup_exited = threading.Event()
                actual_popup = app.language_menu.tk_popup

                def observed_popup(*args, **kwargs):
                    popup_entered.set()
                    try:
                        return actual_popup(*args, **kwargs)
                    finally:
                        popup_exited.set()

                popup_patcher = patch.object(app.language_menu, "tk_popup", observed_popup)
                popup_patcher.start()
                self.addCleanup(popup_patcher.stop)

                def send_menu_keys(screenshot_tag, keycodes):
                    def deliver():
                        try:
                            if not popup_entered.wait(3):
                                raise AssertionError("native menu popup never started")
                            time.sleep(.1)
                            capture_language_menu(screenshot_tag, delay=0,
                                                  wait_for_capture=True)
                            for index, keycode in enumerate(keycodes):
                                for down in (True, False):
                                    event = Quartz.CGEventCreateKeyboardEvent(
                                        None, keycode, down)
                                    if event is None:
                                        raise AssertionError(
                                            "Quartz could not create menu key event {} ({})".format(
                                                keycode, "down" if down else "up"))
                                    Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
                                if index < len(keycodes) - 1:
                                    time.sleep(.18)
                        except Exception as error:
                            capture_errors.append("{} keyboard input: {!r}".format(
                                screenshot_tag, error))

                    thread = threading.Thread(target=deliver, daemon=True)
                    input_threads.append(thread)
                    thread.start()
                    if screenshot_tag == "return":
                        capture_language_menu(screenshot_tag, active=True)

                post_key(49, pump=False)  # Open, then cancel from inside native menu loop.
                send_menu_keys("escape", (53,))
                self.wait_for_ui(root, popup_exited.is_set)
                self.assertFalse(app.language_menu.winfo_viewable())
                self.assertEqual(app.language_choice.get(), current_language)
                self.assertIsNone(app._language_hint._window)
                self.assertEqual(app.language_choice.get(), current_language)
                self.assertIs(root.focus_get(), app.language_button)
                self.assertEqual(app.current_language, current_language)
                self.assertEqual(app.language_choice.get(), current_language)

                target_language = ENGLISH if current_language == TRADITIONAL_CHINESE else TRADITIONAL_CHINESE
                target_name = "English" if target_language == ENGLISH else "繁體中文"
                target_index = next(
                    index for index in range(app.language_menu.index("end") + 1)
                    if app.language_menu.entrycget(index, "label") == target_name)
                popup_entered.clear()
                popup_exited.clear()
                post_key(125, pump=False)  # Down opens; native menu receives further keys.
                send_menu_keys("return", (115,) + (125,) * target_index + (36,))
                root.update()
                self.wait_for_ui(root, lambda: app.language_choice.get() == target_language)
                self.assertEqual(app.language_choice.get(), target_language)
                self.assertIs(root.focus_get(), app.language_button)
                write_tk_bounds_evidence("st2-language-native-keyboard", {
                    "tab_focus": str(root.focus_get()),
                    "cancel_preserved_language": current_language,
                    "selected_language": app.current_language,
                    "selected_menu_index": target_index,
                })
                app.open_settings()
                root.update()
                children = []
                def collect(widget):
                    for child in widget.winfo_children():
                        children.append(child)
                        collect(child)
                collect(app.settings_window)
                entry = next(widget for widget in children
                             if isinstance(widget, ttk.Entry) and widget.winfo_viewable())
                entry.focus_force()
                self.wait_for_ui(root, lambda: root.focus_get() is entry)
                entry.event_generate("<KeyPress-Tab>")
                root.update()
                self.assertIs(root.focus_get().winfo_toplevel(), app.settings_window)
                app._close_settings()
                app.language_button.focus_force()
                root.update()
                post_key(49, pump=False)
                send_menu_keys("close", (53,))
                root.update()



            finally:
                for sender in input_threads:
                    sender.join(timeout=1)
                app.rounds.request_close()
                self.wait_for(lambda: app.rounds.close_status().status == "complete")
                app.hotkey.close()
                root.destroy()
            self.assertFalse(root.winfo_exists())
            self.assertEqual(callback_errors, [])
            if evidence_value:
                self.assertEqual(capture_errors, [],
                                 "native language-menu evidence/input failed")

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_hm1_logo_normal_missing_and_corrupt_keep_fixed_slot_without_dialog(self):
        with TemporaryDirectory() as temporary:
            temporary_path = Path(temporary)
            missing_logo = temporary_path / "missing.png"
            corrupt_logo = temporary_path / "corrupt.png"
            corrupt_logo.write_bytes(b"not a PNG")
            normal_logo = Path(__file__).resolve().parents[1] / "assets" / "foxlink_logo.png"
            expected_bounds = None

            for state, logo_path in (("normal", normal_logo),
                                     ("missing", missing_logo),
                                     ("corrupt", corrupt_logo)):
                with self.subTest(state=state), \
                        patch("b518_log_solution.PREFS_PATH",
                              temporary_path / "preferences.json"), \
                        patch("b518_log_solution.COMPANY_LOGO_PATH", logo_path):
                    root = tk.Tk()
                    root.deiconify()
                    app = B518LogSolutionApp(
                        root, hotkey_factory=FakeHotkey,
                        session_root=temporary_path / (state + "-sessions"),
                        app_event_path=temporary_path / (state + "-events.json"),
                    )
                    try:
                        self.wait_for_ui(root, lambda: app.company_logo_slot.winfo_ismapped() and
                                         app.company_logo_slot.winfo_width() > 1)
                        slot_bounds = (app.company_logo_slot.winfo_x(),
                                       app.company_logo_slot.winfo_y(),
                                       app.company_logo_slot.winfo_width(),
                                       app.company_logo_slot.winfo_height())
                        toolbar_bounds = tuple(
                            (widget.winfo_x(), widget.winfo_y(),
                             widget.winfo_width(), widget.winfo_height())
                            for widget in (app.settings_button, app.review_group,
                                           app.round_alarm_button, app.language_button)
                        )
                        self.assertEqual(slot_bounds[2:], (137, 35))
                        self.assertEqual(root.winfo_width(), WINDOW_WIDTH)
                        if expected_bounds is None:
                            expected_bounds = (slot_bounds, toolbar_bounds)
                        else:
                            self.assertEqual((slot_bounds, toolbar_bounds), expected_bounds)

                        if state == "normal":
                            self.assertIsNotNone(app.company_logo)
                            self.assertEqual((app.company_logo.width(), app.company_logo.height()),
                                             (137, 35))
                            self.assertEqual(len(app.company_logo_slot.winfo_children()), 1)
                        else:
                            self.assertIsNone(app.company_logo)
                            self.assertEqual(app.company_logo_slot.winfo_children(), [])

                        def descendants(widget):
                            for child in widget.winfo_children():
                                yield child
                                yield from descendants(child)

                        visible_text = [child.cget("text") for child in descendants(root)
                                        if "text" in child.keys()]
                        self.assertNotIn("B518 LOG", visible_text)
                        deadline = time.monotonic() + 0.4
                        while time.monotonic() < deadline:
                            root.update()
                            time.sleep(0.01)
                        self.assertEqual(
                            [child for child in root.children.values()
                             if isinstance(child, tk.Toplevel)], [],
                        )
                    finally:
                        app.rounds.request_close()
                        self.wait_for(lambda: app.rounds.close_status().status == "complete")
                        app.hotkey.close()
                        root.destroy()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_language_refresh_failure_keeps_other_receiver_and_offers_retry(self):
        root = tk.Tk()
        root.deiconify()
        app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey)
        other = ttk.Label(root, text="English")
        failed_window = ttk.Label(root, text="Not translated")
        other.pack()
        failed_window.pack()
        fail_refresh = [True]
        try:
            unregister = app.register_language_receiver(
                "Other window", lambda: other.configure(
                    text="繁體中文" if app.current_language == TRADITIONAL_CHINESE else "English"),
                other.winfo_exists)
            def refresh_failed_window():
                if fail_refresh[0]:
                    raise RuntimeError("diagnostic refresh failed")
                failed_window.configure(text="已更新")

            unregister_failed = app.register_language_receiver(
                "Diagnostics window", refresh_failed_window, failed_window.winfo_exists)
            with patch.object(app.project_label, "configure", side_effect=RuntimeError("refresh failed")):
                root.update()
                chinese = next(i for i in range(app.language_menu.index("end") + 1)
                               if app.language_menu.entrycget(i, "label") == "繁體中文")
                app.language_menu.invoke(chinese)
                root.update()
                self.assertEqual(other.cget("text"), "繁體中文")
                self.assertEqual(app.app_event_status_label.cget("text"), "文字更新失敗")
                failed = next(record for record in app.rounds.app_event_records()
                              if record["localized_message"]["message_id"] ==
                              "app.language.refresh_failed")
                self.assertEqual(failed["localized_message"]["en"],
                                 "A window could not refresh its text.")
                self.assertEqual(failed["localized_message"]["zh-TW"],
                                 "有視窗的文字更新失敗。")
                self.assertEqual(failed["diagnostic"], "主畫面: refresh failed")
                self.assertNotIn("round_id", failed)
                self.assertTrue(app.app_events.flush(timeout=5))
                rebuilt = read_app_event_store(app.app_events.path)
                disk_failure = next(record for record in rebuilt["events"]
                                    if record["event_id"] == failed["event_id"])
                self.assertEqual(disk_failure["localized_message"],
                                 failed["localized_message"])
                self.assertEqual(disk_failure["diagnostic"], "主畫面: refresh failed")
                # Use the real App diagnostic entry and select the persisted event.
                app.app_diagnostics_button.event_generate(
                    "<ButtonPress-1>", x=app.app_diagnostics_button.winfo_width() // 2,
                    y=app.app_diagnostics_button.winfo_height() // 2)
                app.app_diagnostics_button.event_generate(
                    "<ButtonRelease-1>", x=app.app_diagnostics_button.winfo_width() // 2,
                    y=app.app_diagnostics_button.winfo_height() // 2)
                root.update()
                records = app.rounds.app_event_records()
                failed_index = next(index for index, record in enumerate(records)
                                    if record["event_id"] == failed["event_id"])
                app.app_diagnostics_list.selection_clear(0, "end")
                app.app_diagnostics_list.selection_set(failed_index)
                app.app_diagnostics_list.event_generate("<<ListboxSelect>>")
                root.update()
                self.assertIn("主畫面: refresh failed",
                              app.app_diagnostics_detail.get("1.0", "end-1c"))
                self.assertIn("app.language.refresh_failed",
                              app.app_diagnostics_detail.get("1.0", "end-1c"))
            fail_refresh[0] = True
            self.diagnostics_language_retry(app).invoke()
            root.update()
            self.assertEqual(str(self.diagnostics_language_retry(app).cget("state")), "normal")
            self.assertEqual(app.app_event_status_label.cget("text"), "文字更新失敗")
            self.assertEqual(app.project_label.cget("text"), "專案")
            self.assertEqual(failed_window.cget("text"), "Not translated")
            failed_window.destroy()
            app._language_refresh_notifications.notify()
            root.update()
            self.assertEqual(str(self.diagnostics_language_retry(app).cget("state")), "disabled")
            self.assertNotEqual(app.app_event_status_label.cget("text"), "文字更新失敗")
            unregister()
            unregister_failed()
        finally:
            root.destroy()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_open_notice_receives_language_refresh_and_keeps_modal_acknowledgement(self):
        root = tk.Tk()
        root.deiconify()
        app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey)
        observed = []

        def find_notice():
            pending = list(root.winfo_children())
            while pending:
                widget = pending.pop()
                if isinstance(widget, tk.Toplevel) and widget is not root:
                    if widget.title() in {"Language Preference Not Saved", "語言設定未保存"}:
                        return widget
                pending.extend(widget.winfo_children())
            return None

        def switch_notice_language():
            notice = find_notice()
            try:
                self.assertIsNotNone(notice)
                body = next(widget for widget in notice.winfo_children()
                            if isinstance(widget, ttk.Frame)).winfo_children()
                text = next(widget for widget in body if isinstance(widget, tk.Text))
                acknowledge = next(widget for widget in notice.winfo_children()
                                   if isinstance(widget, ttk.Button))
                acknowledge.event_generate("<Enter>")
                deadline = time.monotonic() + 2
                hint_window = None
                while time.monotonic() < deadline:
                    root.update()
                    hint_window = next((child for child in notice.winfo_children()
                                        if isinstance(child, tk.Toplevel) and
                                        child.overrideredirect()), None)
                    if hint_window is not None:
                        break
                    time.sleep(.01)
                self.assertIsNotNone(hint_window)
                self.assertIn("Acknowledge this message",
                              hint_window.winfo_children()[0].cget("text"))
                self.assertIs(root.focus_get(), acknowledge)
                capture_native_window_with_hint(
                    notice, "st5-notice-dismiss-hint-en.png")
                app.current_language = TRADITIONAL_CHINESE
                app._language_refresh_notifications.notify()
                root.update_idletasks()
                observed.extend((notice.title(), text.get("1.0", "end-1c"),
                                 acknowledge.cget("text")))
                self.assertTrue(hint_window.winfo_exists())
                self.assertIn("確認並關閉這則訊息",
                              hint_window.winfo_children()[0].cget("text"))
                capture_native_window_with_hint(
                    notice, "st5-notice-dismiss-hint-zh-TW.png")
                acknowledge.invoke()
            except Exception as error:
                observed.append(error)
                if notice is not None and notice.winfo_exists():
                    notice.destroy()

        try:
            root.after(100, switch_notice_language)
            root.after(1500, lambda: (find_notice().destroy()
                                      if find_notice() is not None and find_notice().winfo_exists()
                                      else None))
            app._show_notice("language.save_failed_title", "language.save_failed",
                             {"reason": "disk full"})
            self.assertEqual(observed[0], "語言設定未保存")
            self.assertIn("disk full", observed[1])
            self.assertEqual(observed[2], "確定")
            self.assertIsNone(root.grab_current())
        finally:
            root.destroy()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_hm5_long_notice_stays_scrollable_and_fixed_across_languages(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.deiconify()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey,
                session_root=Path(temporary) / "sessions",
                app_event_path=Path(temporary) / "app-events.json")
            captures = {}
            callback_errors = []

            def find_notice():
                return next((child for child in root.winfo_children()
                             if isinstance(child, tk.Toplevel)), None)

            def inspect_and_switch_language():
                notice = find_notice()
                try:
                    self.assertIsNotNone(notice)
                    body = next(widget for widget in notice.winfo_children()
                                if isinstance(widget, ttk.Frame)).winfo_children()[0]
                    acknowledge = next(widget for widget in notice.winfo_children()
                                       if isinstance(widget, ttk.Button))
                    self.assertIsInstance(body, tk.Text)
                    self.assertEqual(body.cget("background"), LIGHT_BACKGROUND)
                    self.assertEqual(int(body.cget("borderwidth")), 1)
                    self.assertEqual(body.cget("relief"), "solid")
                    self.assertEqual(body.cget("state"), "disabled")
                    self.assertIs(root.grab_current(), notice)
                    self.assertIs(root.focus_get(), acknowledge)
                    captures["en"] = capture_tk_window_evidence(
                        notice, "general-notice", "en", {
                            "body": body, "acknowledge": acknowledge,
                        })
                    app.current_language = TRADITIONAL_CHINESE
                    app._language_refresh_notifications.notify()
                    root.update()
                    self.assertTrue(notice.winfo_exists())
                    self.assertEqual(notice.title(), "語言設定未保存")
                    self.assertIn("確定", acknowledge.cget("text"))
                    self.assertIn("diagnostic line 159", body.get("1.0", "end-1c"))
                    captures["zh-TW"] = capture_tk_window_evidence(
                        notice, "general-notice", "zh-TW", {
                            "body": body, "acknowledge": acknowledge,
                        })
                    self.assertEqual(captures["en"]["size"],
                                     captures["zh-TW"]["size"])
                    self.assertEqual(captures["en"]["controls"],
                                     captures["zh-TW"]["controls"])
                    notice.event_generate("<Escape>")
                except Exception as error:
                    callback_errors.append(traceback.format_exc())
                    if notice is not None and notice.winfo_exists():
                        notice.destroy()

            try:
                diagnostic = "\n".join(
                    "diagnostic line {} — source failure detail".format(index)
                    for index in range(160))
                root.after(100, inspect_and_switch_language)
                root.after(15000, lambda: (find_notice().destroy()
                                          if find_notice() is not None else None))
                app._show_notice("language.save_failed_title", "language.save_failed",
                                 {"reason": diagnostic}, diagnostic=diagnostic)
                self.assertFalse(callback_errors, callback_errors)
                self.assertIsNone(find_notice())
                self.assertIsNone(root.grab_current())
                write_tk_bounds_evidence("general_notice", captures)
            finally:
                if root.winfo_exists():
                    app.hotkey.close()
                    root.destroy()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_notice_escape_hidden_reopen_and_current_language_lifecycle(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.deiconify()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey,
                session_root=Path(temporary) / "sessions",
                app_event_path=Path(temporary) / "app-events.json")
            root.focus_force()
            app.settings_button.focus_force()
            root.update()
            original_focus = root.focus_get()
            observations = []
            second_escape_kept_notice = []
            reopened_modal_restored = []
            reopened_button_focused = []

            def find_notice():
                for child in root.winfo_children():
                    if isinstance(child, tk.Toplevel) and child is not root:
                        return child
                return None

            def close_first_notice():
                notice = find_notice()
                observations.append((notice is not None, root.grab_current() is notice))
                notice.event_generate("<Escape>")

            try:
                root.after(100, close_first_notice)
                app._show_notice("language.save_failed_title", "language.save_failed",
                                 {"reason": "first notice"})
                root.update()
                self.assertIsNone(find_notice())
                self.assertIsNone(root.grab_current())
                if original_focus is not None:
                    self.assertTrue(original_focus.winfo_exists())

                app.current_language = TRADITIONAL_CHINESE
                def hide_refresh_show_and_close():
                    notice = find_notice()
                    if notice is None:
                        observations.append(("missing-notice", None))
                        return
                    identity = str(notice)
                    notice.withdraw()
                    app.current_language = ENGLISH
                    app._language_refresh_notifications.notify()
                    root.update()
                    notice.deiconify()
                    root.update()
                    observations.append((identity == str(notice), notice.title()))
                    reopened_modal_restored.append(root.grab_current() is notice)
                    acknowledge = next(widget for widget in notice.winfo_children()
                                       if isinstance(widget, ttk.Button))
                    reopened_button_focused.append(root.focus_get() is acknowledge)
                    acknowledge.event_generate("<Escape>")
                    second_escape_kept_notice.append(bool(notice.winfo_exists()))
                    if notice.winfo_exists():
                        notice.destroy()

                def close_notice_if_escape_did_not():
                    notice = find_notice()
                    if notice is not None:
                        observations.append(("escape-timeout", notice.title()))
                        notice.destroy()

                root.after(100, hide_refresh_show_and_close)
                root.after(2000, close_notice_if_escape_did_not)
                app._show_notice("language.save_failed_title", "language.save_failed",
                                 {"reason": "reopened notice"})
                root.update()
                self.assertIsNone(find_notice())
                self.assertIsNone(root.grab_current())
                self.assertEqual(len(app._language_refresh_failures), 0)
                self.assertEqual(reopened_modal_restored, [True])
                self.assertEqual(reopened_button_focused, [True])
                self.assertEqual(second_escape_kept_notice, [False])
                self.assertEqual(observations,
                                 [(True, True), (True, "Language Preference Not Saved")])
            finally:
                try:
                    app.close()
                    deadline = time.monotonic() + 5
                    while (time.monotonic() < deadline and root.winfo_exists() and
                           app.rounds.close_status().status not in {"complete", "failed"}):
                        root.update()
                        time.sleep(.01)
                finally:
                    if root.winfo_exists():
                        root.destroy()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_language_refresh_diagnostic_store_failure_is_visible_and_retryable(self):
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
                self.fail("Timed out waiting for language-refresh diagnostic persistence")

            try:
                root.update()
                pump_until(lambda: app.rounds.app_event_status().complete)

                def fail_app_store(_path, _content):
                    raise OSError("diagnostic journal unavailable")

                with patch("app_event_store._atomic_replace", side_effect=fail_app_store), \
                        patch.object(app.project_label, "configure",
                                     side_effect=RuntimeError("main text refresh failed")):
                    root.update()
                    chinese = next(
                        index for index in range(app.language_menu.index("end") + 1)
                        if app.language_menu.entrycget(index, "label") == "繁體中文")
                    app.language_menu.invoke(chinese)
                    pump_until(lambda: app.rounds.app_event_status().status == "failed")

                records = app.rounds.app_event_records()
                diagnostic = next(item for item in records
                                  if item["localized_message"]["message_id"] ==
                                  "app.language.refresh_failed")
                self.assertEqual(diagnostic["localized_message"]["en"],
                                 "A window could not refresh its text.")
                self.assertEqual(diagnostic["localized_message"]["zh-TW"],
                                 "有視窗的文字更新失敗。")
                self.assertEqual(diagnostic["diagnostic"],
                                 "主畫面: main text refresh failed")
                self.assertNotIn("round_id", diagnostic)
                self.assertEqual(app.current_language, TRADITIONAL_CHINESE)
                self.assertEqual(app.app_event_status_label.cget("text"), "文字更新失敗")
                self.assertIn("diagnostic journal unavailable",
                              app.rounds.app_event_status().error)

                app.app_diagnostics_button.event_generate(
                    "<ButtonPress-1>", x=app.app_diagnostics_button.winfo_width() // 2,
                    y=app.app_diagnostics_button.winfo_height() // 2)
                app.app_diagnostics_button.event_generate(
                    "<ButtonRelease-1>", x=app.app_diagnostics_button.winfo_width() // 2,
                    y=app.app_diagnostics_button.winfo_height() // 2)
                root.update()
                self.assertIsNotNone(app.app_diagnostics_window)
                self.assertIn("diagnostic journal unavailable",
                              app.app_diagnostics_history.cget("text"))

                app.app_diagnostics_retry_button.event_generate(
                    "<ButtonPress-1>",
                    x=app.app_diagnostics_retry_button.winfo_width() // 2,
                    y=app.app_diagnostics_retry_button.winfo_height() // 2)
                app.app_diagnostics_retry_button.event_generate(
                    "<ButtonRelease-1>",
                    x=app.app_diagnostics_retry_button.winfo_width() // 2,
                    y=app.app_diagnostics_retry_button.winfo_height() // 2)
                pump_until(lambda: app.rounds.app_event_status().complete)
                rebuilt = read_app_event_store(app_path)
                persisted = next(item for item in rebuilt["events"]
                                 if item["event_id"] == diagnostic["event_id"])
                self.assertEqual(persisted["localized_message"],
                                 diagnostic["localized_message"])
                self.assertEqual(persisted["diagnostic"], diagnostic["diagnostic"])
                self.assertEqual(persisted["sequence"], diagnostic["sequence"])
            finally:
                try:
                    if app.app_diagnostics_window and app.app_diagnostics_window.winfo_exists():
                        app.app_diagnostics_window.destroy()
                    app.close()
                    deadline = time.monotonic() + 5
                    while time.monotonic() < deadline and root.winfo_exists():
                        root.update()
                        if app.rounds.close_status().status in {"complete", "failed"}:
                            break
                        time.sleep(.01)
                finally:
                    if root.winfo_exists():
                        app.hotkey.close()
                        app.app_events.stop()
                        root.destroy()

    @classmethod
    def setUpClass(cls):
        # Tk on macOS uses a process-wide event queue. Keep one interpreter
        # alive; each App still gets a real, independently destroyed window.
        cls._desktop_root = tk.Tk()
        cls._pointer_before_suite = cls._desktop_root.winfo_pointerxy()
        cls._desktop_root.geometry("1x1+0+0")
        cls._desktop_root.update()
        cls._desktop_root.tk.eval(
            "set ::b518_test_bgerrors {}; "
            "proc bgerror {message} {lappend ::b518_test_bgerrors $message}")

    @classmethod
    def tearDownClass(cls):
        cls._desktop_root.destroy()
        cls._desktop_root = None
        if Quartz is not None:
            Quartz.CGWarpMouseCursorPosition(cls._pointer_before_suite)
        gc.collect()

    def setUp(self):
        # A prior native-input test can leave the real cursor over a new
        # App's controls, competing with this test's synthetic focus/Enter.
        if Quartz is not None and os.environ.get("B518_MANUAL_HOVER") != "1":
            self.assertEqual(Quartz.CGWarpMouseCursorPosition((1, 1)), 0)
        self._async_errors = []
        errors = self._async_errors
        previous_hook = sys.unraisablehook

        def record_unraisable(event):
            errors.append("Unraisable: {}".format(event.exc_value))
            previous_hook(event)

        def record_callback(kind, value, trace):
            errors.append("".join(traceback.format_exception(kind, value, trace)))

        sys.unraisablehook = record_unraisable
        self._desktop_root.report_callback_exception = record_callback
        self.addCleanup(setattr, sys, "unraisablehook", previous_hook)
        self.addCleanup(self._assert_no_async_errors)
        self.addCleanup(gc.collect)
        self._test_windows = []
        self._after_before_test = set(self._desktop_root.tk.call("after", "info"))

        def create_window():
            window = tk.Toplevel(self._desktop_root)
            self._test_windows.append(window)
            return window

        root_patcher = patch("tkinter.Tk", side_effect=create_window)
        root_patcher.start()
        self.addCleanup(root_patcher.stop)
        self.addCleanup(self._destroy_test_windows)
        self._isolated_app_root = TemporaryDirectory()
        self._app_event_stores = []
        self._app_round_coordinators = []
        app_root = Path(self._isolated_app_root.name)
        app_root_patcher = patch("b518_log_solution.APP_ROOT", app_root)
        preferences_patcher = patch("b518_log_solution.PREFS_PATH", app_root / "preferences.json")
        real_store = AppEventStore

        def create_store(*args, **kwargs):
            store = real_store(*args, **kwargs)
            self._app_event_stores.append(store)
            return store

        real_coordinator = RoundCoordinator

        real_coordinator_init = real_coordinator.__init__

        def initialize_coordinator(coordinator, *args, **kwargs):
            real_coordinator_init(coordinator, *args, **kwargs)
            self._app_round_coordinators.append(coordinator)

        store_patcher = patch("b518_log_solution.AppEventStore", side_effect=create_store)
        coordinator_patcher = patch.object(
            real_coordinator, "__init__", initialize_coordinator)
        app_root_patcher.start()
        preferences_patcher.start()
        store_patcher.start()
        coordinator_patcher.start()
        self.addCleanup(app_root_patcher.stop)
        self.addCleanup(preferences_patcher.stop)
        self.addCleanup(store_patcher.stop)
        self.addCleanup(coordinator_patcher.stop)
        self.addCleanup(self._isolated_app_root.cleanup)
        self.addCleanup(self._settle_app_event_writes)

    def _assert_no_async_errors(self):
        self.assertEqual(self._async_errors, [], "Background/Tk callback errors must fail the test")
        tcl_errors = self._desktop_root.tk.call("set", "::b518_test_bgerrors")
        self._desktop_root.tk.call("set", "::b518_test_bgerrors", "")
        self.assertEqual(tcl_errors, "", "Tcl after errors must fail the test")

    def _destroy_test_windows(self):
        # Timers scheduled by a test itself are also its responsibility. App
        # timers are checked independently by the destruction regressions.
        pending = set(self._desktop_root.tk.call("after", "info")) - self._after_before_test
        owners = {}

        def remember_commands(widget):
            for command in widget._tclCommands or ():
                owners[command] = widget
            for child in widget.winfo_children():
                remember_commands(child)

        remember_commands(self._desktop_root)
        for after_id in pending:
            script = self._desktop_root.tk.call("after", "info", after_id)[0]
            command = self._desktop_root.tk.splitlist(script)[0]
            owner = owners.get(command)
            if owner is not None:
                owner.after_cancel(after_id)
            else:
                # Raw Tcl timers do not own a Python-registered Tcl command.
                self._desktop_root.tk.call("after", "cancel", after_id)
        for window in self._test_windows:
            if window.winfo_exists():
                window.destroy()
        self._test_windows.clear()
        self._desktop_root.update_idletasks()

    def _settle_app_event_writes(self):
        for coordinator in self._app_round_coordinators:
            # Cancel test-only close attempts waiting on intentional unresolved
            # operator work, and stop all monitor loops before deleting data.
            coordinator.cancel_close()
            coordinator.stop()
            pending_states = {"running"}
            if coordinator._retention_next_due is not None:
                pending_states.add("idle")
            deadline = time.monotonic() + 5
            while (coordinator.retention_cleanup_status().status in pending_states and
                   time.monotonic() < deadline):
                time.sleep(.01)
            self.assertNotIn(coordinator.retention_cleanup_status().status, pending_states,
                             "Background cleanup must finish before temporary data cleanup")
            self.wait_for(lambda: not (
                coordinator._close_worker_active or coordinator._archive_worker_active or
                coordinator._retention_worker_active), timeout=5)
            with coordinator._lock:
                rounds = set(coordinator._tracked_rounds.values())
                if coordinator._current is not None:
                    rounds.add(coordinator._current)
            for round_ in rounds:
                if round_._run_thread is not None:
                    round_._run_thread.join(5)
                    self.assertFalse(round_._run_thread.is_alive(),
                                     "Monitor worker must exit before temporary data cleanup")
        for store in self._app_event_stores:
            deadline = time.monotonic() + 5
            while store.status().status == "saving" and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertNotEqual(store.status().status, "saving",
                                "App event write must finish before temporary data cleanup")
            store.stop()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1", "requires desktop Tk")
    def test_native_capture_selects_current_window_with_duplicate_title(self):
        first = tk.Tk()
        second = tk.Tk()
        first.title("Duplicate capture title")
        second.title("Duplicate capture title")
        first.geometry("220x150+30+30")
        second.geometry("320x210+300+30")
        first.update()
        second.update()
        # Emulate the observed AppKit order deterministically; both entries
        # remain real NSWindows and both rendered caches remain real NSViews.
        ordered = sorted(NSApplication.sharedApplication().windows(),
                         key=lambda item: item.contentView().bounds().size.width)
        application = SimpleNamespace(windows=lambda: ordered)
        with TemporaryDirectory() as temporary, patch(
                "AppKit.NSApplication", SimpleNamespace(sharedApplication=lambda: application)):
            evidence = capture_tk_content_view_evidence(
                second, "duplicate-title", {"target": second}, output_dir=temporary)
            self.assertEqual(evidence["size"], [320, 210])
            self.assertEqual(evidence["image_pixels"], {"width": 640, "height": 420})
        self.assertEqual(first.title(), "Duplicate capture title")
        self.assertEqual(second.title(), "Duplicate capture title")

    def test_fixture_cleanup_cancels_nested_widget_timer_without_double_delete(self):
        root = tk.Tk()
        button = ttk.Button(root)
        timer = button.after(60000, lambda: None)
        self._destroy_test_windows()
        self.assertFalse(root.winfo_exists())
        self.assertNotIn(timer, self._desktop_root.tk.call("after", "info"))

    def test_destroy_cancels_owned_timers_without_cancelling_embedding_timer(self):
        root = tk.Tk()
        root.withdraw()
        app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey)
        external = root.after(60000, lambda: None)
        try:
            app._schedule_ui(300, app._show_startup_warning)
            app._schedule_ui("idle", app._set_initial_conflict_sash)
            app._schedule_close_poll(1)
            first_poll = app._close_after_id
            app._schedule_close_poll(2)
            self.assertNotIn(first_poll, root.tk.call("after", "info"))
            self.assertGreaterEqual(len(app._after_ids), 3)
            root.destroy()
            self.assertEqual(root.tk.call("after", "info"), (external,))
            self.assertEqual(app._after_ids, set())
            self.assertIsNone(app.root)
            self.assertIsNone(app.project)
            self.assertTrue(app.hotkey.closed)
            app._drain_events()  # A late dispatch cannot touch the dead interpreter.
        finally:
            root.after_cancel(external)
            if not app._ui_destroyed:
                root.destroy()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_real_tk_reads_mixed_cleanup_reason_ledger_and_keeps_raw_evidence_read_only(self):
        app_root = Path(self._isolated_app_root.name)
        ledger_path = app_root / "round-retention-ledger.json"
        reason = {
            "version": 1,
            "message_id": "app.settings.retention.reason.archive_read_failed",
            "parameters": {"diagnostic": "archive disk fault"},
            "en": "Archive metadata could not be read: archive disk fault",
            "zh-TW": "無法讀取封存資訊：archive disk fault",
            "diagnostic": "raw archive stack remains unchanged",
        }
        app_reason = {
            "version": 1,
            "message_id": "app.settings.retention.reason.app_events_pending",
            "parameters": {},
            "en": "App event saves are pending or completeness is not confirmed.",
            "zh-TW": "App 事件仍有待補存，或完整保存狀態尚未確認。",
            "diagnostic": "pending App event raw diagnostic",
        }
        deleted_reason = {
            "version": 1,
            "message_id": "app.settings.retention.reason.deleted",
            "parameters": {},
            "en": "Trusted round records were completely deleted.",
            "zh-TW": "已完整刪除可信輪次資料。",
        }
        unknown_reason = {
            "version": 1,
            "message_id": "internal.cleanup.future_reason",
            "parameters": {"detail": "captured future parameter"},
            "en": "Captured future cleanup reason",
            "zh-TW": "未來原因的原始繁中",
            "diagnostic": "future cleanup raw diagnostic",
        }
        old_summary = round_retention.RetentionSummary(
            "run-c1", "2026-10-12T08:00:00+08:00", "2026-10-12T08:00:01+08:00",
            30, "controlled-fixture", "failed",
            results=(round_retention.RetentionRoundResult(
                "round-success", "deleted", "已完整刪除可信輪次資料", deleted_reason),
                round_retention.RetentionRoundResult(
                "round-c1", "failed", "封存資訊無法讀取：legacy disk fault", reason),
                round_retention.RetentionRoundResult(
                    "round-legacy", "skipped", "封存資訊版本未知"),
                round_retention.RetentionRoundResult(
                    "round-future-id", "skipped", "Captured future cleanup reason",
                    unknown_reason)),
            message="legacy summary text",
            app_events=round_retention.RetentionAppEventResult(
                "failed", 0, 1, 1, "custom App event reason", app_reason),
            message_reason=reason,
        )
        ledger_path.write_text(json.dumps({
            "schema_version": round_retention.LEDGER_SCHEMA_VERSION,
            "runs": [old_summary.to_record()],
            "active_plans": {"round-pending": {
                "round_id": "round-pending", "paths": ["sessions/pending"],
                "path_order": ["sessions/pending"], "next_index": 0,
                "archived_at": "2026-10-01T08:00:00+08:00",
            }},
        }, ensure_ascii=False), encoding="utf-8")
        original_ledger = ledger_path.read_bytes()
        root = tk.Tk()
        root.deiconify()
        with patch.object(RoundCoordinator, "start_retention_schedule", return_value=None):
            app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey,
                                     session_root=app_root / "sessions",
                                     app_event_path=app_root / "app-events.json")
        try:
            app.open_settings()
            app.settings_notebook.select(2)
            root.update()
            english_detail = app.retention_cleanup_status.get()
            self.assertIn("Archive metadata could not be read: archive disk fault", english_detail)
            self.assertIn("Original cleanup reason", english_detail)
            self.assertIn("raw archive stack remains unchanged", english_detail)
            self.assertIn("round-success", english_detail)
            self.assertIn("Trusted round records were completely deleted", english_detail)
            self.assertIn("round-c1", english_detail)
            self.assertIn("App event saves are pending", english_detail)
            self.assertIn("The archive metadata version is not supported", english_detail)
            self.assertIn("Cleanup reason is not recognized.", english_detail)
            self.assertIn("future cleanup raw diagnostic", english_detail)
            self.assertNotIn("app.settings.retention.reason.archive_read_failed", english_detail)

            self.set_language_for_test_setup(app, root, TRADITIONAL_CHINESE)
            chinese_detail = app.retention_cleanup_status.get()
            self.assertIn("無法讀取封存資訊：archive disk fault", chinese_detail)
            self.assertIn("原始清理原因", chinese_detail)
            self.assertIn("原始診斷：raw archive stack remains unchanged", chinese_detail)
            self.assertIn("round-success", chinese_detail)
            self.assertIn("已完整刪除可信輪次資料。", chinese_detail)
            self.assertIn("App 事件仍有待補存", chinese_detail)
            self.assertIn("封存資訊版本不受支援", chinese_detail)
            self.assertIn("無法辨識此清理原因。", chinese_detail)
            self.assertIn("future cleanup raw diagnostic", chinese_detail)
            self.assertNotIn("app.settings.retention.reason.archive_read_failed", chinese_detail)
            self.assertNotIn("internal.cleanup.future_reason", chinese_detail)
            summary = app.rounds.retention_cleanup_summaries()[0]
            self.assertEqual(
                next(item for item in summary.results if item.round_id == "round-c1").round_id,
                "round-c1")
            self.assertEqual(
                next(item for item in summary.results if item.round_id == "round-success")
                .reason_message,
                deleted_reason)
            self.assertEqual(ledger_path.read_bytes(), original_ledger)
        finally:
            active_failure = sys.exc_info()[0] is not None
            app.close()
            deadline = time.monotonic() + 5
            while (time.monotonic() < deadline and root.winfo_exists() and
                   app.rounds.close_status().status not in {"complete", "failed"}):
                root.update()
                time.sleep(0.01)
            close_state = app.rounds.close_status().status
            try:
                if close_state != "complete" and not active_failure:
                    self.fail("App close must complete before the cleanup ledger is removed; got {}"
                              .format(close_state))
            finally:
                if root.winfo_exists():
                    app.hotkey.close()
                    root.destroy()

    def test_destroyed_ui_is_safe_when_next_worker_collects_cycles(self):
        # A wrong-thread Tcl interpreter deletion aborts the process; keep this
        # regression in a subprocess so a failure is reported by unittest.
        script = textwrap.dedent("""\
            import gc, sys, threading, time, tkinter as tk, weakref
            from pathlib import Path
            from tempfile import TemporaryDirectory
            from unittest.mock import patch
            from b518_log_solution import B518LogSolutionApp
            from test_log_solution_ui import FakeHotkey
            gc.disable()
            errors = []
            sys.unraisablehook = lambda event: errors.append(str(event.exc_value))
            with TemporaryDirectory() as tmp, patch(
                    'b518_log_solution.PREFS_PATH', Path(tmp) / 'preferences.json'):
                root = tk.Tk()
                root.withdraw()
                app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey,
                    session_root=Path(tmp) / 'sessions',
                    app_event_path=Path(tmp) / 'events.json')
                coordinator = app.rounds
                app.open_settings()
                app._schedule_close_poll(1)
                assert app.app_events.flush(timeout=5)
                app.app_events.stop()
                # Keep a Python App cycle to collect on the worker deliberately.
                app.cycle = app
                app_ref, root_ref = weakref.ref(app), weakref.ref(root)
                root.destroy()
                assert app._language_refresh_notifications is None
                assert app._main_language_receiver is None
                assert not root.tk.call('after', 'info')
                del app, root
                assert root_ref() is None, 'Destroyed interpreter is still retained'
                worker = threading.Thread(target=gc.collect)
                worker.start()
                worker.join(10)
                assert not worker.is_alive(), 'Worker collection hung'
                assert app_ref() is None, 'App cycle was not collected'
                assert not errors, errors
                coordinator.request_close()
                deadline = time.monotonic() + 10
                while coordinator.close_status().status != 'complete' and time.monotonic() < deadline:
                    time.sleep(.01)
                assert coordinator.close_status().status == 'complete', coordinator.close_status()
        """)
        environment = dict(os.environ)
        environment["PYTHONPATH"] = os.pathsep.join(
            str(Path(__file__).resolve().parents[1] / directory)
            for directory in ("src", "tests"))
        completed = subprocess.run(
            [sys.executable, "-X", "faulthandler", "-c", script],
            env=environment, capture_output=True, text=True, timeout=30)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(completed.stderr, "")

    def wait_for(self, predicate, timeout=3):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.01)
        self.fail("Timed out waiting for asynchronous monitor preparation")

    def wait_for_ui(self, root, predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            root.update()
            if predicate():
                return
            time.sleep(.01)
        self.fail("Timed out waiting for the Tk presentation")

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
                root.update()
                chinese_index = next(
                    index for index in range(app.language_menu.index("end") + 1)
                    if app.language_menu.entrycget(index, "label") == "繁體中文")
                with patch("machine_profiles._atomic_write_text", side_effect=OSError("preference disk full")), \
                        patch("b518_log_solution.show_notice"):
                    app.language_menu.invoke(chinese_index)
                root.update()
                self.assertEqual(app.current_language, TRADITIONAL_CHINESE)
                self.assertEqual(app.language_choice.get(), TRADITIONAL_CHINESE)
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
                    root.update()
                    chinese_index = next(
                        index for index in range(app.language_menu.index("end") + 1)
                        if app.language_menu.entrycget(index, "label") == "繁體中文")
                    with patch("machine_profiles._atomic_write_text",
                               side_effect=OSError("preference disk full")), \
                            patch("b518_log_solution.show_notice"):
                        app.language_menu.invoke(chinese_index)
                    event_record = next(item for item in app.rounds.app_event_records()
                                        if item["localized_message"]["message_id"] ==
                                        "app.language.preference_save_failed")
                    pump_until(lambda: app.rounds.app_event_status().status == "failed")
                    app.close()
                    pump_until(lambda: app.rounds.close_status().status == "failed")
                    pump_until(lambda: "app journal unavailable" in
                               app._close_diagnostic_text.get("1.0", "end-1c"))
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
                with patch("b518_log_solution.show_notice") as warning:
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
                        patch("b518_log_solution.show_notice"):
                    click(import_button)
                self.assertEqual(app.profiles.to_dict(), original_catalog)
                self.assertEqual((app.project.get(), app.station.get()), original_selection)
                self.assertIn("saved configuration remains unchanged",
                              app.profile_editor_status.get())
                with patch("b518_log_solution.filedialog.asksaveasfilename",
                           return_value=str(Path(temporary) / "missing" / "export.json")), \
                        patch("b518_log_solution.show_notice"):
                    click(export_button)
                self.assertIn("could not be exported", app.profile_editor_status.get())
                root.update()
                chinese_index = next(
                    index for index in range(app.language_menu.index("end") + 1)
                    if app.language_menu.entrycget(index, "label") == "繁體中文"
                )
                app.language_menu.invoke(chinese_index)
                root.update()
                self.assertIn("無法匯出配置", app.profile_editor_status.get())
                self.assertIn("No such file or directory", app.profile_editor_status.get())
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
                        patch("b518_log_solution.show_notice"), \
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
    def test_ls6_real_tk_heartbeat_cycles_blocks_tracks_states_and_cleans_up(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.deiconify()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey,
                session_root=Path(temporary) / "sessions",
                app_event_path=Path(temporary) / "app-events.json",
            )
            try:
                def rendered_cells():
                    items = app.kvm_heartbeat_marker.find_withtag("heartbeat-cell")
                    self.assertEqual(len(items), 4)
                    colours = tuple(app.kvm_heartbeat_marker.itemcget(item, "fill")
                                    for item in items)
                    self.assertTrue(set(colours) <= {"#000000", "#ffffff"})
                    return tuple(
                        tuple(colours[row * 2 + column] == "#000000"
                              for column in range(2))
                        for row in range(2)
                    )

                initial_state = app._heartbeat_state
                initial_pattern = rendered_cells()
                self.assertEqual(initial_state, 0)
                self.assertEqual(initial_pattern, HEARTBEAT_PATTERNS[0])
                self.wait_for_ui(root, lambda: root.winfo_ismapped() and
                                 app.kvm_heartbeat_marker.winfo_ismapped())
                self.assertEqual(HEARTBEAT_INTERVAL_MS, 500)
                self.assertEqual((app.kvm_state_marker.winfo_x(),
                                  app.kvm_state_marker.winfo_y(),
                                  app.kvm_state_marker.winfo_width(),
                                  app.kvm_state_marker.winfo_height()), (250, 0, 26, 26))
                self.assertEqual((app.kvm_heartbeat_marker.winfo_x(),
                                  app.kvm_heartbeat_marker.winfo_y(),
                                  app.kvm_heartbeat_marker.winfo_width(),
                                  app.kvm_heartbeat_marker.winfo_height()), (278, 0, 26, 26))
                self.assertEqual((app.kvm_locator_left.winfo_x(),
                                  app.kvm_locator_right.winfo_x()), (0, 320))
                self.assertEqual(app.kvm_result_blocks[1].winfo_y(), 34)

                if os.environ.get("B518_TK_EVIDENCE_DIR"):
                    capture = capture_tk_window_evidence(
                        root, "ls6-heartbeat-state-00", "en", {
                            "kvm": app.kvm_results,
                            "state_marker": app.kvm_state_marker,
                            "heartbeat_marker": app.kvm_heartbeat_marker,
                            "left_locator": app.kvm_locator_left,
                            "right_locator": app.kvm_locator_right,
                            "first_result": app.kvm_result_blocks[1],
                        })
                else:
                    capture = {"geometry": root.geometry()}

                self.wait_for_ui(root, lambda: app._heartbeat_state != initial_state,
                                 timeout=HEARTBEAT_INTERVAL_MS / 1000 + .8)
                cycle_start_state = app._heartbeat_state
                expected_cycle_states = [
                    (cycle_start_state + offset) % len(HEARTBEAT_PATTERNS)
                    for offset in range(1, len(HEARTBEAT_PATTERNS) + 1)
                ]
                observed_states = [initial_state, cycle_start_state]
                observed_patterns = [initial_pattern, rendered_cells()]
                transition_times = [time.monotonic()]
                expected_index = 0
                deadline = time.monotonic() + 10
                while (expected_index < len(expected_cycle_states) and
                       time.monotonic() < deadline):
                    root.update()
                    current = app._heartbeat_state
                    if current == expected_cycle_states[expected_index]:
                        observed_states.append(current)
                        observed_patterns.append(rendered_cells())
                        transition_times.append(time.monotonic())
                        expected_index += 1
                    time.sleep(.005)
                self.assertEqual(observed_states, [initial_state, cycle_start_state] +
                                 expected_cycle_states)
                self.assertEqual(observed_patterns,
                                 [HEARTBEAT_PATTERNS[state]
                                  for state in observed_states])
                intervals = [later - earlier for earlier, later in
                             zip(transition_times, transition_times[1:])]
                self.assertEqual(len(intervals), 16)
                self.assertTrue(all(.35 <= interval <= 1.25 for interval in intervals),
                                intervals)

                state_samples = (
                    (RoundState.READY, False, "", (), MarkerState.STANDBY),
                    (RoundState.PREPARING, False, "", (), MarkerState.PREPARING),
                    (RoundState.RUNNING, False, "", (), MarkerState.MONITORING),
                    (RoundState.AWAITING_REVIEW, False, "", (), MarkerState.REVIEW),
                    (RoundState.COMPLETED, True, "", (), MarkerState.COMPLETE),
                    (RoundState.STOPPED, True, "manual_stop", (),
                     MarkerState.MANUAL_STOP_COMPLETE),
                    (RoundState.STOPPED, False, "start_failed", (), MarkerState.STANDBY),
                )
                for round_state, available, reason, conflicts, expected_state in state_samples:
                    snapshot = RoundSnapshot(
                        round_id="ls6-state-sample", station="FCT", state=round_state,
                        results=(), result_available=available, event_sequence=0, events=(),
                        collection_stopped=round_state in {RoundState.COMPLETED,
                                                           RoundState.STOPPED},
                        completion_reason=reason, pending_conflicts=conflicts,
                        round_alarm=None, cancellation_available=False)
                    before = app._heartbeat_state
                    self.assertEqual(app._render_state_marker(snapshot), expected_state)
                    self.assertEqual(app._heartbeat_state, before)
                    self.wait_for_ui(root, lambda: app._heartbeat_state != before,
                                     timeout=HEARTBEAT_INTERVAL_MS / 1000 + .8)

                saving = SimpleNamespace(status="saving", generation=701, message="")
                cancelled = SimpleNamespace(status="cancelled", generation=701, message="")
                before_close = app._heartbeat_state
                with patch.object(app.rounds, "request_close", return_value=saving), \
                        patch.object(app.rounds, "close_status", return_value=saving), \
                        patch.object(app.rounds, "cancel_close", return_value=cancelled):
                    app.close()
                    root.update()
                    self.assertTrue(app._closing_ui)
                    self.assertTrue(app._close_window.winfo_viewable())
                    self.assertEqual(str(app._close_cancel_button.cget("state")), "normal")
                    self.wait_for_ui(root, lambda: app._heartbeat_state != before_close,
                                     timeout=HEARTBEAT_INTERVAL_MS / 1000 + .8)
                    self.assertTrue(root.winfo_exists())
                    app.cancel_close()
                    self.assertFalse(app._closing_ui)

                blocked = []

                def block_ui_callback():
                    state_before_block = app._heartbeat_state
                    time.sleep(0.75)
                    blocked.append((state_before_block, app._heartbeat_state))

                root.after(100, block_ui_callback)
                while not blocked:
                    root.update()
                    time.sleep(.005)
                self.assertEqual(blocked[0][0], blocked[0][1])
                state_after_resume = app._heartbeat_state
                self.wait_for_ui(root, lambda: app._heartbeat_state != state_after_resume,
                                 timeout=HEARTBEAT_INTERVAL_MS / 1000 + .8)
                self.assertEqual(app._heartbeat_state, (state_after_resume + 1) % 16)

                if os.environ.get("B518_TK_EVIDENCE_DIR"):
                    capture["heartbeat"] = {
                        "interval_ms": HEARTBEAT_INTERVAL_MS,
                        "states": observed_states,
                        "patterns": observed_patterns,
                        "initial_state_zero_verified": True,
                        "cycle_start_state": cycle_start_state,
                        "transition_elapsed_seconds": [
                            round(value - transition_times[0], 3)
                            for value in transition_times],
                        "measured_intervals_seconds": [round(value, 3)
                                                       for value in intervals],
                        "state_coverage": [state.value for *_, state in state_samples],
                        "actionable_close_save_ui_verified": True,
                        "blocked_ui_state_before_and_after_sleep": blocked[0],
                        "state_after_ui_resumed": app._heartbeat_state,
                    }
                    write_tk_bounds_evidence("ls6-heartbeat", capture)

                heartbeat_id = app._heartbeat_after_id
                external_id = root.after(10_000, lambda: None)
                self.assertIn(heartbeat_id, root.tk.call("after", "info"))
                cancelled_ids = []
                original_after_cancel = root.after_cancel
                root.after_cancel = lambda after_id: (
                    cancelled_ids.append(after_id), original_after_cancel(after_id))[-1]
                callback_errors = []
                root.report_callback_exception = lambda *error: callback_errors.append(error)
                root.destroy()
                self.assertIn(heartbeat_id, cancelled_ids)
                self.assertNotIn(external_id, cancelled_ids)
                self.assertIsNone(app._heartbeat_after_id)
                self.assertNotIn(heartbeat_id, app._after_ids)
                self.assertTrue(app._ui_destroyed)
                self.assertEqual(callback_errors, [])

                app.hotkey.close()
                app.rounds.request_close()
                app.app_events.stop()
                persisted_events = read_app_event_store(app.app_events.path)["events"]
                self.assertFalse(any("heartbeat" in str(event).lower()
                                     for event in persisted_events))
            finally:
                if not app._ui_destroyed:
                    try:
                        root.destroy()
                    except tk.TclError:
                        pass

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
                    self.assertEqual(app.kvm_state_marker.winfo_x(), 250)
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
                self.assertEqual(app.language_button.cget("text"), "🌐")
                self.assertEqual(
                    [app.language_menu.entrycget(index, "label")
                     for index in range(app.language_menu.index("end") + 1)],
                    ["English", "繁體中文"],
                )
                self.assertEqual(app.language_choice.get(), ENGLISH)
                self.assertEqual(app.settings_button.cget("text"), "⚙️")
                self.assertEqual(app.project_label.cget("text"), "Project")
                self.assertFalse(hasattr(app, "kvm_result_title"))
                self.assertLessEqual(
                    app.language_button.winfo_x() + app.language_button.winfo_width(),
                    app.language_button.master.winfo_width(),
                )
                self.assertLess(app.language_button.winfo_rooty(), app.kvm_results.winfo_rooty())

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

                # Exercise the actual Menu command; native popup input has its own test.
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
                self.assertEqual(app.language_button.cget("text"), "🌐")
                self.assertEqual(app.settings_button.cget("text"), "⚙️")
                self.assertEqual(app.project_label.cget("text"), "專案")
                self.assertEqual(app.status_rows[1]["slot"].cget("text"), "通道 1")
                self.assertFalse(hasattr(app, "kvm_result_title"))
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
                        patch("b518_log_solution.show_notice") as show_error:
                    app.language_menu.invoke(chinese_index)
                self.assertEqual(app.current_language, TRADITIONAL_CHINESE)
                self.assertEqual(app.language_choice.get(), TRADITIONAL_CHINESE)
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
                second_root.deiconify()
                second_app = B518LogSolutionApp(
                    second_root, hotkey_factory=FakeHotkey,
                    session_root=Path(temporary) / "sessions-2",
                )
                try:
                    self.assertEqual(second_app.current_language, ENGLISH)
                    self.assertEqual(second_app.language_choice.get(), ENGLISH)
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
                patch("b518_log_solution.show_notice") as show_warning:
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
                self.assertEqual(app.language_choice.get(), ENGLISH)
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

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_hm6_two_row_kvm_keeps_geometry_and_unused_slots_black(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.deiconify()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey,
                session_root=Path(temporary) / "sessions",
                app_event_path=Path(temporary) / "app-events.json",
            )
            try:
                profile = replace(
                    app.profiles.get("B518", "FCT"), project="HM6-KVM", capacity=12,
                    mapping=tuple((slot, slot) for slot in range(1, 13)),
                )
                app.profiles = app.profiles.with_profile(profile)
                app.project_choice.configure(values=app.profiles.projects)
                app.project.set(profile.project)
                app._project_changed()
                app.machine_choice.set(profile.machine)
                app._profile_changed()
                root.update_idletasks()

                self.assertEqual(app._display_capacity(), 12)
                self.assertEqual(app.kvm_results.winfo_height(), KVM_BAND_HEIGHT)
                first_row_y = app.kvm_result_blocks[1].winfo_y()
                second_row_y = app.kvm_result_blocks[11].winfo_y()
                self.assertGreater(second_row_y, first_row_y)
                self.assertEqual(app.kvm_state_marker.winfo_height(), MARKER_SIZE)
                self.assertEqual(app.kvm_layout_marker.winfo_height(), 14)
                app._set_kvm_result_block(12, "PASS")
                app._set_kvm_result_block(13, "PASS")
                self.assertEqual(app.kvm_result_blocks[12].cget("background"),
                                 STATUS_COLOURS["PASS"])
                self.assertEqual(app.kvm_result_blocks[13].cget("background"),
                                 UNAVAILABLE_COLOUR)

                evidence = capture_tk_window_evidence(
                    root, "main-page-capacity12", "en", {
                        "kvm": app.kvm_results,
                        "state_marker": app.kvm_state_marker,
                        "layout_marker": app.kvm_layout_marker,
                        "slot_1": app.kvm_result_blocks[1],
                        "slot_11": app.kvm_result_blocks[11],
                        "slot_12": app.kvm_result_blocks[12],
                        "unused_slot_13": app.kvm_result_blocks[13],
                    })
                write_tk_bounds_evidence("main_page_capacity12", {"en": evidence})
            finally:
                app.rounds.request_close()
                self.wait_for(lambda: app.rounds.close_status().status == "complete")
                app.hotkey.close()
                root.destroy()

    def test_real_tk_global_retention_setting_validates_persists_and_preserves_round_files(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.deiconify()
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
            root.deiconify()
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
            app_event_path = Path(temporary) / "app-events.json"
            old_app_events = AppEventStore(app_event_path, clock=lambda: archived_at)
            old_app_event = old_app_events.record(
                "app.hotkey.unavailable", {}, "old hotkey diagnostic")
            self.assertTrue(old_app_events.flush())
            old_app_events.stop()
            protected_files = {
                Path(temporary) / "manual-export.json": b'{"keep": true}',
                Path(temporary) / "source-log.txt": b"external source log",
            }
            for path, contents in protected_files.items():
                path.write_bytes(contents)

            app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey, session_root=session_root,
                                     app_event_path=app_event_path)
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
                self.assertIn("App events deleted 0, retained 2", app.retention_cleanup_status.get())
                self.assertTrue(archive_path.parent.exists())

                root.update()
                chinese_index = next(
                    index for index in range(app.language_menu.index("end") + 1)
                    if app.language_menu.entrycget(index, "label") == "繁體中文")
                app.language_menu.invoke(chinese_index)
                root.update()
                self.assertIn("App 事件：刪除 0、保留 2、失敗 0",
                              app.retention_cleanup_status.get())
                self.assertIn("App 事件從各自原事件時間起算",
                              app.retention_help_label.cget("text"))
                root.update()
                app.language_menu.invoke(0)
                root.update()

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
                self.assertIn("App events deleted 1", app.retention_cleanup_status.get())
                ledger_path = session_root.parent / "round-retention-ledger.json"
                ledger_bytes = ledger_path.read_bytes()
                previous_rounds = app.rounds
                fresh_reader = RoundCoordinator(
                    audit_root=session_root, retention_ledger_path=ledger_path)
                self._app_round_coordinators.remove(fresh_reader)
                restored = fresh_reader.retention_cleanup_summaries()[-1]
                self.assertEqual(restored.deleted_round_ids, (archived_round.round_id,))
                self.assertEqual(restored.results[0].reason_message["message_id"],
                                 "app.settings.retention.reason.deleted")
                self.assertEqual(restored.message_reason["message_id"],
                                 "app.settings.retention.reason.cleanup.run_summary")
                self.assertEqual(restored.app_events.reason_message["message_id"],
                                 "app.settings.retention.reason.app_events_deleted")
                self.assertEqual(restored.app_events.reason_message["parameters"][
                    "deleted_count"], 1)
                self.assertEqual(restored.app_events.reason_message["parameters"][
                    "skipped_count"], restored.app_events.skipped_count)
                app.rounds = fresh_reader
                app._refresh_retention_cleanup_status()
                self.assertIn("Trusted round records were completely deleted",
                              app.retention_cleanup_status.get())
                self.assertIn(restored.app_events.reason_message["en"],
                              app.retention_cleanup_status.get())
                self.set_language_for_test_setup(app, root, TRADITIONAL_CHINESE)
                self.assertIn("已完整刪除可信輪次資料。", app.retention_cleanup_status.get())
                self.assertIn(restored.app_events.reason_message["zh-TW"],
                              app.retention_cleanup_status.get())
                self.assertEqual(ledger_path.read_bytes(), ledger_bytes)
                app.rounds = previous_rounds
                self.set_language_for_test_setup(app, root, ENGLISH)
                app._refresh_retention_cleanup_status()
                remaining = read_app_event_store(app_event_path)
                self.assertNotIn(old_app_event.event_id,
                                 [item["event_id"] for item in remaining["events"]])
                self.assertEqual(remaining["retired_sequences"], [[1, 1]])
                persisted = MachineProfileStore(Path(temporary) / "preferences.json")
                persisted.load()
                self.assertEqual(persisted.retention_days, 180)
                for path, contents in protected_files.items():
                    self.assertEqual(path.read_bytes(), contents)
                self.assertFalse(archive_path.parent.exists())
                self.assertGreater(heartbeat[0], 1)
                self.assertEqual(app.retention_retry_button.cget("text"),
                                 "Retry Background Cleanup")
                before_retry = len(app.rounds.retention_cleanup_summaries())
                app.retention_retry_button.invoke()
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    root.update()
                    if (len(app.rounds.retention_cleanup_summaries()) > before_retry and
                            app.rounds.retention_cleanup_status().status in {"complete", "failed"}):
                        break
                    time.sleep(0.01)
                self.assertEqual(app.rounds.retention_cleanup_status().status, "complete")
                self.assertEqual(app.rounds.retention_cleanup_summaries()[-1].trigger,
                                 "manual-retry")
            finally:
                app._close_settings()
                app.rounds.request_close()
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline and app.rounds.close_status().status != "complete":
                    root.update()
                    time.sleep(0.01)
                app.hotkey.close()
                root.destroy()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_cleanup_summary_is_visibly_drawn_in_the_real_settings_window(self):
        with TemporaryDirectory() as temporary:
            root = tk.Tk()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey,
                session_root=Path(temporary) / "sessions",
                app_event_path=Path(temporary) / "app-events.json",
            )
            try:
                app.open_settings()
                app.settings_window.geometry("720x620")
                app.settings_notebook.select(2)
                self.wait_for(lambda: app.rounds.retention_cleanup_status().status
                              in {"complete", "failed"})
                app._refresh_retention_cleanup_status()
                summary = app.retention_cleanup_text
                summary.tag_add("sel", "1.0", "1.4")
                reading_position = summary.index("@0,0")
                stable_detail = summary.get("1.0", "end-1c")
                deadline = time.monotonic() + .8
                while time.monotonic() < deadline:
                    root.update()
                    time.sleep(.01)
                self.assertEqual(summary.get("1.0", "end-1c"), stable_detail)
                self.assertEqual(summary.index("@0,0"), reading_position)
                self.assertEqual(tuple(map(str, summary.tag_ranges("sel"))),
                                 ("1.0", "1.4"))
                end = time.monotonic() + .3
                while time.monotonic() < end:
                    root.update()
                    time.sleep(.01)

                evidence_dir = os.environ.get(
                    "B518_TK_EVIDENCE_DIR", str(Path(temporary) / "hf6-rendered"))
                with patch.dict(os.environ, {"B518_TK_EVIDENCE_DIR": evidence_dir}):
                    capture = capture_tk_window_evidence(
                        app.settings_window, "hf6-cleanup-render", "en",
                        {"summary": app.retention_cleanup_text})
                    self.assertIn("cleanup", summary.get("1.0", "end-1c").lower())
                    self.set_language_for_test_setup(app, root, TRADITIONAL_CHINESE)
                    app._refresh_retention_cleanup_status()
                    self.assertIn("清理", app.retention_cleanup_text.get("1.0", "end-1c"))
                    chinese_capture = capture_tk_window_evidence(
                        app.settings_window, "hf6-cleanup-render", "zh-TW",
                        {"summary": app.retention_cleanup_text})
                    empty_captures = {}
                    idle_status = SimpleNamespace(
                        status="idle", message="", reason_message=None)
                    with patch.object(app.rounds, "retention_cleanup_status",
                                      return_value=idle_status), \
                            patch.object(app.rounds, "retention_cleanup_summaries",
                                         return_value=()):
                        self.set_language_for_test_setup(app, root, ENGLISH)
                        app._refresh_retention_cleanup_status()
                        self.assertEqual(summary.get("1.0", "end-1c"),
                                         "Background cleanup has not run.")
                        empty_captures["empty-en"] = capture_tk_window_evidence(
                            app.settings_window, "hf6-cleanup-empty", "en",
                            {"summary": summary})
                        self.set_language_for_test_setup(app, root, TRADITIONAL_CHINESE)
                        app._refresh_retention_cleanup_status()
                        self.assertEqual(summary.get("1.0", "end-1c"), "背景清理尚未執行。")
                        empty_captures["empty-zh-TW"] = capture_tk_window_evidence(
                            app.settings_window, "hf6-cleanup-empty", "zh-TW",
                            {"summary": summary})
                    (Path(evidence_dir) / "hf6-window-bounds.json").write_text(
                        json.dumps({"en": capture, "zh-TW": chinese_capture,
                                    **empty_captures},
                                   ensure_ascii=False, indent=2), encoding="utf-8")
                    from AppKit import NSData, NSBitmapImageRep

                    image_path = Path(evidence_dir) / capture["screenshot"]
                    bitmap = NSBitmapImageRep.imageRepWithData_(
                        NSData.dataWithContentsOfFile_(str(image_path)))
                    width = bitmap.pixelsWide()
                    height = bitmap.pixelsHigh()
                    scale = width / capture["native_bounds"]["Width"]
                    x, y, widget_width, _widget_height = capture["controls"]["summary"]
                    top_bar = height / scale - app.settings_window.winfo_height()
                    data = bitmap.bitmapData()
                    bytes_per_pixel = bitmap.bitsPerPixel() // 8
                    bytes_per_row = bitmap.bytesPerRow()
                    x0 = int((x + 2) * scale)
                    x1 = int((x + min(widget_width, 160)) * scale)
                    y0 = int((y + top_bar + 3) * scale)
                    y1 = int((y + top_bar + 24) * scale)
                    visible_ink_pixels = 0
                    for row in range(y0, min(y1, height)):
                        for column in range(x0, min(x1, width)):
                            offset = row * bytes_per_row + column * bytes_per_pixel
                            if min(data[offset:offset + 3]) < 128:
                                visible_ink_pixels += 1
                self.assertGreater(
                    visible_ink_pixels, 100,
                    "cleanup summary text exists in Tk but is not visible in the native window",
                )
                summary.configure(state="normal")
                summary.delete("1.0", "end")
                summary.insert("1.0", "\\n".join(
                    "Long cleanup diagnostic line {}: preserved evidence.".format(index)
                    for index in range(80)))
                summary.configure(state="disabled")
                summary.yview_moveto(1.0)
                root.update()
                self.assertLess(summary.yview()[0], 1.0)
                self.assertGreater(app.retention_cleanup_scrollbar.winfo_height(), 0)
                app._refresh_retention_cleanup_status()
                root.update()
                self.assertEqual(summary.get("1.0", "end-1c"), app.retention_cleanup_status.get())
                self.assertGreaterEqual(summary.yview()[0], 0.0)
                self.assertLessEqual(summary.yview()[1], 1.0)
                app._close_settings()
                app.open_settings()
                app.settings_notebook.select(2)
                root.update()
                self.assertTrue(app.retention_cleanup_text.get("1.0", "end-1c").strip())
                self.assertTrue(app.retention_cleanup_scrollbar.winfo_ismapped())
            finally:
                app._close_settings()
                app.rounds.request_close()
                self.wait_for(lambda: app.rounds.close_status().status == "complete")
                app.hotkey.close()
                app.app_events.stop()
                root.destroy()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_real_tk_app_event_cleanup_failure_is_visible_and_retryable(self):
        with TemporaryDirectory() as temporary:
            root_path = Path(temporary)
            preferences = root_path / "preferences.json"
            profile_store = MachineProfileStore(preferences)
            profile_store.load()
            profile_store.save_retention_days(30)
            app_event_path = root_path / "app-events.json"
            event_time = [datetime.now(timezone.utc) - timedelta(days=31)]
            seeded_store = AppEventStore(app_event_path, clock=lambda: event_time[0])
            expired_event = seeded_store.record(
                "app.hotkey.unavailable", {}, "original expired diagnostic")
            event_time[0] += timedelta(days=30)
            retained_event = seeded_store.record(
                "app.profile.save_failed", {"reason": "current"}, "retained diagnostic")
            self.assertTrue(seeded_store.flush())
            seeded_store.stop()
            root = tk.Tk()
            root.deiconify()
            with patch("b518_log_solution.PREFS_PATH", preferences), \
                    patch.object(RoundCoordinator, "start_retention_schedule", return_value=None):
                app = B518LogSolutionApp(
                    root, hotkey_factory=FakeHotkey, session_root=root_path / "sessions",
                    app_event_path=app_event_path)

            def pump_until(predicate, timeout=5):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    root.update()
                    if predicate():
                        return
                    time.sleep(0.01)
                self.fail("Timed out while pumping App-event cleanup UI")

            try:
                pump_until(lambda: app.rounds.app_event_status().complete)
                app.open_settings()
                app.settings_notebook.select(2)
                root.update()
                with patch("app_event_store._atomic_replace_at",
                           side_effect=OSError("retention media unavailable")):
                    app.rounds.request_retention_cleanup(30, "manual-retry")
                    pump_until(lambda: app.rounds.retention_cleanup_status().status == "failed")
                    app._refresh_retention_cleanup_status()
                    self.assertIn("retention media unavailable",
                                  app.retention_cleanup_status.get())
                    failed_reason = app.rounds.retention_cleanup_summaries()[-1].app_events.reason_message
                    self.assertEqual(failed_reason["message_id"],
                                     "app.settings.retention.reason.app_events_persistence_failed")
                    self.assertIn("retention media unavailable", failed_reason["diagnostic"])
                    still_saved = read_app_event_store(app_event_path)["events"]
                    self.assertIn(expired_event.event_id,
                                  [item["event_id"] for item in still_saved])

                retry_x = app.retention_retry_button.winfo_width() // 2
                retry_y = app.retention_retry_button.winfo_height() // 2
                app.retention_retry_button.event_generate(
                    "<ButtonPress-1>", x=retry_x, y=retry_y)
                app.retention_retry_button.event_generate(
                    "<ButtonRelease-1>", x=retry_x, y=retry_y)
                pump_until(lambda: (app.rounds.retention_cleanup_status().status == "complete" and
                                    app.rounds.retention_cleanup_summaries()[-1].trigger ==
                                    "manual-retry"))
                app._refresh_retention_cleanup_status()
                self.assertNotIn(expired_event.event_id,
                                  [item["event_id"] for item in
                                   read_app_event_store(app_event_path)["events"]])
                self.assertIn(retained_event.event_id,
                              [item["event_id"] for item in
                               read_app_event_store(app_event_path)["events"]])
                success_reason = app.rounds.retention_cleanup_summaries()[-1].app_events.reason_message
                self.assertEqual(success_reason["message_id"],
                                 "app.settings.retention.reason.app_events_deleted")
                self.assertIn(success_reason["en"], app.retention_cleanup_status.get())
                self.assertIn("retention media unavailable",
                              app.rounds.retention_cleanup_summaries()[0].app_events.reason)

                root.update()
                chinese_index = next(
                    index for index in range(app.language_menu.index("end") + 1)
                    if app.language_menu.entrycget(index, "label") == "繁體中文")
                app.language_menu.invoke(chinese_index)
                root.update()
                self.assertEqual(app.retention_retry_button.cget("text"), "重試背景清理")
                self.assertIn("App 事件：刪除 1", app.retention_cleanup_status.get())
                self.assertIn(success_reason["zh-TW"], app.retention_cleanup_status.get())
                app.rounds.request_close()
                pump_until(lambda: app.rounds.close_status().status == "complete")
            finally:
                app.hotkey.close()
                root.destroy()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_real_tk_localizes_timezone_missing_app_event_cleanup_reason(self):
        with TemporaryDirectory() as temporary:
            root_path = Path(temporary)
            preferences = root_path / "preferences.json"
            profile_store = MachineProfileStore(preferences)
            profile_store.load()
            profile_store.save_retention_days(30)
            app_event_path = root_path / "app-events.json"
            store = AppEventStore(app_event_path)
            store.record("app.hotkey.unavailable", {}, "time fixture")
            self.assertTrue(store.flush())
            store.stop()

            root = tk.Tk()
            root.deiconify()
            with patch("b518_log_solution.PREFS_PATH", preferences), \
                    patch.object(RoundCoordinator, "start_retention_schedule", return_value=None):
                app = B518LogSolutionApp(
                    root, hotkey_factory=FakeHotkey, session_root=root_path / "sessions",
                    app_event_path=app_event_path)
            payload = json.loads(app_event_path.read_text(encoding="utf-8"))
            payload["events"][0]["occurred_at"] = "2026-10-09T08:00:00"
            app_event_path.write_text(json.dumps(payload), encoding="utf-8")
            malformed_bytes = app_event_path.read_bytes()

            def pump_until(predicate, timeout=5):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    root.update()
                    if predicate():
                        return
                    time.sleep(0.01)
                self.fail("Timed out while pumping malformed-time cleanup UI")

            try:
                with patch("b518_log_solution.show_notice", return_value="ok"):
                    app.open_settings()
                    app.settings_notebook.select(2)
                    app.rounds.request_retention_cleanup(30, "malformed-time")
                    pump_until(lambda: app.rounds.retention_cleanup_status().status == "failed")
                    app._refresh_retention_cleanup_status()
                    self.assertIn("An App event original time has no time zone",
                                  app.retention_cleanup_status.get())
                    chinese_index = next(
                        index for index in range(app.language_menu.index("end") + 1)
                        if app.language_menu.entrycget(index, "label") == "繁體中文")
                    app.language_menu.invoke(chinese_index)
                    root.update()
                    self.assertIn("App 事件原始時間缺少時區", app.retention_cleanup_status.get())
                    self.assertEqual(app_event_path.read_bytes(), malformed_bytes)
                app.rounds.request_close()
                pump_until(lambda: app.rounds.close_status().status == "complete")
            finally:
                app.hotkey.close()
                root.destroy()

    def test_real_tk_notification_badge_stays_until_alarm_is_acknowledged(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.deiconify()
            session_root = Path(temporary) / "sessions"
            app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey,
                                     session_root=session_root)
            elapsed = [0.0]
            rounds = RoundCoordinator(app.events.put, monotonic=lambda: elapsed[0],
                                      audit_root=session_root)
            app.rounds = rounds
            monitors = []

            class AlarmMonitor(BaseMonitor):
                def __init__(self, callback):
                    super().__init__("FCT", {}, (1,), callback=callback,
                                     session_root=session_root, monotonic=lambda: elapsed[0],
                                     async_session_writes=True, round_timeout_seconds=1)
                    monitors.append(self)

                def poll_once(self):
                    pass

            try:
                badge_text = lambda: app.notification_badge.itemcget(
                    app._notification_badge_label, "text")
                self.assertEqual(badge_text(), "")
                started = rounds.start("FCT", AlarmMonitor, run_async=False,
                                       round_timeout_seconds=1, capacity=1)
                self.wait_for_ui(root, lambda: app._pending_notification_count() == 0)
                elapsed[0] = 2.0
                rounds.poll_once()
                self.wait_for_ui(root, lambda: rounds.snapshot().round_alarm_ready)
                monitor = monitors[0]
                original_open = Path.open
                write_attempts = {monitor.session.path: 0}
                failure_limits = {monitor.session.path: 3}

                def fail_round_event_append(path, mode="r", *args, **kwargs):
                    if path.name == "events.log" and path.parent in failure_limits and mode == "a":
                        write_attempts[path.parent] += 1
                        if write_attempts[path.parent] <= failure_limits[path.parent]:
                            raise OSError("HF3 controlled Session write failure")
                    return original_open(path, mode, *args, **kwargs)

                with patch.object(Path, "open", fail_round_event_append):
                    monitor.session.enqueue_event("HF3 notification lifecycle probe")
                    self.wait_for_ui(root, lambda: rounds.snapshot().save_state == "failed")
                    self.wait_for_ui(root, lambda: app._pending_notification_count() == 2)

                    for language in (ENGLISH, TRADITIONAL_CHINESE):
                        self.set_language_for_test_setup(app, root, language)
                        self.wait_for_ui(root, lambda: badge_text() == "2")
                        self.assertTrue(app.notification_badge.winfo_ismapped())
                        if app.round_alarm_window and app.round_alarm_window.winfo_exists():
                            app.round_alarm_window.withdraw()
                        capture_main_badge_evidence(app, "hf3-count-two", language,
                                                    {"bell": app.round_alarm_button,
                                                     "badge": app.notification_badge})

                    bell_left = app.round_alarm_button.winfo_rootx()
                    bell_right = bell_left + app.round_alarm_button.winfo_width()
                    badge_left = app.notification_badge.winfo_rootx()
                    badge_y = app.notification_badge.winfo_height() // 2
                    outside_x = min(app.notification_badge.winfo_width() - 2,
                                    bell_right - badge_left + 3)
                    self.assertGreaterEqual(badge_left + outside_x, bell_right)
                    app.notification_badge.event_generate(
                        "<ButtonRelease-1>", x=outside_x, y=badge_y)
                    root.update()
                    self.assertTrue(app.recovery_window is None or
                                    not app.recovery_window.winfo_viewable())
                    inside_x = max(1, min(app.notification_badge.winfo_width() - 2,
                                          bell_right - badge_left - 2))
                    app.notification_badge.event_generate(
                        "<ButtonRelease-1>", x=inside_x, y=badge_y)
                    root.update()
                    self.assertIsNotNone(app.recovery_window)
                    self.assertTrue(app.recovery_window.winfo_viewable())
                    app.recovery_window.withdraw()
                    self.assertEqual(badge_text(), "2")
                    app.recovery_alarm_ack_button.invoke()
                    self.wait_for_ui(root, lambda: bool(rounds.snapshot().round_alarm.acknowledged_at))
                    self.wait_for_ui(root, lambda: app._pending_notification_count() == 1)
                    self.wait_for_ui(root, lambda: badge_text() == "1")

                    app.recovery_tabs.select(1)
                    root.update()
                    for language in (ENGLISH, TRADITIONAL_CHINESE):
                        self.set_language_for_test_setup(app, root, language)
                        self.assertEqual(badge_text(), "1")
                        self.assertTrue(app.notification_badge.winfo_ismapped())
                        app.recovery_window.withdraw()
                        if app.round_alarm_window and app.round_alarm_window.winfo_exists():
                            app.round_alarm_window.withdraw()
                        capture_main_badge_evidence(app, "hf3-one-save-failure", language,
                                                    {"bell": app.round_alarm_button,
                                                     "badge": app.notification_badge})
                        app.recovery_window.deiconify()
                        app.recovery_window.lift()

                    # Acknowledging a timeout is separate from cancelling its
                    # unverified round under LI5; neither clears pending saves.
                    self.assertTrue(rounds.snapshot().cancellation_available)
                    with self.assertRaisesRegex(RuntimeError, "人工核對"):
                        rounds.start("FCT", AlarmMonitor, run_async=False,
                                     round_timeout_seconds=1, capacity=1)
                    self.assertTrue(rounds.cancel_unverified_round(
                        started.round_id, "operator verified and cancelled timed-out round"))
                    self.assertEqual(rounds.snapshot().completion_reason,
                                     "unverified_round_cancelled")
                    self.assertEqual(app._pending_notification_count(), 1)
                    second_started = rounds.start("FCT", AlarmMonitor, run_async=False,
                                                   round_timeout_seconds=1, capacity=1)
                    second_monitor = monitors[1]
                    write_attempts[second_monitor.session.path] = 0
                    failure_limits[second_monitor.session.path] = 1
                    second_monitor.session.enqueue_event("HF3 second-round write failure")
                    self.wait_for_ui(root, lambda:
                                     rounds.snapshot().save_state == "failed")
                    rounds.stop()
                    self.wait_for_ui(root, lambda: app._pending_notification_count() == 2)
                    # Build ten additional independently failed rounds through the
                    # coordinator/session lifecycle so the real badge proves it is
                    # not capped at a single digit.
                    additional_round_ids = []
                    for index in range(10):
                        started_extra = rounds.start(
                            "FCT", AlarmMonitor, run_async=False,
                            round_timeout_seconds=1, capacity=1)
                        extra_monitor = monitors[-1]
                        write_attempts[extra_monitor.session.path] = 0
                        failure_limits[extra_monitor.session.path] = 1
                        extra_monitor.session.enqueue_event(
                            "HF3 multi-digit failure {}".format(index + 1))
                        self.wait_for_ui(root, lambda round_id=started_extra.round_id:
                                         rounds.round_snapshot(round_id).save_state == "failed")
                        rounds.stop()
                        additional_round_ids.append(started_extra.round_id)
                    self.wait_for_ui(root, lambda: app._pending_notification_count() == 12)
                    app.recovery_window.withdraw()
                    for language in (ENGLISH, TRADITIONAL_CHINESE):
                        self.set_language_for_test_setup(app, root, language)
                        self.wait_for_ui(root, lambda: badge_text() == "12")
                        capture_main_badge_evidence(app, "hf3-twelve-save-rounds", language,
                                                    {"bell": app.round_alarm_button,
                                                     "badge": app.notification_badge})
                    app.recovery_window.deiconify()
                    app.recovery_window.lift()

                    first_index = app._recovery_save_ids.index(started.round_id)
                    app.recovery_save_list.selection_clear(0, "end")
                    app.recovery_save_list.selection_set(first_index)
                    app.recovery_save_list.event_generate("<<ListboxSelect>>")
                    root.update()

                    app.recovery_save_retry_button.invoke()
                    self.wait_for_ui(root, lambda: write_attempts[monitor.session.path] >= 2 and
                                     rounds.round_snapshot(started.round_id).save_state == "failed" and
                                     str(app.recovery_save_retry_button["state"]) == "normal")
                    self.assertEqual(badge_text(), "12")
                    app.recovery_save_retry_button.invoke()
                    self.wait_for_ui(root, lambda: write_attempts[monitor.session.path] >= 3 and
                                     rounds.round_snapshot(started.round_id).save_state == "failed" and
                                     str(app.recovery_save_retry_button["state"]) == "normal")
                    self.assertEqual(badge_text(), "12")
                    app.recovery_save_retry_button.invoke()
                    self.wait_for_ui(root, lambda:
                                     app._pending_notification_count() == 11)
                    second_index = app._recovery_save_ids.index(second_started.round_id)
                    app.recovery_save_list.selection_clear(0, "end")
                    app.recovery_save_list.selection_set(second_index)
                    app.recovery_save_list.event_generate("<<ListboxSelect>>")
                    root.update()
                    original_archive_write = monitoring_round.write_round_archive
                    archive_failure = [True]

                    def fail_one_archive(audit_path, session_path, archived_at, **kwargs):
                        if (kwargs.get("expected_round_id") == second_started.round_id and
                                archive_failure[0]):
                            archive_failure[0] = False
                            raise OSError("HF3 controlled archive write failure")
                        return original_archive_write(
                            audit_path, session_path, archived_at, **kwargs)

                    with patch("monitoring_round.write_round_archive", fail_one_archive):
                        app.recovery_save_retry_button.invoke()
                        self.wait_for_ui(
                            root,
                            lambda: (rounds.archive_status(second_started.round_id).status == "failed" and
                                     rounds.archive_status(second_started.round_id).save_state == "complete"),
                        )
                        self.assertEqual(app._pending_notification_count(), 11)
                        app.recovery_window.withdraw()
                        for language in (ENGLISH, TRADITIONAL_CHINESE):
                            self.set_language_for_test_setup(app, root, language)
                            capture_main_badge_evidence(
                                app, "hf3-archive-failure", language,
                                {"bell": app.round_alarm_button,
                                 "badge": app.notification_badge})
                        app.recovery_window.deiconify()
                        app.recovery_window.lift()
                        archive = rounds.archive_status(second_started.round_id)
                        if os.environ.get("B518_TK_EVIDENCE_DIR"):
                            archive_record = {
                                "round_id": second_started.round_id,
                                "status": archive.status,
                                "save_state": archive.save_state,
                                "message": archive.message,
                                "notification_count": app._pending_notification_count(),
                            }
                            (Path(os.environ["B518_TK_EVIDENCE_DIR"]) /
                             "hf3-archive-failure-status.json").write_text(
                                json.dumps(archive_record, ensure_ascii=False, indent=2))
                        app.recovery_tabs.select(1)
                        self.wait_for_ui(root, lambda:
                                         second_started.round_id in app._recovery_archive_ids)
                        archive_index = app._recovery_archive_ids.index(second_started.round_id)
                        app.recovery_archive_list.selection_clear(0, "end")
                        app.recovery_archive_list.selection_set(archive_index)
                        app.recovery_archive_list.event_generate("<<ListboxSelect>>")
                        root.update()
                        self.assertEqual(str(app.recovery_archive_retry_button["state"]), "normal")
                        for language in (ENGLISH, TRADITIONAL_CHINESE):
                            self.set_language_for_test_setup(app, root, language)
                            capture_recovery_evidence(
                                app, "hf3-archive-recovery", language,
                                {"archive-list": app.recovery_archive_list,
                                 "archive-detail": app.recovery_archive_detail,
                                 "archive-retry": app.recovery_archive_retry_button})
                    app.recovery_archive_retry_button.invoke()
                    self.wait_for_ui(root, lambda: app._pending_notification_count() == 10)
                    failure_limits.clear()
                    for round_id in additional_round_ids:
                        snapshot = rounds.round_snapshot(round_id)
                        if snapshot is not None and snapshot.save_state == "failed":
                            self.assertTrue(rounds.retry_saves(round_id))
                        archive = rounds.archive_status(round_id)
                        if archive is not None:
                            rounds.retry_archival(round_id)
                    self.wait_for_ui(root, lambda: app._pending_notification_count() == 0,
                                     timeout=30)
                    self.wait_for_ui(root, lambda: app.notification_badge.winfo_manager() == "")
                    self.assertFalse(app.notification_badge.winfo_ismapped())
                    self.assertEqual(badge_text(), "")
                    for language in (ENGLISH, TRADITIONAL_CHINESE):
                        self.set_language_for_test_setup(app, root, language)
                        app.recovery_window.withdraw()
                        if app.round_alarm_window and app.round_alarm_window.winfo_exists():
                            app.round_alarm_window.withdraw()
                        capture_main_badge_evidence(app, "hf3-zero", language,
                                                    {"bell": app.round_alarm_button})
                        app.recovery_window.deiconify()
                        app.recovery_window.lift()
                    self.assertEqual(app._pending_notification_count(), 0)
            finally:
                rounds.stop()
                rounds.request_close()
                self.wait_for(lambda: rounds.close_status().status == "complete")
                app.hotkey.close()
                try:
                    root.destroy()
                except tk.TclError:
                    pass

    def test_recovery_zero_alarm_language_and_reopen_preserve_tab(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey,
                                     session_root=Path(temporary) / "sessions")
            try:
                self.set_language_for_test_setup(app, root, TRADITIONAL_CHINESE)
                app.round_alarm_button.invoke()
                root.update()
                for language, expected in ((ENGLISH, "Acknowledge Round Alarm"),
                                            (TRADITIONAL_CHINESE, "確認整輪警報")):
                    self.set_language_for_test_setup(app, root, language)
                    self.assertEqual(app.recovery_alarm_ack_button.cget("text"), expected)
                    self.assertEqual(str(app.recovery_alarm_ack_button["state"]), "disabled")
                    capture_recovery_evidence(app, "hf2-zero-alarm", language,
                        {"acknowledge": app.recovery_alarm_ack_button})
                    app.recovery_tabs.select(1)
                    root.update()
                    capture_recovery_evidence(app, "hf2-zero-recovery", language,
                        {"save_retry": app.recovery_save_retry_button,
                         "archive_retry": app.recovery_archive_retry_button})
                    app.recovery_window.withdraw()
                    app.round_alarm_button.invoke()
                    root.update()
                    self.assertEqual(app.recovery_tabs.index("current"), 1)
                    app.recovery_tabs.select(0)
            finally:
                app.hotkey.close()
                root.destroy()

    def test_recovery_window_outer_surface_uses_the_app_light_palette(self):
        """The app-owned window gutter stays light regardless of Aqua appearance."""
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey,
                                     session_root=Path(temporary) / "sessions")
            try:
                app._open_recovery_center()
                self.wait_for_ui(root, lambda: app.recovery_window.winfo_viewable())
                for language in (ENGLISH, TRADITIONAL_CHINESE):
                    self.set_language_for_test_setup(app, root, language)
                    self.assertEqual(app.recovery_window.cget("background"), LIGHT_BACKGROUND)
                    for tab in (0, 1):
                        app.recovery_tabs.select(tab)
                        root.update()
                        self.assertEqual(app.recovery_window.cget("background"), LIGHT_BACKGROUND)
                        if os.environ.get("B518_TK_EVIDENCE_DIR"):
                            key = "st7-dark-tab{}".format(tab)
                            capture_tk_window_evidence(app.recovery_window, key, language, {
                                "notebook": app.recovery_tabs,
                                "acknowledge": app.recovery_alarm_ack_button,
                                "save_retry": app.recovery_save_retry_button,
                                "archive_retry": app.recovery_archive_retry_button,
                            })
            finally:
                app.hotkey.close()
                root.destroy()

    @unittest.skipUnless(os.environ.get("B518_ST7_MANUAL_APPEARANCE") == "1",
                         "requires user-driven macOS appearance changes")
    def test_recovery_window_stays_light_during_real_system_appearance_changes(self):
        """Capture an open real window across user-driven Light/Dark changes."""
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey,
                                     session_root=Path(temporary) / "sessions")
            evidence_root = Path(os.environ["B518_TK_EVIDENCE_DIR"])
            original_window = None
            records = []

            def system_appearance():
                appearance = subprocess.run(
                    ["defaults", "read", "-g", "AppleInterfaceStyle"],
                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    universal_newlines=True)
                return "dark" if appearance.returncode == 0 and \
                    appearance.stdout.strip() == "Dark" else "light"

            def capture(mode):
                actual_mode = system_appearance()
                self.assertEqual(actual_mode, mode.split("-")[0])
                app._refresh_recovery_center()
                root.update()
                self.assertEqual(app.recovery_window, original_window)
                self.assertTrue(app.recovery_window.winfo_viewable())
                self.assertEqual(app.recovery_window.cget("background"), LIGHT_BACKGROUND)
                for language in (ENGLISH, TRADITIONAL_CHINESE):
                    self.set_language_for_test_setup(app, root, language)
                    for tab in (0, 1):
                        app.recovery_tabs.select(tab)
                        root.update()
                        self.assertEqual(app.recovery_window.cget("background"), LIGHT_BACKGROUND)
                        self.assertEqual(app.recovery_tabs.index("current"), tab)
                        if tab == 0:
                            self.assertTrue(app.recovery_alarm_ack_button.winfo_viewable())
                        else:
                            self.assertTrue(app.recovery_save_heading.winfo_viewable())
                            self.assertTrue(app.recovery_archive_heading.winfo_viewable())
                        record = capture_recovery_evidence(app,
                            "st7-{}-tab{}".format(mode, tab), language, {
                                "notebook": app.recovery_tabs,
                                "acknowledge": app.recovery_alarm_ack_button,
                                "save_retry": app.recovery_save_retry_button,
                                "archive_retry": app.recovery_archive_retry_button,
                            })
                        records.append({"mode": actual_mode, "tab": tab,
                                        "language": language, **record})

            def wait_for_user(message):
                ready = threading.Event()
                deadline = time.monotonic() + 1800
                print(message, flush=True)
                reader = threading.Thread(target=lambda: (sys.stdin.readline(), ready.set()),
                                          daemon=True)
                reader.start()
                while not ready.is_set() and time.monotonic() < deadline:
                    root.update()
                    time.sleep(.05)
                self.assertTrue(ready.is_set(), "timed out waiting for the real appearance change")

            try:
                initial_mode = system_appearance()
                original_mode = os.environ.get("B518_ST7_ORIGINAL_APPEARANCE", "dark")
                self.assertIn(original_mode, {"light", "dark"})
                app._open_recovery_center()
                self.wait_for_ui(root, lambda: app.recovery_window.winfo_viewable())
                original_window = app.recovery_window
                self.assertEqual(app.recovery_window.cget("background"), LIGHT_BACKGROUND)
                capture("{}-before".format(initial_mode))
                if initial_mode == original_mode:
                    other_mode = "light" if original_mode == "dark" else "dark"
                    wait_for_user(
                        "ST7: Switch macOS appearance to {}, then signal this test with Enter."
                        .format(other_mode.title()))
                    capture("{}-open".format(other_mode))
                else:
                    other_mode = original_mode
                    wait_for_user(
                        "ST7: Restore the original macOS {} appearance, then signal this test "
                        "with Enter.".format(original_mode.title()))
                    capture("{}-after".format(original_mode))
                if system_appearance() != original_mode:
                    wait_for_user(
                        "ST7: Restore the original macOS {} appearance, then signal this test "
                        "with Enter.".format(original_mode.title()))
                    capture("{}-after".format(original_mode))
                self.assertEqual(system_appearance(), original_mode)
                self.assertEqual(app._pending_notification_count(), 0)
                self.assertEqual(str(app.recovery_alarm_ack_button["state"]), "disabled")
                self.assertEqual(str(app.recovery_save_retry_button["state"]), "disabled")
                self.assertEqual(str(app.recovery_archive_retry_button["state"]), "disabled")
                evidence_root.mkdir(parents=True, exist_ok=True)
                (evidence_root / "appearance-evidence.json").write_text(
                    json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
                (evidence_root / "appearance-change-result.txt").write_text(
                    "The same recovery Toplevel was captured in both real macOS appearance "
                    "modes while open. Both tabs were captured in English and Traditional "
                    "Chinese. No alarms were acknowledged; no save or archive retry was "
                    "invoked. Original system appearance was {} and was restored.\n"
                    .format(original_mode.title()),
                    encoding="utf-8")
            finally:
                app.hotkey.close()
                root.destroy()

    def test_recovery_archive_list_preserves_selection_and_scroll_across_poll_language_reopen(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            session_root = Path(temporary) / "sessions"
            app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey, session_root=session_root)
            rounds = RoundCoordinator(app.events.put, audit_root=session_root)
            app.rounds = rounds
            counter = [0]

            class Monitor(BaseMonitor):
                def __init__(self, callback):
                    counter[0] += 1
                    super().__init__("FCT", {}, (1,), callback=callback,
                        session_root=session_root, now=lambda:
                        datetime(2026, 10, 16, 8, 0) + timedelta(seconds=counter[0]))

                def poll_once(self):
                    self.set_result(1, "PASS", "HF2-SCROLL", "controlled.csv")

            try:
                for _ in range(24):
                    started = rounds.start("FCT", Monitor, run_async=False, capacity=1)
                    app.active_round_id = started.round_id
                    rounds.poll_once()
                    self.wait_for_ui(root, lambda:
                        rounds.archive_status(started.round_id).cleanup_eligible)
                app.round_alarm_button.invoke()
                app.recovery_tabs.select(1)
                app.recovery_window.geometry("760x520")
                root.update()
                self.assertEqual(app.recovery_archive_list.size(), 24)
                app.recovery_archive_list.selection_clear(0, "end")
                app.recovery_archive_list.selection_set(17)
                app.recovery_archive_list.event_generate("<<ListboxSelect>>")
                app.recovery_archive_list.yview_moveto(.5)
                root.update()
                selected_id = app._recovery_archive_ids[17]
                reading = app.recovery_archive_list.yview()
                self.assertGreater(reading[0], 0)
                for language in (ENGLISH, TRADITIONAL_CHINESE):
                    self.set_language_for_test_setup(app, root, language)
                    until = time.monotonic() + .7
                    while time.monotonic() < until:
                        root.update()
                        time.sleep(.01)
                    self.assertEqual(app.recovery_archive_list.curselection(), (17,))
                    self.assertIn(selected_id, app.recovery_archive_detail.get("1.0", "end"))
                    self.assertEqual(app.recovery_archive_list.yview(), reading)
                    app.recovery_window.withdraw()
                    app.round_alarm_button.invoke()
                    root.update()
                    self.assertEqual(app.recovery_tabs.index("current"), 1)
                    self.assertEqual(app.recovery_archive_list.yview(), reading)
                    capture_recovery_evidence(app, "hf2-list-reading", language,
                        {"archive_retry": app.recovery_archive_retry_button})
            finally:
                rounds.stop()
                rounds.flush_audit()
                rounds.flush_session()
                app.hotkey.close()
                root.destroy()

    def test_recovery_acknowledges_only_manually_and_session_retry_keeps_evidence_once(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            session_root = Path(temporary) / "sessions"
            historical = SessionStore("untracked-history", {}, session_root)
            historical.enqueue_event("historical sentinel")
            app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey, session_root=session_root)
            elapsed = [0.0]
            rounds = RoundCoordinator(app.events.put, monotonic=lambda: elapsed[0],
                                      audit_root=session_root)
            app.rounds = rounds
            holders = []

            class Monitor(BaseMonitor):
                def __init__(self, callback):
                    super().__init__("FCT", {}, (1,), callback=callback,
                                     session_root=session_root, monotonic=lambda: elapsed[0],
                                     async_session_writes=True, round_timeout_seconds=1)
                    holders.append(self)

                def poll_once(self):
                    pass

            try:
                started = rounds.start("FCT", Monitor, run_async=False,
                                       round_timeout_seconds=1, capacity=1)
                app.active_round_id = started.round_id
                elapsed[0] = 2.0
                rounds.poll_once()
                self.wait_for_ui(root, lambda: rounds.snapshot().round_alarm_ready)
                monitor = holders[0]
                self.assertTrue(rounds.flush_audit())
                self.assertTrue(rounds.flush_session())
                alarm = rounds.snapshot().round_alarm
                app.round_alarm_button.invoke()
                root.update()
                for language in (ENGLISH, TRADITIONAL_CHINESE):
                    self.set_language_for_test_setup(app, root, language)
                    self.assertIn(alarm.alarm_id, app.recovery_alarm_detail.get("1.0", "end"))
                    self.assertIn(started.round_id, app.recovery_alarm_detail.get("1.0", "end"))
                    self.assertEqual(str(app.recovery_alarm_ack_button["state"]), "normal")
                    self.assertFalse(rounds.snapshot().round_alarm.acknowledged_at)
                    capture_recovery_evidence(app, "hf2-alarm-pending", language,
                        {"acknowledge": app.recovery_alarm_ack_button})
                    app.recovery_window.withdraw()
                    app.round_alarm_button.invoke()
                    root.update()
                    self.assertFalse(rounds.snapshot().round_alarm.acknowledged_at)
                original_open = Path.open
                attempts = [0]

                def fail_session_open(path, mode="r", *args, **kwargs):
                    if path == monitor.session.path / "events.log" and mode == "a":
                        attempts[0] += 1
                        if attempts[0] <= 2:
                            raise OSError("controlled Session events fault")
                    return original_open(path, mode, *args, **kwargs)

                original_write = audit_records.os.write
                recovery_failures = [0]

                def fail_recovery_event_once(descriptor, content):
                    if b'"kind": "save_recovered"' in content and not recovery_failures[0]:
                        recovery_failures[0] += 1
                        raise OSError("recovery audit event is not yet durable")
                    return original_write(descriptor, content)

                with patch.object(Path, "open", fail_session_open), \
                        patch.object(audit_records.os, "write", side_effect=fail_recovery_event_once):
                    monitor.session.enqueue_event("hf2 unique session probe")
                    self.wait_for_ui(root, lambda: rounds.snapshot().save_state == "failed")
                    app.recovery_alarm_ack_button.invoke()
                    self.wait_for_ui(root, lambda: bool(rounds.snapshot().round_alarm.acknowledged_at))
                    self.assertEqual(rounds.snapshot().save_state, "failed")
                    for language in (ENGLISH, TRADITIONAL_CHINESE):
                        self.set_language_for_test_setup(app, root, language)
                        self.assertEqual(str(app.recovery_alarm_ack_button["state"]), "disabled")
                        capture_recovery_evidence(app, "hf2-alarm-acknowledged", language,
                            {"acknowledge": app.recovery_alarm_ack_button})
                    app.recovery_tabs.select(1)
                    root.update()
                    self.assertNotIn("untracked-history", app.recovery_archive_list.get(0, "end"))
                    self.assertEqual(len(app._recovery_archive_ids), 1)
                    self.assertIn("controlled Session events fault",
                                  app.recovery_save_detail.get("1.0", "end"))
                    app.recovery_save_retry_button.invoke()
                    self.wait_for_ui(root, lambda: rounds.snapshot().save_state == "failed" and
                                     str(app.recovery_save_retry_button["state"]) == "normal")
                    app.recovery_save_retry_button.invoke()
                    self.wait_for_ui(root, lambda: recovery_failures[0] == 1 and
                                     rounds.snapshot().save_state == "failed" and
                                     str(app.recovery_save_retry_button["state"]) == "normal")
                    self.assertFalse(rounds.archive_status(started.round_id).cleanup_eligible)
                    self.assertFalse(read_round_audit(monitor.session.path / "audit.jsonl")["audit_complete"])
                    app.recovery_save_retry_button.invoke()
                    self.wait_for_ui(root, lambda: rounds.snapshot().save_state == "complete")
                self.assertTrue(rounds.flush_session())
                self.assertTrue(rounds.flush_audit())
                records = [json.loads(line) for line in
                           (monitor.session.path / "events.log").read_text().splitlines()]
                self.assertEqual(sum(item["message"] == "hf2 unique session probe"
                                     for item in records), 1)
                rebuilt = read_round_audit(monitor.session.path / "audit.jsonl")
                self.assertTrue(rebuilt["audit_complete"])
                stream_header, stream_events = audit_records.iter_round_audit_events(
                    monitor.session.path / "audit.jsonl")
                self.assertTrue(stream_header["audit_complete"])
                self.assertEqual(list(stream_events), rebuilt["events"])
                # Recovered does not waive missing records or a later failure.
                rows = [json.loads(line) for line in
                        (monitor.session.path / "audit.jsonl").read_text().splitlines()]
                corrupt = Path(temporary) / "corrupt-audit.jsonl"
                variants = [rows[:2] + rows[3:],
                            [item for item in rows if item.get("kind") != "save_recovered"]]
                later_failure = dict(rows[-1], sequence=rows[-1]["sequence"] + 1,
                                     kind="session_write_failed")
                variants.append(rows + [later_failure])
                for records_variant in variants:
                    corrupt.write_text("\n".join(json.dumps(item) for item in records_variant) + "\n")
                    self.assertFalse(read_round_audit(corrupt)["audit_complete"])
                    stream_header, stream_events = audit_records.iter_round_audit_events(corrupt)
                    self.assertFalse(stream_header["audit_complete"])
                    list(stream_events)

                self.assertEqual([item["sequence"] for item in rebuilt["events"]],
                                 list(range(1, len(rebuilt["events"]) + 1)))
                self.assertEqual(rounds.snapshot().save_state, "complete")
                self.assertTrue(any(item["kind"] == "save_recovered"
                                    for item in rebuilt["events"]))
                self.assertEqual(sum(item["kind"] == "round_alarm_acknowledged"
                                     for item in rebuilt["events"]), 1)
                self.assertTrue((historical.path / "events.log").exists())
                self.wait_for_ui(root, lambda: rounds.archive_status(started.round_id).cleanup_eligible)
                for language in (ENGLISH, TRADITIONAL_CHINESE):
                    self.set_language_for_test_setup(app, root, language)
                    capture_recovery_evidence(app, "hf2-session-recovered", language,
                        {"save_retry": app.recovery_save_retry_button})

                app.close()
                self.wait_for(lambda: rounds.close_status().status == "complete")

            finally:
                rounds.stop()
                rounds.flush_audit()
                rounds.flush_session()
                app.hotkey.close()
                try:
                    root.destroy()
                except tk.TclError:
                    pass

    def test_real_tk_distinguishes_unsaved_saved_and_archived_round_states(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.deiconify()
            session_root = Path(temporary) / "sessions"
            app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey, session_root=session_root)
            now = datetime(2026, 10, 7, 10, 0, tzinfo=timezone(timedelta(hours=8)))
            rounds = RoundCoordinator(app.events.put, audit_root=session_root, wall_clock=lambda: now)

            monitors = []

            class OneResultMonitor(BaseMonitor):
                def __init__(self, callback):
                    super().__init__("FCT", {}, (1,), callback=callback, session_root=session_root,
                                     now=lambda: now + timedelta(seconds=len(monitors)))
                    self.done = False
                    monitors.append(self)

                def poll_once(self):
                    if not self.done:
                        self.done = True
                        self.set_result(1, "PASS", "SERIAL000001", "source.csv", {
                            "round_evidence_id": "tk-archive-round",
                            "source_time": "2026-10-07T10:01:00",
                        })

            try:
                app.rounds = rounds
                app.round_alarm_button.invoke()
                self.wait_for_ui(root, lambda: app.recovery_window is not None and
                                 app.recovery_window.winfo_viewable())
                self.assertEqual(app.recovery_archive_list.get(0), "No tracked rounds")
                started = rounds.start("FCT", OneResultMonitor, run_async=False)
                app.active_round_id = started.round_id
                app._apply_round_snapshot(rounds.snapshot())
                app._refresh_recovery_center()
                self.assertIn(started.round_id[:10], app.recovery_archive_list.get(0))

                import round_archival
                original_replace = round_archival.os.replace

                def fail_archive_replace(source, destination):
                    if str(destination).endswith("round-archive.json"):
                        raise OSError("temporary archive fault")
                    return original_replace(source, destination)

                with patch.object(round_archival.os, "replace", side_effect=fail_archive_replace):
                    rounds.poll_once()
                    def archive_failure_visible():
                        app._refresh_recovery_center()
                        return (rounds.archive_status(started.round_id).status == "failed" and
                                str(app.recovery_archive_retry_button["state"]) == "normal" and
                                "temporary archive fault" in
                                app.recovery_archive_detail.get("1.0", "end-1c"))
                    self.wait_for(archive_failure_visible)
                    self.assertEqual(rounds.archive_status(started.round_id).reason_message["message_id"],
                                     "app.settings.retention.reason.archive.write_failed")
                    self.assertIn("temporary archive fault",
                                  app.recovery_archive_detail.get("1.0", "end-1c"))
                    second = rounds.start("FCT", OneResultMonitor, run_async=False)
                    app.active_round_id = second.round_id
                    rounds.poll_once()
                    self.wait_for_ui(root, lambda:
                        rounds.archive_status(second.round_id).status == "failed")

                app.round_alarm_button.invoke()
                root.update()
                app.recovery_tabs.select(1)
                app._refresh_recovery_center()
                self.assertIn("temporary archive fault",
                              app.recovery_archive_detail.get("1.0", "end-1c"))
                self.assertIn("all eligible archives (2)",
                              app.recovery_archive_retry_button.cget("text").lower())

                self.set_language_for_test_setup(app, root, TRADITIONAL_CHINESE)
                self.assertIn("無法寫入可信輪次封存資訊",
                              app.recovery_archive_detail.get("1.0", "end-1c"))
                self.assertIn("temporary archive fault",
                              app.recovery_archive_detail.get("1.0", "end-1c"))
                for language in (TRADITIONAL_CHINESE, ENGLISH):
                    self.set_language_for_test_setup(app, root, language)
                    capture_recovery_evidence(app, "hf2-archive-failure", language,
                        {"archive_retry": app.recovery_archive_retry_button})

                app.recovery_archive_retry_button.invoke()
                self.wait_for_ui(root, lambda:
                    rounds.archive_status(started.round_id).status == "archived" and
                    rounds.archive_status(second.round_id).status == "archived" and
                    app.status_rows[1]["status"].cget("text") == "PASS")

                self.wait_for_ui(root, lambda: "Trusted Archive" in
                                 app.recovery_archive_detail.get("1.0", "end"))
                self.assertNotIn("not recognized", app.recovery_archive_detail.get("1.0", "end"))
                self.assertIn("2026-10-07T10:00:00+08:00",
                              app.recovery_archive_detail.get("1.0", "end"))
                for monitor in monitors:
                    archive_file = monitor.session.path / "round-archive.json"
                    self.assertTrue(archive_file.exists())
                    rebuilt = read_round_audit(monitor.session.path / "audit.jsonl")
                    self.assertTrue(rebuilt["audit_complete"])
                    event_ids = [event["sequence"] for event in rebuilt["events"]]
                    self.assertEqual(len(event_ids), len(set(event_ids)))
                for language in (ENGLISH, TRADITIONAL_CHINESE):
                    self.set_language_for_test_setup(app, root, language)
                    capture_recovery_evidence(app, "hf2-archive-recovered", language,
                        {"archive_retry": app.recovery_archive_retry_button})
                self.set_language_for_test_setup(app, root, ENGLISH)
                app._refresh_recovery_center()
                recovered_detail = app.recovery_archive_detail.get("1.0", "end-1c")
                self.assertIn(started.round_id, recovered_detail)
                self.assertIn("Trusted Archive", recovered_detail)
                self.assertIn("2026-10-07T10:00:00+08:00", recovered_detail)
                self.assertEqual(app.status_rows[1]["status"].cget("text"), "PASS")
            finally:
                root.destroy()

    def test_real_tk_retry_button_recovers_disk_record_once_without_blocking_ui(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.deiconify()
            app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey,
                                     session_root=Path(temporary) / "sessions")
            coordinator = RoundCoordinator(app.events.put, audit_root=Path(temporary) / "sessions")
            holder = {}
            release_retry = threading.Event()
            retry_waiting = threading.Event()

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
                write_number = [0]

                def inject_fault(descriptor, content):
                    if b"tk_retry_probe" in content:
                        write_number[0] += 1
                        if write_number[0] == 1:
                            failed.set()
                            raise OSError("temporary disk fault\n" + "\n".join(
                                "diagnostic evidence {:03d}: long raw disk error".format(i)
                                for i in range(80)))
                        if write_number[0] == 2:
                            retry_entered.set()
                            retry_waiting.set()
                            release_retry.wait()
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

                    self.assertEqual(str(app.round_alarm_button["state"]), "normal")
                    app.round_alarm_button.invoke()
                    root.update()
                    self.assertTrue(app.recovery_window.winfo_exists())
                    self.assertIsNone(coordinator.snapshot().round_alarm)
                    self.assertIn("temporary disk fault",
                                  app.recovery_save_detail.get("1.0", "end-1c"))
                    app.recovery_tabs.select(1)
                    for language in (ENGLISH, TRADITIONAL_CHINESE):
                        self.set_language_for_test_setup(app, root, language)
                        root.update()
                        capture_recovery_evidence(app, "hf2-save-failure", language,
                            {"save_retry": app.recovery_save_retry_button,
                             "archive_retry": app.recovery_archive_retry_button})
                        self.assertLessEqual(app.recovery_save_retry_button.winfo_rooty() +
                            app.recovery_save_retry_button.winfo_height(),
                            app.recovery_window.winfo_rooty() + app.recovery_window.winfo_height())
                    self.set_language_for_test_setup(app, root, ENGLISH)
                    app.recovery_tabs.select(1)
                    root.update()
                    app.recovery_save_detail.yview_moveto(0.6)
                    root.update()
                    reading = app.recovery_save_detail.index("@0,0")
                    self.assertGreater(int(reading.split(".")[0]), 1)
                    until = time.monotonic() + .7
                    while time.monotonic() < until:
                        root.update()
                        time.sleep(.01)
                    self.assertEqual(app.recovery_save_detail.index("@0,0"), reading)
                    self.set_language_for_test_setup(app, root, TRADITIONAL_CHINESE)
                    self.assertEqual(app.recovery_save_detail.index("@0,0"), reading)
                    app.recovery_window.withdraw()
                    app.round_alarm_button.invoke()
                    root.update()
                    self.assertEqual(app.recovery_tabs.index("current"), 1)
                    self.assertEqual(app.recovery_save_detail.index("@0,0"), reading)
                    self.set_language_for_test_setup(app, root, ENGLISH)

                    app.recovery_save_retry_button.invoke()
                    self.assertTrue(retry_entered.wait(2))
                    self.assertTrue(retry_waiting.wait(2))
                    self.assertEqual(str(app.recovery_save_retry_button["state"]), "disabled")
                    heartbeat_before_retry = app._heartbeat_state
                    self.wait_for_ui(root,
                                     lambda: app._heartbeat_state != heartbeat_before_retry,
                                     timeout=1.5)
                    self.assertNotEqual(app._heartbeat_state, heartbeat_before_retry)
                    self.assertFalse(release_retry.is_set())
                    ui_tick = threading.Event()
                    root.after(0, ui_tick.set)
                    root.update()
                    self.assertTrue(ui_tick.is_set())
                    app.recovery_save_retry_button.invoke()
                    self.assertEqual(write_number[0], 2)
                    release_retry.set()
                    deadline = time.monotonic() + 3
                    while (coordinator.snapshot().save_state != "failed" or
                           str(app.recovery_save_retry_button["state"]) != "normal") and time.monotonic() < deadline:
                        root.update()
                        time.sleep(0.01)
                    self.assertEqual(coordinator.snapshot().save_state, "failed")
                    self.assertEqual(str(app.recovery_save_retry_button["state"]), "normal")
                    ui_tick.clear()
                    root.after(0, ui_tick.set)
                    root.update()
                    self.assertTrue(ui_tick.is_set())
                    app.recovery_save_retry_button.invoke()
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
                release_retry.set()
                app.hotkey.close()
                root.destroy()

    def test_real_tk_can_select_and_retry_previous_round_without_changing_current_board(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.deiconify()
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
                app.round_alarm_button.invoke()
                app.recovery_tabs.select(1)
                root.update()
                previous_index = app._recovery_save_ids.index(previous.round_id)
                app.recovery_save_list.selection_clear(0, "end")
                app.recovery_save_list.selection_set(previous_index)
                app.recovery_save_list.event_generate("<<ListboxSelect>>")
                root.update()
                self.assertEqual(str(app.recovery_save_retry_button["state"]), "normal")
                self.assertIn("temporary previous round UI fault",
                              app.recovery_save_detail.get("1.0", "end-1c"))

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
                    app.recovery_save_retry_button.invoke()
                    self.assertTrue(retry_entered.wait(2))
                    self.assertEqual(str(app.recovery_save_retry_button["state"]), "disabled")
                    ui_tick = threading.Event()
                    root.after(0, ui_tick.set)
                    root.update()
                    self.assertTrue(ui_tick.is_set())
                    app.recovery_save_retry_button.invoke()
                    self.assertEqual(len(attempts), 1)
                    release_retry.set()
                self.assertTrue(pump_until(
                        lambda: coordinator.round_snapshot(previous.round_id) is None))

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
            root.deiconify()
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
            self.set_language_for_test_setup(app, root, TRADITIONAL_CHINESE)
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
                root.update()
                self.assertFalse(app.review_badge.winfo_ismapped())
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
            self.set_language_for_test_setup(app, root, TRADITIONAL_CHINESE)
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
                           and app.rounds.snapshot().results[0].status == "PASS"
                           and app.rounds.snapshot().source_ready
                           and app.rounds.snapshot().results[1].status == "TESTING")
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
                self.assertEqual(app.review_badge.itemcget(
                    app.review_badge_label, "text"), "3")
                self.assertTrue(app.review_badge.winfo_ismapped())
                self.assertEqual(len(app.rounds.snapshot().pending_conflicts), 3)

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
                self.assertEqual(app.review_badge.itemcget(
                    app.review_badge_label, "text"), "4")
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
                pump_until(lambda: len(app.rounds.snapshot().pending_conflicts) == 5
                           and app.review_badge.itemcget(
                               app.review_badge_label, "text") == "5")
                self.assertEqual(app.review_badge.itemcget(
                    app.review_badge_label, "text"), "5")
                self.assertEqual(app.conflict_list.curselection(), (1,))
                app.review_button.invoke()
                root.update_idletasks()
                self.assertTrue(app.conflict_window.winfo_viewable())
                self.assertEqual(app.review_badge.itemcget(
                    app.review_badge_label, "text"), "5")
                self.assertIn(second_id, app.conflict_details.get("1.0", "end"))

                for index in range(6, 13):
                    self.assertEqual(source.offer_candidate(
                        1, "SN-CANDIDATE-{}".format(index), "FAIL",
                        "/controlled/slot1/candidate-{}.csv".format(index),
                        "candidate-{}".format(index),
                        "2026-10-08T10:{:02d}:00".format(index)), "defer")
                pump_until(lambda: len(app.rounds.snapshot().pending_conflicts) == 12
                           and app.conflict_list.size() == 12
                           and app.review_badge.itemcget(
                               app.review_badge_label, "text") == "12")
                badge_text = app.review_badge.itemcget(app.review_badge_label, "text")
                self.assertEqual(badge_text, "12")
                self.assertNotIn("+", badge_text)

                # Expire this real RoundCoordinator round deterministically so
                # both independent toolbar indicators are visible together.
                current_round = app.rounds._current
                current_round._apply_deadlines(current_round._started_monotonic + 3601)
                self.assertTrue(app.rounds.flush_session(timeout=3))
                pump_until(lambda: app.rounds.archive_status(started.round_id) is not None)
                app._refresh_round_alarm()
                if app.round_alarm_window and app.round_alarm_window.winfo_exists():
                    app.round_alarm_window.withdraw()
                pump_until(lambda: app._pending_notification_count() == 1)
                root.update_idletasks()
                self.assertEqual(app.review_badge.itemcget(
                    app.review_badge_label, "text"), "12")
                self.assertEqual(app.notification_badge.itemcget(
                    app._notification_badge_label, "text"), "1")
                self.assertTrue(app.review_badge.winfo_ismapped())
                self.assertTrue(app.notification_badge.winfo_ismapped())
                app.round_alarm_button.invoke()
                pump_until(lambda: app.recovery_window is not None and
                           app.recovery_window.winfo_viewable())
                self.assertEqual(app._pending_notification_count(), 1)
                self.assertEqual(app.review_badge.itemcget(
                    app.review_badge_label, "text"), "12")
                app.recovery_window.withdraw()

                def rectangle(widget):
                    return (widget.winfo_rootx(), widget.winfo_rooty(),
                            widget.winfo_width(), widget.winfo_height())

                review_badge = rectangle(app.review_badge)
                alarm_button = rectangle(app.round_alarm_button)
                alarm_badge = rectangle(app.notification_badge)
                language_button = rectangle(app.language_button)
                self.assertLessEqual(review_badge[0] + review_badge[2], alarm_button[0])
                if app.notification_badge.winfo_ismapped():
                    self.assertLessEqual(alarm_badge[0] + alarm_badge[2], language_button[0])
                self.assertGreaterEqual(review_badge[0], root.winfo_rootx())
                self.assertLessEqual(review_badge[0] + review_badge[2],
                                     root.winfo_rootx() + root.winfo_width())
                self.assertIsInstance(app.language_button, ttk.Button)
                self.assertEqual(app.language_button.cget("text"), "🌐")
                alarm_badge = rectangle(app.notification_badge)
                self.assertLessEqual(alarm_badge[0] + alarm_badge[2], language_button[0])

                if os.environ.get("B518_TK_EVIDENCE_DIR"):
                    for language, key in ((ENGLISH, "en"),
                                          (TRADITIONAL_CHINESE, "zh-TW")):
                        self.set_language_for_test_setup(app, root, language)
                        self.assertEqual(app.review_badge.itemcget(
                            app.review_badge_label, "text"), "12")
                        self.assertEqual(app.notification_badge.itemcget(
                            app._notification_badge_label, "text"), "1")
                        capture_main_badge_evidence(
                            app, "st2-twelve-conflicts", key,
                            {"settings": app.settings_button,
                             "logo": app.company_logo_slot,
                             "review": app.review_button,
                             "review_badge": app.review_badge,
                             "bell": app.round_alarm_button,
                             "bell_badge": app.notification_badge,
                             "language": app.language_button,
                             "kvm": app.kvm_results,
                             "kvm_state_marker": app.kvm_state_marker,
                             "kvm_layout_marker": app.kvm_layout_marker})
                    self.set_language_for_test_setup(app, root, TRADITIONAL_CHINESE)

                app.resolve_conflict_candidate_button.invoke()
                pump_until(lambda: len(app.rounds.snapshot().pending_conflicts) == 11
                           and second_id not in {item.conflict_id
                                                 for item in app.rounds.snapshot().pending_conflicts}
                           and app.review_badge.itemcget(
                               app.review_badge_label, "text") == "11")
                self.assertEqual(app.review_badge.itemcget(
                    app.review_badge_label, "text"), "11")
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
                self.assertEqual(len(detected), 12)
                self.assertEqual(len(resolved), 12)
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
            self.set_language_for_test_setup(app, root, TRADITIONAL_CHINESE)

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
            self.set_language_for_test_setup(app, root, TRADITIONAL_CHINESE)
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
                                 (960, 600))
                conflict_x = app.conflict_window.winfo_rootx()
                conflict_y = app.conflict_window.winfo_rooty()
                self.assertGreaterEqual(conflict_x, 0)
                self.assertGreaterEqual(conflict_y, 0)
                self.assertLessEqual(conflict_x + app.conflict_window.winfo_width(),
                                     root.winfo_screenwidth())
                self.assertLessEqual(conflict_y + app.conflict_window.winfo_height(),
                                     root.winfo_screenheight())
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
                app.rounds.request_close()
                self.wait_for(lambda: app.rounds.close_status().status in {"complete", "failed"})
                self.assertEqual(app.rounds.close_status().status, "complete")
            finally:
                if app._round_is_active():
                    app.rounds.stop()
                app.rounds.flush_session(timeout=3)
                app.rounds.flush_audit(timeout=3)
                app.rounds.request_close()
                self.wait_for(lambda: app.rounds.close_status().status in {"complete", "failed"})
                app._close_settings()
                app.hotkey.close()
                root.update()
                root.destroy()

    def test_real_tk_conflict_selection_keeps_both_sections_on_same_snapshot(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.deiconify()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey, session_root=Path(temporary) / "sessions",
            )
            self.set_language_for_test_setup(app, root, TRADITIONAL_CHINESE)
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
            self.set_language_for_test_setup(app, root, TRADITIONAL_CHINESE)

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

    def test_main_title_preserves_build_version_through_language_and_station_changes(self):
        root = tk.Tk()
        with patch("b518_log_solution.APP_VERSION", "9.8.7"):
            app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey)
            try:
                for language in (ENGLISH, TRADITIONAL_CHINESE):
                    app._select_language(language)
                    for station in ("FCT", "BT"):
                        app.station.set(station)
                        app._render_main_title()
                        self.assertEqual(root.title(),
                                         "B518 {} ATE Log Solution-V9.8.7".format(station))
            finally:
                root.destroy()

    def test_fixed_hmi_geometry_survives_mapping_and_capacity_changes(self):
        root = tk.Tk()
        app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey)
        try:
            self.wait_for_ui(root, lambda: root.winfo_ismapped())
            for capacity in (2, 10, 20, 2):
                with self.subTest(capacity=capacity), patch.object(
                        app, "_display_capacity", return_value=capacity):
                    app._render_rows()
                    self.wait_for_ui(root, lambda:
                        root.winfo_width() == WINDOW_WIDTH and
                        root.winfo_height() == window_height(capacity, root.winfo_screenheight()))
                    self.assertEqual(root.winfo_width(), WINDOW_WIDTH)
                    self.assertEqual(root.winfo_height(),
                                     window_height(capacity, root.winfo_screenheight()))
                    self.assertEqual(tuple(map(int, root.resizable())), (0, 0))
                    self.assertEqual((app.kvm_state_marker.winfo_x(),
                                      app.kvm_state_marker.winfo_y()), (250, 0))
        finally:
            root.destroy()

    def test_twenty_position_profile_renders_two_fixed_bands_and_scrollable_details(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.deiconify()
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
                self.assertEqual(app.kvm_state_marker.winfo_x(), 250)
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
            root.deiconify()
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

                app.profile_editor_project.set("B518")
                app.profile_editor_machine.set("FCT")
                app.profile_editor_platform.set("atlas")
                app.profile_editor_capacity.set("2")
                app.profile_editor_paths["active"].set("/deployment/fct-active")
                app.profile_editor_paths["final"].set("/deployment/fct-final")
                app.profile_editor_mapping.set("1:1, 2:2")
                app.profile_editor_timeouts["start"].set("180")
                app._apply_profile_editor()

                fct_saved = app.profiles.get("B518", "FCT")
                self.assertEqual(fct_saved.timeouts["start"], 180)
                self.assertEqual(MachineProfileStore(Path(temporary) / "preferences.json").load()[0]
                                 .get("B518", "FCT").timeouts["start"], 180)

                app.profile_editor_project.set("Demo")
                app.profile_editor_machine.set("DFU")
                app._load_profile_editor_selection()
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
        root.deiconify()
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
            root.deiconify()
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
                root.deiconify()
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
                deploy_root.deiconify()
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

    def test_awaiting_review_start_entrypoints_share_admission_without_side_effects(self):
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
            app._save_preferences()
            preferences_before = (Path(temporary) / "preferences.json").read_bytes()
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

                # The button and both shortcuts share the same admission gate while a
                # round awaits review; rejected starts must not persist changed settings.
                app.station.set("DFU")
                app._profile_changed()
                app.start_button.invoke()
                self.assertEqual((Path(temporary) / "preferences.json").read_bytes(),
                                 preferences_before)
                self.assertEqual(app.rounds.snapshot().round_id, original_round_id)

                app.station.set("FCT")
                root.event_generate("<Command-Shift-M>")
                root.update()
                self.assertEqual(app.rounds.snapshot().round_id, original_round_id)
                self.assertEqual((Path(temporary) / "preferences.json").read_bytes(),
                                 preferences_before)

                app.station.set("DFU")
                app.hotkey.callback()
                root.update()
                self.assertEqual(app.rounds.snapshot().round_id, original_round_id)
                self.assertEqual((Path(temporary) / "preferences.json").read_bytes(),
                                 preferences_before)
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
        # The two profile rows and save/archive/diagnostic controls stay visible.
        self.assertEqual(window_height(4), 761)
        self.assertEqual(window_height(6), 808)
        self.assertEqual(window_height(7), 808)
        self.assertEqual(window_height(20), 835)
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
        root.deiconify()
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

    def assert_start_failure_blocks_until_explicit_reset(self, app, root, diagnostic,
                                                       accepted=False):
        failed = app.rounds.snapshot()
        self.assertEqual(failed.state, RoundState.AWAITING_REVIEW)
        self.assertEqual(bool(failed.round_id), accepted)
        self.assertEqual(failed.completion_reason, "start_failed")
        self.assertEqual(failed.start_failure.diagnostic, diagnostic)
        self.assertFalse(failed.result_available)
        self.assertEqual(str(app.start_button.cget("state")), "disabled")
        self.assertEqual(str(app.reset_start_failure_button.cget("state")), "normal")
        request_id = failed.start_failure.request_id
        app.start_monitor()
        self.assertEqual(app.rounds.snapshot().start_failure.request_id, request_id)
        app.reset_start_failure_button.invoke()
        root.update()
        self.assertIsNone(app.rounds.start_failure_snapshot())
        self.assertFalse(app._round_is_active())
        self.assertEqual(str(app.start_button.cget("state")), "normal")
        if accepted:
            reset = app.rounds.snapshot()
            self.assertEqual(reset.round_id, failed.round_id)
            self.assertEqual(reset.completion_reason, "start_failed_cancelled")
            self.assertFalse(reset.result_available)
        else:
            self.assertIsNone(app.rounds.snapshot())

    def test_empty_paths_are_rejected_before_monitor_creation(self):
        root = tk.Tk()
        root.deiconify()
        app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey)
        app.station.set("DFU")
        profile = app.profiles.get("B518", "DFU")
        app.profiles = app.profiles.with_profile(replace(profile, paths={"active": "", "final": ""}))
        try:
            with patch("b518_log_solution.DEFAULT_PLATFORM_REGISTRY.create_monitor") as monitor_type, \
                    patch("b518_log_solution.show_notice") as show_error:
                app.start_button.invoke()
            monitor_type.assert_not_called()
            show_error.assert_called_once()
            self.assertEqual(show_error.call_args.args[:2], (
                "Configuration Error",
                "The selected configuration is invalid: See the original diagnostic below.\n\n"
                "Original diagnostic: 請設定存在且可讀取的Atlas 即時 Log 路徑。",
            ))
            self.assert_start_failure_blocks_until_explicit_reset(
                app, root, "請設定存在且可讀取的Atlas 即時 Log 路徑。")
            monitor_type.assert_not_called()
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
                        patch("b518_log_solution.show_notice") as show_error:
                    app.start_button.invoke()

                self.assert_start_failure_blocks_until_explicit_reset(app, root, "disk full")
                self.assertEqual(app.monitor_state.cget("text"), "Standby")
                self.assertEqual(app.profile_store.path.read_bytes(), preferences_before)
                self.assertEqual(show_error.call_args.args[:2], (
                    "Configuration Save Failed",
                    "Configuration preferences could not be saved; the active configuration remains unchanged: "
                    "See the original diagnostic below.\n\nOriginal diagnostic: disk full",
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
                root.deiconify()
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
            root.deiconify()
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
                        patch("b518_log_solution.show_notice") as show_error:
                    app.start_monitor()
                    deadline = time.monotonic() + 3
                    while not show_error.called and time.monotonic() < deadline:
                        root.update()
                        time.sleep(0.01)
                self.assertTrue(app._round_is_active())
                self.assertEqual(app.monitor_state.cget("text"), "Start Failed")
                self.assertIn("denied", app.event_lines[-1])
                show_error.assert_called_once()
                self.assert_start_failure_blocks_until_explicit_reset(
                    app, root, "denied", accepted=True)
            finally:
                app.hotkey.close()
                root.destroy()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_real_tk_button_and_hotkey_share_start_admission(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            active = Path(temporary) / "active"
            final = Path(temporary) / "final"
            active.mkdir()
            final.mkdir()
            root = tk.Tk()
            root.deiconify()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey,
                session_root=Path(temporary) / "sessions",
            )
            try:
                app.open_settings()
                app.profile_editor_machine.set("FCT")
                app.profile_editor_paths["active"].set(str(active))
                app.profile_editor_paths["final"].set(str(final))
                app._apply_profile_editor()
                app._close_settings()

                app.start_button.invoke()
                accepted = app.rounds.snapshot()
                self.assertIsNotNone(accepted)
                self.assertIn(accepted.state, {RoundState.PREPARING, RoundState.RUNNING})

                self.assertEqual(app._on_local_hotkey(None), "break")
                app._on_global_hotkey()
                app._drain_events()

                self.assertEqual(app.rounds.snapshot().round_id, accepted.round_id)
                self.assertEqual(app.active_round_id, accepted.round_id)
            finally:
                app.rounds.stop()
                app.rounds.request_close()
                self.wait_for(lambda: app.rounds.close_status().status in {"complete", "failed"})
                app.hotkey.close()
                root.destroy()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_real_tk_presentation_failure_keeps_accepted_round_and_diagnostic(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            active = Path(temporary) / "active"
            final = Path(temporary) / "final"
            active.mkdir()
            final.mkdir()
            root = tk.Tk()
            root.deiconify()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey,
                session_root=Path(temporary) / "sessions",
                app_event_path=Path(temporary) / "app-events.json",
            )
            try:
                app.open_settings()
                app.profile_editor_machine.set("FCT")
                app.profile_editor_paths["active"].set(str(active))
                app.profile_editor_paths["final"].set(str(final))
                app._apply_profile_editor()
                app._close_settings()

                with patch.object(app, "_apply_round_snapshot",
                                  side_effect=RuntimeError("render fault")), \
                        patch("b518_log_solution.show_notice") as show_notice:
                    app.start_button.invoke()

                snapshot = app.rounds.snapshot()
                self.assertIsNotNone(snapshot)
                self.assertEqual(snapshot.round_id, app.active_round_id)
                self.assertIsNone(app.rounds.start_failure_snapshot())
                self.assertEqual(str(app.stop_button.cget("state")), "normal")
                diagnostic = next(
                    record for record in app.app_events.records
                    if record["localized_message"]["message_id"] == "app.round.presentation_failed"
                )
                self.assertEqual(diagnostic["diagnostic"], "render fault")
                self.assertEqual(diagnostic["localized_message"]["parameters"]["round_id"],
                                 snapshot.round_id)
                show_notice.assert_called_once()
            finally:
                app.rounds.stop()
                app.rounds.request_close()
                self.wait_for(lambda: app.rounds.close_status().status in {"complete", "failed"})
                app.hotkey.close()
                root.destroy()

    def test_settings_expose_profile_editor_and_session_log_without_legacy_monitor_tab(self):
        root = tk.Tk()
        root.deiconify()
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
    def test_source_preparation_failure_prompt_uses_selected_language_and_keeps_diagnostic(self):
        with TemporaryDirectory() as temporary:
            active = Path(temporary) / "active"
            final = Path(temporary) / "final"
            active.mkdir()
            final.mkdir()
            root = tk.Tk()
            root.deiconify()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey,
                session_root=Path(temporary) / "sessions",
            )
            try:
                app.open_settings()
                app.profile_editor_machine.set("FCT")
                app.profile_editor_paths["active"].set(str(active))
                app.profile_editor_paths["final"].set(str(final))
                app._apply_profile_editor()
                app._close_settings()
                self.set_language_for_test_setup(app, root, TRADITIONAL_CHINESE)

                with patch("b518_log_solution.DEFAULT_PLATFORM_REGISTRY.create_monitor",
                           side_effect=PermissionError("source access denied")), \
                        patch("b518_log_solution.show_notice") as show_error:
                    app.start_button.invoke()
                    deadline = time.monotonic() + 3
                    while not show_error.called and time.monotonic() < deadline:
                        root.update()
                        time.sleep(0.01)

                    self.assertTrue(show_error.called,
                                    "The source preparation failure must be requested")
                title, message = show_error.call_args.args[:2]
                self.assertEqual(title, "啟動失敗")
                self.assertIn("FCT 監控來源準備失敗", message)
                self.assertIn("原始診斷: source access denied", message)
                failed = next(item.event for item in app.rounds.snapshot().events
                              if item.event.kind == "start_failed")
                self.assertEqual(failed.localized_message.message_id, "round.start_failed")
                self.assertEqual(failed.localized_message.diagnostic, "source access denied")
                self.assertEqual(failed.localized_message.traditional_chinese,
                                 "FCT 監控來源準備失敗")
                round_id = app.rounds.snapshot().round_id
                self.assertTrue(app.rounds.flush_audit(timeout=3))
                audit_path = Path(temporary) / "sessions" / round_id / "audit.jsonl"
                rebuilt = read_round_audit(audit_path)
                saved_failure = next(item for item in rebuilt["events"]
                                     if item["kind"] == "start_failed")
                self.assertEqual(saved_failure["localized_message"]["message_id"],
                                 "round.start_failed")
                self.assertEqual(saved_failure["localized_message"]["diagnostic"],
                                 "source access denied")
            finally:
                app.hotkey.close()
                root.destroy()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_integrated_language_refresh_keeps_open_settings_diagnostics_and_history(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.deiconify()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey,
                session_root=Path(temporary) / "sessions",
                app_event_path=Path(temporary) / "app-events.json",
            )

            def select_language(language):
                # Exercise the real Menu command without entering Aqua's
                # modal popup loop before the test can select an item.
                native_name = "English" if language == ENGLISH else "繁體中文"
                index = next(
                    item for item in range(app.language_menu.index("end") + 1)
                    if app.language_menu.entrycget(item, "label") == native_name
                )
                app.language_menu.invoke(index)
                root.update()

            try:
                self.wait_for(lambda: app.rounds.app_event_status().complete)
                app.open_settings()
                settings_window = app.settings_window
                app.profile_editor_project.set("Unsaved Integrated Draft")
                selected_tab = app.settings_notebook.tabs()[2]
                app.settings_notebook.select(selected_tab)

                app.open_app_diagnostics()
                diagnostics_window = app.app_diagnostics_window
                diagnostic_records = app.rounds.app_event_records()
                diagnostic_index = next(
                    index for index, record in enumerate(diagnostic_records)
                    if record.get("localized_message", {}).get("message_id")
                    == "app.startup.started"
                )
                self.assertGreater(app.app_diagnostics_list.size(), diagnostic_index)
                app.app_diagnostics_list.selection_set(diagnostic_index)
                app.app_diagnostics_list.event_generate("<<ListboxSelect>>")
                root.update()
                diagnostic_selection = tuple(app.app_diagnostics_list.curselection())
                diagnostic_row_english = app.app_diagnostics_list.get(diagnostic_index)
                diagnostic_detail_english = app.app_diagnostics_detail.get(
                    "1.0", "end-1c")
                self.assertIn("Application started", diagnostic_row_english)
                self.assertIn("Application started", diagnostic_detail_english)

                app.open_historical_events()
                app.historical_event_refresh_button.invoke()
                self.wait_for_ui(root, lambda: app._historical_query_result is not None)
                history_window = app.historical_event_window
                self.assertEqual(
                    app.historical_event_cancel_button.cget("text"),
                    app._t("app.settings.history.cancel_query"))
                history_index = next(
                    index for index, event in enumerate(app._historical_event_records)
                    if (event.localized_message or {}).get("message_id")
                    == "app.startup.started"
                )
                self.assertGreater(app.historical_event_list.size(), history_index)
                app.historical_event_list.selection_set(history_index)
                app.historical_event_list.event_generate("<<ListboxSelect>>")
                root.update()
                self.wait_for_ui(
                    root, lambda: app._historical_event_detail_request_id is None)
                history_selection = tuple(app.historical_event_list.curselection())
                history_row_english = app.historical_event_list.get(history_index)
                history_detail_english = app.historical_event_detail.get("1.0", "end-1c")
                self.assertIn("Application started", history_row_english)
                self.assertIn("Application started", history_detail_english)

                event_bytes = app.app_events.path.read_bytes()
                event_revision = app.rounds.app_event_revision()
                with patch.object(
                        app.rounds, "app_event_records",
                        side_effect=AssertionError("language refresh re-read App events")), \
                        patch("b518_log_solution.query_historical_events",
                              side_effect=AssertionError(
                                  "language refresh re-read historical sources")):
                    select_language(TRADITIONAL_CHINESE)
                self.assertIs(app.settings_window, settings_window)
                self.assertIs(app.app_diagnostics_window, diagnostics_window)
                self.assertIs(app.historical_event_window, history_window)
                self.assertTrue(all(window.winfo_exists() for window in (
                    settings_window, diagnostics_window, history_window,
                )))
                self.assertEqual(app.profile_editor_project.get(), "Unsaved Integrated Draft")
                self.assertEqual(app.settings_notebook.select(), selected_tab)
                self.assertEqual(tuple(app.app_diagnostics_list.curselection()),
                                 diagnostic_selection)
                self.assertEqual(tuple(app.historical_event_list.curselection()), history_selection)
                self.assertEqual(settings_window.title(), app._t("app.settings.title"))
                self.assertEqual(diagnostics_window.title(), app._t("app.diagnostic.heading"))
                self.assertEqual(history_window.title(), app._t("app.settings.history.title"))
                self.assertEqual(app.historical_event_cancel_button.cget("text"), "取消查詢")
                self.assertIn("App 已啟動", app.app_diagnostics_list.get(diagnostic_index))
                self.assertIn("App 已啟動", app.app_diagnostics_detail.get("1.0", "end-1c"))
                self.assertNotEqual(app.app_diagnostics_list.get(diagnostic_index),
                                    diagnostic_row_english)
                self.assertNotEqual(app.app_diagnostics_detail.get("1.0", "end-1c"),
                                    diagnostic_detail_english)
                self.assertIn("App 已啟動", app.historical_event_list.get(history_index))
                self.assertIn("App 已啟動", app.historical_event_detail.get("1.0", "end-1c"))
                self.assertNotEqual(app.historical_event_list.get(history_index),
                                    history_row_english)
                self.assertNotEqual(app.historical_event_detail.get("1.0", "end-1c"),
                                    history_detail_english)
                self.assertEqual(event_bytes, app.app_events.path.read_bytes())
                self.assertEqual(app.rounds.app_event_revision(), event_revision)

                select_language(ENGLISH)
                self.assertIs(app.settings_window, settings_window)
                self.assertIs(app.app_diagnostics_window, diagnostics_window)
                self.assertIs(app.historical_event_window, history_window)
                self.assertEqual(app.historical_event_cancel_button.cget("text"), "Cancel search")
                self.assertEqual(app.profile_editor_project.get(), "Unsaved Integrated Draft")
                self.assertEqual(tuple(app.app_diagnostics_list.curselection()),
                                 diagnostic_selection)
                self.assertEqual(tuple(app.historical_event_list.curselection()), history_selection)
                self.assertIn("Application started",
                              app.app_diagnostics_list.get(diagnostic_index))
                self.assertIn("Application started",
                              app.app_diagnostics_detail.get("1.0", "end-1c"))
                self.assertIn("Application started",
                              app.historical_event_list.get(history_index))
                self.assertIn("Application started",
                              app.historical_event_detail.get("1.0", "end-1c"))
                self.assertEqual(event_bytes, app.app_events.path.read_bytes())
                self.assertEqual(app.rounds.app_event_revision(), event_revision)

                # Close through the configured WM protocol, destroy another
                # view directly, and keep the history view merely hidden.
                root.tk.call(settings_window.protocol("WM_DELETE_WINDOW"))
                diagnostics_window.destroy()
                history_window.withdraw()
                root.update()
                select_language(TRADITIONAL_CHINESE)
                self.assertTrue(history_window.winfo_exists())
                self.assertFalse(history_window.winfo_viewable())
                self.assertEqual(history_window.title(), app._t("app.settings.history.title"))
                app.open_settings()
                app.open_app_diagnostics()
                self.assertNotEqual(app.settings_window, settings_window)
                self.assertNotEqual(app.app_diagnostics_window, diagnostics_window)
                self.assertEqual(app.settings_window.title(), app._t("app.settings.title"))
                self.assertEqual(app.app_diagnostics_window.title(),
                                 app._t("app.diagnostic.heading"))
                app.open_historical_events()
                self.assertIs(app.historical_event_window, history_window)
                self.assertTrue(history_window.winfo_viewable())
            finally:
                if app.historical_event_window and app.historical_event_window.winfo_exists():
                    app._close_historical_event_window()
                if app.app_diagnostics_window and app.app_diagnostics_window.winfo_exists():
                    app._close_app_diagnostics_window()
                app._close_settings()
                app.hotkey.close()
                root.destroy()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_settings_refresh_failure_isolated_and_retried_from_main_window(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.deiconify()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey,
                session_root=Path(temporary) / "sessions",
                app_event_path=Path(temporary) / "app-events.json",
            )

            def select_language(language):
                # Exercise the real Menu command without entering Aqua's
                # modal popup loop before the test can select an item.
                native_name = "English" if language == ENGLISH else "繁體中文"
                index = next(
                    item for item in range(app.language_menu.index("end") + 1)
                    if app.language_menu.entrycget(item, "label") == native_name
                )
                app.language_menu.invoke(index)
                root.update()

            try:
                self.wait_for(lambda: app.rounds.app_event_status().complete)
                app.open_settings()
                settings_window = app.settings_window
                app.profile_editor_project.set("Keep this draft")
                app.open_app_diagnostics()
                diagnostics_window = app.app_diagnostics_window
                app.open_historical_events()
                history_window = app.historical_event_window

                with patch.object(settings_window, "title",
                                  side_effect=RuntimeError("settings refresh unavailable")):
                    select_language(TRADITIONAL_CHINESE)

                self.assertIs(app.settings_window, settings_window)
                self.assertIs(app.app_diagnostics_window, diagnostics_window)
                self.assertIs(app.historical_event_window, history_window)
                self.assertEqual(app.profile_editor_project.get(), "Keep this draft")
                self.assertEqual(app.app_event_status_label.cget("text"), "文字更新失敗")
                self.assertIn("App 診斷", app.app_diagnostics_window.title())
                self.assertIn("事件", app.historical_event_heading.cget("text"))
                self.assertEqual(str(self.diagnostics_language_retry(app).cget("state")), "normal")

                path = app.app_events.path
                self.wait_for(lambda: app.rounds.app_event_status().complete)
                memory_records = app.rounds.app_event_records()
                failure = next(record for record in memory_records
                               if record["localized_message"]["message_id"] ==
                               "app.language.refresh_failed")
                self.assertIsNone(failure.get("round_id"))
                self.assertEqual(failure["diagnostic"],
                                 "設定: settings refresh unavailable")
                disk_records = read_app_event_store(path)["events"]
                self.assertIn(failure["event_id"],
                              [record["event_id"] for record in disk_records])

                self.diagnostics_language_retry(app).event_generate("<ButtonPress-1>")
                self.diagnostics_language_retry(app).event_generate("<ButtonRelease-1>")
                root.update()
                self.assertEqual(settings_window.title(), app._t("app.settings.title"))
                self.assertEqual(app.profile_editor_project.get(), "Keep this draft")
                self.assertEqual(str(self.diagnostics_language_retry(app).cget("state")),
                                 "disabled")
                self.assertEqual(app.app_event_status_label.cget("text"),
                                 app.app_event_status_label.cget("text"))
            finally:
                if app.historical_event_window and app.historical_event_window.winfo_exists():
                    app._close_historical_event_window()
                if app.app_diagnostics_window and app.app_diagnostics_window.winfo_exists():
                    app._close_app_diagnostics_window()
                app._close_settings()
                app.hotkey.close()
                app.rounds.request_close()
                self.wait_for(lambda: app.rounds.close_status().status == "complete")
                self.wait_for(lambda: app.rounds.app_event_status().complete)
                root.destroy()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_each_reader_refresh_failure_isolated_and_retryable(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.deiconify()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey,
                session_root=Path(temporary) / "sessions",
                app_event_path=Path(temporary) / "app-events.json",
            )

            def select_language(language):
                # Exercise the real Menu command without entering Aqua's
                # modal popup loop before the test can select an item.
                native_name = "English" if language == ENGLISH else "繁體中文"
                index = next(
                    item for item in range(app.language_menu.index("end") + 1)
                    if app.language_menu.entrycget(item, "label") == native_name
                )
                app.language_menu.invoke(index)
                root.update()

            def click(widget):
                x, y = widget.winfo_width() // 2, widget.winfo_height() // 2
                widget.event_generate("<ButtonPress-1>", x=x, y=y)
                widget.event_generate("<ButtonRelease-1>", x=x, y=y)
                root.update()

            try:
                self.wait_for(lambda: app.rounds.app_event_status().complete)
                app.open_settings()
                app.profile_editor_project.set("Preserve this draft")
                settings_window = app.settings_window
                app.open_app_diagnostics()
                diagnostics_window = app.app_diagnostics_window
                app.open_historical_events()
                history_window = app.historical_event_window
                windows = {
                    "settings": settings_window,
                    "diagnostics": diagnostics_window,
                    "history": history_window,
                }
                failure_cases = (("settings",), ("diagnostics",), ("history",),
                                 ("settings", "diagnostics"))
                language = ENGLISH
                for failed_views in failure_cases:
                    language = (TRADITIONAL_CHINESE if language == ENGLISH else ENGLISH)
                    patchers = [patch.object(
                        windows[name], "title",
                        side_effect=RuntimeError("{} refresh unavailable".format(name)),
                    ) for name in failed_views]
                    for patcher in patchers:
                        patcher.start()
                    try:
                        select_language(language)
                    finally:
                        for patcher in reversed(patchers):
                            patcher.stop()

                    self.assertTrue(all(window.winfo_exists() for window in windows.values()))
                    self.assertEqual(app.profile_editor_project.get(), "Preserve this draft")
                    self.assertEqual(settings_window.title() == app._t("app.settings.title"),
                                     "settings" not in failed_views)
                    self.assertEqual(diagnostics_window.title() ==
                                     app._t("app.diagnostic.heading"),
                                     "diagnostics" not in failed_views)
                    self.assertEqual(history_window.title() ==
                                     app._t("app.settings.history.title"),
                                     "history" not in failed_views)
                    self.assertEqual(app.app_event_status_label.cget("text"),
                                     "文字更新失敗" if language == TRADITIONAL_CHINESE
                                     else "Text refresh failed")
                    self.assertEqual(str(self.diagnostics_language_retry(app).cget("state")),
                                     "normal")

                    click(self.diagnostics_language_retry(app))
                    self.assertEqual(settings_window.title(), app._t("app.settings.title"))
                    self.assertEqual(diagnostics_window.title(),
                                     app._t("app.diagnostic.heading"))
                    self.assertEqual(history_window.title(),
                                     app._t("app.settings.history.title"))
                    self.assertEqual(app.profile_editor_project.get(), "Preserve this draft")
                    self.assertEqual(str(self.diagnostics_language_retry(app).cget("state")),
                                     "disabled")
                    self.assertEqual(app.app_event_status_label.cget("text"),
                                     app.app_event_status_label.cget("text"))
            finally:
                if app.historical_event_window and app.historical_event_window.winfo_exists():
                    app._close_historical_event_window()
                if app.app_diagnostics_window and app.app_diagnostics_window.winfo_exists():
                    app._close_app_diagnostics_window()
                app._close_settings()
                app.rounds.request_close()
                self.wait_for(lambda: app.rounds.close_status().status == "complete")
                root.destroy()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_app_diagnostics_scroll_position_survives_language_refresh(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.deiconify()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey,
                session_root=Path(temporary) / "sessions",
                app_event_path=Path(temporary) / "app-events.json",
            )

            def select_language(language):
                # Exercise the real Menu command without entering Aqua's
                # modal popup loop before the test can select an item.
                native_name = "English" if language == ENGLISH else "繁體中文"
                index = next(
                    item for item in range(app.language_menu.index("end") + 1)
                    if app.language_menu.entrycget(item, "label") == native_name
                )
                app.language_menu.invoke(index)
                root.update()

            try:
                self.wait_for(lambda: app.rounds.app_event_status().complete)
                diagnostic = "raw diagnostic line\n" * 100
                app.rounds.record_app_event("app.startup.started", {}, diagnostic)
                self.wait_for(lambda: app.rounds.app_event_status().complete)
                app.open_app_diagnostics()
                records = app.rounds.app_event_records()
                selected_index = next(
                    index for index, record in enumerate(records)
                    if record.get("diagnostic") == diagnostic
                )
                app.app_diagnostics_list.selection_set(selected_index)
                app.app_diagnostics_list.event_generate("<<ListboxSelect>>")
                root.update_idletasks()
                app.app_diagnostics_detail.yview_moveto(0.55)
                root.update_idletasks()
                selected_id = app._selected_app_event_id
                detail_top = app.app_diagnostics_detail.index("@0,0")
                detail_yview = app.app_diagnostics_detail.yview()[0]
                self.assertGreater(detail_yview, 0.4)

                select_language(TRADITIONAL_CHINESE)
                root.update_idletasks()
                self.assertEqual(app._selected_app_event_id, selected_id)
                self.assertEqual(app.app_diagnostics_detail.index("@0,0"), detail_top)
                self.assertAlmostEqual(app.app_diagnostics_detail.yview()[0],
                                       detail_yview, places=2)
                self.assertIn(diagnostic,
                              app.app_diagnostics_detail.get("1.0", "end-1c"))
                self.assertIn("App 已啟動", app.app_diagnostics_detail.get("1.0", "end-1c"))
            finally:
                if app.app_diagnostics_window and app.app_diagnostics_window.winfo_exists():
                    app._close_app_diagnostics_window()
                app.rounds.request_close()
                self.wait_for(lambda: app.rounds.close_status().status == "complete")
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
                    chinese_index = next(
                        index for index in range(app.language_menu.index("end") + 1)
                        if app.language_menu.entrycget(index, "label") == "繁體中文"
                    )
                    app.language_menu.invoke(chinese_index)
                    root.update()
                    self.assertIn("關閉保存期間暫停清理", app.retention_cleanup_status.get())
                    visible_reason, raw_details = app.retention_cleanup_status.get().split("\n", 1)
                    self.assertNotIn("Cleanup paused", visible_reason)
                    self.assertIn('"en": "Cleanup paused while records are being saved for app close."',
                                  raw_details)
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
    def test_real_tk_cleanup_status_shows_captured_reason_details_during_close(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"), \
                patch.object(RoundCoordinator, "start_retention_schedule", return_value=None):
            root = tk.Tk()
            root.deiconify()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey,
                session_root=Path(temporary) / "sessions",
                app_event_path=Path(temporary) / "app-events.json",
            )
            write_entered = threading.Event()
            release_write = threading.Event()
            atomic_replace = app_event_store._atomic_replace

            def hold_event_write(path, content):
                write_entered.set()
                if not release_write.wait(5):
                    raise OSError("test write gate timed out")
                atomic_replace(path, content)

            def click(widget):
                x, y = widget.winfo_width() // 2, widget.winfo_height() // 2
                widget.event_generate("<ButtonPress-1>", x=x, y=y)
                widget.event_generate("<ButtonRelease-1>", x=x, y=y)
                root.update()

            try:
                app.open_settings()
                app.settings_notebook.select(2)
                app.rounds.request_retention_cleanup(app.profile_store.retention_days,
                                                     "c4-status-detail")
                self.wait_for(lambda: app.rounds.retention_cleanup_status().status == "complete")
                self.set_language_for_test_setup(app, root, ENGLISH)
                with patch("app_event_store._atomic_replace", side_effect=hold_event_write):
                    app.rounds.record_app_event("app.settings.event.retention.saved", {"days": 365})
                    self.wait_for(write_entered.is_set)
                    app.rounds.request_close()
                    self.wait_for(lambda: app.rounds.close_status().status in {"saving", "waiting"})
                    app.retention_days_var.set(str(app.profile_store.retention_days))
                    click(app.retention_save_button)
                    self.assertIn("Background cleanup was skipped:",
                                  app.retention_cleanup_status.get())
                    self.assertIn('"en": "Cleanup paused while records are being saved for app close."',
                                  app.retention_cleanup_status.get())

                    summaries_before_language_change = len(
                        app.rounds.retention_cleanup_summaries())
                    ledger_path = Path(temporary) / "round-retention-ledger.json"
                    ledger_before_language_change = ledger_path.read_bytes()
                    self.set_language_for_test_setup(app, root, TRADITIONAL_CHINESE)
                    self.assertIn("關閉保存期間暫停清理", app.retention_cleanup_status.get())
                    self.assertIn('"zh-TW": "關閉保存期間暫停清理。"',
                                  app.retention_cleanup_status.get())
                    self.assertEqual(len(app.rounds.retention_cleanup_summaries()),
                                     summaries_before_language_change)
                    self.assertEqual(ledger_path.read_bytes(), ledger_before_language_change)
                    release_write.set()
                    self.wait_for(lambda: app.rounds.app_event_status().complete)
                    self.wait_for(lambda: app.rounds.close_status().status == "complete")
            finally:
                release_write.set()
                app._close_settings()
                app.rounds.request_close()
                self.wait_for(lambda: app.rounds.close_status().status == "complete")
                self.wait_for(lambda: app.rounds.app_event_status().complete)
                app.hotkey.close()
                app.app_events.stop()
                root.destroy()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_real_tk_historical_reader_selects_and_localizes_disk_records_without_rewriting(self):
        from audit_records import AuditEvent, RoundAuditStore
        from language_catalog import make_bilingual_message

        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root_path = Path(temporary)
            session_root = root_path / "sessions"
            app_path = root_path / "app-events.json"
            legacy_path = session_root / "legacy-session" / "events.log"
            legacy_path.parent.mkdir(parents=True)
            legacy_path.write_text(json.dumps({
                "timestamp": "2026-10-08T10:00:03+08:00",
                "message": "Legacy operator note — keep this original wording",
                "detail": {"operator_note": "raw legacy detail"},
            }, ensure_ascii=False) + "\nnot-json legacy evidence\n", encoding="utf-8")
            legacy_before = legacy_path.read_bytes()
            audit = RoundAuditStore(
                session_root, "round-history-1", "FCT", "2026-10-08T10:00:00+08:00",
                10.0, {"platform": "atlas"},
            )
            audit.append_event(AuditEvent(1, "round_started", "FCT 本輪已接受開始", None),
                               "2026-10-08T10:00:02+08:00", 1.0)
            audit.append_event(AuditEvent(
                2, "final", "slot1 最終 PASS", 1, "SN-HISTORY", "PASS",
                "/sources/history.csv", {}, make_bilingual_message(
                    "platform.atlas.final", {"station": "FCT", "slot": 1, "status": "PASS"}),
            ), "2026-10-08T10:00:02+08:00", 2.0)
            long_diagnostic = "diagnostic evidence " * 500
            for sequence in range(3, 151):
                detail = {"raw_diagnostic": long_diagnostic} if sequence == 50 else {}
                audit.append_event(AuditEvent(
                    sequence, "round_ready", "FCT 來源已就緒", None,
                    detail=detail,
                ), "2026-10-08T10:00:02+08:00", float(sequence))
            self.assertTrue(audit.flush())
            audit_path = audit.audit_path
            audit_before = audit_path.read_bytes()

            root = tk.Tk()
            app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey,
                                     session_root=session_root, app_event_path=app_path,
                                     app_event_clock=lambda: datetime(
                                         2026, 10, 9, 2, 3, 4, tzinfo=timezone.utc))

            def click_history_row(index):
                app.historical_event_list.see(index)
                root.update()
                bounds = app.historical_event_list.bbox(index)
                self.assertIsNotNone(bounds)
                x, y, _width, height = bounds
                point = (max(5, x + 5), y + max(1, height // 2))
                app.historical_event_list.event_generate(
                    "<ButtonPress-1>", x=point[0], y=point[1])
                app.historical_event_list.event_generate(
                    "<ButtonRelease-1>", x=point[0], y=point[1])
                root.update()
                self.wait_for_ui(root, lambda: app._historical_event_detail_request_id is None)

            def select_language_with_real_menu(language):
                index = next(i for i in range(app.language_menu.index("end") + 1)
                             if app.language_menu.entrycget(i, "label") == language_name(language))
                app.language_menu.invoke(index)
                root.update()

            try:
                self.wait_for(lambda: app.app_events.status().complete)
                app_events_before = app_path.read_bytes()
                expected_total = 151 + len(app.app_events.records)
                app.open_historical_events()
                self.assertEqual(app.historical_event_list.size(), 0)
                self.assertIn("Search", app.historical_query_status.cget("text"))
                self.assertEqual(app.historical_start_var.get(),
                                 recent_historical_event_date_range(
                                     datetime.now().date(), 90).start.isoformat())
                today = datetime.now().date()
                for mode_index, days in ((0, 1), (1, 7), (2, 30), (3, 90), (4, 1)):
                    app.historical_range_choice.current(mode_index)
                    app.historical_range_choice.event_generate("<<ComboboxSelected>>")
                    root.update()
                    expected_range = recent_historical_event_date_range(today, days)
                    self.assertEqual(app.historical_start_var.get(),
                                     expected_range.start.isoformat())
                    self.assertEqual(app.historical_end_var.get(), today.isoformat())
                    self.assertIsNone(app._historical_query_result)
                app.historical_start_var.set("2026-01-01")
                app.historical_end_var.set(today.isoformat())
                app.historical_range_choice.current(5)
                app.historical_range_choice.event_generate("<<ComboboxSelected>>")
                root.update()
                self.assertEqual(app.historical_range_choice.current(), 5)
                self.assertIsNone(app._historical_query_result)
                app.historical_event_refresh_button.event_generate("<ButtonPress-1>")
                app.historical_event_refresh_button.event_generate("<ButtonRelease-1>")
                root.update()
                self.wait_for_ui(root, lambda: app._historical_query_result is not None)
                root.update_idletasks()
                self.assertTrue(app.historical_event_window.winfo_exists())
                self.assertEqual(app._historical_query_result.total_count, expected_total)
                index_path = root_path / "historical-event-query-index.sqlite3"
                self.assertTrue(index_path.is_file())
                self.assertEqual(app._historical_query_result.index_metrics.parsed_source_count, 3)
                self.assertEqual(app._historical_query_result.index_metrics.reused_source_count, 0)
                self.assertLessEqual(len(app._historical_event_records), 100)
                self.assertEqual(len(app._historical_event_records), 100)
                self.assertEqual(app.historical_event_list.size(), 101)
                self.assertGreater(app._historical_query_result.total_count, 100)
                self.assertGreater(app._historical_query_result.page_count, 1)
                self.assertIn("Page 1 of", app.historical_page_label.cget("text"))
                self.assertNotIn("More pages will be available",
                                 app.historical_query_status.cget("text"))
                warning_index = len(app._historical_event_records)
                self.assertEqual(app.historical_event_list.size(), warning_index + 1)
                click_history_row(warning_index)
                self.wait_for_ui(root, lambda: app._historical_showing_diagnostics and
                                 len(app._historical_event_records) == 1)
                click_history_row(1)
                warning_detail = app.historical_event_detail.get("1.0", "end")
                self.assertIn("not-json legacy evidence", warning_detail)
                self.assertIn("error:legacy_session:",
                              app._historical_event_selected_key)
                click_history_row(0)
                self.wait_for_ui(root, lambda: not app._historical_showing_diagnostics and
                                 app._historical_page_request_id is None and
                                 len(app._historical_event_records) == 100)
                first_page_records = app._historical_event_records
                self.click_tk_widget(root, app.historical_next_button)
                self.wait_for_ui(root, lambda: app._historical_query_page_number == 2)
                self.assertEqual(app._historical_query_page_number, 2)
                self.assertEqual(len(app._historical_event_records), expected_total - 100)
                self.assertIn("Page 2 of 2", app.historical_page_label.cget("text"))
                self.assertEqual(str(app.historical_next_button.cget("state")), "disabled")
                self.click_tk_widget(root, app.historical_previous_button)
                self.wait_for_ui(root, lambda: app._historical_query_page_number == 1)
                self.assertEqual(app._historical_event_records[0].key,
                                 first_page_records[0].key)
                first_result = app._historical_query_result
                app.historical_event_refresh_button.event_generate("<ButtonPress-1>")
                app.historical_event_refresh_button.event_generate("<ButtonRelease-1>")
                root.update()
                self.wait_for_ui(root, lambda: app._historical_query_result is not first_result)
                self.assertEqual(app._historical_query_result.total_count, expected_total)
                self.assertEqual(app._historical_query_result.index_metrics.parsed_source_count, 0)
                self.assertEqual(app._historical_query_result.index_metrics.reused_source_count, 3)
                self.assertEqual(audit_path.read_bytes(), audit_before)
                self.assertEqual(legacy_path.read_bytes(), legacy_before)
                self.assertEqual(app_path.read_bytes(), app_events_before)
                previous_records = app._historical_event_records
                previous_result = app._historical_query_result
                app.historical_start_var.set("2026-02-30")
                app.historical_event_refresh_button.event_generate("<ButtonPress-1>")
                app.historical_event_refresh_button.event_generate("<ButtonRelease-1>")
                root.update()
                self.assertEqual(
                    app.historical_date_error.cget("text"),
                    app._t("app.settings.history.validation.start_invalid"))
                self.assertIs(app._historical_query_result, previous_result)
                self.assertIs(app._historical_event_records, previous_records)
                app.historical_start_var.set("2026-10-14")
                app.historical_end_var.set("2026-10-13")
                app.historical_event_refresh_button.event_generate("<ButtonPress-1>")
                app.historical_event_refresh_button.event_generate("<ButtonRelease-1>")
                root.update()
                self.assertEqual(
                    app.historical_date_error.cget("text"),
                    app._t("app.settings.history.validation.reversed"))
                self.assertIs(app._historical_query_result, previous_result)
                app.historical_start_var.set("2026-10-08")
                app.historical_end_var.set("2026-10-13")
                app.historical_range_choice.current(5)

                read_entered = threading.Event()
                release_read = threading.Event()
                submitted_start = datetime.strptime(
                    app.historical_start_var.get(), "%Y-%m-%d").date()
                submitted_end = datetime.strptime(
                    app.historical_end_var.get(), "%Y-%m-%d").date()
                late_audit = RoundAuditStore(
                    session_root, "round-added-during-index-test", "FCT",
                    "2026-10-09T00:00:00+00:00", 0.0)
                late_audit.append_event(
                    AuditEvent(1, "round_ready", "added while index was idle", None),
                    "2026-10-09T08:00:00+00:00", 1.0)
                self.assertTrue(late_audit.flush())

                original_source_reader = historical_event_query.iter_historical_source_events

                def controlled_index_scan(source, read_observer=None):
                    yield from original_source_reader(source, read_observer=read_observer)
                    if not read_entered.is_set():
                        read_entered.set()
                        if not release_read.wait(20):
                            raise RuntimeError("controlled history index gate timed out")

                with patch.object(historical_event_query, "iter_historical_source_events",
                                  side_effect=controlled_index_scan):
                    app.historical_event_refresh_button.event_generate("<ButtonPress-1>")
                    app.historical_event_refresh_button.event_generate("<ButtonRelease-1>")
                    root.update()
                    self.wait_for(read_entered.is_set)
                    app.historical_start_var.set("2026-10-09")
                    app.historical_end_var.set("2026-10-09")
                    root.update()
                    self.assertEqual(app.historical_start_var.get(), "2026-10-09")
                    self.assertIn(app._t("app.settings.history.querying"),
                                  app.historical_query_status.cget("text"))
                    self.assertIn("2026-01-01",
                                  app.historical_query_status.cget("text"))
                    release_read.set()
                    self.wait_for_ui(
                        root,
                        lambda: app._historical_query_result is not None and
                        app._historical_query_result.date_range.start == submitted_start)
                self.assertEqual(app._historical_query_result.date_range.end, submitted_end)
                expected_total += 1
                previous_success = app._historical_query_result
                app.historical_start_var.set("2026-01-01")
                app.historical_end_var.set(today.isoformat())
                with patch("b518_log_solution.query_historical_events",
                           side_effect=RuntimeError("controlled read failure")):
                    app.historical_event_refresh_button.event_generate("<ButtonPress-1>")
                    app.historical_event_refresh_button.event_generate("<ButtonRelease-1>")
                    root.update()
                    self.wait_for_ui(
                        root,
                        lambda: app._historical_query_status_key ==
                        "app.settings.history.query_failed")
                self.assertIs(app._historical_query_result, previous_success)
                failed_status = app.historical_query_status.cget("text")
                self.assertIn("2026-10-08", failed_status)
                self.assertIn("2026-10-13", failed_status)
                keys = [record.key for record in app._historical_event_records]
                round_index = keys.index("round:round-history-1:1")
                click_history_row(round_index)
                self.assertIn("FCT round start accepted",
                              app.historical_event_detail.get("1.0", "end"))
                self.assertIn("FCT 本輪已接受開始",
                              app.historical_event_detail.get("1.0", "end"))
                platform_key = "round:round-history-1:2"
                platform_index = [record.key for record in app._historical_event_records].index(
                    platform_key)
                click_history_row(platform_index)
                self.assertIn("Atlas Slot 1 final result: PASS",
                              app.historical_event_detail.get("1.0", "end"))

                selected_key = app._historical_event_selected_key
                select_language_with_real_menu(TRADITIONAL_CHINESE)
                root.update_idletasks()
                self.assertTrue(app.historical_event_window.winfo_exists())
                self.assertEqual(app._historical_event_selected_key, selected_key)
                self.assertIn("Atlas 通道 1 最終結果：PASS",
                              app.historical_event_detail.get("1.0", "end"))
                self.assertEqual(app._historical_event_selected_key, platform_key)
                self.assertEqual(audit_path.read_bytes(), audit_before)
                self.assertEqual(app.historical_event_heading.cget("text"), "事件")
                app_record = next(record for record in app._historical_event_records
                                  if record.source == "app")
                app_index = [record.key for record in app._historical_event_records].index(
                    app_record.key)
                click_history_row(app_index)
                self.assertIn("App 已啟動", app.historical_event_detail.get("1.0", "end"))
                self.assertIn("Application started", app.historical_event_detail.get("1.0", "end"))
                select_language_with_real_menu(ENGLISH)
                self.assertIn("FCT round start accepted",
                              app.historical_event_list.get(round_index))

                long_key = "round:round-history-1:50"
                long_index = [record.key for record in app._historical_event_records].index(long_key)
                click_history_row(long_index)
                app.historical_event_list.yview_moveto(0.65)
                app.historical_event_detail.yview_moveto(0.5)
                root.update_idletasks()
                list_top_before = int(app.historical_event_list.index("@0,0"))
                detail_top_before = app.historical_event_detail.index("@0,0")
                select_language_with_real_menu(TRADITIONAL_CHINESE)
                root.update()
                self.assertEqual(app._historical_event_selected_key, long_key)
                self.assertEqual(int(app.historical_event_list.index("@0,0")),
                                 list_top_before)
                self.assertEqual(app.historical_event_detail.index("@0,0"),
                                 detail_top_before)
                self.assertIn(long_diagnostic,
                              app.historical_event_detail.get("1.0", "end"))

                legacy_key = "legacy:legacy-session:1"
                legacy_index = [record.key for record in app._historical_event_records].index(
                    legacy_key)
                click_history_row(legacy_index)
                self.assertIn("無法安全翻譯此歷史事件",
                              app.historical_event_list.get(legacy_index))
                self.assertIn("Legacy operator note — keep this original wording",
                              app.historical_event_detail.get("1.0", "end"))
                self.assertIn("raw legacy detail",
                              app.historical_event_detail.get("1.0", "end"))
                app.historical_start_var.set("2099-01-01")
                app.historical_end_var.set("2099-01-01")
                app.historical_event_refresh_button.event_generate("<ButtonPress-1>")
                app.historical_event_refresh_button.event_generate("<ButtonRelease-1>")
                root.update()
                self.wait_for_ui(
                    root,
                    lambda: app._historical_query_result is not None and
                    app._historical_query_result.date_range.start.isoformat() == "2099-01-01" and
                    app._historical_query_status_key not in {
                        "app.settings.history.querying",
                        "app.settings.history.preparing",
                    })
                self.assertEqual(app._historical_event_records, ())
                self.assertIn("歷史讀取不完整",
                              app.historical_query_status.cget("text"))
                self.assertEqual(legacy_path.read_bytes(), legacy_before)
                self.assertEqual(audit_path.read_bytes(), audit_before)
                self.assertEqual(app_path.read_bytes(), app_events_before)

                unreadable_app_path = root_path / "unreadable-app-events.json"
                unreadable_app_path.write_text("not-json\n", encoding="utf-8")
                previous_incomplete_result = app._historical_query_result
                app.historical_start_var.set("2099-01-01")
                app.historical_end_var.set("2099-01-01")
                with patch("b518_log_solution.query_historical_events",
                           side_effect=lambda _sessions, _app_path, date_range, **_kwargs:
                           query_historical_events(session_root, unreadable_app_path,
                                                   date_range)):
                    app.historical_event_refresh_button.event_generate("<ButtonPress-1>")
                    app.historical_event_refresh_button.event_generate("<ButtonRelease-1>")
                    root.update()
                    self.wait_for_ui(
                        root,
                        lambda: app._historical_query_result is not None and
                        app._historical_query_result is not previous_incomplete_result and
                        app._historical_query_result.source_issue_count > 0)
                self.assertEqual(app._historical_query_result.total_count, 0)
                self.assertGreater(app._historical_query_result.source_issue_count, 0)
                self.assertIn("歷史讀取不完整",
                              app.historical_query_status.cget("text"))
                self.assertNotIn(app._t("app.settings.history.no_results"),
                                 app.historical_query_status.cget("text"))
            finally:
                if "release_read" in locals():
                    release_read.set()
                app._close_historical_event_window()
                app.hotkey.close()
                root.destroy()
                self.assertTrue(audit.flush())

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_real_tk_history_query_latest_request_cancel_and_window_lifecycle(self):
        from audit_records import AuditEvent, RoundAuditStore

        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"), \
                patch.object(RoundCoordinator, "start_retention_schedule", return_value=None):
            root_path = Path(temporary)
            session_root = root_path / "sessions"
            app_path = root_path / "app-events.json"
            audit = RoundAuditStore(
                session_root, "query-lifecycle", "FCT", "2026-10-13T00:00:00+08:00",
                0.0)
            audit.append_event(
                AuditEvent(1, "round_ready", "FCT saved result", None,
                           detail={"raw_diagnostic": "keep selected result"}),
                datetime.now().astimezone().replace(microsecond=0).isoformat(), 1.0)
            self.assertTrue(audit.flush())

            root = tk.Tk()
            root.deiconify()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey, session_root=session_root,
                app_event_path=app_path)
            gates = {}
            entered = {}
            finished = {}
            query_dates = []
            original_query = query_historical_events

            def click(button):
                root.update_idletasks()
                x, y = max(2, button.winfo_width() // 2), max(2, button.winfo_height() // 2)
                button.event_generate("<ButtonPress-1>", x=x, y=y)
                button.event_generate("<ButtonRelease-1>", x=x, y=y)
                root.update()

            def set_dates(start, end=None):
                app.historical_start_entry.delete(0, "end")
                app.historical_start_entry.insert(0, start.isoformat())
                app.historical_end_entry.delete(0, "end")
                app.historical_end_entry.insert(0, (end or start).isoformat())
                root.update()

            def click_row(index):
                app.historical_event_list.see(index)
                root.update()
                x, y, _width, height = app.historical_event_list.bbox(index)
                point = (max(2, x + 4), y + max(1, height // 2))
                app.historical_event_list.event_generate(
                    "<ButtonPress-1>", x=point[0], y=point[1])
                app.historical_event_list.event_generate(
                    "<ButtonRelease-1>", x=point[0], y=point[1])
                root.update()
                self.wait_for_ui(root, lambda: app._historical_event_detail_request_id is None)

            def controlled_query(sessions, event_path, date_range, cancellation_event=None,
                                 index_path=None):
                query_dates.append(date_range.start)
                gate = gates.get(date_range.start)
                finished[date_range.start] = threading.Event()
                try:
                    if gate is not None:
                        entered[date_range.start] = cancellation_event
                        gate[0].set()
                        if not gate[1].wait(10):
                            raise RuntimeError("controlled history query gate timed out")
                        if date_range.start == date(2026, 1, 1):
                            raise RuntimeError("obsolete request failed after replacement")
                    return original_query(sessions, event_path, date_range,
                                          cancellation_event=cancellation_event,
                                          index_path=index_path)
                finally:
                    finished[date_range.start].set()

            try:
                self.wait_for(lambda: app.app_events.status().complete)
                audit_bytes_before_query = audit.audit_path.read_bytes()
                app_event_bytes_before_query = app_path.read_bytes()
                app.open_historical_events()
                initial_cancel_entered = threading.Event()
                initial_cancel_release = threading.Event()
                initial_cancel_finished = threading.Event()

                def controlled_initial_cancel(sessions, event_path, date_range,
                                              cancellation_event=None, index_path=None):
                    initial_cancel_entered.set()
                    try:
                        if not initial_cancel_release.wait(10):
                            raise RuntimeError("initial cancellation gate timed out")
                        return original_query(
                            sessions, event_path, date_range,
                            cancellation_event=cancellation_event,
                            index_path=index_path)
                    finally:
                        initial_cancel_finished.set()

                with patch("b518_log_solution.query_historical_events",
                           side_effect=controlled_initial_cancel):
                    set_dates(date(2025, 12, 1))
                    click(app.historical_event_refresh_button)
                    self.assertTrue(initial_cancel_entered.wait(2))
                    self.assertIsNone(app._historical_query_result)
                    click(app.historical_event_cancel_button)
                    self.assertEqual(app._historical_query_status_key,
                                     "app.settings.history.query_cancelled")
                    self.assertIsNone(app._historical_query_result)
                    initial_cancel_release.set()
                    self.assertTrue(initial_cancel_finished.wait(2))

                initial_range = recent_historical_event_date_range(date.today(), 90)
                set_dates(initial_range.start, initial_range.end)
                click(app.historical_event_refresh_button)
                self.wait_for_ui(root, lambda: app._historical_query_result is not None)
                self.assertEqual(audit.audit_path.read_bytes(), audit_bytes_before_query)
                self.assertEqual(app_path.read_bytes(), app_event_bytes_before_query)
                old_result = app._historical_query_result
                initial_range = old_result.date_range
                saved_key = "round:query-lifecycle:1"
                saved_index = next(index for index, record in enumerate(
                    app._historical_event_records) if record.key == saved_key)
                click_row(saved_index)
                old_key = app._historical_event_selected_key
                old_detail = app.historical_event_detail.get("1.0", "end")
                self.assertEqual(old_key, "round:query-lifecycle:1")

                first_gate = (threading.Event(), threading.Event())
                coalesced_gate = (threading.Event(), threading.Event())
                latest_gate = (threading.Event(), threading.Event())
                cancel_gate = (threading.Event(), threading.Event())
                close_gate = (threading.Event(), threading.Event())
                reopened_gate = (threading.Event(), threading.Event())
                app_close_gate = (threading.Event(), threading.Event())
                gates.update({
                    date(2026, 1, 1): first_gate,
                    date(2026, 2, 1): coalesced_gate,
                    date(2026, 3, 1): latest_gate,
                    date(2026, 4, 1): cancel_gate,
                    date(2026, 5, 1): close_gate,
                    date(2026, 6, 1): reopened_gate,
                    date(2026, 7, 1): app_close_gate,
                })

                with patch("b518_log_solution.query_historical_events",
                           side_effect=controlled_query):
                    set_dates(date(2026, 1, 1))
                    click(app.historical_event_refresh_button)
                    self.assertTrue(first_gate[0].wait(2))
                    self.assertEqual(str(app.historical_event_refresh_button.cget("state")),
                                     "normal")
                    set_dates(date(2026, 2, 1))
                    self.assertEqual(app._historical_query_result, old_result)
                    self.assertEqual(app._historical_event_selected_key, old_key)
                    self.assertIn("keep selected result", old_detail)
                    click(app.historical_event_refresh_button)
                    set_dates(date(2026, 3, 1))
                    click(app.historical_event_refresh_button)
                    self.assertEqual(app._historical_query_result, old_result)
                    self.assertEqual(app._historical_event_selected_key, old_key)
                    self.assertFalse(coalesced_gate[0].is_set())
                    self.assertEqual(query_dates, [date(2026, 1, 1)])
                    first_gate[1].set()
                    self.assertTrue(latest_gate[0].wait(2))
                    self.assertEqual(query_dates,
                                     [date(2026, 1, 1), date(2026, 3, 1)])
                    self.assertEqual(app.historical_start_var.get(), "2026-03-01")
                    self.assertEqual(app._historical_query_result, old_result)
                    self.assertIn(initial_range.start.isoformat(),
                                  app.historical_query_status.cget("text"))
                    latest_gate[1].set()
                    self.wait_for_ui(
                        root, lambda: app._historical_query_result is not old_result and
                        app._historical_query_result.date_range.start == date(2026, 3, 1))
                    latest_result = app._historical_query_result
                    self.assertNotEqual(app._historical_query_status_key,
                                        "app.settings.history.query_failed")
                    self.assertEqual(
                        app.historical_event_list.size(), len(latest_result.events),
                        "visible list must match newly published query")

                    set_dates(date(2026, 4, 1))
                    click(app.historical_event_refresh_button)
                    self.assertTrue(cancel_gate[0].wait(2))
                    self.assertEqual(str(app.historical_event_cancel_button.cget("state")),
                                     "normal")
                    click(app.historical_event_cancel_button)
                    self.assertIsNone(app._historical_query_generation)
                    self.assertEqual(app._historical_query_status_key,
                                     "app.settings.history.query_cancelled")
                    self.assertIs(app._historical_query_result, latest_result)
                    self.assertIn("2026-03-01",
                                  app.historical_query_status.cget("text"))
                    self.assertEqual(str(app.historical_event_cancel_button.cget("state")),
                                     "disabled")
                    cancel_gate[1].set()
                    self.wait_for(lambda: date(2026, 4, 1) in query_dates)
                    deadline = time.monotonic() + 0.1
                    while time.monotonic() < deadline:
                        root.update()
                        time.sleep(0.005)
                    self.assertIs(app._historical_query_result, latest_result)
                    self.assertEqual(app._historical_query_status_key,
                                     "app.settings.history.query_cancelled")

                    set_dates(date(2026, 5, 1))
                    click(app.historical_event_refresh_button)
                    self.assertTrue(close_gate[0].wait(2))
                    old_window = app.historical_event_window
                    close_script = old_window.protocol("WM_DELETE_WINDOW")
                    old_window.tk.call(close_script)
                    root.update()
                    self.assertIsNone(app.historical_event_window)
                    self.assertTrue(entered[date(2026, 5, 1)].is_set())
                    new_window_query_count = len(query_dates)

                    app.open_historical_events()
                    new_window = app.historical_event_window
                    self.assertIsNot(new_window, old_window)
                    self.assertIsNone(app._historical_query_result)
                    self.assertEqual(len(query_dates), new_window_query_count)
                    set_dates(date(2026, 6, 1))
                    click(app.historical_event_refresh_button)
                    self.assertEqual(len(query_dates), new_window_query_count)
                    close_gate[1].set()
                    self.assertTrue(reopened_gate[0].wait(2))
                    reopened_gate[1].set()
                    self.wait_for_ui(
                        root, lambda: app._historical_query_result is not None and
                        app._historical_query_result.date_range.start == date(2026, 6, 1))
                    self.assertIs(app.historical_event_window, new_window)
                    self.assertEqual(app._historical_query_status_key, "")
                    self.assertEqual(query_dates.count(date(2026, 5, 1)), 1)
                    self.assertEqual(query_dates.count(date(2026, 6, 1)), 1)
                    self.assertEqual(audit.audit_path.read_bytes(), audit_bytes_before_query)
                    self.assertEqual(app_path.read_bytes(), app_event_bytes_before_query)
                    set_dates(date(2026, 7, 1))
                    click(app.historical_event_refresh_button)
                    self.assertTrue(app_close_gate[0].wait(2))
                    app.close()
                    self.assertTrue(entered[date(2026, 7, 1)].is_set())
                    deadline = time.monotonic() + 5
                    while not app._ui_destroyed and time.monotonic() < deadline:
                        root.update()
                        time.sleep(0.005)
                    self.assertTrue(app._ui_destroyed,
                                    "App close waited for the obsolete history reader")
                    self.assertEqual(app.rounds.close_status().status, "complete")
                    app_close_gate[1].set()
                    self.assertTrue(finished[date(2026, 7, 1)].wait(2))
            finally:
                for _entered, release in gates.values():
                    release.set()
                if not app._ui_destroyed:
                    app._close_historical_event_window()
                    app.rounds.request_close()
                    self.wait_for(lambda: app.rounds.close_status().status == "complete")
                    self.wait_for(lambda: app.app_events.status().complete)
                    app.hotkey.close()
                    app.app_events.stop()
                    root.destroy()
                self.assertTrue(audit.flush())

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

                choose_button = find_button(app.settings_window, "📂 Browse")
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
            root.deiconify()
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
                            widget.winfo_rootx() + widget.winfo_width() - right_edge,
                            widget.winfo_rootx() - window.winfo_rootx(),
                            widget.winfo_width(),
                            widget.master.winfo_rootx() - window.winfo_rootx(),
                            widget.master.winfo_width())
                           for widget in visible_controls
                           if widget.winfo_rootx() + widget.winfo_width() > right_edge]
                self.assertEqual(outside, [],
                                 "Settings controls extend beyond the window: {}".format(outside))
                self.assertTrue(any(isinstance(widget, ttk.Button) and
                                    widget.cget("text") == "📂 Browse"
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

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_settings_layout_is_stable_across_languages_and_keeps_drafts(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.deiconify()
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
                app.profile_editor_project.set("HM2-DRAFT")
                app.profile_editor_capacity.set("17")
                long_path = "/deployment/" + ("long-directory/" * 12) + "final-results.csv"
                app.profile_editor_paths["final"].set(long_path)
                station_before_mouse_selection = app.profile_editor_machine.get()
                machine_choice = app.profile_editor_machine_choice
                arrow_x = machine_choice.winfo_width() - 5
                arrow_y = machine_choice.winfo_height() // 2
                machine_choice.event_generate("<ButtonPress-1>", x=arrow_x, y=arrow_y)
                machine_choice.event_generate("<ButtonRelease-1>", x=arrow_x, y=arrow_y)
                root.update()
                machine_choice.event_generate("<KeyPress-Down>")
                machine_choice.event_generate("<KeyPress-Return>")
                root.update()

                def settings_control_bounds():
                    bounds = []

                    def collect(parent):
                        for widget in parent.winfo_children():
                            if isinstance(widget, (ttk.Label, ttk.Button, ttk.Entry,
                                                  ttk.Combobox)) and widget.winfo_ismapped():
                                bounds.append((widget.winfo_class(),
                                               widget.winfo_rootx() - window.winfo_rootx(),
                                               widget.winfo_rooty() - window.winfo_rooty(),
                                               widget.winfo_width(), widget.winfo_height(),
                                               widget.cget("text")))
                            collect(widget)

                    collect(window)
                    return bounds

                def profile_form_values():
                    return {
                        "project": app.profile_editor_project.get(),
                        "machine": app.profile_editor_machine.get(),
                        "platform": app.profile_editor_platform.get(),
                        "capacity": app.profile_editor_capacity.get(),
                        "mapping": app.profile_editor_mapping.get(),
                        "paths": {key: value.get()
                                  for key, value in app.profile_editor_paths.items()},
                        "timeouts": {key: value.get()
                                     for key, value in app.profile_editor_timeouts.items()},
                    }

                evidence_root = os.environ.get("B518_TK_EVIDENCE_DIR")
                screenshot_bounds = {}

                def capture_settings_language(language, filename):
                    if not evidence_root:
                        return
                    import Quartz
                    from Foundation import NSURL

                    app._select_language(language)
                    window.geometry("680x560")
                    window.lift()
                    window.focus_force()
                    root.update()
                    native_windows = Quartz.CGWindowListCopyWindowInfo(
                        Quartz.kCGWindowListOptionOnScreenOnly,
                        Quartz.kCGNullWindowID)
                    native_window = next((item for item in native_windows
                                          if item.get(Quartz.kCGWindowOwnerPID) == os.getpid()
                                          and item.get(Quartz.kCGWindowNumber) ==
                          native_window_for_capture(window).windowNumber()), None)
                    self.assertIsNotNone(native_window,
                                         "Settings window missing from Aqua window list")
                    native_id = native_window[Quartz.kCGWindowNumber]
                    captured_image = Quartz.CGWindowListCreateImage(
                        Quartz.CGRectNull, Quartz.kCGWindowListOptionIncludingWindow,
                        native_id, Quartz.kCGWindowImageBoundsIgnoreFraming)
                    self.assertIsNotNone(captured_image,
                                         "CGWindowListCreateImage returned no window image")
                    output_path = Path(evidence_root) / filename
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_url = NSURL.fileURLWithPath_(str(output_path))
                    image_destination = Quartz.CGImageDestinationCreateWithURL(
                        output_url, "public.png", 1, None)
                    self.assertIsNotNone(image_destination)
                    Quartz.CGImageDestinationAddImage(image_destination, captured_image, None)
                    self.assertTrue(Quartz.CGImageDestinationFinalize(image_destination))
                    bounds = native_window[Quartz.kCGWindowBounds]
                    screenshot_bounds[language] = {
                        "window_geometry": window.geometry(),
                        "native_window_bounds": {
                            key: float(bounds[key]) for key in ("X", "Y", "Width", "Height")
                        },
                        "captured_image_pixels": {
                            "width": Quartz.CGImageGetWidth(captured_image),
                            "height": Quartz.CGImageGetHeight(captured_image),
                        },
                        "form_values": profile_form_values(),
                        "controls": settings_control_bounds(),
                        "screenshot": filename,
                    }

                capture_settings_language("en", "settings-configuration-en.png")
                capture_settings_language("zh-TW", "settings-configuration-zh-TW.png")
                if evidence_root:
                    self.assertEqual(
                        [item[:5] for item in screenshot_bounds["en"]["controls"]],
                        [item[:5] for item in screenshot_bounds["zh-TW"]["controls"]])
                    self.assertEqual(screenshot_bounds["en"]["form_values"],
                                     screenshot_bounds["zh-TW"]["form_values"])
                    with (Path(evidence_root) / "settings-bounds.json").open(
                            "w", encoding="utf-8") as evidence_file:
                        json.dump(screenshot_bounds, evidence_file, ensure_ascii=False,
                                  indent=2)
                        evidence_file.write("\n")
                    app._select_language("en")
                    root.update()

                self.assertIn(app.profile_editor_machine.get(),
                              app.profile_editor_machine_choice.cget("values"))
                self.assertNotEqual(app.profile_editor_machine.get(),
                                    station_before_mouse_selection)
                self.assertEqual(app.style.lookup("TEntry", "fieldbackground"), "#ffffff")
                profile_inputs = [item for item in settings_control_bounds()
                                  if item[0] in {"TEntry", "TCombobox"}]
                self.assertTrue(all(item[3] >= 90 for item in profile_inputs),
                                "Profile inputs must remain usable at 680px: {}".format(
                                    [(item[5], item[3]) for item in profile_inputs
                                     if item[3] < 90]))
                for index, tab in enumerate(app.settings_notebook.tabs()):
                    app.settings_notebook.select(tab)
                    root.update()
                    english_bounds = settings_control_bounds()
                    app._select_language("zh-TW")
                    root.update()
                    chinese_bounds = settings_control_bounds()
                    self.assertEqual([item[:5] for item in chinese_bounds],
                                     [item[:5] for item in english_bounds],
                                     "Settings tab {} changed control bounds: {}".format(
                                         index + 1,
                                         [(old[5], new[5], old[:5], new[:5])
                                          for old, new in zip(english_bounds, chinese_bounds)
                                          if old[:5] != new[:5]]))
                    self.assertEqual(app.settings_notebook.select(), tab)
                    self.assertEqual(window.title(), "設定")
                    app._select_language("en")
                    root.update()
                    self.assertEqual(window.title(), "Setting")
                    self.assertEqual(settings_control_bounds(), english_bounds)

                app.settings_notebook.select(app.settings_notebook.tabs()[0])
                root.update()
                self.assertEqual(app.profile_editor_project.get(), "HM2-DRAFT")
                self.assertEqual(app.profile_editor_capacity.get(), "17")
                self.assertEqual(app.profile_editor_paths["final"].get(), long_path)

                app.settings_notebook.select(app.settings_notebook.tabs()[1])
                app._event_records = [("event {}".format(index), None, None)
                                      for index in range(120)]
                app.event_lines = ["event {}".format(index) for index in range(120)]
                app._refresh_event_log()
                root.update()
                app.settings_log.yview_moveto(0.45)
                app.settings_log.tag_add("sel", "24.0", "26.0")
                app._select_language("zh-TW")
                root.update()
                self.assertAlmostEqual(app.settings_log.yview()[0], 0.45, delta=0.03)
                self.assertEqual(tuple(map(str, app.settings_log.tag_ranges("sel"))),
                                 ("24.0", "26.0"))
                self.assertEqual(app.settings_log.cget("background"), "#f3f4f6")
                self.assertEqual(app.settings_log.cget("relief"), "solid")

                app.settings_notebook.select(app.settings_notebook.tabs()[2])
                app.retention_days_entry.delete(0, "end")
                app.retention_days_entry.insert(0, "14")
                save_button = app.retention_save_button
                save_button.event_generate("<ButtonPress-1>",
                                           x=save_button.winfo_width() // 2,
                                           y=save_button.winfo_height() // 2)
                save_button.event_generate("<ButtonRelease-1>",
                                           x=save_button.winfo_width() // 2,
                                           y=save_button.winfo_height() // 2)
                root.update()
                self.assertEqual(app.profile_store.retention_days, 14)
                app._select_language("en")
                root.update()
                self.assertEqual(app.retention_days_var.get(), "14")
                self.assertTrue(app.retention_cleanup_text.winfo_ismapped())
                self.assertGreater(app.retention_cleanup_scrollbar.winfo_height(), 0)

                app.settings_notebook.select(app.settings_notebook.tabs()[0])
                root.update()
                export_button = next(widget for widget, message_id in app._settings_text_widgets
                                     if message_id == "app.settings.profile.export")
                export_path = Path(temporary) / "profiles.json"
                with patch("b518_log_solution.filedialog.asksaveasfilename",
                           return_value=str(export_path)):
                    export_button.focus_set()
                    export_button.event_generate("<KeyPress-space>")
                    export_button.event_generate("<KeyRelease-space>")
                    root.update()
                self.assertTrue(export_path.exists())
                import_button = next(widget for widget, message_id in app._settings_text_widgets
                                     if message_id == "app.settings.profile.import")
                with patch("b518_log_solution.filedialog.askopenfilename",
                           return_value=str(export_path)):
                    import_button.focus_set()
                    import_button.event_generate("<KeyPress-space>")
                    import_button.event_generate("<KeyRelease-space>")
                    root.update()
                self.assertIn("Configuration validated, imported", app.profile_editor_status.get())
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

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_profile_editor_uses_three_equal_action_columns_and_browse_label(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.deiconify()
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

                def button_for(message_id):
                    return next(widget for widget, key in app._settings_text_widgets
                                if key == message_id)

                choose = button_for("app.settings.profile.choose_directory")
                self.assertEqual(choose.cget("text"), "📂 Browse")
                app.profile_editor_project.set("DRAFT-PROJECT")
                app.profile_editor_paths["active"].set("/before/chooser")
                original_dialog_path = app.profile_editor_paths["active"].get()
                with patch("b518_log_solution.filedialog.askdirectory",
                           return_value="/selected/logs") as chooser:
                    choose.invoke()
                self.assertEqual(chooser.call_args.kwargs["parent"], window)
                self.assertEqual(chooser.call_args.kwargs["title"], "Choose Configuration Path")
                self.assertEqual(chooser.call_args.kwargs["mustexist"], True)
                self.assertEqual(app.profile_editor_paths["active"].get(), "/selected/logs")
                with patch("b518_log_solution.filedialog.askdirectory", return_value=""):
                    choose.invoke()
                self.assertEqual(app.profile_editor_paths["active"].get(), "/selected/logs")
                selected_dialog_path = app.profile_editor_paths["active"].get()

                row_ids = (
                    ("app.settings.profile.load", "app.settings.profile.validate",
                     "app.settings.profile.apply"),
                    ("app.settings.profile.import", "app.settings.profile.export",
                     "app.settings.profile.reload"),
                )
                action_font = tkfont.Font(
                    root=root, font=app.style.lookup("ProfileAction.TButton", "font"))
                measured = []
                action_buttons = []
                for ids in row_ids:
                    buttons = [button_for(key) for key in ids]
                    action_buttons.extend(buttons)
                    for button in buttons:
                        self.assertLessEqual(action_font.measure(button.cget("text")) + 16,
                                             button.winfo_width(),
                                             "Action label is clipped: {} ({}/{})".format(
                                                 button.cget("text"),
                                                 action_font.measure(button.cget("text")),
                                                 button.winfo_width()))
                    bounds = [(button.winfo_rootx(), button.winfo_rooty(),
                               button.winfo_width(), button.winfo_height())
                              for button in buttons]
                    widths = [item[2] for item in bounds]
                    self.assertLessEqual(max(widths) - min(widths), 1, bounds)
                    self.assertEqual(len({item[1] for item in bounds}), 1, bounds)
                    self.assertEqual(len({item[3] for item in bounds}), 1, bounds)
                    gaps = [bounds[index + 1][0] -
                            (bounds[index][0] + bounds[index][2]) for index in range(2)]
                    self.assertLessEqual(max(gaps) - min(gaps), 1, bounds)
                    measured.append(bounds)
                cancel = button_for("app.settings.profile.cancel")
                self.assertGreater(cancel.winfo_rooty(), measured[1][0][1])
                self.assertGreaterEqual(
                    cancel.winfo_rootx(),
                    measured[1][2][0] + measured[1][2][2] - cancel.winfo_width())
                self.assertTrue(cancel.winfo_viewable())
                self.assertLessEqual(cancel.winfo_rooty() + cancel.winfo_height(),
                                     window.winfo_rooty() + window.winfo_height())
                action_buttons.append(cancel)
                left_edge = window.winfo_rootx()
                right_edge = left_edge + window.winfo_width()
                self.assertTrue(all(button.winfo_viewable() and
                                    button.winfo_rootx() >= left_edge and
                                    button.winfo_rootx() + button.winfo_width() <= right_edge
                                    for button in action_buttons),
                                [(button.cget("text"), button.winfo_rootx(),
                                  button.winfo_width()) for button in action_buttons])

                app._select_language(TRADITIONAL_CHINESE)
                root.update()
                self.assertEqual(choose.cget("text"), "📂 瀏覽")
                self.assertEqual(app.profile_editor_project.get(), "DRAFT-PROJECT")
                self.assertEqual(app.profile_editor_paths["active"].get(), "/selected/logs")
                self.assertEqual(button_for("app.settings.profile.cancel").winfo_rootx(),
                                 cancel.winfo_rootx())
                evidence_root = os.environ.get("B518_TK_EVIDENCE_DIR")
                if evidence_root:
                    captures = {}
                    for key, language in (("en", "en"),
                                          ("zh-TW", TRADITIONAL_CHINESE)):
                        app._select_language(language)
                        root.update()
                        captures[key] = capture_tk_window_evidence(
                            window, "hf5-settings", key, {
                                "browse": choose,
                                "load": button_for("app.settings.profile.load"),
                                "validate": button_for("app.settings.profile.validate"),
                                "apply": button_for("app.settings.profile.apply"),
                                "import": button_for("app.settings.profile.import"),
                                "export": button_for("app.settings.profile.export"),
                                "reload": button_for("app.settings.profile.reload"),
                                "cancel": button_for("app.settings.profile.cancel"),
                            })
                        for tab, name in ((1, "settings-events"), (2, "settings-retention")):
                            app.settings_notebook.select(tab)
                            root.update()
                            capture_tk_window_evidence(window, name, key, {})
                        app.settings_notebook.select(0)
                        root.update()
                    behavior = {
                        "folder_dialog": {
                            "parent_is_settings_window": True,
                            "mustexist": chooser.call_args.kwargs["mustexist"],
                            "selected_path": "/selected/logs",
                            "draft_path_after_selection": selected_dialog_path,
                            "draft_path_before_dialog": original_dialog_path,
                            "draft_path_after_cancel": selected_dialog_path,
                            "draft_project_after_language_change": app.profile_editor_project.get(),
                            "active_path_after_language_change":
                                app.profile_editor_paths["active"].get(),
                        }
                    }
                    (Path(evidence_root) / "hf5-settings-bounds.json").write_text(
                        json.dumps({"rows": measured, "captures": captures,
                                    "behavior": behavior},
                                   ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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
        root.deiconify()
        app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey)
        app.open_settings()
        root.update_idletasks()
        try:
            self.wait_for(lambda: app.rounds.retention_cleanup_status().status in {
                "complete", "failed"
            })
            self.assertEqual(app.rounds.retention_cleanup_status().status, "complete")
            style = ttk.Style(root)
            self.assertEqual(style.theme_use(), "clam")
            self.assertEqual(style.lookup("TLabel", "foreground"), "#111827")
            self.assertEqual(style.lookup("TEntry", "fieldbackground"), "#ffffff")
            self.assertEqual(style.lookup("TButton", "foreground"), "#111827")
            self.assertEqual(app.settings_window.cget("background"), "#f3f4f6")
            self.assertEqual(app.settings_log.cget("background"), LIGHT_BACKGROUND)
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
            app.rounds.request_close()
            self.wait_for(lambda: app.rounds.close_status().status == "complete")
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

    def test_result_event_updates_dashboard_without_forcing_window_or_focus(self):
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
        app.root.deiconify.assert_not_called()
        app.root.lift.assert_not_called()
        app.root.focus_force.assert_not_called()

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
        app._set_monitor_controls.assert_called_once_with(False, "monitor.timeout_stopped")

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
            root.deiconify()
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
            root.deiconify()
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
            captures = {}

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
                    self.assertIn("persistent close audit fault",
                                  app._close_diagnostic_text.get("1.0", "end-1c"))
                    self.assertEqual(app._close_diagnostic_text.cget("background"),
                                     LIGHT_BACKGROUND)
                    self.assertEqual(int(app._close_diagnostic_text.cget("borderwidth")), 1)
                    self.assertTrue(app._close_diagnostic_text.cget("yscrollcommand"))
                    captures["en"] = capture_tk_window_evidence(
                        app._close_window, "close-progress", "en", {
                            "status": app._close_status_label,
                            "language_reason": app._close_language_reason_label,
                            "diagnostic": app._close_diagnostic_text,
                            "retry": app._close_retry_button,
                            "cancel": app._close_cancel_button,
                        })
                    app._close_retry_button.focus_force()
                    deadline = time.monotonic() + 2
                    hint_window = None
                    while time.monotonic() < deadline:
                        root.update()
                        hint_window = next((child for child in app._close_window.winfo_children()
                                            if isinstance(child, tk.Toplevel) and
                                            child.overrideredirect()), None)
                        if hint_window is not None:
                            break
                        time.sleep(.01)
                    self.assertIsNotNone(hint_window)
                    self.assertIn("Retry the required App and round-record saves",
                                  hint_window.winfo_children()[0].cget("text"))
                    capture_native_window_with_hint(
                        app._close_window, "st5-close-retry-enabled-hint-en.png")

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
                    captures["zh-TW"] = capture_tk_window_evidence(
                        app._close_window, "close-progress", "zh-TW", {
                            "status": app._close_status_label,
                            "language_reason": app._close_language_reason_label,
                            "diagnostic": app._close_diagnostic_text,
                            "retry": app._close_retry_button,
                            "cancel": app._close_cancel_button,
                        })
                    app._close_retry_button.focus_force()
                    deadline = time.monotonic() + 2
                    hint_window = None
                    while time.monotonic() < deadline:
                        root.update()
                        hint_window = next((child for child in app._close_window.winfo_children()
                                            if isinstance(child, tk.Toplevel) and
                                            child.overrideredirect()), None)
                        if hint_window is not None:
                            break
                        time.sleep(.01)
                    self.assertIsNotNone(hint_window)
                    self.assertIn("重試保存必要的 App 與輪次紀錄",
                                  hint_window.winfo_children()[0].cget("text"))
                    capture_native_window_with_hint(
                        app._close_window, "st5-close-retry-enabled-hint-zh-TW.png")
                    self.assertEqual(captures["en"]["size"],
                                     captures["zh-TW"]["size"])
                    self.assertEqual(captures["en"]["controls"],
                                     captures["zh-TW"]["controls"])
                    write_tk_bounds_evidence("close_progress", captures)
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
            root.deiconify()
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
                heartbeat_before_close = app._heartbeat_state
                app.close()
                ticks = []
                root.after(0, lambda: ticks.append("responsive"))
                pump_until(lambda: (rounds.close_status().status == "waiting" and
                                    app._heartbeat_state != heartbeat_before_close))
                self.assertIn("responsive", ticks)
                self.assertNotEqual(app._heartbeat_state, heartbeat_before_close)
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

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_scrolled_conflict_candidates_keep_reading_position_on_language_change(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.deiconify()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey,
                session_root=Path(temporary) / "sessions",
                app_event_path=Path(temporary) / "app-events.json")
            sources = []

            def create(callback):
                source = ControlledConflictMonitor(callback)
                sources.append(source)
                return source

            try:
                started = app.rounds.start("FCT", create, run_async=False, capacity=2)
                app.active_round_id = started.round_id
                for index in range(28):
                    self.assertEqual(sources[0].offer_candidate(
                        1, "CANDIDATE-{:02d}".format(index), "FAIL",
                        "/controlled/{}/candidate.csv".format(index), str(index),
                        "2026-10-12T10:01:00"), "defer")
                self.wait_for_ui(root, lambda: app.conflict_list is not None
                                 and app.conflict_list.size() == 28)
                window = app.conflict_window
                window.geometry("{}x{}".format(*window.minsize()))
                root.update()
                app.conflict_list.selection_clear(0, "end")
                app.conflict_list.selection_set(17)
                app.conflict_list.event_generate("<<ListboxSelect>>")
                app.conflict_list.yview_moveto(0.4)
                root.update()
                snapshot = app.rounds.snapshot()
                top_candidate = snapshot.pending_conflicts[app.conflict_list.nearest(1)].conflict_id
                self.assertGreater(app.conflict_list.nearest(1), 0)
                app.conflict_panes.sashpos(0, 200)
                root.update()
                sash = app.conflict_panes.sashpos(0)

                for language in ("繁體中文", "English", "繁體中文"):
                    menu_index = next(index for index in range(app.language_menu.index("end") + 1)
                                      if app.language_menu.entrycget(index, "label") == language)
                    app.language_menu.invoke(menu_index)
                    root.update()
                    self.assertIs(app.conflict_window, window)
                    self.assertEqual(app.conflict_list.curselection(), (17,))
                    self.assertEqual(app.rounds.snapshot().pending_conflicts,
                                     snapshot.pending_conflicts)
                    self.assertEqual(snapshot.pending_conflicts[
                        app.conflict_list.nearest(1)].conflict_id, top_candidate)
                    self.assertEqual(app.conflict_panes.sashpos(0), sash)
                    self.assertIn("CANDIDATE-17", app.conflict_details.get("1.0", "end"))
            finally:
                for conflict in app.rounds.snapshot().pending_conflicts:
                    app.rounds.resolve_review(conflict.conflict_id, "keep_original")
                app.rounds.stop()
                app.close()
                self.wait_for(lambda: app.rounds.close_status().status == "complete", timeout=5)
                try:
                    root.destroy()
                except tk.TclError:
                    pass

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_hm3_conflict_and_alarm_layout_stays_fixed_across_languages(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.deiconify()
            session_root = Path(temporary) / "sessions"
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey, session_root=session_root,
                app_event_path=Path(temporary) / "app-events.json",
            )
            elapsed = [0.0]
            rounds = RoundCoordinator(
                app.events.put, monotonic=lambda: elapsed[0], audit_root=session_root)
            rounds.register_app_event_store(app.app_events, Path(temporary))
            app.rounds = rounds
            sources = []

            def create(callback):
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
                self.fail("Timed out while pumping HM3 layout validation")

            def bounds(window):
                root.update_idletasks()
                values = []
                def collect(widget):
                    if widget is not window and widget.winfo_ismapped():
                        values.append((widget.winfo_pathname(widget.winfo_id()),
                                       widget.winfo_class(), widget.winfo_x(),
                                       widget.winfo_y(), widget.winfo_width(),
                                       widget.winfo_height()))
                    for child in widget.winfo_children():
                        collect(child)
                collect(window)
                return sorted(values)

            def overlaps(first, second):
                first_left, first_top = first.winfo_rootx(), first.winfo_rooty()
                first_right = first_left + first.winfo_width()
                first_bottom = first_top + first.winfo_height()
                second_left, second_top = second.winfo_rootx(), second.winfo_rooty()
                second_right = second_left + second.winfo_width()
                second_bottom = second_top + second.winfo_height()
                return (first_left < second_right and second_left < first_right and
                        first_top < second_bottom and second_top < first_bottom)

            def capture(window, filename):
                evidence_root = os.environ.get("B518_TK_EVIDENCE_DIR")
                if not evidence_root:
                    return
                import Quartz
                from Foundation import NSURL

                root.update()
                native_windows = Quartz.CGWindowListCopyWindowInfo(
                    Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID)
                native_window = next((item for item in native_windows
                                      if item.get(Quartz.kCGWindowOwnerPID) == os.getpid()
                                      and item.get(Quartz.kCGWindowNumber) ==
                          native_window_for_capture(window).windowNumber()), None)
                self.assertIsNotNone(native_window,
                                     "Window missing from Aqua window list: {}".format(
                                         window.title()))
                native_id = native_window[Quartz.kCGWindowNumber]
                captured = capture_tk_window_image(window, native_window)
                self.assertIsNotNone(captured)
                output = Path(evidence_root) / filename
                output.parent.mkdir(parents=True, exist_ok=True)
                destination = Quartz.CGImageDestinationCreateWithURL(
                    NSURL.fileURLWithPath_(str(output)), "public.png", 1, None)
                Quartz.CGImageDestinationAddImage(destination, captured, None)
                self.assertTrue(Quartz.CGImageDestinationFinalize(destination))
                return {
                    "geometry": window.geometry(),
                    "native_bounds": {
                        key: float(native_window[Quartz.kCGWindowBounds][key])
                        for key in ("X", "Y", "Width", "Height")
                    },
                    "image_pixels": {
                        "width": Quartz.CGImageGetWidth(captured),
                        "height": Quartz.CGImageGetHeight(captured),
                    },
                    "controls": bounds(window),
                    "screenshot": filename,
                }

            try:
                started = rounds.start(
                    "FCT", create, run_async=False, round_timeout_seconds=1, capacity=2)
                app.active_round_id = started.round_id
                for index in range(28):
                    source = "/controlled/" + ("long-diagnostic-directory/" * 8) + "base.csv"
                    sn = ("SN-CANDIDATE-LONG-{:02d}-".format(index) +
                          ("READING-POSITION-" * 4))
                    event = MonitorEvent(
                        "result_candidate", "controlled candidate", slot=1, sn=sn,
                        status="FAIL", source=source,
                        detail={"round_evidence_id": "controlled-round-evidence",
                                "source_id": "candidate-" + ("long-provenance-" * 8),
                                "source_time": "2026-10-08T10:01:00",
                                "diagnostic": "long source diagnostic " * 24},
                    )
                    self.assertEqual(sources[0].callback(event), "defer")
                pump_until(lambda: app.conflict_list is not None
                           and app.conflict_list.size() == 28)
                sources[0].timeout_seconds = lambda kind: 1 if kind == "round" else 3600
                elapsed[0] = 2.0
                rounds.poll_once()
                pump_until(lambda: app.round_alarm_window is not None
                           and app.round_alarm_window.winfo_exists())
                original_snapshot = rounds.snapshot()

                conflict_window = app.conflict_window
                alarm_window = app.round_alarm_window
                conflict_window.geometry("960x600")
                alarm_window.geometry("700x340")
                root.update()
                for marker in (app.kvm_state_marker, app.kvm_layout_marker,
                               *app.kvm_result_blocks.values()):
                    self.assertFalse(overlaps(conflict_window, marker),
                                     "Conflict review must not cover KVM markers")
                app.conflict_list.selection_clear(0, "end")
                app.conflict_list.selection_set(17)
                app.conflict_list.activate(17)
                app.conflict_list.event_generate("<<ListboxSelect>>")
                app.conflict_list.yview_moveto(0.4)
                app.conflict_panes.sashpos(0, 220)
                app.conflict_details.yview_moveto(0.35)
                app.conflict_comparison.xview_moveto(0.25)
                root.update()
                conflict_id = app._conflict_ids[17]
                selected_snapshot = rounds.snapshot()
                detail_top = app.conflict_details.index("@0,0")
                kvm_widgets = [
                    app.kvm_results, app.kvm_state_marker, app.kvm_layout_marker,
                    *app.kvm_result_blocks.values(),
                ]
                kvm_geometry = tuple(
                    (widget.winfo_x(), widget.winfo_y(),
                     widget.winfo_width(), widget.winfo_height())
                    for widget in kvm_widgets
                )
                conflict_bounds = {}
                alarm_bounds = {}
                conflict_evidence = {}
                alarm_evidence = {}
                for language in (ENGLISH, TRADITIONAL_CHINESE, ENGLISH,
                                 TRADITIONAL_CHINESE):
                    if language != app.current_language:
                        self.set_language_for_test_setup(app, root, language)
                    key = "en" if language == ENGLISH else "zh-TW"
                    conflict_bounds[key] = bounds(conflict_window)
                    alarm_bounds[key] = bounds(alarm_window)
                    conflict_window.update_idletasks()
                    alarm_window.update_idletasks()
                    conflict_evidence[key] = capture(
                        conflict_window, "conflict-review-{}.png".format(key))
                    alarm_evidence[key] = capture(
                        alarm_window, "round-alarm-{}.png".format(key))
                    self.assertEqual(conflict_window.geometry().split("+")[0], "960x600")
                    self.assertEqual(alarm_window.geometry().split("+")[0], "700x340")
                    self.assertEqual(app.conflict_list.curselection(), (17,))
                    self.assertEqual(app._conflict_ids[17], conflict_id)
                    self.assertTrue(app.conflict_list_xscrollbar.winfo_ismapped())
                    self.assertEqual(
                        conflict_window.title(),
                        "Same-Round Result Conflict" if language == ENGLISH
                        else "同輪結果衝突",
                    )
                    self.assertEqual(
                        alarm_window.title(),
                        "Round Monitoring Timeout" if language == ENGLISH
                        else "整輪監控逾時",
                    )
                    self.assertEqual(rounds.snapshot().pending_conflicts,
                                     selected_snapshot.pending_conflicts)
                    self.assertEqual(rounds.snapshot().results, original_snapshot.results)
                    self.assertFalse(rounds.snapshot().round_alarm.acknowledged_at)
                    self.assertEqual(str(app.round_alarm_ack_button["state"]), "normal")
                    self.assertEqual(app.conflict_panes.sashpos(0), 220)
                    self.assertEqual(app.conflict_details.index("@0,0"), detail_top)
                    self.assertEqual(tuple(
                        (widget.winfo_x(), widget.winfo_y(),
                         widget.winfo_width(), widget.winfo_height())
                        for widget in kvm_widgets
                    ), kvm_geometry)
                    self.assertIn("/controlled/slot1/base.csv",
                                  app.conflict_details.get("@0,0", "@0,0 + 200 chars"))
                    self.assertEqual(app.conflict_comparison.cget("relief"), "solid")
                    self.assertEqual(app.conflict_comparison.cget("background"), "#f3f4f6")
                    self.assertGreaterEqual(int(app.conflict_comparison.cget("borderwidth")), 1)
                    self.assertIn("SN-CANDIDATE", app.conflict_details.get("1.0", "end"))

                self.assertEqual(conflict_bounds["en"], conflict_bounds["zh-TW"])
                self.assertEqual(alarm_bounds["en"], alarm_bounds["zh-TW"])
                if os.environ.get("B518_TK_EVIDENCE_DIR"):
                    evidence_dir = Path(os.environ["B518_TK_EVIDENCE_DIR"])
                    with (evidence_dir / "window-bounds.json").open(
                            "w", encoding="utf-8") as evidence_file:
                        json.dump({
                            "conflict": conflict_evidence,
                            "alarm": alarm_evidence,
                            "selected_conflict_id": conflict_id,
                            "selected_index": 17,
                            "sash_position": app.conflict_panes.sashpos(0),
                            "detail_top_index": detail_top,
                            "alarm_acknowledged": False,
                            "pending_conflict_count": len(
                                selected_snapshot.pending_conflicts),
                        }, evidence_file, ensure_ascii=False, indent=2)
                        evidence_file.write("\n")
            finally:
                snapshot = rounds.snapshot()
                for conflict in snapshot.pending_conflicts:
                    rounds.resolve_review(conflict.conflict_id, "keep_original")
                alarm = rounds.snapshot().round_alarm
                if alarm and not alarm.acknowledged_at:
                    rounds.acknowledge_round_alarm(alarm.round_id, alarm.alarm_id)
                rounds.stop()
                app.close()
                pump_until(lambda: rounds.close_status().status == "complete")
                try:
                    root.destroy()
                except tk.TclError:
                    pass

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_conflict_and_alarm_refresh_fail_independently_and_retry_latest_language(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.deiconify()
            session_root = Path(temporary) / "sessions"
            app_event_path = Path(temporary) / "app-events.json"
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey, session_root=session_root,
                app_event_path=app_event_path,
            )
            elapsed = [0.0]
            rounds = RoundCoordinator(
                app.events.put, monotonic=lambda: elapsed[0], audit_root=session_root)
            rounds.register_app_event_store(app.app_events, session_root.parent)
            app.rounds = rounds
            holder = {}

            class Monitor:
                def __init__(self, callback):
                    self.callback = callback
                    self.session = SessionStore("language-refresh-round", {}, session_root)
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
                    evidence = {"round_evidence_id": "fct:1:language-refresh",
                                "source_time": "2026-10-12T10:00:00",
                                "source_id": "active.csv"}
                    self.apply_round_result(1, "PASS", "SN-ORIGINAL",
                                            "/temporary/active.csv", evidence)
                    self.apply_round_result(2, "TESTING", "SN-OTHER",
                                            "/temporary/other.csv", evidence)

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
                        "result", "slot{} {}".format(slot, status), slot=slot,
                        sn=result.sn, status=status, source=source, detail=detail or {},
                    ))

                def set_result(self, slot, status, detail=None, lock_terminal=False):
                    self.apply_round_result(slot, status, detail=detail,
                                            lock_terminal=lock_terminal)

            def create(callback):
                holder["monitor"] = Monitor(callback)
                return holder["monitor"]

            def pump_until(predicate, timeout=5):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    root.update()
                    if predicate():
                        return
                    time.sleep(.01)
                self.fail("Timed out while pumping the Tk language-refresh flow")

            def select_language(label):
                index = next(
                    item for item in range(app.language_menu.index("end") + 1)
                    if app.language_menu.entrycget(item, "label") == label)
                app.language_menu.invoke(index)
                root.update()

            def click(button):
                x = max(1, button.winfo_width() // 2)
                y = max(1, button.winfo_height() // 2)
                button.event_generate("<ButtonPress-1>", x=x, y=y)
                button.event_generate("<ButtonRelease-1>", x=x, y=y)
                root.update()

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
                evidence = {"round_evidence_id": "fct:1:language-refresh",
                            "source_time": "2026-10-12T10:00:00",
                            "source_id": " ".join("PROVENANCE-{:04d}".format(i)
                                                  for i in range(160))}
                monitor.apply_round_result(1, "PASS", "SN-ORIGINAL",
                                           "/temporary/active.csv", evidence)
                candidate = MonitorEvent(
                    "result_candidate", "controlled candidate", slot=1,
                    sn="SN-ORIGINAL", status="FAIL", source="/temporary/final.csv",
                    detail=dict(evidence, source_id="candidate.csv"),
                )
                self.assertEqual(monitor.callback(candidate), "defer")
                elapsed[0] = 2.0
                rounds.poll_once()
                pump_until(lambda: app.conflict_window and app.conflict_window.winfo_exists()
                           and app.round_alarm_window and app.round_alarm_window.winfo_exists())

                conflict_window = app.conflict_window
                alarm_window = app.round_alarm_window
                conflict_id = rounds.snapshot().pending_conflicts[0].conflict_id
                alarm = rounds.snapshot().round_alarm
                app.round_alarm_button.invoke()
                root.update()
                recovery_window = app.recovery_window
                self.assertTrue(recovery_window.winfo_exists())
                self.assertIn(alarm.alarm_id, app.recovery_alarm_detail.get("1.0", "end-1c"))
                self.assertIn("configured round monitoring limit",
                              app.recovery_alarm_detail.get("1.0", "end-1c"))
                self.assertFalse(rounds.snapshot().round_alarm.acknowledged_at)
                app.conflict_list.selection_set(0)
                app.conflict_list.activate(0)
                conflict_window.geometry("{}x{}".format(*conflict_window.minsize()))
                root.update()
                app.conflict_details.yview_moveto(0.4)
                root.update_idletasks()
                visible_detail = app.conflict_details.get("@0,0", "@0,0 + 100 chars")
                self.assertIn("PROVENANCE-", visible_detail)
                anchor_start = visible_detail.index("PROVENANCE-")
                reading_anchor = visible_detail[anchor_start:anchor_start + 15]
                app.conflict_comparison.xview_moveto(1.0)
                detail_reading = int(app.conflict_details.index("@0,0").split(".")[0])
                selected_details = app.conflict_details.get("1.0", "end-1c")
                self.assertGreater(detail_reading, 1)
                self.assertIn("SN-ORIGINAL", selected_details)
                self.assertIn("SN-ORIGINAL", app.conflict_comparison.get("1.0", "end-1c"))
                self.assertFalse(rounds.snapshot().round_alarm.acknowledged_at)
                self.assertTrue(rounds.flush_audit(timeout=5))
                self.assertTrue(rounds.flush_session(timeout=5))
                audit_path = monitor.session.path / "audit.jsonl"
                before_refresh = audit_path.read_bytes()

                original_conflict_refresh = app._refresh_conflict_review
                inject_conflict_failure = [True]

                def refresh_conflict(*args, **kwargs):
                    if kwargs.get("update_main") is False and inject_conflict_failure[0]:
                        raise RuntimeError("injected conflict refresh failure")
                    return original_conflict_refresh(*args, **kwargs)

                with patch.object(app, "_refresh_conflict_review",
                                  side_effect=refresh_conflict):
                    select_language("繁體中文")
                    self.assertEqual(app.current_language, TRADITIONAL_CHINESE)
                    self.assertEqual(alarm_window.title(), "整輪監控逾時")
                    self.assertEqual(recovery_window.title(), "通知與恢復")
                    self.assertIn("已達設定的整輪監控時間上限",
                                  app.recovery_alarm_detail.get("1.0", "end-1c"))
                    self.assertEqual(conflict_window.title(), "Same-Round Result Conflict")
                    self.assertEqual(app.app_event_status_label.cget("text"), "文字更新失敗")
                    self.assertIn("確認整輪警報", app.round_alarm_ack_button.cget("text"))
                    self.assertFalse(rounds.snapshot().round_alarm.acknowledged_at)
                    select_language("English")
                    self.assertEqual(alarm_window.title(), "Round Monitoring Timeout")
                    self.assertEqual(app.app_event_status_label.cget("text"),
                                     "Text refresh failed")

                inject_conflict_failure[0] = False
                select_language("繁體中文")
                self.assertEqual(app.current_language, TRADITIONAL_CHINESE)
                click(self.diagnostics_language_retry(app))
                self.assertIs(app.conflict_window, conflict_window)
                self.assertIs(app.round_alarm_window, alarm_window)
                self.assertIs(app.recovery_window, recovery_window)
                self.assertEqual(conflict_window.title(), "同輪結果衝突")
                self.assertEqual(alarm_window.title(), "整輪監控逾時")
                self.assertEqual(app._conflict_ids[app.conflict_list.curselection()[0]],
                                 conflict_id)
                refreshed_details = app.conflict_details.get("1.0", "end-1c")
                self.assertNotEqual(refreshed_details, selected_details)
                self.assertIn("SN-ORIGINAL", refreshed_details)
                self.assertIn("/temporary/active.csv", refreshed_details)
                self.assertIn("SN-ORIGINAL", app.conflict_comparison.get("1.0", "end-1c"))
                self.assertEqual(int(app.conflict_details.index("@0,0").split(".")[0]),
                                 detail_reading)
                self.assertIn(reading_anchor, app.conflict_details.get(
                    "@0,0", "@0,0 + 100 chars"))
                self.assertFalse(rounds.snapshot().round_alarm.acknowledged_at)
                self.assertEqual(str(app.round_alarm_ack_button["state"]), "normal")
                self.assertEqual(str(self.diagnostics_language_retry(app)["state"]), "disabled")
                self.assertEqual(audit_path.read_bytes(), before_refresh)

                original_alarm_refresh = app._refresh_round_alarm_language
                inject_alarm_failure = [True]

                def refresh_alarm():
                    if inject_alarm_failure[0]:
                        raise RuntimeError("injected alarm refresh failure")
                    return original_alarm_refresh()

                with patch.object(app, "_refresh_round_alarm_language",
                                  side_effect=refresh_alarm):
                    select_language("English")
                    self.assertEqual(conflict_window.title(), "Same-Round Result Conflict")
                    self.assertEqual(alarm_window.title(), "整輪監控逾時")
                    self.assertEqual(app.app_event_status_label.cget("text"),
                                     "Text refresh failed")
                    self.assertFalse(rounds.snapshot().round_alarm.acknowledged_at)
                    select_language("繁體中文")
                    self.assertEqual(conflict_window.title(), "同輪結果衝突")
                    self.assertEqual(alarm_window.title(), "整輪監控逾時")
                    self.assertEqual(app.app_event_status_label.cget("text"), "文字更新失敗")

                inject_alarm_failure[0] = False
                click(self.diagnostics_language_retry(app))
                self.assertIs(app.round_alarm_window, alarm_window)
                self.assertEqual(alarm_window.title(), "整輪監控逾時")
                self.assertEqual(str(self.diagnostics_language_retry(app)["state"]), "disabled")
                self.assertEqual(audit_path.read_bytes(), before_refresh)

                inject_conflict_failure[0] = True
                inject_alarm_failure[0] = True
                with patch.object(app, "_refresh_conflict_review", side_effect=refresh_conflict), \
                        patch.object(app, "_refresh_round_alarm_language", side_effect=refresh_alarm):
                    select_language("English")
                    self.assertEqual(conflict_window.title(), "同輪結果衝突")
                    self.assertEqual(alarm_window.title(), "整輪監控逾時")
                    self.assertEqual(app.app_event_status_label.cget("text"),
                                     "Text refresh failed")
                    diagnostic_events = app.app_events.records
                    ui_tick = []
                    root.after(350, lambda: ui_tick.append(True))
                    pump_until(lambda: bool(ui_tick))
                    self.assertEqual(app.app_events.records, diagnostic_events)
                    inject_conflict_failure[0] = False
                    click(self.diagnostics_language_retry(app))
                    self.assertEqual(conflict_window.title(), "Same-Round Result Conflict")
                    self.assertEqual(alarm_window.title(), "整輪監控逾時")
                    self.assertEqual(str(self.diagnostics_language_retry(app)["state"]), "normal")
                    inject_alarm_failure[0] = False
                    click(self.diagnostics_language_retry(app))
                    self.assertEqual(alarm_window.title(), "Round Monitoring Timeout")
                    self.assertEqual(str(self.diagnostics_language_retry(app)["state"]), "disabled")
                    self.assertIs(app.conflict_window, conflict_window)
                    self.assertIs(app.round_alarm_window, alarm_window)
                    self.assertEqual(audit_path.read_bytes(), before_refresh)
                select_language("繁體中文")

                app.conflict_close_button.invoke()
                app.round_alarm_close_button.invoke()
                self.assertEqual(conflict_window.state(), "withdrawn")
                self.assertEqual(alarm_window.state(), "withdrawn")
                select_language("English")
                self.assertEqual(conflict_window.title(), "Same-Round Result Conflict")
                self.assertEqual(alarm_window.title(), "Round Monitoring Timeout")
                self.assertEqual(conflict_window.state(), "withdrawn")
                self.assertEqual(alarm_window.state(), "withdrawn")
                click(app.review_button)
                click(app.round_alarm_button)
                self.assertIs(app.conflict_window, conflict_window)
                self.assertIs(app.round_alarm_window, alarm_window)
                self.assertEqual(conflict_window.title(), "Same-Round Result Conflict")
                self.assertEqual(alarm_window.title(), "Round Monitoring Timeout")
                select_language("繁體中文")
                self.assertEqual(app._conflict_ids[app.conflict_list.curselection()[0]],
                                 conflict_id)
                self.assertFalse(rounds.snapshot().round_alarm.acknowledged_at)

                conflict_window.tk.call(conflict_window.protocol("WM_DELETE_WINDOW"))
                alarm_window.tk.call(alarm_window.protocol("WM_DELETE_WINDOW"))
                root.update()
                self.assertEqual(conflict_window.state(), "withdrawn")
                self.assertEqual(alarm_window.state(), "withdrawn")
                select_language("English")
                click(app.review_button)
                click(app.round_alarm_button)
                self.assertIs(app.conflict_window, conflict_window)
                self.assertIs(app.round_alarm_window, alarm_window)
                self.assertEqual(conflict_window.title(), "Same-Round Result Conflict")
                self.assertEqual(alarm_window.title(), "Round Monitoring Timeout")
                select_language("繁體中文")

                old_conflict_window = conflict_window
                old_alarm_window = alarm_window
                old_conflict_window.destroy()
                old_alarm_window.destroy()
                root.update()
                click(app.review_button)
                pump_until(lambda: app.round_alarm_window and
                           app.round_alarm_window.winfo_exists())
                conflict_window = app.conflict_window
                alarm_window = app.round_alarm_window
                self.assertIsNot(conflict_window, old_conflict_window)
                self.assertIsNot(alarm_window, old_alarm_window)
                self.assertEqual(conflict_window.title(), "同輪結果衝突")
                self.assertEqual(alarm_window.title(), "整輪監控逾時")
                self.assertEqual(app._conflict_ids[app.conflict_list.curselection()[0]],
                                 conflict_id)
                self.assertFalse(rounds.snapshot().round_alarm.acknowledged_at)

                self.assertTrue(app.app_events.flush(timeout=5))
                diagnostic_store = read_app_event_store(app_event_path)
                refresh_failures = [event for event in diagnostic_store["events"]
                                    if event.get("localized_message", {}).get("message_id") ==
                                    "app.language.refresh_failed"]
                self.assertTrue(refresh_failures)
                self.assertTrue(refresh_failures[-1]["localized_message"]["en"])
                self.assertTrue(refresh_failures[-1]["localized_message"]["zh-TW"])
                self.assertEqual(refresh_failures[-1].get("round_id"), None)
                diagnostics = "\n".join(event["diagnostic"] for event in refresh_failures)
                self.assertIn("injected conflict refresh failure", diagnostics)
                self.assertIn("injected alarm refresh failure", diagnostics)

                inject_conflict_failure[0] = True
                with patch.object(app, "_refresh_conflict_review", side_effect=refresh_conflict):
                    select_language("English")
                    select_language("繁體中文")
                inject_conflict_failure[0] = False
                app.close()
                pump_until(lambda: rounds.close_status().status == "waiting")
                self.assertIn("取消關閉後即可切換", app._close_language_reason_label.cget("text"))
                failure_banner = app.app_event_status_label.cget("text")
                self.assertEqual(failure_banner, "文字更新失敗")
                self.assertEqual(str(self.diagnostics_language_retry(app)["state"]), "disabled")
                closing_records = app.app_events.records
                click(self.diagnostics_language_retry(app))
                root.after(0, app.retry_language_refresh)
                root.update()
                self.assertEqual(app.app_event_status_label.cget("text"), failure_banner)
                self.assertEqual(app.app_events.records, closing_records)
                app._close_cancel_button.invoke()
                root.update()
                self.assertEqual(str(self.diagnostics_language_retry(app)["state"]), "normal")
                self.assertTrue(rounds.snapshot().collection_stopped)
                self.assertEqual(rounds.snapshot().pending_conflicts[0].conflict_id, conflict_id)
                click(self.diagnostics_language_retry(app))
                self.assertEqual(str(self.diagnostics_language_retry(app)["state"]), "disabled")
                app.close()
                pump_until(lambda: rounds.close_status().status == "waiting")
                app._select_language(ENGLISH)
                self.assertEqual(app.current_language, TRADITIONAL_CHINESE)
                self.assertEqual(conflict_window.title(), "同輪結果衝突")
                self.assertEqual(alarm_window.title(), "整輪監控逾時")
                app.resolve_conflict_original_button.invoke()
                self.assertEqual(rounds.snapshot().pending_conflicts, ())
                app.round_alarm_ack_button.invoke()
                pump_until(lambda: rounds.close_status().status == "complete")
                pump_until(lambda: not root_is_alive())

                rebuilt = read_round_audit(monitor.session.path / "audit.jsonl")
                self.assertTrue(rebuilt["audit_complete"])
                kinds = [event["kind"] for event in rebuilt["events"]]
                self.assertEqual(kinds.count("conflict_resolved"), 1)
                self.assertEqual(kinds.count("round_alarm_acknowledged"), 1)
                decisions = [event for event in rebuilt["events"]
                             if event["kind"] in {
                                 "conflict_resolved", "round_alarm_acknowledged"}]
                self.assertEqual(len(decisions), 2)
                self.assertTrue(all(event["localized_message"]["en"] and
                                    event["localized_message"]["zh-TW"]
                                    for event in decisions))
            finally:
                if root_is_alive():
                    rounds.stop()
                    for conflict in rounds.snapshot().pending_conflicts:
                        rounds.resolve_review(conflict.conflict_id, "keep_original")
                    alarm = rounds.snapshot().round_alarm
                    if alarm and not alarm.acknowledged_at:
                        rounds.acknowledge_round_alarm(alarm.round_id, alarm.alarm_id)
                    app.close()
                    pump_until(lambda: rounds.close_status().status == "complete")
                    app.hotkey.close()
                    app.app_events.stop()
                    if root_is_alive():
                        root.destroy()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_real_tk_close_keeps_conflict_and_alarm_actions_available(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.deiconify()
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

            def hover_hint(widget):
                from AppKit import NSApplicationActivateIgnoringOtherApps, NSRunningApplication

                NSRunningApplication.runningApplicationWithProcessIdentifier_(
                    os.getpid()).activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
                owner = widget.winfo_toplevel()
                # Both minimum-height dialogs cannot fit vertically on this
                # desktop. Keep the other dialog away from the target actions.
                if owner is app.conflict_window and app.round_alarm_window:
                    app.round_alarm_window.geometry("+30+0")
                elif owner is app.round_alarm_window:
                    owner.geometry("+30+{}".format(max(
                        0, root.winfo_screenheight() - owner.winfo_height() - 50)))
                owner.deiconify()
                owner.lift()
                focused = root.focus_get()
                if focused is None or focused.winfo_toplevel() is not owner:
                    owner.focus_force()
                root.update()
                point = (widget.winfo_rootx() + widget.winfo_width() // 2,
                         widget.winfo_rooty() + widget.winfo_height() // 2)
                if os.environ.get("B518_MANUAL_HOVER") == "1":
                    hint = app._conflict_action_hints.get(widget)
                    if hint is not None:
                        hint._hide()
                        hint._pointer_inside = False
                    motion = {"outside": False, "entered": False}

                    def observe_physical_motion(event):
                        inside = (widget.winfo_rootx() <= event.x_root <
                                  widget.winfo_rootx() + widget.winfo_width() and
                                  widget.winfo_rooty() <= event.y_root <
                                  widget.winfo_rooty() + widget.winfo_height())
                        if not inside:
                            motion["outside"] = True
                        elif motion["outside"]:
                            motion["entered"] = True

                    root.bind_all("<Motion>", observe_physical_motion, add="+")
                    print("Move the physical mouse outside the disabled {!r} button, "
                          "then hover its center at screen point {} for 0.5 seconds."
                          .format(widget.cget("text"), point), flush=True)
                    pump_until(lambda: motion["entered"] and any(
                        child.overrideredirect() and child.winfo_viewable()
                        for child in widget.winfo_toplevel().winfo_children()
                        if isinstance(child, tk.Toplevel)), timeout=60)
                else:
                    event_source = Quartz.CGEventSourceCreate(
                        Quartz.kCGEventSourceStateHIDSystemState)
                    approach = (max(1, point[0] - widget.winfo_width() // 2 - 6), point[1])
                    Quartz.CGEventPost(
                        Quartz.kCGHIDEventTap,
                        Quartz.CGEventCreateMouseEvent(
                            event_source, Quartz.kCGEventMouseMoved, approach,
                            Quartz.kCGMouseButtonLeft))
                    Quartz.CGEventPost(
                        Quartz.kCGHIDEventTap,
                        Quartz.CGEventCreateMouseEvent(
                            event_source, Quartz.kCGEventMouseMoved, point,
                            Quartz.kCGMouseButtonLeft))
                pump_until(lambda: _LocalizedControlHint._visible_hint is not None and
                           _LocalizedControlHint._visible_hint._widget is widget and
                           _LocalizedControlHint._visible_hint._window is not None and
                           _LocalizedControlHint._visible_hint._window.winfo_viewable())
                hint_window = next(
                    child
                    for child in widget.winfo_toplevel().winfo_children()
                    if isinstance(child, tk.Toplevel) and child.overrideredirect()
                    and child.winfo_viewable())
                label = hint_window.winfo_children()[0]
                self.assertGreater(hint_window.winfo_width(), 0)
                self.assertGreater(hint_window.winfo_height(), 0)
                self.assertTrue(label.cget("text"))
                return label.cget("text")

            def click_native(widget):
                event_source = Quartz.CGEventSourceCreate(
                    Quartz.kCGEventSourceStateHIDSystemState)
                point = (widget.winfo_rootx() + widget.winfo_width() // 2,
                         widget.winfo_rooty() + widget.winfo_height() // 2)
                for event_kind in (Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp):
                    Quartz.CGEventPost(
                        Quartz.kCGHIDEventTap,
                        Quartz.CGEventCreateMouseEvent(
                            event_source, event_kind, point, Quartz.kCGMouseButtonLeft))
                    deadline = time.monotonic() + .08
                    while time.monotonic() < deadline:
                        root.update()
                        time.sleep(.005)

            def press_and_release_outside(widget, screenshot_name):
                event_source = Quartz.CGEventSourceCreate(
                    Quartz.kCGEventSourceStateHIDSystemState)
                point = (widget.winfo_rootx() + widget.winfo_width() // 2,
                         widget.winfo_rooty() + widget.winfo_height() // 2)
                Quartz.CGEventPost(
                    Quartz.kCGHIDEventTap,
                    Quartz.CGEventCreateMouseEvent(
                        event_source, Quartz.kCGEventLeftMouseDown, point,
                        Quartz.kCGMouseButtonLeft))
                root.update()
                capture_native_window_with_hint(
                    widget.winfo_toplevel(), screenshot_name)
                outside = (widget.winfo_rootx() + widget.winfo_width() + 10, point[1])
                Quartz.CGEventPost(
                    Quartz.kCGHIDEventTap,
                    Quartz.CGEventCreateMouseEvent(
                        event_source, Quartz.kCGEventMouseMoved, outside,
                        Quartz.kCGMouseButtonLeft))
                Quartz.CGEventPost(
                    Quartz.kCGHIDEventTap,
                    Quartz.CGEventCreateMouseEvent(
                        event_source, Quartz.kCGEventLeftMouseUp, outside,
                        Quartz.kCGMouseButtonLeft))
                root.update()

            def press_key(keycode, shift=False):
                flags = Quartz.kCGEventFlagMaskShift if shift else 0
                for down in (True, False):
                    event = Quartz.CGEventCreateKeyboardEvent(None, keycode, down)
                    Quartz.CGEventSetFlags(event, flags)
                    Quartz.CGEventPostToPid(os.getpid(), event)
                root.update()

            def capture_hover(key, window):
                return capture_native_window_with_hint(window, key)

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

                # Native pointer acceptance needs exposed controls in both
                # sibling windows, rather than hovering through an occluder.
                app.conflict_window.geometry("960x540+30+0")
                root.update()
                app.round_alarm_window.geometry("700x300+30+{}".format(
                    app.conflict_window.winfo_rooty() +
                    app.conflict_window.winfo_height() + 12))
                root.update()
                app._select_language(ENGLISH)
                app.conflict_list.selection_clear(0, "end")
                app.conflict_list.event_generate("<<ListboxSelect>>")
                root.update()
                self.assertEqual(str(app.resolve_conflict_candidate_button["state"]),
                                 "disabled")
                disabled_hint = hover_hint(app.resolve_conflict_candidate_button)
                self.assertIn("Select an item awaiting review", disabled_hint)
                capture_hover("st5-conflict-candidate-disabled-hint-en.png",
                              app.conflict_window)
                if os.environ.get("B518_MANUAL_HOVER") == "1":
                    app._select_language(TRADITIONAL_CHINESE)
                    root.update()
                    translated_disabled_hint = next(
                        child.winfo_children()[0].cget("text")
                        for child in app.conflict_window.winfo_children()
                        if isinstance(child, tk.Toplevel) and child.overrideredirect()
                        and child.winfo_viewable())
                    self.assertIn("請先選取一筆", translated_disabled_hint)
                    capture_hover("st5-conflict-candidate-disabled-hint-zh-TW.png",
                                  app.conflict_window)
                    click_native(app.resolve_conflict_candidate_button)
                    self.assertEqual(len(rounds.snapshot().pending_conflicts), 1)
                    self.assertFalse(rounds.snapshot().round_alarm.acknowledged_at)
                    return
                click_native(app.resolve_conflict_candidate_button)
                self.assertEqual(len(rounds.snapshot().pending_conflicts), 1)
                app.conflict_list.selection_set(0)
                app.conflict_list.activate(0)
                app.conflict_list.event_generate("<<ListboxSelect>>")
                root.update()
                app.resolve_conflict_original_button.focus_force()
                pump_until(lambda: app.conflict_window.focus_get() is
                           app.resolve_conflict_original_button)
                press_key(48)
                pump_until(lambda: app.conflict_window.focus_get() is
                           app.resolve_conflict_candidate_button)
                enabled_hint = hover_hint(app.resolve_conflict_candidate_button)
                self.assertIs(app.conflict_window.focus_get(),
                              app.resolve_conflict_candidate_button)
                self.assertIn("choosing the new candidate", enabled_hint)
                self.assertIn("Other items awaiting review still need a decision", enabled_hint)
                self.assertNotIn("Select an item awaiting review", enabled_hint)
                capture_hover("st5-conflict-candidate-hint-en.png", app.conflict_window)
                original_hint = hover_hint(app.resolve_conflict_original_button)
                self.assertIn("keeping the original result", original_hint)
                capture_hover("st5-conflict-original-hint-en.png", app.conflict_window)
                conflict_close_hint = hover_hint(app.conflict_close_button)
                self.assertIn("without deciding any result or removing", conflict_close_hint)
                press_and_release_outside(
                    app.conflict_close_button, "st5-conflict-close-pressed-en.png")
                self.assertEqual(len(rounds.snapshot().pending_conflicts), 1)
                self.assertTrue(app.conflict_window.winfo_viewable())
                capture_hover("st5-conflict-close-hint-en.png", app.conflict_window)
                app.conflict_close_button.invoke()
                root.update()
                self.assertFalse(app.conflict_window.winfo_viewable())
                self.assertFalse(any(isinstance(child, tk.Toplevel) and
                                     child.overrideredirect()
                                     for child in app.conflict_window.winfo_children()))
                self.assertEqual(len(rounds.snapshot().pending_conflicts), 1)
                app._open_conflict_review()
                pump_until(lambda: app.conflict_window.winfo_viewable())

                alarm_before_hover = rounds.snapshot().round_alarm.acknowledged_at
                alarm_hint = hover_hint(app.round_alarm_ack_button)
                self.assertIn("Confirm that you have reviewed this round alarm", alarm_hint)
                capture_hover("st5-round-alarm-acknowledge-hint-en.png",
                              app.round_alarm_window)
                self.assertEqual(rounds.snapshot().round_alarm.acknowledged_at,
                                 alarm_before_hover)
                alarm_close_hint = hover_hint(app.round_alarm_close_button)
                self.assertIn("without confirming the alarm", alarm_close_hint)
                self.assertIsNotNone(app.round_alarm_window)
                capture_hover("st5-round-alarm-close-hint-en.png", app.round_alarm_window)
                app.round_alarm_close_button.invoke()
                root.update()
                self.assertFalse(app.round_alarm_window.winfo_viewable())
                self.assertFalse(any(isinstance(child, tk.Toplevel) and
                                     child.overrideredirect()
                                     for child in app.round_alarm_window.winfo_children()))
                self.assertFalse(rounds.snapshot().round_alarm.acknowledged_at)
                app._open_round_alarm()
                pump_until(lambda: app.round_alarm_window.winfo_viewable())
                app._select_language(TRADITIONAL_CHINESE)
                translated_alarm_hint = hover_hint(app.round_alarm_ack_button)
                self.assertIn("確認你已查看此輪警報", translated_alarm_hint)
                capture_hover("st5-round-alarm-acknowledge-hint-zh-TW.png",
                              app.round_alarm_window)
                translated_alarm_close_hint = hover_hint(app.round_alarm_close_button)
                self.assertIn("不會確認警報", translated_alarm_close_hint)
                capture_hover("st5-round-alarm-close-hint-zh-TW.png",
                              app.round_alarm_window)
                app.conflict_list.selection_clear(0, "end")
                app.conflict_list.event_generate("<<ListboxSelect>>")
                root.update()
                translated_disabled_hint = hover_hint(app.resolve_conflict_candidate_button)
                self.assertIn("請先選取待確認項目", translated_disabled_hint)
                capture_hover("st5-conflict-candidate-disabled-hint-zh-TW.png",
                              app.conflict_window)
                click_native(app.resolve_conflict_candidate_button)
                self.assertEqual(len(rounds.snapshot().pending_conflicts), 1)
                app.conflict_list.selection_set(0)
                app.conflict_list.activate(0)
                app.conflict_list.event_generate("<<ListboxSelect>>")
                root.update()
                translated_conflict_hint = hover_hint(app.resolve_conflict_candidate_button)
                self.assertIn("逐項決定", translated_conflict_hint)
                capture_hover("st5-conflict-candidate-hint-zh-TW.png",
                              app.conflict_window)
                translated_original_hint = hover_hint(app.resolve_conflict_original_button)
                self.assertIn("保留這筆原結果", translated_original_hint)
                capture_hover("st5-conflict-original-hint-zh-TW.png", app.conflict_window)
                translated_conflict_close_hint = hover_hint(app.conflict_close_button)
                self.assertIn("不會替你決定結果或移除", translated_conflict_close_hint)
                self.assertEqual(len(rounds.snapshot().pending_conflicts), 1)
                capture_hover("st5-conflict-close-hint-zh-TW.png", app.conflict_window)
                self.assertEqual(rounds.snapshot().round_alarm.acknowledged_at,
                                 alarm_before_hover)
                app._select_language(ENGLISH)

                app.close()
                pump_until(lambda: rounds.close_status().status == "waiting")
                close_retry_hint = hover_hint(app._close_retry_button)
                self.assertIn("only after a required save fails", close_retry_hint)
                capture_hover("st5-close-retry-disabled-hint-en.png", app._close_window)
                click_native(app._close_retry_button)
                self.assertEqual(rounds.close_status().status, "waiting")
                cancel_hint = hover_hint(app._close_cancel_button)
                self.assertIn("Pending save work continues", cancel_hint)
                capture_hover("st5-close-cancel-hint-en.png", app._close_window)
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


    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_real_tk_historical_pages_load_details_on_selection(self):
        from audit_records import AuditEvent, RoundAuditStore
        from historical_event_query import HistoricalEventQueryResult

        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"), \
                patch.object(RoundCoordinator, "start_retention_schedule", return_value=None):
            root_path = Path(temporary)
            sessions = root_path / "sessions"
            audit = RoundAuditStore(
                sessions, "paged-ui", "FCT", "2026-10-13T00:00:00+08:00", 0.0)
            event_time = datetime.now().astimezone().replace(microsecond=0).isoformat()
            raw_detail = "original long diagnostic " * 500
            for sequence in range(1, 206):
                audit.append_event(AuditEvent(
                    sequence, "round_ready", "FCT source ready", None,
                    detail={"raw_diagnostic": raw_detail if sequence == 103 else ""}),
                    event_time, float(sequence))
            self.assertTrue(audit.flush())
            source_bytes = audit.audit_path.read_bytes()

            root = tk.Tk()
            root.deiconify()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey, session_root=sessions,
                app_event_path=root_path / "app-events.json")
            try:
                self.wait_for(lambda: app.app_events.status().complete)
                app_event_bytes = app.app_events.path.read_bytes()
                expected_app_events = len(app.app_events.records)
                app.open_historical_events()
                self.click_tk_widget(root, app.historical_event_refresh_button)
                self.wait_for_ui(root, lambda: app._historical_query_result is not None)

                expected_total = 205 + expected_app_events
                self.assertEqual(app._historical_query_result.total_count, expected_total)
                self.assertEqual(app._historical_query_result.page_count, 3)
                self.assertEqual(len(app._historical_event_records), 100)
                self.assertEqual(app.historical_page_label.cget("text"),
                                 "Page 1 of 3 · {} events".format(expected_total))
                self.assertEqual(str(app.historical_previous_button.cget("state")), "disabled")
                self.assertEqual(str(app.historical_next_button.cget("state")), "normal")
                self.assertNotIn("More pages will be available", app.historical_query_status.cget("text"))
                displayed_keys = [item.key for item in app._historical_event_records]
                displayed_round_sequences = [item.sequence for item in
                                             app._historical_event_records
                                             if item.source == "round"]

                # Use real Tk mouse events, and confirm the source is not rescanned for another page.
                with patch("historical_event_query.iter_historical_events",
                           side_effect=AssertionError("page navigation rescanned the sources")):
                    self.click_tk_widget(root, app.historical_next_button)
                    self.wait_for_ui(root, lambda: app._historical_query_page_number == 2)
                    self.assertEqual(app._historical_query_page_number, 2)
                    self.assertEqual(len(app._historical_event_records), 100)
                    self.assertEqual(app.historical_page_label.cget("text"),
                                     "Page 2 of 3 · {} events".format(expected_total))
                    displayed_keys.extend(item.key for item in app._historical_event_records)
                    displayed_round_sequences.extend(item.sequence for item in
                                                     app._historical_event_records
                                                     if item.source == "round")
                    self.assertEqual(str(app.historical_previous_button.cget("state")), "normal")

                    self.click_tk_widget(root, app.historical_next_button)
                    self.wait_for_ui(root, lambda: app._historical_query_page_number == 3)
                    self.assertEqual(app._historical_query_page_number, 3)
                    self.assertEqual(len(app._historical_event_records), expected_total - 200)
                    displayed_keys.extend(item.key for item in app._historical_event_records)
                    displayed_round_sequences.extend(item.sequence for item in
                                                     app._historical_event_records
                                                     if item.source == "round")
                    self.assertEqual(str(app.historical_next_button.cget("state")), "disabled")
                    self.assertEqual(displayed_round_sequences, list(range(1, 206)))
                    self.assertEqual(len(displayed_keys), expected_total)
                    self.assertEqual(len(set(displayed_keys)), expected_total)
                    self.click_tk_widget(root, app.historical_previous_button)
                    self.wait_for_ui(root, lambda: app._historical_query_page_number == 2)
                    self.assertEqual(app._historical_query_page_number, 2)

                self.wait_for_ui(
                    root, lambda: app._historical_event_detail_request_id is None)
                selected_index = next(index for index, item in enumerate(
                    app._historical_event_records) if item.sequence == 103)
                selected = app._historical_event_records[selected_index]
                self.assertFalse(hasattr(selected, "diagnostic"))
                self.assertNotIn(raw_detail[:40],
                                 app.historical_event_detail.get("1.0", "end"))
                detail_entered, release_detail = threading.Event(), threading.Event()
                original_get_detail = HistoricalEventQueryResult.get_detail

                def blocked_detail(query_result, event_key):
                    detail_entered.set()
                    if not release_detail.wait(5):
                        raise RuntimeError("controlled UI detail gate timed out")
                    return original_get_detail(query_result, event_key)

                try:
                    with patch.object(HistoricalEventQueryResult, "get_detail",
                                      blocked_detail):
                        self.click_tk_listbox_row(
                            root, app.historical_event_list, selected_index)
                        self.wait_for(detail_entered.is_set)
                        # The UI remains responsive to a real date edit and page request.
                        app.historical_start_var.set(date.today().isoformat())
                        root.update()
                        self.assertEqual(app.historical_start_var.get(),
                                         date.today().isoformat())
                        self.click_tk_widget(root, app.historical_next_button)
                        self.assertEqual(app._historical_query_page_number, 2)
                        release_detail.set()
                        self.wait_for_ui(root, lambda: app._historical_query_page_number == 3)
                finally:
                    release_detail.set()
                self.click_tk_widget(root, app.historical_previous_button)
                self.wait_for_ui(root, lambda: app._historical_query_page_number == 2)
                selected_index = next(index for index, item in enumerate(
                    app._historical_event_records) if item.sequence == 103)
                self.click_tk_listbox_row(root, app.historical_event_list, selected_index)
                self.wait_for_ui(root, lambda: raw_detail[:40] in
                                 app.historical_event_detail.get("1.0", "end"))
                self.assertIn("round:paged-ui:103", app._historical_event_selected_key)
                self.assertEqual(audit.audit_path.read_bytes(), source_bytes)
                self.assertEqual(app.app_events.path.read_bytes(), app_event_bytes)
            finally:
                app._close_historical_event_window()
                app.hotkey.close()
                root.destroy()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_real_tk_qp3_cached_pages_detail_language_and_cancelled_requery(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"), \
                patch.object(RoundCoordinator, "start_retention_schedule", return_value=None):
            root_path = Path(temporary)
            sessions = root_path / "sessions"
            round_id = "qp3-priority-ui"
            audit_path = sessions / round_id / "audit.jsonl"
            audit_path.parent.mkdir(parents=True)
            today = datetime.now().astimezone().date()
            occurred_at = datetime.combine(
                today, datetime.min.time(), datetime.now().astimezone().tzinfo).isoformat()
            records = [{
                "record_type": "round", "schema_version": 1,
                "round_id": round_id, "station": "FCT", "config": {},
                "time_contract": {},
            }]
            for sequence in range(1, 802):
                records.append({
                    "record_type": "event", "schema_version": 1,
                    "round_id": round_id, "sequence": sequence,
                    "kind": "round_ready", "message": "QP3 event {}".format(sequence),
                    "observed_at": occurred_at, "elapsed_seconds": float(sequence),
                    "display_position": None,
                    "detail": {"raw_diagnostic": "QP3 detail {}".format(sequence)},
                })
            audit_path.write_text(
                "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
            source_bytes = audit_path.read_bytes()
            entered_read, release_read = threading.Event(), threading.Event()
            read_offsets = []
            original_read = HistoricalEventQueryResult._read_unprepared_summaries

            def gated_read(result, offset, limit):
                read_offsets.append(offset)
                if offset == 500:
                    entered_read.set()
                    if not release_read.wait(20):
                        raise RuntimeError("controlled QP3 background-read gate timed out")
                return original_read(result, offset, limit)

            root = tk.Tk()
            root.deiconify()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey, session_root=sessions,
                app_event_path=root_path / "app-events.json")
            try:
                self.wait_for(lambda: app.app_events.status().complete)
                app_event_bytes = app.app_events.path.read_bytes()
                app.open_historical_events()
                with patch.object(HistoricalEventQueryResult,
                                  "_read_unprepared_summaries", gated_read):
                    self.click_tk_widget(root, app.historical_event_refresh_button)
                    self.wait_for_ui(root, lambda: app._historical_query_result is not None)
                    self.assertTrue(entered_read.wait(2))
                    result = app._historical_query_result
                    self.assertGreaterEqual(result.total_count, 801)
                    self.assertGreaterEqual(result.page_count, 9)
                    self.assertEqual(len(result.initial_events), 500)
                    self.assertFalse(result.preparation_complete)
                    self.assertLessEqual(result.cached_summary_count, 500)

                    # The initially prepared page cache remains usable while the
                    # slow ordinal-range read is held in the background.
                    for expected_page in range(2, 6):
                        self.click_tk_widget(root, app.historical_next_button)
                        self.wait_for_ui(
                            root, lambda page=expected_page:
                            app._historical_query_page_number == page)
                        self.assertEqual(len(app._historical_event_records), 100)
                    selected_index = next(
                        index for index, event in enumerate(app._historical_event_records)
                        if event.source == "round")
                    selected = app._historical_event_records[selected_index]
                    self.click_tk_listbox_row(
                        root, app.historical_event_list, selected_index)
                    self.wait_for_ui(
                        root, lambda: app._historical_event_detail_request_id is None and
                        "QP3 detail {}".format(selected.sequence) in
                        app.historical_event_detail.get("1.0", "end"))
                    selected_key = app._historical_event_selected_key

                    self.set_language_for_test_setup(app, root, TRADITIONAL_CHINESE)
                    self.wait_for_ui(root, lambda: app._historical_event_detail_request_id is None)
                    self.assertEqual(app._historical_query_page_number, 5)
                    self.assertEqual(app._historical_event_selected_key, selected_key)
                    self.assertIn("QP3 detail {}".format(selected.sequence),
                                  app.historical_event_detail.get("1.0", "end"))
                    self.assertLessEqual(result.cached_summary_count, 500)

                    self.click_tk_widget(root, app.historical_next_button)
                    self.wait_for_ui(root, lambda: app._historical_requested_page_number == 6)
                    self.assertEqual(app._historical_query_page_number, 5)
                    release_read.set()
                    self.wait_for_ui(root, lambda: app._historical_query_page_number == 6)
                    self.wait_for_ui(root, lambda: result.preparation_complete)
                    self.assertIn(500, read_offsets)
                    self.assertLessEqual(result.cached_summary_count, 500)
                    self.assertEqual(audit_path.read_bytes(), source_bytes)
                    self.assertEqual(app.app_events.path.read_bytes(), app_event_bytes)

                    # Requery through the visible Search button, then cancel it
                    # through the visible Cancel button while its source read is gated.
                    previous_result = app._historical_query_result
                    query_entered, release_query = threading.Event(), threading.Event()
                    query_function = app._historical_query_session._query_service._query_function

                    def gated_query(*args, **kwargs):
                        query_entered.set()
                        if not release_query.wait(20):
                            raise RuntimeError("controlled QP3 requery gate timed out")
                        return query_function(*args, **kwargs)

                    app._historical_query_session._query_service._query_function = gated_query
                    self.click_tk_widget(root, app.historical_event_refresh_button)
                    self.wait_for_ui(root, query_entered.is_set)
                    self.assertIs(app._historical_query_result, previous_result)
                    self.click_tk_widget(root, app.historical_event_cancel_button)
                    self.assertIsNone(app._historical_query_generation)
                    self.assertIs(app._historical_query_result, previous_result)
                    release_query.set()
                    self.wait_for_ui(
                        root, lambda: app._historical_query_session._query_service._worker is None)
                    root.update()
                    self.assertIs(app._historical_query_result, previous_result)
                    self.assertEqual(audit_path.read_bytes(), source_bytes)
                    self.assertEqual(app.app_events.path.read_bytes(), app_event_bytes)
                    release_query.clear()
            finally:
                release_read.set()
                if "release_query" in locals():
                    release_query.set()
                app._close_historical_event_window()
                app.hotkey.close()
                root.destroy()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_real_tk_reads_five_pages_while_remaining_batches_are_paused(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"), \
                patch.object(RoundCoordinator, "start_retention_schedule", return_value=None):
            root_path = Path(temporary)
            sessions = root_path / "sessions"
            round_id = "qp2-paused-batches"
            audit_path = sessions / round_id / "audit.jsonl"
            audit_path.parent.mkdir(parents=True)
            today = datetime.now().astimezone().date()
            occurred_at = datetime.combine(
                today, datetime.min.time(), datetime.now().astimezone().tzinfo).isoformat()
            header = {
                "record_type": "round", "schema_version": 1,
                "round_id": round_id, "station": "FCT", "config": {},
                "time_contract": {},
            }
            records = [header]
            for sequence in range(1, 502):
                records.append({
                    "record_type": "event", "schema_version": 1,
                    "round_id": round_id, "sequence": sequence,
                    "kind": "round_ready", "message": "event {}".format(sequence),
                    "observed_at": occurred_at, "elapsed_seconds": float(sequence),
                    "display_position": None,
                    "detail": {"raw_diagnostic": "QP2 detail {}".format(sequence)},
                })
            audit_path.write_text(
                "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
            source_bytes = audit_path.read_bytes()
            entered_batch, release_batch = threading.Event(), threading.Event()
            original_prepare = historical_event_query._prepare_remaining_query_batches

            def blocked_prepare(result, cancellation_event, batch_size=100):
                entered_batch.set()
                if not release_batch.wait(20):
                    raise RuntimeError("controlled QP2 batch gate timed out")
                return original_prepare(result, cancellation_event, batch_size)

            root = tk.Tk()
            root.deiconify()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey, session_root=sessions,
                app_event_path=root_path / "app-events.json")
            try:
                self.wait_for(lambda: app.app_events.status().complete)
                app.open_historical_events()
                with patch.object(historical_event_query,
                                  "_prepare_remaining_query_batches",
                                  side_effect=blocked_prepare):
                    self.click_tk_widget(root, app.historical_event_refresh_button)
                    self.wait_for_ui(root, lambda: app._historical_query_result is not None)
                    self.assertTrue(entered_batch.wait(2))
                    result = app._historical_query_result
                    self.assertGreaterEqual(result.total_count, 501)
                    self.assertEqual(len(result.initial_events), 500)
                    self.assertFalse(result.preparation_complete)
                    snapshot = sqlite3.connect(str(result._store_path))
                    try:
                        self.assertEqual(snapshot.execute(
                            "SELECT COUNT(*) FROM matching_events").fetchone()[0],
                            result.total_count)
                        self.assertEqual(snapshot.execute(
                            "SELECT COUNT(*) FROM prepared_events").fetchone()[0], 500)
                        columns = {row[1] for row in snapshot.execute(
                            "PRAGMA table_info(matching_events)")}
                        self.assertNotIn("summary_json", columns)
                        self.assertNotIn("event_json", columns)
                    finally:
                        snapshot.close()
                    self.assertIn(app._t("app.settings.history.preparing"),
                                  app.historical_query_status.cget("text"))

                    for page_number in range(1, 6):
                        if page_number > 1:
                            self.click_tk_widget(root, app.historical_next_button)
                        self.wait_for_ui(
                            root, lambda expected=page_number:
                            app._historical_query_page_number == expected)
                        self.assertEqual(app._historical_query_page_number, page_number)
                        self.assertEqual(len(app._historical_event_records), 100)
                        self.assertFalse(result.preparation_complete)
                        selected_index = next(
                            index for index, event in enumerate(app._historical_event_records)
                            if event.source == "round")
                        selected_sequence = app._historical_event_records[
                            selected_index].sequence
                        self.click_tk_listbox_row(
                            root, app.historical_event_list, selected_index)
                        self.wait_for_ui(
                            root, lambda: app._historical_event_detail_request_id is None and
                            "QP2 detail {}".format(selected_sequence) in
                            app.historical_event_detail.get("1.0", "end"))

                    language_index = next(
                        index for index in range(app.language_menu.index("end") + 1)
                        if app.language_menu.entrycget(index, "label") == language_name(ENGLISH))
                    app.language_menu.invoke(language_index)
                    root.update()
                    self.assertEqual(app.current_language, ENGLISH)
                    self.assertFalse(result.preparation_complete)
                    self.click_tk_widget(root, app.historical_next_button)
                    self.wait_for_ui(root, lambda: app._historical_requested_page_number == 6)
                    self.assertEqual(app._historical_query_page_number, 5)
                    self.assertEqual(app.historical_page_label.cget("text"),
                                     app._t("app.settings.history.page_loading", page=6))
                    release_batch.set()
                    self.wait_for_ui(root, lambda: app._historical_query_page_number == 6)
                    self.wait_for_ui(root, lambda: result.preparation_complete)
                    self.assertEqual(result.prepared_count, result.total_count)
                self.assertEqual(audit_path.read_bytes(), source_bytes)
            finally:
                release_batch.set()
                app._close_historical_event_window()
                app.hotkey.close()
                root.destroy()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_real_tk_fallback_keeps_page_six_loading_until_prepared(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"), \
                patch.object(RoundCoordinator, "start_retention_schedule", return_value=None):
            root_path = Path(temporary)
            sessions = root_path / "sessions"
            round_id = "qp2-fallback-paused-batches"
            audit_path = sessions / round_id / "audit.jsonl"
            audit_path.parent.mkdir(parents=True)
            today = datetime.now().astimezone().date()
            occurred_at = datetime.combine(
                today, datetime.min.time(), datetime.now().astimezone().tzinfo).isoformat()
            records = [{
                "record_type": "round", "schema_version": 1,
                "round_id": round_id, "station": "FCT", "config": {},
                "time_contract": {},
            }]
            for sequence in range(1, 502):
                records.append({
                    "record_type": "event", "schema_version": 1,
                    "round_id": round_id, "sequence": sequence,
                    "kind": "round_ready", "message": "fallback event {}".format(sequence),
                    "observed_at": occurred_at, "elapsed_seconds": float(sequence),
                    "display_position": None,
                    "detail": {"raw_diagnostic": "fallback detail {}".format(sequence)},
                })
            audit_path.write_text(
                "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
            entered_batch, release_batch = threading.Event(), threading.Event()
            original_prepare = historical_event_query._prepare_remaining_query_batches

            def blocked_prepare(result, cancellation_event, batch_size=100):
                entered_batch.set()
                if not release_batch.wait(20):
                    raise RuntimeError("controlled QP2 fallback batch gate timed out")
                return original_prepare(result, cancellation_event, batch_size)

            root = tk.Tk()
            root.deiconify()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey, session_root=sessions,
                app_event_path=root_path / "app-events.json")
            app._historical_query_session._query_service._index_path = None
            try:
                self.wait_for(lambda: app.app_events.status().complete)
                app.open_historical_events()
                with patch.object(historical_event_query,
                                  "_prepare_remaining_query_batches",
                                  side_effect=blocked_prepare):
                    self.click_tk_widget(root, app.historical_event_refresh_button)
                    self.wait_for_ui(root, lambda: app._historical_query_result is not None)
                    self.assertTrue(entered_batch.wait(2))
                    result = app._historical_query_result
                    # The 501 audit events are accompanied by one round record.
                    self.assertEqual(result.total_count, 502)
                    self.assertEqual(result.prepared_count, 500)
                    self.assertFalse(result.preparation_complete)
                    for page_number in range(2, 6):
                        self.click_tk_widget(root, app.historical_next_button)
                        self.wait_for_ui(
                            root, lambda expected=page_number:
                            app._historical_query_page_number == expected)
                    self.click_tk_widget(root, app.historical_next_button)
                    self.wait_for_ui(root, lambda: app._historical_requested_page_number == 6)
                    self.assertEqual(app._historical_query_page_number, 5)
                    self.assertEqual(
                        app.historical_page_label.cget("text"),
                        app._t("app.settings.history.page_loading", page=6))
                    release_batch.set()
                    self.wait_for_ui(root, lambda: app._historical_query_page_number == 6)
                    self.wait_for_ui(root, lambda: result.preparation_complete)
                    self.assertEqual(result.prepared_count, 502)
            finally:
                release_batch.set()
                app._close_historical_event_window()
                app.hotkey.close()
                root.destroy()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_real_tk_keeps_later_preparation_failure_visible(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"), \
                patch.object(RoundCoordinator, "start_retention_schedule", return_value=None):
            root_path = Path(temporary)
            sessions = root_path / "sessions"
            round_id = "qp2-failed-later-batches"
            audit_path = sessions / round_id / "audit.jsonl"
            audit_path.parent.mkdir(parents=True)
            today = datetime.now().astimezone().date()
            occurred_at = datetime.combine(
                today, datetime.min.time(), datetime.now().astimezone().tzinfo).isoformat()
            records = [{
                "record_type": "round", "schema_version": 1,
                "round_id": round_id, "station": "FCT", "config": {},
                "time_contract": {},
            }]
            for sequence in range(1, 502):
                records.append({
                    "record_type": "event", "schema_version": 1,
                    "round_id": round_id, "sequence": sequence,
                    "kind": "round_ready", "message": "event {}".format(sequence),
                    "observed_at": occurred_at, "elapsed_seconds": float(sequence),
                    "display_position": None,
                    "detail": {"raw_diagnostic": "QP2 failure detail {}".format(sequence)},
                })
            audit_path.write_text(
                "".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
            source_bytes = audit_path.read_bytes()
            root = tk.Tk()
            root.deiconify()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey, session_root=sessions,
                app_event_path=root_path / "app-events.json")
            try:
                self.wait_for(lambda: app.app_events.status().complete)
                app.open_historical_events()
                with patch.object(
                        historical_event_query, "_prepare_remaining_query_batches",
                        side_effect=OSError("controlled later-page failure")):
                    self.click_tk_widget(root, app.historical_event_refresh_button)
                    self.wait_for_ui(
                        root, lambda: "controlled later-page failure" in
                        app.historical_query_status.cget("text"))
                    self.assertIsNotNone(app._historical_query_result)
                    self.assertIsInstance(
                        app._historical_query_result.preparation_error, OSError)
                    self.assertEqual(len(app._historical_event_records), 100)
                    self.assertEqual(
                        app.historical_query_status.cget("text"),
                        app._t("app.settings.history.preparation_failed",
                               reason="controlled later-page failure"))
                    self.assertEqual(str(app.historical_event_retry_button.cget("state")),
                                     "normal")
                    retry_hint = next(
                        hint for hint in app._historical_control_hints
                        if hint._widget is app.historical_event_retry_button)
                    app.historical_event_retry_button.event_generate("<Enter>")
                    self.wait_for_ui(
                        root, lambda: retry_hint._window is not None and
                        retry_hint._window.winfo_exists())
                    self.assertIn("Retry preparation of the remaining pages",
                                  retry_hint._label.cget("text"))
                    retry_hint._hide()
                    self.assertNotIn(app._t("app.settings.history.preparing"),
                                     app.historical_query_status.cget("text"))
                self.assertEqual(audit_path.read_bytes(), source_bytes)
            finally:
                app._close_historical_event_window()
                app.hotkey.close()
                root.destroy()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_real_tk_fixed_history_coexists_with_official_app_event_cleanup(self):
        old_event_time = datetime(2026, 9, 1, 8, 0, tzinfo=timezone.utc)
        event_clock = [old_event_time]
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"), \
                patch.object(RoundCoordinator, "start_retention_schedule", return_value=None):
            root_path = Path(temporary)
            root = tk.Tk()
            root.deiconify()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey,
                session_root=root_path / "sessions",
                app_event_path=root_path / "app-events.json",
                app_event_clock=lambda: event_clock[0])
            try:
                self.wait_for(lambda: app.app_events.status().complete)
                first = app.app_events.record(
                    "app.hotkey.unavailable", {}, "loaded original diagnostic")
                second = app.app_events.record(
                    "app.profile.save_failed", {"reason": "old device"},
                    "not loaded original diagnostic")
                self.assertTrue(app.app_events.flush())
                source_before_query = app.app_events.path.read_bytes()

                app.open_historical_events()
                app.historical_start_var.set("2026-09-01")
                app.historical_end_var.set("2026-09-01")
                self.click_tk_widget(root, app.historical_event_refresh_button)
                self.wait_for_ui(root, lambda: app._historical_query_result is not None and
                                 app._historical_query_generation is None)
                result = app._historical_query_result
                self.assertIn("app:{}".format(first.event_id),
                              {event.key for event in app._historical_event_records})
                self.assertIn("app:{}".format(second.event_id),
                              {event.key for event in app._historical_event_records})
                fixed_keys_before_save = {event.key for event in app._historical_event_records}
                fixed_count_before_save = result.total_count
                index_path = root_path / "historical-event-query-index.sqlite3"
                index_before_cleanup = index_path.read_bytes()
                self.assertEqual(app.app_events.path.read_bytes(), source_before_query)

                # A public, successful save after submission must not mutate the
                # displayed fixed set; only the normal Search path refreshes it.
                event_clock[0] += timedelta(seconds=1)
                added = app.app_events.record(
                    "app.profile.save_failed", {"reason": "saved after query"},
                    "newly saved detail")
                self.assertTrue(app.app_events.flush())
                self.assertEqual(result.total_count, fixed_count_before_save)
                self.assertEqual({event.key for event in app._historical_event_records},
                                 fixed_keys_before_save)
                self.assertNotIn("app:{}".format(added.event_id),
                                 {event.key for event in app._historical_event_records})

                self.click_tk_widget(root, app.historical_event_refresh_button)
                self.wait_for_ui(root, lambda: app._historical_query_result is not result and
                                 app._historical_query_generation is None)
                result = app._historical_query_result
                self.assertEqual(result.total_count, fixed_count_before_save + 1)
                self.assertIn("app:{}".format(added.event_id),
                              {event.key for event in app._historical_event_records})
                source_before_query = app.app_events.path.read_bytes()
                index_before_cleanup = index_path.read_bytes()

                first_index = next(index for index, event in enumerate(
                    app._historical_event_records)
                    if event.key == "app:{}".format(first.event_id))
                self.click_tk_listbox_row(root, app.historical_event_list, first_index)
                self.wait_for_ui(root, lambda: "loaded original diagnostic" in
                                 app.historical_event_detail.get("1.0", "end"))

                # This invokes the registered App journal retention path while the
                # fixed query window and its temporary snapshot remain open.
                event_clock[0] = datetime.now(timezone.utc)
                app.rounds.request_retention_cleanup(30, "app-startup")
                self.wait_for(lambda: app.rounds.retention_cleanup_status().status in {
                    "complete", "failed"})
                cleanup = app.rounds.retention_cleanup_status()
                self.assertEqual(cleanup.status, "complete", cleanup)
                self.assertTrue(app.app_events.status().complete)
                self.assertNotEqual(app.app_events.path.read_bytes(), source_before_query)
                self.assertEqual(index_path.read_bytes(), index_before_cleanup)
                self.assertEqual(result.total_count, len(app._historical_event_records))
                self.assertIn("loaded original diagnostic",
                              app.historical_event_detail.get("1.0", "end"))

                second_index = next(index for index, event in enumerate(
                    app._historical_event_records)
                    if event.key == "app:{}".format(second.event_id))
                self.click_tk_listbox_row(root, app.historical_event_list, second_index)
                self.wait_for_ui(root, lambda: "not loaded original diagnostic" in
                                 app.historical_event_detail.get("1.0", "end"))
                self.assertEqual(app._historical_event_selected_key,
                                 "app:{}".format(second.event_id))

                chinese_index = next(
                    index for index in range(app.language_menu.index("end") + 1)
                    if app.language_menu.entrycget(index, "label") == "繁體中文")
                app.language_menu.invoke(chinese_index)
                root.update()
                self.assertEqual(app._historical_event_selected_key,
                                 "app:{}".format(second.event_id))
                self.assertIn("not loaded original diagnostic",
                              app.historical_event_detail.get("1.0", "end"))

                english_index = next(
                    index for index in range(app.language_menu.index("end") + 1)
                    if app.language_menu.entrycget(index, "label") == "English")
                app.language_menu.invoke(english_index)
                root.update()
                self.assertEqual(app._historical_event_selected_key,
                                 "app:{}".format(second.event_id))
                self.assertIn("not loaded original diagnostic",
                              app.historical_event_detail.get("1.0", "end"))

                self.click_tk_widget(root, app.historical_event_refresh_button)
                self.wait_for_ui(root, lambda: app._historical_query_result is not result and
                                 app._historical_query_generation is None)
                self.assertEqual(app._historical_query_result.total_count, 0)
                self.assertEqual(app._historical_query_result.page_count, 0)
                self.assertNotEqual(index_path.read_bytes(), index_before_cleanup)
                self.assertEqual(app.rounds.retention_cleanup_status().status, "complete")
            finally:
                app._close_historical_event_window()
                app.close()
                try:
                    self.wait_for_ui(root, lambda: not root.winfo_exists() or
                                     app.rounds.close_status().status in {
                                         "complete", "failed"})
                    self.assertEqual(app.rounds.close_status().status, "complete",
                                     app.rounds.close_status())
                finally:
                    if root.winfo_exists():
                        app.rounds.request_close()
                        app.hotkey.close()
                        root.destroy()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_real_tk_history_degraded_index_and_paged_unknown_date_diagnostics(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"), \
                patch.object(RoundCoordinator, "start_retention_schedule", return_value=None):
            root_path = Path(temporary)
            session_root = root_path / "sessions"
            legacy_path = session_root / "legacy" / "events.log"
            legacy_path.parent.mkdir(parents=True)
            raw_lines = [(json.dumps({
                "timestamp": "unknown-date-{}".format(index),
                "message": "legacy anomaly {}".format(index),
                "detail": {"raw_diagnostic": "source diagnostic {}".format(index)},
            }) + "\n") for index in range(105)]
            legacy_path.write_text("".join(raw_lines), encoding="utf-8")
            legacy_before = legacy_path.read_bytes()
            index_path = root_path / "historical-event-query-index.sqlite3"
            index_path.mkdir()

            root = tk.Tk()
            root.deiconify()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey, session_root=session_root,
                app_event_path=root_path / "app-events.json")
            try:
                self.wait_for(lambda: app.app_events.status().complete)
                app_bytes = app.app_events.path.read_bytes()
                app.open_historical_events()
                app.historical_start_var.set("2020-01-01")
                app.historical_end_var.set("2020-01-01")
                self.click_tk_widget(root, app.historical_event_refresh_button)
                self.wait_for_ui(root, lambda: app._historical_query_result is not None and
                                 app._historical_query_generation is None)

                result = app._historical_query_result
                self.assertEqual(result.total_count, 0)
                self.assertEqual(result.unclassified_count, 105)
                self.assertEqual(result.diagnostic_count, 105)
                self.assertTrue(result.index_degraded)
                self.assertIn("history acceleration data is temporarily unavailable",
                              app.historical_query_status.cget("text"))
                self.assertIn("History may be incomplete",
                              app.historical_query_status.cget("text"))
                self.assertTrue(index_path.is_dir())
                self.assertEqual(legacy_path.read_bytes(), legacy_before)
                self.assertEqual(app.app_events.path.read_bytes(), app_bytes)

                # Open the warning entry with an actual Tk listbox click; diagnostic
                # rows are fetched in pages and their source text is loaded on select.
                self.click_tk_listbox_row(root, app.historical_event_list, 0)
                self.wait_for_ui(root, lambda: app._historical_showing_diagnostics and
                                 len(app._historical_event_records) == 100)
                self.click_tk_widget(root, app.historical_next_button)
                self.wait_for_ui(root, lambda: app._historical_diagnostic_page_number == 2)
                self.assertEqual(len(app._historical_event_records), 5)
                self.click_tk_listbox_row(root, app.historical_event_list, 1)
                self.wait_for_ui(root, lambda: "source diagnostic" in
                                 app.historical_event_detail.get("1.0", "end"))
                detail_text = app.historical_event_detail.get("1.0", "end")
                self.assertIn('"timestamp": "unknown-date-', detail_text)
                selected_diagnostic = app._historical_event_selected_key
                chinese_index = next(
                    index for index in range(app.language_menu.index("end") + 1)
                    if app.language_menu.entrycget(index, "label") == "繁體中文")
                app.language_menu.invoke(chinese_index)
                root.update()
                self.assertEqual(app._historical_event_selected_key, selected_diagnostic)
                self.assertIn("source diagnostic",
                              app.historical_event_detail.get("1.0", "end"))
                self.assertIn("查詢加速資料暫時不可用，這次可能較慢",
                              app.historical_query_status.cget("text"))
                english_index = next(
                    index for index in range(app.language_menu.index("end") + 1)
                    if app.language_menu.entrycget(index, "label") == "English")
                app.language_menu.invoke(english_index)
                root.update()

                # Repair the derivative path and retry through the same visible query.
                index_path.rmdir()
                self.click_tk_widget(root, app.historical_event_refresh_button)
                self.wait_for_ui(root, lambda: app._historical_query_result is not result and
                                 app._historical_query_generation is None)
                self.assertFalse(app._historical_query_result.index_degraded)
                self.assertTrue(index_path.is_file())
                self.assertNotIn("history acceleration data is temporarily unavailable",
                                 app.historical_query_status.cget("text"))
                self.assertEqual(legacy_path.read_bytes(), legacy_before)
                self.assertEqual(app.app_events.path.read_bytes(), app_bytes)
            finally:
                app._close_historical_event_window()
                app.hotkey.close()
                root.destroy()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_real_tk_history_failed_query_reason_and_all_unreadable_sources(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"), \
                patch.object(RoundCoordinator, "start_retention_schedule", return_value=None):
            root_path = Path(temporary)
            session_root = root_path / "sessions"
            audit_path = session_root / "audit-round" / "audit.jsonl"
            audit_path.parent.mkdir(parents=True)
            audit_path.write_bytes(b"invalid audit fixture\\n")
            legacy_path = session_root / "legacy-round" / "events.log"
            legacy_path.parent.mkdir(parents=True)
            legacy_path.write_bytes(bytes((0xff, 0xfe, 0xfd)))

            root = tk.Tk()
            root.deiconify()
            app_path = root_path / "app-events.json"
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey, session_root=session_root,
                app_event_path=app_path)
            app_source_original = None
            try:
                self.wait_for(lambda: app.app_events.status().complete)
                app_source_original = app_path.read_bytes()
                app.open_historical_events()
                app.historical_start_var.set("2026-10-13")
                app.historical_end_var.set("2026-10-13")

                with patch("b518_log_solution.query_historical_events",
                           side_effect=RuntimeError("controlled source read failure")):
                    self.click_tk_widget(root, app.historical_event_refresh_button)
                    self.wait_for_ui(root, lambda: app._historical_query_status_key ==
                                     "app.settings.history.query_failed")
                self.assertIsNone(app._historical_query_result)
                failed_text = app.historical_query_status.cget("text")
                self.assertIn("controlled source read failure", failed_text)
                self.assertNotIn("previous results are kept", failed_text)

                # This isolated fixture simulates a corrupt App journal while the
                # real App is open; restore its original bytes before shutdown.
                app_path.write_bytes(b"invalid App journal fixture\\n")
                app_source_corrupt = app_path.read_bytes()
                self.click_tk_widget(root, app.historical_event_refresh_button)
                self.wait_for_ui(root, lambda: app._historical_query_result is not None and
                                 app._historical_query_generation is None)

                result = app._historical_query_result
                self.assertEqual(result.total_count, 0)
                self.assertEqual(result.source_issue_count, 3)
                self.assertEqual(result.unclassified_count, 0)
                self.assertEqual(result.diagnostic_count, 3)
                status = app.historical_query_status.cget("text")
                self.assertIn("History may be incomplete", status)
                self.assertNotIn("No events were found", status)
                self.assertIn("3 source issues", status)
                self.assertIn("0 records without a usable date", status)
                self.assertEqual(audit_path.read_bytes(), b"invalid audit fixture\\n")
                self.assertEqual(legacy_path.read_bytes(), bytes((0xff, 0xfe, 0xfd)))
                self.assertEqual(app_path.read_bytes(), app_source_corrupt)

                self.click_tk_listbox_row(root, app.historical_event_list, 0)
                self.wait_for_ui(root, lambda: app._historical_showing_diagnostics and
                                 len(app._historical_event_records) == 3)
                diagnostic_summaries = tuple(app._historical_event_records)
                detailed_records = []
                for index, summary in enumerate(diagnostic_summaries):
                    self.click_tk_listbox_row(root, app.historical_event_list, index + 1)
                    self.wait_for_ui(
                        root, lambda expected=summary.key:
                        app._historical_event_selected_key == expected and
                        app._historical_event_selected_detail is not None)
                    detailed_records.append(app._historical_event_selected_detail)
                details_by_path = {
                    str(detail.raw_record.get("path", detail.raw_record.get("source_path"))):
                    detail for detail in detailed_records}
                for path in (audit_path, legacy_path, app_path):
                    self.assertIn(str(path), details_by_path)
                self.assertIn("Expecting value", details_by_path[str(audit_path)].message)
            finally:
                if app_source_original is not None and app_path.exists():
                    app_path.write_bytes(app_source_original)
                app._close_historical_event_window()
                app.hotkey.close()
                root.destroy()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_real_tk_history_retry_resumes_fixed_snapshot_and_keeps_reading_page(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"), \
                patch.object(RoundCoordinator, "start_retention_schedule", return_value=None):
            root_path = Path(temporary)
            session_root = root_path / "sessions"
            audit_path = session_root / "resume-round" / "audit.jsonl"
            audit_path.parent.mkdir(parents=True)
            round_record = {
                "record_type": "round", "schema_version": 1,
                "round_id": "resume-round", "station": "FCT", "config": {},
                "time_contract": {},
            }
            records = [round_record]
            for sequence in range(1, 702):
                records.append({
                    "record_type": "event", "schema_version": 1,
                    "round_id": "resume-round", "sequence": sequence,
                    "kind": "round_ready", "message": "original event {}".format(sequence),
                    "observed_at": "2026-10-13T08:{:02d}:{:02d}+00:00".format(
                        (sequence // 60) % 60, sequence % 60),
                    "elapsed_seconds": float(sequence), "display_position": None,
                    "detail": {"raw_diagnostic": "fixed detail {}".format(sequence)},
                })
            audit_path.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8")
            source_before = audit_path.read_bytes()

            root = tk.Tk()
            root.deiconify()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey, session_root=session_root,
                app_event_path=root_path / "app-events.json")
            try:
                self.wait_for(lambda: app.app_events.status().complete)
                app.open_historical_events()
                app.historical_start_var.set("2026-10-13")
                app.historical_end_var.set("2026-10-13")
                def fail_after_batch(result, cancellation_event, batch_size=100):
                    rows = result._read_unprepared_summaries(
                        result.prepared_count, 100)
                    result._persist_prepared_rows(rows)
                    raise OSError("controlled retry gate failure")

                with patch.object(historical_event_query,
                                  "_prepare_remaining_query_batches",
                                  side_effect=fail_after_batch):
                    self.click_tk_widget(root, app.historical_event_refresh_button)
                    self.wait_for_ui(root, lambda:
                                     app._historical_query_status_key ==
                                     "app.settings.history.preparation_failed")
                result = app._historical_query_result
                self.assertIsNotNone(result)
                self.assertEqual(result.total_count, 701)
                self.assertEqual(result.prepared_count, 600)
                self.assertEqual(app._historical_query_page_number, 1)
                self.assertEqual(str(app.historical_event_retry_button.cget("state")),
                                 "normal")
                first_page_key = app._historical_event_records[0].key
                self.click_tk_listbox_row(root, app.historical_event_list, 0)
                self.wait_for_ui(root, lambda:
                                 app._historical_event_selected_detail is not None)
                selected_detail = app._historical_event_selected_detail
                self.assertEqual(selected_detail.key, first_page_key)
                app._show_historical_event_page(5)
                self.wait_for_ui(root, lambda: app._historical_page_request_id is None and
                                 app._historical_query_page_number == 5)
                self.click_tk_listbox_row(root, app.historical_event_list, 0)
                selected_key = app._historical_event_selected_key
                self.wait_for_ui(root, lambda:
                                 app._historical_event_selected_detail is not None and
                                 app._historical_event_selected_detail.key == selected_key)
                app._select_language(ENGLISH)
                root.update()
                self.assertIn("Retry remaining pages",
                              app.historical_event_retry_button.cget("text"))

                retry_entered = threading.Event()
                release_retry = threading.Event()

                def cancel_gated_retry(_result, cancellation_event, batch_size=100):
                    retry_entered.set()
                    if not release_retry.wait(5):
                        raise OSError("controlled retry cancellation gate timed out")
                    if cancellation_event.is_set():
                        raise RuntimeError("historical event query cancelled")

                with patch.object(historical_event_query,
                                  "_prepare_remaining_query_batches",
                                  side_effect=cancel_gated_retry):
                    self.click_tk_widget(root, app.historical_event_retry_button)
                    self.assertTrue(retry_entered.wait(2))
                    self.click_tk_widget(root, app.historical_event_cancel_button)
                    self.assertEqual(app._historical_query_status_key,
                                     "app.settings.history.query_cancelled")
                    release_retry.set()
                    self.wait_for_ui(
                        root, lambda: result.preparation_complete and
                        str(app.historical_event_retry_button.cget("state")) == "normal")
                self.assertEqual(result.prepared_count, 600)
                self.assertIsInstance(result.preparation_error, RuntimeError)
                self.assertEqual(app._historical_query_page_number, 5)
                self.assertEqual(app._historical_event_selected_key, selected_key)

                appended = {
                    "record_type": "event", "schema_version": 1,
                    "round_id": "resume-round", "sequence": 702,
                    "kind": "round_ready", "message": "new after query",
                    "observed_at": "2026-10-13T23:59:59+00:00",
                    "elapsed_seconds": 702.0, "display_position": None,
                    "detail": {"raw_diagnostic": "new source version"},
                }
                with audit_path.open("ab") as source:
                    source.write((json.dumps(appended) + "\n").encode("utf-8"))

                self.click_tk_widget(root, app.historical_event_retry_button)
                self.wait_for_ui(root, lambda: app._historical_query_generation is None and
                                 result.preparation_complete and
                                 result.preparation_error is None)
                self.assertIs(app._historical_query_result, result)
                self.assertEqual(result.total_count, 701)
                self.assertEqual(result.prepared_count, 701)
                self.assertEqual(app._historical_query_page_number, 5)
                self.assertEqual(app._historical_event_selected_key, selected_key)
                self.assertEqual(app._historical_event_selected_detail.key, selected_key)
                self.assertEqual(app.historical_query_status.cget("text"),
                                 "701 events found for 2026-10-13 through 2026-10-13.")
                self.assertEqual(
                    result.get_detail("round:resume-round:701").raw_record["detail"][
                        "raw_diagnostic"], "fixed detail 701")
                self.assertEqual(audit_path.read_bytes(),
                                 source_before + (json.dumps(appended) + "\n").encode())
                self.assertNotIn("round:resume-round:702", {
                    event.key for page in range(1, result.page_count + 1)
                    for event in result.get_page(page).events})
                app._select_language(TRADITIONAL_CHINESE)
                root.update()
                self.assertIn("共找到 701 筆事件", app.historical_query_status.cget("text"))
            finally:
                if "release_retry" in locals():
                    release_retry.set()
                app._close_historical_event_window()
                app.hotkey.close()
                root.destroy()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_real_tk_history_controls_have_names_and_keyboard_activation_is_scoped(self):
        from audit_records import AuditEvent, RoundAuditStore

        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"), \
                patch.object(RoundCoordinator, "start_retention_schedule", return_value=None):
            root_path = Path(temporary)
            session_root = root_path / "sessions"
            audit = RoundAuditStore(
                session_root, "keyboard-history", "FCT", "2026-10-14T00:00:00+08:00", 0.0)
            event_time = datetime.now().astimezone().replace(microsecond=0).isoformat()
            for sequence in range(1, 206):
                audit.append_event(AuditEvent(
                    sequence, "round_ready", "saved keyboard event", None),
                    event_time, float(sequence))
            self.assertTrue(audit.flush())
            source_bytes = audit.audit_path.read_bytes()

            root = tk.Tk()
            root.deiconify()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey, session_root=session_root,
                app_event_path=root_path / "app-events.json")
            try:
                self.wait_for(lambda: app.app_events.status().complete)
                app.open_historical_events()

                # Enter in a date field edits/submits no work; Search must be activated directly.
                app.historical_start_entry.focus_force()
                app.historical_start_entry.event_generate("<KeyPress-Return>")
                app.historical_start_entry.event_generate("<KeyRelease-Return>")
                root.update()
                self.assertIsNone(app._historical_query_generation)
                self.assertIsNone(app._historical_query_result)
                app.historical_event_list.focus_force()
                app.historical_event_list.event_generate("<KeyPress-Return>")
                app.historical_event_list.event_generate("<KeyRelease-Return>")
                root.update()
                self.assertIsNone(app._historical_query_generation)
                self.assertIsNone(app._historical_query_result)

                app.historical_start_entry.focus_force()

                def focus_next_with_tab(target):
                    focused = app.historical_start_entry.winfo_toplevel().focus_get()
                    for _ in range(50):
                        if focused is target:
                            return
                        focused.event_generate("<KeyPress-Tab>")
                        focused.event_generate("<KeyRelease-Tab>")
                        root.update()
                        focused = app.historical_start_entry.winfo_toplevel().focus_get()
                        self.assertIsNotNone(focused, "Tab navigation lost keyboard focus")
                    self.fail("Tab navigation did not reach {}".format(target))

                def visible_hint_text():
                    pending = list(root.winfo_children())
                    while pending:
                        child = pending.pop()
                        if (isinstance(child, tk.Toplevel) and
                                child is not app.historical_event_window and
                                child.winfo_exists()):
                            labels = [item.cget("text") for item in child.winfo_children()
                                      if isinstance(item, (tk.Label, ttk.Label))]
                            if labels:
                                return " ".join(labels)
                        pending.extend(child.winfo_children())
                    return None

                focus_next_with_tab(app.historical_event_refresh_button)
                app.historical_event_refresh_button.event_generate("<KeyPress-space>")
                app.historical_event_refresh_button.event_generate("<KeyRelease-space>")
                self.wait_for_ui(root, lambda: app._historical_query_result is not None)
                self.assertGreater(app._historical_query_result.total_count, 200)
                self.assertEqual(app.historical_previous_button.cget("text"), "←")
                self.assertEqual(app.historical_next_button.cget("text"), "→")
                self.assertEqual(str(app.historical_previous_button.cget("state")), "disabled")
                self.assertIn(app._t("app.settings.history.search"),
                              app.historical_event_refresh_button.cget("text"))

                focus_next_with_tab(app.historical_next_button)
                self.wait_for_ui(root, lambda: visible_hint_text() is not None)
                self.assertEqual(visible_hint_text(), "Show the next results page")
                app.historical_next_button.event_generate("<KeyPress-space>")
                app.historical_next_button.event_generate("<KeyRelease-space>")
                self.wait_for_ui(root, lambda: app._historical_query_page_number == 2)
                self.assertEqual(str(app.historical_previous_button.cget("state")), "normal")
                app.historical_next_button.event_generate("<KeyPress-space>")
                app.historical_next_button.event_generate("<KeyRelease-space>")
                self.wait_for_ui(root, lambda: app._historical_query_page_number == 3)
                self.assertEqual(str(app.historical_next_button.cget("state")), "disabled")
                app.historical_next_button.event_generate("<KeyPress-space>")
                app.historical_next_button.event_generate("<KeyRelease-space>")
                root.update()
                self.assertEqual(app._historical_query_page_number, 3)
                self.assertEqual(visible_hint_text(),
                                 "There is no later results page to show.")
                focus_next_with_tab(app.historical_previous_button)
                self.wait_for_ui(root, lambda: visible_hint_text() is not None)
                self.assertEqual(visible_hint_text(), "Show the previous results page")
                app.historical_previous_button.event_generate("<KeyPress-space>")
                app.historical_previous_button.event_generate("<KeyRelease-space>")
                self.wait_for_ui(root, lambda: app._historical_query_page_number == 2)
                app.historical_previous_button.event_generate("<KeyPress-space>")
                app.historical_previous_button.event_generate("<KeyRelease-space>")
                self.wait_for_ui(root, lambda: app._historical_query_page_number == 1)
                self.assertEqual(str(app.historical_previous_button.cget("state")), "disabled")
                app.historical_previous_button.event_generate("<KeyPress-space>")
                app.historical_previous_button.event_generate("<KeyRelease-space>")
                root.update()
                self.assertEqual(app._historical_query_page_number, 1)
                self.assertEqual(audit.audit_path.read_bytes(), source_bytes)
            finally:
                app._close_historical_event_window()
                app.hotkey.close()
                root.destroy()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_real_tk_history_hover_hint_updates_language_and_closes_with_window(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"), \
                patch.object(RoundCoordinator, "start_retention_schedule", return_value=None):
            root = tk.Tk()
            root.deiconify()
            app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey,
                                     app_event_path=Path(temporary) / "app-events.json")

            history_window = None

            def hints():
                def descendants(widget):
                    found = []
                    for child in widget.winfo_children():
                        found.append(child)
                        found.extend(descendants(child))
                    return found
                return [child for child in descendants(root)
                        if isinstance(child, tk.Toplevel) and child is not root and
                        child is not history_window and child.winfo_exists()]

            def hint_text(window):
                return [child.cget("text") for child in window.winfo_children()
                        if isinstance(child, (tk.Label, ttk.Label))]

            try:
                self.wait_for(lambda: app.app_events.status().complete)
                app.open_historical_events()
                history_window = app.historical_event_window
                app.historical_event_refresh_button.event_generate(
                    "<Motion>", x=max(2, app.historical_event_refresh_button.winfo_width() // 2),
                    y=max(2, app.historical_event_refresh_button.winfo_height() // 2),
                    warp=True)
                app.historical_event_refresh_button.event_generate("<Enter>")
                self.wait_for_ui(root, lambda: len(hints()) == 1)
                hint = hints()[0]
                self.assertTrue(any(
                    text.startswith("Search the selected date range")
                    for text in hint_text(hint)))

                self.set_language_for_test_setup(app, root, TRADITIONAL_CHINESE)
                self.assertTrue(any(
                    text.startswith("查詢所選日期範圍") for text in hint_text(hint)))
                self.assertEqual(app._historical_query_result, None)
                self.assertIs(app.historical_event_window, history_window)

                app.historical_event_refresh_button.event_generate("<Leave>")
                self.wait_for_ui(root, lambda: len(hints()) == 0)
                app.historical_next_button.event_generate("<FocusIn>")
                root.update()
                self.assertEqual(hints(), [])
                app._close_historical_event_window()
                self.assertFalse(history_window.winfo_exists())
                root.update()
                self.assertEqual(hints(), [])
            finally:
                app._close_historical_event_window()
                app.hotkey.close()
                root.destroy()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_real_tk_history_and_diagnostics_controls_explain_current_actions(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"), \
                patch.object(RoundCoordinator, "start_retention_schedule", return_value=None):
            root = tk.Tk()
            root.deiconify()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey,
                app_event_path=Path(temporary) / "app-events.json")
            try:
                self.wait_for(lambda: app.app_events.status().complete)
                app.open_historical_events()
                app.open_app_diagnostics()
                root.update()

                def show_hint(widget):
                    visible = _LocalizedControlHint._visible_hint
                    if visible is not None and visible._widget is not widget:
                        visible._widget.event_generate("<Leave>")
                        root.update()
                    widget.event_generate(
                        "<Motion>", x=max(2, widget.winfo_width() // 2),
                        y=max(2, widget.winfo_height() // 2), warp=True)
                    widget.event_generate("<Enter>")
                    self.wait_for_ui(root, lambda:
                                     _LocalizedControlHint._visible_hint is not None and
                                     _LocalizedControlHint._visible_hint._widget is widget and
                                     _LocalizedControlHint._visible_hint._window is not None)
                    hint = _LocalizedControlHint._visible_hint
                    root.update()
                    return hint._label.cget("text")

                def wait_for_physical_hover(widget, expected_text):
                    hint = next(item for item in app._historical_control_hints
                                if item._widget is widget)
                    hint._hide()
                    hint._pointer_inside = False
                    hint._focused = False
                    app.historical_event_window.lift()
                    root.update()
                    x = widget.winfo_rootx() + widget.winfo_width() // 2
                    y = widget.winfo_rooty() + widget.winfo_height() // 2
                    print("ST6: historical window foreground; move physical pointer outside, "
                          "then hover disabled Cancel search at ({}, {}) for 0.5s.".format(
                              x, y), flush=True)
                    deadline = time.monotonic() + 90
                    while time.monotonic() < deadline:
                        root.update()
                        if (hint._pointer_inside and hint._window is not None and
                                hint._window.winfo_exists() and hint._window.winfo_viewable() and
                                hint._label.cget("text") == expected_text):
                            return hint._label.cget("text")
                        time.sleep(0.02)
                    self.fail("physical hover did not display the disabled Cancel search hint")

                before = (app.historical_start_var.get(), app.historical_end_var.get(),
                          app._historical_query_generation,
                          app.historical_event_list.curselection())
                cancel_hint = (wait_for_physical_hover(
                    app.historical_event_cancel_button,
                    "There is no search in progress to cancel.")
                    if os.environ.get("B518_MANUAL_HOVER") == "1" else
                    show_hint(app.historical_event_cancel_button))
                self.assertIn("There is no search in progress to cancel", cancel_hint)
                capture_native_window_with_hint(
                    app.historical_event_window, "st6-history-cancel-disabled-hint-en.png")
                self.assertEqual(before, (app.historical_start_var.get(),
                                          app.historical_end_var.get(),
                                          app._historical_query_generation,
                                          app.historical_event_list.curselection()))

                app._select_language(TRADITIONAL_CHINESE)
                root.update()
                query_entered = threading.Event()
                release_query = threading.Event()

                def gated_query(*args, **kwargs):
                    query_entered.set()
                    if not release_query.wait(5):
                        raise RuntimeError("controlled history search gate timed out")
                    raise RuntimeError("controlled history search cancelled")

                app.historical_start_var.set("2099-01-01")
                app.historical_end_var.set("2099-01-01")
                with patch("b518_log_solution.query_historical_events",
                           side_effect=gated_query):
                    self.click_tk_widget(root, app.historical_event_refresh_button)
                    self.assertTrue(query_entered.wait(2))
                    self.wait_for_ui(root, lambda: app._historical_query_generation is not None)
                    active_cancel_hint = show_hint(app.historical_event_cancel_button)
                    self.assertIn("取消目前的查詢", active_cancel_hint)
                    self.assertIsNotNone(app._historical_query_generation,
                                         "reading a hint must not cancel the search")
                    capture_native_window_with_hint(
                        app.historical_event_window,
                        "st6-history-cancel-active-hint-zh-TW.png")
                    app._cancel_historical_event_query()
                    release_query.set()
                    self.wait_for_ui(
                        root, lambda: app._historical_query_status_key ==
                        "app.settings.history.query_cancelled")

                app._select_language(TRADITIONAL_CHINESE)
                root.update()
                self.assertIn("目前沒有進行中的查詢可取消",
                              _LocalizedControlHint._visible_hint._label.cget("text"))
                capture_native_window_with_hint(
                    app.historical_event_window, "st6-history-cancel-disabled-hint-zh-TW.png")

                retry_hint = show_hint(app.historical_event_retry_button)
                self.assertIn("目前沒有可重試的歷史頁面", retry_hint)
                capture_native_window_with_hint(
                    app.historical_event_window, "st6-history-retry-disabled-hint-zh-TW.png")
                app._select_language(ENGLISH)
                root.update()
                diagnostics_retry_hint = show_hint(app.app_diagnostics_retry_button)
                self.assertIn("no App troubleshooting records waiting to be saved again",
                              diagnostics_retry_hint)
                capture_native_window_with_hint(
                    app.app_diagnostics_window,
                    "st6-diagnostics-save-retry-disabled-hint-en.png")
                app._select_language(TRADITIONAL_CHINESE)
                root.update()
                diagnostics_retry_hint = show_hint(app.app_diagnostics_retry_button)
                self.assertIn("目前沒有尚未存好的 App 問題紀錄", diagnostics_retry_hint)
                capture_native_window_with_hint(
                    app.app_diagnostics_window,
                    "st6-diagnostics-save-retry-disabled-hint-zh-TW.png")
                language_retry_hint = show_hint(app.app_diagnostics_language_retry_button)
                self.assertIn("目前沒有介面文字更新錯誤需要重試", language_retry_hint)
                close_hint = show_hint(app.app_diagnostics_close_button)
                self.assertIn("不會修改或刪除", close_hint)
                capture_native_window_with_hint(
                    app.app_diagnostics_window, "st6-diagnostics-close-hint-zh-TW.png")
            finally:
                app._close_historical_event_window()
                app._close_app_diagnostics_window()
                app.hotkey.close()
                root.destroy()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_real_tk_history_language_refresh_preserves_draft_snapshot_page_and_detail(self):
        from audit_records import AuditEvent, RoundAuditStore

        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"), \
                patch.object(RoundCoordinator, "start_retention_schedule", return_value=None):
            root_path = Path(temporary)
            session_root = root_path / "sessions"
            audit = RoundAuditStore(
                session_root, "language-history", "FCT", "2026-10-14T00:00:00+08:00", 0.0)
            event_time = datetime.now().astimezone().replace(microsecond=0).isoformat()
            raw_detail = "Keep original historical diagnostic — " * 500
            for sequence in range(1, 206):
                audit.append_event(AuditEvent(
                    sequence, "round_ready",
                    "saved language event — " + "LONG-READING-POSITION-" * 12, None,
                    detail={"raw_diagnostic": raw_detail if sequence == 103 else ""}),
                    event_time, float(sequence))
            self.assertTrue(audit.flush())
            source_bytes = audit.audit_path.read_bytes()
            legacy_path = session_root / "legacy-language" / "events.log"
            legacy_path.parent.mkdir(parents=True)
            legacy_record = json.dumps({
                "timestamp": datetime.now().astimezone().replace(
                    second=0, microsecond=0).isoformat(),
                "message": "Keep the original legacy wording",
            })
            legacy_path.write_text(legacy_record + "\n{malformed legacy record\n",
                                   encoding="utf-8")
            legacy_bytes = legacy_path.read_bytes()

            root = tk.Tk()
            root.deiconify()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey, session_root=session_root,
                app_event_path=root_path / "app-events.json")
            moved_source = audit.audit_path.with_suffix(".held")
            evidence_value = os.environ.get("B518_TK_EVIDENCE_DIR")
            evidence_root = Path(evidence_value) if evidence_value else None
            evidence_bounds = {}

            def control_bounds(widgets):
                root.update_idletasks()
                return {
                    name: [widget.winfo_x(), widget.winfo_y(),
                           widget.winfo_width(), widget.winfo_height()]
                    for name, widget in widgets.items()
                }

            def capture_window(language, key, window, widgets):
                if evidence_root is None:
                    return
                import Quartz
                from Foundation import NSURL

                window.lift()
                window.focus_force()
                root.update()
                native_windows = Quartz.CGWindowListCopyWindowInfo(
                    Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID)
                native_window = next((item for item in native_windows
                                      if item.get(Quartz.kCGWindowOwnerPID) == os.getpid()
                                      and item.get(Quartz.kCGWindowNumber) ==
                          native_window_for_capture(window).windowNumber()), None)
                self.assertIsNotNone(native_window, "missing native window: {}".format(key))
                image = capture_tk_window_image(window, native_window)
                self.assertIsNotNone(image)
                filename = "{}-{}.png".format(key, language)
                output = evidence_root / filename
                output.parent.mkdir(parents=True, exist_ok=True)
                destination = Quartz.CGImageDestinationCreateWithURL(
                    NSURL.fileURLWithPath_(str(output)), "public.png", 1, None)
                Quartz.CGImageDestinationAddImage(destination, image, None)
                self.assertTrue(Quartz.CGImageDestinationFinalize(destination))
                native_bounds = native_window[Quartz.kCGWindowBounds]
                evidence_bounds.setdefault(language, {})[key] = {
                    "title": window.title(),
                    "geometry": window.geometry(),
                    "native_bounds": {
                        name: float(native_bounds[name])
                        for name in ("X", "Y", "Width", "Height")
                    },
                    "image_pixels": {
                        "width": Quartz.CGImageGetWidth(image),
                        "height": Quartz.CGImageGetHeight(image),
                    },
                    "controls": control_bounds(widgets),
                    "source_sha256": {
                        "round_audit": hashlib.sha256(source_bytes).hexdigest(),
                        "legacy_events": hashlib.sha256(legacy_bytes).hexdigest(),
                        "app_events": hashlib.sha256(app_event_bytes).hexdigest(),
                    },
                    "screenshot": filename,
                }

            def capture_current_language(language):
                capture_window(language, "history-events", app.historical_event_window, {
                    "date_mode": app.historical_range_choice,
                    "date_start": app.historical_start_entry,
                    "date_end": app.historical_end_entry,
                    "previous": app.historical_previous_button,
                    "page": app.historical_page_label,
                    "next": app.historical_next_button,
                    "event_list": app.historical_event_list,
                    "detail": app.historical_event_detail,
                    "cancel": app.historical_event_cancel_button,
                    "search": app.historical_event_refresh_button,
                })
                capture_window(language, "app-diagnostics", app.app_diagnostics_window, {
                    "event_list": app.app_diagnostics_list,
                    "detail": app.app_diagnostics_detail,
                    "retry": app.app_diagnostics_retry_button,
                    "close": app.app_diagnostics_close_button,
                })
                app.historical_event_window.lift()
                root.update()

            try:
                self.wait_for(lambda: app.app_events.status().complete)
                app_event_bytes = app.app_events.path.read_bytes()
                app.open_app_diagnostics()
                app.open_historical_events()
                self.assertIsNone(app._historical_query_result)
                self.click_tk_widget(root, app.historical_event_refresh_button)
                self.wait_for_ui(root, lambda: app._historical_query_result is not None and
                                 app._historical_query_generation is None)
                original_result = app._historical_query_result
                original_range = original_result.date_range
                self.assertGreater(original_result.page_count, 2)
                self.assertGreater(original_result.diagnostic_count, 0)

                self.click_tk_widget(root, app.historical_next_button)
                self.wait_for_ui(root, lambda: app._historical_query_page_number == 2)
                selected_index = next(index for index, item in enumerate(
                    app._historical_event_records) if item.sequence == 103)
                self.click_tk_listbox_row(root, app.historical_event_list, selected_index)
                self.wait_for_ui(root, lambda: raw_detail[:40] in
                                 app.historical_event_detail.get("1.0", "end"))
                selected_key = app._historical_event_selected_key
                selected_detail = app._historical_event_selected_detail
                # Text estimates wrapped-line heights lazily for long raw
                # diagnostics. Complete its display metrics before taking a
                # precise reading-position baseline for the language switch.
                app.historical_event_detail.count("1.0", "end", "update", "ypixels")
                app.historical_event_detail.yview_moveto(0.4)
                app.historical_event_list.yview_moveto(0.35)
                app.historical_event_list.xview_moveto(0.35)
                root.update()
                detail_top = app.historical_event_detail.index("@0,0")
                list_left = app.historical_event_list.xview()[0]
                list_top_index = app.historical_event_list.index("@0,0")
                list_top_key = app._historical_event_records[list_top_index].key
                for widget in (app.historical_event_detail, app.app_diagnostics_detail):
                    self.assertEqual(widget.cget("background"), LIGHT_BACKGROUND)
                    self.assertEqual(int(widget.cget("borderwidth")), 1)
                    self.assertEqual(widget.cget("relief"), "solid")
                self.assertEqual(app.style.lookup("TEntry", "fieldbackground"),
                                 FIELD_BACKGROUND)
                self.assertTrue(app.historical_event_list.cget("xscrollcommand"))
                self.assertTrue(app.historical_event_list.cget("yscrollcommand"))
                self.assertEqual(app.app_diagnostics_retry_button.cget("text"),
                                 "Retry App Saves")
                self.assertEqual(app.app_diagnostics_close_button.cget("text"), "Close")
                en_history_size = (app.historical_event_window.winfo_width(),
                                   app.historical_event_window.winfo_height())
                en_diagnostics_size = (app.app_diagnostics_window.winfo_width(),
                                       app.app_diagnostics_window.winfo_height())
                en_history_bounds = control_bounds({
                    "mode": app.historical_range_choice,
                    "start": app.historical_start_entry,
                    "end": app.historical_end_entry,
                    "previous": app.historical_previous_button,
                    "page": app.historical_page_label,
                    "next": app.historical_next_button,
                    "list": app.historical_event_list,
                    "detail": app.historical_event_detail,
                    "cancel": app.historical_event_cancel_button,
                    "search": app.historical_event_refresh_button,
                })
                en_diagnostics_bounds = control_bounds({
                    "list": app.app_diagnostics_list,
                    "detail": app.app_diagnostics_detail,
                    "retry": app.app_diagnostics_retry_button,
                    "close": app.app_diagnostics_close_button,
                })
                capture_current_language("en")

                app.historical_start_var.set("not-a-date")
                app.historical_end_var.set("2026-")
                self.click_tk_widget(root, app.historical_event_refresh_button)
                self.assertEqual(app._historical_date_error_key,
                                 "app.settings.history.validation.start_invalid")
                self.assertEqual(app.historical_start_var.get(), "not-a-date")
                self.assertIsNone(app._historical_query_generation)
                english_validation = app.historical_date_error.cget("text")
                self.assertIn("valid start date", english_validation)

                os.replace(audit.audit_path, moved_source)
                self.set_language_for_test_setup(app, root, TRADITIONAL_CHINESE)
                root.update()
                self.assertEqual(app.current_language, TRADITIONAL_CHINESE)
                self.assertIs(app._historical_query_result, original_result)
                self.assertEqual(app._historical_query_result.date_range, original_range)
                self.assertEqual(app._historical_query_page_number, 2)
                self.assertEqual(app.historical_start_var.get(), "not-a-date")
                self.assertEqual(app.historical_end_var.get(), "2026-")
                self.assertEqual(app._historical_event_selected_key, selected_key)
                self.assertIs(app._historical_event_selected_detail, selected_detail)
                self.assertEqual(app.app_diagnostics_retry_button.cget("text"),
                                 "重試 App 保存")
                self.assertEqual(app.app_diagnostics_close_button.cget("text"), "關閉")
                self.assertIn("開始日期無效", app.historical_date_error.cget("text"))
                self.assertNotEqual(app.historical_date_error.cget("text"), english_validation)
                self.assertIn("第 2／3 頁", app.historical_page_label.cget("text"))
                self.assertIn("歷史讀取不完整", app.historical_query_status.cget("text"))
                self.assertIn(raw_detail[:40], app.historical_event_detail.get("1.0", "end"))
                self.assertEqual(detail_top, app.historical_event_detail.index("@0,0"))
                self.assertAlmostEqual(list_left, app.historical_event_list.xview()[0], places=2)
                restored_list_top = app.historical_event_list.index("@0,0")
                self.assertEqual(app._historical_event_records[restored_list_top].key,
                                 list_top_key)
                self.assertIsNone(app._historical_query_generation)
                self.assertFalse(audit.audit_path.exists())
                self.assertEqual(moved_source.read_bytes(), source_bytes)
                self.assertEqual(app.historical_event_refresh_button.cget("text"),
                                 "🔍 " + app._t("app.settings.history.search"))
                self.assertEqual(legacy_path.read_bytes(), legacy_bytes)
                self.assertEqual(app.app_events.path.read_bytes(), app_event_bytes)
                self.assertEqual((app.historical_event_window.winfo_width(),
                                  app.historical_event_window.winfo_height()),
                                 en_history_size)
                self.assertEqual((app.app_diagnostics_window.winfo_width(),
                                  app.app_diagnostics_window.winfo_height()),
                                 en_diagnostics_size)
                self.assertEqual(control_bounds({
                    "mode": app.historical_range_choice,
                    "start": app.historical_start_entry,
                    "end": app.historical_end_entry,
                    "previous": app.historical_previous_button,
                    "page": app.historical_page_label,
                    "next": app.historical_next_button,
                    "list": app.historical_event_list,
                    "detail": app.historical_event_detail,
                    "cancel": app.historical_event_cancel_button,
                    "search": app.historical_event_refresh_button,
                }), en_history_bounds)
                self.assertEqual(control_bounds({
                    "list": app.app_diagnostics_list,
                    "detail": app.app_diagnostics_detail,
                    "retry": app.app_diagnostics_retry_button,
                    "close": app.app_diagnostics_close_button,
                }), en_diagnostics_bounds)
                capture_current_language("zh-TW")

                warning_index = len(app._historical_event_records)
                self.click_tk_listbox_row(root, app.historical_event_list, warning_index)
                self.wait_for_ui(root, lambda: app._historical_showing_diagnostics)
                self.wait_for_ui(root, lambda: app._historical_page_request_id is None and
                                 app._historical_event_detail_request_id is None)
                self.assertGreater(app.historical_event_list.size(), 1)
                self.click_tk_listbox_row(root, app.historical_event_list, 1)
                self.wait_for_ui(root, lambda: app._historical_event_detail_request_id is None)
                self.assertEqual(app.historical_event_list.curselection(), (1,))
                capture_window("zh-TW", "history-diagnostics",
                               app.historical_event_window, {
                                   "page": app.historical_page_label,
                                   "list": app.historical_event_list,
                                   "detail": app.historical_event_detail,
                                   "previous": app.historical_previous_button,
                                   "next": app.historical_next_button,
                               })
                warning_selection = tuple(app.historical_event_list.curselection())
                self.set_language_for_test_setup(app, root, ENGLISH)
                self.assertTrue(app._historical_showing_diagnostics)
                self.assertEqual(tuple(app.historical_event_list.curselection()),
                                 warning_selection)
                capture_window("en", "history-diagnostics",
                               app.historical_event_window, {
                                   "page": app.historical_page_label,
                                   "list": app.historical_event_list,
                                   "detail": app.historical_event_detail,
                                   "previous": app.historical_previous_button,
                                   "next": app.historical_next_button,
                               })
                if evidence_root is not None:
                    with (evidence_root / "window-bounds.json").open(
                            "w", encoding="utf-8") as evidence_file:
                        json.dump(evidence_bounds, evidence_file, ensure_ascii=False,
                                  indent=2)

                os.replace(moved_source, audit.audit_path)
                query_entered = threading.Event()
                release_query = threading.Event()
                original_query = query_historical_events

                def gated_query(sessions, app_path, date_range, **kwargs):
                    query_entered.set()
                    if not release_query.wait(10):
                        raise RuntimeError("controlled H7 query gate timed out")
                    return original_query(sessions, app_path, date_range, **kwargs)

                with patch("b518_log_solution.query_historical_events",
                           side_effect=gated_query):
                    app.historical_start_var.set("2099-01-01")
                    app.historical_end_var.set("2099-01-01")
                    self.click_tk_widget(root, app.historical_event_refresh_button)
                    self.assertTrue(query_entered.wait(2))
                    in_flight_generation = app._historical_query_generation
                    self.assertIsNotNone(in_flight_generation)
                    self.assertIs(app._historical_query_result, original_result)
                    self.assertEqual(app._historical_query_page_number, 2)
                    self.set_language_for_test_setup(app, root, ENGLISH)
                    self.assertEqual(app._historical_query_generation, in_flight_generation)
                    self.assertIs(app._historical_query_result, original_result)
                    self.assertIn("Searching saved history",
                                  app.historical_query_status.cget("text"))
                    self.assertEqual(str(app.historical_event_cancel_button.cget("state")),
                                     "normal")
                    release_query.set()
                    self.wait_for_ui(root, lambda: app._historical_query_result is not
                                     original_result and
                                     app._historical_query_generation is None)
                    self.assertEqual(app._historical_query_result.date_range.start.isoformat(),
                                     "2099-01-01")
                    self.assertEqual(app._historical_query_result.total_count, 0)
                    self.assertIn("0 matching events were read",
                                  app.historical_query_status.cget("text"))
                self.assertEqual(audit.audit_path.read_bytes(), source_bytes)
                self.assertEqual(legacy_path.read_bytes(), legacy_bytes)
                self.assertEqual(app.app_events.path.read_bytes(), app_event_bytes)
            finally:
                if "release_query" in locals():
                    release_query.set()
                if moved_source.exists():
                    os.replace(moved_source, audit.audit_path)
                app._close_historical_event_window()
                app._close_app_diagnostics_window()
                app.hotkey.close()
                root.destroy()
            self.assertEqual(audit.audit_path.read_bytes(), source_bytes)

    @staticmethod
    def click_tk_widget(root, widget):
        root.update_idletasks()
        x, y = max(2, widget.winfo_width() // 2), max(2, widget.winfo_height() // 2)
        widget.event_generate("<ButtonPress-1>", x=x, y=y)
        widget.event_generate("<ButtonRelease-1>", x=x, y=y)
        root.update()

    @staticmethod
    def click_tk_listbox_row(root, widget, index):
        widget.see(index)
        root.update()
        x, y, _width, height = widget.bbox(index)
        widget.event_generate("<ButtonPress-1>", x=max(2, x + 4),
                              y=y + max(1, height // 2))
        widget.event_generate("<ButtonRelease-1>", x=max(2, x + 4),
                              y=y + max(1, height // 2))
        root.update()


if __name__ == "__main__":
    unittest.main()
