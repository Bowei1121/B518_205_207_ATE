"""B518 Log Solution — local-only KVM-friendly desktop monitor."""

from __future__ import annotations

import os
import queue
import sys
import subprocess
import time
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Dict, Optional

from global_hotkey import HotkeyRegistration, create_global_hotkey
from log_monitoring import DEFAULT_TIMEOUTS, AtlasActiveArchiveMonitor, BtLogMonitor, MonitorEvent
from monitoring_round import RoundCoordinator, RoundEvent
from configured_monitor import ConfiguredMonitor
from machine_profiles import (
    MachineProfile, MachineProfileStore, ProfileError,
)
from rswmt_monitoring import RsWmtLogMonitor


APP_ROOT = Path.home() / "Library" / "Application Support" / "B518LogSolution"
PREFS_PATH = APP_ROOT / "preferences.json"
ASSETS_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1])) / "assets"
COMPANY_LOGO_PATH = ASSETS_ROOT / "foxlink_logo.png"
LIGHT_BACKGROUND = "#f3f4f6"
FIELD_BACKGROUND = "#ffffff"
TEXT_COLOUR = "#111827"
MUTED_TEXT_COLOUR = "#555555"
STATION_SLOTS = {"DFU": 7, "FCT": 6, "BT": 4}
WINDOW_HEIGHTS = {"DFU": 642, "FCT": 595, "BT": 501}
WINDOW_WIDTH = 360
MAIN_FONT_SIZE = 14
ROW_HEIGHT = 46
ROW_GAP = 1
ROW_WIDTH = 342
STATUS_TEMPLATE_STATES = ("PASS", "FAIL", "TESTING", "NOTEST")
STATUS_COLOURS = {
    "PASS": "#00ef00", "FAIL": "#ff0000", "TESTING": "#ffff00", "NOTEST": "#f04bf1",
    "WAITING": "#d9d9d9", "COMPLETING": "#82c7ff", "STALLED": "#ff9900", "STOPPED": "#bfbfbf",
    "TIMEOUT": "#ff9900",
}
UNAVAILABLE_COLOUR = "#000000"
KVM_BLOCK_COUNT = 7


def slot_count(station: str) -> int:
    return STATION_SLOTS.get(station.upper(), STATION_SLOTS["FCT"])


def window_height(station: str) -> int:
    return WINDOW_HEIGHTS.get(station.upper(), WINDOW_HEIGHTS["FCT"])


def kvm_block_colour(station: str, slot: int, status: str) -> str:
    """Return the no-text KVM result colour for one fixed slot position."""
    if slot > slot_count(station):
        return UNAVAILABLE_COLOUR
    return STATUS_COLOURS.get(status, STATUS_COLOURS["WAITING"])


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
        return path if path.is_dir() and os.access(str(path), os.R_OK | os.X_OK) else None
    except OSError:
        return None


class B518LogSolutionApp:
    def __init__(self, root: tk.Tk, hotkey_factory=create_global_hotkey):
        self.root = root
        self.root.title("B518 Log Solution-V0.1.0")
        self.root.resizable(False, False)
        self.events: queue.Queue[RoundEvent] = queue.Queue()
        self.hotkey_events: queue.Queue[bool] = queue.Queue()
        self.rounds = RoundCoordinator(self.events.put)
        self.active_round_id: Optional[str] = None
        self.monitor = None
        self.prefs = {}
        self.profile_store = MachineProfileStore(PREFS_PATH)
        self.profiles, selected_project, selected_machine, self.profile_error = self.profile_store.load()
        self.project = tk.StringVar(value=selected_project)
        self.station = tk.StringVar(value=selected_machine)
        self.bt_format = tk.StringVar(value="B518 RS-WMT" if self._profile_platform() == "rswmt"
                                      else "B482 TestData")
        self.paths = {name: {field: tk.StringVar(value=self.prefs.get("paths", {}).get(name, {}).get(field, ""))
                             for field in ("active", "final", "caseinfo")}
                      for name in STATION_SLOTS}
        self.timeouts = {name: {field: tk.StringVar(value=str(self._stored_timeout(name, field)))
                                for field in ("start", "test", "round")}
                         for name in STATION_SLOTS}
        self._load_selected_profile_values()
        self.status_rows: Dict[int, Dict[str, tk.Label]] = {}
        self.template_labels: Dict[str, tk.Label] = {}
        self.kvm_result_blocks: Dict[int, tk.Label] = {}
        self.company_logo: Optional[tk.PhotoImage] = None
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
        self._build_company_identity(header)
        self.station_title = tk.Label(header, background=LIGHT_BACKGROUND, foreground=TEXT_COLOUR,
                                      font=("Helvetica", MAIN_FONT_SIZE, "bold"))
        self.station_title.pack(side="left", expand=True)
        self.monitor_state = tk.Label(header, background=LIGHT_BACKGROUND, foreground=MUTED_TEXT_COLOUR,
                                      font=("Helvetica", MAIN_FONT_SIZE, "bold"))
        self.monitor_state.pack(side="right")

        selection = tk.Frame(body, background=LIGHT_BACKGROUND)
        selection.pack(fill="x", pady=(4, 3))
        ttk.Label(selection, text="專案").pack(side="left")
        self.project_choice = ttk.Combobox(selection, textvariable=self.project, state="readonly", width=10,
                                           values=self.profiles.projects)
        self.project_choice.pack(side="left", padx=(5, 12))
        self.project_choice.bind("<<ComboboxSelected>>", self._project_changed)
        ttk.Label(selection, text="機型").pack(side="left")
        self.machine_choice = ttk.Combobox(selection, textvariable=self.station, state="readonly", width=8)
        self.machine_choice.pack(side="left", padx=(5, 0))
        self.machine_choice.bind("<<ComboboxSelected>>", self._profile_changed)
        self._refresh_machine_choices()

        kvm_results = tk.Frame(body, background=LIGHT_BACKGROUND, height=48)
        kvm_results.pack(fill="x", pady=(2, 4))
        kvm_results.pack_propagate(False)
        tk.Label(kvm_results, text="KVM RESULT", background=LIGHT_BACKGROUND, foreground=TEXT_COLOUR,
                 font=("Helvetica", 10, "bold"), anchor="w").place(x=0, y=0, width=80, height=16)
        self._build_kvm_locator(kvm_results, 82, 2, mirrored=False)
        self._build_kvm_locator(kvm_results, 320, 2, mirrored=True)
        for slot in range(1, KVM_BLOCK_COUNT + 1):
            block = tk.Label(kvm_results, text="", background=STATUS_COLOURS["WAITING"], relief="solid", borderwidth=1)
            block.place(x=(slot - 1) * 49, y=20, width=47, height=26)
            self.kvm_result_blocks[slot] = block

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

    def _build_company_identity(self, parent: tk.Widget) -> None:
        """Show the supplied company asset when deployed, with a readable fallback."""
        if COMPANY_LOGO_PATH.is_file():
            try:
                self.company_logo = tk.PhotoImage(file=str(COMPANY_LOGO_PATH))
            except tk.TclError:
                self.company_logo = None
        if self.company_logo:
            tk.Label(parent, image=self.company_logo, background=LIGHT_BACKGROUND).pack(side="left", padx=(8, 4))
        else:
            tk.Label(parent, text="B518 LOG", background=LIGHT_BACKGROUND, foreground=MUTED_TEXT_COLOUR,
                     font=("Helvetica", 10, "bold")).pack(side="left", padx=(8, 4))

    @staticmethod
    def _build_kvm_locator(parent: tk.Widget, x: int, y: int, mirrored: bool) -> None:
        """Two asymmetric black/white marks let image analysis lock orientation and scale."""
        marker = tk.Frame(parent, background="#000000", width=14, height=14)
        marker.place(x=x, y=y, width=14, height=14)
        inset_x = 2 if not mirrored else 6
        inset_y = 2 if not mirrored else 6
        tk.Frame(marker, background="#ffffff", width=6, height=6).place(x=inset_x, y=inset_y, width=6, height=6)

    def _set_kvm_result_block(self, slot: int, status: str) -> None:
        block = self.kvm_result_blocks.get(slot)
        if not block:
            return
        block.configure(background=kvm_block_colour(self.station.get(), slot, status))

    def _render_rows(self) -> None:
        for child in self.rows_box.winfo_children():
            child.destroy()
        self.status_rows = {}
        station = self.station.get().upper()
        try:
            row_count = self._selected_profile().capacity
        except (AttributeError, ProfileError):
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
        for slot in range(1, KVM_BLOCK_COUNT + 1):
            self._set_kvm_result_block(slot, "WAITING")
        self._position_window()

    def _position_window(self) -> None:
        self.root.update_idletasks()
        width, height = WINDOW_WIDTH, window_height(self.station.get())
        x = max(self.root.winfo_screenwidth() - width - 12, 0)
        self.root.geometry("{}x{}+{}+32".format(width, height, x))

    def _selected_profile(self) -> MachineProfile:
        if self.profile_error:
            raise ProfileError(self.profile_error)
        return self.profiles.get(self.project.get(), self.station.get())

    def _profile_platform(self) -> str:
        try:
            return self.profiles.get(self.project.get(), self.station.get()).platform
        except (AttributeError, ProfileError):
            return "atlas" if self.station.get() in {"DFU", "FCT"} else "b482"

    def _load_selected_profile_values(self) -> None:
        try:
            profile = self.profiles.get(self.project.get(), self.station.get())
        except (AttributeError, ProfileError):
            return
        for field, value in profile.paths.items():
            if field in self.paths[profile.machine]:
                self.paths[profile.machine][field].set(value)
        for field in ("start", "test"):
            self.timeouts[profile.machine][field].set(str(profile.timeouts[field]))
        self.bt_format.set("B518 RS-WMT" if profile.platform == "rswmt" else "B482 TestData")

    def _refresh_machine_choices(self) -> None:
        available = self.profiles.for_project(self.project.get())
        machines = tuple(profile.machine for profile in available)
        self.machine_choice.configure(values=machines)
        if self.station.get() not in machines and machines:
            self.station.set(machines[0])
        self._load_selected_profile_values()

    def _project_changed(self, _event=None) -> None:
        if self.profile_error and self.profile_error.startswith("已保存的專案與機型選擇"):
            self.profile_error = None
        self._refresh_machine_choices()
        self._render_rows()

    def _profile_changed(self, _event=None) -> None:
        if self.profile_error and self.profile_error.startswith("已保存的專案與機型選擇"):
            self.profile_error = None
        self._load_selected_profile_values()
        self.bt_format.set("B518 RS-WMT" if self._profile_platform() == "rswmt" else "B482 TestData")
        self._render_rows()

    def _stored_timeout(self, station: str, field: str) -> int:
        default = DEFAULT_TIMEOUTS.get(station, DEFAULT_TIMEOUTS["FCT"]).get(field, 7200)
        value = self.prefs.get("timeouts", {}).get(station, {}).get(field, default)
        try:
            value = int(value)
        except (TypeError, ValueError):
            return default
        return value if value > 0 else default

    def _timeout_seconds(self, station: str, values: Optional[Dict[str, Dict[str, tk.StringVar]]] = None) -> Dict[str, int]:
        variables = (values or self.timeouts)[station]
        result = {}
        for field, label in (("start", "等待開始測試逾時"), ("test", "測試時間上限"),
                             ("round", "整輪監控上限")):
            try:
                raw_value = variables[field].get().strip()
                missing_value = False
            except KeyError:
                raw_value = ""
                missing_value = True
            if field == "round" and missing_value:
                try:
                    if values is self.settings_timeouts:
                        configured = self.profiles.get(self.settings_project.get(), station)
                    else:
                        configured = self.profiles.get(self.project.get(), station)
                    raw_value = str(configured.timeouts[field])
                except (AttributeError, KeyError, ProfileError):
                    raw_value = "7200"
            try:
                value = int(raw_value)
            except ValueError:
                value = 0
            if value <= 0:
                raise ValueError("{}必須是正整數秒數。".format(label))
            result[field] = value
        return result

    def _save_preferences(self) -> None:
        if self.profile_error:
            raise ProfileError(self.profile_error)
        self.profile_store.save(
            self.profiles, self.project.get(), self.station.get(),
            preserve_legacy=self.profile_store.migration_required,
        )

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

    def _set_monitor_controls(self, monitoring: bool, state_text: Optional[str] = None) -> None:
        self.start_button.configure(state="disabled" if monitoring else "normal")
        self.stop_button.configure(state="normal" if monitoring else "disabled")
        self.monitor_state.configure(text=state_text or ("監控中" if monitoring else "待命"))
        for name in ("project_choice", "machine_choice"):
            choice = getattr(self, name, None)
            if choice:
                choice.configure(state="disabled" if monitoring else "readonly")

    def _set_row(self, slot: int, sn: str, status: str) -> None:
        widgets = self.status_rows.get(slot)
        if not widgets:
            return
        status = status if status in STATUS_COLOURS else "WAITING"
        widgets["status"].configure(text=status, background=STATUS_COLOURS[status])
        widgets["sn"].configure(text=sn, font=("Menlo", sn_font_size(sn), "bold"))
        self._set_kvm_result_block(slot, status)

    def _reset_rows(self) -> None:
        for slot in self.status_rows:
            self._set_row(slot, "", "WAITING")

    def start_monitor(self) -> None:
        current = self.rounds.snapshot()
        if current is not None and current.state == "RUNNING":
            return
        station = self.station.get().upper()
        values = self.paths[station]
        try:
            profile = self._selected_profile()
        except (AttributeError, ProfileError) as error:
            if hasattr(self, "profiles"):
                messagebox.showerror("配置錯誤", str(error), parent=self.root)
                return
            profile = None
        try:
            timeouts = self._timeout_seconds(station)
        except ValueError as error:
            messagebox.showerror("逾時設定錯誤", str(error), parent=self.root)
            return
        platform = profile.platform if profile else (
            "rswmt" if station == "BT" and self.bt_format.get() == "B518 RS-WMT"
            else ("b482" if station == "BT" else "atlas")
        )
        if platform == "atlas":
            active = configured_directory(values["active"].get())
            final = configured_directory(values["final"].get())
            if active is None or final is None:
                messagebox.showerror("路徑錯誤", "請設定存在且可讀取的 active 與最終結果路徑。", parent=self.root)
                return
            caseinfo = None
        else:
            final = configured_directory(values["final"].get())
            if final is None:
                messagebox.showerror("路徑錯誤", "請設定存在且可讀取的結果根路徑。", parent=self.root)
                return
            optional_field = "caseinfo"
            optional_value = values[optional_field].get()
            caseinfo_text = optional_value.strip()
            caseinfo = configured_directory(caseinfo_text) if caseinfo_text else None
            if caseinfo_text and caseinfo is None:
                messagebox.showerror("路徑錯誤", "即時 Log 路徑不存在或無法讀取。", parent=self.root)
                return
        if profile and profile.capacity > slot_count(station):
            messagebox.showerror("配置不相容", "目前 {} Adapter／畫面支援容量上限為 {}。".format(
                station, slot_count(station)), parent=self.root)
            return
        self.start_button.configure(state="disabled")
        self.monitor_state.configure(text="啟動中")
        self.root.update_idletasks()
        round_started_monotonic = time.monotonic()
        try:
            def monitor_factory(on_event):
                capacity = profile.capacity if profile else slot_count(station)
                mapping = dict(profile.mapping) if profile else {slot: slot for slot in range(1, capacity + 1)}
                source_slots = tuple(mapping)
                view_holder = {}

                def deliver(event):
                    view = view_holder.get("view")
                    if view is not None:
                        view.deliver(event, on_event)
                    else:
                        on_event(event)

                if platform == "rswmt":
                    monitor = RsWmtLogMonitor(
                        final, slots=source_slots, progress_root=caseinfo, callback=deliver,
                        start_timeout_seconds=timeouts["start"], test_timeout_seconds=timeouts["test"],
                        round_timeout_seconds=timeouts["round"],
                        round_started_monotonic=round_started_monotonic,
                    )
                elif platform == "b482":
                    monitor = BtLogMonitor(
                        final, source_slots, caseinfo_root=caseinfo, callback=deliver,
                        start_timeout_seconds=timeouts["start"], test_timeout_seconds=timeouts["test"],
                        round_timeout_seconds=timeouts["round"],
                        round_started_monotonic=round_started_monotonic,
                    )
                elif platform == "atlas":
                    monitor = AtlasActiveArchiveMonitor(
                        station, active, final, source_slots, callback=deliver,
                        start_timeout_seconds=timeouts["start"], test_timeout_seconds=timeouts["test"],
                        round_timeout_seconds=timeouts["round"],
                        round_started_monotonic=round_started_monotonic,
                    )
                else:
                    raise ValueError("未知平台：{}。".format(platform))
                configured = ConfiguredMonitor(monitor, mapping)
                if profile:
                    monitor.session.update_settings({
                        "profile_snapshot": {
                            "schema_version": 1,
                            "profile": profile.to_dict(),
                        },
                    })
                view_holder["view"] = configured
                return configured

            self._save_preferences()
            self._reset_rows()
            snapshot = self.rounds.start(station, monitor_factory)
            self.active_round_id = snapshot.round_id
            self.monitor = self.rounds.monitor
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
            self.rounds.stop()

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

    def _bring_dashboard_to_front(self) -> None:
        """Show the completed-result board without keeping it permanently on top."""
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        except tk.TclError as error:
            self._log("無法將結果看板帶到前景：{}".format(error))

    def _handle_event(self, event: MonitorEvent) -> None:
        if isinstance(event, RoundEvent):
            if event.round_id != self.active_round_id:
                return
            event = event.event
        self._log(event.message)
        snapshot = self.rounds.snapshot() if hasattr(self, "rounds") else None
        if event.slot and snapshot:
            result = next((item for item in snapshot.results if item.slot == event.slot), None)
            if result is not None:
                self._set_row(event.slot, result.sn, result.status)
        elif event.slot and self.monitor and event.slot in self.monitor.results:
            result = self.monitor.results[event.slot]
            self._set_row(event.slot, result.sn, result.status)
        if event.kind == "result" and event.status in {"PASS", "FAIL", "NOTEST"}:
            self._bring_dashboard_to_front()
        if event.kind == "review" and self.monitor:
            choice = messagebox.askyesno("BT 人工覆核", event.message + "\n\n是否接受新檔案？", parent=self.root)
            self.monitor.resolve_review("accept" if choice else "reject")
        if event.kind == "timeout" and event.detail.get("kind") == "start":
            self.monitor = None
            self._set_monitor_controls(False, "逾時停止")
        if event.kind == "timeout" and event.detail.get("kind") == "round":
            self.monitor = None
            self._set_monitor_controls(False, "逾時停止")
            messagebox.showwarning("整輪監控逾時", event.message + "\n\n已停止讀取來源並保留本輪結果。",
                                   parent=self.root)
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
        self.settings_project = tk.StringVar(value=self.project.get())
        self.settings_bt_format = tk.StringVar(value=self.bt_format.get())
        self.settings_paths = {station: {field: tk.StringVar(value=value.get()) for field, value in fields.items()}
                               for station, fields in self.paths.items()}
        self.settings_timeouts = {station: {field: tk.StringVar(value=value.get()) for field, value in fields.items()}
                                  for station, fields in self.timeouts.items()}
        ttk.Label(parent, text="工站").grid(row=0, column=0, sticky="w")
        state = "disabled" if self.monitor else "readonly"
        station_choice = ttk.Combobox(parent, values=tuple(STATION_SLOTS), textvariable=self.settings_station, state=state, width=14)
        station_choice.grid(row=0, column=1, sticky="w", padx=(8, 0))
        station_choice.bind("<<ComboboxSelected>>", self._settings_profile_changed)
        ttk.Label(parent, text="專案").grid(row=0, column=2, sticky="w", padx=(16, 0))
        self.settings_project_choice = ttk.Combobox(
            parent, values=self.profiles.projects, textvariable=self.settings_project,
            state="readonly", width=12,
        )
        self.settings_project_choice.grid(row=0, column=3, sticky="w", padx=(8, 0))
        self.settings_project_choice.bind("<<ComboboxSelected>>", self._settings_profile_changed)
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
        offset = 0
        if station == "BT":
            ttk.Label(self.settings_paths_box, text="BT 格式 / Format").grid(row=0, column=0, sticky="w")
            choice = ttk.Combobox(self.settings_paths_box, textvariable=self.settings_bt_format,
                                  values=("B482 TestData", "B518 RS-WMT"),
                                  state="disabled" if disabled else "readonly", width=24)
            choice.grid(row=0, column=1, sticky="w", padx=8, pady=5)
            choice.bind("<<ComboboxSelected>>", self._bt_format_changed)
            offset = 1
            if self.settings_bt_format.get() == "B518 RS-WMT":
                schema = (("final", "RS-WMT output/SmtCal"), ("caseinfo", "Live logs（選填 / optional）"))
        for row, (field, label) in enumerate(schema, offset):
            ttk.Label(self.settings_paths_box, text=label).grid(row=row, column=0, sticky="w", pady=5)
            entry = ttk.Entry(self.settings_paths_box, textvariable=self.settings_paths[station][field], width=62,
                              state="disabled" if disabled else "normal")
            entry.grid(row=row, column=1, sticky="ew", padx=8, pady=5)
            ttk.Button(self.settings_paths_box, text="選擇", state="disabled" if disabled else "normal",
                       command=lambda current=field: self._choose_setting_path(current)).grid(row=row, column=2, pady=5)
        timeout_row = len(schema) + offset
        for offset, (field, label) in enumerate((
                ("start", "等待開始測試逾時（秒）"), ("test", "測試時間上限（秒）"),
                ("round", "整輪監控上限（秒）"))):
            ttk.Label(self.settings_paths_box, text=label).grid(row=timeout_row + offset, column=0, sticky="w", pady=5)
            ttk.Entry(self.settings_paths_box, textvariable=self.settings_timeouts[station][field], width=16,
                      state="disabled" if disabled else "normal").grid(row=timeout_row + offset, column=1, sticky="w", padx=8, pady=5)
        self.settings_paths_box.columnconfigure(1, weight=1)

    def _settings_profile_changed(self, _event=None) -> None:
        machine = self.settings_station.get()
        project = self.settings_project.get()
        try:
            profile = self.profiles.get(project, machine)
        except ProfileError:
            candidates = self.profiles.for_project(project)
            if not candidates:
                candidates = tuple(item for item in self.profiles.profiles if item.machine == machine)
            if not candidates:
                return
            profile = candidates[0]
            self.settings_project.set(profile.project)
            self.settings_station.set(profile.machine)
        for field, value in profile.paths.items():
            if field in self.settings_paths[profile.machine]:
                self.settings_paths[profile.machine][field].set(value)
        for field in ("start", "test", "round"):
            self.settings_timeouts[profile.machine][field].set(str(profile.timeouts[field]))
        self.settings_bt_format.set("B518 RS-WMT" if profile.platform == "rswmt" else "B482 TestData")
        self._render_setting_paths()

    def _bt_format_changed(self, _event=None) -> None:
        if self.settings_bt_format.get() == "B518 RS-WMT":
            self.settings_project.set("B518")
        else:
            self.settings_project.set("B482")
        if self.settings_bt_format.get() == "B518 RS-WMT" and self.settings_timeouts["BT"]["start"].get() == "30":
            # Archived output may first appear only when the ~90 s test finishes.
            self.settings_timeouts["BT"]["start"].set("240")
        self._render_setting_paths()

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
        if self.profile_error:
            messagebox.showerror("配置錯誤", self.profile_error, parent=self.settings_window)
            return
        try:
            for station in STATION_SLOTS:
                self._timeout_seconds(station, self.settings_timeouts)
        except ValueError as error:
            messagebox.showerror("逾時設定錯誤", str(error), parent=self.settings_window)
            return
        machine = self.settings_station.get()
        project = self.settings_project.get()
        if machine == "BT":
            project = "B518" if self.settings_bt_format.get() == "B518 RS-WMT" else "B482"
        try:
            profile = self.profiles.get(project, machine)
        except ProfileError as error:
            messagebox.showerror("配置錯誤", str(error), parent=self.settings_window)
            return
        profile_paths = dict(profile.paths)
        for station, fields in self.settings_paths.items():
            if station == machine:
                profile_paths.update({field: variable.get() for field, variable in fields.items()
                                      if field in profile_paths})
        profile_timeouts = dict(profile.timeouts)
        profile_timeouts.update(self._timeout_seconds(machine, self.settings_timeouts))
        updated = replace(profile, paths=profile_paths, timeouts=profile_timeouts)
        updated_catalog = self.profiles.with_profile(updated)
        try:
            self.profile_store.save(
                updated_catalog, project, machine,
                preserve_legacy=self.profile_store.migration_required,
            )
        except OSError as error:
            messagebox.showerror("設定儲存失敗", "配置未變更：{}".format(error), parent=self.settings_window)
            return
        self.profiles = updated_catalog
        self.project.set(project)
        self.station.set(machine)
        self._refresh_machine_choices()
        for field, variable in self.settings_paths[machine].items():
            self.paths[machine][field].set(variable.get())
        for field, variable in self.settings_timeouts[machine].items():
            self.timeouts[machine][field].set(variable.get())
        self.bt_format.set("B518 RS-WMT" if updated.platform == "rswmt" else "B482 TestData")
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
            self.rounds.stop()
        try:
            self._save_preferences()
        except (OSError, ProfileError) as error:
            messagebox.showerror("偏好儲存失敗", str(error), parent=self.root)
        self.root.destroy()


if __name__ == "__main__":
    window = tk.Tk()
    B518LogSolutionApp(window)
    window.mainloop()
