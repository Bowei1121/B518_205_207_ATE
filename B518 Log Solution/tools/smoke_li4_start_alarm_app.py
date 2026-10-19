"""Exercise the real Tk alarm window using the public round coordinator seam."""

from __future__ import annotations

import json
import os
import platform
from pathlib import Path
import sys
import tempfile
import time
import tkinter as tk
from dataclasses import replace
from unittest.mock import patch

APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT / "src"))


class LocalHotkey:
    available = True
    message = "LI4 isolated desktop acceptance"

    def __init__(self, _callback):
        pass

    def close(self):
        pass


class WaitingMonitor:
    def __init__(self, callback, slots, session_root):
        from log_monitoring import SessionStore, SlotResult

        self.callback = callback
        self.results = {slot: SlotResult(slot) for slot in slots}
        self.start_timeout_seconds = 5
        self.test_timeout_seconds = 60
        self.round_timeout_seconds = 600
        self.collection_stopped = False
        self.session = SessionStore("li4-start-alarm", {}, session_root)

    def round_results(self):
        return tuple(self.results.values())

    def timeout_seconds(self, kind):
        return {"start": 5, "test": 60, "round": 600}[kind]

    def update_round_settings(self, _settings):
        pass

    def start(self):
        pass

    def stop_collection(self):
        self.collection_stopped = True

    def finish(self):
        self.session.enqueue_finish()

    def stop(self):
        self.stop_collection()

    def poll_once(self):
        pass

    def publish_round_event(self, event):
        self.session.enqueue_event(event.message, event.detail)
        self.callback(event)

    def apply_round_result(self, slot, status, detail=None, lock_terminal=False):
        from log_monitoring import MonitorEvent

        self.results[slot].status = status
        self.callback(MonitorEvent("result", "slot{} {}".format(slot, status),
                                   slot=slot, status=status, detail=detail or {}))

    def set_result(self, slot, status, detail=None, lock_terminal=False):
        self.apply_round_result(slot, status, detail, lock_terminal)


def capture_window(title, path):
    import Quartz
    from Foundation import NSURL

    windows = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionAll,
                                                Quartz.kCGNullWindowID)
    matches = [item for item in windows if item.get("kCGWindowLayer") == 0 and
               item.get("kCGWindowIsOnscreen") == 1 and
               item.get("kCGWindowOwnerPID") == os.getpid() and
               item.get("kCGWindowName") == title]
    if not matches:
        raise RuntimeError("Visible Tk window owned by this App process not found: {!r}; owned={}".format(
            title, [(item.get("kCGWindowName"), item.get("kCGWindowNumber")) for item in windows
                    if item.get("kCGWindowOwnerPID") == os.getpid()]))
    image = Quartz.CGWindowListCreateImage(
        Quartz.CGRectNull, Quartz.kCGWindowListOptionIncludingWindow,
        matches[0]["kCGWindowNumber"], Quartz.kCGWindowImageBoundsIgnoreFraming)
    if image is None:
        raise RuntimeError("Quartz could not capture Tk window {!r}".format(title))
    writer = Quartz.CGImageDestinationCreateWithURL(
        NSURL.fileURLWithPath_(str(path)), "public.png", 1, None)
    Quartz.CGImageDestinationAddImage(writer, image, None)
    if not Quartz.CGImageDestinationFinalize(writer):
        raise RuntimeError("Screenshot failed: {}".format(path))
    return {"file": path.name, "window_title": title,
            "window_owner_pid": os.getpid(),
            "physical_pixels": [Quartz.CGImageGetWidth(image), Quartz.CGImageGetHeight(image)]}


def main():
    evidence = Path(os.environ.get(
        "B518_LI4_EVIDENCE_DIR", APP_ROOT / "docs" / "refactoring" / "evidence" /
        "li4-real-app"))
    evidence.mkdir(parents=True, exist_ok=True)
    elapsed = [0.0]
    output = []
    with tempfile.TemporaryDirectory(prefix="li4-start-alarm-") as temporary:
        root = tk.Tk()
        with patch("b518_log_solution.APP_ROOT", Path(temporary) / "support"), \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            from b518_log_solution import B518LogSolutionApp
            from monitoring_round import RoundCoordinator

            support = Path(temporary) / "support"
            sessions = support / "sessions"
            app = B518LogSolutionApp(root, hotkey_factory=LocalHotkey, session_root=sessions)
            app.rounds = RoundCoordinator(app.events.put, monotonic=lambda: elapsed[0],
                                          audit_root=sessions)
            selected = app.profiles.get("B518", "FCT")
            app.profiles = app.profiles.with_profile(replace(
                selected, capacity=2, mapping=((1, 1), (2, 2))))
            app.project.set("B518")
            app.station.set("FCT")
            app._render_rows()
            root.deiconify()
            root.lift()
            root.update()
            try:
                monitor_holder = {}

                def factory(callback):
                    monitor_holder["monitor"] = WaitingMonitor(callback, (1, 2), sessions)
                    return monitor_holder["monitor"]

                started = app.rounds.start(
                    "FCT", factory, run_async=False, start_timeout_seconds=5,
                    round_timeout_seconds=600, capacity=2,
                )
                app.active_round_id = started.round_id
                app._apply_round_snapshot(started)
                root.update()
                elapsed[0] = 5
                expired = app.rounds.poll_once()
                app._apply_round_snapshot(expired)
                app._refresh_round_alarm()
                root.update()
                if app.round_alarm_window is None or not app.round_alarm_window.winfo_viewable():
                    raise RuntimeError("The real B518 App did not show the start alarm window")
                alarm_text = app.round_alarm_message.cget("text")
                if ("No trusted activity or valid result" not in alarm_text or
                        "does not confirm an ATE failure" not in alarm_text):
                    raise RuntimeError("The Tk alarm did not explain the start deadline: {!r}".format(
                        alarm_text))
                if expired.state.value != "AWAITING_REVIEW" or expired.result_available:
                    raise RuntimeError("The App exposed results before alarm acknowledgement")
                main_title = root.wm_title()
                alarm_title = app.round_alarm_window.wm_title()
                output.append({"phase": "alarm_pending", "state": expired.state.value,
                               "results": [item.status for item in expired.results],
                               "window": capture_window(main_title, evidence / "main-review.png"),
                               "alarm": capture_window(alarm_title, evidence / "alarm-pending.png")})

                app.round_alarm_close_button.invoke()
                root.update()
                if app.round_alarm_window.state() != "withdrawn":
                    raise RuntimeError("Close did not hide the alarm dialog")
                if app.rounds.snapshot().round_alarm.acknowledged_at:
                    raise RuntimeError("Closing the alarm dialog incorrectly acknowledged it")

                app._open_round_alarm()
                root.update()
                app.round_alarm_ack_button.invoke()
                root.update()
                completed = app.rounds.snapshot()
                if not completed.result_available or completed.state.value != "COMPLETED":
                    raise RuntimeError("Acknowledging the alarm did not release the complete results")
                if completed.pending_conflicts:
                    raise RuntimeError("Alarm acknowledgement should not create or resolve conflicts")
                output.append({"phase": "alarm_acknowledged", "state": completed.state.value,
                               "result_available": completed.result_available,
                               "acknowledged_at": completed.round_alarm.acknowledged_at,
                               "window": capture_window(main_title, evidence / "main-complete.png")})
                app.rounds.flush_audit(timeout=5)
                app.rounds.flush_session(timeout=5)
            finally:
                app.close()
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    try:
                        root.update()
                        exists = bool(root.winfo_exists())
                    except tk.TclError:
                        exists = False
                    if not exists:
                        break
                    time.sleep(0.01)
                try:
                    exists = bool(root.winfo_exists())
                except tk.TclError:
                    exists = False
                if exists:
                    root.destroy()

    run = {"command": "PYTHONPATH=src python3 tools/smoke_li4_start_alarm_app.py",
           "python": sys.version, "platform": sys.platform,
           "macos_version": platform.mac_ver()[0],
           "tk_patchlevel": tk.Tcl().eval("info patchlevel"),
           "clock": "controlled monotonic clock; 5-second deadline, no wall-clock wait",
           "app_pid": os.getpid(), "evidence": output}
    (evidence / "run.json").write_text(json.dumps(run, ensure_ascii=False, indent=2) + "\n",
                                       encoding="utf-8")
    print(json.dumps(run, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
