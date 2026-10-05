"""Run a fully isolated one-slot Atlas round through the real Tk app."""

import csv
import json
import os
import sys
import tempfile
import time
import tkinter as tk
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT / "src"))
sys.path.insert(0, str(APP_ROOT / "tools"))

from audit_records import read_round_audit
from kvm_display_contract import MarkerState
from smoke_deadline_app import LocalHotkey, wait_for, write_atlas_record
from b518_log_solution import B518LogSolutionApp


def main():
    previous_home = os.environ.get("HOME")
    try:
        with tempfile.TemporaryDirectory(prefix="b518-ticket13-app-") as temporary:
            home = Path(temporary)
            os.environ["HOME"] = str(home)
            application_support = home / "Application Support"
            preferences = application_support / "preferences.json"
            active, archive = home / "source/active", home / "source/archive"
            active.mkdir(parents=True)
            archive.mkdir(parents=True)
            with patch("b518_log_solution.APP_ROOT", application_support), \
                    patch("b518_log_solution.PREFS_PATH", preferences):
                root = tk.Tk()
                app = B518LogSolutionApp(root, hotkey_factory=LocalHotkey,
                                         session_root=application_support / "sessions")
                root.deiconify()
                root.update()
                try:
                    current = app.profiles.get("B518", "FCT")
                    paths = dict(current.paths)
                    paths.update({"active": str(active), "final": str(archive)})
                    app.profiles = app.profiles.with_profile(replace(
                        current, capacity=1, mapping=((1, 1),), paths=paths,
                        timeouts={"start": 20, "test": 60, "round": 120},
                    ))
                    app.project.set("B518")
                    app.station.set("FCT")
                    app._load_selected_profile_values()
                    app.start_button.invoke()
                    wait_for(root, lambda: app.monitor is not None, "Atlas source preparation")
                    session_path = app.monitor.session.path

                    serial = "SMOKEATLAS0001"
                    active_record = active / "group0-slot1" / "system" / "records.csv"
                    write_atlas_record(active_record, serial)
                    wait_for(root, lambda: app.rounds.snapshot().results[0].status == "TESTING",
                             "Atlas activity")
                    stamp = (app.monitor.started + timedelta(seconds=1)).strftime(
                        "%Y%m%d_%H-%M-%S.000-ticket13")
                    write_atlas_record(archive / serial / stamp / "system" / "records.csv", serial)
                    import shutil
                    shutil.rmtree(active / "group0-slot1")
                    wait_for(root, lambda: app.rounds.snapshot().result_available,
                             "completed Atlas round")
                    wait_for(root, lambda: app._rendered_marker_state == MarkerState.COMPLETE,
                             "completed state marker")

                    snapshot = app.rounds.snapshot()
                    if not app.rounds.flush_audit():
                        raise RuntimeError("Tk 輪次稽核紀錄尚未保存完整")
                    audit_path = session_path / "audit.jsonl"
                    rebuilt = read_round_audit(audit_path)
                    if rebuilt["results"][1]["status"] != snapshot.results[0].status:
                        raise RuntimeError("磁碟重建狀態與 Tk 共用輪次快照不一致")
                    if not rebuilt["result_available"] or not rebuilt["audit_complete"]:
                        raise RuntimeError("Tk 輪次紀錄未完整重建或尚未放行")
                    marker_state = app._rendered_marker_state
                    if marker_state != MarkerState.COMPLETE:
                        raise RuntimeError("Tk 狀態標記與同一輪次快照不一致")
                    print(json.dumps({
                        "round_id": snapshot.round_id,
                        "round_state": snapshot.state.value,
                        "displayed_status": snapshot.results[0].status,
                        "rebuilt_status": rebuilt["results"][1]["status"],
                        "event_count": len(rebuilt["events"]),
                        "audit_complete": rebuilt["audit_complete"],
                        "marker_state": marker_state.value,
                        "result_available": rebuilt["result_available"],
                        "window_geometry": root.geometry(),
                        "session_contains_audit": audit_path.is_file(),
                    }, ensure_ascii=False, sort_keys=True))
                finally:
                    root.destroy()
    finally:
        if previous_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = previous_home


if __name__ == "__main__":
    main()
