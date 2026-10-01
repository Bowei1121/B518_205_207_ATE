"""Exercise the real Tk app against controlled, anonymized Atlas file replay."""

import os
import json
import shutil
import sys
import tempfile
import time
import tkinter as tk
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_ROOT = APP_ROOT / "testdata" / "anonymized-baseline"
sys.path.insert(0, str(APP_ROOT / "src"))


class LocalHotkey:
    available = True
    message = "local App smoke"

    def __init__(self, _callback):
        pass

    def close(self):
        pass


def sample_for(station):
    folder = "B482 DFU/test_data" if station == "DFU" else "B482 FCT/unit-archive"
    samples = sorted((SAMPLE_ROOT / folder).rglob("records.csv"))
    if not samples:
        raise RuntimeError("The anonymized Atlas {} archive sample is missing.".format(station))
    return samples[0]


def wait_for(root, condition, description, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        root.update()
        if condition():
            return
        time.sleep(0.05)
    raise RuntimeError("Timed out while waiting for {}.".format(description))


def exercise_station(station, sample, temporary_root, app_type, trusted_sn_from_records, records_status):
    station_root = temporary_root / station
    active = station_root / "active"
    final = station_root / ("test_data" if station == "DFU" else "unit-archive")
    active.mkdir(parents=True)
    final.mkdir(parents=True)
    record = active / "group0-slot1" / "system" / "records.csv"
    record.parent.mkdir(parents=True)

    root = tk.Tk()
    app = app_type(root, hotkey_factory=LocalHotkey)
    app.project.set("B518")
    app.station.set(station)
    profile = app.profiles.get("B518", station)
    paths = dict(profile.paths)
    paths.update({"active": str(active), "final": str(final)})
    app.profiles = app.profiles.with_profile(replace(profile, paths=paths))
    app._load_selected_profile_values()
    root.deiconify()
    root.update()
    try:
        app.start_button.invoke()
        if app.monitor is None:
            raise RuntimeError("The {} monitor did not start.".format(station))
        running_monitor = app.monitor

        running_profile = app.profiles.get("B518", station)
        changed_mapping = ((1, 2), (2, 1)) + running_profile.mapping[2:]
        app.profiles = app.profiles.with_profile(replace(running_profile, mapping=changed_mapping))

        shutil.copyfile(sample, record)
        wait_for(
            root,
            lambda: app.rounds.snapshot().results[0].status == "TESTING",
            "{} active evidence".format(station),
        )
        shutil.rmtree(active / "group0-slot1")
        serial = trusted_sn_from_records(sample)
        archive_stamp = (datetime.now() + timedelta(seconds=1)).strftime("%Y%m%d_%H-%M-%S.000-smoke")
        archive = final / serial / archive_stamp / "system" / "records.csv"
        archive.parent.mkdir(parents=True)
        shutil.copyfile(sample, archive)

        wait_for(
            root,
            lambda: app.rounds.snapshot().state == "COMPLETED",
            "{} completed round".format(station),
        )
        snapshot = app.rounds.snapshot()
        expected = records_status(sample)
        first_result = snapshot.results[0]
        if first_result.status != expected or first_result.sn != serial:
            raise RuntimeError("The {} round did not preserve the sample's final result.".format(station))
        if not snapshot.result_available:
            raise RuntimeError("The {} completed round is not marked available.".format(station))
        if app.status_rows[1]["status"].cget("text") != expected:
            raise RuntimeError("The {} App row did not display the completed result.".format(station))
        session = json.loads((running_monitor.session.path / "session.json").read_text(encoding="utf-8"))
        snapshot_mapping = session["settings"]["profile_snapshot"]["profile"]["mapping"]
        if snapshot_mapping[0]["display"] != 1:
            raise RuntimeError("The {} round profile snapshot changed after start.".format(station))
        return {"station": station, "result": expected, "completed_slots": 1,
                "notest_slots": sum(result.status == "NOTEST" for result in snapshot.results)}
    finally:
        try:
            app.close()
        except tk.TclError:
            root.destroy()


def main():
    previous_home = os.environ.get("HOME")
    try:
        with tempfile.TemporaryDirectory(prefix="b518-atlas-app-smoke-") as temporary:
            os.environ["HOME"] = temporary
            from atlas_source_adapter import records_status, trusted_sn_from_records
            from b518_log_solution import B518LogSolutionApp

            results = []
            for station in ("DFU", "FCT"):
                results.append(exercise_station(
                    station, sample_for(station), Path(temporary),
                    B518LogSolutionApp, trusted_sn_from_records, records_status,
                ))
            print("Controlled local App replay passed: {}".format(
                ", ".join("{} {} ({} NOTEST)".format(
                    result["station"], result["result"], result["notest_slots"],
                ) for result in results)
            ))
    finally:
        if previous_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = previous_home


if __name__ == "__main__":
    main()
