"""Exercise LI2 stop/review/release paths in the real Tk application."""

import json
import os
import platform
import subprocess
import sys
import tempfile
import threading
import time
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT / "src"))


class LocalHotkey:
    available = True
    message = "LI2 isolated Tk verification"

    def __init__(self, _callback):
        pass

    def close(self):
        pass


def wait_for(root, condition, label, timeout=12):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        root.update()
        if condition():
            return
        time.sleep(0.02)
    raise RuntimeError("Timed out waiting for {}".format(label))


def capture(root, path):
    import Quartz
    from Foundation import NSURL

    root.update()
    windows = Quartz.CGWindowListCopyWindowInfo(Quartz.kCGWindowListOptionAll,
                                                Quartz.kCGNullWindowID)
    candidates = [item for item in windows if item.get("kCGWindowLayer") == 0 and
                  item.get("kCGWindowOwnerPID") == os.getpid() and
                  item.get("kCGWindowName") == root.wm_title()]
    info = max(candidates, key=lambda item: (
        item.get("kCGWindowBounds", {}).get("Width", 0) *
        item.get("kCGWindowBounds", {}).get("Height", 0)), default=None)
    if info is None or "B518" not in root.wm_title():
        raise RuntimeError("Could not identify the real B518 Tk window for this process")
    image = Quartz.CGWindowListCreateImage(
        Quartz.CGRectNull, Quartz.kCGWindowListOptionIncludingWindow,
        info["kCGWindowNumber"], Quartz.kCGWindowImageBoundsIgnoreFraming)
    if image is None:
        raise RuntimeError("Quartz could not capture the B518 Tk window")
    writer = Quartz.CGImageDestinationCreateWithURL(
        NSURL.fileURLWithPath_(str(path)), "public.png", 1, None)
    Quartz.CGImageDestinationAddImage(writer, image, None)
    if not Quartz.CGImageDestinationFinalize(writer):
        raise RuntimeError("Could not write screenshot {}".format(path))
    return {"file": path.name, "window_title": info["kCGWindowName"],
            "window_owner_pid": info["kCGWindowOwnerPID"],
            "window_bounds": dict(info.get("kCGWindowBounds", {})),
            "physical_pixels": [Quartz.CGImageGetWidth(image), Quartz.CGImageGetHeight(image)]}


def marker_matches(app, snapshot):
    from kvm_display_contract import MARKER_PATTERNS, state_for_round_snapshot

    expected = tuple(value for row in MARKER_PATTERNS[state_for_round_snapshot(snapshot)]
                     for value in row)
    cells = sorted(app.kvm_state_marker.find_withtag("marker-cell"),
                   key=lambda item: (app.kvm_state_marker.coords(item)[1],
                                     app.kvm_state_marker.coords(item)[0]))
    actual = tuple(app.kvm_state_marker.itemcget(item, "fill") == "#000000"
                   for item in cells)
    return len(actual) == 4 and actual == expected


def main():
    evidence = Path(os.environ.get(
        "B518_LI2_EVIDENCE_DIR",
        APP_ROOT / "docs" / "refactoring" / "evidence" / "li2-real-app"))
    evidence.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix="li2-real-app-"))
    active, archive, support = (temporary / "active", temporary / "archive",
                                temporary / "Application Support")
    active.mkdir()
    archive.mkdir()
    entered, release = threading.Event(), threading.Event()
    result = {"screens": []}
    root = tk.Tk()
    with patch("b518_log_solution.APP_ROOT", support), \
            patch("b518_log_solution.PREFS_PATH", support / "preferences.json"):
        import b518_log_solution as app_module
        from b518_log_solution import B518LogSolutionApp
        from kvm_display_contract import state_for_round_snapshot
        from log_monitoring import MonitorEvent
        from monitoring_round import RoundState

        app = B518LogSolutionApp(root, hotkey_factory=LocalHotkey,
                                 session_root=support / "sessions")
        app_root = root.winfo_toplevel()
        app_root.deiconify()
        app_root.lift()
        root.update()
        try:
            profile = app.profiles.get("B518", "FCT")
            profile = replace(
                profile, project="B518", machine="FCT", platform="atlas", capacity=2,
                mapping=((1, 1), (2, 2)),
                paths=dict(profile.paths, active=str(active), final=str(archive)),
                timeouts={"start": 30, "test": 30, "round": 60})
            app.profiles = app.profiles.with_profile(profile)
            app.project.set("B518")
            app.station.set("FCT")
            app._render_rows()
            registry = app_module.DEFAULT_PLATFORM_REGISTRY
            create_monitor = registry.create_monitor
            created_monitors = []

            def capture_monitor(name, **kwargs):
                monitor = create_monitor(name, **kwargs)
                created_monitors.append(monitor)
                return monitor

            # Stop during a blocked source factory. The full configured result
            # must be visible before the factory is released.
            def blocked_factory(name, **kwargs):
                entered.set()
                if not release.wait(8):
                    raise RuntimeError("source gate timed out")
                return create_monitor(name, **kwargs)

            with patch.object(registry, "create_monitor", blocked_factory):
                app.start_button.invoke()
                wait_for(root, entered.is_set, "source preparation gate")
                wait_for(root, lambda: app.rounds.snapshot().state == RoundState.PREPARING,
                         "PREPARING state")
                prep_id = app.rounds.snapshot().round_id
                app.stop_button.invoke()
                wait_for(root, lambda: app.rounds.snapshot().result_available,
                         "immediate preparation-stop result")
                prep_stop = app.rounds.snapshot()
                if [item.status for item in prep_stop.results] != ["STOPPED", "STOPPED"]:
                    raise RuntimeError("Preparation stop did not settle the full capacity")
                if state_for_round_snapshot(prep_stop).value != "manual_stop_complete":
                    raise RuntimeError("Preparation stop did not render manual-stop marker")
                wait_for(root, lambda: marker_matches(app, app.rounds.snapshot())
                         and [app.status_rows[index]["status"].cget("text")
                              for index in (1, 2)] == ["STOPPED", "STOPPED"],
                         "preparation-stop HMI rows and marker")
                result["screens"].append({
                    "scenario": "preparing-stop", "round_id": prep_id,
                    "results": [item.status for item in prep_stop.results],
                    "state": state_for_round_snapshot(prep_stop).value,
                    **capture(root, evidence / "preparing-stop.png")})
            release.set()
            wait_for(root, lambda: not app.rounds.snapshot().source_preparation_pending,
                     "late source completion")
            if app.rounds.snapshot().completion_reason != "manual_stop":
                raise RuntimeError("Late source completion replaced the manual-stop reason")

            # Normal monitoring, mixed terminal/progress state, and operator stop.
            wait_for(root, lambda: str(app.start_button.cget("state")) == "normal",
                     "Start enabled after manual stop")
            with patch.object(registry, "create_monitor", capture_monitor):
                app.start_button.invoke()
            wait_for(root, lambda: app.rounds.snapshot().state == RoundState.RUNNING,
                     "normal monitoring")
            adapter = created_monitors[-1]
            detail = {"round_evidence_id": "LI2-mixed-round"}
            adapter.apply_round_result(1, "PASS", "LI2-PASS-1", "controlled", detail,
                                       lock_terminal=True)
            adapter.apply_round_result(2, "TESTING", "LI2-TEST-2", "controlled", detail)
            wait_for(root, lambda: app.rounds.snapshot().results[1].status == "TESTING",
                     "mixed terminal and activity states")
            mixed_id = app.rounds.snapshot().round_id
            app.stop_button.invoke()
            wait_for(root, lambda: app.rounds.snapshot().result_available,
                     "mixed-result manual release")
            mixed = app.rounds.snapshot()
            if [item.status for item in mixed.results] != ["PASS", "STOPPED"]:
                raise RuntimeError("Manual stop did not preserve PASS and settle only the active slot")
            wait_for(root, lambda: marker_matches(app, app.rounds.snapshot())
                     and [app.status_rows[index]["status"].cget("text")
                          for index in (1, 2)] == ["PASS", "STOPPED"],
                     "mixed-stop HMI rows and marker")
            result["screens"].append({
                "scenario": "mixed-terminal-stop", "round_id": mixed_id,
                "results": [item.status for item in mixed.results],
                "state": state_for_round_snapshot(mixed).value,
                **capture(root, evidence / "mixed-terminal-stop.png")})

            # Every slot has a terminal result but a trusted conflict remains.
            wait_for(root, lambda: str(app.start_button.cget("state")) == "normal",
                     "Start enabled after first delivered stop")
            with patch.object(registry, "create_monitor", capture_monitor):
                app.start_button.invoke()
            wait_for(root, lambda: app.rounds.snapshot().state == RoundState.RUNNING,
                     "new monitoring round")
            adapter = created_monitors[-1]
            trusted = {"round_evidence_id": "LI2-conflict-round"}
            adapter.apply_round_result(1, "PASS", "LI2-SN-1", "controlled", trusted,
                                       lock_terminal=True)
            adapter.apply_round_result(2, "FAIL", "LI2-SN-2", "controlled", trusted,
                                       lock_terminal=True)
            adapter.publish_round_event(MonitorEvent(
                "result_candidate", "controlled same-round candidate", 1, "LI2-SN-1", "FAIL",
                "controlled-candidate", dict(trusted, source_id="candidate",
                                             source_time="2026-10-19T08:01:00")))
            wait_for(root, lambda: len(app.rounds.snapshot().pending_conflicts) == 1,
                     "trusted same-round conflict")
            review_id = app.rounds.snapshot().round_id
            app.stop_button.invoke()
            wait_for(root, lambda: app.rounds.snapshot().collection_stopped,
                     "stop while all slots are terminal")
            pending = app.rounds.snapshot()
            if pending.result_available or pending.state != RoundState.AWAITING_REVIEW:
                raise RuntimeError("Manual stop bypassed an unresolved conflict")
            if state_for_round_snapshot(pending).value != "review":
                raise RuntimeError("Unresolved conflict did not keep REVIEW marker")
            wait_for(root, lambda: marker_matches(app, app.rounds.snapshot())
                     and [app.status_rows[index]["status"].cget("text")
                          for index in (1, 2)] == ["PASS", "FAIL"],
                     "all-terminal REVIEW HMI rows and marker")
            result["screens"].append({
                "scenario": "all-terminal-review", "round_id": review_id,
                "results": [item.status for item in pending.results],
                "state": state_for_round_snapshot(pending).value,
                **capture(root, evidence / "all-terminal-review.png")})
            app._open_conflict_review()
            wait_for(root, lambda: app.conflict_list is not None,
                     "conflict review controls")
            app.conflict_list.selection_set(0)
            app._resolve_selected_conflict("keep_original")
            wait_for(root, lambda: app.rounds.snapshot().result_available,
                     "manual result release after conflict resolution")
            released = app.rounds.snapshot()
            if state_for_round_snapshot(released).value != "manual_stop_complete":
                raise RuntimeError("Resolved manual stop did not render its completion marker")
            wait_for(root, lambda: marker_matches(app, app.rounds.snapshot())
                     and [app.status_rows[index]["status"].cget("text")
                          for index in (1, 2)] == ["PASS", "FAIL"],
                     "released manual-stop HMI rows and marker")
            result["screens"].append({
                "scenario": "manual-stop-released", "round_id": review_id,
                "results": [item.status for item in released.results],
                "state": state_for_round_snapshot(released).value,
                **capture(root, evidence / "manual-stop-released.png")})

            if not app.rounds.flush_audit(timeout=3):
                raise RuntimeError("The test rounds' audit records did not flush")
            from audit_records import read_round_audit
            rebuilt = []
            for audit_path in sorted((support / "sessions").rglob("audit.jsonl")):
                record = read_round_audit(audit_path)
                if record["manual_stop"]:
                    rebuilt.append({"round_id": record["round"]["round_id"],
                                    "state": record["state"],
                                    "manual_stop": record["manual_stop"],
                                    "result_available": record["result_available"],
                                    "results": [item["status"] for item in record["results"].values()]})
            result["disk_rebuild"] = rebuilt
            if len(rebuilt) < 3 or not all(item["manual_stop"] for item in rebuilt):
                raise RuntimeError("Fresh audit reader did not reconstruct all manual-stop rounds")
        finally:
            release.set()
            app.close()
    result["ticket"] = "LI2"
    result["environment"] = {
        "macOS": subprocess.check_output(["/usr/bin/sw_vers", "-productVersion"], text=True).strip(),
        "architecture": platform.machine(), "python": platform.python_version(),
        "tk": str(tk.TkVersion), "capture": "Quartz window filtered by app process PID and exact title"}
    result["physical_kvm_available"] = False
    (evidence / "run.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                                       encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
