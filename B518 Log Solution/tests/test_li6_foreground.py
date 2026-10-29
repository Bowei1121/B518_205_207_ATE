"""Real desktop acceptance for round-triggered foreground requests."""
import os
import json
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from AppKit import NSApplication, NSWorkspace

import tkinter as tk
from tkinter import ttk

try:
    import Quartz
except ImportError:
    Quartz = None

from b518_log_solution import B518LogSolutionApp
from monitoring_round import RoundResult, RoundSnapshot, RoundState
from test_log_solution_ui import FakeHotkey, capture_tk_window_evidence


@unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1" and Quartz is not None,
                     "requires a macOS desktop and Quartz")
class LI6ForegroundAcceptanceTests(unittest.TestCase):
    def _front_window_names(self, pid):
        windows = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID)
        return [window.get(Quartz.kCGWindowName, "") for window in windows
                if window.get(Quartz.kCGWindowOwnerPID) == pid]

    def _wait(self, root, predicate, timeout=2):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            root.update()
            if predicate():
                return
            time.sleep(.01)
        self.fail("desktop condition did not become true")

    def _settle_other_window_front(self, root, pid, main_window_title, timeout=3, stable_for=.25):
        """Wait (bounded, never failing) until app activation and window order stop changing."""
        other = "LI6 Other Local Window"

        def sample():
            application = NSApplication.sharedApplication()
            key = application.keyWindow()
            front = NSWorkspace.sharedWorkspace().frontmostApplication()
            return (bool(application.isActive()),
                    front.processIdentifier() if front else None,
                    str(key.title()) if key else None,
                    self._front_window_names(pid))

        def ready(state):
            names = state[3]
            return (state[0] and state[1] == os.getpid() and state[2] == other and
                    other in names and main_window_title in names and
                    names.index(other) < names.index(main_window_title))

        started = time.monotonic()
        first = last = None
        changes = 0
        stable_since = None
        stable = False
        while time.monotonic() - started < timeout:
            root.update()
            state = sample()
            if first is None:
                first = state
            if state != last:
                if last is not None:
                    changes += 1
                last = state
                stable_since = time.monotonic()
            if ready(state) and time.monotonic() - stable_since >= stable_for:
                stable = True
                break
            time.sleep(.01)
        return {"elapsed": round(time.monotonic() - started, 3), "stable": stable,
                "first": first, "last": last, "order_changes": changes}

    def test_round_events_raise_log_without_focus_and_without_topmost(self):
        with TemporaryDirectory() as temporary, \
                patch.dict(os.environ, {"B518_FOREGROUND_TRACE": "1"}), \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.title("B518 LI6 Foreground Test")
            root.deiconify()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey,
                session_root=Path(temporary) / "sessions")
            main_window_title = root.title()
            desk = tk.Toplevel(root)
            desk.title("LI6 Other Local Window")
            entry = ttk.Entry(desk)
            entry.pack()
            ttk.Label(desk, text="Other local application: keep typing here").pack()
            app.active_round_id = "li6-round"
            observations = []

            def put_other_window_in_front():
                NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
                desk.deiconify()
                desk.lift()
                entry.focus_force()
                self._wait(root, lambda: root.focus_get() is entry)
                setup = self._settle_other_window_front(root, os.getpid(), main_window_title)
                print("LI6_SETUP " + json.dumps(setup, default=str), file=sys.stderr, flush=True)
                observations.append({"setup_settle": setup})
                names = self._front_window_names(os.getpid())
                log_is_visible = main_window_title in names
                observations.append({
                    "log_above_other_before": (
                        log_is_visible and names.index(main_window_title) <
                        names.index("LI6 Other Local Window")),
                    "focused_widget": str(root.focus_get()),
                })
                return capture_tk_window_evidence(
                    desk, "li6-other-window", "en", {"entry": entry})

            def assert_log_raises(label):
                def log_is_above_other():
                    names = self._front_window_names(os.getpid())
                    return (main_window_title in names and "LI6 Other Local Window" in names and
                            names.index(main_window_title) <
                            names.index("LI6 Other Local Window"))

                try:
                    self._wait(root, log_is_above_other)
                except AssertionError:
                    native = [
                        {"title": window.title(), "visible": window.isVisible(),
                         "miniaturized": window.isMiniaturized(),
                         "key": window.isKeyWindow()}
                        for window in NSApplication.sharedApplication().windows()]
                    front = NSWorkspace.sharedWorkspace().frontmostApplication()
                    self.fail("{} did not raise: stack={}, Tk state={}, native={}, "
                              "isActive={}, frontmost pid={} (own pid={}), "
                              "foreground trace={}".format(
                                  label, self._front_window_names(os.getpid()), root.state(),
                                  native, NSApplication.sharedApplication().isActive(),
                                  front.processIdentifier() if front else None, os.getpid(),
                                  getattr(app, "_foreground_trace", [])[-30:]))
                try:
                    self._wait(root, lambda: root.focus_get() is entry, timeout=0.5)
                except AssertionError:
                    key = NSApplication.sharedApplication().keyWindow()
                    self.fail("{} focus changed to {}; key window={}".format(
                        label, root.focus_get(), key.title() if key else None))
                observations.append({
                    "event": label,
                    "log_above_other_after": True,
                    "focused_widget": str(root.focus_get()),
                    "topmost": bool(root.attributes("-topmost")),
                })
                self.assertFalse(bool(root.attributes("-topmost")))
                return capture_tk_window_evidence(
                    root, "li6-log-window-" + label, "en", {"start": app.start_button})

            try:
                self._wait(root, lambda: root.winfo_viewable() and desk.winfo_viewable())
                capture_tk_window_evidence(
                    root, "li6-log-window-before", "en", {"start": app.start_button})
                desk_record = put_other_window_in_front()
                self.assertFalse(observations[-1]["log_above_other_before"])

                preparing = RoundSnapshot(
                    "li6-round", "FCT", RoundState.PREPARING, (), False, 0, (),
                    source_preparation_pending=True)
                monitoring = RoundSnapshot(
                    "li6-round", "FCT", RoundState.RUNNING, (), False, 1, (),
                    source_ready=True)
                testing = RoundSnapshot(
                    "li6-round", "FCT", RoundState.RUNNING,
                    (RoundResult(1, "SN-LI6", "TESTING", "controlled", "now"),),
                    False, 2, (), source_ready=True)
                app._apply_round_snapshot(preparing)
                app._apply_round_snapshot(monitoring)
                app._apply_round_snapshot(testing)
                log_record = assert_log_raises("testing-batch")

                # A polling pass with an unchanged round must not steal the window order.
                desk.lift()
                unchanged = RoundSnapshot(
                    "li6-round", "FCT", RoundState.RUNNING, testing.results,
                    False, 2, (), source_ready=True)
                app._apply_round_snapshot(unchanged)
                root.update()
                self.assertLess(self._front_window_names(os.getpid()).index(
                    "LI6 Other Local Window"),
                    self._front_window_names(os.getpid()).index(main_window_title))
                self.assertIs(root.focus_get(), entry)
                self.assertFalse(bool(root.attributes("-topmost")))

                desk_record = put_other_window_in_front()
                passed = RoundSnapshot(
                    "li6-round", "FCT", RoundState.RUNNING,
                    (RoundResult(1, "SN-LI6", "PASS", "controlled", "now"),),
                    True, 3, (), source_ready=True)
                app._apply_round_snapshot(passed)
                result_record = assert_log_raises("result-updated")

                desk_record = put_other_window_in_front()
                completed = RoundSnapshot(
                    "li6-round", "FCT", RoundState.COMPLETED, passed.results,
                    True, 4, (), collection_stopped=True,
                    completion_reason="complete", source_ready=True)
                app._apply_round_snapshot(completed)
                complete_record = assert_log_raises("normal-complete")

                # A terminal TIMEOUT result is still a result transition and raises the Log.
                app.active_round_id = "li6-timeout-round"
                app._apply_round_snapshot(RoundSnapshot(
                    "li6-timeout-round", "FCT", RoundState.PREPARING, (), False, 0, (),
                    source_preparation_pending=True))
                desk_record = put_other_window_in_front()
                timeout = RoundSnapshot(
                    "li6-timeout-round", "FCT", RoundState.STOPPED,
                    (RoundResult(1, "SN-LI6", "TIMEOUT", "controlled", "now"),),
                    False, 3, (), collection_stopped=True,
                    completion_reason="round_timeout", source_ready=True)
                app._apply_round_snapshot(timeout)
                timeout_record = assert_log_raises("timeout-complete")

                # Manual stop uses a distinct completion reason but has the same foreground rule.
                app.active_round_id = "li6-manual-round"
                app._apply_round_snapshot(RoundSnapshot(
                    "li6-manual-round", "FCT", RoundState.PREPARING, (), False, 0, (),
                    source_preparation_pending=True))
                desk_record = put_other_window_in_front()
                manual = RoundSnapshot(
                    "li6-manual-round", "FCT", RoundState.STOPPED,
                    (RoundResult(1, "SN-LI6", "STOPPED", "operator", "now"),),
                    True, 1, (), collection_stopped=True,
                    completion_reason="manual_stop", source_ready=True)
                app._apply_round_snapshot(manual)
                manual_record = assert_log_raises("manual-stop-complete")

                # Raising a minimized Log window restores it without forcing entry focus.
                root.iconify()
                self._wait(root, lambda: root.state() == "iconic")
                app.active_round_id = "li6-restored-round"
                app._apply_round_snapshot(RoundSnapshot(
                    "li6-restored-round", "FCT", RoundState.PREPARING, (), False, 0, (),
                    source_preparation_pending=True))
                desk_record = put_other_window_in_front()
                frontmost_before = NSWorkspace.sharedWorkspace().frontmostApplication().processIdentifier()
                app._apply_round_snapshot(RoundSnapshot(
                    "li6-restored-round", "FCT", RoundState.RUNNING, (), False, 1, (),
                    source_ready=True))
                self._wait(root, lambda: root.state() == "normal")
                restore_record = assert_log_raises("minimize-restore")
                self.assertEqual(
                    NSWorkspace.sharedWorkspace().frontmostApplication().processIdentifier(),
                    frontmost_before, "minimize-restore changed the frontmost application")

                # An old round event must not reorder the window for the new round.
                from log_monitoring import MonitorEvent
                from monitoring_round import RoundEvent
                desk.lift()
                entry.focus_force()
                self._wait(root, lambda: root.focus_get() is entry)
                app.events.put(RoundEvent(
                    "li6-manual-round", 2,
                    MonitorEvent("result", "old result", 1, "SN-OLD", "PASS", "old")))
                app._drain_events()
                self._wait(root, lambda: root.winfo_viewable())
                self.assertLess(self._front_window_names(os.getpid()).index(
                    "LI6 Other Local Window"),
                    self._front_window_names(os.getpid()).index(main_window_title))

                # A failed native raise is diagnostic, but result rendering continues.
                app.active_round_id = "li6-fault-round"
                app._apply_round_snapshot(RoundSnapshot(
                    "li6-fault-round", "FCT", RoundState.PREPARING, (), False, 0, (),
                    source_preparation_pending=True))
                desk_record = put_other_window_in_front()
                with patch.object(app, "_native_main_window", side_effect=RuntimeError(
                        "injected native raise failure")):
                    app._apply_round_snapshot(RoundSnapshot(
                        "li6-fault-round", "FCT", RoundState.RUNNING,
                        (RoundResult(1, "SN-FAULT", "FAIL", "controlled", "now"),),
                        True, 1, (), source_ready=True))
                    root.update()
                fault_events = [record for record in app.app_events.records
                                if record["localized_message"]["message_id"] ==
                                "app.dashboard.foreground_failed"]
                self.assertTrue(fault_events)
                self.assertIn("injected native raise failure",
                              fault_events[-1]["diagnostic"])
                self.assertEqual(app.status_rows[1]["status"].cget("text"), "FAIL")

                evidence_value = os.environ.get("B518_TK_EVIDENCE_DIR")
                if evidence_value:
                    output = Path(evidence_value)
                    output.mkdir(parents=True, exist_ok=True)
                    (output / "run.json").write_text(json.dumps({
                        "python": sys.version,
                        "tk": str(root.tk.call("info", "patchlevel")),
                        "observations": observations,
                        "screenshots": [desk_record, log_record, timeout_record,
                                        manual_record, restore_record, result_record,
                                        complete_record],
                        "foreground_failure_diagnostic": fault_events[-1]["diagnostic"],
                    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            finally:
                try:
                    evidence_dir = os.environ.get("B518_TK_EVIDENCE_DIR")
                    if evidence_dir:
                        trace_dir = Path(evidence_dir)
                        trace_dir.mkdir(parents=True, exist_ok=True)
                        (trace_dir / "li6-foreground-trace.json").write_text(
                            json.dumps(getattr(app, "_foreground_trace", []),
                                       ensure_ascii=False, indent=2, default=str) + "\n",
                            encoding="utf-8")
                except Exception:
                    pass
                app.rounds.request_close()
                self._wait(root, lambda: app.rounds.close_status().status == "complete")
                app.hotkey.close()
                root.destroy()


if __name__ == "__main__":
    unittest.main()
