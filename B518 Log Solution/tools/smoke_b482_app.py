"""Exercise the real Tk app against an anonymized B482 TestData round."""

import os
import shutil
import sys
import tempfile
import time
import tkinter as tk
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_ROOT = APP_ROOT / "testdata" / "anonymized-baseline" / "B482 BT" / "2026-08-21" / "FAILED"
sys.path.insert(0, str(APP_ROOT / "src"))


class LocalHotkey:
    available = True
    message = "local App smoke"

    def __init__(self, _callback):
        pass

    def close(self):
        pass


def wait_for(root, condition, description, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        root.update()
        if condition():
            return
        time.sleep(0.05)
    raise RuntimeError("Timed out while waiting for {}.".format(description))


def main():
    previous_home = os.environ.get("HOME")
    try:
        with tempfile.TemporaryDirectory(prefix="b518-b482-app-smoke-") as temporary:
            os.environ["HOME"] = temporary
            from b518_log_solution import B518LogSolutionApp
            from b482_source_adapter import parse_bt_filename

            samples = sorted(SAMPLE_ROOT.glob("*.csv"))
            if len(samples) != 4:
                raise RuntimeError("The four anonymized B482 TestData samples are required.")

            testdata = Path(temporary) / "TestData"
            testdata.mkdir()
            root = tk.Tk()
            app = B518LogSolutionApp(root, hotkey_factory=LocalHotkey)
            app.project.set("B482")
            app.station.set("BT")
            profile = app.profiles.get("B482", "BT")
            paths = dict(profile.paths)
            paths["final"] = str(testdata)
            app.profiles = app.profiles.with_profile(replace(profile, paths=paths))
            app._load_selected_profile_values()
            root.deiconify()
            root.update()
            try:
                app.start_button.invoke()
                wait_for(root, lambda: app.monitor is not None, "BT source preparation")

                stamp = (datetime.now() + timedelta(seconds=2)).strftime("%Y%m%d%H%M%S")
                for sample in samples:
                    parsed = parse_bt_filename(sample)
                    if not parsed:
                        raise RuntimeError("An anonymized B482 TestData filename is unsupported.")
                    target = testdata / datetime.strptime(stamp, "%Y%m%d%H%M%S").strftime("%Y-%m-%d") / "FAILED"
                    name = "[Thread{}][{}][{}][{}][{}].csv".format(
                        parsed["thread"], parsed["config"], parsed["sn"], parsed["status"], stamp,
                    )
                    target.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(sample, target / name)

                wait_for(
                    root,
                    lambda: app.rounds.snapshot().state == "COMPLETED"
                    and all(app.status_rows[slot]["status"].cget("text") == "NOTEST"
                            for slot in range(1, 5)),
                    "completed B482 round",
                )
                snapshot = app.rounds.snapshot()
                statuses = [result.status for result in snapshot.results]
                if statuses != ["NOTEST"] * 4 or not snapshot.result_available:
                    raise RuntimeError("The B482 App round did not complete with four platform NOTEST results.")
                if any(app.status_rows[slot]["status"].cget("text") != "NOTEST" for slot in range(1, 5)):
                    raise RuntimeError("The App did not display the completed B482 results.")
                print("Controlled local B482 App replay passed: 4 platform NOTEST results, round completed.")
            finally:
                try:
                    app.close()
                except tk.TclError:
                    root.destroy()
    finally:
        if previous_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = previous_home


if __name__ == "__main__":
    main()
