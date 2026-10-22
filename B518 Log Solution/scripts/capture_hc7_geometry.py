"""Capture HC7's real macOS Tk layout matrix; restores the display mode on exit."""
import argparse
import hashlib
import itertools
import json
import platform
import subprocess
import sys
import time
import tkinter as tk
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
for directory in ("src", "tools", "tests"):
    sys.path.insert(0, str(ROOT / directory))

import Quartz
from AppKit import NSApplication, NSBitmapImageRep
from b518_log_solution import B518LogSolutionApp
from language_catalog import ENGLISH, TRADITIONAL_CHINESE
from machine_profiles import MachineProfileStore
from test_log_solution_ui import FakeHotkey, capture_tk_content_view_evidence


def wait(root, predicate, timeout=10):
    deadline = time.monotonic() + timeout
    while not predicate():
        root.update()
        if time.monotonic() > deadline:
            raise AssertionError("Tk condition timed out")
        time.sleep(.01)
    root.update_idletasks()


def bounds(widget, root):
    x = y = 0
    current = widget
    while current is not root:
        x += current.winfo_x()
        y += current.winfo_y()
        current = current.master
    return [x, y, widget.winfo_width(), widget.winfo_height()]


def timer_pixels(path, roi):
    bitmap = NSBitmapImageRep.imageRepWithContentsOfFile_(str(path))
    x, y, width, height = roi
    points = []
    for py in range(y, y + height):
        for px in range(x, x + width):
            colour = bitmap.colorAtX_y_(px, py)
            if max(colour.redComponent(), colour.greenComponent(),
                   colour.blueComponent()) < .45:
                points.append((px, py))
    assert points, "timer ROI contains no dark glyph pixels"
    bbox = [min(p[0] for p in points), min(p[1] for p in points),
            max(p[0] for p in points) + 1, max(p[1] for p in points) + 1]
    assert x < bbox[0] < bbox[2] < x + width, (roi, bbox)
    assert y < bbox[1] < bbox[3] < y + height, (roi, bbox)
    return {"dark_pixel_count": len(points), "glyph_bbox_pixels_xyxy": bbox,
            "glyph_inside_roi_with_margin": True}


def capture_case(output, resolution, scaling, capacity, language):
    with TemporaryDirectory() as temporary:
        temporary = Path(temporary)
        prefs = temporary / "preferences.json"
        store = MachineProfileStore(prefs)
        catalog, project, machine, error = store.load()
        assert error is None, error
        profile = replace(catalog.get(project, machine), capacity=capacity,
                          mapping=tuple((slot, slot) for slot in range(1, capacity + 1)))
        store.save(catalog.with_profile(profile), project, machine)
        root = tk.Tk()
        root.tk.call("tk", "scaling", scaling)
        app = None
        try:
            with patch("b518_log_solution.PREFS_PATH", prefs):
                app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey,
                    session_root=temporary / "sessions",
                    app_event_path=temporary / "app-events.json")
            app._select_language(language)
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            wait(root, lambda: root.winfo_ismapped())
            assert app._display_capacity() == capacity
            assert abs(float(root.tk.call("tk", "scaling")) - scaling) < .01
            assert [root.winfo_screenwidth(), root.winfo_screenheight()] == list(resolution)
            widgets = {
                "kvm_parent": app.kvm_results,
                "left_locator": app.kvm_locator_left,
                "right_locator": app.kvm_locator_right,
                "row_count_marker": app.kvm_layout_marker,
                "state_marker": app.kvm_state_marker,
                "heartbeat_marker": app.kvm_heartbeat_marker,
                "first_result": app.kvm_result_blocks[1],
                "last_configured_result": app.kvm_result_blocks[capacity],
                "table": app.rows_canvas,
                "start": app.start_button,
                "monitor_state": app.monitor_state,
                "timer": app.monitor_elapsed,
                "reminder": app.notification_reminder_frame,
                "stop": app.stop_button,
                "app_event_status": app.app_event_status_label,
            }
            prefix = "hc7-{}x{}-s{}-c{}-{}".format(
                *resolution, str(scaling).replace(".", "p"), capacity, language)
            baseline = {name: bounds(widget, root) for name, widget in widgets.items()}
            for name, (x, y, width, height) in baseline.items():
                assert x >= 0 and y >= 0, (name, baseline[name])
                assert x + width <= root.winfo_width(), (name, baseline[name])
                assert y + height <= root.winfo_height(), (name, baseline[name])
            assert baseline["monitor_state"][0] + baseline["monitor_state"][2] <= baseline["timer"][0]
            captures = []

            def capture(state, text):
                record = capture_tk_content_view_evidence(
                    root, prefix + "-" + state, widgets, output_dir=output)
                assert app.monitor_elapsed.cget("text") == text
                assert record["controls"] == baseline, (prefix, state, record["controls"], baseline)
                sx = record["image_pixels"]["width"] / record["size"][0]
                sy = record["image_pixels"]["height"] / record["size"][1]
                x, y, width, height = record["controls"]["timer"]
                roi = [round(x*sx), round(y*sy), round(width*sx), round(height*sy)]
                path = output / record["screenshot"]
                record.update({"state": state, "timer_text": text,
                    "content_origin": "live NSView contentView top-left; titlebar excluded",
                    "pixels_per_tk_unit": [sx, sy], "timer_roi_pixels": roi,
                    "timer_pixels": timer_pixels(path, roi),
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "pending_count": app._pending_notification_count(),
                    "reminder_foreground": str(app.notification_reminder.cget("foreground")),
                    "reminder_text": app.notification_reminder.cget("text"),
                    "monitor_state_text": app.monitor_state.cget("text"),
                    "heartbeat_state": app._heartbeat_state})
                captures.append(record)

            app._render_monitoring_elapsed(SimpleNamespace(monitoring_elapsed_seconds=0))
            capture("normal-clear", "00:00")
            app._set_main_monitor_state("monitor.awaiting_conflicts", count=12345)
            app._render_monitoring_elapsed(SimpleNamespace(monitoring_elapsed_seconds=600000))
            with patch.object(app, "_pending_notification_count", return_value=12):
                app._refresh_notification_badge()
                wait(root, lambda: str(app.notification_reminder.cget("foreground")) == "#dc2626")
                heartbeat_before = app._heartbeat_state
                capture("long-pending-bright", "10000:00")
                wait(root, lambda: str(app.notification_reminder.cget("foreground")) == "#7f1d1d")
                wait(root, lambda: app._heartbeat_state != heartbeat_before)
                capture("long-pending-dim", "10000:00")
                with patch.object(app, "_pending_notification_count", return_value=0):
                    app._refresh_notification_badge()
                    assert app._notification_reminder_after_id is None
                    capture("long-cleared", "10000:00")
            return {"display_resolution": list(resolution),
                "requested_tk_scaling": scaling,
                "actual_tk_scaling": float(root.tk.call("tk", "scaling")),
                "capacity": capacity, "language": language,
                "screen_metrics": app._main_screen_metrics,
                "controls_content_tk": baseline,
                "geometry_unchanged_across_reminder_and_timer_states": True,
                "heartbeat_advanced_while_reminder_active": True,
                "captures": captures}
        finally:
            if app is not None:
                app.hotkey.close()
                app.rounds.request_close()
                wait(root, lambda: app.rounds.close_status().status == "complete")
                wait(root, lambda: app.rounds.app_event_status().complete)
            root.destroy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    display = Quartz.CGMainDisplayID()
    original = Quartz.CGDisplayCopyDisplayMode(display)
    modes = Quartz.CGDisplayCopyAllDisplayModes(display, None)
    dimensions = lambda mode: (Quartz.CGDisplayModeGetWidth(mode), Quartz.CGDisplayModeGetHeight(mode))
    original_resolution = dimensions(original)
    records = []
    resolutions = [(1440,900)] if args.smoke else [(1440,900),(1152,720)]
    cases = [(1.0,1,ENGLISH)] if args.smoke else list(itertools.product(
        (1.0,1.5), (1,10,11,20), (ENGLISH,TRADITIONAL_CHINESE)))
    try:
        for resolution in resolutions:
            mode = (original if dimensions(original) == resolution else
                    next(mode for mode in modes if dimensions(mode) == resolution))
            assert Quartz.CGDisplaySetDisplayMode(display, mode, None) == 0
            time.sleep(.8)
            for scaling, capacity, language in cases:
                print("capture", resolution, scaling, capacity, language, flush=True)
                records.append(capture_case(output, resolution, scaling, capacity, language))
                (output / "matrix.partial.json").write_text(json.dumps(records, ensure_ascii=False, indent=2)+"\n")
    finally:
        assert Quartz.CGDisplaySetDisplayMode(display, original, None) == 0
        time.sleep(.5)
        assert dimensions(Quartz.CGDisplayCopyDisplayMode(display)) == original_resolution
    result = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "app_source_commit": subprocess.check_output(["git","rev-parse","HEAD"], cwd=ROOT, text=True).strip(),
        "app_src_tree": subprocess.check_output(["git","rev-parse","HEAD:B518 Log Solution/src"], cwd=ROOT, text=True).strip(),
        "capture_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "environment": {"macos": platform.mac_ver()[0], "architecture": platform.machine(),
            "python": platform.python_version(), "capture": "real mapped macOS Tk NSView content cache",
            "execution": "outside Codex filesystem/process sandbox; minimum Tk repro passes",
            "original_display_resolution_restored": list(original_resolution)},
        "matrix_case_count": len(records),
        "image_count": sum(len(record["captures"]) for record in records),
        "local_only": True, "remote_jetkvm_verified": False,
        "minimum_screen_height_note": "648 is the computed minimum, not an available physically tested display mode; tested native heights are 720 and 900.",
        "cases": records,
    }
    (output / "matrix.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
    (output / "matrix.partial.json").unlink()
    print("PASS", result["matrix_case_count"], "cases", result["image_count"], "images; display restored", flush=True)


if __name__ == "__main__":
    main()
