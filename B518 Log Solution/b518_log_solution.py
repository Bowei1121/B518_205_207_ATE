"""B518 Log Solution — local-only desktop monitor."""

from __future__ import annotations

import json
import queue
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from log_monitoring import AtlasActiveArchiveMonitor, BtLogMonitor, MonitorEvent


APP_ROOT = Path.home() / "Library" / "Application Support" / "B518LogSolution"
PREFS_PATH = APP_ROOT / "preferences.json"
STATUS_COLOURS = {
    "PASS": "#00ef00", "FAIL": "#ff0000", "TESTING": "#ffff00", "NOTEST": "#f04bf1",
    "WAITING": "#d9d9d9", "COMPLETING": "#82c7ff", "STALLED": "#ff9900", "STOPPED": "#bfbfbf",
}


class B518LogSolutionApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("B518 Log Solution-V0.1.0")
        self.root.minsize(680, 720)
        self.events: queue.Queue[MonitorEvent] = queue.Queue()
        self.monitor = None
        self.prefs = self._load_preferences()
        self.station = tk.StringVar(value=self.prefs.get("station", "FCT"))
        self.paths = {name: {field: tk.StringVar(value=self.prefs.get("paths", {}).get(name, {}).get(field, ""))
                             for field in ("active", "final", "caseinfo")}
                      for name in ("DFU", "FCT", "BT")}
        self._build()
        self._refresh_path_labels()
        self.root.after(150, self._drain_events)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _build(self) -> None:
        body = ttk.Frame(self.root, padding=12)
        body.pack(fill="both", expand=True)
        station_box = ttk.LabelFrame(body, text="工站與本機 Log 路徑", padding=10)
        station_box.pack(fill="x")
        ttk.Label(station_box, text="工站").grid(row=0, column=0, sticky="w")
        choice = ttk.Combobox(station_box, values=("DFU", "FCT", "BT"), state="readonly", textvariable=self.station, width=14)
        choice.grid(row=0, column=1, sticky="w", padx=(8, 16))
        choice.bind("<<ComboboxSelected>>", lambda _: self._refresh_path_labels())
        self.path_labels = []
        for row in range(3):
            label = ttk.Label(station_box, text="")
            value = ttk.Entry(station_box, width=62)
            select = ttk.Button(station_box, text="選擇", width=8, command=lambda index=row: self._choose_path(index))
            label.grid(row=row + 1, column=0, sticky="w", pady=3)
            value.grid(row=row + 1, column=1, sticky="ew", padx=8, pady=3)
            select.grid(row=row + 1, column=2, pady=3)
            self.path_labels.append((label, value, select))
        station_box.columnconfigure(1, weight=1)

        controls = ttk.LabelFrame(body, text="本輪監控", padding=10)
        controls.pack(fill="x", pady=(10, 0))
        self.start_button = ttk.Button(controls, text="開始監控", command=self.start_monitor)
        self.start_button.grid(row=0, column=0, padx=4)
        self.stop_button = ttk.Button(controls, text="停止監控", command=self.stop_monitor, state="disabled")
        self.stop_button.grid(row=0, column=1, padx=4)
        self.bt_all = ttk.Button(controls, text="BT Log Start All", command=lambda: self.start_monitor((1, 2, 3, 4)))
        self.bt_one = [ttk.Button(controls, text="BT Log Start {}".format(slot), command=lambda slot=slot: self.start_monitor((slot,))) for slot in range(1, 5)]
        self.bt_all.grid(row=0, column=2, padx=(18, 4))
        for index, button in enumerate(self.bt_one):
            button.grid(row=0, column=index + 3, padx=2)
        ttk.Button(controls, text="開啟 Session 紀錄", command=self.open_session).grid(row=0, column=7, padx=(16, 0))

        results = ttk.LabelFrame(body, text="本輪結果", padding=8)
        results.pack(fill="both", expand=True, pady=(10, 0))
        self.tree = ttk.Treeview(results, columns=("slot", "sn", "status"), show="headings", height=10)
        for column, title, width in (("slot", "Slot", 90), ("sn", "SN", 390), ("status", "狀態", 150)):
            self.tree.heading(column, text=title)
            self.tree.column(column, width=width, anchor="center" if column != "sn" else "w")
        for status, colour in STATUS_COLOURS.items():
            self.tree.tag_configure(status, background=colour)
        self.tree.pack(fill="both", expand=True)

        log_box = ttk.LabelFrame(body, text="即時事件 Log", padding=8)
        log_box.pack(fill="both", expand=True, pady=(10, 0))
        self.log = tk.Text(log_box, height=10, wrap="word", state="disabled")
        self.log.pack(fill="both", expand=True)

    def _load_preferences(self) -> dict:
        try:
            return json.loads(PREFS_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_preferences(self) -> None:
        APP_ROOT.mkdir(parents=True, exist_ok=True)
        payload = {"station": self.station.get(), "paths": {station: {field: value.get() for field, value in values.items()}
                  for station, values in self.paths.items()}}
        PREFS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _refresh_path_labels(self) -> None:
        station = self.station.get()
        schema = (("active", "即時 Log 根路徑 (active)"), ("final", "最終結果根路徑 (unitest)" if station == "DFU" else "最終結果根路徑 (unit-archive)"))
        if station == "BT":
            schema = (("final", "BT TestData 根路徑"), ("caseinfo", "BT CaseInfo 根路徑（選填）"))
        for index, widgets in enumerate(self.path_labels):
            label, entry, button = widgets
            if index < len(schema):
                field, text = schema[index]
                label.configure(text=text)
                entry.configure(textvariable=self.paths[station][field], state="normal")
                button.configure(state="normal")
            else:
                label.configure(text="")
                entry.configure(textvariable=tk.StringVar(value=""), state="disabled")
                button.configure(state="disabled")
        visible_bt = station == "BT"
        for widget in [self.bt_all, *self.bt_one]:
            widget.configure(state="normal" if visible_bt and self.monitor is None else "disabled")

    def _choose_path(self, index: int) -> None:
        station = self.station.get()
        fields = ("final", "caseinfo") if station == "BT" else ("active", "final")
        path = filedialog.askdirectory(parent=self.root, mustexist=True, title="選擇 {} 路徑".format(station))
        if path:
            self.paths[station][fields[index]].set(path)
            self._save_preferences()

    def _log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def start_monitor(self, requested_slots=None) -> None:
        if self.monitor is not None:
            return
        station = self.station.get()
        values = self.paths[station]
        if station == "BT":
            final = Path(values["final"].get()).expanduser()
            if not final.is_dir():
                messagebox.showerror("路徑錯誤", "請選擇可讀取的 BT TestData 根路徑。", parent=self.root)
                return
            self.monitor = BtLogMonitor(final, requested_slots or (1, 2, 3, 4),
                                        caseinfo_root=Path(values["caseinfo"].get()).expanduser() if values["caseinfo"].get() else None,
                                        callback=self.events.put)
        else:
            active, final = Path(values["active"].get()).expanduser(), Path(values["final"].get()).expanduser()
            if not active.is_dir() or not final.is_dir():
                messagebox.showerror("路徑錯誤", "請同時選擇 active 與最終結果根路徑。", parent=self.root)
                return
            limit = 7 if station == "DFU" else 6
            self.monitor = AtlasActiveArchiveMonitor(station, active, final, tuple(range(1, limit + 1)), callback=self.events.put)
        self._save_preferences()
        self.tree.delete(*self.tree.get_children())
        for slot in self.monitor.slots:
            self.tree.insert("", "end", iid=str(slot), values=("slot{}".format(slot), "", "WAITING"), tags=("WAITING",))
        self.monitor.start()
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self._refresh_path_labels()
        self._log("{} 監控已開始；本輪時間與啟動前快照已建立。".format(station))

    def stop_monitor(self) -> None:
        if self.monitor:
            self.monitor.stop()

    def _drain_events(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                self._handle_event(event)
        except queue.Empty:
            pass
        self.root.after(150, self._drain_events)

    def _handle_event(self, event: MonitorEvent) -> None:
        self._log(event.message)
        if event.slot and self.monitor:
            result = self.monitor.results[event.slot]
            self.tree.item(str(event.slot), values=("slot{}".format(event.slot), result.sn, result.status), tags=(result.status,))
        if event.kind == "review":
            if messagebox.askyesno("BT 人工覆核", event.message + "\n\n是否接受新檔案？", parent=self.root):
                self.monitor.resolve_review("accept")
            else:
                self.monitor.resolve_review("reject")
        if event.kind in {"finished", "stopped"}:
            self.start_button.configure(state="normal")
            self.stop_button.configure(state="disabled")
            self.monitor = None
            self._refresh_path_labels()

    def open_session(self) -> None:
        path = self.monitor.session.path if self.monitor else (APP_ROOT / "sessions")
        path.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.Popen(["open", str(path)])
        except OSError as error:
            messagebox.showerror("無法開啟", str(error), parent=self.root)

    def close(self) -> None:
        if self.monitor:
            self.monitor.stop()
        self._save_preferences()
        self.root.destroy()


if __name__ == "__main__":
    window = tk.Tk()
    B518LogSolutionApp(window)
    window.mainloop()
