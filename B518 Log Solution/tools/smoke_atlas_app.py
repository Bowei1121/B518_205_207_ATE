"""Exercise the real Tk app against controlled, anonymized Atlas file replay."""

import os
import json
import shutil
import sys
import tempfile
import time
import tkinter as tk
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch


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

    export_path = station_root / "deployment-profile.json"
    maker_preferences = station_root / "engineer" / "preferences.json"
    with patch("b518_log_solution.APP_ROOT", maker_preferences.parent), \
            patch("b518_log_solution.PREFS_PATH", maker_preferences):
        maker_root = tk.Tk()
        maker = app_type(maker_root, hotkey_factory=LocalHotkey)
        maker.open_settings()
        maker.profile_editor_project.set("Demo")
        maker.profile_editor_machine.set(station)
        maker.profile_editor_platform.set("atlas")
        maker.profile_editor_capacity.set(str(maker.profiles.get("B518", station).capacity))
        maker.profile_editor_paths["active"].set(str(active))
        maker.profile_editor_paths["final"].set(str(final))
        maker.profile_editor_mapping.set(maker._mapping_text(
            maker.profiles.get("B518", station).mapping))
        maker._apply_profile_editor()
        with patch("b518_log_solution.filedialog.asksaveasfilename", return_value=str(export_path)):
            maker._export_profiles()
        maker._close_settings()
        maker.hotkey.close()
        maker_root.destroy()

    deployment_preferences = station_root / "deployment" / "preferences.json"
    with patch("b518_log_solution.APP_ROOT", deployment_preferences.parent), \
            patch("b518_log_solution.PREFS_PATH", deployment_preferences):
        root = tk.Tk()
        app = app_type(root, hotkey_factory=LocalHotkey)
        app.open_settings()
        with patch("b518_log_solution.filedialog.askopenfilename", return_value=str(export_path)):
            app._import_profiles()
        app.project.set("Demo")
        app._project_changed()
        app.station.set(station)
        app._profile_changed()
        app._close_settings()
    root.deiconify()
    root.update()
    try:
        app.start_button.invoke()
        if app.monitor is None:
            raise RuntimeError("The {} monitor did not start.".format(station))
        running_monitor = app.monitor

        running_profile = app.profiles.get("Demo", station)
        changed_mapping = ((1, 2), (2, 1)) + running_profile.mapping[2:]
        app.open_settings()
        app.profile_editor_mapping.set(app._mapping_text(changed_mapping))
        app._apply_profile_editor()
        app._close_settings()

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
            app._close_settings()
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
