"""Exercise LI5 local cancellation through real B518 Tk controls."""

from __future__ import annotations

import json
import os
import platform
from pathlib import Path
import sys
import tempfile
import threading
import time
import tkinter as tk
from dataclasses import replace
from unittest.mock import patch

APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT / "src"))


class LocalHotkey:
    available = True
    message = "LI5 isolated Tk verification"

    def __init__(self, _callback):
        pass

    def close(self):
        pass


class BlockedMonitor:
    def __init__(self, callback, entered, release):
        from log_monitoring import SlotResult

        self.callback = callback
        self.entered = entered
        self.release = release
        self.results = {slot: SlotResult(slot) for slot in (1, 2)}
        self.stopped = False

    def prepare(self):
        self.entered.set()
        if not self.release.wait(10):
            raise RuntimeError("source gate timed out")

    def round_results(self):
        return tuple(self.results.values())

    def timeout_seconds(self, kind):
        return {"start": 5, "test": 30, "round": 60}[kind]

    def update_round_settings(self, _settings):
        pass

    def publish_round_event(self, event):
        self.callback(event)

    def start(self):
        pass

    def poll_once(self):
        pass

    def stop_collection(self):
        self.stopped = True

    def set_result(self, slot, status, detail=None, lock_terminal=False):
        self.apply_round_result(slot, status, detail=detail, lock_terminal=lock_terminal)

    def apply_round_result(self, slot, status, sn="", source="", detail=None, lock_terminal=False):
        from log_monitoring import MonitorEvent

        self.results[slot].status = status
        self.results[slot].sn = sn
        self.results[slot].source = source
        self.callback(MonitorEvent("result", "slot{} {}".format(slot, status), slot,
                                   sn, status, source, detail or {}))

    def stop(self):
        self.stopped = True

    def finish(self):
        self.stopped = True


def wait_for(root, condition, label, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        root.update()
        if condition():
            return
        time.sleep(0.02)
    raise RuntimeError("Timed out waiting for {}".format(label))


def capture(root, path, expected_prefix="B518"):
    import Quartz
    from Foundation import NSURL

    root.update()
    title = root.wm_title()
    windows = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionAll,
                                                Quartz.kCGNullWindowID)
    candidates = [item for item in windows if item.get("kCGWindowLayer") == 0 and
                  item.get("kCGWindowIsOnscreen") == 1 and
                  item.get("kCGWindowOwnerPID") == os.getpid() and
                  item.get("kCGWindowName") == title]
    if not candidates or (expected_prefix and expected_prefix not in title):
        raise RuntimeError("Visible B518 Tk window owned by this process not found: {!r}; owned={}".format(
            title, [(item.get("kCGWindowName"), item.get("kCGWindowNumber")) for item in windows
                    if item.get("kCGWindowOwnerPID") == os.getpid()]))
    window = max(candidates, key=lambda item: item.get("kCGWindowBounds", {}).get("Width", 0) *
                 item.get("kCGWindowBounds", {}).get("Height", 0))
    image = Quartz.CGWindowListCreateImage(
        Quartz.CGRectNull, Quartz.kCGWindowListOptionIncludingWindow,
        window["kCGWindowNumber"], Quartz.kCGWindowImageBoundsIgnoreFraming)
    if image is None:
        raise RuntimeError("Quartz could not capture B518 Tk window")
    writer = Quartz.CGImageDestinationCreateWithURL(NSURL.fileURLWithPath_(str(path)), "public.png", 1, None)
    Quartz.CGImageDestinationAddImage(writer, image, None)
    if not Quartz.CGImageDestinationFinalize(writer):
        raise RuntimeError("Could not write screenshot {}".format(path))
    return {"file": path.name, "window_title": title,
            "window_owner_pid": window["kCGWindowOwnerPID"],
            "window_bounds": dict(window.get("kCGWindowBounds", {})),
            "physical_pixels": [Quartz.CGImageGetWidth(image), Quartz.CGImageGetHeight(image)]}


def configure_app(app, active, archive):
    profile = app.profiles.get("B518", "FCT")
    profile = replace(
        profile, project="B518", machine="FCT", platform="atlas", capacity=2,
        mapping=((1, 1), (2, 2)),
        paths=dict(profile.paths, active=str(active), final=str(archive)),
        timeouts={"start": 5, "test": 30, "round": 60})
    app.profiles = app.profiles.with_profile(profile)
    app.project.set("B518")
    app.station.set("FCT")
    app._render_rows()


def main():
    evidence = Path(os.environ.get(
        "B518_LI5_EVIDENCE_DIR", APP_ROOT / "docs" / "refactoring" / "evidence" /
        "li5-real-app"))
    evidence.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="li5-real-app-"))
    active, archive, support = (temporary / "active", temporary / "archive",
                                temporary / "Application Support")
    active.mkdir()
    archive.mkdir()
    gate_entered, gate_release = threading.Event(), threading.Event()
    screens = []
    root = tk.Tk()
    with patch("b518_log_solution.APP_ROOT", support), \
            patch("b518_log_solution.PREFS_PATH", support / "preferences.json"):
        import b518_log_solution as app_module
        from b518_log_solution import B518LogSolutionApp
        from monitoring_round import RoundCoordinator, RoundState

        app = B518LogSolutionApp(root, hotkey_factory=LocalHotkey,
                                 session_root=support / "sessions")
        configure_app(app, active, archive)
        root.deiconify()
        root.lift()
        root.update()
        registry = app_module.DEFAULT_PLATFORM_REGISTRY
        original_factory = registry.create_monitor
        create_calls = []

        def first_blocked_factory(name, **kwargs):
            create_calls.append(name)
            if len(create_calls) == 1:
                gate_entered.set()
                if not gate_release.wait(10):
                    raise RuntimeError("source gate timed out")
            return original_factory(name, **kwargs)

        try:
            # Accepted start, real Stop control, preserved result review, explicit
            # cancellation confirmation, and a separately requested new round.
            with patch.object(registry, "create_monitor", first_blocked_factory):
                app.start_button.invoke()
                wait_for(root, gate_entered.is_set, "source factory gate")
                stopped_id = app.rounds.snapshot().round_id
                app.stop_button.invoke()
                wait_for(root, lambda: app.rounds.snapshot().completion_reason == "manual_stop",
                         "manual stop result publication")
                stopped_snapshot = app.rounds.snapshot()
                if not stopped_snapshot.cancellation_available:
                    raise RuntimeError("Manual stop snapshot does not offer cancellation: {}".format(
                        stopped_snapshot))
                app._apply_round_snapshot(stopped_snapshot)
                if str(app.start_button.cget("state")) != "disabled":
                    raise RuntimeError("Start stayed enabled before local cancellation after manual stop")
                if str(app.cancel_unverified_round_button.cget("state")) != "normal":
                    raise RuntimeError("Cancel control stayed disabled after snapshot render: {}".format(
                        {"active_round_id": app.active_round_id,
                         "snapshot_id": stopped_snapshot.round_id,
                         "available": stopped_snapshot.cancellation_available,
                         "state": app.cancel_unverified_round_button.cget("state")}))
                try:
                    wait_for(root, lambda: str(app.cancel_unverified_round_button.cget("state")) == "normal",
                             "local cancellation control after manual stop")
                except RuntimeError as error:
                    current = app.rounds.snapshot()
                    raise RuntimeError("{}; snapshot={!r}, button={!r}".format(
                        error, current, app.cancel_unverified_round_button.cget("state")))
                stopped = app.rounds.snapshot()
                if stopped.completion_reason != "manual_stop" or not stopped.result_available:
                    raise RuntimeError("Manual stop did not show its local review result")
                screens.append({"phase": "manual_stop_review", "round_id": stopped_id,
                                "results": [item.status for item in stopped.results],
                                "result_available": stopped.result_available,
                                "start_button_state": str(app.start_button.cget("state")),
                                **capture(root, evidence / "manual-stop-review.png")})
                with patch.object(app_module.messagebox, "askyesno", return_value=True) as confirm:
                    app.cancel_unverified_round_button.invoke()
                    if not confirm.called:
                        raise RuntimeError("Cancel control skipped explicit confirmation")
                cancelled = app.rounds.snapshot()
                if cancelled.completion_reason != "unverified_round_cancelled" or cancelled.result_available:
                    raise RuntimeError("Manual-stop cancellation remained available for delivery")
                if len(cancelled.results) != 2 or not cancelled.results:
                    raise RuntimeError("Cancellation erased the original results")
                screens.append({"phase": "manual_stop_cancelled", "round_id": stopped_id,
                                "results": [item.status for item in cancelled.results],
                                "result_available": cancelled.result_available,
                                **capture(root, evidence / "manual-stop-cancelled.png")})
                app.start_button.invoke()
                wait_for(root, lambda: app.rounds.snapshot().round_id != stopped_id,
                         "explicit new round after manual-stop cancellation")
                new_manual_id = app.rounds.snapshot().round_id
                wait_for(root, lambda: app.rounds.snapshot().state == RoundState.RUNNING,
                         "new round source ready")
                screens.append({"phase": "new_round_after_manual_stop", "round_id": new_manual_id,
                                "old_round_id": stopped_id,
                                **capture(root, evidence / "new-round-after-manual-stop.png")})
                gate_release.set()
                wait_for(root, lambda: app.rounds.round_snapshot(stopped_id) is None or
                         not app.rounds.round_snapshot(stopped_id).source_preparation_pending,
                         "old source preparation handoff")
                old_stopped = app.rounds.round_snapshot(stopped_id)
                if (old_stopped is not None and
                        old_stopped.completion_reason != "unverified_round_cancelled"):
                    raise RuntimeError("Late old source changed the cancelled round")
                app.stop_button.invoke()
                wait_for(root, lambda: app.rounds.snapshot().completion_reason == "manual_stop",
                         "second round normal manual stop")

            # Start-deadline while source factory is still blocked: acknowledge
            # only the alarm, then explicitly cancel, then start another round.
            elapsed = [0.0]
            app.rounds = RoundCoordinator(app.events.put, monotonic=lambda: elapsed[0],
                                          audit_root=support / "sessions")
            app.rounds.register_app_event_store(app.app_events, support)
            gate_entered.clear()
            gate_release.clear()
            create_calls.clear()
            create_calls.append("local-gated-round")
            with patch.object(registry, "create_monitor", first_blocked_factory):
                app.active_profile_snapshot = app._selected_profile()
                def blocked_monitor_factory(callback):
                    monitor = BlockedMonitor(callback, gate_entered, gate_release)
                    # Match the ordinary asynchronous source setup boundary.
                    monitor.prepare()
                    return monitor

                timeout_start = app.rounds.start(
                    "FCT", blocked_monitor_factory,
                    run_async=True, start_timeout_seconds=5,
                    round_timeout_seconds=60, capacity=2,
                    audit_context={"profile": "B518/FCT LI5 controlled deadline"},
                )
                app.active_round_id = timeout_start.round_id
                app._set_monitor_controls(True)
                app._apply_round_snapshot(timeout_start)
                wait_for(root, gate_entered.is_set, "deadline scenario source gate")
                timed_out_id = app.rounds.snapshot().round_id
                elapsed[0] = 5
                expired = app.rounds.poll_once()
                app._apply_round_snapshot(expired)
                app._open_round_alarm()
                root.update()
                if app.round_alarm_window is None or not app.round_alarm_window.winfo_viewable():
                    raise RuntimeError("The real App did not open the deadline review: snapshot={!r}, window={!r}".format(
                        app.rounds.snapshot(), app.round_alarm_window))
                screens.append({"phase": "preparation_timeout_review", "round_id": timed_out_id,
                                "results": [item.status for item in expired.results],
                                "alarm_acknowledged": bool(expired.round_alarm.acknowledged_at),
                                "alarm_window": capture(app.round_alarm_window,
                                                         evidence / "preparation-timeout-alarm.png",
                                                         expected_prefix=None),
                                **capture(root, evidence / "preparation-timeout-review.png")})
                gate_release.set()
                wait_for(root, lambda: app.rounds.snapshot().round_alarm_ready,
                         "source preparation settled after timeout")
                app._open_round_alarm()
                root.update()
                app.round_alarm_ack_button.invoke()
                root.update()
                acknowledged = app.rounds.snapshot()
                if not acknowledged.result_available or acknowledged.state != RoundState.COMPLETED:
                    raise RuntimeError("Acknowledged deadline did not release the settled local result")
                if str(app.start_button.cget("state")) != "disabled":
                    raise RuntimeError("Start stayed enabled after timeout acknowledgement but before local cancellation")
                wait_for(root, lambda: str(app.cancel_unverified_round_button.cget("state")) == "normal",
                         "local cancellation after alarm acknowledgement")
                screens.append({"phase": "preparation_timeout_acknowledged", "round_id": timed_out_id,
                                "alarm_acknowledged": bool(acknowledged.round_alarm.acknowledged_at),
                                "result_available": acknowledged.result_available,
                                "cancellation_available": acknowledged.cancellation_available,
                                "cancellation_button_state": str(app.cancel_unverified_round_button.cget("state")),
                                "start_button_state": str(app.start_button.cget("state")),
                                **capture(root, evidence / "preparation-timeout-acknowledged.png")})
                with patch.object(app_module.messagebox, "askyesno", return_value=True) as confirm:
                    app.cancel_unverified_round_button.invoke()
                    if not confirm.called:
                        raise RuntimeError("Timeout cancel skipped explicit confirmation")
                timed_out_cancelled = app.rounds.snapshot()
                if timed_out_cancelled.result_available or timed_out_cancelled.completion_reason != "unverified_round_cancelled":
                    raise RuntimeError("Timeout cancellation did not withdraw delivery")
                screens.append({"phase": "preparation_timeout_cancelled", "round_id": timed_out_id,
                                "results": [item.status for item in timed_out_cancelled.results],
                                "result_available": timed_out_cancelled.result_available,
                                **capture(root, evidence / "preparation-timeout-cancelled.png")})
                elapsed[0] = 0.0
                app.start_button.invoke()
                wait_for(root, lambda: app.rounds.snapshot().round_id != timed_out_id,
                         "explicit new round after timeout cancellation")
                new_timeout_id = app.rounds.snapshot().round_id
                wait_for(root, lambda: app.rounds.snapshot().state == RoundState.RUNNING,
                         "new round prepared after timeout")
                screens.append({"phase": "new_round_after_timeout", "round_id": new_timeout_id,
                                "old_round_id": timed_out_id,
                                **capture(root, evidence / "new-round-after-timeout.png")})
        finally:
            gate_release.set()
            app.close()
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                try:
                    root.update()
                    if not root.winfo_exists():
                        break
                except tk.TclError:
                    break
                time.sleep(0.01)
            try:
                if root.winfo_exists():
                    root.destroy()
            except tk.TclError:
                pass

    result = {"command": "PYTHONPATH=src /opt/anaconda3/bin/python3 tools/smoke_li5_manual_cancel_app.py",
              "python": sys.version, "platform": sys.platform,
              "macos_version": platform.mac_ver()[0],
              "tk_patchlevel": tk.Tcl().eval("info patchlevel"),
              "app_pid": os.getpid(), "screens": screens,
              "assertions": ["manual stop -> explicit local cancel -> explicit new round",
                             "blocked preparation deadline -> alarm acknowledgement -> explicit cancel -> new round",
                             "old source handoff cannot affect the new round"],
              "external_integrations": "none; synthetic local source only"}
    (evidence / "run.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                                       encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
