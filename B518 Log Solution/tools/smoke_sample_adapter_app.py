"""Exercise a controlled sample adapter through the real Tk app and audit store."""

import json
import os
import sys
import tempfile
import time
import tkinter as tk
from pathlib import Path
from unittest.mock import patch

import Quartz
from Foundation import NSURL

APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT / "src"))

from audit_records import read_round_audit
from b518_log_solution import B518LogSolutionApp
from monitoring_round import RoundState


class LocalHotkey:
    available = True
    message = "Ticket 14 controlled replay"

    def __init__(self, _callback):
        pass

    def close(self):
        pass


def wait_for(root, condition, description, timeout=18):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        root.update()
        if condition():
            return
        time.sleep(0.03)
    raise RuntimeError("Timed out while waiting for {}.".format(description))


def capture_window(title_fragment, destination):
    windows = Quartz.CGWindowListCopyWindowInfo(
        Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID)
    info = next((item for item in windows if item.get("kCGWindowLayer") == 0
                 and title_fragment in item.get("kCGWindowName", "")), None)
    if info is None:
        raise RuntimeError("Could not find visible window {!r}.".format(title_fragment))
    image = Quartz.CGWindowListCreateImage(
        Quartz.CGRectNull, Quartz.kCGWindowListOptionIncludingWindow,
        info["kCGWindowNumber"], Quartz.kCGWindowImageBoundsIgnoreFraming)
    if image is None:
        raise RuntimeError("Could not capture window {!r}.".format(title_fragment))
    writer = Quartz.CGImageDestinationCreateWithURL(
        NSURL.fileURLWithPath_(str(destination)), "public.png", 1, None)
    Quartz.CGImageDestinationAddImage(writer, image, None)
    if not Quartz.CGImageDestinationFinalize(writer):
        raise RuntimeError("Could not save screenshot {}.".format(destination))
    return {"file": destination.name,
            "physical_pixels": [Quartz.CGImageGetWidth(image), Quartz.CGImageGetHeight(image)],
            "window_title": info.get("kCGWindowName", "")}


def find_button(widget, label):
    if isinstance(widget, tk.Button) and widget.cget("text") == label:
        return widget
    try:
        if widget.winfo_class() == "TButton" and widget.cget("text") == label:
            return widget
    except tk.TclError:
        pass
    for child in widget.winfo_children():
        match = find_button(child, label)
        if match is not None:
            return match
    return None


def main():
    previous_home = os.environ.get("HOME")
    try:
        with tempfile.TemporaryDirectory(prefix="b518-ticket14-app-") as temporary:
            home = Path(temporary)
            os.environ["HOME"] = str(home)
            support = home / "Application Support"
            source = home / "sources" / "round-1"
            source.mkdir(parents=True)
            evidence = APP_ROOT / "docs" / "refactoring" / "evidence" / "ticket-14"
            evidence.mkdir(parents=True, exist_ok=True)
            with patch("b518_log_solution.APP_ROOT", support), \
                    patch("b518_log_solution.PREFS_PATH", support / "preferences.json"):
                root = tk.Tk()
                app = B518LogSolutionApp(
                    root, hotkey_factory=LocalHotkey, session_root=support / "sessions")
                closed = False
                root.deiconify()
                root.update()
                try:
                    app.open_settings()
                    app.profile_editor_project.set("SAMPLE")
                    app.profile_editor_machine.set("FCT")
                    app.profile_editor_platform.set("sample-json")
                    app.profile_editor_capacity.set("3")
                    app.profile_editor_paths["active"].set(str(source))
                    app.profile_editor_mapping.set("20:1, 4:2, 7:3")
                    for name, value in (("start", "30"), ("test", "60"), ("round", "8")):
                        app.profile_editor_timeouts[name].set(value)
                    apply_profile = find_button(app.settings_window, "套用並保存")
                    if apply_profile is None:
                        raise RuntimeError("Engineer profile apply action was not rendered.")
                    apply_profile.invoke()
                    profile = app.profiles.get("SAMPLE", "FCT")
                    app._close_settings()

                    # Exercise the same visible operator project/machine choice.
                    app.project_choice.set("B518")
                    app._project_changed()
                    app.project_choice.set("SAMPLE")
                    app._project_changed()
                    app.machine_choice.set("FCT")
                    app._profile_changed()
                    if app._selected_profile().platform != "sample-json":
                        raise RuntimeError("Project and machine selection did not restore the sample profile.")
                    app._render_rows()
                    root.update()
                    scale = float(root.tk.call("tk", "scaling"))
                    screen = [root.winfo_screenwidth(), root.winfo_screenheight()]
                    window = [root.winfo_width(), root.winfo_height()]
                    screenshots = {}
                    app.start_button.invoke()
                    wait_for(root, lambda: app.rounds.snapshot() is not None
                             and app.rounds.snapshot().state == RoundState.RUNNING
                             and app.rounds.monitor is not None, "registered sample Adapter preparation")
                    screenshots["monitoring"] = capture_window(
                        "B518 Log Solution", evidence / "monitoring.png")
                    session_path = app.rounds.monitor.session.path
                    records = (
                        '{"kind":"activity","position":20,"sn":"SAMPLE000020",'
                        '"source_time":"2026-10-05T09:00:00","batch_id":"fixture-run-7"}\n'
                        '{"kind":"activity","position":7,"sn":"SAMPLE000007",'
                        '"source_time":"2026-10-05T09:00:01","batch_id":"fixture-run-7"}\n'
                        '{"kind":"final","position":4,"sn":"SAMPLE000004","status":"FAIL",'
                        '"source_time":"2026-10-05T09:00:02","batch_id":"fixture-run-7"}\n'
                        '{"kind":"final","position":20,"sn":"SAMPLE000020","status":"PASS",'
                        '"source_time":"2026-10-05T09:00:03","batch_id":"fixture-run-7"}\n'
                        '{"kind":"final","position":20,"sn":"SAMPLE000020","status":"FAIL",'
                        '"source_time":"2026-10-05T09:00:04","batch_id":"fixture-run-7"}\n'
                    )
                    (source / "events.jsonl").write_text(records, encoding="utf-8")
                    wait_for(root, lambda: len(app.rounds.snapshot().pending_conflicts) == 1
                             and app.conflict_window is not None
                             and app.conflict_window.winfo_viewable(), "shared conflict review")
                    snapshot = app.rounds.snapshot()
                    if [(item.slot, item.status) for item in snapshot.results] != [
                            (1, "PASS"), (2, "FAIL"), (3, "TESTING")]:
                        raise RuntimeError("Mapped sample results did not match the shared snapshot.")
                    screenshots["conflict"] = capture_window(
                        "同輪結果衝突確認", evidence / "conflict.png")

                    wait_for(root, lambda: app.rounds.snapshot().round_alarm is not None
                             and app.round_alarm_window is not None
                             and app.round_alarm_window.winfo_viewable(), "shared round deadline alarm", 15)
                    snapshot = app.rounds.snapshot()
                    if snapshot.results[2].status != "TIMEOUT" or snapshot.result_available:
                        raise RuntimeError("Round deadline failed to preserve the conflict blocker.")
                    screenshots["alarm"] = capture_window(
                        "整輪監控逾時", evidence / "alarm.png")
                    if app.round_alarm_ack_button is None:
                        raise RuntimeError("Round alarm acknowledgement button is unavailable.")
                    app.round_alarm_ack_button.invoke()
                    root.update()
                    if app.rounds.snapshot().result_available:
                        raise RuntimeError("Alarm acknowledgement cleared the separate conflict.")
                    if app.conflict_list is None:
                        raise RuntimeError("The existing conflict selector is unavailable.")
                    app.conflict_list.selection_set(0)
                    choose_candidate = find_button(app.conflict_window, "採用新結果")
                    if choose_candidate is None:
                        raise RuntimeError("Existing candidate choice button was not rendered.")
                    choose_candidate.invoke()
                    wait_for(root, lambda: app.rounds.snapshot().result_available,
                             "result release after both shared confirmations")
                    wait_for(root, lambda: app._rendered_marker_state.value == "complete",
                             "snapshot-backed complete marker")
                    snapshot = app.rounds.snapshot()
                    if [(item.slot, item.status) for item in snapshot.results] != [
                            (1, "FAIL"), (2, "FAIL"), (3, "TIMEOUT")]:
                        raise RuntimeError("The selected candidate or timeout was not displayed.")
                    screenshots["complete"] = capture_window(
                        "B518 Log Solution", evidence / "complete.png")
                    if not app.rounds.flush_audit():
                        raise RuntimeError("Sample round audit journal did not flush.")
                    rebuilt = read_round_audit(session_path / "audit.jsonl")
                    if not rebuilt["result_available"] or rebuilt["state"] != "COMPLETED":
                        raise RuntimeError("Disk reconstruction did not show the released round.")
                    if [(slot, result["status"]) for slot, result in sorted(rebuilt["results"].items())] != [
                            (1, "FAIL"), (2, "FAIL"), (3, "TIMEOUT")]:
                        raise RuntimeError("Disk reconstruction disagreed with the Tk snapshot.")

                    result = {
                        "project_machine": "SAMPLE / FCT",
                        "platform": "sample-json",
                        "engineer_profile_saved": True,
                        "operator_selected_project_machine": [app.project.get(), app.station.get()],
                        "profile_capacity": profile.capacity,
                        "mapping": [[20, 1], [4, 2], [7, 3]],
                        "round_state": snapshot.state.value,
                        "result_available": snapshot.result_available,
                        "displayed_results": [[item.slot, item.status] for item in snapshot.results],
                        "reconstructed_results": [[slot, value["status"]]
                                                   for slot, value in sorted(rebuilt["results"].items())],
                        "pending_conflicts_after_release": len(snapshot.pending_conflicts),
                        "alarm_acknowledged": bool(snapshot.round_alarm.acknowledged_at),
                        "audit_complete": rebuilt["audit_complete"],
                        "tk_scaling": scale,
                        "screen_tk_units": screen,
                        "app_window_tk_units": window,
                        "window_geometry": root.geometry(),
                        "screenshots": screenshots,
                    }
                    (evidence / "app-round.json").write_text(
                        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                    app.close()
                    closed = True
                    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
                finally:
                    if not closed:
                        app.close()
    finally:
        if previous_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = previous_home


if __name__ == "__main__":
    main()
