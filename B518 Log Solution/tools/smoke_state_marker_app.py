"""Run the real Tk app through all four Ticket 12 marker states and capture windows."""

import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import Quartz
from Foundation import NSURL


APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT / "src"))


class LocalHotkey:
    available = True
    message = "Ticket 12 isolated Tk marker replay"

    def __init__(self, _callback):
        pass

    def close(self):
        pass


def wait_for(root, condition, description, timeout=12):
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
    info = next((item for item in windows
                 if item.get("kCGWindowLayer") == 0
                 and title_fragment in item.get("kCGWindowName", "")), None)
    if info is None:
        raise RuntimeError("Could not find visible window {!r}.".format(title_fragment))
    image = Quartz.CGWindowListCreateImage(
        Quartz.CGRectNull, Quartz.kCGWindowListOptionIncludingWindow,
        info["kCGWindowNumber"], Quartz.kCGWindowImageBoundsIgnoreFraming)
    if image is None:
        raise RuntimeError("Could not capture window {!r}.".format(title_fragment))
    destination_url = NSURL.fileURLWithPath_(str(destination))
    writer = Quartz.CGImageDestinationCreateWithURL(destination_url, "public.png", 1, None)
    if writer is None:
        raise RuntimeError("Could not create PNG output at {}.".format(destination))
    Quartz.CGImageDestinationAddImage(writer, image, None)
    if not Quartz.CGImageDestinationFinalize(writer):
        raise RuntimeError("Could not finish PNG output at {}.".format(destination))
    return {
        "file": destination.name,
        "window_title": info.get("kCGWindowName", ""),
        "physical_pixels": [Quartz.CGImageGetWidth(image), Quartz.CGImageGetHeight(image)],
    }


def update_profile(app, active, final, round_limit=5):
    current = app.profiles.get("B518", "FCT")
    profile = replace(
        current, project="B518", machine="FCT", platform="atlas", capacity=20,
        mapping=tuple((slot, slot) for slot in range(1, 21)),
        paths=dict(current.paths, active=str(active), final=str(final)),
        timeouts={"start": 30, "test": 30, "round": round_limit},
    )
    app.profiles = app.profiles.with_profile(profile)
    app.project.set("B518")
    app.station.set("FCT")


def window_rect(window):
    window.update_idletasks()
    return [window.winfo_rootx(), window.winfo_rooty(),
            window.winfo_rootx() + window.winfo_width(),
            window.winfo_rooty() + window.winfo_height()]


def assert_dialog_clear_of_recognition_band(app, dialog):
    main = window_rect(app.root)
    popup = window_rect(dialog)
    protected = [main[0] + 82, main[1], main[0] + 342, main[1] + 88]
    overlap = (popup[0] < protected[2] and popup[2] > protected[0]
               and popup[1] < protected[3] and popup[3] > protected[1])
    if overlap:
        raise RuntimeError("A review dialog covers the fixed locator/marker/result band: {}"
                           .format(popup))
    return {"dialog_tk_rect": popup, "protected_top_band_tk_rect": protected,
            "overlaps_top_band": False}


def main():
    evidence_root = Path(os.environ.get(
        "B518_SMOKE_EVIDENCE_DIR",
        APP_ROOT / "docs" / "refactoring" / "evidence" / "ticket-12",
    ))
    evidence_root.mkdir(parents=True, exist_ok=True)
    run_root = Path(tempfile.mkdtemp(prefix="ticket12-isolated-"))
    previous_home = os.environ.get("HOME")
    output = []
    try:
        os.environ["HOME"] = str(run_root)
        import b518_log_solution as app_module
        from b518_log_solution import B518LogSolutionApp
        from log_monitoring import MonitorEvent
        from monitoring_round import RoundState
        from kvm_display_contract import state_for_round_snapshot

        app_root = run_root / "Application Support"
        active = run_root / "sources" / "active"
        final = run_root / "sources" / "archive"
        active.mkdir(parents=True)
        final.mkdir(parents=True)
        screenshots = evidence_root
        with patch("b518_log_solution.APP_ROOT", app_root), \
                patch("b518_log_solution.PREFS_PATH", app_root / "preferences.json"):
            root = tk.Tk()
            app = B518LogSolutionApp(root, hotkey_factory=LocalHotkey,
                                     session_root=app_root / "sessions")
            root.deiconify()
            root.update()
            try:
                update_profile(app, active, final)
                app._render_rows()
                root.update()
                scale = float(root.tk.call("tk", "scaling"))
                screen = [root.winfo_screenwidth(), root.winfo_screenheight()]
                window = [root.winfo_width(), root.winfo_height()]
                capture_meta = capture_window("B518 Log Solution", screenshots / "standby.png")
                output.append(dict(state="standby", round_id=None, result_available=False,
                                   tk_scaling=scale, screen_tk_units=screen,
                                   app_window_tk_units=window, **capture_meta))

                adapter = {}
                registry = app_module.DEFAULT_PLATFORM_REGISTRY
                create_monitor = registry.create_monitor

                def capture_registered_adapter(platform_name, **context):
                    adapter["value"] = create_monitor(platform_name, **context)
                    return adapter["value"]

                with patch.object(registry, "create_monitor", capture_registered_adapter):
                    app.start_button.invoke()
                    wait_for(root, lambda: app.rounds.snapshot().state == RoundState.RUNNING
                             and app.rounds.session_path is not None, "shared round preparation")
                snapshot = app.rounds.snapshot()
                capture_meta = capture_window("B518 Log Solution", screenshots / "monitoring.png")
                output.append(dict(state=state_for_round_snapshot(snapshot).value,
                                   round_id=snapshot.round_id,
                                   result_available=snapshot.result_available,
                                   tk_scaling=scale, screen_tk_units=screen,
                                   app_window_tk_units=window, **capture_meta))

                monitor = adapter["value"]
                evidence = {"round_evidence_id": "ticket12-controlled-round"}
                monitor.apply_round_result(1, "PASS", "SAMPLE-T12-001", "controlled-source",
                                           evidence, lock_terminal=True)
                monitor.publish_round_event(MonitorEvent(
                    "result_candidate", "controlled same-round candidate", 1,
                    "SAMPLE-T12-001", "FAIL", "controlled-candidate",
                    dict(evidence, source_id="anonymous-candidate", source_time="unknown"),
                ))
                wait_for(root, lambda: len(app.rounds.snapshot().pending_conflicts) == 1
                         and app.conflict_window is not None
                         and app.conflict_window.winfo_viewable(),
                         "captured conflict candidate")
                capture_meta = capture_window("B518 Log Solution", screenshots / "review.png")
                output.append(dict(state=state_for_round_snapshot(app.rounds.snapshot()).value,
                                   round_id=app.rounds.snapshot().round_id,
                                   result_available=app.rounds.snapshot().result_available,
                                   pending_conflicts=1, tk_scaling=scale,
                                   screen_tk_units=screen, app_window_tk_units=window,
                                   **capture_meta))
                conflict_capture = capture_window("同輪結果衝突確認",
                                                  screenshots / "conflict-window.png")
                conflict_capture["geometry_check"] = assert_dialog_clear_of_recognition_band(
                    app, app.conflict_window)

                wait_for(root, lambda: app.rounds.snapshot().round_alarm is not None,
                         "independent round deadline alarm", timeout=10)
                alarm = app.rounds.snapshot().round_alarm
                wait_for(root, lambda: app.round_alarm_ack_button is not None
                         and str(app.round_alarm_ack_button.cget("state")) == "normal",
                         "alarm acknowledgement action")
                alarm_capture = capture_window("整輪監控逾時", screenshots / "alarm-window.png")
                alarm_capture["geometry_check"] = assert_dialog_clear_of_recognition_band(
                    app, app.round_alarm_window)
                app.round_alarm_window.withdraw()
                root.update()
                app.round_alarm_button.invoke()
                root.update()
                if not app.round_alarm_window.winfo_viewable():
                    raise RuntimeError("The closed alarm window could not be reopened.")
                if app.rounds.snapshot().result_available:
                    raise RuntimeError("A pending conflict allowed premature result release.")
                app.round_alarm_ack_button.invoke()
                root.update()
                if app.rounds.snapshot().result_available:
                    raise RuntimeError("Acknowledging the alarm cleared an unrelated conflict.")
                conflict_capture = dict(conflict_capture, alarm_window=alarm_capture)
                app.conflict_list.selection_set(0)
                app._resolve_selected_conflict("keep_original")
                wait_for(root, lambda: app.rounds.snapshot().result_available,
                         "result release after independent acknowledgement and conflict choice")
                wait_for(root, lambda: app._rendered_marker_state.value == "complete",
                         "visible completion marker")
                capture_meta = capture_window("B518 Log Solution", screenshots / "complete.png")
                output.append(dict(state=state_for_round_snapshot(app.rounds.snapshot()).value,
                                   round_id=app.rounds.snapshot().round_id,
                                   result_available=app.rounds.snapshot().result_available,
                                   conflict_choice="keep_original", alarm_id=alarm.alarm_id,
                                   tk_scaling=scale, screen_tk_units=screen,
                                   app_window_tk_units=window, **capture_meta))
                output[-2]["dialogs"] = conflict_capture
                locator_y = app.kvm_state_marker.winfo_rooty()
                app.rows_canvas.yview_moveto(1.0)
                root.update_idletasks()
                root.update()
                if app.kvm_state_marker.winfo_rooty() != locator_y:
                    raise RuntimeError("The top marker moved when the twenty-row detail list scrolled.")
                capture_meta = capture_window("B518 Log Solution", screenshots / "details-scrolled.png")
                output.append(dict(state=state_for_round_snapshot(
                                       app.rounds.snapshot()).value,
                                   capacity=20, detail_scroll_position=app.rows_canvas.yview(),
                                   marker_screen_y=locator_y, tk_scaling=scale,
                                   screen_tk_units=screen, app_window_tk_units=window,
                                   **capture_meta))
                app.rows_canvas.yview_moveto(0.0)

                previous_round = app.rounds.snapshot().round_id
                app.start_button.invoke()
                wait_for(root, lambda: app.rounds.snapshot().round_id != previous_round
                         and app.rounds.snapshot().state == RoundState.RUNNING,
                         "new round snapshot after completed result")
                root.update()
                new_snapshot = app.rounds.snapshot()
                if state_for_round_snapshot(new_snapshot).value != "monitoring":
                    raise RuntimeError("New round did not replace the previous completion marker.")
                if any(item.status != "WAITING" for item in new_snapshot.results):
                    raise RuntimeError("The new round snapshot did not initialize its result band.")
                capture_meta = capture_window("B518 Log Solution", screenshots / "new-round.png")
                output.append(dict(state="monitoring", round_id=new_snapshot.round_id,
                                   previous_round_id=previous_round,
                                   result_available=new_snapshot.result_available,
                                   old_complete_with_new_waiting_band=False,
                                   tk_scaling=scale, screen_tk_units=screen,
                                   app_window_tk_units=window, **capture_meta))
                app.stop_button.invoke()
                wait_for(root, lambda: app.rounds.snapshot().state == RoundState.STOPPED,
                         "manual stop snapshot")
                stopped = app.rounds.snapshot()
                if state_for_round_snapshot(stopped).value != "standby":
                    raise RuntimeError("Manual stop incorrectly retained a completion marker.")
                capture_meta = capture_window("B518 Log Solution", screenshots / "manual-stop.png")
                output.append(dict(state="standby", round_id=stopped.round_id,
                                   completion_reason=stopped.completion_reason,
                                   result_available=stopped.result_available,
                                   tk_scaling=scale, screen_tk_units=screen,
                                   app_window_tk_units=window, **capture_meta))
            finally:
                app._close_settings()
                app.hotkey.close()
                root.destroy()
        details = {
            "ticket": "15" if "B518_SMOKE_EVIDENCE_DIR" in os.environ else "12",
            "smoke_origin_ticket": "12",
            "environment": {"macOS": subprocess.check_output(
                                ["/usr/bin/sw_vers", "-productVersion"], text=True).strip(),
                            "architecture": platform.machine(),
                            "python": platform.python_version()},
            "capture_source": "Quartz CGWindowListCreateImage of isolated Tk windows",
            "physical_kvm_available": False,
            "upper_computer_integration": "deferred to Ticket 16 by user decision",
            "screens": output,
        }
        (evidence_root / "run.json").write_text(
            json.dumps(details, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(details, ensure_ascii=False, indent=2))
        print("Isolated source, preference, and session tree (removed after capture):", run_root)
    finally:
        shutil.rmtree(run_root, ignore_errors=True)
        if previous_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = previous_home


if __name__ == "__main__":
    main()
