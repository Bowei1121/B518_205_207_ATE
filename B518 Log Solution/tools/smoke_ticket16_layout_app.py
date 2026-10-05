"""Capture real one/two-row Tk rounds; expected results come from public snapshots."""

import argparse
import json
import shutil
import sys
import tempfile
import time
import tkinter as tk
from pathlib import Path
from unittest.mock import patch

APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT / "src"))

from audit_records import read_round_audit
from b518_log_solution import B518LogSolutionApp
from kvm_display_contract import CONTRACT_VERSION
from smoke_sample_adapter_app import LocalHotkey, capture_window, find_button, wait_for


def capture_round(capacity, output, isolated):
    support = isolated / "support"
    source = isolated / "source"
    source.mkdir(parents=True)
    with patch("b518_log_solution.APP_ROOT", support), \
            patch("b518_log_solution.PREFS_PATH", support / "preferences.json"):
        root = tk.Tk()
        app = B518LogSolutionApp(root, hotkey_factory=LocalHotkey,
                                 session_root=support / "sessions")
        try:
            app.open_settings()
            app.profile_editor_project.set("SAMPLE")
            app.profile_editor_machine.set("FCT")
            app.profile_editor_platform.set("sample-json")
            app.profile_editor_capacity.set(str(capacity))
            app.profile_editor_paths["active"].set(str(source))
            mapping = [(position, capacity + 1 - position)
                       for position in range(1, capacity + 1)]
            app.profile_editor_mapping.set(", ".join("{}:{}".format(*item) for item in mapping))
            for field in ("start", "test", "round"):
                app.profile_editor_timeouts[field].set("60")
            button = find_button(app.settings_window, "套用並保存")
            if button is None:
                raise RuntimeError("Engineer apply action is unavailable")
            button.invoke()
            app._close_settings()
            app.project_choice.set("SAMPLE")
            app.project_choice.event_generate("<<ComboboxSelected>>")
            app.machine_choice.set("FCT")
            app.machine_choice.event_generate("<<ComboboxSelected>>")
            root.update()
            app.start_button.invoke()
            wait_for(root, lambda: app.rounds.snapshot() is not None
                     and app.rounds.session_path is not None, "source preparation")
            wait_for(root, lambda: app._rendered_marker_state.value == "monitoring",
                     "visible monitoring frame")
            frames = [capture_window("B518 Log Solution", output / "monitoring.png")]
            statuses = (["PASS", "FAIL", "NOTEST"] * 7)[:capacity]
            records = [dict(kind="final", position=position, status=statuses[display - 1],
                            sn="SAMPLE-T16-{:03d}".format(display), batch_id="layout-{}".format(capacity))
                       for position, display in reversed(mapping)]
            (source / "events.jsonl").write_text(
                "".join(json.dumps(item) + "\n" for item in records), encoding="utf-8")
            wait_for(root, lambda: app.rounds.snapshot().result_available, "normal completion")
            wait_for(root, lambda: app._rendered_marker_state.value == "complete",
                     "visible released frame")
            root.update_idletasks()
            time.sleep(0.15)  # Let Quartz compose the flushed Tk drawing before capture.
            snapshot = app.rounds.snapshot()
            if [item.status for item in snapshot.results] != statuses:
                raise RuntimeError("Shared results differ from the controlled mapped source")
            frames.append(capture_window("B518 Log Solution", output / "complete.png"))
            app.rows_canvas.yview_moveto(1.0)
            root.update()
            frames.append(capture_window("B518 Log Solution", output / "complete-scrolled.png"))
            if not app.rounds.flush_session(timeout=3) or not app.rounds.flush_audit(timeout=3):
                raise RuntimeError("Controlled audit did not flush")
            audit_path = app.rounds.session_path / "audit.jsonl"
            rebuilt = read_round_audit(audit_path)
            if [value["status"] for _, value in sorted(rebuilt["results"].items())] != statuses:
                raise RuntimeError("Disk audit reconstruction differs from the displayed round")
            shutil.copyfile(audit_path, output / "audit.jsonl")
            return dict(capacity=capacity, mapping=mapping, statuses=statuses,
                        round_id=snapshot.round_id, result_available=snapshot.result_available,
                        audit_complete=rebuilt["audit_complete"], frames=frames,
                        tk_scaling=float(root.tk.call("tk", "scaling")),
                        window_tk_units=[root.winfo_width(), root.winfo_height()],
                        screen_tk_units=[root.winfo_screenwidth(), root.winfo_screenheight()])
        finally:
            app.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ticket16-layout-") as temporary:
        records = []
        for capacity in (1, 4, 6, 10, 11, 12, 20):
            folder = output / "capacity-{}".format(capacity)
            folder.mkdir(parents=True, exist_ok=True)
            records.append(capture_round(capacity, folder, Path(temporary) / str(capacity)))
    report = dict(contract_version=CONTRACT_VERSION, source="real Tk/Quartz capture",
                  is_jetkvm_frame=False, rounds=records)
    (output / "layouts.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("PASS: real Tk mapped rounds and disk audits for capacities 1/4/6/10/11/12/20")


if __name__ == "__main__":
    main()
