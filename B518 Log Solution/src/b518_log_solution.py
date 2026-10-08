"""B518 Log Solution — local-only KVM-friendly desktop monitor."""

from __future__ import annotations

import queue
import json
import sys
import subprocess
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, font as tkfont, messagebox, ttk
from typing import Dict, Optional

from app_event_store import AppEventStore
from global_hotkey import HotkeyRegistration, create_global_hotkey
from log_monitoring import MonitorEvent
from monitoring_round import RoundCoordinator, RoundEvent
from machine_profiles import (
    MachineProfile, MachineProfileStore, ProfileError, profile_from_editor_fields,
)
from platform_registry import DEFAULT_PLATFORM_REGISTRY
from round_start_preparation import RoundStartPathError, RoundStartPreparation
from language_catalog import (
    DEFAULT_LANGUAGE, LANGUAGE_OPTIONS, TRADITIONAL_CHINESE, language_name,
    render_bilingual_message, save_state_message_id, translate,
)
from kvm_display_contract import (
    KVM_CELL_HEIGHT, KVM_CELL_STEP, KVM_CELL_WIDTH, KVM_COLUMN_COUNT,
    KVM_FIRST_ROW_Y, KVM_ROW_STEP,
    LOCATOR_FAR_INSET, LOCATOR_LEFT, LOCATOR_NEAR_INSET, LOCATOR_RIGHT,
    LOCATOR_SIZE, LOCATOR_WHITE_SIZE, MARKER_CELL_GAP, MARKER_CELL_SIZE,
    MARKER_PATTERNS, MARKER_QUIET_ZONE, MARKER_SIZE, MarkerState,
    STATE_MARKER_ORIGIN, state_for_round_snapshot,
    LAYOUT_MARKER_ORIGIN, LAYOUT_MARKER_SIZE, LAYOUT_MARKER_PATTERNS,
)


APP_ROOT = Path.home() / "Library" / "Application Support" / "B518LogSolution"
PREFS_PATH = APP_ROOT / "preferences.json"
ASSETS_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1])) / "assets"
COMPANY_LOGO_PATH = ASSETS_ROOT / "foxlink_logo.png"
LIGHT_BACKGROUND = "#f3f4f6"
FIELD_BACKGROUND = "#ffffff"
TEXT_COLOUR = "#111827"
MUTED_TEXT_COLOUR = "#555555"
WINDOW_WIDTH = 376
MAIN_FONT_SIZE = 14
ROW_HEIGHT = 46
ROW_GAP = 1
ROW_WIDTH = 342
KVM_BAND_HEIGHT = 88
KVM_SINGLE_ROW_HEIGHT = 61
DETAIL_ROWS_VISIBLE = 7
WINDOW_FIXED_HEIGHT = 379
STATUS_TEMPLATE_STATES = ("PASS", "FAIL", "TESTING", "NOTEST")
STATUS_COLOURS = {
    "PASS": "#00ef00", "FAIL": "#ff0000", "TESTING": "#ffff00", "NOTEST": "#f04bf1",
    "WAITING": "#d9d9d9", "COMPLETING": "#82c7ff", "STALLED": "#ff9900", "STOPPED": "#bfbfbf",
    "TIMEOUT": "#ff9900",
}
UNAVAILABLE_COLOUR = "#000000"
KVM_BLOCK_COUNT = 20


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


class B518LogSolutionApp:
    def __init__(self, root: tk.Tk, hotkey_factory=create_global_hotkey,
                 session_root: Optional[Path] = None, app_event_path: Optional[Path] = None,
                 app_event_clock=None):
        self.root = root
        self.session_root = Path(session_root) if session_root else APP_ROOT / "sessions"
        self.root.title("B518 Log Solution-V0.1.0")
        self.root.resizable(False, False)
        self.events: queue.Queue[RoundEvent] = queue.Queue()
        self.hotkey_events: queue.Queue[bool] = queue.Queue()
        self.rounds = RoundCoordinator(
            self.events.put, audit_root=self.session_root,
            retention_ledger_path=self.session_root.parent / "round-retention-ledger.json")
        self.app_events = AppEventStore(app_event_path or APP_ROOT / "app-events.json", clock=app_event_clock)
        self.rounds.register_app_event_store(self.app_events)
        self._closing_ui = False
        self._close_window = None
        self._close_status_label = None
        self._close_error_label = None
        self._close_retry_button = None
        self._close_poll_generation = None
        self.resolve_conflict_original_button = None
        self.resolve_conflict_candidate_button = None
        self.conflict_close_button = None
        self.active_round_id: Optional[str] = None
        self.active_profile_snapshot: Optional[MachineProfile] = None
        self.profile_store = MachineProfileStore(PREFS_PATH)
        self.round_start_preparation = RoundStartPreparation()
        self.profiles, selected_project, selected_machine, self.profile_error = self.profile_store.load()
        self.current_language = self.profile_store.language
        self._language_save_error: Optional[str] = None
        self._monitor_state_message = "monitor.idle"
        self._monitor_state_parameters: dict[str, object] = {}
        self._current_save_state = "waiting"
        self.project = tk.StringVar(value=selected_project)
        self.station = tk.StringVar(value=selected_machine)
        self.status_rows: Dict[int, Dict[str, tk.Label]] = {}
        self.template_labels: Dict[str, tk.Label] = {}
        self.kvm_result_blocks: Dict[int, tk.Label] = {}
        self._rendered_marker_state: Optional[MarkerState] = None
        self.company_logo: Optional[tk.PhotoImage] = None
        self.event_lines: list[str] = []
        self._event_records: list[tuple[str, object, Optional[str]]] = []
        self._app_event_ids = set()
        self._last_app_event_revision: Optional[int] = None
        self.app_diagnostics_window = None
        self.app_diagnostics_list = None
        self.app_diagnostics_detail = None
        self.app_diagnostics_status = None
        self.app_diagnostics_history = None
        self.app_diagnostics_retry_button = None
        self.app_event_status_label = None
        self.settings_window: Optional[tk.Toplevel] = None
        self.settings_log: Optional[tk.Text] = None
        self._settings_text_widgets: list[tuple[tk.Widget, str]] = []
        self._settings_tab_ids: list[str] = []
        self._profile_editor_status_message: Optional[tuple[str, dict[str, object]]] = None
        self._retention_status_message: Optional[tuple[str, dict[str, object]]] = None
        self.retention_days_var: Optional[tk.StringVar] = None
        self.retention_status: Optional[tk.StringVar] = None
        self.retention_cleanup_status: Optional[tk.StringVar] = None
        self._retention_cleanup_request_status = None
        self.conflict_window: Optional[tk.Toplevel] = None
        self.conflict_list: Optional[tk.Listbox] = None
        self.conflict_panes: Optional[ttk.Panedwindow] = None
        self.conflict_position_label: Optional[ttk.Label] = None
        self.conflict_comparison: Optional[tk.Text] = None
        self.conflict_comparison_scrollbar: Optional[ttk.Scrollbar] = None
        self.conflict_details: Optional[tk.Text] = None
        self._conflict_ids: list[str] = []
        self.round_alarm_window: Optional[tk.Toplevel] = None
        self.round_alarm_message: Optional[ttk.Label] = None
        self.round_alarm_ack_button: Optional[ttk.Button] = None
        self._round_alarm_window_identity: Optional[tuple[str, str]] = None
        self._configure_appearance()
        self._record_startup_diagnostics()
        self._build()
        self.hotkey: HotkeyRegistration = hotkey_factory(self._on_global_hotkey)
        self.root.bind_all("<Command-Shift-M>", self._on_local_hotkey)
        self._position_window()
        self.root.after(150, self._drain_events)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.rounds.start_retention_schedule(self.profile_store.retention_days)
        if self.profile_error:
            self.root.after(300, self._show_startup_warning)
        if self.profile_store.language_error:
            self.root.after(300, self._show_invalid_language_warning)
        if self.app_events.status().error:
            self.root.after(300, self._show_app_event_store_warning)
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
        self.settings_button = header.winfo_children()[-1]
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
        selection.columnconfigure(1, weight=1)
        self.project_label = ttk.Label(selection, text="專案")
        self.project_label.grid(row=0, column=0, sticky="w")
        self.project_choice = ttk.Combobox(selection, textvariable=self.project, state="readonly", width=10,
                                           values=self.profiles.projects)
        self.project_choice.grid(row=0, column=1, sticky="ew", padx=(5, 12))
        self.project_choice.bind("<<ComboboxSelected>>", self._project_changed)
        self.machine_label = ttk.Label(selection, text="機型")
        self.machine_label.grid(row=1, column=0, sticky="w")
        self.machine_choice = ttk.Combobox(selection, textvariable=self.station, state="readonly", width=8)
        self.machine_choice.grid(row=1, column=1, sticky="ew", padx=(5, 12))
        self.machine_choice.bind("<<ComboboxSelected>>", self._profile_changed)
        self._refresh_machine_choices()
        self.language_choice = tk.StringVar(value=self.current_language)
        self.language_button = tk.Menubutton(
            selection, text="English ▾",
            background=FIELD_BACKGROUND, foreground=TEXT_COLOUR,
            activebackground="#e5e7eb", relief="raised", borderwidth=1,
            font=("Helvetica", 10), takefocus=True,
        )
        self.language_menu = tk.Menu(self.language_button, tearoff=False)
        for language, native_name in LANGUAGE_OPTIONS:
            self.language_menu.add_radiobutton(
                label=native_name, variable=self.language_choice, value=language,
                command=lambda selected=language: self._select_language(selected),
            )
        self.language_button.configure(menu=self.language_menu)
        self.language_button.grid(row=0, column=2, rowspan=2, sticky="ne", padx=(3, 0))
        for key in ("<space>", "<Return>", "<Down>"):
            self.language_button.bind(key, self._post_language_menu)
        self.language_button.bind("<Escape>", self._cancel_language_menu)

        self.kvm_results = tk.Frame(body, background=LIGHT_BACKGROUND, height=KVM_BAND_HEIGHT)
        self.kvm_results.pack(fill="x", pady=(2, 4))
        self.kvm_results.pack_propagate(False)
        self.kvm_result_title = tk.Label(self.kvm_results, text="KVM RESULT", background=LIGHT_BACKGROUND,
                                         foreground=TEXT_COLOUR,
                                         font=("Helvetica", 10, "bold"), anchor="w")
        self.kvm_result_title.place(x=0, y=0, width=80, height=16)
        self._build_kvm_locator(self.kvm_results, *LOCATOR_LEFT, mirrored=False)
        self._build_kvm_locator(self.kvm_results, *LOCATOR_RIGHT, mirrored=True)
        self.kvm_state_marker = tk.Canvas(
            self.kvm_results, width=MARKER_SIZE, height=MARKER_SIZE,
            background="#ffffff", highlightthickness=0, borderwidth=0,
        )
        self.kvm_state_marker.place(x=STATE_MARKER_ORIGIN[0], y=STATE_MARKER_ORIGIN[1],
                                    width=MARKER_SIZE, height=MARKER_SIZE)
        self._render_state_marker(None)
        self.kvm_layout_marker = tk.Canvas(
            self.kvm_results, width=LAYOUT_MARKER_SIZE[0], height=LAYOUT_MARKER_SIZE[1],
            background="#ffffff", highlightthickness=0, borderwidth=0,
        )
        self.kvm_layout_marker.place(x=LAYOUT_MARKER_ORIGIN[0], y=LAYOUT_MARKER_ORIGIN[1],
                                     width=LAYOUT_MARKER_SIZE[0], height=LAYOUT_MARKER_SIZE[1])
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
        self.kvm_legend_title = tk.Label(legend, text="KVM 狀態模板", background=LIGHT_BACKGROUND,
                                         foreground=TEXT_COLOUR,
                                         font=("Helvetica", MAIN_FONT_SIZE, "bold"))
        self.kvm_legend_title.place(x=0, y=0, width=342, height=24)
        for index, status in enumerate(STATUS_TEMPLATE_STATES):
            label = tk.Label(legend, text=status, background=STATUS_COLOURS[status], foreground="#000000",
                             font=("Helvetica", MAIN_FONT_SIZE, "bold"), relief="solid", borderwidth=1)
            label.place(x=index * 85, y=26, width=84, height=30)
            self.template_labels[status] = label

        headings = tk.Frame(body, background=LIGHT_BACKGROUND, height=30)
        headings.pack(fill="x")
        headings.pack_propagate(False)
        self.main_headings = {}
        for message_id, x, width in (("main.slot_heading", 0, 60),
                                     ("main.status_heading", 60, 94),
                                     ("main.serial_heading", 154, 188)):
            label = tk.Label(headings, text="", background=LIGHT_BACKGROUND, foreground=TEXT_COLOUR,
                             font=("Helvetica", MAIN_FONT_SIZE, "bold"), anchor="center")
            label.place(x=x, y=0, width=width, height=30)
            self.main_headings[message_id] = label

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
        save_controls = ttk.Frame(controls)
        save_controls.pack(fill="x")
        self.stop_button = ttk.Button(save_controls, text="停止", command=self.stop_monitor,
                                      style="Main.TButton", state="disabled")
        self.stop_button.pack(side="left")
        self.save_status = ttk.Label(save_controls, text="等待保存")
        self.save_status.pack(side="left", fill="x", expand=True)
        self.retry_save_button = ttk.Button(save_controls, text="重試保存", command=self.retry_saves,
                                            state="disabled")
        self.retry_save_button.pack(side="right")
        round_save_controls = ttk.Frame(controls)
        round_save_controls.pack(fill="x", pady=(5, 0))
        self.unsaved_round_count = ttk.Label(round_save_controls, text="未保存輪次 0")
        self.unsaved_round_count.pack(side="left")
        self.unsaved_round_choice = tk.StringVar(value="")
        self.unsaved_round_picker = ttk.Combobox(
            round_save_controls, textvariable=self.unsaved_round_choice,
            state="readonly", width=26,
        )
        self.unsaved_round_picker.pack(side="left", fill="x", expand=True, padx=(5, 4))
        self.unsaved_round_retry_button = ttk.Button(
            round_save_controls, text="重試所選", command=self.retry_selected_round, state="disabled")
        self.unsaved_round_retry_button.pack(side="right")
        round_detail_controls = ttk.Frame(controls)
        round_detail_controls.pack(fill="x", pady=(3, 0))
        self.unsaved_round_detail = ttk.Label(round_detail_controls, text="", anchor="w", wraplength=270)
        self.unsaved_round_detail.pack(side="left", fill="x", expand=True)
        self._unsaved_round_ids = {}
        self.unsaved_round_picker.bind("<<ComboboxSelected>>", self._update_selected_round_retry)
        self.archive_status_label = self.unsaved_round_detail
        self.archive_round_detail = self.unsaved_round_detail
        self.archive_status_label.configure(
            text="輪次：未完整保存 0 · 完整保存 0 · 可信封存 0")
        self.archive_retry_button = ttk.Button(
            round_detail_controls, text="重試封存", command=self.retry_selected_archive, state="disabled")
        self.archive_retry_button.pack(side="right")
        app_event_controls = ttk.Frame(controls)
        app_event_controls.pack(fill="x", pady=(4, 0))
        self.app_event_status_label = ttk.Label(app_event_controls, text="")
        self.app_event_status_label.pack(side="left", fill="x", expand=True)
        self.app_diagnostics_button = ttk.Button(
            app_event_controls, text=self._t("app.diagnostic.heading"), command=self.open_app_diagnostics)
        self.app_diagnostics_button.pack(side="right")
        self._render_rows()
        self._apply_main_language()
        self._refresh_app_event_status()

    def _t(self, message_id: str, **parameters: object) -> str:
        return translate(message_id, self.current_language, **parameters)

    def _set_main_monitor_state(self, message_id: str, **parameters: object) -> None:
        self._monitor_state_message = message_id
        self._monitor_state_parameters = parameters
        if hasattr(self, "monitor_state"):
            self.monitor_state.configure(text=self._t(message_id, **parameters))

    def _apply_main_language(self) -> None:
        """Update existing main-page widgets without rebuilding monitoring state."""
        if not hasattr(self, "language_button"):
            return
        self.root.title(self._t("app.title"))
        self.language_button.configure(text="{} ▾".format(language_name(self.current_language)))
        self.language_button.configure(
            relief="sunken" if self._language_save_error else "raised")
        self.project_label.configure(text=self._t("main.project"))
        self.machine_label.configure(text=self._t("main.machine_type"))
        self.settings_button.configure(text=self._t("main.settings"))
        self.kvm_result_title.configure(text=self._t("main.kvm_result"))
        self.kvm_legend_title.configure(text=self._t("main.kvm_legend"))
        for message_id, widget in self.main_headings.items():
            widget.configure(text=self._t(message_id))
        for slot, row in self.status_rows.items():
            row["slot"].configure(text=self._t("main.slot", number=slot))
        self.start_button.configure(text=self._t("main.start_monitor"))
        self.stop_button.configure(text=self._t("main.stop"))
        self.retry_save_button.configure(text=self._t("main.retry_save"))
        self.unsaved_round_retry_button.configure(text=self._t("main.retry_selected"))
        self.archive_retry_button.configure(text=self._t("main.retry_archive"))
        self.app_diagnostics_button.configure(text=self._t("app.diagnostic.heading"))
        self._set_main_monitor_state(self._monitor_state_message,
                                     **self._monitor_state_parameters)
        self._render_station_title()
        self._render_save_status()
        self._refresh_unsaved_rounds()
        self._refresh_archive_statuses()
        self._refresh_main_round_labels()
        self._restore_captured_round_messages_for_display()
        self._refresh_event_log()
        self._refresh_app_event_status()
        self._apply_settings_language()
        if self._close_window and self._close_window.winfo_exists():
            self._render_close_status(self.rounds.close_status())
        if self.app_diagnostics_window and self.app_diagnostics_window.winfo_exists():
            self._refresh_app_event_records(force=True)

    def _settings_label(self, parent, message_id: str, **kwargs):
        widget = ttk.Label(parent, text=self._t(message_id, **kwargs))
        self._settings_text_widgets.append((widget, message_id))
        return widget

    def _settings_button(self, parent, message_id: str, command):
        widget = ttk.Button(parent, text=self._t(message_id), command=command)
        self._settings_text_widgets.append((widget, message_id))
        return widget

    def _set_profile_editor_status(self, message_id: str, **parameters: object) -> None:
        self._profile_editor_status_message = (message_id, dict(parameters))
        if self.profile_editor_status is not None:
            self.profile_editor_status.set(self._t(message_id, **parameters))

    def _set_retention_status(self, message_id: str, **parameters: object) -> None:
        self._retention_status_message = (message_id, dict(parameters))
        if self.retention_status is not None:
            self.retention_status.set(self._t(message_id, **parameters))

    def _apply_settings_language(self) -> None:
        """Refresh settings labels in place without touching draft or validation state."""
        dialog = self.settings_window
        if dialog is None or not dialog.winfo_exists():
            return
        dialog.title(self._t("app.settings.title"))
        for widget, message_id in self._settings_text_widgets:
            try:
                if widget.winfo_exists():
                    widget.configure(text=self._t(message_id))
            except tk.TclError:
                continue
        notebook = getattr(self, "settings_notebook", None)
        if notebook is not None and notebook.winfo_exists():
            for tab, message_id in zip(notebook.tabs(), self._settings_tab_ids):
                notebook.tab(tab, text=self._t(message_id))
        if getattr(self, "retention_effective_label", None) is not None:
            self.retention_effective_label.configure(
                text=self._t("app.settings.retention.effective",
                             days=self.profile_store.retention_days))
        if self._profile_editor_status_message is not None:
            message_id, parameters = self._profile_editor_status_message
            self.profile_editor_status.set(self._t(message_id, **parameters))
        if self._retention_status_message is not None:
            message_id, parameters = self._retention_status_message
            self.retention_status.set(self._t(message_id, **parameters))
        self._refresh_retention_cleanup_status()

    def _restore_captured_round_messages_for_display(self) -> None:
        """Reuse captured round messages when an early callback reached the UI first."""
        snapshot = self.rounds.snapshot()
        if snapshot is None or snapshot.round_id != self.active_round_id:
            return
        available = [item for item in snapshot.events if item.event.localized_message is not None]
        used = set()
        refreshed = []
        changed = False
        for fallback, localized, round_id in self._event_records:
            if localized is None:
                captured = next((item for item in available
                                 if (item.round_id, item.sequence) not in used and
                                 any(fallback == captured_text or fallback.endswith(captured_text)
                                     for captured_text in (
                                         item.event.message,
                                         item.event.localized_message.english,
                                         item.event.localized_message.traditional_chinese,
                                     )) and
                                 (round_id is None or round_id == item.round_id)), None)
                if captured is not None:
                    localized = captured.event.localized_message
                    round_id = captured.round_id
                    used.add((captured.round_id, captured.sequence))
                    changed = True
            refreshed.append((fallback, localized, round_id))
        if changed:
            self._event_records = refreshed

    def _refresh_main_round_labels(self) -> None:
        """Refresh only main-page round labels; language changes do not touch dialogs."""
        snapshot = self.rounds.snapshot() if hasattr(self, "rounds") else None
        conflicts = snapshot.pending_conflicts if snapshot else ()
        self.review_button.configure(
            text=self._t("main.review_count", count=len(conflicts)),
            state="normal" if conflicts else "disabled",
        )
        alarm = snapshot.round_alarm if snapshot else None
        alarm_pending = alarm is not None and not alarm.acknowledged_at
        self.round_alarm_button.configure(
            text=self._t("main.round_alarm_pending" if alarm_pending else
                         "main.round_alarm_acknowledged" if alarm else "main.round_alarm"),
            state="normal" if alarm_pending and snapshot.round_alarm_ready else "disabled",
        )
        if alarm_pending and conflicts:
            self._set_main_monitor_state("monitor.awaiting_both", count=len(conflicts))
        elif alarm_pending:
            self._set_main_monitor_state("monitor.awaiting_alarm")
        elif conflicts:
            self._set_main_monitor_state("monitor.awaiting_conflicts", count=len(conflicts))
        elif snapshot and snapshot.state.value == "COMPLETED":
            self._set_main_monitor_state("monitor.completed")
        elif snapshot and snapshot.state.value == "STOPPED" and snapshot.completion_reason == "manual_stop":
            self._set_main_monitor_state("monitor.stopped")
        elif self._round_is_active():
            self._set_main_monitor_state("monitor.active")
        elif self._monitor_state_message not in {"monitor.starting", "monitor.start_failed",
                                                 "monitor.timeout_stopped", "monitor.closing"}:
            self._set_main_monitor_state("monitor.idle")

    def _render_station_title(self) -> None:
        if hasattr(self, "station_title"):
            self.station_title.configure(text=self._t("main.station_title", machine=self.station.get().upper()))

    def _render_save_status(self) -> None:
        if hasattr(self, "save_status"):
            self.save_status.configure(text=self._t(save_state_message_id(self._current_save_state)))

    def _record_startup_diagnostics(self) -> None:
        self._record_app_event("app.startup.started")
        if self.profile_error:
            self._record_app_event("app.startup.preferences_read_failed",
                                   {"reason": self.profile_error}, self.profile_error)
        if self.profile_store.language_error:
            self._record_app_event("app.preferences.invalid_language", {},
                                   self.profile_store.language_error)
        initial_error = self.app_events.status().error
        if initial_error:
            self._record_app_event("app.event_store.initialize_failed", {"reason": initial_error},
                                   initial_error)

    def _record_app_event(self, message_id: str, parameters=None, diagnostic: str = ""):
        """Capture and display one App-owned event through the shared public boundary."""
        event = self.rounds.record_app_event(message_id, parameters or {}, diagnostic)
        if event is not None:
            self._app_event_ids.add(event.event_id)
            self._log(event.message.english, event.message)
        return event

    def _refresh_app_event_status(self) -> None:
        status = self.rounds.app_event_status()
        if status is None:
            return
        if status.status == "failed":
            text = self._t("app.save.failed", reason=status.error)
        elif status.status == "saving":
            text = self._t("app.save.pending", count=status.pending_count)
        else:
            text = self._t("app.save.complete")
        if self.app_event_status_label and self.app_event_status_label.winfo_exists():
            self.app_event_status_label.configure(text=text)
        if self.app_diagnostics_status and self.app_diagnostics_status.winfo_exists():
            self.app_diagnostics_status.configure(text=text)
        if self.app_diagnostics_history and self.app_diagnostics_history.winfo_exists():
            history = "；".join(status.error_history) if status.error_history else "—"
            self.app_diagnostics_history.configure(text=self._t(
                "app.diagnostic.save_history",
                status=self._t("app.diagnostic.save_state." + status.status),
                history=history))
        if self.app_diagnostics_retry_button and self.app_diagnostics_retry_button.winfo_exists():
            self.app_diagnostics_retry_button.configure(
                state="normal" if status.status == "failed" else "disabled")

    def _refresh_app_event_records(self, force: bool = False) -> None:
        if not self.app_diagnostics_window or not self.app_diagnostics_window.winfo_exists():
            return
        revision = self.rounds.app_event_revision()
        if not force and revision == self._last_app_event_revision:
            return
        records = self.rounds.app_event_records()
        self._last_app_event_revision = revision
        added_to_main_log = False
        for record in records:
            event_id = record.get("event_id")
            if not isinstance(event_id, str) or event_id in self._app_event_ids:
                continue
            self._app_event_ids.add(event_id)
            localized = record.get("localized_message")
            fallback = record.get("message", "")
            self._event_records.append((fallback, localized, None))
            added_to_main_log = True
        if added_to_main_log:
            self._refresh_event_log()
        if self.app_diagnostics_list and self.app_diagnostics_list.winfo_exists():
            selected = self.app_diagnostics_list.curselection()
            prior_id = getattr(self, "_selected_app_event_id", None)
            self.app_diagnostics_list.delete(0, "end")
            for record in records:
                self.app_diagnostics_list.insert(
                    "end", "{} · {}".format(record.get("occurred_at", ""),
                                               render_bilingual_message(
                                                   record.get("localized_message"),
                                                   self.current_language,
                                                   record.get("message", ""))))
            if prior_id:
                for index, record in enumerate(records):
                    if record.get("event_id") == prior_id:
                        self.app_diagnostics_list.selection_set(index)
                        self._show_app_event_detail(index)
                        break
            elif records and not selected:
                self.app_diagnostics_list.selection_set(len(records) - 1)
                self._show_app_event_detail(len(records) - 1)

    def _show_app_event_detail(self, index: Optional[int] = None) -> None:
        if not self.app_diagnostics_detail or not self.app_diagnostics_detail.winfo_exists():
            return
        if index is None:
            selected = self.app_diagnostics_list.curselection() if self.app_diagnostics_list else ()
            index = selected[0] if selected else None
        records = self.rounds.app_event_records()
        if index is None or index < 0 or index >= len(records):
            return
        record = records[index]
        self._selected_app_event_id = record.get("event_id")
        message = render_bilingual_message(record.get("localized_message"),
                                           self.current_language, record.get("message", ""))
        detail = "{}\n{}: {}\n{}: {}\n{}: {}\n{}:\n{}\n{}:\n{}".format(
            message,
            self._t("app.diagnostic.event_time"), record.get("occurred_at", ""),
            self._t("app.diagnostic.event_id"), record.get("event_id", ""),
            self._t("app.diagnostic.message_id"),
            record.get("localized_message", {}).get("message_id", ""),
            self._t("app.diagnostic.parameters"),
            json.dumps(record.get("localized_message", {}).get("parameters", {}),
                       ensure_ascii=False, indent=2),
            self._t("app.diagnostic.raw"), record.get("diagnostic", ""),
        )
        self.app_diagnostics_detail.configure(state="normal")
        self.app_diagnostics_detail.delete("1.0", "end")
        self.app_diagnostics_detail.insert("1.0", detail)
        self.app_diagnostics_detail.configure(state="disabled")

    def open_app_diagnostics(self) -> None:
        if self.app_diagnostics_window and self.app_diagnostics_window.winfo_exists():
            self.app_diagnostics_window.lift()
            self._refresh_app_event_records(force=True)
            return
        window = tk.Toplevel(self.root)
        self.app_diagnostics_window = window
        window.title(self._t("app.diagnostic.heading"))
        window.geometry("760x430")
        window.minsize(600, 340)
        window.transient(self.root)
        body = ttk.Frame(window, padding=10)
        body.pack(fill="both", expand=True)
        self.app_diagnostics_list = tk.Listbox(body, width=42, exportselection=False)
        self.app_diagnostics_list.pack(side="left", fill="both", expand=True)
        self.app_diagnostics_list.bind("<<ListboxSelect>>", lambda _event: self._show_app_event_detail())
        self.app_diagnostics_detail = tk.Text(body, wrap="word", state="disabled")
        self.app_diagnostics_detail.pack(side="left", fill="both", expand=True, padx=(8, 0))
        footer = ttk.Frame(window, padding=(10, 0, 10, 10))
        footer.pack(fill="x")
        footer_row = ttk.Frame(footer)
        footer_row.pack(fill="x")
        self.app_diagnostics_status = ttk.Label(footer_row, text="")
        self.app_diagnostics_status.pack(side="left", fill="x", expand=True)
        self.app_diagnostics_retry_button = ttk.Button(
            footer_row, text=self._t("app.diagnostic.retry"), command=self.retry_app_event_saves,
            state="disabled")
        self.app_diagnostics_retry_button.pack(side="left", padx=6)
        ttk.Button(footer_row, text=self._t("app.diagnostic.close"), command=window.destroy).pack(side="right")
        self.app_diagnostics_history = ttk.Label(footer, text="", wraplength=720, justify="left")
        self.app_diagnostics_history.pack(fill="x", pady=(5, 0))
        window.protocol("WM_DELETE_WINDOW", window.destroy)
        self._refresh_app_event_records()
        self._refresh_app_event_status()

    def retry_app_event_saves(self) -> None:
        self.rounds.retry_app_event_saves()
        self._refresh_app_event_status()

    def _select_language(self, language: str) -> None:
        if language == self.current_language:
            self.language_choice.set(self.current_language)
            return
        self.current_language = language
        self.language_choice.set(language)
        self._language_save_error = None
        self._apply_main_language()
        try:
            self.profile_store.save_language(language)
        except (OSError, ProfileError) as error:
            self._language_save_error = str(error)
            message = self._t("language.save_failed", reason=str(error))
            title = self._t("language.save_failed_title")
            self._record_app_event("app.language.preference_save_failed", {"reason": str(error)},
                                   str(error))
            self.language_button.configure(relief="sunken")
            messagebox.showerror(title, message, parent=self.root)
        else:
            self._language_save_error = None
            self.language_button.configure(relief="raised")

    def _post_language_menu(self, _event=None):
        self.language_menu.post(self.language_button.winfo_rootx(),
                                self.language_button.winfo_rooty() + self.language_button.winfo_height())
        self.language_menu.focus_set()
        return "break"

    def _cancel_language_menu(self, _event=None):
        try:
            self.language_menu.unpost()
        except tk.TclError:
            pass
        self.language_button.focus_set()
        return "break"

    def _show_invalid_language_warning(self) -> None:
        if self.root.winfo_exists() and self.profile_store.language_error:
            messagebox.showwarning(
                self._t("language.invalid_saved_title"),
                self._t("language.invalid_saved"), parent=self.root,
            )

    def _show_startup_warning(self) -> None:
        if self.root.winfo_exists() and self.profile_error:
            messagebox.showwarning(self._t("app.startup.title"),
                                   self._t("app.startup.preferences_read_failed",
                                           reason=self.profile_error), parent=self.root)

    def _show_app_event_store_warning(self) -> None:
        status = self.rounds.app_event_status()
        if self.root.winfo_exists() and status and status.error:
            messagebox.showerror(self._t("app.event_store.title"),
                                 self._t("app.event_store.initialize_failed", reason=status.error),
                                 parent=self.root)

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

    def _render_layout_marker(self, capacity: int) -> None:
        rows = 2 if capacity > KVM_COLUMN_COUNT else 1
        marker = getattr(self, "kvm_layout_marker", None)
        if marker is None or rows == getattr(self, "_rendered_layout_rows", None):
            return
        marker.delete("layout-cell")
        for column, black in enumerate(LAYOUT_MARKER_PATTERNS[rows]):
            x = MARKER_QUIET_ZONE + column * (MARKER_CELL_SIZE + MARKER_CELL_GAP)
            y = MARKER_QUIET_ZONE
            colour = "#000000" if black else "#ffffff"
            marker.create_rectangle(x, y, x + MARKER_CELL_SIZE, y + MARKER_CELL_SIZE,
                                    fill=colour, outline=colour, tags=("layout-cell",))
        self._rendered_layout_rows = rows

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
        save_state = getattr(snapshot, "save_state", "saving")
        save_errors = getattr(snapshot, "save_errors", ())
        reported_save_errors = getattr(self, "_reported_save_errors", set())
        for error in save_errors:
            if error not in reported_save_errors:
                self._log("本輪保存失敗：{}".format(error))
                reported_save_errors.add(error)
        self._reported_save_errors = reported_save_errors
        self._current_save_state = save_state
        status_text = self._t(save_state_message_id(save_state))
        if hasattr(self, "save_status"):
            self.save_status.configure(text=status_text)
        if hasattr(self, "retry_save_button"):
            self.retry_save_button.configure(
                state="normal" if save_state == "failed" else "disabled")
        for result in snapshot.results:
            self._set_row(result.slot, result.sn, result.status)
        self._render_layout_marker(self._display_capacity())
        self._render_state_marker(snapshot)

    def retry_saves(self) -> None:
        """Ask the shared round coordinator to retry in a background worker."""
        started = self.rounds.retry_saves()
        if started:
            self._current_save_state = "saving"
            self._render_save_status()
            self.retry_save_button.configure(state="disabled")

    def retry_selected_round(self) -> None:
        """Retry the operator-selected current-run round without blocking Tk."""
        if getattr(self, "_closing_ui", False):
            return
        round_id = self._unsaved_round_ids.get(self.unsaved_round_choice.get())
        if round_id and self.rounds.retry_saves(round_id):
            self.unsaved_round_retry_button.configure(state="disabled")

    def _update_selected_round_retry(self, _event=None) -> None:
        round_id = self._unsaved_round_ids.get(self.unsaved_round_choice.get())
        snapshot = self.rounds.round_snapshot(round_id) if round_id else None
        state = "normal" if (not getattr(self, "_closing_ui", False) and snapshot is not None and
                              snapshot.save_state == "failed") else "disabled"
        self.unsaved_round_retry_button.configure(state=state)
        if snapshot is None:
            self.unsaved_round_detail.configure(text="")
        elif snapshot.save_errors:
            self.unsaved_round_detail.configure(text="{}：{}".format(
                snapshot.round_id[:10], snapshot.save_errors[0]))
        else:
            self.unsaved_round_detail.configure(text="{}：{}".format(
                snapshot.round_id[:10], self._t(save_state_message_id(snapshot.save_state))))

    def _refresh_unsaved_rounds(self) -> None:
        """Render all protected rounds by identity, separate from the active result board."""
        if not hasattr(self, "unsaved_round_picker"):
            return
        snapshots = self.rounds.unsaved_rounds()
        current_id = self._unsaved_round_ids.get(self.unsaved_round_choice.get())
        labels = []
        mapping = {}
        for snapshot in snapshots:
            label = "{} · {} · {}".format(snapshot.station, snapshot.round_id[:10],
                                           self._t(save_state_message_id(snapshot.save_state)))
            mapping[label] = snapshot.round_id
            labels.append(label)
        self._unsaved_round_ids = mapping
        self.unsaved_round_picker.configure(values=labels)
        selected = next((label for label, round_id in mapping.items() if round_id == current_id), "")
        if not selected and labels:
            failed_round_id = next((snapshot.round_id for snapshot in snapshots
                                    if snapshot.save_state == "failed"), None)
            selected = next((label for label, round_id in mapping.items()
                             if round_id == failed_round_id), labels[0])
        self.unsaved_round_choice.set(selected)
        self.unsaved_round_count.configure(text=self._t("main.unsaved_rounds", count=len(snapshots)))
        self._update_selected_round_retry()

    def _refresh_archive_statuses(self) -> None:
        """Show current-run save and archive states without disk work in Tk."""
        if not hasattr(self, "archive_retry_button"):
            return
        statuses = self.rounds.archive_statuses()
        unsaved = sum(status.save_state != "complete" for status in statuses)
        saved = sum(status.save_state == "complete" and not status.cleanup_eligible
                    for status in statuses)
        archived = sum(status.cleanup_eligible for status in statuses)
        summary = self._t("main.archive_summary", unsaved=unsaved, saved=saved, archived=archived)
        selected_round_id = self._unsaved_round_ids.get(self.unsaved_round_choice.get())
        unsaved_status = next((status for status in statuses
                               if status.round_id == selected_round_id and status.save_state != "complete"), None)
        if unsaved_status is None:
            unsaved_status = next((status for status in statuses if status.save_state != "complete"), None)
        retryable = [status for status in statuses
                     if status.status in {"failed", "protected"} and status.save_state == "complete"]
        archived_status = next((status for status in statuses if status.cleanup_eligible), None)
        detail_status = unsaved_status or (retryable[0] if retryable else archived_status)
        detail = ""
        if detail_status is not None:
            state = (self._t("main.archived") if detail_status.cleanup_eligible else
                     self._t("main.archive_protected") if detail_status.save_state == "complete" else
                     self._t(save_state_message_id(detail_status.save_state)))
            reason = detail_status.message
            if detail_status.save_state == "failed":
                snapshot = self.rounds.round_snapshot(detail_status.round_id)
                if snapshot is not None and snapshot.save_errors:
                    reason = snapshot.save_errors[-1]
            if detail_status.cleanup_eligible:
                reason = str(detail_status.archived_at)
            detail = " · {} · {}{}".format(
                detail_status.round_id, state, "：" + reason if reason else "")
        self.archive_status_label.configure(text=summary + detail)
        self.archive_retry_button.configure(
            state="normal" if retryable and not self._closing_ui else "disabled")

    def retry_selected_archive(self) -> None:
        if self._closing_ui:
            return
        retryable = [status.round_id for status in self.rounds.archive_statuses()
                     if status.status in {"failed", "protected"} and status.save_state == "complete"]
        if retryable:
            self.archive_retry_button.configure(state="disabled")
            for round_id in retryable:
                self.rounds.retry_archival(round_id)

    def _set_kvm_result_block(self, slot: int, status: str) -> None:
        block = self.kvm_result_blocks.get(slot)
        if not block:
            return
        block.configure(background=kvm_block_colour(self._display_capacity(), slot, status))

    def _display_capacity(self) -> int:
        if self.active_profile_snapshot is not None:
            return self.active_profile_snapshot.capacity
        return self._selected_profile().capacity

    def _update_rows_scroll_region(self, _event=None) -> None:
        self.rows_canvas.configure(scrollregion=self.rows_canvas.bbox("all"))

    def _resize_rows_content(self, event) -> None:
        self.rows_canvas.itemconfigure(self.rows_canvas_window, width=event.width)

    def _render_rows(self) -> None:
        for child in self.rows_box.winfo_children():
            child.destroy()
        self.status_rows = {}
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
        self._render_station_title()
        self._set_main_monitor_state("monitor.active" if self._round_is_active() else "monitor.idle")
        for slot in range(1, row_count + 1):
            row = tk.Frame(self.rows_box, background="#111111", width=ROW_WIDTH, height=ROW_HEIGHT)
            row.place(x=0, y=(slot - 1) * (ROW_HEIGHT + ROW_GAP), width=ROW_WIDTH, height=ROW_HEIGHT)
            row.pack_propagate(False)
            slot_label = tk.Label(row, text=self._t("main.slot", number=slot),
                                  background="#ffffff", foreground="#000000",
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
        self._render_layout_marker(row_count)
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

    def _round_is_active(self) -> bool:
        rounds = getattr(self, "rounds", None)
        snapshot = rounds.snapshot() if rounds is not None else None
        return snapshot is not None and snapshot.state.value in {"RUNNING", "AWAITING_REVIEW"}

    def _refresh_machine_choices(self) -> None:
        self.project_choice.configure(values=self.profiles.projects)
        available = self.profiles.for_project(self.project.get())
        machines = tuple(profile.machine for profile in available)
        self.machine_choice.configure(values=machines)
        if self.station.get() not in machines and machines:
            self.station.set(machines[0])

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
        self._render_rows()

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
        if not getattr(self, "_closing_ui", False) and not self._round_is_active():
            self.start_monitor()

    def _show_hotkey_warning(self) -> None:
        self._record_app_event("app.hotkey.unavailable", {}, self.hotkey.message)
        messagebox.showwarning(self._t("app.hotkey.title"),
                               self._t("app.hotkey.unavailable"), parent=self.root)

    def _set_monitor_controls(self, monitoring: bool, state_text: Optional[str] = None) -> None:
        if getattr(self, "_closing_ui", False):
            self.start_button.configure(state="disabled")
            self.stop_button.configure(state="disabled")
            self._set_main_monitor_state("monitor.closing")
        else:
            self.start_button.configure(state="disabled" if monitoring else "normal")
            self.stop_button.configure(state="normal" if monitoring else "disabled")
            message_by_text = {
                "啟動中": "monitor.starting", "逾時停止": "monitor.timeout_stopped",
                "啟動失敗": "monitor.start_failed", "監控中": "monitor.active", "待命": "monitor.idle",
            }
            self._set_main_monitor_state(message_by_text.get(
                state_text, "monitor.active" if monitoring else "monitor.idle"))
        for name in ("project_choice", "machine_choice"):
            choice = getattr(self, name, None)
            if choice:
                choice.configure(state="disabled" if monitoring or getattr(self, "_closing_ui", False) else "readonly")

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
        if getattr(self, "_closing_ui", False):
            return
        current = self.rounds.snapshot()
        if current is not None and current.state == "RUNNING":
            return
        station = self.station.get().upper()
        try:
            profile = self._selected_profile()
        except (AttributeError, ProfileError) as error:
            self._record_app_event("app.profile.validation_failed", {"reason": str(error)}, str(error))
            messagebox.showerror(self._t("app.profile.validation_title"),
                                 self._t("app.profile.validation_failed", reason=str(error)),
                                 parent=self.root)
            return
        try:
            prepared = self.round_start_preparation.prepare(
                profile, self.session_root, async_session_writes=True,
            )
        except RoundStartPathError as error:
            self._record_app_event("app.profile.validation_failed", {"reason": str(error)}, str(error))
            messagebox.showerror(self._t("app.profile.validation_title"),
                                 self._t("app.profile.validation_failed", reason=str(error)),
                                 parent=self.root)
            return
        except (AttributeError, ProfileError, ValueError) as error:
            self._record_app_event("app.profile.validation_failed", {"reason": str(error)}, str(error))
            messagebox.showerror(self._t("app.profile.validation_title"),
                                 self._t("app.profile.validation_failed", reason=str(error)),
                                 parent=self.root)
            return

        self.active_profile_snapshot = prepared.profile
        self.start_button.configure(state="disabled")
        self._set_main_monitor_state("monitor.starting")
        self.root.update_idletasks()
        try:
            self._save_preferences()
            snapshot = prepared.start(self.rounds, run_async=True)
            self.active_round_id = snapshot.round_id
            self._reset_rows()
            self._apply_round_snapshot(snapshot)
        except Exception as error:
            self.active_profile_snapshot = None
            self._render_state_marker(None)
            self._set_monitor_controls(False)
            message = "無法開始監控：{}".format(error)
            self._record_app_event("app.profile.save_failed", {"reason": str(error)}, str(error))
            messagebox.showerror(self._t("app.profile.save_title"),
                                 self._t("app.profile.save_failed", reason=str(error)), parent=self.root)
            return
        self._set_monitor_controls(True)
        self._log("{} 監控已開始；本輪時間與啟動前快照已建立。".format(station))

    def stop_monitor(self) -> None:
        snapshot = self.rounds.snapshot()
        if snapshot is not None and snapshot.state in {"RUNNING", "AWAITING_REVIEW"}:
            self.rounds.stop()

    def _render_event_record(self, record: tuple[str, object, Optional[str]]) -> str:
        fallback, localized, round_id = record
        language = getattr(self, "current_language", DEFAULT_LANGUAGE)
        message = render_bilingual_message(localized, language, fallback)
        diagnostic = getattr(localized, "diagnostic", "")
        if not diagnostic and isinstance(localized, dict):
            diagnostic = localized.get("diagnostic", "")
        if isinstance(diagnostic, str) and diagnostic and diagnostic not in message:
            message = "{} — {}".format(message, diagnostic)
        if round_id:
            prefix = "輪次 {}：" if language == TRADITIONAL_CHINESE else "Round {}: "
            return prefix.format(round_id[:10]) + message
        return message

    def _refresh_event_log(self) -> None:
        if not hasattr(self, "_event_records"):
            self._event_records = [(line, None, None) for line in self.event_lines]
        elif len(self.event_lines) != len(self._event_records):
            # Keep compatibility with callers that reset the legacy text list.
            self._event_records = [(line, None, None) for line in self.event_lines]
        self._event_records = self._event_records[-500:]
        self.event_lines = [self._render_event_record(record) for record in self._event_records]
        if self.settings_log and self.settings_log.winfo_exists():
            self.settings_log.configure(state="normal")
            self.settings_log.delete("1.0", "end")
            self.settings_log.insert("1.0", "\n".join(self.event_lines))
            self.settings_log.see("end")
            self.settings_log.configure(state="disabled")

    def _log(self, text: str, localized_message=None, round_id: Optional[str] = None) -> None:
        if not hasattr(self, "_event_records"):
            self._event_records = []
        elif len(self.event_lines) != len(self._event_records):
            self._event_records = [(line, None, None) for line in self.event_lines]
        self._event_records.append((text, localized_message, round_id))
        self._event_records = self._event_records[-500:]
        self.event_lines = [self._render_event_record(record) for record in self._event_records]
        if self.settings_log and self.settings_log.winfo_exists():
            self.settings_log.configure(state="normal")
            self.settings_log.delete("1.0", "end")
            self.settings_log.insert("1.0", "\n".join(self.event_lines))
            self.settings_log.see("end")
            self.settings_log.configure(state="disabled")

    def _drain_events(self) -> None:
        round_snapshot = self.rounds.snapshot() if hasattr(self, "rounds") else None
        if round_snapshot and round_snapshot.source_preparation_pending:
            self.rounds.poll_once()
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
        self._refresh_unsaved_rounds()
        self._refresh_archive_statuses()
        self._refresh_app_event_status()
        self._refresh_app_event_records()
        self.rounds.poll_retention_schedule(self.profile_store.retention_days)
        self._refresh_retention_cleanup_status()
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
        round_id = None
        coordinator = getattr(self, "rounds", None)
        snapshot = coordinator.snapshot() if coordinator is not None else None
        if isinstance(event, RoundEvent):
            if event.round_id != self.active_round_id:
                if event.event.kind in {"audit_write_failed", "save_recovered"}:
                    self._log(event.event.message, event.event.localized_message, event.round_id)
                self._refresh_unsaved_rounds()
                return
            captured = next((item for item in getattr(snapshot, "events", ())
                             if item.round_id == event.round_id and
                             item.sequence == event.sequence), None) if snapshot else None
            round_id = event.round_id
            event = captured.event if captured is not None else event.event
        elif snapshot is not None:
            captured = next((item for item in getattr(snapshot, "events", ())
                             if item.event is event or
                             (event.detail.get("round_id") == item.round_id and
                              event.kind == item.event.kind and
                              event.message == item.event.message and
                              event.slot == item.event.slot)), None)
            if captured is not None:
                event = captured.event
                round_id = captured.round_id
        self._log(event.message, event.localized_message, round_id)
        snapshot = coordinator.snapshot() if coordinator is not None else None
        self._apply_round_snapshot(snapshot)
        if event.slot and snapshot:
            result = next((item for item in snapshot.results if item.slot == event.slot), None)
            if result is not None:
                self._set_row(event.slot, result.sn, result.status)
        if event.kind == "result" and event.status in {"PASS", "FAIL", "NOTEST"}:
            self._bring_dashboard_to_front()
        if event.kind == "conflict_detected":
            self._open_conflict_review()
        if event.kind == "timeout" and event.detail.get("kind") == "start":
            self._set_monitor_controls(False, "逾時停止")
        if event.kind == "timeout" and event.detail.get("kind") == "round":
            self._set_monitor_controls(False, "逾時停止")
            self._open_round_alarm()
        if event.kind == "start_failed":
            self.active_profile_snapshot = None
            self._set_monitor_controls(False, "啟動失敗")
            messagebox.showerror("監控啟動失敗", event.message, parent=self.root)
        if event.kind in {"finished", "stopped"}:
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
            self.conflict_panes = ttk.Panedwindow(body, orient="vertical")
            self.conflict_panes.pack(side="left", fill="both", expand=True, padx=(10, 0))

            summary = ttk.Frame(self.conflict_panes)
            summary.columnconfigure(0, weight=1)
            summary.rowconfigure(1, weight=1)
            self.conflict_position_label = ttk.Label(summary, text="顯示位置：未知")
            self.conflict_position_label.grid(row=0, column=0, sticky="w", pady=(0, 4))
            comparison_font = tkfont.nametofont("TkDefaultFont")
            self.conflict_comparison = tk.Text(
                summary, wrap="none", height=5, state="disabled", font=comparison_font,
                background=LIGHT_BACKGROUND, foreground=TEXT_COLOUR, relief="flat",
                borderwidth=0, padx=4, pady=4,
            )
            self.conflict_comparison_header_font = tkfont.Font(
                root=window, font=comparison_font,
            )
            self.conflict_comparison_header_font.configure(weight="bold")
            self.conflict_comparison_difference_font = tkfont.Font(
                root=window, font=comparison_font,
            )
            self.conflict_comparison_difference_font.configure(weight="bold")
            self.conflict_comparison.tag_configure(
                "comparison_header", font=self.conflict_comparison_header_font,
            )
            self.conflict_comparison.tag_configure(
                "comparison_difference", foreground="#b00020",
                font=self.conflict_comparison_difference_font,
            )
            self._conflict_value_ranges = {}
            self.conflict_comparison.grid(row=1, column=0, sticky="nsew")
            summary_scrollbar = ttk.Scrollbar(
                summary, orient="vertical", command=self.conflict_comparison.yview,
            )
            summary_scrollbar.grid(row=1, column=1, sticky="ns")
            self.conflict_comparison_scrollbar = ttk.Scrollbar(
                summary, orient="horizontal", command=self.conflict_comparison.xview,
            )
            self.conflict_comparison_scrollbar.grid(row=2, column=0, sticky="ew")
            self.conflict_comparison.configure(
                yscrollcommand=summary_scrollbar.set,
                xscrollcommand=self.conflict_comparison_scrollbar.set,
            )

            details = ttk.Frame(self.conflict_panes)
            details.columnconfigure(0, weight=1)
            details.rowconfigure(0, weight=1)
            self.conflict_details = tk.Text(details, wrap="word", height=14, state="disabled",
                                            background=LIGHT_BACKGROUND, foreground=TEXT_COLOUR,
                                            font=("Menlo", 11), relief="solid", borderwidth=1)
            self.conflict_details.grid(row=0, column=0, sticky="nsew")
            details_scrollbar = ttk.Scrollbar(details, orient="vertical",
                                              command=self.conflict_details.yview)
            details_scrollbar.grid(row=0, column=1, sticky="ns")
            self.conflict_details.configure(yscrollcommand=details_scrollbar.set)
            self.conflict_panes.add(summary, weight=4)
            self.conflict_panes.add(details, weight=6)
            window.after_idle(self._set_initial_conflict_sash)
            actions = ttk.Frame(window)
            actions.pack(fill="x", padx=12, pady=(8, 12))
            self.resolve_conflict_original_button = ttk.Button(
                actions, text="保留原結果",
                command=lambda: self._resolve_selected_conflict("keep_original"),
            )
            self.resolve_conflict_original_button.pack(side="left", padx=(0, 8))
            self.resolve_conflict_candidate_button = ttk.Button(
                actions, text="採用新結果",
                command=lambda: self._resolve_selected_conflict("accept_candidate"),
            )
            self.resolve_conflict_candidate_button.pack(side="left")
            self.conflict_close_button = ttk.Button(actions, text="關閉", command=window.withdraw)
            self.conflict_close_button.pack(side="right")
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
            text=self._t("main.review_count", count=len(conflicts)),
            state="normal" if conflicts else "disabled",
        )
        alarm = snapshot.round_alarm if snapshot else None
        alarm_pending = alarm is not None and not alarm.acknowledged_at
        if alarm_pending or conflicts:
            reasons = []
            if alarm_pending and conflicts:
                self._set_main_monitor_state("monitor.awaiting_both", count=len(conflicts))
            elif alarm_pending:
                self._set_main_monitor_state("monitor.awaiting_alarm")
            else:
                self._set_main_monitor_state("monitor.awaiting_conflicts", count=len(conflicts))
        elif snapshot and snapshot.state.value == "COMPLETED":
            self._set_main_monitor_state("monitor.completed")
        elif snapshot and snapshot.state.value == "STOPPED" and snapshot.completion_reason == "manual_stop":
            self._set_main_monitor_state("monitor.stopped")
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
                self._clear_conflict_comparison()

    def _set_initial_conflict_sash(self) -> None:
        if not self.conflict_panes or not self.conflict_panes.winfo_exists():
            return
        height = self.conflict_panes.winfo_height()
        if height > 1:
            self.conflict_panes.sashpos(0, int(height * 0.4))

    def _clear_conflict_comparison(self) -> None:
        if self.conflict_comparison:
            self.conflict_comparison.configure(state="normal")
            self.conflict_comparison.delete("1.0", "end")
            self.conflict_comparison.configure(tabs=("120p", "280p"))
            self.conflict_comparison.configure(state="disabled")
            self._conflict_value_ranges = {}
            self.conflict_comparison.xview_moveto(0)
        if self.conflict_position_label:
            self.conflict_position_label.configure(text="顯示位置：未知")
        if self.conflict_details:
            self.conflict_details.configure(state="normal")
            self.conflict_details.delete("1.0", "end")
            self.conflict_details.insert("1.0", "目前沒有待確認項目。")
            self.conflict_details.configure(state="disabled")
        for button in (self.resolve_conflict_original_button,
                       self.resolve_conflict_candidate_button):
            if button and button.winfo_exists():
                button.configure(state="disabled")

    def _show_selected_conflict(self, _event=None) -> None:
        if (not self.conflict_list or not self.conflict_details or
                not self.conflict_comparison or not self.conflict_position_label):
            return
        selected = self.conflict_list.curselection()
        if not selected or selected[0] >= len(self._conflict_ids):
            self._clear_conflict_comparison()
            return
        snapshot = self.rounds.snapshot()
        if not snapshot:
            self._clear_conflict_comparison()
            return
        conflict_id = self._conflict_ids[selected[0]]
        conflict = next((item for item in snapshot.pending_conflicts
                         if item.conflict_id == conflict_id), None)
        if not conflict:
            self._clear_conflict_comparison()
            return
        for button in (self.resolve_conflict_original_button,
                       self.resolve_conflict_candidate_button):
            if button and button.winfo_exists():
                button.configure(state="normal")

        def source_parts(side):
            if not side.source:
                return "", "未知", (), (False, ())
            normalized = side.source.replace("\\", "/").rstrip("/")
            parts = tuple(part for part in normalized.split("/") if part)
            return (side.source, parts[-1] if parts else "未知", parts[:-1],
                    (normalized.startswith("/"), parts))

        original_path, original_filename, original_directories, original_path_key = source_parts(
            conflict.original,
        )
        candidate_path, candidate_filename, candidate_directories, candidate_path_key = source_parts(
            conflict.candidate,
        )
        original_source = original_filename
        candidate_source = candidate_filename
        paths_differ = original_path_key != candidate_path_key
        if (original_path and candidate_path and paths_differ and
                original_filename == candidate_filename):
            for directory_count in range(1, max(len(original_directories),
                                                len(candidate_directories)) + 1):
                original_hint = "/".join(original_directories[-directory_count:])
                candidate_hint = "/".join(candidate_directories[-directory_count:])
                if original_hint != candidate_hint:
                    original_source = "{} · {}".format(original_filename, original_hint)
                    candidate_source = "{} · {}".format(candidate_filename, candidate_hint)
                    break
            else:
                original_hint = "根目錄" if original_path_key[0] else "相對路徑"
                candidate_hint = "根目錄" if candidate_path_key[0] else "相對路徑"
                original_source = "{} · {}".format(original_filename, original_hint)
                candidate_source = "{} · {}".format(candidate_filename, candidate_hint)

        rows = (
            ("結果", conflict.original.status or "", conflict.candidate.status or "",
             (conflict.original.status or "") != (conflict.candidate.status or "")),
            ("SN", conflict.original.sn or "", conflict.candidate.sn or "",
             (conflict.original.sn or "") != (conflict.candidate.sn or "")),
            ("來源時間", conflict.original.source_time or "",
             conflict.candidate.source_time or "",
             (conflict.original.source_time or "") != (conflict.candidate.source_time or "")),
            ("來源檔名", original_source if original_path else "",
             candidate_source if candidate_path else "", paths_differ),
        )
        display_rows = tuple((label, original or "未知", candidate or "未知", differs)
                             for label, original, candidate, differs in rows)
        self.conflict_position_label.configure(text="顯示位置：{}".format(conflict.slot))
        self.conflict_comparison.configure(state="normal")
        self.conflict_comparison.delete("1.0", "end")
        self.conflict_comparison.insert("end", "項目\t原結果\t新候選\n", "comparison_header")
        self._conflict_value_ranges = {}
        for label, original, candidate, differs in display_rows:
            self.conflict_comparison.insert("end", label + "\t")
            row_ranges = []
            for value in (original, candidate):
                start = self.conflict_comparison.index("end-1c")
                self.conflict_comparison.insert("end", value)
                end = self.conflict_comparison.index("end-1c")
                row_ranges.append((start, end))
                self.conflict_comparison.insert("end", "\t")
            self.conflict_comparison.insert("end", "\n")
            self._conflict_value_ranges[label] = tuple(row_ranges)
            if differs:
                for start, end in row_ranges:
                    self.conflict_comparison.tag_add("comparison_difference", start, end)
        display_font = tkfont.nametofont("TkDefaultFont")
        label_width = max(display_font.measure("項目"),
                          max(display_font.measure(row[0]) for row in display_rows)) + 24
        original_width = max(display_font.measure("原結果"),
                             max(display_font.measure(row[1]) for row in display_rows)) + 24
        original_width = max(140, original_width)
        self.conflict_comparison.configure(
            tabs=("{}p".format(label_width),
                  "{}p".format(label_width + original_width)),
            state="disabled",
        )
        self.conflict_comparison.xview_moveto(0)

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
            self.round_alarm_button.configure(text=self._t("main.round_alarm"), state="disabled")
            if (snapshot and self._round_alarm_window_identity and
                    self._round_alarm_window_identity[0] != snapshot.round_id and
                    self.round_alarm_window and self.round_alarm_window.winfo_exists()):
                self.round_alarm_window.withdraw()
            return
        pending = not alarm.acknowledged_at
        self.round_alarm_button.configure(
            text=self._t("main.round_alarm_pending" if pending else "main.round_alarm_acknowledged"),
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
        self._settings_text_widgets = []
        self._settings_tab_ids = []
        dialog.configure(background=LIGHT_BACKGROUND)
        dialog.title(self._t("app.settings.title"))
        dialog.geometry("720x620")
        dialog.minsize(680, 560)
        dialog.transient(self.root)
        dialog.protocol("WM_DELETE_WINDOW", self._close_settings)
        notebook = ttk.Notebook(dialog)
        self.settings_notebook = notebook
        notebook.pack(fill="both", expand=True, padx=12, pady=12)
        profile_tab = ttk.Frame(notebook, padding=12)
        log_tab = ttk.Frame(notebook, padding=12)
        retention_tab = ttk.Frame(notebook, padding=12)
        self._settings_tab_ids = [
            "app.settings.tab.configuration", "app.settings.tab.events",
            "app.settings.tab.retention",
        ]
        notebook.add(profile_tab, text=self._t(self._settings_tab_ids[0]))
        notebook.add(log_tab, text=self._t(self._settings_tab_ids[1]))
        notebook.add(retention_tab, text=self._t(self._settings_tab_ids[2]))
        self._build_profile_editor_tab(profile_tab)
        self._build_log_tab(log_tab)
        self._build_retention_tab(retention_tab)
        self._apply_settings_language()

    def _build_retention_tab(self, parent: ttk.Frame) -> None:
        """Build the global round-record retention settings tab."""
        self.retention_days_var = tk.StringVar(value=str(self.profile_store.retention_days))
        self.retention_status = tk.StringVar()
        self._set_retention_status("app.settings.retention.status.saved")
        self.retention_effective_label = ttk.Label(
            parent, text=self._t("app.settings.retention.effective",
                                 days=self.profile_store.retention_days))
        self.retention_effective_label.grid(row=0, column=0, columnspan=2, sticky="w", pady=(4, 10))
        self._settings_label(parent, "app.settings.retention.days").grid(
            row=1, column=0, sticky="w", pady=4)
        self.retention_days_entry = ttk.Entry(parent, textvariable=self.retention_days_var, width=16)
        self.retention_days_entry.grid(row=1, column=1, sticky="w", padx=8, pady=4)
        self.retention_save_button = self._settings_button(
            parent, "app.settings.retention.save", self._save_retention_days)
        self.retention_save_button.grid(row=2, column=0, sticky="w", pady=(8, 4))
        ttk.Label(parent, textvariable=self.retention_status, wraplength=620,
                  foreground=TEXT_COLOUR).grid(row=2, column=1, sticky="w", padx=8, pady=(8, 4))
        self.retention_help_label = self._settings_label(
            parent, "app.settings.retention.help")
        self.retention_help_label.configure(
            wraplength=650, justify="left", foreground=TEXT_COLOUR,
        )
        self.retention_help_label.grid(row=3, column=0, columnspan=2, sticky="w", pady=(12, 4))
        self.retention_cleanup_status = tk.StringVar(value="背景清理尚未執行")
        self.retention_cleanup_heading = self._settings_label(
            parent, "app.settings.retention.cleanup.heading")
        self.retention_cleanup_heading.configure(font=("Helvetica", 10, "bold"))
        self.retention_cleanup_heading.grid(row=4, column=0, columnspan=2, sticky="w", pady=(18, 4))
        ttk.Label(parent, textvariable=self.retention_cleanup_status, wraplength=650,
                  justify="left").grid(row=5, column=0, columnspan=2, sticky="w")
        self._refresh_retention_cleanup_status()
        parent.columnconfigure(1, weight=1)

    def _save_retention_days(self) -> None:
        """Validate and persist the global retention duration from the settings UI."""
        assert self.retention_days_var is not None and self.retention_status is not None
        text = self.retention_days_var.get().strip()
        try:
            days = int(text)
        except ValueError:
            reason = "retention days must be a positive integer"
            self._set_retention_status("app.settings.retention.status.invalid")
            self._record_app_event("app.settings.event.retention.invalid", {"reason": reason}, text)
            return
        if days <= 0:
            reason = "retention days must be a positive integer"
            self._set_retention_status("app.settings.retention.status.invalid")
            self._record_app_event("app.settings.event.retention.invalid", {"reason": reason}, text)
            return

        previous = self.profile_store.retention_days
        try:
            cleanup_request = self.rounds.save_retention_setting(
                days, lambda: self.profile_store.save_retention_days(days))
        except ProfileError as error:
            self._set_retention_status("app.settings.retention.status.read_failed",
                                       days=previous, reason=str(error))
            self._record_app_event("app.settings.event.retention.save_failed",
                                   {"reason": str(error)}, str(error))
            return
        except (OSError, TypeError, ValueError) as error:
            self._set_retention_status("app.settings.retention.status.save_failed",
                                       days=previous, reason=str(error))
            self._record_app_event("app.settings.event.retention.save_failed",
                                   {"reason": str(error)}, str(error))
            return

        self.retention_effective_label.configure(
            text=self._t("app.settings.retention.effective", days=days))
        self._record_app_event("app.settings.event.retention.saved", {"days": days})
        self._retention_cleanup_request_status = (
            cleanup_request if cleanup_request.status == "skipped" else None)
        self._refresh_retention_cleanup_status()
        if days < previous:
            self._set_retention_status("app.settings.retention.status.shortened")
        else:
            self._set_retention_status("app.settings.retention.status.updated")

    def _refresh_retention_cleanup_status(self) -> None:
        """Display coordinator cleanup state and durable summaries on the Tk thread."""
        variable = getattr(self, "retention_cleanup_status", None)
        if variable is None:
            return
        status = self.rounds.retention_cleanup_status()
        close_state = self.rounds.close_status().status
        request_status = self._retention_cleanup_request_status
        if (request_status is not None and request_status.status == "skipped" and
                close_state in {"saving", "waiting", "failed"}):
            status = request_status
        elif request_status is not None:
            self._retention_cleanup_request_status = None
        summaries = self.rounds.retention_cleanup_summaries()
        latest = summaries[-1] if summaries else None
        status_message = {
            "idle": "app.settings.retention.cleanup.idle",
            "running": "app.settings.retention.cleanup.running",
            "complete": "app.settings.retention.cleanup.complete",
            "failed": "app.settings.retention.cleanup.failed",
            "skipped": "app.settings.retention.cleanup.skipped",
        }.get(status.status, "app.settings.retention.cleanup.failed")
        detail = self._t(
            status_message,
            reason=self._retention_reason_text(status.message) if status.status == "skipped" else "")
        if status.status == "failed" and latest is None and status.message:
            detail += "\n" + status.message
        if latest is not None:
            outcomes = latest.results
            detail += "\n" + self._t(
                "app.settings.retention.cleanup.summary",
                time=latest.completed_at or latest.started_at,
                days=latest.retention_days,
                deleted=sum(item.outcome == "deleted" for item in outcomes),
                skipped=sum(item.outcome == "skipped" for item in outcomes),
                failed=sum(item.outcome == "failed" for item in outcomes))
            failures = [item for item in outcomes if item.outcome == "failed"]
            if failures:
                items = "；".join(self._t(
                    "app.settings.retention.cleanup.item",
                    round_id=item.round_id or self._t("app.settings.retention.cleanup.heading"),
                    reason=item.reason) for item in failures[:3])
                detail += "\n" + self._t("app.settings.retention.cleanup.failures", items=items)
            skipped = [item for item in outcomes if item.outcome == "skipped"]
            if skipped:
                items = "；".join(self._t(
                    "app.settings.retention.cleanup.item",
                    round_id=item.round_id or self._t("term.test_round"),
                    reason=self._retention_reason_text(item.reason)) for item in skipped[:3])
                detail += "\n" + self._t("app.settings.retention.cleanup.protected", items=items)
        variable.set(detail)

    def _retention_reason_text(self, reason: str) -> str:
        """Translate known cleanup status copy while leaving diagnostic details intact."""
        diagnostic_prefixes = {
            "封存資訊無法讀取：": "archive_read_failed",
            "必要輪次紀錄缺失或無法讀取：": "archive_component_read_failed",
            "必要輪次紀錄無法重建：": "archive_component_rebuild_failed",
        }
        for prefix, message_id in diagnostic_prefixes.items():
            if reason.startswith(prefix):
                return self._t("app.settings.retention.reason." + message_id,
                               diagnostic=reason[len(prefix):])
        message_ids = {
            "關閉保存期間不啟動新清理": "close",
            "封存資訊版本未知": "archive_unknown_version",
            "封存時間無效或缺少時區": "archive_invalid_time",
            "封存資訊格式不正確": "archive_format_invalid",
            "封存資訊完整性驗證失敗": "archive_integrity_failed",
            "封存輪次身分不一致": "archive_round_identity_mismatch",
            "封存完整性資訊缺失": "archive_integrity_missing",
            "封存組成資料不完整": "archive_components_incomplete",
            "封存組成資料格式不正確": "archive_component_format_invalid",
            "封存組成資料路徑不正確": "archive_component_path_invalid",
            "必要輪次紀錄內容已變更": "archive_component_changed",
            "磁碟紀錄未完整保存或輪次身分不一致": "archive_disk_incomplete",
            "關閉保存期間暫停清理": "close",
            "本次 App 執行仍受保護": "protected",
            "可信封存時間缺少時區": "timezone",
            "尚未到保存期限": "not_expired",
            "已完整刪除可信輪次資料": "deleted",
            "封存檔路徑含符號連結或越界": "unsafe_manifest",
            "封存證據無效": "invalid_archive",
            "必要資料路徑含符號連結或不在 App 管理範圍": "unsafe_component",
            "封存路徑與驗證後路徑不一致": "archive_path_mismatch",
            "輪次目錄含未知檔案，整輪保留": "unknown_file",
            "中斷清理輪次目前仍受保護": "recovery_protected",
            "持久刪除計畫格式或輪次組件不可信": "invalid_plan",
            "刪除已完成，補寫先前中斷的摘要": "recovery_summary",
            "目前保存期限尚未到期；已還原中斷時的暫置資料並保留其餘進度":
                "recovered_not_expired",
            "保存期限在清理期間變更，保留剩餘資料等待重新判定": "period_changed",
            "依持久刪除計畫完成中斷復原": "recovered_deleted",
        }
        suffix = message_ids.get(reason)
        return self._t("app.settings.retention.reason." + suffix) if suffix else reason

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
        self.profile_editor_status = tk.StringVar()
        self._set_profile_editor_status("app.settings.profile.status.draft")

        self._settings_label(parent, "app.settings.profile.project").grid(
            row=0, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.profile_editor_project, width=18).grid(
            row=0, column=1, sticky="w", padx=6, pady=4)
        self._settings_label(parent, "app.settings.profile.station_type").grid(
            row=0, column=2, sticky="w", padx=(12, 0), pady=4)
        self.profile_editor_machine_choice = ttk.Combobox(
            parent, textvariable=self.profile_editor_machine,
            values=("DFU", "FCT", "BT"), state="readonly", width=9)
        self.profile_editor_machine_choice.grid(
            row=0, column=3, sticky="w", padx=6, pady=4)
        self._settings_label(parent, "app.settings.profile.platform").grid(
            row=1, column=0, sticky="w", pady=4)
        ttk.Combobox(parent, textvariable=self.profile_editor_platform,
                     values=DEFAULT_PLATFORM_REGISTRY.names, state="readonly", width=16).grid(
            row=1, column=1, sticky="w", padx=6, pady=4)

        self._settings_label(parent, "app.settings.profile.capacity").grid(
            row=1, column=2, sticky="w", padx=(12, 0), pady=4)
        ttk.Entry(parent, textvariable=self.profile_editor_capacity, width=10).grid(
            row=1, column=3, sticky="w", padx=6, pady=4)
        self._settings_label(parent, "app.settings.profile.mapping").grid(
            row=2, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.profile_editor_mapping, width=34).grid(
            row=2, column=1, columnspan=3, sticky="ew", padx=6, pady=4)

        path_labels = (("active", "app.settings.profile.path_active"),
                       ("final", "app.settings.profile.path_final"),
                       ("caseinfo", "app.settings.profile.path_caseinfo"))
        for index, (field, message_id) in enumerate(path_labels):
            row = 3 + index * 2
            self._settings_label(parent, message_id).grid(
                row=row, column=0, columnspan=4, sticky="w", pady=(6, 0))
            ttk.Entry(parent, textvariable=self.profile_editor_paths[field]).grid(
                row=row + 1, column=0, columnspan=3, sticky="ew", padx=6, pady=4)
            self._settings_button(
                parent, "app.settings.profile.choose_directory",
                lambda current=field: self._choose_profile_editor_path(current)).grid(
                row=row + 1, column=3, sticky="e", padx=6, pady=4)

        timeout_labels = (("start", "app.settings.profile.timeout_start"),
                          ("test", "app.settings.profile.timeout_test"),
                          ("round", "app.settings.profile.timeout_round"))
        for row, (field, message_id) in ((9, timeout_labels[0]), (9, timeout_labels[1]),
                                         (10, timeout_labels[2])):
            column = 0 if field in {"start", "round"} else 2
            self._settings_label(parent, message_id).grid(
                row=row, column=column, sticky="w", padx=(12, 0) if column else 0, pady=4)
            ttk.Entry(parent, textvariable=self.profile_editor_timeouts[field], width=16).grid(
                row=row, column=column + 1, sticky="ew", padx=6, pady=4)
        ttk.Label(parent, textvariable=self.profile_editor_status, wraplength=620,
                  foreground=TEXT_COLOUR).grid(row=11, column=0, columnspan=4,
                                               sticky="w", pady=(10, 6))
        edit_actions = ttk.Frame(parent)
        edit_actions.grid(row=12, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        for message_id, action in (("app.settings.profile.load", self._load_profile_editor_selection),
                                   ("app.settings.profile.validate", self._validate_profile_editor),
                                   ("app.settings.profile.apply", self._apply_profile_editor),
                                   ("app.settings.profile.cancel", self._cancel_profile_editor)):
            self._settings_button(edit_actions, message_id, action).pack(side="left", padx=(0, 6))
        file_actions = ttk.Frame(parent)
        file_actions.grid(row=13, column=0, columnspan=4, sticky="ew", pady=(6, 0))
        for message_id, action in (("app.settings.profile.import", self._import_profiles),
                                   ("app.settings.profile.export", self._export_profiles),
                                   ("app.settings.profile.reload", self._reload_profiles)):
            self._settings_button(file_actions, message_id, action).pack(side="left", padx=(0, 6))
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(11, weight=1)

    @staticmethod
    def _mapping_text(mapping) -> str:
        return ", ".join("{}:{}".format(source, display) for source, display in mapping)

    def _choose_profile_editor_path(self, field: str) -> None:
        path = filedialog.askdirectory(
            parent=self.settings_window, mustexist=True,
            title=self._t("app.settings.profile.path.title"))
        if path:
            self.profile_editor_paths[field].set(path)
            self._record_app_event("app.settings.event.profile.path_selected", {"path": path})

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
            self._set_profile_editor_status(
                "app.settings.profile.status.invalid", reason=str(error))
            self._record_app_event("app.settings.event.profile.validation_failed",
                                   {"reason": str(error)}, str(error))
            return None
        self._set_profile_editor_status("app.settings.profile.status.valid")
        return profile

    def _validate_profile_editor(self) -> None:
        profile = self._profile_editor_draft()
        if profile is not None:
            self._record_app_event("app.settings.event.profile.validated", {
                "project": profile.project, "machine": profile.machine,
                "platform": profile.platform,
            })

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
            self._set_profile_editor_status("app.profile.save_failed", reason=str(error))
            self._record_app_event("app.profile.save_failed", {"reason": str(error)}, str(error))
            return
        self.profiles = catalog
        self.profile_error = None
        self.profile_editor_original = profile
        if not self._round_is_active():
            self.project.set(profile.project)
            self.station.set(profile.machine)
        self._refresh_machine_choices()
        if not self._round_is_active():
            self._render_rows()
        self._render_profile_editor(profile)
        self._set_profile_editor_status("app.settings.profile.status.saved")
        self._record_app_event("app.settings.event.profile.saved", {
            "project": profile.project, "machine": profile.machine,
            "platform": profile.platform,
        })

    def _cancel_profile_editor(self) -> None:
        self._render_profile_editor(self.profile_editor_original)
        self._set_profile_editor_status("app.settings.profile.status.cancelled")
        self._record_app_event("app.settings.event.profile.cancelled")

    def _load_profile_editor_selection(self) -> None:
        try:
            profile = self.profiles.get(
                self.profile_editor_project.get().strip(), self.profile_editor_machine.get())
        except ProfileError as error:
            self._set_profile_editor_status(
                "app.settings.profile.status.not_found", reason=str(error))
            self._record_app_event("app.profile.validation_failed",
                                   {"reason": str(error)}, str(error))
            return
        self.profile_editor_original = profile
        self._render_profile_editor(profile)
        self._set_profile_editor_status("app.settings.profile.status.loaded")
        self._record_app_event("app.settings.event.profile.loaded", {
            "project": profile.project, "machine": profile.machine,
            "platform": profile.platform,
        })

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

    def _import_profiles(self) -> None:
        path = filedialog.askopenfilename(
            parent=self.settings_window,
            title=self._t("app.settings.profile.import.title"),
            filetypes=((self._t("app.settings.profile.import.type_json"), "*.json"),
                       (self._t("app.settings.profile.import.type_all"), "*")),
        )
        if not path:
            return
        try:
            document = Path(path).read_text(encoding="utf-8")
            catalog, project, machine = self.profile_store.import_document(
                document, self.project.get(), self.station.get())
        except (OSError, ProfileError, TypeError, ValueError) as error:
            self._set_profile_editor_status("app.profile.import_failed", reason=str(error))
            self._record_app_event("app.profile.import_failed", {"reason": str(error)}, str(error))
            return
        self._activate_profile_catalog(
            catalog, project, machine,
            "app.settings.profile.status.imported",
            "app.settings.profile.status.import_selection",
        )
        self._record_app_event("app.settings.event.profile.imported")

    def _export_profiles(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self.settings_window,
            title=self._t("app.settings.profile.export.title"),
            defaultextension=".json",
            filetypes=((self._t("app.settings.profile.export.type_json"), "*.json"),),
        )
        if not path:
            return
        try:
            MachineProfileStore.export_document(Path(path), self.profiles)
        except OSError as error:
            self._set_profile_editor_status("app.profile.export_failed", reason=str(error))
            self._record_app_event("app.profile.export_failed", {"reason": str(error)}, str(error))
            return
        self._set_profile_editor_status("app.settings.profile.status.exported",
                                        count=len(self.profiles.profiles))
        self._record_app_event("app.settings.event.profile.exported", {
            "count": len(self.profiles.profiles),
        })

    def _reload_profiles(self) -> None:
        catalog, saved_project, saved_machine, error = self.profile_store.load()
        if error:
            self._set_profile_editor_status(
                "app.settings.profile.status.reload_failed", reason=error)
            self._record_app_event("app.startup.preferences_read_failed", {"reason": error}, error)
            return
        self._activate_profile_catalog(
            catalog, saved_project, saved_machine,
            "app.settings.profile.status.reloaded",
            "app.settings.profile.status.reload_selection",
        )
        self._record_app_event("app.settings.event.profile.loaded")

    def _activate_profile_catalog(self, catalog, suggested_project: str, suggested_machine: str,
                                  success_message: str, fallback_message: str) -> None:
        """Activate a valid catalog while preserving or explicitly replacing selection."""
        try:
            profile = catalog.get(self.project.get(), self.station.get())
        except ProfileError:
            profile = None
        if profile is None and self._round_is_active():
            self.profiles = catalog
            self.profile_error = "目前選擇已從配置清單移除；請明確選擇有效專案與機型。"
            editor_profile = catalog.get(suggested_project, suggested_machine)
            self.profile_editor_original = editor_profile
            self._render_profile_editor(editor_profile)
            self._set_profile_editor_status("app.settings.profile.status.active_removed")
            return
        selection_changed = profile is None
        if selection_changed:
            profile = catalog.get(suggested_project, suggested_machine)
        try:
            catalog.get(profile.project, profile.machine)
        except ProfileError:
            raise ProfileError(self._t("app.settings.profile.status.import_selection_missing"))
        self.profiles = catalog
        self.project.set(profile.project)
        self.station.set(profile.machine)
        self.profile_error = None
        self._refresh_machine_choices()
        if not self._round_is_active():
            self._render_rows()
        self.profile_editor_original = profile
        self._render_profile_editor(profile)
        if selection_changed:
            self._set_profile_editor_status(
                fallback_message, project=profile.project, machine=profile.machine)
        else:
            self._set_profile_editor_status(success_message)

    def _build_log_tab(self, parent: ttk.Frame) -> None:
        controls = ttk.Frame(parent)
        controls.pack(fill="x", pady=(0, 8))
        self._settings_button(controls, "app.settings.session.open",
                              self.open_session).pack(side="left")
        self.settings_log = tk.Text(parent, wrap="word", state="disabled", height=26,
                                    background=FIELD_BACKGROUND, foreground=TEXT_COLOUR,
                                    insertbackground=TEXT_COLOUR, selectbackground="#dbeafe",
                                    selectforeground=TEXT_COLOUR)
        self.settings_log.pack(fill="both", expand=True)
        self.settings_log.configure(state="normal")
        self.settings_log.insert("1.0", "\n".join(self.event_lines))
        self.settings_log.configure(state="disabled")

    def _close_settings(self) -> None:
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.destroy()
        self.settings_window = None
        self.settings_log = None
        self._settings_text_widgets = []
        self._settings_tab_ids = []
        self._profile_editor_status_message = None
        self._retention_status_message = None

    def open_session(self) -> None:
        path = self.rounds.session_path or self.session_root
        path.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.Popen(["open", str(path)])
        except OSError as error:
            reason = str(error)
            self._record_app_event("app.settings.event.session.open_failed",
                                   {"reason": reason}, reason)
            messagebox.showerror(self._t("app.settings.session.open"),
                                 self._t("app.settings.session.open_failed", reason=reason),
                                 parent=self.root)

    def close(self) -> None:
        rounds = getattr(self, "rounds", None)
        if rounds is None:
            self._finish_close()
            return
        if self._closing_ui:
            return
        try:
            self._save_preferences()
        except (OSError, ProfileError) as error:
            self._record_app_event("app.profile.save_failed", {"reason": str(error)}, str(error))
            messagebox.showerror(self._t("app.profile.save_title"),
                                 self._t("app.profile.save_failed", reason=str(error)), parent=self.root)
        self._closing_ui = True
        self._set_monitor_controls(self._round_is_active())
        status = rounds.request_close()
        self._show_close_progress(status)
        self._schedule_close_poll(status.generation)

    def _show_close_progress(self, status) -> None:
        if self._close_window is None or not self._close_window.winfo_exists():
            window = tk.Toplevel(self.root)
            self._close_window = window
            window.title("關閉前保存紀錄")
            window.geometry("500x210")
            window.resizable(False, False)
            window.transient(self.root)
            window.protocol("WM_DELETE_WINDOW", self.cancel_close)
            self._close_status_label = ttk.Label(window, text="正在停止來源並確認所有輪次紀錄…",
                                                  wraplength=460, justify="left")
            self._close_status_label.pack(fill="x", padx=18, pady=(18, 8))
            self._close_error_label = ttk.Label(window, text="", wraplength=460, justify="left")
            self._close_error_label.pack(fill="x", padx=18, pady=6)
            actions = ttk.Frame(window)
            actions.pack(fill="x", padx=18, pady=(12, 16))
            self._close_retry_button = ttk.Button(actions, text="重試保存", command=self.retry_close_saves,
                                                  state="disabled")
            self._close_retry_button.pack(side="left")
            ttk.Button(actions, text="取消關閉", command=self.cancel_close).pack(side="right")
        if self._close_window and self._close_window.winfo_exists():
            self._close_window.deiconify()
            self._close_window.lift()
        self._render_close_status(status)

    def _render_close_status(self, status) -> None:
        if not self._close_status_label or not self._close_status_label.winfo_exists():
            return
        labels = {
            "saving": "app.close.saving",
            "waiting": "app.close.waiting",
            "failed": "app.close.failed",
            "complete": "app.close.complete",
            "cancelled": "app.close.cancelled",
        }
        self._close_status_label.configure(
            text=self._t(labels.get(status.status, "app.close.waiting")))
        self._close_error_label.configure(text=status.message)
        if self._close_retry_button:
            self._close_retry_button.configure(state="normal" if status.status == "failed" else "disabled")

    def _schedule_close_poll(self, generation: int) -> None:
        self._close_poll_generation = generation
        self.root.after(100, lambda: self._poll_close_status(generation))

    def _poll_close_status(self, generation: int) -> None:
        if not self._closing_ui or generation != self._close_poll_generation:
            return
        status = self.rounds.close_status()
        if status.generation != generation:
            return
        self._render_close_status(status)
        if status.status == "complete":
            self._finish_close()
        elif status.status in {"saving", "waiting"}:
            self._schedule_close_poll(generation)

    def retry_close_saves(self) -> None:
        if not self._closing_ui:
            return
        status = self.rounds.retry_close_saves()
        self._render_close_status(status)
        self._schedule_close_poll(status.generation)

    def cancel_close(self) -> None:
        if not self._closing_ui:
            return
        status = self.rounds.cancel_close()
        self._closing_ui = False
        self._close_poll_generation = None
        if self._close_window and self._close_window.winfo_exists():
            self._close_window.destroy()
        self._close_window = None
        self._apply_round_snapshot(self.rounds.snapshot())
        self._refresh_unsaved_rounds()
        self._refresh_archive_statuses()

    def _finish_close(self) -> None:
        if self._close_window and self._close_window.winfo_exists():
            self._close_window.destroy()
        self._closing_ui = False
        self.hotkey.close()
        self.app_events.stop()
        self.root.destroy()


if __name__ == "__main__":
    window = tk.Tk()
    B518LogSolutionApp(window)
    window.mainloop()
