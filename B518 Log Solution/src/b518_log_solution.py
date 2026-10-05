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
from log_monitoring import DEFAULT_TIMEOUTS, MonitorEvent
from monitoring_round import RoundCoordinator, RoundEvent
from configured_monitor import ConfiguredMonitor
from machine_profiles import (
    MachineProfile, MachineProfileStore, ProfileError, profile_from_editor_fields,
)
from platform_registry import DEFAULT_PLATFORM_REGISTRY
from kvm_display_contract import (
    KVM_CELL_HEIGHT, KVM_CELL_STEP, KVM_CELL_WIDTH, KVM_COLUMN_COUNT,
    KVM_FIRST_ROW_Y, KVM_ROW_STEP,
    LOCATOR_FAR_INSET, LOCATOR_LEFT, LOCATOR_NEAR_INSET, LOCATOR_RIGHT,
    LOCATOR_SIZE, LOCATOR_WHITE_SIZE, MARKER_CELL_GAP, MARKER_CELL_SIZE,
    MARKER_PATTERNS, MARKER_QUIET_ZONE, MARKER_SIZE, MarkerState,
    STATE_MARKER_ORIGIN, state_for_round_snapshot,
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
WINDOW_WIDTH = 376
MAIN_FONT_SIZE = 14
ROW_HEIGHT = 46
ROW_GAP = 1
ROW_WIDTH = 342
KVM_BAND_HEIGHT = 88
KVM_SINGLE_ROW_HEIGHT = 61
DETAIL_ROWS_VISIBLE = 7
WINDOW_FIXED_HEIGHT = 353
STATUS_TEMPLATE_STATES = ("PASS", "FAIL", "TESTING", "NOTEST")
STATUS_COLOURS = {
    "PASS": "#00ef00", "FAIL": "#ff0000", "TESTING": "#ffff00", "NOTEST": "#f04bf1",
    "WAITING": "#d9d9d9", "COMPLETING": "#82c7ff", "STALLED": "#ff9900", "STOPPED": "#bfbfbf",
    "TIMEOUT": "#ff9900",
}
UNAVAILABLE_COLOUR = "#000000"
KVM_BLOCK_COUNT = 20


def slot_count(station: str) -> int:
    return STATION_SLOTS.get(station.upper(), STATION_SLOTS["FCT"])


def visible_detail_rows(capacity: int, screen_height: int) -> int:
    fixed_height = WINDOW_FIXED_HEIGHT if capacity > KVM_COLUMN_COUNT else WINDOW_FIXED_HEIGHT - 27
    screen_limit = max(1, (screen_height - 64 - fixed_height) // (ROW_HEIGHT + ROW_GAP))
    return min(max(1, capacity), DETAIL_ROWS_VISIBLE, screen_limit)


def window_height(capacity: int, screen_height: int = 900) -> int:
    fixed_height = WINDOW_FIXED_HEIGHT if capacity > KVM_COLUMN_COUNT else WINDOW_FIXED_HEIGHT - 27
    return fixed_height + visible_detail_rows(capacity, screen_height) * (ROW_HEIGHT + ROW_GAP)


def kvm_block_colour(capacity: int, slot: int, status: str) -> str:
    """Return the no-text KVM result colour for one fixed slot position."""
    if slot > capacity:
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
    def __init__(self, root: tk.Tk, hotkey_factory=create_global_hotkey,
                 session_root: Optional[Path] = None):
        self.root = root
        self.session_root = Path(session_root) if session_root else APP_ROOT / "sessions"
        self.root.title("B518 Log Solution-V0.1.0")
        self.root.resizable(False, False)
        self.events: queue.Queue[RoundEvent] = queue.Queue()
        self.hotkey_events: queue.Queue[bool] = queue.Queue()
        self.rounds = RoundCoordinator(self.events.put, audit_root=self.session_root)
        self.active_round_id: Optional[str] = None
        self.monitor = None
        self.active_profile_snapshot: Optional[MachineProfile] = None
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
        self._rendered_marker_state: Optional[MarkerState] = None
        self.company_logo: Optional[tk.PhotoImage] = None
        self.event_lines: list[str] = []
        self.settings_window: Optional[tk.Toplevel] = None
        self.settings_log: Optional[tk.Text] = None
        self.conflict_window: Optional[tk.Toplevel] = None
        self.conflict_list: Optional[tk.Listbox] = None
        self.conflict_details: Optional[tk.Text] = None
        self._conflict_ids: list[str] = []
        self.round_alarm_window: Optional[tk.Toplevel] = None
        self.round_alarm_message: Optional[ttk.Label] = None
        self.round_alarm_ack_button: Optional[ttk.Button] = None
        self._round_alarm_window_identity: Optional[tuple[str, str]] = None
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
        self.review_button = ttk.Button(header, text="待確認", command=self._open_conflict_review,
                                        state="disabled")
        self.review_button.pack(side="right", padx=(0, 10))
        self.round_alarm_button = ttk.Button(header, text="整輪警報", command=self._open_round_alarm,
                                             state="disabled")
        self.round_alarm_button.pack(side="right", padx=(0, 10))
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

        self.kvm_results = tk.Frame(body, background=LIGHT_BACKGROUND, height=KVM_BAND_HEIGHT)
        self.kvm_results.pack(fill="x", pady=(2, 4))
        self.kvm_results.pack_propagate(False)
        tk.Label(self.kvm_results, text="KVM RESULT", background=LIGHT_BACKGROUND, foreground=TEXT_COLOUR,
                 font=("Helvetica", 10, "bold"), anchor="w").place(x=0, y=0, width=80, height=16)
        self._build_kvm_locator(self.kvm_results, *LOCATOR_LEFT, mirrored=False)
        self._build_kvm_locator(self.kvm_results, *LOCATOR_RIGHT, mirrored=True)
        self.kvm_state_marker = tk.Canvas(
            self.kvm_results, width=MARKER_SIZE, height=MARKER_SIZE,
            background="#ffffff", highlightthickness=0, borderwidth=0,
        )
        self.kvm_state_marker.place(x=STATE_MARKER_ORIGIN[0], y=STATE_MARKER_ORIGIN[1],
                                    width=MARKER_SIZE, height=MARKER_SIZE)
        self._render_state_marker(None)
        for slot in range(1, KVM_BLOCK_COUNT + 1):
            block = tk.Label(self.kvm_results, text="", background=STATUS_COLOURS["WAITING"], relief="solid", borderwidth=1)
            row = (slot - 1) // KVM_COLUMN_COUNT
            column = (slot - 1) % KVM_COLUMN_COUNT
            block.place(x=column * KVM_CELL_STEP, y=KVM_FIRST_ROW_Y + row * KVM_ROW_STEP,
                        width=KVM_CELL_WIDTH, height=KVM_CELL_HEIGHT)
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

        self.rows_panel = tk.Frame(body, background=LIGHT_BACKGROUND)
        self.rows_panel.pack(fill="both", expand=True)
        self.rows_canvas = tk.Canvas(
            self.rows_panel, background="#111111", highlightthickness=1,
            highlightbackground="#111111", borderwidth=0, width=ROW_WIDTH + 2, height=1,
        )
        self.rows_scrollbar = ttk.Scrollbar(self.rows_panel, orient="vertical", command=self.rows_canvas.yview)
        self.rows_canvas.configure(yscrollcommand=self.rows_scrollbar.set)
        self.rows_canvas.pack(side="left", fill="both", expand=True)
        self.rows_scrollbar.pack(side="right", fill="y")
        self.rows_box = tk.Frame(self.rows_canvas, background="#111111", width=ROW_WIDTH + 2, height=1)
        self.rows_canvas_window = self.rows_canvas.create_window((0, 0), anchor="nw", window=self.rows_box)
        self.rows_box.bind("<Configure>", self._update_rows_scroll_region)
        self.rows_canvas.bind("<Configure>", self._resize_rows_content)
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
        marker = tk.Frame(parent, background="#000000", width=LOCATOR_SIZE, height=LOCATOR_SIZE)
        marker.place(x=x, y=y, width=LOCATOR_SIZE, height=LOCATOR_SIZE)
        inset = LOCATOR_FAR_INSET if mirrored else LOCATOR_NEAR_INSET
        tk.Frame(marker, background="#ffffff", width=LOCATOR_WHITE_SIZE,
                 height=LOCATOR_WHITE_SIZE).place(
            x=inset, y=inset, width=LOCATOR_WHITE_SIZE, height=LOCATOR_WHITE_SIZE)

    def _render_state_marker(self, snapshot) -> MarkerState:
        """Draw the machine marker and product band from the same round snapshot."""
        state = state_for_round_snapshot(snapshot)
        if state == getattr(self, "_rendered_marker_state", None):
            return state
        marker = getattr(self, "kvm_state_marker", None)
        if marker is None:
            self._rendered_marker_state = state
            return state
        pattern = MARKER_PATTERNS[state]
        marker.delete("marker")
        for row in range(2):
            for column in range(2):
                x = MARKER_QUIET_ZONE + column * (MARKER_CELL_SIZE + MARKER_CELL_GAP)
                y = MARKER_QUIET_ZONE + row * (MARKER_CELL_SIZE + MARKER_CELL_GAP)
                colour = "#000000" if pattern[row][column] else "#ffffff"
                marker.create_rectangle(
                    x, y, x + MARKER_CELL_SIZE, y + MARKER_CELL_SIZE,
                    fill=colour, outline=colour, tags=("marker", "marker-cell"),
                )
        self._rendered_marker_state = state
        return state

    def _apply_round_snapshot(self, snapshot) -> None:
        """Atomically render one current-round snapshot to cells and marker."""
        if snapshot is None or snapshot.round_id != self.active_round_id:
            return
        if not snapshot.audit_complete and snapshot.audit_errors:
            reported = getattr(self, "_reported_audit_errors", set())
            for error in snapshot.audit_errors:
                if error not in reported:
                    self._log("稽核紀錄不完整：{}".format(error))
                    reported.add(error)
            self._reported_audit_errors = reported
        for result in snapshot.results:
            self._set_row(result.slot, result.sn, result.status)
        self._render_state_marker(snapshot)

    def _set_kvm_result_block(self, slot: int, status: str) -> None:
        block = self.kvm_result_blocks.get(slot)
        if not block:
            return
        block.configure(background=kvm_block_colour(self._display_capacity(), slot, status))

    def _display_capacity(self) -> int:
        if self.monitor is not None and self.active_profile_snapshot is not None:
            return self.active_profile_snapshot.capacity
        try:
            return self._selected_profile().capacity
        except (AttributeError, ProfileError):
            return slot_count(self.station.get())

    def _update_rows_scroll_region(self, _event=None) -> None:
        self.rows_canvas.configure(scrollregion=self.rows_canvas.bbox("all"))

    def _resize_rows_content(self, event) -> None:
        self.rows_canvas.itemconfigure(self.rows_canvas_window, width=event.width)

    def _render_rows(self) -> None:
        for child in self.rows_box.winfo_children():
            child.destroy()
        self.status_rows = {}
        station = self.station.get().upper()
        row_count = self._display_capacity()
        screen_height = self.root.winfo_screenheight()
        visible_rows = visible_detail_rows(row_count, screen_height)
        has_second_kvm_row = row_count > KVM_COLUMN_COUNT
        self.kvm_results.configure(height=KVM_BAND_HEIGHT if has_second_kvm_row
                                   else KVM_SINGLE_ROW_HEIGHT)
        self.rows_canvas.configure(height=visible_rows * (ROW_HEIGHT + ROW_GAP))
        self.rows_box.configure(height=row_count * (ROW_HEIGHT + ROW_GAP), width=ROW_WIDTH + 2)
        self.rows_scrollbar.pack_forget()
        if row_count > visible_rows:
            self.rows_scrollbar.pack(side="right", fill="y")
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
            block = self.kvm_result_blocks[slot]
            if slot > KVM_COLUMN_COUNT and not has_second_kvm_row:
                block.place_forget()
            else:
                row = (slot - 1) // KVM_COLUMN_COUNT
                column = (slot - 1) % KVM_COLUMN_COUNT
                block.place(x=column * KVM_CELL_STEP, y=KVM_FIRST_ROW_Y + row * KVM_ROW_STEP,
                            width=KVM_CELL_WIDTH, height=KVM_CELL_HEIGHT)
            self._set_kvm_result_block(slot, "WAITING")
        self._position_window()

    def _position_window(self) -> None:
        self.root.update_idletasks()
        capacity = self._display_capacity()
        width = WINDOW_WIDTH
        height = window_height(capacity, self.root.winfo_screenheight())
        visible_rows = visible_detail_rows(capacity, self.root.winfo_screenheight())
        self.kvm_results.configure(height=KVM_BAND_HEIGHT if capacity > KVM_COLUMN_COUNT
                                   else KVM_SINGLE_ROW_HEIGHT)
        self.rows_canvas.configure(height=visible_rows * (ROW_HEIGHT + ROW_GAP))
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
        for field in ("start", "test", "round"):
            self.timeouts[profile.machine][field].set(str(profile.timeouts[field]))
        self.bt_format.set("B518 RS-WMT" if profile.platform == "rswmt" else "B482 TestData")

    def _refresh_machine_choices(self) -> None:
        self.project_choice.configure(values=self.profiles.projects)
        available = self.profiles.for_project(self.project.get())
        machines = tuple(profile.machine for profile in available)
        self.machine_choice.configure(values=machines)
        if self.station.get() not in machines and machines:
            self.station.set(machines[0])
        self._load_selected_profile_values()

    def _project_changed(self, _event=None) -> None:
        if self.profile_error and self.profile_error.startswith((
                "已保存的專案與機型選擇", "目前選擇已從配置清單移除")):
            self.profile_error = None
        self._refresh_machine_choices()
        self._render_rows()

    def _profile_changed(self, _event=None) -> None:
        if self.profile_error and self.profile_error.startswith((
                "已保存的專案與機型選擇", "目前選擇已從配置清單移除")):
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
        try:
            platform_definition = DEFAULT_PLATFORM_REGISTRY.get(platform)
        except ValueError as error:
            messagebox.showerror("配置錯誤", str(error), parent=self.root)
            return
        # The station fields are the current selected profile's loaded values;
        # freeze them here before asynchronous adapter preparation begins.
        profile_paths = {field: variable.get() for field, variable in values.items()}
        resolved_paths = {}
        for field in platform_definition.required_paths:
            directory = configured_directory(profile_paths.get(field, ""))
            if directory is None:
                messagebox.showerror(
                    "路徑錯誤", "請設定存在且可讀取的{}。".format(
                        platform_definition.path_labels.get(field, field)), parent=self.root,
                )
                return
            resolved_paths[field] = directory
        for field in platform_definition.optional_paths:
            configured = profile_paths.get(field, "")
            directory = configured_directory(configured) if configured.strip() else None
            if configured.strip() and directory is None:
                messagebox.showerror(
                    "路徑錯誤", "{} 不存在或無法讀取。".format(
                        platform_definition.path_labels.get(field, field)), parent=self.root,
                )
                return
            resolved_paths[field] = directory
        self.active_profile_snapshot = profile
        self.start_button.configure(state="disabled")
        self.monitor_state.configure(text="啟動中")
        self.root.update_idletasks()
        try:
            def monitor_factory(on_event):
                capacity = profile.capacity if profile else slot_count(station)
                mapping = dict(profile.mapping) if profile else {slot: slot for slot in range(1, capacity + 1)}
                source_slots = tuple(mapping)
                view_holder = {}

                def deliver(event):
                    view = view_holder.get("view")
                    if view is not None:
                        return view.deliver(event, on_event)
                    else:
                        return on_event(event)

                monitor = DEFAULT_PLATFORM_REGISTRY.create_monitor(
                    platform, station=station, paths=resolved_paths, source_slots=source_slots,
                    callback=deliver, timeouts=timeouts,
                    session_root=getattr(self, "session_root", APP_ROOT / "sessions"),
                    async_session_writes=True,
                )
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
            snapshot = self.rounds.start(station, monitor_factory, run_async=True,
                                         round_timeout_seconds=timeouts["round"],
                                         capacity=profile.capacity if profile else slot_count(station),
                                         audit_context={
                                             "project": profile.project if profile else (
                                                 self.project.get() if hasattr(self, "project") else "unknown"),
                                             "machine": profile.machine if profile else station,
                                             "platform": platform,
                                             "profile_version": 1 if profile else None,
                                             "config_snapshot": profile.to_dict() if profile else {
                                                 "capacity": slot_count(station),
                                                 "paths": {key: str(value) for key, value in values.items()},
                                                 "timeouts": timeouts,
                                             },
                                             "capacity": profile.capacity if profile else slot_count(station),
                                             "mapping": ([{"source": source, "display": display}
                                                          for source, display in profile.mapping]
                                                         if profile else []),
                                             "paths": ({key: value for key, value in profile.paths.items()}
                                                       if profile else {key: str(value) for key, value in values.items()}),
                                             "timeouts": dict(timeouts),
                                         })
            self.active_round_id = snapshot.round_id
            self.monitor = self.rounds.monitor
            self._reset_rows()
            self._apply_round_snapshot(snapshot)
        except Exception as error:
            self.monitor = None
            self.active_profile_snapshot = None
            self._render_state_marker(None)
            self._set_monitor_controls(False)
            message = "無法開始監控：{}".format(error)
            self._log(message)
            messagebox.showerror("監控啟動失敗", message, parent=self.root)
            return
        self._set_monitor_controls(True)
        self._log("{} 監控已開始；本輪時間與啟動前快照已建立。".format(station))

    def stop_monitor(self) -> None:
        snapshot = self.rounds.snapshot()
        if snapshot is not None and snapshot.state in {"RUNNING", "AWAITING_REVIEW"}:
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
        round_snapshot = self.rounds.snapshot() if hasattr(self, "rounds") else None
        if round_snapshot and (self.rounds.monitor is None or round_snapshot.source_preparation_pending):
            self.rounds.poll_once()
            if self.monitor is None:
                self.monitor = self.rounds.monitor
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
        snapshot = self.rounds.snapshot() if hasattr(self, "rounds") else None
        self._apply_round_snapshot(snapshot)
        self._refresh_conflict_review()
        self._refresh_round_alarm()
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
        if self.monitor is None and hasattr(self, "rounds"):
            self.monitor = self.rounds.monitor
        self._log(event.message)
        snapshot = self.rounds.snapshot() if hasattr(self, "rounds") else None
        self._apply_round_snapshot(snapshot)
        if event.slot and snapshot:
            result = next((item for item in snapshot.results if item.slot == event.slot), None)
            if result is not None:
                self._set_row(event.slot, result.sn, result.status)
        elif event.slot and self.monitor and event.slot in self.monitor.results:
            result = self.monitor.results[event.slot]
            self._set_row(event.slot, result.sn, result.status)
        if event.kind == "result" and event.status in {"PASS", "FAIL", "NOTEST"}:
            self._bring_dashboard_to_front()
        if event.kind == "conflict_detected":
            self._open_conflict_review()
        if event.kind == "timeout" and event.detail.get("kind") == "start":
            self.monitor = None
            self._set_monitor_controls(False, "逾時停止")
        if event.kind == "timeout" and event.detail.get("kind") == "round":
            self.monitor = None
            self._set_monitor_controls(False, "逾時停止")
            self._open_round_alarm()
        if event.kind == "start_failed":
            self.monitor = None
            self.active_profile_snapshot = None
            self._set_monitor_controls(False, "啟動失敗")
            messagebox.showerror("監控啟動失敗", event.message, parent=self.root)
        if event.kind in {"finished", "stopped"}:
            self.monitor = None
            self.active_profile_snapshot = None
            self._set_monitor_controls(False)

    def _open_conflict_review(self) -> None:
        """Show the captured candidates in a modeless, non-blocking window."""
        if not self.conflict_window or not self.conflict_window.winfo_exists():
            window = tk.Toplevel(self.root)
            self.conflict_window = window
            window.title("同輪結果衝突確認")
            self.root.update_idletasks()
            window_x = max(self.root.winfo_rootx() - 820 - 12, 0)
            window_y = max(self.root.winfo_rooty(), 0)
            window.geometry("820x430+{}+{}".format(window_x, window_y))
            window.minsize(720, 360)
            window.transient(self.root)
            window.protocol("WM_DELETE_WINDOW", window.withdraw)
            ttk.Label(window, text="逐項選擇保留原結果或採用已捕捉的新結果；關閉此視窗不會自動選擇。",
                      wraplength=780).pack(fill="x", padx=12, pady=(12, 8))
            body = ttk.Frame(window)
            body.pack(fill="both", expand=True, padx=12, pady=4)
            self.conflict_list = tk.Listbox(body, width=38, exportselection=False,
                                            background=FIELD_BACKGROUND, foreground=TEXT_COLOUR,
                                            selectbackground="#1d4ed8", selectforeground="#ffffff")
            self.conflict_list.pack(side="left", fill="y")
            self.conflict_list.bind("<<ListboxSelect>>", self._show_selected_conflict)
            self.conflict_details = tk.Text(body, wrap="word", height=14, state="disabled",
                                            background=LIGHT_BACKGROUND, foreground=TEXT_COLOUR,
                                            font=("Menlo", 11), relief="solid", borderwidth=1)
            self.conflict_details.pack(side="left", fill="both", expand=True, padx=(10, 0))
            actions = ttk.Frame(window)
            actions.pack(fill="x", padx=12, pady=(8, 12))
            ttk.Button(actions, text="保留原結果", command=lambda: self._resolve_selected_conflict(
                "keep_original")).pack(side="left", padx=(0, 8))
            ttk.Button(actions, text="採用新結果", command=lambda: self._resolve_selected_conflict(
                "accept_candidate")).pack(side="left")
            ttk.Button(actions, text="關閉", command=window.withdraw).pack(side="right")
        self._refresh_conflict_review()
        if self.conflict_window and self.conflict_window.winfo_exists():
            self.conflict_window.deiconify()
            self.conflict_window.lift()

    def _refresh_conflict_review(self) -> None:
        if not hasattr(self, "review_button"):
            return
        snapshot = self.rounds.snapshot() if hasattr(self, "rounds") else None
        conflicts = snapshot.pending_conflicts if snapshot else ()
        self.review_button.configure(
            text="待確認 ({})".format(len(conflicts)),
            state="normal" if conflicts else "disabled",
        )
        alarm = snapshot.round_alarm if snapshot else None
        alarm_pending = alarm is not None and not alarm.acknowledged_at
        if alarm_pending or conflicts:
            reasons = []
            if alarm_pending:
                reasons.append("整輪警報")
            if conflicts:
                reasons.append("衝突 {} 項".format(len(conflicts)))
            self.monitor_state.configure(text="待確認：" + "、".join(reasons))
        elif snapshot and snapshot.state.value == "COMPLETED":
            self.monitor_state.configure(text="本輪完成")
        elif snapshot and snapshot.state.value == "STOPPED" and snapshot.completion_reason == "manual_stop":
            self.monitor_state.configure(text="已停止")
        if self.conflict_window and self.conflict_window.winfo_exists():
            if self.conflict_list is None:
                return
            selected = self.conflict_list.curselection()
            selected_id = self._conflict_ids[selected[0]] if selected and selected[0] < len(self._conflict_ids) else None
            self._conflict_ids = [item.conflict_id for item in conflicts]
            self.conflict_list.delete(0, "end")
            for item in conflicts:
                self.conflict_list.insert("end", "位置 {}：{} {} → {} {}".format(
                    item.slot, item.original.sn or "SN 未知", item.original.status,
                    item.candidate.sn or "SN 未知", item.candidate.status,
                ))
            if selected_id in self._conflict_ids:
                index = self._conflict_ids.index(selected_id)
            else:
                index = 0 if self._conflict_ids else -1
            if index >= 0:
                self.conflict_list.selection_set(index)
                self.conflict_list.activate(index)
                self._show_selected_conflict()
            elif self.conflict_details:
                self.conflict_details.configure(state="normal")
                self.conflict_details.delete("1.0", "end")
                self.conflict_details.insert("1.0", "目前沒有待確認項目。")
                self.conflict_details.configure(state="disabled")

    def _show_selected_conflict(self, _event=None) -> None:
        if not self.conflict_list or not self.conflict_details:
            return
        selected = self.conflict_list.curselection()
        if not selected or selected[0] >= len(self._conflict_ids):
            return
        snapshot = self.rounds.snapshot()
        if not snapshot:
            return
        conflict_id = self._conflict_ids[selected[0]]
        conflict = next((item for item in snapshot.pending_conflicts
                         if item.conflict_id == conflict_id), None)
        if not conflict:
            return
        def render(side):
            return ("SN：{}\n結果：{}\n來源：{}\n來源識別：{}\n來源時間：{}\n證據：{}".format(
                side.sn or "未知", side.status or "未知", side.source or "未知",
                side.source_id or "未知", side.source_time or "未知",
                dict(side.evidence),
            ))
        text = ("輪次：{}\n衝突：{}\n顯示位置：{}\n同輪證據：{}\n\n原結果\n{}\n\n候選快照\n{}"
                .format(conflict.round_id, conflict.conflict_id, conflict.slot,
                        dict(conflict.same_round_evidence), render(conflict.original),
                        render(conflict.candidate)))
        self.conflict_details.configure(state="normal")
        self.conflict_details.delete("1.0", "end")
        self.conflict_details.insert("1.0", text)
        self.conflict_details.configure(state="disabled")

    def _resolve_selected_conflict(self, choice: str) -> None:
        if not self.conflict_list:
            return
        selected = self.conflict_list.curselection()
        if not selected or selected[0] >= len(self._conflict_ids):
            return
        self.rounds.resolve_review(self._conflict_ids[selected[0]], choice)
        self._refresh_conflict_review()

    def _refresh_round_alarm(self) -> None:
        if not hasattr(self, "round_alarm_button"):
            return
        snapshot = self.rounds.snapshot() if hasattr(self, "rounds") else None
        alarm = snapshot.round_alarm if snapshot else None
        if alarm is None:
            self.round_alarm_button.configure(text="整輪警報", state="disabled")
            if (snapshot and self._round_alarm_window_identity and
                    self._round_alarm_window_identity[0] != snapshot.round_id and
                    self.round_alarm_window and self.round_alarm_window.winfo_exists()):
                self.round_alarm_window.withdraw()
            return
        pending = not alarm.acknowledged_at
        self.round_alarm_button.configure(
            text="整輪警報（待確認）" if pending else "整輪警報已確認",
            state="normal" if pending and snapshot.round_alarm_ready else "disabled",
        )
        identity = (alarm.round_id, alarm.alarm_id)
        if identity != getattr(self, "_shown_round_alarm_identity", None):
            self._open_round_alarm()
        if self.round_alarm_window and self.round_alarm_window.winfo_exists():
            self._render_round_alarm(alarm)

    def _open_round_alarm(self) -> None:
        snapshot = self.rounds.snapshot() if hasattr(self, "rounds") else None
        alarm = snapshot.round_alarm if snapshot else None
        if alarm is None:
            return
        if not self.round_alarm_window or not self.round_alarm_window.winfo_exists():
            window = tk.Toplevel(self.root)
            self.round_alarm_window = window
            window.title("整輪監控逾時")
            window.geometry("460x220")
            window.minsize(420, 190)
            window.transient(self.root)
            window.protocol("WM_DELETE_WINDOW", window.withdraw)
            self.round_alarm_message = ttk.Label(window, wraplength=420, justify="left")
            self.round_alarm_message.pack(fill="both", expand=True, padx=16, pady=(18, 10))
            actions = ttk.Frame(window)
            actions.pack(fill="x", padx=16, pady=(0, 14))
            self.round_alarm_ack_button = ttk.Button(
                actions, text="確認整輪警報",
            )
            self.round_alarm_ack_button.pack(side="left")
            ttk.Button(actions, text="關閉", command=window.withdraw).pack(side="right")
        self._render_round_alarm(alarm)
        self._round_alarm_window_identity = (alarm.round_id, alarm.alarm_id)
        self.round_alarm_ack_button.configure(
            command=lambda round_id=alarm.round_id, alarm_id=alarm.alarm_id:
            self._acknowledge_round_alarm(round_id, alarm_id),
        )
        self._shown_round_alarm_identity = (alarm.round_id, alarm.alarm_id)
        self.round_alarm_window.deiconify()
        self.round_alarm_window.lift()

    def _render_round_alarm(self, alarm) -> None:
        if self.round_alarm_message and self.round_alarm_message.winfo_exists():
            self.round_alarm_message.configure(text=(
                "整輪監控已到達設定上限。新的來源讀取已停止，既有終態已保留，未完成位置已依活動證據裁決。\n\n"
                "輪次：{}\n警報：{}\n建立時間：{}\n{}"
            ).format(alarm.round_id, alarm.alarm_id, alarm.created_at,
                     "此警報已確認；其他待確認事項仍須逐項處理。"
                     if alarm.acknowledged_at else (
                         "來源準備尚未結束；位置裁決完成前不能確認。" if not self.rounds.snapshot().round_alarm_ready
                         else "確認此警報不會接受或清除結果衝突。")))
        if self.round_alarm_ack_button and self.round_alarm_ack_button.winfo_exists():
            self.round_alarm_ack_button.configure(
                state="disabled" if alarm.acknowledged_at or not self.rounds.snapshot().round_alarm_ready else "normal",
                text="警報已確認" if alarm.acknowledged_at else "確認整輪警報",
            )

    def _acknowledge_round_alarm(self, round_id: str, alarm_id: str) -> None:
        snapshot = self.rounds.snapshot()
        if snapshot is None:
            return
        self.rounds.acknowledge_round_alarm(round_id, alarm_id)
        self._refresh_round_alarm()
        self._refresh_conflict_review()

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
        self.settings_notebook = notebook
        notebook.pack(fill="both", expand=True, padx=12, pady=12)
        settings_tab = ttk.Frame(notebook, padding=12)
        profile_tab = ttk.Frame(notebook, padding=12)
        log_tab = ttk.Frame(notebook, padding=12)
        notebook.add(settings_tab, text="監控設定")
        notebook.add(profile_tab, text="工程師配置")
        notebook.add(log_tab, text="事件與 Session")
        self._build_settings_tab(settings_tab)
        self._build_profile_editor_tab(profile_tab)
        self._build_log_tab(log_tab)

    def _build_profile_editor_tab(self, parent: ttk.Frame) -> None:
        """Build a draft editor whose values stay separate until explicit apply."""
        try:
            profile = self.profiles.get(self.project.get(), self.station.get())
        except ProfileError:
            profile = self.profiles.profiles[0]
        self.profile_editor_original = profile
        self.profile_editor_project = tk.StringVar(value=profile.project)
        self.profile_editor_machine = tk.StringVar(value=profile.machine)
        self.profile_editor_platform = tk.StringVar(value=profile.platform)
        self.profile_editor_capacity = tk.StringVar(value=str(profile.capacity))
        self.profile_editor_paths = {
            field: tk.StringVar(value=profile.paths.get(field, ""))
            for field in ("active", "final", "caseinfo")
        }
        self.profile_editor_mapping = tk.StringVar(value=self._mapping_text(profile.mapping))
        self.profile_editor_timeouts = {
            field: tk.StringVar(value=str(profile.timeouts[field]))
            for field in ("start", "test", "round")
        }
        self.profile_editor_status = tk.StringVar(
            value="編輯草稿；路徑只做結構檢查，實際可讀性在開始監控前檢查。")

        ttk.Label(parent, text="專案代號").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.profile_editor_project, width=18).grid(
            row=0, column=1, sticky="w", padx=6, pady=4)
        ttk.Label(parent, text="機型").grid(row=0, column=2, sticky="w", padx=(12, 0), pady=4)
        self.profile_editor_machine_choice = ttk.Combobox(
            parent, textvariable=self.profile_editor_machine,
            values=("DFU", "FCT", "BT"), state="readonly", width=9)
        self.profile_editor_machine_choice.grid(
            row=0, column=3, sticky="w", padx=6, pady=4)
        ttk.Label(parent, text="平台").grid(row=0, column=4, sticky="w", padx=(12, 0), pady=4)
        ttk.Combobox(parent, textvariable=self.profile_editor_platform,
                     values=DEFAULT_PLATFORM_REGISTRY.names, state="readonly", width=16).grid(
            row=0, column=5, sticky="w", padx=6, pady=4)

        ttk.Label(parent, text="測試容量").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.profile_editor_capacity, width=10).grid(
            row=1, column=1, sticky="w", padx=6, pady=4)
        ttk.Label(parent, text="來源:顯示位置映射").grid(row=1, column=2, sticky="w", padx=(12, 0), pady=4)
        ttk.Entry(parent, textvariable=self.profile_editor_mapping, width=34).grid(
            row=1, column=3, columnspan=3, sticky="ew", padx=6, pady=4)

        path_labels = (("active", "即時 Log 路徑"), ("final", "最終結果路徑"),
                       ("caseinfo", "CaseInfo／進度路徑（選填）"))
        for row, (field, label) in enumerate(path_labels, 2):
            ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4)
            ttk.Entry(parent, textvariable=self.profile_editor_paths[field]).grid(
                row=row, column=1, columnspan=4, sticky="ew", padx=6, pady=4)
            ttk.Button(parent, text="選擇本機資料夾",
                       command=lambda current=field: self._choose_profile_editor_path(current)).grid(
                row=row, column=5, sticky="e", padx=6, pady=4)

        timeout_labels = (("start", "開始期限（秒）"), ("test", "測試期限（秒）"),
                          ("round", "整輪期限（秒）"))
        for row, (field, label) in enumerate(timeout_labels, 5):
            ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4)
            ttk.Entry(parent, textvariable=self.profile_editor_timeouts[field], width=16).grid(
                row=row, column=1, sticky="w", padx=6, pady=4)
        ttk.Label(parent, textvariable=self.profile_editor_status, wraplength=620,
                  foreground=TEXT_COLOUR).grid(row=8, column=0, columnspan=6, sticky="w", pady=(10, 6))
        edit_actions = ttk.Frame(parent)
        edit_actions.grid(row=9, column=0, columnspan=6, sticky="ew", pady=(8, 0))
        for label, action in (("載入已保存配置", self._load_profile_editor_selection),
                              ("驗證草稿", self._validate_profile_editor),
                              ("套用並保存", self._apply_profile_editor),
                              ("取消草稿", self._cancel_profile_editor)):
            ttk.Button(edit_actions, text=label, command=action).pack(side="left", padx=(0, 6))
        file_actions = ttk.Frame(parent)
        file_actions.grid(row=10, column=0, columnspan=6, sticky="ew", pady=(6, 0))
        for label, action in (("匯入配置", self._import_profiles),
                              ("匯出配置", self._export_profiles),
                              ("重新載入部署配置", self._reload_profiles)):
            ttk.Button(file_actions, text=label, command=action).pack(side="left", padx=(0, 6))
        parent.columnconfigure(3, weight=1)
        parent.rowconfigure(7, weight=1)

    @staticmethod
    def _mapping_text(mapping) -> str:
        return ", ".join("{}:{}".format(source, display) for source, display in mapping)

    def _choose_profile_editor_path(self, field: str) -> None:
        path = filedialog.askdirectory(parent=self.settings_window, mustexist=True,
                                       title="選擇配置路徑")
        if path:
            self.profile_editor_paths[field].set(path)

    def _profile_editor_draft(self) -> Optional[MachineProfile]:
        try:
            profile = profile_from_editor_fields(
                self.profile_editor_project.get(), self.profile_editor_machine.get(),
                self.profile_editor_platform.get(), self.profile_editor_capacity.get(),
                {field: variable.get() for field, variable in self.profile_editor_paths.items()},
                self.profile_editor_mapping.get(),
                {field: variable.get() for field, variable in self.profile_editor_timeouts.items()},
            )
        except (ProfileError, TypeError, ValueError) as error:
            self.profile_editor_status.set("配置欄位錯誤：{}".format(error))
            return None
        self.profile_editor_status.set("結構驗證通過；部署電腦仍會在開始前檢查路徑。")
        return profile

    def _validate_profile_editor(self) -> None:
        self._profile_editor_draft()

    def _apply_profile_editor(self) -> None:
        profile = self._profile_editor_draft()
        if profile is None:
            return
        catalog = self.profiles.with_profile(profile)
        try:
            self.profile_store.save(
                catalog, profile.project, profile.machine,
                preserve_legacy=self.profile_store.migration_required,
            )
        except (OSError, ProfileError, TypeError, ValueError) as error:
            self.profile_editor_status.set("保存失敗，原配置仍有效：{}".format(error))
            return
        self.profiles = catalog
        self.profile_error = None
        self.profile_editor_original = profile
        if self.monitor is None:
            self.project.set(profile.project)
            self.station.set(profile.machine)
        self._load_selected_profile_values()
        self._refresh_machine_choices()
        self._synchronize_monitor_settings_draft()
        if self.monitor is None:
            self._render_rows()
        self._render_profile_editor(profile)
        self.profile_editor_status.set("配置已套用並保存；更新供後續輪次使用。")

    def _cancel_profile_editor(self) -> None:
        self._render_profile_editor(self.profile_editor_original)
        self.profile_editor_status.set("草稿已取消，已保存配置未變更。")

    def _load_profile_editor_selection(self) -> None:
        try:
            profile = self.profiles.get(
                self.profile_editor_project.get().strip(), self.profile_editor_machine.get())
        except ProfileError as error:
            self.profile_editor_status.set("找不到可載入配置：{}".format(error))
            return
        self.profile_editor_original = profile
        self._render_profile_editor(profile)
        self.profile_editor_status.set("已載入已保存配置作為草稿。")

    def _render_profile_editor(self, profile: MachineProfile) -> None:
        self.profile_editor_project.set(profile.project)
        self.profile_editor_machine.set(profile.machine)
        self.profile_editor_platform.set(profile.platform)
        self.profile_editor_capacity.set(str(profile.capacity))
        for field in self.profile_editor_paths:
            self.profile_editor_paths[field].set(profile.paths.get(field, ""))
        self.profile_editor_mapping.set(self._mapping_text(profile.mapping))
        for field in self.profile_editor_timeouts:
            self.profile_editor_timeouts[field].set(str(profile.timeouts[field]))

    def _synchronize_monitor_settings_draft(self) -> None:
        """Prevent the legacy settings tab from saving values captured before an update."""
        settings_paths = getattr(self, "settings_paths", None)
        settings_timeouts = getattr(self, "settings_timeouts", None)
        if settings_paths is None or settings_timeouts is None:
            return
        try:
            profile = self.profiles.get(self.project.get(), self.station.get())
        except ProfileError:
            return
        self.settings_project.set(profile.project)
        self.settings_station.set(profile.machine)
        self.settings_bt_format.set("B518 RS-WMT" if profile.platform == "rswmt" else "B482 TestData")
        for field, value in profile.paths.items():
            if field in settings_paths[profile.machine]:
                settings_paths[profile.machine][field].set(value)
        for field, value in profile.timeouts.items():
            settings_timeouts[profile.machine][field].set(str(value))

    def _import_profiles(self) -> None:
        path = filedialog.askopenfilename(
            parent=self.settings_window, title="匯入工程師配置",
            filetypes=(("JSON 配置", "*.json"), ("所有檔案", "*")),
        )
        if not path:
            return
        try:
            document = Path(path).read_text(encoding="utf-8")
            catalog, project, machine = self.profile_store.import_document(
                document, self.project.get(), self.station.get())
        except (OSError, ProfileError, TypeError, ValueError) as error:
            self.profile_editor_status.set("匯入失敗，原配置保留：{}".format(error))
            return
        self._activate_profile_catalog(
            catalog, project, machine,
            "配置已驗證、完整匯入並保存。",
            "匯入後原選擇不存在；已明確切換至文件中的有效配置：{project} / {machine}。",
        )

    def _export_profiles(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self.settings_window, title="匯出工程師配置",
            defaultextension=".json", filetypes=(("JSON 配置", "*.json"),),
        )
        if not path:
            return
        try:
            MachineProfileStore.export_document(Path(path), self.profiles)
        except OSError as error:
            self.profile_editor_status.set("匯出失敗：{}".format(error))
            return
        self.profile_editor_status.set("已匯出 {} 組配置。".format(len(self.profiles.profiles)))

    def _reload_profiles(self) -> None:
        catalog, saved_project, saved_machine, error = self.profile_store.load()
        if error:
            self.profile_editor_status.set("重新載入失敗，目前有效配置保留：{}".format(error))
            return
        self._activate_profile_catalog(
            catalog, saved_project, saved_machine,
            "已重新載入部署配置；正在進行的輪次仍使用原快照。",
            "重新載入後原選擇不存在；已明確切換至偏好檔中的有效配置：{project} / {machine}。",
        )

    def _activate_profile_catalog(self, catalog, suggested_project: str, suggested_machine: str,
                                  success_message: str, fallback_message: str) -> None:
        """Activate a valid catalog while preserving or explicitly replacing selection."""
        try:
            profile = catalog.get(self.project.get(), self.station.get())
        except ProfileError:
            profile = None
        if profile is None and self.monitor is not None:
            self.profiles = catalog
            self.profile_error = "目前選擇已從配置清單移除；請明確選擇有效專案與機型。"
            editor_profile = catalog.get(suggested_project, suggested_machine)
            self.profile_editor_original = editor_profile
            self._render_profile_editor(editor_profile)
            self.profile_editor_status.set(self.profile_error)
            return
        selection_changed = profile is None
        if selection_changed:
            profile = catalog.get(suggested_project, suggested_machine)
        try:
            catalog.get(profile.project, profile.machine)
        except ProfileError:
            raise ProfileError("匯入／重新載入配置缺少建議的有效選擇。")
        self.profiles = catalog
        self.project.set(profile.project)
        self.station.set(profile.machine)
        self.profile_error = None
        self._refresh_machine_choices()
        self._synchronize_monitor_settings_draft()
        if self.monitor is None:
            self._render_rows()
        self.profile_editor_original = profile
        self._render_profile_editor(profile)
        if selection_changed:
            self.profile_editor_status.set(fallback_message.format(
                project=profile.project, machine=profile.machine))
        else:
            self.profile_editor_status.set(success_message)

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
        try:
            selected = self.profiles.get(self.settings_project.get(), station)
            definition = DEFAULT_PLATFORM_REGISTRY.get(selected.platform)
            schema = tuple((field, definition.path_labels.get(field, field))
                           for field in definition.required_paths + definition.optional_paths)
        except (AttributeError, ProfileError, ValueError):
            schema = (("final", "BT TestData 根路徑"), ("caseinfo", "BT CaseInfo 根路徑（選填）")) if station == "BT" else (
                ("active", "即時 Log 根路徑 (active)"), ("final", "最終結果根路徑"),
            )
        disabled = self.monitor is not None
        offset = 0
        if station == "BT" and not hasattr(self, "profiles"):
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
        path = self.monitor.session.path if self.monitor else self.session_root
        path.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.Popen(["open", str(path)])
        except OSError as error:
            messagebox.showerror("無法開啟", str(error), parent=self.root)

    def close(self) -> None:
        self.hotkey.close()
        rounds = getattr(self, "rounds", None)
        snapshot = rounds.snapshot() if rounds is not None else None
        if snapshot is not None and snapshot.state in {"RUNNING", "AWAITING_REVIEW"}:
            rounds.stop()
        monitor = getattr(self, "monitor", None)
        if monitor is None and rounds is not None:
            monitor = rounds.monitor
        session = getattr(monitor, "session", None)
        session_saved = session.flush(timeout=2.0) if session is not None else True
        audit_saved = rounds.flush_audit(timeout=2.0) if rounds is not None else True
        if not session_saved or not audit_saved:
            messagebox.showwarning(
                "稽核紀錄不完整",
                "關閉前仍有稽核或 Session 紀錄未能完整保存；既有結果放行狀態不變。",
                parent=self.root,
            )
        try:
            self._save_preferences()
        except (OSError, ProfileError) as error:
            messagebox.showerror("偏好儲存失敗", str(error), parent=self.root)
        self.root.destroy()


if __name__ == "__main__":
    window = tk.Tk()
    B518LogSolutionApp(window)
    window.mainloop()
