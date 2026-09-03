"""B518 Log Solution — local-only KVM-friendly desktop monitor."""

from __future__ import annotations

import json
import queue
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Dict, Optional

from global_hotkey import HotkeyRegistration, create_global_hotkey
from log_monitoring import AtlasActiveArchiveMonitor, BtLogMonitor, MonitorEvent


APP_ROOT = Path.home() / "Library" / "Application Support" / "B518LogSolution"
PREFS_PATH = APP_ROOT / "preferences.json"
STATION_SLOTS = {"DFU": 7, "FCT": 6, "BT": 4}
WINDOW_HEIGHTS = {"DFU": 620, "FCT": 556, "BT": 428}
WINDOW_WIDTH = 480
STATUS_COLOURS = {
    "PASS": "#00ef00", "FAIL": "#ff0000", "TESTING": "#ffff00", "NOTEST": "#f04bf1",
    "WAITING": "#d9d9d9", "COMPLETING": "#82c7ff", "STALLED": "#ff9900", "STOPPED": "#bfbfbf",
}


def slot_count(station: str) -> int:
    return STATION_SLOTS.get(station.upper(), STATION_SLOTS["FCT"])


def window_height(station: str) -> int:
    return WINDOW_HEIGHTS.get(station.upper(), WINDOW_HEIGHTS["FCT"])


def sn_font_size(sn: str, column_width: int = 250) -> int:
    """Approximate a readable fixed-width font size without truncating a SN."""
    if not sn:
        return 20
    return max(12, min(20, int(column_width / max(len(sn) * 0.62, 1))))


class B518LogSolutionApp:
    def __init__(self, root: tk.Tk, hotkey_factory=create_global_hotkey):
        self.root = root
        self.root.title("B518 Log Solution-V0.1.0")
        self.root.resizable(False, False)
        self.events: queue.Queue[MonitorEvent] = queue.Queue()
        self.monitor = None
        self.prefs = self._load_preferences()
        self.station = tk.StringVar(value=self.prefs.get("station", "FCT"))
        self.paths = {name: {field: tk.StringVar(value=self.prefs.get("paths", {}).get(name, {}).get(field, ""))
                             for field in ("active", "final", "caseinfo")}
                      for name in STATION_SLOTS}
        self.status_rows: Dict[int, Dict[str, tk.Label]] = {}
        self.event_lines: list[str] = []
        self.settings_window: Optional[tk.Toplevel] = None
        self.settings_log: Optional[tk.Text] = None
        self._build()
        self.hotkey: HotkeyRegistration = hotkey_factory(self._on_global_hotkey)
        self.root.bind_all("<Control-Shift-M>", self._on_local_hotkey)
        self._position_window()
        self.root.after(150, self._drain_events)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        if not self.hotkey.available:
            self.root.after(300, self._show_hotkey_warning)

    def _build(self) -> None:
        self.root.configure(background="#f3f4f6")
        body = tk.Frame(self.root, background="#f3f4f6", padx=8, pady=8)
        body.pack(fill="both", expand=True)
        header = tk.Frame(body, background="#f3f4f6", height=38)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Button(header, text="設定", command=self.open_settings, font=("Helvetica", 14, "bold"), width=5).pack(side="left")
        self.station_title = tk.Label(header, background="#f3f4f6", font=("Helvetica", 20, "bold"))
        self.station_title.pack(side="left", expand=True)
        self.monitor_state = tk.Label(header, background="#f3f4f6", foreground="#555555", font=("Helvetica", 11, "bold"))
        self.monitor_state.pack(side="right")

        headings = tk.Frame(body, background="#f3f4f6", pady=5)
        headings.pack(fill="x")
        for column, text, width in ((0, "通道", 70), (1, "狀態", 130), (2, "產品 SN", 256)):
            headings.grid_columnconfigure(column, minsize=width, weight=0)
            tk.Label(headings, text=text, background="#f3f4f6", font=("Helvetica", 14, "bold"), anchor="center").grid(
                row=0, column=column, sticky="nsew")

        self.rows_box = tk.Frame(body, background="#111111", highlightthickness=1, highlightbackground="#111111")
        self.rows_box.pack(fill="x")
        controls = tk.Frame(body, background="#f3f4f6", pady=9)
        controls.pack(fill="x", side="bottom")
        self.start_button = tk.Button(controls, text="開始監控  (Ctrl+Shift+M)", command=self.start_monitor,
                                      font=("Helvetica", 16, "bold"), height=2)
        self.start_button.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.stop_button = tk.Button(controls, text="停止監控", command=self.stop_monitor,
                                     font=("Helvetica", 16, "bold"), height=2, state="disabled")
        self.stop_button.pack(side="left", fill="x", expand=True, padx=(4, 0))
        self._render_rows()

    def _render_rows(self) -> None:
        for child in self.rows_box.winfo_children():
            child.destroy()
        self.status_rows = {}
        station = self.station.get().upper()
        self.station_title.configure(text="{} Log 監控".format(station))
        self.monitor_state.configure(text="監控中" if self.monitor else "待命")
        for slot in range(1, slot_count(station) + 1):
            row = tk.Frame(self.rows_box, background="#111111", height=64)
            row.grid(row=slot - 1, column=0, sticky="ew", pady=(0, 1))
            row.grid_propagate(False)
            row.grid_columnconfigure(0, minsize=70)
            row.grid_columnconfigure(1, minsize=130)
            row.grid_columnconfigure(2, minsize=256)
            slot_label = tk.Label(row, text="Slot {}".format(slot), background="#ffffff", foreground="#000000",
                                  font=("Helvetica", 18, "bold"), anchor="center")
            status_label = tk.Label(row, text="WAITING", background=STATUS_COLOURS["WAITING"], foreground="#000000",
                                    font=("Helvetica", 22, "bold"), anchor="center")
            sn_label = tk.Label(row, text="", background="#ffffff", foreground="#000000",
                                font=("Menlo", 20, "bold"), anchor="w", padx=8)
            slot_label.grid(row=0, column=0, sticky="nsew", padx=(0, 1))
            status_label.grid(row=0, column=1, sticky="nsew", padx=(0, 1))
            sn_label.grid(row=0, column=2, sticky="nsew")
            self.status_rows[slot] = {"slot": slot_label, "status": status_label, "sn": sn_label}
        self._position_window()

    def _position_window(self) -> None:
        self.root.update_idletasks()
        width, height = WINDOW_WIDTH, window_height(self.station.get())
        x = max(self.root.winfo_screenwidth() - width - 12, 0)
        self.root.geometry("{}x{}+{}+32".format(width, height, x))

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

    def _on_local_hotkey(self, _event: object) -> str:
        self._start_from_hotkey()
        return "break"

    def _on_global_hotkey(self) -> None:
        self.root.after_idle(self._start_from_hotkey)

    def _start_from_hotkey(self) -> None:
        if self.monitor is None:
            self.start_monitor()

    def _show_hotkey_warning(self) -> None:
        messagebox.showwarning("全域快捷鍵不可用", self.hotkey.message, parent=self.root)

    def _set_monitor_controls(self, monitoring: bool) -> None:
        self.start_button.configure(state="disabled" if monitoring else "normal")
        self.stop_button.configure(state="normal" if monitoring else "disabled")
        self.monitor_state.configure(text="監控中" if monitoring else "待命")

    def _set_row(self, slot: int, sn: str, status: str) -> None:
        widgets = self.status_rows.get(slot)
        if not widgets:
            return
        status = status if status in STATUS_COLOURS else "WAITING"
        widgets["status"].configure(text=status, background=STATUS_COLOURS[status])
        widgets["sn"].configure(text=sn, font=("Menlo", sn_font_size(sn), "bold"))

    def _reset_rows(self) -> None:
        for slot in self.status_rows:
            self._set_row(slot, "", "WAITING")

    def start_monitor(self) -> None:
        if self.monitor is not None:
            return
        station = self.station.get().upper()
        values = self.paths[station]
        if station == "BT":
            final = Path(values["final"].get()).expanduser()
            if not final.is_dir():
                messagebox.showerror("路徑錯誤", "請選擇可讀取的 BT TestData 根路徑。", parent=self.root)
                return
            self.monitor = BtLogMonitor(final, (1, 2, 3, 4),
                                        caseinfo_root=Path(values["caseinfo"].get()).expanduser() if values["caseinfo"].get() else None,
                                        callback=self.events.put)
        else:
            active, final = Path(values["active"].get()).expanduser(), Path(values["final"].get()).expanduser()
            if not active.is_dir() or not final.is_dir():
                messagebox.showerror("路徑錯誤", "請同時選擇 active 與最終結果根路徑。", parent=self.root)
                return
            self.monitor = AtlasActiveArchiveMonitor(station, active, final, tuple(range(1, slot_count(station) + 1)), callback=self.events.put)
        self._save_preferences()
        self._reset_rows()
        self.monitor.start()
        self._set_monitor_controls(True)
        self._log("{} 監控已開始；本輪時間與啟動前快照已建立。".format(station))

    def stop_monitor(self) -> None:
        if self.monitor:
            self.monitor.stop()

    def _log(self, text: str) -> None:
        self.event_lines.append(text)
        self.event_lines = self.event_lines[-500:]
        if self.settings_log and self.settings_log.winfo_exists():
            self.settings_log.configure(state="normal")
            self.settings_log.insert("end", text + "\n")
            self.settings_log.see("end")
            self.settings_log.configure(state="disabled")

    def _drain_events(self) -> None:
        try:
            while True:
                self._handle_event(self.events.get_nowait())
        except queue.Empty:
            pass
        self.root.after(150, self._drain_events)

    def _handle_event(self, event: MonitorEvent) -> None:
        self._log(event.message)
        if event.slot and self.monitor:
            result = self.monitor.results[event.slot]
            self._set_row(event.slot, result.sn, result.status)
        if event.kind == "review" and self.monitor:
            choice = messagebox.askyesno("BT 人工覆核", event.message + "\n\n是否接受新檔案？", parent=self.root)
            self.monitor.resolve_review("accept" if choice else "reject")
        if event.kind in {"finished", "stopped"}:
            self.monitor = None
            self._set_monitor_controls(False)

    def open_settings(self) -> None:
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.lift()
            return
        dialog = tk.Toplevel(self.root)
        self.settings_window = dialog
        dialog.title("B518 Log Solution 設定")
        dialog.geometry("720x620")
        dialog.minsize(680, 560)
        dialog.transient(self.root)
        dialog.protocol("WM_DELETE_WINDOW", self._close_settings)
        notebook = ttk.Notebook(dialog)
        notebook.pack(fill="both", expand=True, padx=12, pady=12)
        settings_tab = ttk.Frame(notebook, padding=12)
        log_tab = ttk.Frame(notebook, padding=12)
        notebook.add(settings_tab, text="監控設定")
        notebook.add(log_tab, text="事件與 Session")
        self._build_settings_tab(settings_tab)
        self._build_log_tab(log_tab)

    def _build_settings_tab(self, parent: ttk.Frame) -> None:
        self.settings_station = tk.StringVar(value=self.station.get())
        self.settings_paths = {station: {field: tk.StringVar(value=value.get()) for field, value in fields.items()}
                               for station, fields in self.paths.items()}
        ttk.Label(parent, text="工站").grid(row=0, column=0, sticky="w")
        state = "disabled" if self.monitor else "readonly"
        station_choice = ttk.Combobox(parent, values=tuple(STATION_SLOTS), textvariable=self.settings_station, state=state, width=14)
        station_choice.grid(row=0, column=1, sticky="w", padx=(8, 0))
        station_choice.bind("<<ComboboxSelected>>", lambda _event: self._render_setting_paths())
        self.settings_paths_box = ttk.Frame(parent)
        self.settings_paths_box.grid(row=1, column=0, columnspan=3, sticky="nsew", pady=(16, 0))
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(1, weight=1)
        self._render_setting_paths()
        ttk.Separator(parent).grid(row=2, column=0, columnspan=3, sticky="ew", pady=14)
        ttk.Label(parent, text="全域快捷鍵").grid(row=3, column=0, sticky="nw")
        shortcut = "Control+Shift+M\n{}".format(self.hotkey.message)
        ttk.Label(parent, text=shortcut, foreground="#157347" if self.hotkey.available else "#b02a37").grid(row=3, column=1, columnspan=2, sticky="w")
        buttons = ttk.Frame(parent)
        buttons.grid(row=4, column=0, columnspan=3, sticky="e", pady=(22, 0))
        ttk.Button(buttons, text="取消", command=self._close_settings).pack(side="right")
        if not self.monitor:
            ttk.Button(buttons, text="儲存", command=self._save_settings).pack(side="right", padx=(0, 8))

    def _render_setting_paths(self) -> None:
        for child in self.settings_paths_box.winfo_children():
            child.destroy()
        station = self.settings_station.get()
        schema = (("final", "BT TestData 根路徑"), ("caseinfo", "BT CaseInfo 根路徑（選填）")) if station == "BT" else (
            ("active", "即時 Log 根路徑 (active)"),
            ("final", "最終結果根路徑 (unitest)" if station == "DFU" else "最終結果根路徑 (unit-archive)"),
        )
        disabled = self.monitor is not None
        for row, (field, label) in enumerate(schema):
            ttk.Label(self.settings_paths_box, text=label).grid(row=row, column=0, sticky="w", pady=5)
            entry = ttk.Entry(self.settings_paths_box, textvariable=self.settings_paths[station][field], width=62,
                              state="disabled" if disabled else "normal")
            entry.grid(row=row, column=1, sticky="ew", padx=8, pady=5)
            ttk.Button(self.settings_paths_box, text="選擇", state="disabled" if disabled else "normal",
                       command=lambda current=field: self._choose_setting_path(current)).grid(row=row, column=2, pady=5)
        self.settings_paths_box.columnconfigure(1, weight=1)

    def _choose_setting_path(self, field: str) -> None:
        path = filedialog.askdirectory(parent=self.settings_window, mustexist=True,
                                       title="選擇 {} 路徑".format(self.settings_station.get()))
        if path:
            self.settings_paths[self.settings_station.get()][field].set(path)

    def _build_log_tab(self, parent: ttk.Frame) -> None:
        controls = ttk.Frame(parent)
        controls.pack(fill="x", pady=(0, 8))
        ttk.Button(controls, text="開啟 Session 紀錄", command=self.open_session).pack(side="left")
        self.settings_log = tk.Text(parent, wrap="word", state="disabled", height=26)
        self.settings_log.pack(fill="both", expand=True)
        self.settings_log.configure(state="normal")
        self.settings_log.insert("1.0", "\n".join(self.event_lines))
        self.settings_log.configure(state="disabled")

    def _save_settings(self) -> None:
        self.station.set(self.settings_station.get())
        for station, fields in self.settings_paths.items():
            for field, variable in fields.items():
                variable.set(self.settings_paths[station][field].get())
        self._save_preferences()
        self._render_rows()
        self._close_settings()

    def _close_settings(self) -> None:
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.destroy()
        self.settings_window = None
        self.settings_log = None

    def open_session(self) -> None:
        path = self.monitor.session.path if self.monitor else (APP_ROOT / "sessions")
        path.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.Popen(["open", str(path)])
        except OSError as error:
            messagebox.showerror("無法開啟", str(error), parent=self.root)

    def close(self) -> None:
        self.hotkey.close()
        if self.monitor:
            self.monitor.stop()
        self._save_preferences()
        self.root.destroy()


if __name__ == "__main__":
    window = tk.Tk()
    B518LogSolutionApp(window)
    window.mainloop()
