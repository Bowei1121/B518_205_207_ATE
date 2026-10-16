"""Capture a short human-operated input trace in an isolated, real Tk App."""

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import tkinter as tk
import b518_log_solution as ui


class DiagnosticHotkey:
    available = True
    message = "Input diagnostic: global hotkey disabled"

    def __init__(self, callback):
        pass

    def close(self):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int, default=45)
    parser.add_argument("--output", type=Path, help="Directory for trace and summary")
    args = parser.parse_args()
    if not 5 <= args.seconds <= 60:
        parser.error("--seconds must be between 5 and 60")
    directory = Path(tempfile.mkdtemp(prefix="b518-hmi-input-"))
    original_preferences = ui.PREFS_PATH
    ui.APP_ROOT = directory
    ui.PREFS_PATH = directory / "preferences.json"
    if original_preferences.is_file():
        shutil.copyfile(original_preferences, ui.PREFS_PATH)
    output = args.output or directory
    output.mkdir(parents=True, exist_ok=True)
    log_path = output / "input-trace.jsonl"
    log = log_path.open("w", encoding="utf-8", buffering=1)
    started = time.monotonic()
    root = tk.Tk()
    app = ui.B518LogSolutionApp(root, hotkey_factory=DiagnosticHotkey,
                                session_root=directory / "sessions",
                                app_event_path=directory / "app-events.json")

    records = []
    root_destroyed = False

    def record(kind, **details):
        entry = {"seconds": round(time.monotonic() - started, 4), "kind": kind, **details}
        records.append(entry)
        log.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def on_destroy(event):
        nonlocal root_destroyed
        if event.widget is root:
            root_destroyed = True
            record("root_destroyed")

    root.bind("<Destroy>", on_destroy, add="+")

    def event_received(sequence, event):
        # Record control identities only; never record entered text or keys.
        record(sequence, widget=str(event.widget),
               focus=str(root.focus_get()),
               toolbar=event.widget in (app.settings_button,
                                       app.round_alarm_button,
                                       app.language_button, app.review_button))

    for sequence in ("<FocusIn>", "<FocusOut>", "<ButtonPress-1>",
                     "<ButtonRelease-1>", "<KeyPress-Tab>",
                     "<Shift-KeyPress-Tab>", "<KeyPress-space>",
                     "<KeyPress-Return>"):
        root.bind_all(sequence, lambda event, sequence=sequence:
                      event_received(sequence, event), add="+")

    for name, button in (("settings", app.settings_button),
                         ("recovery", app.round_alarm_button)):
        original_command = button.cget("command")

        def invoke(name=name, original_command=original_command):
            command_started = time.monotonic()
            record("command_start", control=name)
            try:
                return root.tk.call(original_command)
            finally:
                record("command_end", control=name,
                       duration_ms=round((time.monotonic() - command_started) * 1000, 2))

        button.configure(command=invoke)

    try:
        from AppKit import NSApplication
    except ImportError:
        NSApplication = None

    last_heartbeat = time.monotonic()
    previous_state = None

    def heartbeat():
        nonlocal last_heartbeat, previous_state
        now = time.monotonic()
        state = {"focus": str(root.focus_get()),
                 "hints": [hint._window is not None for hint in app._toolbar_hints]}
        if NSApplication is not None:
            native_app = NSApplication.sharedApplication()
            key = native_app.keyWindow()
            state.update(active=bool(native_app.isActive()),
                         key_window=key.windowNumber() if key else None)
        elapsed_ms = round((now - last_heartbeat) * 1000, 2)
        if state != previous_state or elapsed_ms > 150:
            record("heartbeat", interval_ms=elapsed_ms, **state)
        previous_state = state
        last_heartbeat = now
        root.after(50, heartbeat)

    def finish():
        record("normal_close_requested")
        app.close()

    root.protocol("WM_DELETE_WINDOW", finish)
    root.after(50, heartbeat)
    root.after(args.seconds * 1000, finish)
    print("真實 App 輸入診斷，{} 秒後自動關閉。".format(args.seconds), flush=True)
    print("請先按 Tab，滑鼠停在齒輪直到提示出現，再單擊齒輪；關閉設定後重複鈴鐺。", flush=True)
    print("測試使用暫存資料；請勿啟動監控。紀錄：{}".format(log_path), flush=True)
    try:
        root.mainloop()
    finally:
        record("finished")
        log.close()
        counts = {}
        for entry in records:
            counts[entry["kind"]] = counts.get(entry["kind"], 0) + 1
        summary = {
            "trace": str(log_path), "event_counts": counts,
            "max_heartbeat_interval_ms": max(
                (entry.get("interval_ms", 0) for entry in records), default=0),
            "commands": [entry for entry in records if entry["kind"] == "command_end"],
            "normal_close_completed": root_destroyed and bool(
                counts.get("normal_close_requested")),
            "interpretation": "Human input trace; no automatic defect/pass verdict.",
        }
        (output / "input-summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("摘要：{}".format(output / "input-summary.json"), flush=True)


if __name__ == "__main__":
    main()
