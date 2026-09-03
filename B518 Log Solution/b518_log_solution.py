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
LIGHT_BACKGROUND = "#f3f4f6"
FIELD_BACKGROUND = "#ffffff"
TEXT_COLOUR = "#111827"
MUTED_TEXT_COLOUR = "#555555"
STATION_SLOTS = {"DFU": 7, "FCT": 6, "BT": 4}
WINDOW_HEIGHTS = {"DFU": 560, "FCT": 513, "BT": 419}
WINDOW_WIDTH = 360
MAIN_FONT_SIZE = 14
ROW_HEIGHT = 46
ROW_GAP = 1
ROW_WIDTH = 342
STATUS_TEMPLATE_STATES = ("PASS", "FAIL", "TESTING", "NOTEST")
STATUS_COLOURS = {
    "PASS": "#00ef00", "FAIL": "#ff0000", "TESTING": "#ffff00", "NOTEST": "#f04bf1",
    "WAITING": "#d9d9d9", "COMPLETING": "#82c7ff", "STALLED": "#ff9900", "STOPPED": "#bfbfbf",
}


def slot_count(station: str) -> int:
    return STATION_SLOTS.get(station.upper(), STATION_SLOTS["FCT"])


def window_height(station: str) -> int:
    return WINDOW_HEIGHTS.get(station.upper(), WINDOW_HEIGHTS["FCT"])


def sn_font_size(_sn: str, _column_width: int = 188) -> int:
    """Keep all main-HMI text at the fixed KVM template size."""
    return MAIN_FONT_SIZE


def configured_directory(value: str) -> Optional[Path]:
    """Return an existing configured directory; never treat blank as cwd."""
    text = value.strip()
    if not text:
        return None
    path = Path(text).expanduser()
    try:
        return path if path.is_dir() else None
    except OSError:
        return None


class B518LogSolutionApp:
    def __init__(self, root: tk.Tk, hotkey_factory=create_global_hotkey):
        self.root = root
        self.root.title("B518 Log Solution-V0.1.0")
        self.root.resizable(False, False)
        self.events: queue.Queue[MonitorEvent] = queue.Queue()
        self.hotkey_events: queue.Queue[bool] = queue.Queue()
        self.monitor = None
        self.prefs = self._load_preferences()
        self.station = tk.StringVar(value=self.prefs.get("station", "FCT"))
        self.paths = {name: {field: tk.StringVar(value=self.prefs.get("paths", {}).get(name, {}).get(field, ""))
                             for field in ("active", "final", "caseinfo")}
                      for name in STATION_SLOTS}
        self.status_rows: Dict[int, Dict[str, tk.Label]] = {}
        self.template_labels: Dict[str, tk.Label] = {}
        self.event_lines: list[str] = []
        self.settings_window: Optional[tk.Toplevel] = None
        self.settings_log: Optional[tk.Text] = None
        self._configure_appearance()
        self._build()
        self.hotkey: HotkeyRegistration = hotkey_factory(self._on_global_hotkey)
        self.root.bind_all("<Command-Shift-M>", self._on_local_hotkey)
        self._position_window()
        self.root.after(150, self._drain_events)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        if not self.hotkey.available:
            self.root.after(300, self._show_hotkey_warning)

    def _configure_appearance(self) -> None:
        """Force a readable light palette even when macOS uses Dark Mode."""
        self.style = ttk.Style(self.root)
        if "clam" in self.style.theme_names():
            self.style.theme_use("clam")
        self.root.configure(background=LIGHT_BACKGROUND)
        self.root.option_add("*TCombobox*Listbox.background", FIELD_BACKGROUND)
        self.root.option_add("*TCombobox*Listbox.foreground", TEXT_COLOUR)
        self.root.option_add("*TCombobox*Listbox.selectBackground", "#dbeafe")
        self.root.option_add("*TCombobox*Listbox.selectForeground", TEXT_COLOUR)
        self.style.configure(".", background=LIGHT_BACKGROUND, foreground=TEXT_COLOUR,
                             fieldbackground=FIELD_BACKGROUND)
        self.style.configure("TFrame", background=LIGHT_BACKGROUND)
        self.style.configure("TLabel", background=LIGHT_BACKGROUND, foreground=TEXT_COLOUR)
        self.style.configure("TLabelFrame", background=LIGHT_BACKGROUND, foreground=TEXT_COLOUR)
        self.style.configure("TLabelFrame.Label", background=LIGHT_BACKGROUND, foreground=TEXT_COLOUR)
        self.style.configure("TNotebook", background=LIGHT_BACKGROUND, borderwidth=0)
        self.style.configure("TNotebook.Tab", background="#e5e7eb", foreground=TEXT_COLOUR, padding=(12, 7))
        self.style.map("TNotebook.Tab", background=[("selected", FIELD_BACKGROUND), ("active", "#dbeafe")],
                       foreground=[("selected", TEXT_COLOUR), ("active", TEXT_COLOUR)])
        self.style.configure("TButton", background="#e5e7eb", foreground=TEXT_COLOUR,
                             padding=(10, 6), borderwidth=1)
        self.style.map("TButton", background=[("active", "#d1d5db"), ("pressed", "#cbd5e1"),
                                               ("disabled", "#eeeeee")],
                       foreground=[("disabled", "#777777")])
        self.style.configure("Main.TButton", background=FIELD_BACKGROUND, foreground=TEXT_COLOUR,
                             font=("Helvetica", MAIN_FONT_SIZE, "bold"), padding=(8, 7), borderwidth=1)
        self.style.map("Main.TButton", background=[("active", "#e5e7eb"), ("pressed", "#d1d5db"),
                                                    ("disabled", "#eeeeee")],
                       foreground=[("disabled", "#777777")])
        self.style.configure("TEntry", fieldbackground=FIELD_BACKGROUND, foreground=TEXT_COLOUR,
                             insertcolor=TEXT_COLOUR)
        self.style.map("TEntry", fieldbackground=[("disabled", "#e5e7eb")],
                       foreground=[("disabled", "#777777")])
        self.style.configure("TCombobox", fieldbackground=FIELD_BACKGROUND, background="#e5e7eb",
                             foreground=TEXT_COLOUR, arrowcolor=TEXT_COLOUR)
        self.style.map("TCombobox", fieldbackground=[("readonly", FIELD_BACKGROUND),
                                                      ("disabled", "#e5e7eb")],
                       foreground=[("readonly", TEXT_COLOUR), ("disabled", "#777777")],
                       selectbackground=[("readonly", FIELD_BACKGROUND)],
                       selectforeground=[("readonly", TEXT_COLOUR)])
        self.style.configure("TSeparator", background="#9ca3af")

    def _build(self) -> None:
        body = tk.Frame(self.root, background=LIGHT_BACKGROUND, padx=8, pady=8)
        body.pack(fill="both", expand=True)
        header = tk.Frame(body, background=LIGHT_BACKGROUND, height=34)
        header.pack(fill="x")
        header.pack_propagate(False)
        ttk.Button(header, text="設定", command=self.open_settings, style="Main.TButton", width=4).pack(side="left")
        self.station_title = tk.Label(header, background=LIGHT_BACKGROUND, foreground=TEXT_COLOUR,
                                      font=("Helvetica", MAIN_FONT_SIZE, "bold"))
        self.station_title.pack(side="left", expand=True)
        self.monitor_state = tk.Label(header, background=LIGHT_BACKGROUND, foreground=MUTED_TEXT_COLOUR,
                                      font=("Helvetica", MAIN_FONT_SIZE, "bold"))
        self.monitor_state.pack(side="right")

        legend = tk.Frame(body, background=LIGHT_BACKGROUND, height=58)
        legend.pack(fill="x")
        legend.pack_propagate(False)
        tk.Label(legend, text="KVM 狀態模板", background=LIGHT_BACKGROUND, foreground=TEXT_COLOUR,
                 font=("Helvetica", MAIN_FONT_SIZE, "bold")).place(x=0, y=0, width=342, height=24)
        for index, status in enumerate(STATUS_TEMPLATE_STATES):
            label = tk.Label(legend, text=status, background=STATUS_COLOURS[status], foreground="#000000",
                             font=("Helvetica", MAIN_FONT_SIZE, "bold"), relief="solid", borderwidth=1)
            label.place(x=index * 85, y=26, width=84, height=30)
            self.template_labels[status] = label

        headings = tk.Frame(body, background=LIGHT_BACKGROUND, height=30)
        headings.pack(fill="x")
        headings.pack_propagate(False)
        for text, x, width in (("通道", 0, 60), ("狀態", 60, 94), ("產品 SN", 154, 188)):
            tk.Label(headings, text=text, background=LIGHT_BACKGROUND, foreground=TEXT_COLOUR,
                     font=("Helvetica", MAIN_FONT_SIZE, "bold"), anchor="center").place(
                x=x, y=0, width=width, height=30)

        self.rows_box = tk.Frame(body, background="#111111", highlightthickness=1, highlightbackground="#111111",
                                 width=ROW_WIDTH + 2, height=1)
        self.rows_box.pack(fill="x")
        self.rows_box.pack_propagate(False)
        controls = tk.Frame(body, background=LIGHT_BACKGROUND, pady=9)
        controls.pack(fill="x", side="bottom")
        self.start_button = ttk.Button(controls, text="開始監控  (Command+Shift+M)", command=self.start_monitor,
                                       style="Main.TButton")
        self.start_button.pack(fill="x", pady=(0, 4))
        self.stop_button = ttk.Button(controls, text="停止監控", command=self.stop_monitor,
                                      style="Main.TButton", state="disabled")
        self.stop_button.pack(fill="x")
        self._render_rows()

    def _render_rows(self) -> None:
        for child in self.rows_box.winfo_children():
            child.destroy()
        self.status_rows = {}
        station = self.station.get().upper()
        row_count = slot_count(station)
        self.rows_box.configure(height=row_count * (ROW_HEIGHT + ROW_GAP) - ROW_GAP)
        self.station_title.configure(text="{} Log 監控".format(station))
        self.monitor_state.configure(text="監控中" if self.monitor else "待命")
        for slot in range(1, row_count + 1):
            row = tk.Frame(self.rows_box, background="#111111", width=ROW_WIDTH, height=ROW_HEIGHT)
            row.place(x=0, y=(slot - 1) * (ROW_HEIGHT + ROW_GAP), width=ROW_WIDTH, height=ROW_HEIGHT)
            row.pack_propagate(False)
            slot_label = tk.Label(row, text="Slot {}".format(slot), background="#ffffff", foreground="#000000",
                                  font=("Helvetica", MAIN_FONT_SIZE, "bold"), anchor="center")
            status_label = tk.Label(row, text="WAITING", background=STATUS_COLOURS["WAITING"], foreground="#000000",
                                    font=("Helvetica", MAIN_FONT_SIZE, "bold"), anchor="center")
            sn_label = tk.Label(row, text="", background="#ffffff", foreground="#000000",
                                font=("Menlo", MAIN_FONT_SIZE, "bold"), anchor="w", padx=5)
            slot_label.place(x=0, y=0, width=59, height=ROW_HEIGHT)
            status_label.place(x=60, y=0, width=93, height=ROW_HEIGHT)
            sn_label.place(x=154, y=0, width=188, height=ROW_HEIGHT)
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
        # Carbon may invoke this callback outside Tk's event dispatch.  Queue
        # the request and let _drain_events call Tk only on its own loop.
        self.hotkey_events.put(True)

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
            final = configured_directory(values["final"].get())
            if final is None:
                messagebox.showerror("路徑錯誤", "請選擇可讀取的 BT TestData 根路徑。", parent=self.root)
                return
            caseinfo_text = values["caseinfo"].get().strip()
            caseinfo = configured_directory(caseinfo_text) if caseinfo_text else None
            if caseinfo_text and caseinfo is None:
                messagebox.showerror("路徑錯誤", "BT CaseInfo 路徑不存在或無法讀取。", parent=self.root)
                return
        else:
            active = configured_directory(values["active"].get())
            final = configured_directory(values["final"].get())
            if active is None or final is None:
                messagebox.showerror("路徑錯誤", "請同時選擇 active 與最終結果根路徑。", parent=self.root)
                return
        self.start_button.configure(state="disabled")
        self.monitor_state.configure(text="啟動中")
        self.root.update_idletasks()
        try:
            if station == "BT":
                monitor = BtLogMonitor(final, (1, 2, 3, 4), caseinfo_root=caseinfo, callback=self.events.put)
            else:
                monitor = AtlasActiveArchiveMonitor(
                    station, active, final, tuple(range(1, slot_count(station) + 1)), callback=self.events.put,
                )
            self._save_preferences()
            self._reset_rows()
            monitor.start()
            self.monitor = monitor
        except Exception as error:
            self.monitor = None
            self._set_monitor_controls(False)
            message = "無法開始監控：{}".format(error)
            self._log(message)
            messagebox.showerror("監控啟動失敗", message, parent=self.root)
            return
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
        try:
            while True:
                self.hotkey_events.get_nowait()
                self._start_from_hotkey()
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
        dialog.configure(background=LIGHT_BACKGROUND)
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
        shortcut = "Command+Shift+M\n{}".format(self.hotkey.message)
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
        self.settings_log = tk.Text(parent, wrap="word", state="disabled", height=26,
                                    background=FIELD_BACKGROUND, foreground=TEXT_COLOUR,
                                    insertbackground=TEXT_COLOUR, selectbackground="#dbeafe",
                                    selectforeground=TEXT_COLOUR)
        self.settings_log.pack(fill="both", expand=True)
        self.settings_log.configure(state="normal")
        self.settings_log.insert("1.0", "\n".join(self.event_lines))
        self.settings_log.configure(state="disabled")

    def _save_settings(self) -> None:
        self.station.set(self.settings_station.get())
        for station, fields in self.settings_paths.items():
            for field, variable in fields.items():
                self.paths[station][field].set(variable.get())
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
