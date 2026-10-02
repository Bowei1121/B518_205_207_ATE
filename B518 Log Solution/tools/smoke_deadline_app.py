"""Exercise Ticket 09 flows in the real Tk app with isolated controlled sources."""

import csv
import io
import json
import os
import shutil
import sys
import tempfile
import time
import tkinter as tk
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch


APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT / "src"))


class LocalHotkey:
    available = True
    message = "local deadline App smoke"

    def __init__(self, _callback):
        pass

    def close(self):
        pass


def wait_for(root, condition, description, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        root.update()
        if condition():
            return
        time.sleep(0.05)
    raise RuntimeError("Timed out while waiting for {}.".format(description))


def update_profile(app, project, machine, platform, paths, capacity, start, test, round_limit):
    current = app.profiles.get(project, machine)
    profile_paths = dict(current.paths)
    profile_paths.update(paths)
    profile = replace(
        current, project=project, machine=machine, platform=platform,
        capacity=capacity,
        mapping=tuple((slot, slot) for slot in range(1, capacity + 1)),
        paths=profile_paths,
        timeouts={"start": start, "test": test, "round": round_limit},
    )
    app.profiles = app.profiles.with_profile(profile)
    app.project.set(project)
    app.station.set(machine)
    app._load_selected_profile_values()
    for field, value in ("start", start), ("test", test), ("round", round_limit):
        app.timeouts[machine][field].set(str(value))


def write_atlas_record(path, serial, status="Pass"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("MLB_SN,status\n{},{}\n".format(serial, status), encoding="utf-8")


def write_rswmt_final(path, serial, slot, stopped_at):
    headers = ["Serial Number", "Test Pass/Fail Status", "List of Failing Tests",
               "Error Description", "Test Start Time", "Test Stop Time", "PRODUCT",
               "tc=Slot:tech=None:band=None;subtc=None:rate=None:freq=None:pwr=None;"]
    start_time = (stopped_at - timedelta(seconds=5)).strftime("%Y/%d/%m %H:%M:%S")
    stop_time = stopped_at.strftime("%Y/%d/%m %H:%M:%S")
    content = io.StringIO()
    writer = csv.writer(content)
    writer.writerow(["Overlay", "SmtCal"] + [""] * 6)
    writer.writerow(headers)
    writer.writerow([serial, "Pass", "[]", "", start_time, stop_time, "B518", slot])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.getvalue(), encoding="utf-8")


def main():
    old_home = os.environ.get("HOME")
    try:
        with tempfile.TemporaryDirectory(prefix="b518-ticket09-app-") as temporary:
            os.environ["HOME"] = temporary
            from b518_log_solution import B518LogSolutionApp

            root_path = Path(temporary)
            active = root_path / "atlas" / "active"
            archive = root_path / "atlas" / "archive"
            active.mkdir(parents=True)
            archive.mkdir(parents=True)
            app_root = root_path / "Application Support"
            prefs = app_root / "preferences.json"
            with patch("b518_log_solution.APP_ROOT", app_root), \
                    patch("b518_log_solution.PREFS_PATH", prefs):
                root = tk.Tk()
                app = B518LogSolutionApp(root, hotkey_factory=LocalHotkey,
                                         session_root=app_root / "sessions")
                root.deiconify()
                root.update()
                try:
                    update_profile(app, "B518", "FCT", "atlas",
                                   {"active": str(active), "final": str(archive)}, 2, 3, 10, 90)

                    app.start_button.invoke()
                    wait_for(root, lambda: app.monitor is not None, "Atlas source preparation")
                    running_monitor = app.monitor
                    serial = "SMOKEATLAS0001"
                    active_record = active / "group0-slot1" / "system" / "records.csv"
                    write_atlas_record(active_record, serial)
                    wait_for(root, lambda: app.rounds.snapshot().results[0].status == "TESTING",
                             "Atlas trusted activity")
                    stamp = (datetime.now() + timedelta(seconds=1)).strftime(
                        "%Y%m%d_%H-%M-%S.000-ticket09")
                    final_record = archive / serial / stamp / "system" / "records.csv"
                    write_atlas_record(final_record, serial)
                    shutil.rmtree(active / "group0-slot1")
                    wait_for(root, lambda: app.rounds.snapshot().state == "COMPLETED"
                             and [item.status for item in app.rounds.snapshot().results] == ["PASS", "NOTEST"]
                             and [app.status_rows[slot]["status"].cget("text")
                                  for slot in range(1, 3)] == ["PASS", "NOTEST"],
                             "underfilled Atlas round")
                    underfilled = app.rounds.snapshot()

                    wait_for(root, lambda: str(app.start_button.cget("state")) == "normal",
                             "restart button after Atlas completion")
                    app.start_button.invoke()
                    wait_for(root, lambda: app.monitor is not None, "empty-round source preparation")
                    wait_for(root, lambda: app.rounds.snapshot().state == "COMPLETED"
                             and all(item.status == "NOTEST" for item in app.rounds.snapshot().results),
                             "all-empty start deadline")
                    empty = app.rounds.snapshot()

                    wait_for(root, lambda: str(app.start_button.cget("state")) == "normal",
                             "restart button after empty round")
                    update_profile(app, "B518", "FCT", "atlas",
                                   {"active": str(active), "final": str(archive)}, 2, 30, 2, 90)
                    previous_round_id = app.rounds.snapshot().round_id
                    app.start_button.invoke()
                    wait_for(root, lambda: app.rounds.snapshot().round_id != previous_round_id
                             and app.monitor is not None, "timeout-round source preparation")
                    write_atlas_record(active / "group0-slot1" / "system" / "records.csv", "SMOKEATLAS0002")
                    try:
                        wait_for(root, lambda: app.rounds.snapshot().results[0].status == "TESTING",
                                 "second Atlas trusted activity")
                    except RuntimeError as error:
                        print("timeout-flow diagnostic:", app.rounds.snapshot(),
                              "active exists:", (active / "group0-slot1").exists())
                        raise error
                    wait_for(root, lambda: app.rounds.snapshot().results[0].status == "TIMEOUT",
                             "individual channel timeout")
                    if app.rounds.snapshot().state != "RUNNING":
                        raise RuntimeError("A channel timeout stopped the other active positions.")
                    app.stop_button.invoke()
                    stopped = app.rounds.snapshot()
                    if [item.status for item in stopped.results] != ["TIMEOUT", "STOPPED"]:
                        raise RuntimeError("Manual stop did not preserve TIMEOUT and stop the waiting slot.")
                    if stopped.result_available or stopped.state != "STOPPED":
                        raise RuntimeError("Manual stop incorrectly released a normal completed round.")

                    rswmt_output = root_path / "rswmt" / "SmtCal"
                    rswmt_output.mkdir(parents=True)
                    update_profile(app, "B518", "BT", "rswmt",
                                   {"output": str(rswmt_output), "final": str(rswmt_output),
                                    "caseinfo": ""},
                                   4, 12, 1, 90)
                    wait_for(root, lambda: str(app.start_button.cget("state")) == "normal",
                             "restart button after manual stop")
                    app.start_button.invoke()
                    wait_for(root, lambda: app.monitor is not None, "RS-WMT source preparation")
                    source_start = datetime.now()
                    folder_stamp = (source_start + timedelta(seconds=1)).strftime("%Y-%m-%d_%H-%M-%S")
                    file_stamp = folder_stamp
                    result = rswmt_output / folder_stamp / ("SMOKERSWMT0001_{}.csv".format(file_stamp))
                    stopped_at = source_start + timedelta(seconds=1)
                    write_rswmt_final(result, "SMOKERSWMT0001", 1, stopped_at)
                    try:
                        wait_for(root, lambda: app.rounds.snapshot().state == "COMPLETED"
                                 and app.rounds.snapshot().results[0].status == "PASS",
                                 "RS-WMT final-only result", timeout=20)
                    except RuntimeError as error:
                        print("RS-WMT diagnostic:", app.rounds.snapshot(), result,
                              result.exists(), app.monitor.settings if app.monitor else None)
                        raise error
                    rswmt = app.rounds.snapshot()
                    if any(item.event.status == "TESTING" for item in rswmt.events):
                        raise RuntimeError("The final-only source fabricated TESTING activity.")
                    if [item.status for item in rswmt.results[1:]] != ["NOTEST"] * 3:
                        raise RuntimeError("The final-only round did not finish empty positions as NOTEST.")

                    print(json.dumps({
                        "tk_window": root.geometry(),
                        "tk_scaling": float(root.tk.call("tk", "scaling")),
                        "underfilled": [item.status for item in underfilled.results],
                        "all_empty": [item.status for item in empty.results],
                        "individual_timeout_and_manual_stop": [item.status for item in stopped.results],
                        "rswmt_final_only": [item.status for item in rswmt.results],
                    }, sort_keys=True))
                finally:
                    try:
                        app.close()
                    except tk.TclError:
                        root.destroy()
    finally:
        if old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = old_home


if __name__ == "__main__":
    main()
