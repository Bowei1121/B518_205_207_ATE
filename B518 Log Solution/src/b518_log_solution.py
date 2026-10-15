"""B518 Log Solution — local-only KVM-friendly desktop monitor."""

from __future__ import annotations

import queue
import inspect
import json
import sys
import subprocess
import threading
import time
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, font as tkfont, ttk
from typing import Dict, Optional

from app_event_store import AppEventStore
from cleanup_reasons import present_cleanup_reason
from localized_notice import LanguageRefreshNotifications, show_notice
from historical_event_display import (HistoricalEvent, render_historical_event,
                                      render_historical_event_message)
from historical_event_query import (HistoricalEventDateError, HistoricalEventDateRange,
                                    HistoricalEventDetailService,
                                    HistoricalEventQueryService,
                                    HistoricalEventQueryResult, HistoricalEventSummary,
                                    HistoricalEventSnapshotUnavailable,
                                    parse_historical_event_date_range,
                                    query_historical_events,
                                    recent_historical_event_date_range)
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
    make_bilingual_message, render_bilingual_message, save_state_message_id, translate,
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


def _invoke_historical_query_with_supported_options(sessions, app_path, date_range, **kwargs):
    query_function = query_historical_events
    signature_target = getattr(query_function, "side_effect", None) or query_function
    try:
        parameters = inspect.signature(signature_target).parameters.values()
        supports_initial = (any(parameter.name == "publish_initial"
                                 for parameter in parameters) or
                            any(parameter.kind == parameter.VAR_KEYWORD
                                for parameter in parameters))
    except (TypeError, ValueError):
        supports_initial = False
    if not supports_initial:
        kwargs.pop("publish_initial", None)
    return query_function(sessions, app_path, date_range, **kwargs)


APP_ROOT = Path.home() / "Library" / "Application Support" / "B518LogSolution"
PREFS_PATH = APP_ROOT / "preferences.json"
RESOURCE_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
VERSION_PATH = RESOURCE_ROOT / "VERSION"
try:
    APP_VERSION = VERSION_PATH.read_text(encoding="utf-8").strip()
except OSError:
    APP_VERSION = "unknown"
ASSETS_ROOT = RESOURCE_ROOT / "assets"
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
TOOLBAR_ICON_ROWS = {
    "settings": (
        "...##...##...", "..###...###..", "..###.##.###..", ".############.",
        "##.########.##", "##.##....##.##", "...##....##...", "...##....##...",
        "##.##....##.##", "##.########.##", ".############.", "..###.##.###..",
        "..###...###..", "...##...##...",
    ),
    "review": (
        ".......##.......", "......####......", ".....######.....", "....########....",
        "...##########...", "..############..", ".##############.", "################",
        "################", ".......##.......", ".......##.......", ".......##.......",
        ".......##.......", ".......##.......", ".......##.......", ".......##.......",
    ),
    "alarm": (
        ".......####.......", "......######......", ".....########.....", "....##########....",
        "...############...", "...############...", "..##############..", "..##############..",
        "..##############..", "..##############..", "...############...", "...############...",
        "....##########....", ".....########......", "......######.......", "....############..",
        "...#############..", "..##############...", ".################..", "##################",
    ),
    "language": (
        ".....########.....", "...############...", "..##############..", ".################.",
        "##################", "####...##...######", "###....##....#####", "##.....##.....####",
        "##.....##.....####", "##.....##.....####", "###....##....#####", "####...##...######",
        "##################", ".################.", "..##############..", "...############...",
        ".....########.....",
    ),
}


def toolbar_icon(master: tk.Misc, name: str) -> tk.PhotoImage:
    """Build stable monochrome toolbar artwork without platform emoji fonts."""
    rows = TOOLBAR_ICON_ROWS[name]
    width = max(map(len, rows))
    image = tk.PhotoImage(master=master, width=width, height=len(rows))
    for y, row in enumerate(rows):
        for x, pixel in enumerate(row):
            if pixel == "#":
                image.put(TEXT_COLOUR, (x, y))
    return image


class _LocalizedControlHint:
    """Show one localized hint for a Tk or ttk control, with owned lifecycle."""

    def __init__(self, widget: tk.Widget, text_provider):
        self._widget = widget
        self._text_provider = text_provider
        self._after_id = None
        self._window = None
        self._label = None
        self._bindings = []
        for sequence, callback in (
                ("<Enter>", self._schedule), ("<FocusIn>", self._schedule),
                ("<Leave>", self._hide), ("<FocusOut>", self._hide)):
            binding_id = widget.bind(sequence, callback, add="+")
            self._bindings.append((sequence, binding_id))
        if isinstance(widget, tk.Menubutton):
            for sequence in ("<ButtonPress-1>", "<KeyPress-space>",
                             "<KeyPress-Return>", "<KeyPress-Down>"):
                binding_id = widget.bind(sequence, self._hide, add="+")
                self._bindings.append((sequence, binding_id))
        self._destroy_binding = widget.bind("<Destroy>", self._on_destroy, add="+")

    def _disabled(self, widget) -> bool:
        try:
            if hasattr(widget, "instate"):
                return widget.instate(["disabled"])
            return str(widget.cget("state")) == "disabled"
        except (tk.TclError, KeyError):
            return True

    def _menu_is_posted(self, widget) -> bool:
        if not isinstance(widget, tk.Menubutton):
            return False
        try:
            menu = widget.cget("menu")
            return bool(menu and widget.tk.call("winfo", "viewable", menu))
        except tk.TclError:
            return False

    def refresh(self) -> None:
        widget = self._widget
        if widget is None:
            return
        try:
            if self._disabled(widget):
                self._hide()
            elif self._label is not None and self._label.winfo_exists():
                self._label.configure(text=self._text_provider())
        except tk.TclError:
            self._hide()

    def close(self) -> None:
        self._hide()
        widget = self._widget
        if widget is None:
            return
        for sequence, binding_id in self._bindings:
            if binding_id:
                try:
                    widget.unbind(sequence, binding_id)
                except tk.TclError:
                    pass
        if self._destroy_binding:
            try:
                widget.unbind("<Destroy>", self._destroy_binding)
            except tk.TclError:
                pass
        self._bindings.clear()
        self._widget = None

    def _schedule(self, _event=None) -> None:
        widget = self._widget
        if widget is None:
            return
        try:
            if (not widget.winfo_exists() or self._disabled(widget) or
                    self._menu_is_posted(widget)):
                self._hide()
                return
            self._cancel_after()
            self._after_id = widget.after(450, self._show)
        except tk.TclError:
            self._hide()

    def _show(self) -> None:
        self._after_id = None
        widget = self._widget
        if widget is None:
            return
        try:
            if (not widget.winfo_exists() or self._disabled(widget) or
                    self._menu_is_posted(widget)):
                return
            if self._window is not None and self._window.winfo_exists():
                self._label.configure(text=self._text_provider())
                return
            window = tk.Toplevel(widget.winfo_toplevel())
            window.overrideredirect(True)
            label = tk.Label(
                window, text=self._text_provider(), anchor="w", justify="left",
                background="#fffbe6", foreground=TEXT_COLOUR, borderwidth=1,
                relief="solid", padx=6, pady=3, wraplength=320)
            label.pack()
            window.update_idletasks()
            x = widget.winfo_rootx()
            y = widget.winfo_rooty() + widget.winfo_height() + 3
            if y + window.winfo_reqheight() > widget.winfo_screenheight():
                y = widget.winfo_rooty() - window.winfo_reqheight() - 3
            x = min(max(2, x), max(2, widget.winfo_screenwidth() -
                                   window.winfo_reqwidth() - 2))
            window.geometry("+{}+{}".format(x, max(2, y)))
            self._window = window
            self._label = label
        except tk.TclError:
            self._hide()

    def _hide(self, _event=None) -> None:
        self._cancel_after()
        window = self._window
        self._window = None
        self._label = None
        if window is not None:
            try:
                if window.winfo_exists():
                    window.destroy()
            except tk.TclError:
                pass

    def _cancel_after(self) -> None:
        widget = self._widget
        after_id = self._after_id
        self._after_id = None
        if widget is not None and after_id is not None:
            try:
                widget.after_cancel(after_id)
            except tk.TclError:
                pass

    def _on_destroy(self, event) -> None:
        if event.widget is self._widget:
            widget = self._widget
            if isinstance(widget, tk.Menubutton):
                try:
                    widget.tk.call("set", "::tk::Priv(inMenubutton)", "")
                except tk.TclError:
                    pass
            self._hide()
            self._bindings.clear()
            self._destroy_binding = None
            self._widget = None


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
        self._ui_destroyed = False
        self._after_ids: set[str] = set()
        self._close_after_id = None
        self.root.bind("<Destroy>", self._on_root_destroy, add="+")
        self.session_root = Path(session_root) if session_root else APP_ROOT / "sessions"
        self.root.resizable(False, False)
        self.events: queue.Queue[RoundEvent] = queue.Queue()
        self.hotkey_events: queue.Queue[bool] = queue.Queue()
        self.rounds = RoundCoordinator(
            self.events.put, audit_root=self.session_root,
            retention_ledger_path=self.session_root.parent / "round-retention-ledger.json")
        self.app_events = AppEventStore(app_event_path or APP_ROOT / "app-events.json", clock=app_event_clock)
        self.rounds.register_app_event_store(self.app_events, self.session_root.parent)
        self._historical_query_service = HistoricalEventQueryService(
            self.session_root, getattr(self.app_events, "path", None),
            query_function=lambda sessions, app_path, date_range, **kwargs:
            _invoke_historical_query_with_supported_options(
                sessions, app_path, date_range, **kwargs),
            index_path=self.session_root.parent / "historical-event-query-index.sqlite3")
        self._historical_detail_service = HistoricalEventDetailService()
        self._closing_ui = False
        self._close_window = None
        self._close_status_label = None
        self._close_language_reason_label = None
        self._close_error_label = None
        self._close_retry_button = None
        self._close_cancel_button = None
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
        self._language_refresh_failures = {}
        self._language_refresh_notifications = None
        self._monitor_state_message = "monitor.idle"
        self._monitor_state_parameters: dict[str, object] = {}
        self._current_save_state = "waiting"
        self.project = tk.StringVar(master=self.root, value=selected_project)
        self.station = tk.StringVar(master=self.root, value=selected_machine)
        self.status_rows: Dict[int, Dict[str, tk.Label]] = {}
        self.template_labels: Dict[str, tk.Label] = {}
        self.kvm_result_blocks: Dict[int, tk.Label] = {}
        self._rendered_marker_state: Optional[MarkerState] = None
        self.company_logo: Optional[tk.PhotoImage] = None
        self.company_logo_slot: Optional[tk.Frame] = None
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
        self._app_diagnostics_records = ()
        self._unregister_settings_language_receiver = None
        self._unregister_app_diagnostics_language_receiver = None
        self._unregister_historical_event_language_receiver = None
        self._unregister_conflict_language_receiver = None
        self._unregister_round_alarm_language_receiver = None
        self.historical_event_window = None
        self.historical_event_list = None
        self.historical_event_detail = None
        self.historical_event_heading = None
        self.historical_event_detail_heading = None
        self.historical_event_refresh_button = None
        self.historical_event_cancel_button = None
        self.historical_event_retry_button = None
        self.historical_previous_button = None
        self.historical_next_button = None
        self.historical_page_label = None
        self.historical_range_label = None
        self.historical_start_label = None
        self.historical_end_label = None
        self.historical_range_choice = None
        self.historical_start_var = None
        self.historical_end_var = None
        self.historical_start_entry = None
        self.historical_end_entry = None
        self.historical_date_error = None
        self.historical_query_status = None
        self._historical_control_hints = ()
        self._historical_event_records: tuple[HistoricalEventSummary, ...] = ()
        self._historical_event_selected_key: Optional[str] = None
        self._historical_event_selected_detail: Optional[HistoricalEvent] = None
        self._historical_event_detail_request_id = None
        self._historical_event_detail_status_key = None
        self._historical_detail_after_id = None
        self._historical_query_page_number = 1
        self._historical_page_request_id = None
        self._historical_page_after_id = None
        self._historical_requested_page_number = None
        self._historical_restore_after_id = None
        self._historical_range_mode = "last90"
        self._historical_date_error_key = None
        self._updating_historical_controls = False
        self._historical_query_result: Optional[HistoricalEventQueryResult] = None
        self._historical_query_status_key = "app.settings.history.not_queried"
        self._historical_query_status_parameters = {}
        self._historical_query_diagnostics = ()
        self._historical_showing_diagnostics = False
        self._historical_diagnostic_page_number = 1
        self._historical_query_generation = None
        self._historical_query_view_generation = 0
        self._historical_query_after_id = None
        self._historical_query_inflight_range: Optional[HistoricalEventDateRange] = None
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
        self._rendered_conflict_id: Optional[str] = None
        self._rendered_conflict_signature = None
        self._updating_conflict_list = False
        self.conflict_instructions: Optional[ttk.Label] = None
        self.conflict_list: Optional[tk.Listbox] = None
        self.conflict_list_xscrollbar: Optional[ttk.Scrollbar] = None
        self.conflict_panes: Optional[ttk.Panedwindow] = None
        self.conflict_position_label: Optional[ttk.Label] = None
        self.conflict_comparison: Optional[tk.Text] = None
        self.conflict_comparison_scrollbar: Optional[ttk.Scrollbar] = None
        self.conflict_details: Optional[tk.Text] = None
        self._conflict_ids: list[str] = []
        self.round_alarm_window: Optional[tk.Toplevel] = None
        self.round_alarm_message: Optional[ttk.Label] = None
        self.round_alarm_ack_button: Optional[ttk.Button] = None
        self.round_alarm_close_button: Optional[ttk.Button] = None
        self._round_alarm_window_identity: Optional[tuple[str, str]] = None
        self._rendered_alarm_view_state = None
        self._configure_appearance()
        self._record_startup_diagnostics()
        self._build()
        self._language_refresh_notifications = LanguageRefreshNotifications(
            self.root, self._language_refresh_result)
        self._main_language_receiver = self.register_language_receiver(
            lambda: self._t("language.refresh.main_window"),
            self._apply_main_language, self.root.winfo_exists)
        self.hotkey: HotkeyRegistration = hotkey_factory(
            lambda events=self.hotkey_events: events.put(True))
        self.root.bind("<Command-Shift-M>", self._on_local_hotkey)
        self._position_window()
        self._schedule_ui(150, self._drain_events)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.rounds.start_retention_schedule(self.profile_store.retention_days)
        if self.profile_error:
            self._schedule_ui(300, self._show_startup_warning)
        if self.profile_store.language_error:
            self._schedule_ui(300, self._show_invalid_language_warning)
        if self.app_events.status().error:
            self._schedule_ui(300, self._show_app_event_store_warning)
        if not self.hotkey.available:
            self._schedule_ui(300, self._show_hotkey_warning)

    def _schedule_ui(self, delay: int | str, callback, *args):
        """Own every App timer so its Tcl command cannot outlive the root."""
        if self._ui_destroyed:
            return None

        def invoke():
            self._after_ids.remove(after_id)
            if not self._ui_destroyed:
                callback(*args)

        after_id = self.root.after(delay, invoke)
        self._after_ids.add(after_id)
        return after_id

    def _cancel_ui_timer(self, after_id) -> None:
        if after_id in self._after_ids:
            self.root.after_cancel(after_id)
            self._after_ids.remove(after_id)

    def _on_root_destroy(self, event) -> None:
        if event.widget is not self.root or self._ui_destroyed:
            return
        self._ui_destroyed = True
        language_button = getattr(self, "language_button", None)
        if language_button is not None:
            try:
                language_button.tk.call("set", "::tk::Priv(inMenubutton)", "")
            except tk.TclError:
                pass
        if hasattr(self, "_historical_query_service"):
            self._historical_query_service.shutdown()
        if hasattr(self, "_historical_detail_service"):
            self._historical_detail_service.shutdown()
        historical_result = getattr(self, "_historical_query_result", None)
        if historical_result is not None:
            historical_result.close()
        if self._language_refresh_notifications is not None:
            self._language_refresh_notifications.close()
        self._language_refresh_notifications = None
        self._main_language_receiver = None
        for hint in getattr(self, "_toolbar_hints", ()):
            hint.close()
        self._toolbar_hints = ()
        for after_id in tuple(self._after_ids):
            self._cancel_ui_timer(after_id)
        self._close_after_id = None
        # A hotkey registration must never keep the UI alive from a worker.
        if hasattr(self, "hotkey"):
            self.hotkey.close()
        # Tk variables, images, fonts, widgets and Style retain the interpreter.
        # Release our entire UI resource graph here, on its creating thread,
        # even when an embedding caller destroys root directly. Domain state
        # and pending durable writes remain available to their own workers.
        def release(value):
            if isinstance(value, (tk.Misc, tk.Variable, tk.Image, tkfont.Font, ttk.Style)):
                return None
            if isinstance(value, dict):
                return {key: release(item) for key, item in value.items()}
            if isinstance(value, list):
                return [release(item) for item in value]
            if isinstance(value, tuple):
                return tuple(release(item) for item in value)
            return value

        for name, value in tuple(vars(self).items()):
            setattr(self, name, release(value))

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
        self.style.configure("Toolbar.TButton", background=LIGHT_BACKGROUND,
                             foreground=TEXT_COLOUR, padding=(3, 3), borderwidth=0)
        self.style.map("Toolbar.TButton", background=[("active", "#e5e7eb"),
                                                        ("pressed", "#d1d5db"),
                                                        ("disabled", LIGHT_BACKGROUND)])
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
        header = tk.Frame(body, background=LIGHT_BACKGROUND, height=35)
        header.pack(fill="x")
        header.pack_propagate(False)
        self.toolbar_icons = {name: toolbar_icon(self.root, name) for name in TOOLBAR_ICON_ROWS}
        self._toolbar_hints = []
        self.settings_button = ttk.Button(
            header, image=self.toolbar_icons["settings"], command=self.open_settings,
            style="Toolbar.TButton", takefocus=True,
        )
        self.settings_button.pack(side="left", padx=(0, 3))
        self._toolbar_hints.append(_LocalizedControlHint(self.settings_button,
                                                 lambda: self._t("main.settings")))
        self._build_company_identity(header)
        tk.Frame(header, background=LIGHT_BACKGROUND).pack(side="left", fill="x", expand=True)
        self.language_choice = tk.StringVar(master=self.root, value=self.current_language)
        self.language_button = tk.Menubutton(
            header, image=self.toolbar_icons["language"],
            background=LIGHT_BACKGROUND, foreground=TEXT_COLOUR,
            activebackground="#e5e7eb", relief="flat", borderwidth=0,
            takefocus=True,
        )
        self.language_menu = tk.Menu(self.language_button, tearoff=False)
        for language, native_name in LANGUAGE_OPTIONS:
            self.language_menu.add_radiobutton(
                label=native_name, variable=self.language_choice, value=language,
                command=lambda selected=language: self._select_language(selected),
            )
        self.language_button.configure(menu=self.language_menu)
        self.language_button.pack(side="right", padx=(2, 0))
        for key in ("<space>", "<Return>", "<Down>"):
            self.language_button.bind(key, self._post_language_menu)
        self.language_button.bind("<Escape>", self._cancel_language_menu)
        self._toolbar_hints.append(_LocalizedControlHint(
            self.language_button, lambda: self._t(
                "main.language", current_language=language_name(self.current_language))))

        self.round_alarm_button = ttk.Button(
            header, image=self.toolbar_icons["alarm"], command=self._open_round_alarm,
            style="Toolbar.TButton", state="disabled", takefocus=True,
        )
        self.round_alarm_button.pack(side="right")
        self._toolbar_hints.append(_LocalizedControlHint(
            self.round_alarm_button, lambda: self._t(self._round_alarm_hint_id())))
        self.review_group = tk.Frame(header, background=LIGHT_BACKGROUND)
        self.review_group.pack(side="right", padx=(2, 2))
        self.review_button = ttk.Button(
            self.review_group, image=self.toolbar_icons["review"], command=self._open_conflict_review,
            style="Toolbar.TButton", state="disabled", takefocus=True,
        )
        self.review_button.pack(side="left")
        self.review_count = tk.Label(
            self.review_group, text="0", width=8, anchor="center",
            background=LIGHT_BACKGROUND, foreground=TEXT_COLOUR,
            font=("Helvetica", 10, "bold"),
        )
        self.review_count.pack(side="left", padx=(1, 0))
        self._toolbar_hints.append(_LocalizedControlHint(
            self.review_button, lambda: self._t("main.review_count",
                                                count=self._pending_conflict_count())))

        selection = tk.Frame(body, background=LIGHT_BACKGROUND)
        selection.pack(fill="x", pady=(3, 3))
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
        self.start_button.pack(fill="x", pady=(0, 2))
        self.monitor_state = ttk.Label(controls, text="", anchor="center",
                                       font=("Helvetica", MAIN_FONT_SIZE, "bold"))
        self.monitor_state.pack(fill="x", pady=(0, 2))
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
        self.unsaved_round_choice = tk.StringVar(master=self.root, value="")
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
        self.language_refresh_banner = self.app_event_status_label
        self.app_event_status_label.pack(side="left", fill="x", expand=True)
        self.language_refresh_retry_button = ttk.Button(
            app_event_controls, text=self._t("language.refresh.retry"),
            command=self.retry_language_refresh, state="disabled")
        self.language_refresh_retry_button.pack(side="right", padx=(4, 0))
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
        self.language_button.configure(
            relief="sunken" if self._language_save_error else "raised")
        self._refresh_language_entry()
        self.project_label.configure(text=self._t("main.project"))
        self.machine_label.configure(text=self._t("main.machine_type"))
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
        self.language_refresh_retry_button.configure(text=self._t("language.refresh.retry"))
        self._set_main_monitor_state(self._monitor_state_message,
                                     **self._monitor_state_parameters)
        self._render_conflict_review_button()
        self._render_round_alarm_button()
        self._render_station_title()
        self._render_save_status()
        self._refresh_unsaved_rounds()
        self._refresh_archive_statuses()
        self._refresh_main_round_labels()
        self._restore_captured_round_messages_for_display()
        self._refresh_event_log()
        self._refresh_app_event_status(update_diagnostics=False)
        for hint in self._toolbar_hints:
            hint.refresh()

    def register_language_receiver(self, name, refresh, alive):
        """Register an App-owned window for the existing language notification."""
        if self._language_refresh_notifications is None:
            return lambda: None
        return self._language_refresh_notifications.register(name, refresh, alive)

    def retry_language_refresh(self) -> None:
        if self._closing_ui or self._language_refresh_notifications is None:
            return
        self._language_refresh_notifications.retry()

    def _language_refresh_result(self, failures, newly_failed) -> None:
        self._language_refresh_failures = dict(failures)
        try:
            if not self.root.winfo_exists():
                return
        except tk.TclError:
            return

        def configure_if_alive(widget, **options):
            if widget is None:
                return
            try:
                if widget.winfo_exists():
                    widget.configure(**options)
            except tk.TclError:
                # A receiver can unregister while Tk is already destroying
                # its parent subtree. Failure reporting must not revive it.
                return

        if failures:
            names = ", ".join(sorted({name() if callable(name) else name
                                      for name, _reason in failures.values()}))
            configure_if_alive(
                self.app_event_status_label,
                text=self._t("language.refresh.failed", windows=names))
            configure_if_alive(self.language_refresh_retry_button,
                               state="disabled" if self._closing_ui else "normal")
        else:
            configure_if_alive(self.language_refresh_retry_button, state="disabled")
            self._refresh_app_event_status(update_diagnostics=False)
        for _token, (name, reason) in newly_failed.items():
            try:
                label = name() if callable(name) else name
                self._record_app_event(
                    "app.language.refresh_failed", {}, "{}: {}".format(label, reason))
            except Exception:
                # A failed diagnostic must not recursively fail notification.
                continue

    def _show_notice(self, title_id, message_id, parameters=None, diagnostic="", captured=None):
        parameters = dict(parameters or {})
        original_reason = parameters.get("reason", "")
        diagnostic = diagnostic or original_reason

        def text_provider():
            display_parameters = dict(parameters)
            if original_reason:
                display_parameters["reason"] = self._t("app.notice.diagnostic_below")
            message = (render_bilingual_message(captured, self.current_language)
                       if captured is not None else self._t(message_id, **display_parameters))
            if diagnostic:
                message += "\n\n{}: {}".format(self._t("app.diagnostic.raw"), diagnostic)
            return self._t(title_id), message, self._t("app.notice.ok")

        title, message, _button = text_provider()
        show_notice(title, message, parent=self.root, text_provider=text_provider,
                    register_refresh=self.register_language_receiver,
                    receiver_name=lambda: self._t(title_id))

    def _settings_label(self, parent, message_id: str, **kwargs):
        widths = {
            "app.settings.profile.project": 13,
            "app.settings.profile.station_type": 13,
            "app.settings.profile.platform": 13,
            "app.settings.profile.capacity": 13,
            "app.settings.retention.days": 28,
            "app.settings.retention.cleanup.heading": 30,
        }
        widget = ttk.Label(parent, text=self._t(message_id, **kwargs),
                           width=widths.get(message_id, 20))
        self._settings_text_widgets.append((widget, message_id))
        return widget

    def _settings_wrapped_label(self, parent, message_id: str,
                                width: int = 140, height: int = 36) -> ttk.Frame:
        """Reserve the same two-line label box for long English and Chinese field names."""
        frame = ttk.Frame(parent, width=width, height=height)
        frame.grid_propagate(False)
        frame.pack_propagate(False)
        label = ttk.Label(frame, text=self._t(message_id), wraplength=width,
                          justify="left", anchor="w")
        label.pack(fill="both", expand=True)
        self._settings_text_widgets.append((label, message_id))
        return frame

    def _settings_button(self, parent, message_id: str, command):
        widths = {
            "app.settings.profile.choose_directory": 20,
            "app.settings.profile.load": 25,
            "app.settings.profile.validate": 19,
            "app.settings.profile.apply": 18,
            "app.settings.profile.cancel": 16,
            "app.settings.profile.import": 21,
            "app.settings.profile.export": 21,
            "app.settings.profile.reload": 30,
            "app.settings.session.open": 24,
            "app.settings.history.open": 24,
            "app.settings.retention.save": 18,
            "app.settings.retention.cleanup.retry": 27,
        }
        widget = ttk.Button(parent, text=self._t(message_id), command=command,
                            width=widths.get(message_id, 20))
        self._settings_text_widgets.append((widget, message_id))
        return widget

    @staticmethod
    def _settings_scrollable_tab(parent: ttk.Frame) -> ttk.Frame:
        """Keep long settings pages reachable without changing control positions on translation."""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        canvas = tk.Canvas(parent, background=LIGHT_BACKGROUND, highlightthickness=0,
                           borderwidth=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        content = ttk.Frame(canvas, padding=12)
        window_id = canvas.create_window((0, 0), window=content, anchor="nw")

        def update_scroll_region(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def fit_content(event):
            canvas.itemconfigure(window_id, width=event.width)

        content.bind("<Configure>", update_scroll_region, add="+")
        canvas.bind("<Configure>", fit_content, add="+")
        return content

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
        self._refresh_event_log()

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
        self.review_count.configure(text=str(len(conflicts)))
        self.review_button.configure(state="normal" if conflicts else "disabled")
        if len(getattr(self, "_toolbar_hints", ())) > 3:
            self._toolbar_hints[3].refresh()
        alarm = snapshot.round_alarm if snapshot else None
        alarm_pending = alarm is not None and not alarm.acknowledged_at
        self.round_alarm_button.configure(
            state="normal" if alarm_pending and snapshot.round_alarm_ready else "disabled",
        )
        if len(getattr(self, "_toolbar_hints", ())) > 2:
            self._toolbar_hints[2].refresh()
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
        self._render_main_title()

    def _render_main_title(self) -> None:
        if hasattr(self, "project") and hasattr(self, "station"):
            self.root.title("{} {} {}".format(
                self.project.get(), self.station.get().upper(),
                self._t("app.title", version=APP_VERSION)))

    def _pending_conflict_count(self) -> int:
        snapshot = self.rounds.snapshot() if hasattr(self, "rounds") else None
        return len(snapshot.pending_conflicts) if snapshot else 0

    def _round_alarm_hint_id(self) -> str:
        snapshot = self.rounds.snapshot() if hasattr(self, "rounds") else None
        alarm = snapshot.round_alarm if snapshot else None
        if alarm is None:
            return "main.round_alarm"
        return ("main.round_alarm_pending" if not alarm.acknowledged_at
                else "main.round_alarm_acknowledged")

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

    def _refresh_app_event_status(self, update_main: bool = True,
                                  update_diagnostics: bool = True) -> None:
        status = self.rounds.app_event_status()
        if status is None:
            return
        if status.status == "failed":
            text = self._t("app.save.failed", reason=status.error)
        elif status.status == "saving":
            text = self._t("app.save.pending", count=status.pending_count)
        else:
            text = self._t("app.save.complete")
        if update_main and self.app_event_status_label and self.app_event_status_label.winfo_exists():
            if not self._language_refresh_failures:
                self.app_event_status_label.configure(text=text)
        if (update_diagnostics and self.app_diagnostics_status
                and self.app_diagnostics_status.winfo_exists()):
            self.app_diagnostics_status.configure(text=text)
        if (update_diagnostics and self.app_diagnostics_history
                and self.app_diagnostics_history.winfo_exists()):
            history = "；".join(status.error_history) if status.error_history else "—"
            self.app_diagnostics_history.configure(text=self._t(
                "app.diagnostic.save_history",
                status=self._t("app.diagnostic.save_state." + status.status),
                history=history))
        if (update_diagnostics and self.app_diagnostics_retry_button
                and self.app_diagnostics_retry_button.winfo_exists()):
            self.app_diagnostics_retry_button.configure(
                state="normal" if status.status == "failed" else "disabled")

    def _refresh_app_event_records(self, force: bool = False) -> None:
        if not self.app_diagnostics_window or not self.app_diagnostics_window.winfo_exists():
            return
        revision = self.rounds.app_event_revision()
        if not force and revision == self._last_app_event_revision:
            return
        records = self.rounds.app_event_records()
        self._app_diagnostics_records = tuple(records)
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
            self.event_lines.append(self._render_event_record((fallback, localized, None)))
            added_to_main_log = True
        if added_to_main_log:
            self._refresh_event_log()
        self._render_app_diagnostics_records(records)

    def _apply_app_diagnostics_language(self) -> None:
        """Re-render the displayed App-event snapshot without reading it again."""
        window = self.app_diagnostics_window
        if window is None or not window.winfo_exists():
            return
        window.title(self._t("app.diagnostic.heading"))
        self._refresh_app_event_status(update_main=False)
        self._render_app_diagnostics_records(self._app_diagnostics_records)

    def _render_app_diagnostics_records(self, records) -> None:
        if not self.app_diagnostics_list or not self.app_diagnostics_list.winfo_exists():
            return
        list_top = self.app_diagnostics_list.yview()[0]
        detail_top = self.app_diagnostics_detail.yview()[0]
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
        selected_index = None
        if prior_id:
            selected_index = next((index for index, record in enumerate(records)
                                   if record.get("event_id") == prior_id), None)
        elif selected:
            selected_index = selected[0] if selected[0] < len(records) else None
        elif records:
            selected_index = len(records) - 1
        if selected_index is not None:
            self.app_diagnostics_list.selection_set(selected_index)
            self._show_app_event_detail(selected_index, records)
        elif prior_id is not None:
            self._selected_app_event_id = None
        self.app_diagnostics_list.yview_moveto(list_top)
        self.app_diagnostics_detail.yview_moveto(detail_top)

    def _show_app_event_detail(self, index: Optional[int] = None, records=None) -> None:
        if not self.app_diagnostics_detail or not self.app_diagnostics_detail.winfo_exists():
            return
        if index is None:
            selected = self.app_diagnostics_list.curselection() if self.app_diagnostics_list else ()
            index = selected[0] if selected else None
        if records is None:
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
            self.app_diagnostics_window.title(self._t("app.diagnostic.heading"))
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
        ttk.Button(footer_row, text=self._t("app.diagnostic.close"),
                   command=self._close_app_diagnostics_window).pack(side="right")
        self.app_diagnostics_history = ttk.Label(footer, text="", wraplength=720, justify="left")
        self.app_diagnostics_history.pack(fill="x", pady=(5, 0))
        window.protocol("WM_DELETE_WINDOW", self._close_app_diagnostics_window)
        window.bind("<Destroy>", self._on_app_diagnostics_destroy, add="+")
        self._unregister_app_diagnostics_language_receiver = self.register_language_receiver(
            lambda: self._t("app.diagnostic.heading"),
            self._apply_app_diagnostics_language,
            lambda: self.app_diagnostics_window is window and window.winfo_exists(),
        )
        self._refresh_app_event_records()
        self._refresh_app_event_status()

    def _on_app_diagnostics_destroy(self, event) -> None:
        if event.widget is not self.app_diagnostics_window:
            return
        unregister = self._unregister_app_diagnostics_language_receiver
        self._unregister_app_diagnostics_language_receiver = None
        if unregister is not None:
            unregister()
        self.app_diagnostics_window = None
        self.app_diagnostics_list = None
        self.app_diagnostics_detail = None
        self.app_diagnostics_status = None
        self.app_diagnostics_history = None
        self.app_diagnostics_retry_button = None
        self._selected_app_event_id = None

    def _close_app_diagnostics_window(self) -> None:
        window = self.app_diagnostics_window
        if window is not None and window.winfo_exists():
            window.destroy()

    def retry_app_event_saves(self) -> None:
        self.rounds.retry_app_event_saves()
        self._refresh_app_event_status()

    def _select_language(self, language: str) -> None:
        if self._closing_ui:
            self.language_choice.set(self.current_language)
            return
        if language == self.current_language:
            self.language_choice.set(self.current_language)
            return
        self.current_language = language
        self.language_choice.set(language)
        self._language_save_error = None
        if self._language_refresh_notifications is not None:
            self._language_refresh_notifications.notify()
        try:
            self.profile_store.save_language(language)
        except (OSError, ProfileError) as error:
            self._language_save_error = str(error)
            self._record_app_event("app.language.preference_save_failed", {"reason": str(error)},
                                   str(error))
            self.language_button.configure(relief="sunken")
            self._show_notice("language.save_failed_title", "language.save_failed",
                              {"reason": str(error)})
        else:
            self._language_save_error = None
            self.language_button.configure(relief="raised")

    def _post_language_menu(self, _event=None):
        if self._closing_ui:
            return "break"
        self.language_menu.post(self.language_button.winfo_rootx(),
                                self.language_button.winfo_rooty() + self.language_button.winfo_height())
        self.language_menu.focus_set()
        return "break"

    def _refresh_language_entry(self) -> None:
        """Keep the visible and programmatic language entry in the close gate."""
        if not hasattr(self, "language_button"):
            return
        state = "disabled" if self._closing_ui else "normal"
        self.language_button.configure(state=state)
        if hasattr(self, "language_refresh_retry_button"):
            self.language_refresh_retry_button.configure(
                state="normal" if self._language_refresh_failures and not self._closing_ui
                else "disabled")
        if hasattr(self, "language_menu"):
            for index in range(self.language_menu.index("end") + 1):
                self.language_menu.entryconfigure(index, state=state)
            if self._closing_ui:
                try:
                    self.language_menu.unpost()
                except tk.TclError:
                    pass

    def _cancel_language_menu(self, _event=None):
        try:
            self.language_menu.unpost()
        except tk.TclError:
            pass
        self.language_button.focus_set()
        return "break"

    def _show_invalid_language_warning(self) -> None:
        if self.root.winfo_exists() and self.profile_store.language_error:
            self._show_notice("language.invalid_saved_title", "language.invalid_saved",
                              diagnostic=self.profile_store.language_error)

    def _show_startup_warning(self) -> None:
        if self.root.winfo_exists() and self.profile_error:
            self._show_notice("app.startup.title", "app.startup.preferences_read_failed",
                              {"reason": self.profile_error})

    def _show_app_event_store_warning(self) -> None:
        status = self.rounds.app_event_status()
        if self.root.winfo_exists() and status and status.error:
            self._show_notice("app.event_store.title", "app.event_store.initialize_failed",
                              {"reason": status.error})

    def _build_company_identity(self, parent: tk.Widget) -> None:
        """Reserve one fixed logo slot; missing or unreadable artwork stays blank."""
        if COMPANY_LOGO_PATH.is_file():
            try:
                self.company_logo = tk.PhotoImage(file=str(COMPANY_LOGO_PATH))
            except tk.TclError:
                self.company_logo = None
        self.company_logo_slot = tk.Frame(parent, background=LIGHT_BACKGROUND, width=137, height=35)
        self.company_logo_slot.pack(side="left")
        self.company_logo_slot.pack_propagate(False)
        if self.company_logo:
            tk.Label(self.company_logo_slot, image=self.company_logo, background=LIGHT_BACKGROUND,
                     borderwidth=0).pack(fill="both", expand=True)

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
                    message = make_bilingual_message("app.round.audit_incomplete", {}, error)
                    self._log(message.english, message)
                    reported.add(error)
            self._reported_audit_errors = reported
        save_state = getattr(snapshot, "save_state", "saving")
        save_errors = getattr(snapshot, "save_errors", ())
        reported_save_errors = getattr(self, "_reported_save_errors", set())
        for error in save_errors:
            if error not in reported_save_errors:
                message = make_bilingual_message("app.round.save_failed", {}, error)
                self._log(message.english, message)
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
            reason = (self._retention_reason_detail(detail_status.reason_message)
                      if detail_status.reason_message is not None else
                      self._retention_reason_detail(detail_status.message))
            if detail_status.save_state == "failed":
                snapshot = self.rounds.round_snapshot(detail_status.round_id)
                if (detail_status.reason_message is None and snapshot is not None and
                        snapshot.save_errors):
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
        self._show_notice("app.hotkey.title", "app.hotkey.unavailable",
                          diagnostic=self.hotkey.message)

    def _set_monitor_controls(self, monitoring: bool, state_message_id: Optional[str] = None) -> None:
        if getattr(self, "_closing_ui", False):
            self.start_button.configure(state="disabled")
            self.stop_button.configure(state="disabled")
            self._set_main_monitor_state("monitor.closing")
        else:
            self.start_button.configure(state="disabled" if monitoring else "normal")
            self.stop_button.configure(state="normal" if monitoring else "disabled")
            self._set_main_monitor_state(
                state_message_id or ("monitor.active" if monitoring else "monitor.idle")
            )
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
            self._show_notice("app.profile.validation_title", "app.profile.validation_failed",
                              {"reason": str(error)})
            return
        try:
            prepared = self.round_start_preparation.prepare(
                profile, self.session_root, async_session_writes=True,
            )
        except RoundStartPathError as error:
            self._record_app_event("app.profile.validation_failed", {"reason": str(error)}, str(error))
            self._show_notice("app.profile.validation_title", "app.profile.validation_failed",
                              {"reason": str(error)})
            return
        except (AttributeError, ProfileError, ValueError) as error:
            self._record_app_event("app.profile.validation_failed", {"reason": str(error)}, str(error))
            self._show_notice("app.profile.validation_title", "app.profile.validation_failed",
                              {"reason": str(error)})
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
            self._record_app_event("app.profile.save_failed", {"reason": str(error)}, str(error))
            self._show_notice("app.profile.save_title", "app.profile.save_failed",
                              {"reason": str(error)})
            return
        self._set_monitor_controls(True)

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
            reading_position = self.settings_log.yview()[0]
            selection = tuple(map(str, self.settings_log.tag_ranges("sel")))
            self.settings_log.configure(state="normal")
            self.settings_log.delete("1.0", "end")
            self.settings_log.insert("1.0", "\n".join(self.event_lines))
            for start, end in zip(selection[::2], selection[1::2]):
                self.settings_log.tag_add("sel", start, end)
            self.settings_log.yview_moveto(reading_position)
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
        if self._ui_destroyed:
            return
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
        self._schedule_ui(150, self._drain_events)

    def _bring_dashboard_to_front(self) -> None:
        """Show the completed-result board without keeping it permanently on top."""
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        except tk.TclError as error:
            message = make_bilingual_message("app.dashboard.focus_failed", {}, str(error))
            self._log(message.english, message)

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
            self._set_monitor_controls(False, "monitor.timeout_stopped")
        if event.kind == "timeout" and event.detail.get("kind") == "round":
            self._set_monitor_controls(False, "monitor.timeout_stopped")
            self._open_round_alarm()
        if event.kind == "start_failed":
            self.active_profile_snapshot = None
            self._set_monitor_controls(False, "monitor.start_failed")
            self._show_notice("monitor.start_failed", "round.start_failed",
                              {"station": self.station.get().upper()},
                              diagnostic=event.diagnostic, captured=event.localized_message)
        if event.kind in {"finished", "stopped"}:
            self._set_monitor_controls(False)

    def _open_conflict_review(self) -> None:
        """Show the captured candidates in a modeless, non-blocking window."""
        if not self.conflict_window or not self.conflict_window.winfo_exists():
            window = tk.Toplevel(self.root)
            self.conflict_window = window
            self.root.update_idletasks()
            window_width, window_height, window_gap = 960, 600, 12
            root_x = self.root.winfo_rootx()
            root_y = self.root.winfo_rooty()
            root_width = self.root.winfo_width()
            root_height = self.root.winfo_height()
            screen_width = self.root.winfo_screenwidth()
            screen_height = self.root.winfo_screenheight()
            left_x = root_x - window_width - window_gap
            right_x = root_x + root_width + window_gap
            if left_x >= 0:
                window_x, window_y = left_x, root_y
            elif right_x + window_width <= screen_width:
                window_x, window_y = right_x, root_y
            else:
                below_y = root_y + root_height + window_gap
                above_y = root_y - window_height - window_gap
                window_x = max(0, min(root_x, screen_width - window_width))
                window_y = (below_y if below_y + window_height <= screen_height
                            else max(0, above_y))
            window.geometry("{}x{}+{}+{}".format(
                window_width, window_height, window_x, window_y))
            window.minsize(820, 540)
            window.transient(self.root)
            window.protocol("WM_DELETE_WINDOW", window.withdraw)
            instruction_area = ttk.Frame(window, height=44)
            instruction_area.pack(fill="x", padx=12, pady=(12, 8))
            instruction_area.pack_propagate(False)
            self.conflict_instructions = ttk.Label(
                instruction_area, text="", wraplength=900,
            )
            self.conflict_instructions.pack(fill="both", expand=True)
            body = ttk.Frame(window)
            body.pack(fill="both", expand=True, padx=12, pady=4)
            list_frame = ttk.Frame(body)
            list_frame.pack(side="left", fill="y")
            self.conflict_list = tk.Listbox(list_frame, width=52, exportselection=False,
                                            background=FIELD_BACKGROUND, foreground=TEXT_COLOUR,
                                            selectbackground="#1d4ed8", selectforeground="#ffffff")
            self.conflict_list.pack(side="top", fill="y", expand=True)
            self.conflict_list_xscrollbar = ttk.Scrollbar(
                list_frame, orient="horizontal", command=self.conflict_list.xview,
            )
            self.conflict_list_xscrollbar.pack(side="bottom", fill="x")
            self.conflict_list.configure(xscrollcommand=self.conflict_list_xscrollbar.set)
            self.conflict_list.bind("<<ListboxSelect>>", self._on_conflict_list_select)
            self.conflict_panes = ttk.Panedwindow(body, orient="vertical")
            self.conflict_panes.pack(side="left", fill="both", expand=True, padx=(10, 0))

            summary = ttk.Frame(self.conflict_panes)
            summary.columnconfigure(0, weight=1)
            summary.rowconfigure(1, weight=1)
            self.conflict_position_label = ttk.Label(summary, text=self._t(
                "conflict.position", position=self._t("conflict.unknown"),
            ))
            self.conflict_position_label.grid(row=0, column=0, sticky="ew", pady=(0, 4))
            comparison_font = tkfont.nametofont("TkDefaultFont")
            self.conflict_comparison = tk.Text(
                summary, wrap="none", height=5, state="disabled", font=comparison_font,
                background=LIGHT_BACKGROUND, foreground=TEXT_COLOUR, relief="solid",
                borderwidth=1, padx=4, pady=4,
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
            self._schedule_ui("idle", self._set_initial_conflict_sash)
            actions = ttk.Frame(window)
            actions.pack(side="bottom", fill="x", padx=12, pady=(8, 12), before=body)
            for column in range(3):
                actions.columnconfigure(column, weight=1, uniform="conflict-actions")
            self.resolve_conflict_original_button = ttk.Button(
                actions, text="",
                command=lambda: self._resolve_selected_conflict("keep_original"),
            )
            self.resolve_conflict_original_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))
            self.resolve_conflict_candidate_button = ttk.Button(
                actions, text="",
                command=lambda: self._resolve_selected_conflict("accept_candidate"),
            )
            self.resolve_conflict_candidate_button.grid(row=0, column=1, sticky="ew", padx=(0, 8))
            self.conflict_close_button = ttk.Button(
                actions, text="", command=window.withdraw,
            )
            self.conflict_close_button.grid(row=0, column=2, sticky="ew")
            window.bind("<Destroy>", self._on_conflict_window_destroy, add="+")
            self._unregister_conflict_language_receiver = self.register_language_receiver(
                lambda: self._t("conflict.title"),
                lambda: self._refresh_conflict_review(preserve_reading=True,
                                                       update_main=False,
                                                       language_refresh=True),
                window.winfo_exists,
            )
        self._refresh_conflict_review(language_refresh=True)
        if self.conflict_window and self.conflict_window.winfo_exists():
            self.conflict_window.deiconify()
            self.conflict_window.lift()

    def _render_conflict_review_button(self, snapshot=None) -> None:
        if not hasattr(self, "review_button"):
            return
        snapshot = snapshot if snapshot is not None else self.rounds.snapshot()
        conflicts = snapshot.pending_conflicts if snapshot else ()
        self.review_count.configure(text=str(len(conflicts)))
        self.review_button.configure(state="normal" if conflicts else "disabled")
        if len(getattr(self, "_toolbar_hints", ())) > 3:
            self._toolbar_hints[3].refresh()

    def _refresh_conflict_review(self, preserve_reading: bool = False,
                                 update_main: bool = True,
                                 language_refresh: bool = False) -> None:
        if not hasattr(self, "review_button"):
            return
        if language_refresh:
            panes = self.conflict_panes
            sash = (panes.sashpos(0) if panes is not None and panes.winfo_exists()
                    and panes.winfo_height() > 1 else None)
            self._apply_conflict_window_language()
            if sash is not None:
                panes.update_idletasks()
                panes.sashpos(0, sash)
        snapshot = self.rounds.snapshot() if hasattr(self, "rounds") else None
        conflicts = snapshot.pending_conflicts if snapshot else ()
        conflict_signature = tuple(
            (item.conflict_id, item.round_id, item.slot, item.original, item.candidate,
             item.same_round_evidence)
            for item in conflicts
        )
        conflict_data_changed = conflict_signature != self._rendered_conflict_signature
        if update_main:
            self._render_conflict_review_button(snapshot)
            alarm = snapshot.round_alarm if snapshot else None
            alarm_pending = alarm is not None and not alarm.acknowledged_at
            if alarm_pending and conflicts:
                self._set_main_monitor_state("monitor.awaiting_both", count=len(conflicts))
            elif alarm_pending:
                self._set_main_monitor_state("monitor.awaiting_alarm")
            elif conflicts:
                self._set_main_monitor_state("monitor.awaiting_conflicts", count=len(conflicts))
            elif snapshot and snapshot.state.value == "COMPLETED":
                self._set_main_monitor_state("monitor.completed")
            elif (snapshot and snapshot.state.value == "STOPPED" and
                  snapshot.completion_reason == "manual_stop"):
                self._set_main_monitor_state("monitor.stopped")
        if self.conflict_window and self.conflict_window.winfo_exists():
            if self.conflict_list is None:
                return
            selected = self.conflict_list.curselection()
            selected_id = self._conflict_ids[selected[0]] if selected and selected[0] < len(self._conflict_ids) else None
            previous_ids = self._conflict_ids
            top_index = self.conflict_list.nearest(1) if previous_ids else 0
            top_id = previous_ids[top_index] if previous_ids else None
            current_ids = [item.conflict_id for item in conflicts]
            display_items = [self._t(
                    "conflict.list_item",
                    position=(item.slot if item.slot is not None else self._t("conflict.unknown")),
                    original_sn=item.original.sn or "SN {}".format(self._t("conflict.unknown")),
                    original_status=item.original.status or self._t("conflict.unknown"),
                    candidate_sn=item.candidate.sn or "SN {}".format(self._t("conflict.unknown")),
                    candidate_status=item.candidate.status or self._t("conflict.unknown"),
                ) for item in conflicts]
            list_changed = (current_ids != previous_ids or conflict_data_changed or
                            language_refresh)
            self._updating_conflict_list = True
            try:
                if list_changed:
                    self._conflict_ids = current_ids
                    self.conflict_list.delete(0, "end")
                    for display_item in display_items:
                        self.conflict_list.insert("end", display_item)
                if selected_id in self._conflict_ids:
                    index = self._conflict_ids.index(selected_id)
                elif selected_id is not None:
                    index = 0 if self._conflict_ids else -1
                elif not previous_ids:
                    index = 0 if self._conflict_ids else -1
                else:
                    index = -1
                if index >= 0 and (list_changed or selected_id != self._conflict_ids[index]):
                    self.conflict_list.selection_set(index)
                    self.conflict_list.activate(index)
                elif index < 0 and selected:
                    self.conflict_list.selection_clear(0, "end")
                if list_changed and current_ids:
                    self.conflict_list.yview(
                        current_ids.index(top_id) if top_id in current_ids
                        else min(top_index, len(current_ids) - 1))
            finally:
                self._updating_conflict_list = False
            should_render = (preserve_reading or list_changed or
                             (index >= 0 and selected_id is None and not previous_ids))
            if should_render:
                if index < 0:
                    self._clear_conflict_comparison()
                else:
                    self._show_selected_conflict(preserve_reading=preserve_reading)
            elif self.conflict_details:
                has_enabled_decision = any(
                    button and button.winfo_exists() and button.instate(("!disabled",))
                    for button in (self.resolve_conflict_original_button,
                                   self.resolve_conflict_candidate_button)
                )
                if index < 0 and (list_changed or selected or self._conflict_value_ranges or
                                  has_enabled_decision):
                    self._clear_conflict_comparison()
        self._rendered_conflict_signature = conflict_signature

    def _apply_conflict_window_language(self) -> None:
        if not self.conflict_window or not self.conflict_window.winfo_exists():
            return
        self.conflict_window.title(self._t("conflict.title"))
        if self.conflict_instructions and self.conflict_instructions.winfo_exists():
            self.conflict_instructions.configure(text=self._t("conflict.instructions"))
        for button, message_id in (
            (self.resolve_conflict_original_button, "conflict.button.keep_original"),
            (self.resolve_conflict_candidate_button, "conflict.button.accept_candidate"),
            (self.conflict_close_button, "conflict.button.close"),
        ):
            if button and button.winfo_exists():
                button.configure(text=self._t(message_id))

    def _set_initial_conflict_sash(self) -> None:
        if not self.conflict_panes or not self.conflict_panes.winfo_exists():
            return
        height = self.conflict_panes.winfo_height()
        if height > 1:
            self.conflict_panes.sashpos(0, int(height * 0.4))

    def _clear_conflict_comparison(self) -> None:
        self._rendered_conflict_id = None
        if self.conflict_comparison:
            self.conflict_comparison.configure(state="normal")
            self.conflict_comparison.delete("1.0", "end")
            self.conflict_comparison.configure(tabs=("120p", "280p"))
            self.conflict_comparison.configure(state="disabled")
            self._conflict_value_ranges = {}
            self.conflict_comparison.xview_moveto(0)
        if self.conflict_position_label:
            self.conflict_position_label.configure(
                text=self._t("conflict.position", position=self._t("conflict.unknown")))
        if self.conflict_details:
            self.conflict_details.configure(state="normal")
            self.conflict_details.delete("1.0", "end")
            self.conflict_details.insert("1.0", self._t("conflict.empty"))
            self.conflict_details.configure(state="disabled")
        for button in (self.resolve_conflict_original_button,
                       self.resolve_conflict_candidate_button):
            if button and button.winfo_exists():
                button.configure(state="disabled")

    def _show_selected_conflict(self, _event=None, preserve_reading: bool = False) -> None:
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
        preserve_reading = preserve_reading or conflict_id == self._rendered_conflict_id
        conflict = next((item for item in snapshot.pending_conflicts
                         if item.conflict_id == conflict_id), None)
        if not conflict:
            self._clear_conflict_comparison()
            return
        comparison_xview = self.conflict_comparison.xview()[0] if preserve_reading else 0.0
        comparison_yview = self.conflict_comparison.yview()[0] if preserve_reading else 0.0
        details_top_line, details_top_column = (
            map(int, self.conflict_details.index("@0,0").split("."))
            if preserve_reading else (1, 0))
        details_tail_columns = (
            int(self.conflict_details.index("{}.end".format(details_top_line)).split(".")[1])
            - details_top_column)
        for button in (self.resolve_conflict_original_button,
                       self.resolve_conflict_candidate_button):
            if button and button.winfo_exists():
                button.configure(state="normal")

        def source_parts(side):
            if not side.source:
                return "", self._t("conflict.unknown"), (), (False, ())
            normalized = side.source.replace("\\", "/").rstrip("/")
            parts = tuple(part for part in normalized.split("/") if part)
            return (side.source, parts[-1] if parts else self._t("conflict.unknown"), parts[:-1],
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
                original_hint = self._t(
                    "conflict.path.root" if original_path_key[0] else "conflict.path.relative")
                candidate_hint = self._t(
                    "conflict.path.root" if candidate_path_key[0] else "conflict.path.relative")
                original_source = "{} · {}".format(original_filename, original_hint)
                candidate_source = "{} · {}".format(candidate_filename, candidate_hint)

        rows = (
            (self._t("conflict.field.result"), conflict.original.status or "",
             conflict.candidate.status or "",
             (conflict.original.status or "") != (conflict.candidate.status or "")),
            (self._t("conflict.field.sn"), conflict.original.sn or "", conflict.candidate.sn or "",
             (conflict.original.sn or "") != (conflict.candidate.sn or "")),
            (self._t("term.source_time"), conflict.original.source_time or "",
             conflict.candidate.source_time or "",
             (conflict.original.source_time or "") != (conflict.candidate.source_time or "")),
            (self._t("term.source_filename"), original_source if original_path else "",
             candidate_source if candidate_path else "", paths_differ),
        )
        unknown = self._t("conflict.unknown")
        display_rows = tuple((label, original or unknown, candidate or unknown, differs)
                             for label, original, candidate, differs in rows)
        self.conflict_position_label.configure(text=self._t(
            "conflict.position",
            position=(conflict.slot if conflict.slot is not None else unknown),
        ))
        self.conflict_comparison.configure(state="normal")
        self.conflict_comparison.delete("1.0", "end")
        self.conflict_comparison.insert("end", "{}\t{}\t{}\n".format(
            self._t("conflict.comparison.item"),
            self._t("conflict.comparison.original"),
            self._t("conflict.comparison.candidate"),
        ), "comparison_header")
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
        label_width = max(display_font.measure(self._t("conflict.comparison.item")),
                          max(display_font.measure(row[0]) for row in display_rows)) + 24
        original_width = max(display_font.measure(self._t("conflict.comparison.original")),
                             max(display_font.measure(row[1]) for row in display_rows)) + 24
        original_width = max(140, original_width)
        self.conflict_comparison.configure(
            tabs=("{}p".format(label_width),
                  "{}p".format(label_width + original_width)),
            state="disabled",
        )
        self.conflict_comparison.xview_moveto(comparison_xview)
        self.conflict_comparison.yview_moveto(comparison_yview)

        def render(side):
            fields = (
                ("conflict.detail.sn", side.sn),
                ("conflict.detail.result", side.status),
                ("conflict.detail.source", side.source),
                ("conflict.detail.source_identity", side.source_id),
                ("conflict.detail.source_time", side.source_time),
                ("conflict.detail.evidence", dict(side.evidence)),
            )
            return "\n".join("{}: {}".format(self._t(label), value or unknown)
                             for label, value in fields)
        text = "\n".join((
            "{}: {}".format(self._t("conflict.detail.round"), conflict.round_id),
            "{}: {}".format(self._t("conflict.detail.conflict"), conflict.conflict_id),
            "{}: {}".format(
                self._t("conflict.detail.position"),
                conflict.slot if conflict.slot is not None else unknown,
            ),
            "{}: {}".format(self._t("conflict.detail.same_round_evidence"),
                             dict(conflict.same_round_evidence)),
            "",
            self._t("conflict.detail.original"),
            render(conflict.original),
            "",
            self._t("conflict.detail.candidate_snapshot"),
            render(conflict.candidate),
        ))
        self.conflict_details.configure(state="normal")
        self.conflict_details.delete("1.0", "end")
        self.conflict_details.insert("1.0", text)
        self.conflict_details.configure(state="disabled")
        self._rendered_conflict_id = conflict_id
        if preserve_reading:
            rendered_line_count = int(self.conflict_details.index("end-1c").split(".")[0])
            details_top_line = min(details_top_line, rendered_line_count)
            line_end_column = int(self.conflict_details.index(
                "{}.end".format(details_top_line)).split(".")[1])
            # Labels change length; the captured raw value at the end of its line does not.
            column = (max(0, line_end_column - details_tail_columns)
                      if details_top_column else 0)
            self.conflict_details.yview("{}.{}".format(details_top_line, column))

    def _on_conflict_list_select(self, event=None) -> None:
        if self._updating_conflict_list:
            return
        self._show_selected_conflict(event)

    def _on_conflict_window_destroy(self, event) -> None:
        window = self.conflict_window
        if event.widget is not window:
            return
        unregister = self._unregister_conflict_language_receiver
        self._unregister_conflict_language_receiver = None
        if unregister is not None:
            unregister()
        self.conflict_window = None
        self.conflict_instructions = None
        self.conflict_list = None
        self.conflict_list_xscrollbar = None
        self.conflict_panes = None
        self.conflict_position_label = None
        self.conflict_comparison = None
        self.conflict_comparison_scrollbar = None
        self.conflict_details = None
        self._conflict_ids = []
        self._rendered_conflict_id = None
        self._rendered_conflict_signature = None
        self._updating_conflict_list = False
        self.resolve_conflict_original_button = None
        self.resolve_conflict_candidate_button = None
        self.conflict_close_button = None

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
        self._render_round_alarm_button(snapshot)
        if alarm is None:
            self._rendered_alarm_view_state = None
            if (snapshot and self._round_alarm_window_identity and
                    self._round_alarm_window_identity[0] != snapshot.round_id and
                    self.round_alarm_window and self.round_alarm_window.winfo_exists()):
                self.round_alarm_window.withdraw()
            return
        identity = (alarm.round_id, alarm.alarm_id)
        if identity != getattr(self, "_shown_round_alarm_identity", None):
            self._open_round_alarm()
        if self.round_alarm_window and self.round_alarm_window.winfo_exists():
            view_state = (alarm, snapshot.round_alarm_ready)
            if view_state != self._rendered_alarm_view_state:
                self._render_round_alarm(alarm)

    def _render_round_alarm_button(self, snapshot=None) -> None:
        if not hasattr(self, "round_alarm_button"):
            return
        snapshot = snapshot if snapshot is not None else self.rounds.snapshot()
        alarm = snapshot.round_alarm if snapshot else None
        if alarm is None:
            self.round_alarm_button.configure(state="disabled")
            if len(getattr(self, "_toolbar_hints", ())) > 2:
                self._toolbar_hints[2].refresh()
            return
        pending = not alarm.acknowledged_at
        self.round_alarm_button.configure(
            state="normal" if pending and snapshot.round_alarm_ready else "disabled",
        )
        if len(getattr(self, "_toolbar_hints", ())) > 2:
            self._toolbar_hints[2].refresh()

    def _refresh_round_alarm_language(self) -> None:
        window = self.round_alarm_window
        if window is None or not window.winfo_exists():
            return
        snapshot = self.rounds.snapshot() if hasattr(self, "rounds") else None
        alarm = snapshot.round_alarm if snapshot else None
        if (alarm is None or
                (alarm.round_id, alarm.alarm_id) != self._round_alarm_window_identity):
            return
        self._render_round_alarm(alarm)

    def _open_round_alarm(self) -> None:
        snapshot = self.rounds.snapshot() if hasattr(self, "rounds") else None
        alarm = snapshot.round_alarm if snapshot else None
        if alarm is None:
            return
        if not self.round_alarm_window or not self.round_alarm_window.winfo_exists():
            window = tk.Toplevel(self.root)
            self.round_alarm_window = window
            window.title(self._t("alarm.title"))
            window.geometry("700x340")
            window.minsize(620, 300)
            window.transient(self.root)
            window.protocol("WM_DELETE_WINDOW", window.withdraw)
            self.round_alarm_message = ttk.Label(
                window, wraplength=650, justify="left",
                background=LIGHT_BACKGROUND, foreground=TEXT_COLOUR,
                anchor="nw",
            )
            self.round_alarm_message.pack(fill="both", expand=True, padx=20, pady=(20, 12))
            actions = ttk.Frame(window)
            actions.pack(fill="x", padx=20, pady=(0, 18))
            actions.columnconfigure(0, weight=1, uniform="alarm-actions")
            actions.columnconfigure(1, weight=1, uniform="alarm-actions")
            self.round_alarm_ack_button = ttk.Button(
                actions, text=self._t("alarm.button.acknowledge"),
            )
            self.round_alarm_ack_button.grid(row=0, column=0, sticky="ew", padx=(0, 8))
            self.round_alarm_close_button = ttk.Button(
                actions, text=self._t("alarm.button.close"), command=window.withdraw,
            )
            self.round_alarm_close_button.grid(row=0, column=1, sticky="ew")
            window.bind("<Destroy>", self._on_round_alarm_destroy, add="+")
            self._unregister_round_alarm_language_receiver = self.register_language_receiver(
                lambda: self._t("alarm.title"),
                lambda: self._refresh_round_alarm_language(),
                window.winfo_exists,
            )
        self._render_round_alarm(alarm)
        self._round_alarm_window_identity = (alarm.round_id, alarm.alarm_id)
        self.round_alarm_ack_button.configure(
            command=lambda round_id=alarm.round_id, alarm_id=alarm.alarm_id:
            self._acknowledge_round_alarm(round_id, alarm_id),
        )
        self._shown_round_alarm_identity = (alarm.round_id, alarm.alarm_id)
        self.round_alarm_window.deiconify()
        self.round_alarm_window.lift()

    def _on_round_alarm_destroy(self, event) -> None:
        window = self.round_alarm_window
        if event.widget is not window:
            return
        unregister = self._unregister_round_alarm_language_receiver
        self._unregister_round_alarm_language_receiver = None
        if unregister is not None:
            unregister()
        self.round_alarm_window = None
        self.round_alarm_message = None
        self.round_alarm_ack_button = None
        self.round_alarm_close_button = None
        self._round_alarm_window_identity = None
        self._shown_round_alarm_identity = None
        self._rendered_alarm_view_state = None

    def _render_round_alarm(self, alarm) -> None:
        if self.round_alarm_window and self.round_alarm_window.winfo_exists():
            self.round_alarm_window.title(self._t("alarm.title"))
        snapshot = self.rounds.snapshot()
        if alarm.acknowledged_at:
            status_id = "alarm.status.acknowledged"
        elif snapshot is not None and not snapshot.round_alarm_ready:
            status_id = "alarm.status.preparation_pending"
        else:
            status_id = "alarm.status.pending"
        status = "{}\n{}".format(self._t(status_id), self._t("alarm.status.conflict_note"))
        if self.round_alarm_message and self.round_alarm_message.winfo_exists():
            self.round_alarm_message.configure(text=self._t(
                "alarm.body", round_label=self._t("alarm.round"), round_id=alarm.round_id,
                alarm_label=self._t("alarm.identity"), alarm_id=alarm.alarm_id,
                created_label=self._t("alarm.created_at"), created_at=alarm.created_at,
                status=status,
            ))
        if self.round_alarm_ack_button and self.round_alarm_ack_button.winfo_exists():
            self.round_alarm_ack_button.configure(
                state="disabled" if alarm.acknowledged_at or (
                    snapshot is not None and not snapshot.round_alarm_ready) else "normal",
                text=(self._t("alarm.button.acknowledged") if alarm.acknowledged_at
                      else self._t("alarm.button.acknowledge")),
            )
        if self.round_alarm_close_button and self.round_alarm_close_button.winfo_exists():
            self.round_alarm_close_button.configure(text=self._t("alarm.button.close"))
        self._rendered_alarm_view_state = (
            alarm, bool(snapshot and snapshot.round_alarm_ready),
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
        self.style.configure("Settings.TNotebook.Tab", width=22)
        notebook = ttk.Notebook(dialog, style="Settings.TNotebook")
        self.style.configure("Settings.TNotebook", background=LIGHT_BACKGROUND,
                             borderwidth=0)
        self.style.map("Settings.TNotebook.Tab",
                       background=[("selected", FIELD_BACKGROUND), ("active", "#dbeafe")],
                       foreground=[("selected", TEXT_COLOUR), ("active", TEXT_COLOUR)])
        self.settings_notebook = notebook
        notebook.pack(fill="both", expand=True, padx=12, pady=12)
        profile_tab = ttk.Frame(notebook)
        log_tab = ttk.Frame(notebook, padding=12)
        retention_tab = ttk.Frame(notebook)
        self._settings_tab_ids = [
            "app.settings.tab.configuration", "app.settings.tab.events",
            "app.settings.tab.retention",
        ]
        notebook.add(profile_tab, text=self._t(self._settings_tab_ids[0]))
        notebook.add(log_tab, text=self._t(self._settings_tab_ids[1]))
        notebook.add(retention_tab, text=self._t(self._settings_tab_ids[2]))
        self._build_profile_editor_tab(self._settings_scrollable_tab(profile_tab))
        self._build_log_tab(log_tab)
        self._build_retention_tab(self._settings_scrollable_tab(retention_tab))
        dialog.bind("<Destroy>", self._on_settings_destroy, add="+")
        self._unregister_settings_language_receiver = self.register_language_receiver(
            lambda: self._t("app.settings.title"),
            self._apply_settings_language,
            lambda: self.settings_window is dialog and dialog.winfo_exists(),
        )
        self._apply_settings_language()

    def _build_retention_tab(self, parent: ttk.Frame) -> None:
        """Build the global round-record retention settings tab."""
        self.retention_days_var = tk.StringVar(master=self.root, value=str(self.profile_store.retention_days))
        self.retention_status = tk.StringVar(master=self.root)
        self._set_retention_status("app.settings.retention.status.saved")
        self.retention_effective_label = ttk.Label(
            parent, text=self._t("app.settings.retention.effective",
                                 days=self.profile_store.retention_days), width=36)
        self.retention_effective_label.grid(row=0, column=0, columnspan=2, sticky="w", pady=(4, 10))
        self._settings_label(parent, "app.settings.retention.days").grid(
            row=1, column=0, sticky="w", pady=4)
        self.retention_days_entry = ttk.Entry(parent, textvariable=self.retention_days_var, width=16)
        self.retention_days_entry.grid(row=1, column=1, sticky="w", padx=8, pady=4)
        self.retention_save_button = self._settings_button(
            parent, "app.settings.retention.save", self._save_retention_days)
        self.retention_save_button.grid(row=2, column=0, sticky="w", pady=(8, 4))
        retention_status_frame = ttk.Frame(parent, width=270, height=54)
        retention_status_frame.grid(row=2, column=1, sticky="ew", padx=8, pady=(8, 4))
        retention_status_frame.grid_propagate(False)
        ttk.Label(retention_status_frame, textvariable=self.retention_status,
                  width=36, wraplength=270, foreground=TEXT_COLOUR).pack(
                      fill="both", expand=True)
        self.retention_help_label = tk.Label(
            parent, text=self._t("app.settings.retention.help"), width=66, height=6,
            wraplength=540, justify="left", anchor="nw",
            background=LIGHT_BACKGROUND, foreground=TEXT_COLOUR)
        self._settings_text_widgets.append(
            (self.retention_help_label, "app.settings.retention.help"))
        self.retention_help_label.grid(row=3, column=0, columnspan=2,
                                       sticky="w", pady=(12, 4))
        self.retention_cleanup_status = tk.StringVar(master=self.root, value="背景清理尚未執行")
        self.retention_cleanup_heading = self._settings_label(
            parent, "app.settings.retention.cleanup.heading")
        self.retention_cleanup_heading.configure(font=("Helvetica", 10, "bold"))
        self.retention_cleanup_heading.grid(row=4, column=0, columnspan=2, sticky="w", pady=(18, 4))
        self.retention_cleanup_text = tk.Text(
            parent, wrap="word", width=1, height=12, state="disabled",
            background=LIGHT_BACKGROUND, foreground=TEXT_COLOUR,
            insertbackground=TEXT_COLOUR, selectbackground="#dbeafe",
            selectforeground=TEXT_COLOUR, relief="solid", borderwidth=1,
        )
        cleanup_output = ttk.Frame(parent)
        cleanup_output.grid(row=5, column=0, columnspan=2, sticky="ew")
        cleanup_output.columnconfigure(0, weight=1)
        self.retention_cleanup_scrollbar = ttk.Scrollbar(
            cleanup_output, orient="vertical", command=self.retention_cleanup_text.yview)
        self.retention_cleanup_text.configure(
            yscrollcommand=self.retention_cleanup_scrollbar.set)
        self.retention_cleanup_text.grid(in_=cleanup_output, row=0, column=0, sticky="nsew")
        self.retention_cleanup_scrollbar.grid(row=0, column=1, sticky="ns")
        self.retention_retry_button = self._settings_button(
            parent, "app.settings.retention.cleanup.retry", self._retry_retention_cleanup)
        self.retention_retry_button.grid(row=6, column=0, sticky="w", pady=(8, 4))
        self._refresh_retention_cleanup_status()
        parent.columnconfigure(1, weight=1)

    def _retry_retention_cleanup(self) -> None:
        """Retry App and round cleanup through the existing coordinator entry point."""
        self.rounds.request_retention_cleanup(
            self.profile_store.retention_days, "manual-retry")
        self._refresh_retention_cleanup_status()

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
        if status.reason_message is not None:
            status_reason_text = self._retention_reason_detail(status.reason_message)
        else:
            status_reason_text = self._retention_reason_detail(status.message)
        detail = self._t(
            status_message,
            reason=(status_reason_text if status.reason_message is not None else
                    self._retention_reason_detail(
                        latest.message_reason if latest and latest.message_reason is not None
                        else status.message)) if status.status == "skipped" else "")
        if status.status == "failed" and status.message:
            reason = (status.reason_message if status.reason_message is not None else status.message)
            detail += "\n" + self._retention_reason_detail(reason)
        if latest is not None:
            outcomes = latest.results
            detail += "\n" + self._t(
                "app.settings.retention.cleanup.summary",
                time=latest.completed_at or latest.started_at,
                days=latest.retention_days,
                deleted=sum(item.outcome == "deleted" for item in outcomes),
                skipped=sum(item.outcome == "skipped" for item in outcomes),
                failed=sum(item.outcome == "failed" for item in outcomes),
                app_deleted=latest.app_events.deleted_count if latest.app_events else 0,
                app_skipped=latest.app_events.skipped_count if latest.app_events else 0,
                app_failed=latest.app_events.failed_count if latest.app_events else 0)
            if latest.message_reason is not None:
                detail += "\n{}: {}".format(
                    self._t("app.settings.retention.reason.summary"),
                    self._retention_reason_detail(latest.message_reason))
            completed = [item for item in outcomes
                         if item.outcome == "deleted" and
                         (item.reason_message is not None or item.reason)]
            if completed:
                items = "；".join(self._t(
                    "app.settings.retention.cleanup.item",
                    round_id=item.round_id or self._t("term.test_round"),
                    reason=self._retention_reason_detail(
                        item.reason_message if item.reason_message is not None else item.reason))
                    for item in completed[:3])
                detail += "\n" + self._t(
                    "app.settings.retention.cleanup.completed", items=items)
            failures = [item for item in outcomes if item.outcome == "failed"]
            if failures:
                items = "；".join(self._t(
                    "app.settings.retention.cleanup.item",
                    round_id=item.round_id or self._t("app.settings.retention.cleanup.heading"),
                    reason=self._retention_reason_detail(
                        item.reason_message if item.reason_message is not None else item.reason))
                    for item in failures[:3])
                detail += "\n" + self._t("app.settings.retention.cleanup.failures", items=items)
            skipped = [item for item in outcomes if item.outcome == "skipped"]
            if skipped:
                items = "；".join(self._t(
                    "app.settings.retention.cleanup.item",
                    round_id=item.round_id or self._t("term.test_round"),
                    reason=self._retention_reason_detail(
                        item.reason_message if item.reason_message is not None else item.reason))
                    for item in skipped[:3])
                detail += "\n" + self._t("app.settings.retention.cleanup.protected", items=items)
            if latest.app_events is not None and latest.app_events.reason:
                detail += "\n" + self._t(
                    "app.settings.retention.cleanup.app_events_reason",
                    reason=self._retention_reason_detail(
                        latest.app_events.reason_message
                        if latest.app_events.reason_message is not None
                        else latest.app_events.reason))
        variable.set(detail)
        output = getattr(self, "retention_cleanup_text", None)
        if output is not None and output.winfo_exists():
            reading_position = output.yview()[0]
            selection = (output.index("sel.first"), output.index("sel.last")) \
                if output.tag_ranges("sel") else None
            output.configure(state="normal")
            output.delete("1.0", "end")
            output.insert("1.0", detail)
            if selection is not None:
                try:
                    output.tag_add("sel", *selection)
                except tk.TclError:
                    pass
            output.yview_moveto(reading_position)
            output.configure(state="disabled")

    def _retention_reason_detail(self, reason: object) -> str:
        """Render a localized outer reason and retain its complete source evidence."""
        presentation = present_cleanup_reason(reason, self.current_language)
        if isinstance(reason, str):
            original = reason
        elif isinstance(reason, dict):
            evidence = {key: value for key, value in reason.items() if key != "message_id"}
            original = json.dumps(evidence, ensure_ascii=False, sort_keys=True, default=str)
        else:
            original = json.dumps(reason, ensure_ascii=False, sort_keys=True, default=str)
        details = self._t("app.settings.retention.reason.original_details", details=original)
        if presentation.diagnostic:
            diagnostic = self._t("app.settings.retention.reason.raw_diagnostic",
                                 diagnostic=presentation.diagnostic)
            return "{}\n{}\n{}".format(presentation.text, details, diagnostic)
        return "{}\n{}".format(presentation.text, details)

    def _build_profile_editor_tab(self, parent: ttk.Frame) -> None:
        """Build a draft editor whose values stay separate until explicit apply."""
        try:
            profile = self.profiles.get(self.project.get(), self.station.get())
        except ProfileError:
            profile = self.profiles.profiles[0]
        self.profile_editor_original = profile
        self.profile_editor_project = tk.StringVar(master=self.root, value=profile.project)
        self.profile_editor_machine = tk.StringVar(master=self.root, value=profile.machine)
        self.profile_editor_platform = tk.StringVar(master=self.root, value=profile.platform)
        self.profile_editor_capacity = tk.StringVar(master=self.root, value=str(profile.capacity))
        self.profile_editor_paths = {
            field: tk.StringVar(master=self.root, value=profile.paths.get(field, ""))
            for field in ("active", "final", "caseinfo")
        }
        self.profile_editor_mapping = tk.StringVar(master=self.root, value=self._mapping_text(profile.mapping))
        self.profile_editor_timeouts = {
            field: tk.StringVar(master=self.root, value=str(profile.timeouts[field]))
            for field in ("start", "test", "round")
        }
        self.profile_editor_status = tk.StringVar(master=self.root)
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
        self._settings_wrapped_label(
            parent, "app.settings.profile.mapping").grid(
                row=2, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.profile_editor_mapping, width=34).grid(
            row=2, column=1, columnspan=3, sticky="ew", padx=6, pady=4)

        path_labels = (("active", "app.settings.profile.path_active"),
                       ("final", "app.settings.profile.path_final"),
                       ("caseinfo", "app.settings.profile.path_caseinfo"))
        for index, (field, message_id) in enumerate(path_labels):
            row = 3 + index * 2
            path_label = self._settings_label(parent, message_id)
            path_label.configure(width=0, wraplength=600)
            path_label.grid(row=row, column=0, columnspan=4, sticky="ew", pady=(6, 0))
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
            self._settings_wrapped_label(parent, message_id).grid(
                row=row, column=column, sticky="w", padx=(12, 0) if column else 0, pady=4)
            ttk.Entry(parent, textvariable=self.profile_editor_timeouts[field], width=16).grid(
                row=row, column=column + 1, sticky="ew", padx=6, pady=4)
        status_frame = ttk.Frame(parent, height=72)
        status_frame.grid(row=11, column=0, columnspan=4, sticky="ew", pady=(10, 6))
        status_frame.grid_propagate(False)
        ttk.Label(status_frame, textvariable=self.profile_editor_status, wraplength=600,
                  foreground=TEXT_COLOUR).pack(fill="both", expand=True)
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
        controls.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        self._settings_button(controls, "app.settings.session.open",
                              self.open_session).pack(side="left")
        self._settings_button(controls, "app.settings.history.open",
                              self.open_historical_events).pack(side="left", padx=(8, 0))
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        self.settings_log_scrollbar = ttk.Scrollbar(parent, orient="vertical")
        self.settings_log = tk.Text(parent, wrap="word", state="disabled",
                                    background=LIGHT_BACKGROUND, foreground=TEXT_COLOUR,
                                    insertbackground=TEXT_COLOUR, selectbackground="#dbeafe",
                                    selectforeground=TEXT_COLOUR, relief="solid", borderwidth=1,
                                    yscrollcommand=self.settings_log_scrollbar.set)
        self.settings_log.grid(row=1, column=0, sticky="nsew")
        self.settings_log_scrollbar.configure(command=self.settings_log.yview)
        self.settings_log_scrollbar.grid(row=1, column=1, sticky="ns")
        self.settings_log.configure(state="normal")
        self.settings_log.insert("1.0", "\n".join(self.event_lines))
        self.settings_log.configure(state="disabled")

    def open_historical_events(self) -> None:
        """Open the date-query view without reading persisted history until Search."""
        if self.historical_event_window and self.historical_event_window.winfo_exists():
            self.historical_event_window.deiconify()
            self.historical_event_window.lift()
            return
        window = tk.Toplevel(self.root)
        self.historical_event_window = window
        self._historical_query_view_generation += 1
        self._historical_query_generation = None
        self._historical_event_records = ()
        self._historical_event_selected_key = None
        self._historical_query_result = None
        self._historical_query_page_number = 1
        self._historical_requested_page_number = None
        self._historical_event_selected_detail = None
        self._historical_event_detail_request_id = None
        self._historical_event_detail_status_key = None
        self._historical_query_diagnostics = ()
        self._historical_showing_diagnostics = False
        self._historical_diagnostic_page_number = 1
        self._historical_query_status_key = "app.settings.history.not_queried"
        self._historical_query_status_parameters = {}
        self._historical_range_mode = "last90"
        window.title(self._t("app.settings.history.title"))
        window.geometry("820x560")
        window.minsize(560, 360)
        outer = ttk.Frame(window, padding=12)
        outer.pack(fill="both", expand=True)

        range_controls = ttk.Frame(outer)
        range_controls.pack(fill="x", pady=(0, 6))
        self.historical_range_label = ttk.Label(
            range_controls, text=self._t("app.settings.history.range"))
        self.historical_range_label.grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.historical_range_choice = ttk.Combobox(
            range_controls, state="readonly", width=18,
            values=self._historical_range_mode_labels())
        self.historical_range_choice.grid(row=0, column=1, sticky="w")
        self.historical_range_choice.current(3)
        self.historical_range_choice.bind(
            "<<ComboboxSelected>>", self._on_historical_range_mode_selected)
        self.historical_start_var = tk.StringVar(master=window)
        self.historical_end_var = tk.StringVar(master=window)
        initial_range = recent_historical_event_date_range(date.today(), 90)
        self.historical_start_var.set(initial_range.start.isoformat())
        self.historical_end_var.set(initial_range.end.isoformat())
        dates = ttk.Frame(outer)
        dates.pack(fill="x", pady=(0, 3))
        self.historical_start_label = ttk.Label(
            dates, text=self._t("app.settings.history.start"))
        self.historical_start_label.grid(row=0, column=0, sticky="w", padx=(0, 5))
        self.historical_start_entry = ttk.Entry(
            dates, textvariable=self.historical_start_var, width=12)
        self.historical_start_entry.grid(row=0, column=1, sticky="w", padx=(0, 12))
        self.historical_end_label = ttk.Label(
            dates, text=self._t("app.settings.history.end"))
        self.historical_end_label.grid(row=0, column=2, sticky="w", padx=(0, 5))
        self.historical_end_entry = ttk.Entry(
            dates, textvariable=self.historical_end_var, width=12)
        self.historical_end_entry.grid(row=0, column=3, sticky="w")
        self.historical_start_entry.bind(
            "<KeyRelease>", self._on_historical_date_edited, add="+")
        self.historical_end_entry.bind(
            "<KeyRelease>", self._on_historical_date_edited, add="+")
        self.historical_date_error = ttk.Label(
            outer, text="", foreground="#b91c1c", wraplength=780)
        self.historical_date_error.pack(fill="x", anchor="w")
        self.historical_query_status = ttk.Label(
            outer, text=self._t("app.settings.history.not_queried"), wraplength=780)
        self.historical_query_status.pack(fill="x", anchor="w", pady=(0, 5))

        page_controls = ttk.Frame(outer)
        page_controls.pack(fill="x", pady=(0, 4))
        self.historical_previous_button = ttk.Button(
            page_controls, text="←", width=4, takefocus=True,
            command=self._show_previous_historical_event_page, state="disabled")
        self.historical_previous_button.pack(side="left")
        self.historical_page_label = ttk.Label(
            page_controls, text=self._t("app.settings.history.page_empty"), anchor="center")
        self.historical_page_label.pack(side="left", fill="x", expand=True)
        self.historical_next_button = ttk.Button(
            page_controls, text="→", width=4, takefocus=True,
            command=self._show_next_historical_event_page, state="disabled")
        self.historical_next_button.pack(side="right")

        headings = ttk.Frame(outer)
        headings.pack(fill="x")
        self.historical_event_heading = ttk.Label(
            headings, text=self._t("app.settings.history.events"))
        self.historical_event_heading.pack(side="left", fill="x", expand=True)
        self.historical_event_detail_heading = ttk.Label(
            headings, text=self._t("app.settings.history.detail"))
        self.historical_event_detail_heading.pack(side="right", fill="x", expand=True)
        body = ttk.Frame(outer)
        body.pack(fill="both", expand=True, pady=(6, 8))
        self.historical_event_list = tk.Listbox(body, exportselection=False, width=38,
                                                selectmode="browse")
        self.historical_event_list.pack(side="left", fill="both", expand=True)
        self.historical_event_list.bind("<<ListboxSelect>>", self._select_historical_event)
        detail_frame = ttk.Frame(body)
        detail_frame.pack(side="right", fill="both", expand=True, padx=(8, 0))
        scrollbar = ttk.Scrollbar(detail_frame, orient="vertical")
        scrollbar.pack(side="right", fill="y")
        self.historical_event_detail = tk.Text(
            detail_frame, wrap="word", state="disabled", yscrollcommand=scrollbar.set,
            background=FIELD_BACKGROUND, foreground=TEXT_COLOUR,
            selectbackground="#dbeafe", selectforeground=TEXT_COLOUR)
        self.historical_event_detail.pack(side="left", fill="both", expand=True)
        scrollbar.configure(command=self.historical_event_detail.yview)
        controls = ttk.Frame(outer)
        controls.pack(fill="x")
        self.historical_event_refresh_button = ttk.Button(
            controls, text="🔍 {}".format(self._t("app.settings.history.search")),
            width=20, takefocus=True,
            command=self._reload_historical_events)
        self.historical_event_refresh_button.pack(side="right", padx=(6, 0))
        self.historical_event_cancel_button = ttk.Button(
            controls, text=self._t("app.settings.history.cancel_query"),
            command=self._cancel_historical_event_query, state="disabled")
        self.historical_event_cancel_button.pack(side="right")
        self.historical_event_retry_button = ttk.Button(
            controls, text=self._t("app.settings.history.retry_remaining"),
            command=self._retry_historical_event_preparation, state="disabled")
        self.historical_event_retry_button.pack(side="right", padx=(6, 0))
        self._historical_control_hints = (
            _LocalizedControlHint(
                self.historical_event_refresh_button,
                lambda: self._t("app.settings.history.search_hint")),
            _LocalizedControlHint(
                self.historical_previous_button,
                lambda: self._t("app.settings.history.previous_page_hint")),
            _LocalizedControlHint(
                self.historical_next_button,
                lambda: self._t("app.settings.history.next_page_hint")),
        )
        self._refresh_historical_event_window()
        window.protocol("WM_DELETE_WINDOW", self._close_historical_event_window)
        window.bind("<Destroy>", self._on_historical_event_destroy, add="+")
        self._unregister_historical_event_language_receiver = self.register_language_receiver(
            lambda: self._t("app.settings.history.title"),
            self._refresh_historical_event_window,
            lambda: self.historical_event_window is window and window.winfo_exists(),
        )

    def _historical_range_mode_keys(self):
        return ("today", "last7", "last30", "last90", "single", "custom")

    def _historical_range_mode_labels(self):
        return tuple(self._t("app.settings.history.mode." + key)
                     for key in self._historical_range_mode_keys())

    def _on_historical_range_mode_selected(self, _event=None) -> None:
        if self._updating_historical_controls or self.historical_range_choice is None:
            return
        selected = self.historical_range_choice.current()
        keys = self._historical_range_mode_keys()
        if selected < 0 or selected >= len(keys):
            return
        self._historical_range_mode = keys[selected]
        today = date.today()
        if self._historical_range_mode == "today":
            date_range = recent_historical_event_date_range(today, 1)
        elif self._historical_range_mode.startswith("last"):
            days = int(self._historical_range_mode[4:])
            date_range = recent_historical_event_date_range(today, days)
        elif self._historical_range_mode == "single":
            date_range = recent_historical_event_date_range(today, 1)
        else:
            return
        self._updating_historical_controls = True
        try:
            self.historical_start_var.set(date_range.start.isoformat())
            self.historical_end_var.set(date_range.end.isoformat())
        finally:
            self._updating_historical_controls = False
        self._set_historical_date_error(None)

    def _on_historical_date_edited(self, _event=None) -> None:
        if self._updating_historical_controls:
            return
        self._historical_range_mode = "custom"
        self._updating_historical_controls = True
        try:
            self.historical_range_choice.current(5)
        finally:
            self._updating_historical_controls = False

    def _set_historical_date_error(self, message_key) -> None:
        self._historical_date_error_key = message_key
        if self.historical_date_error is not None:
            self.historical_date_error.configure(
                text=self._t(message_key) if message_key else "")

    def _reload_historical_events(self) -> None:
        self._submit_historical_event_query()

    def _submit_historical_event_query(self, _event=None):
        window = self.historical_event_window
        if window is None or not window.winfo_exists():
            return "break"
        try:
            date_range = parse_historical_event_date_range(
                self.historical_start_var.get(), self.historical_end_var.get())
        except HistoricalEventDateError as error:
            self._set_historical_date_error(
                "app.settings.history.validation." + error.reason)
            if error.field_name == "start":
                self.historical_start_entry.focus_set()
            else:
                self.historical_end_entry.focus_set()
            return "break"

        self._set_historical_date_error(None)
        self._cancel_ui_timer(self._historical_query_after_id)
        self._cancel_historical_event_page()
        generation = self._historical_query_service.submit(date_range)
        self._historical_query_generation = generation
        self._historical_query_inflight_range = date_range
        self._historical_query_status_key = "app.settings.history.querying"
        self._historical_query_status_parameters = {}
        self.historical_event_retry_button.configure(state="disabled")
        self.historical_event_cancel_button.configure(state="normal")
        self._refresh_historical_query_status()
        self._schedule_historical_query_poll(
            window, self._historical_query_view_generation, generation)
        return "break"

    def _retry_historical_event_preparation(self) -> None:
        result = self._historical_query_result
        if (result is None or not result.preparation_complete or
                result.preparation_error is None):
            return
        try:
            generation = self._historical_query_service.retry_preparation(result)
        except HistoricalEventSnapshotUnavailable as error:
            self._historical_query_status_key = (
                "app.settings.history.snapshot_unavailable")
            self._historical_query_status_parameters = {"reason": str(error)}
            self._refresh_historical_query_status()
            self._refresh_historical_event_window()
            return
        except (RuntimeError, ValueError) as error:
            self._historical_query_status_key = "app.settings.history.preparation_failed"
            self._historical_query_status_parameters = {"reason": str(error)}
            self._refresh_historical_query_status()
            self._refresh_historical_event_window()
            return
        self._historical_query_generation = generation
        self._historical_query_inflight_range = result.date_range
        self._historical_query_status_key = "app.settings.history.preparation_retrying"
        self._historical_query_status_parameters = {}
        self.historical_event_retry_button.configure(state="disabled")
        self.historical_event_cancel_button.configure(state="normal")
        self._refresh_historical_query_status()
        self._schedule_historical_query_poll(
            self.historical_event_window, self._historical_query_view_generation,
            generation)

    def _cancel_historical_event_query(self) -> None:
        generation = self._historical_query_generation
        if generation is None:
            return
        self._historical_query_service.cancel(generation)
        self._historical_query_generation = None
        self._historical_query_inflight_range = None
        self._cancel_ui_timer(self._historical_query_after_id)
        self._historical_query_after_id = None
        if self.historical_event_cancel_button is not None:
            self.historical_event_cancel_button.configure(state="disabled")
        self._historical_query_status_key = "app.settings.history.query_cancelled"
        self._historical_query_status_parameters = {}
        self._refresh_historical_query_status()
        result = self._historical_query_result
        if result is not None and not result.preparation_complete:
            self._schedule_ui(
                50, self._refresh_cancelled_preparation_state,
                result, self._historical_query_view_generation)
        else:
            self._refresh_historical_event_window()

    def _refresh_cancelled_preparation_state(self, result, view_generation) -> None:
        if view_generation != self._historical_query_view_generation:
            return
        if not result.preparation_complete:
            self._schedule_ui(
                50, self._refresh_cancelled_preparation_state,
                result, view_generation)
            return
        if result is self._historical_query_result:
            self._refresh_historical_event_window()

    def _schedule_historical_query_poll(self, window, view_generation, generation) -> None:
        self._historical_query_after_id = self._schedule_ui(
            40, self._poll_historical_event_query,
            window, view_generation, generation)

    def _poll_historical_event_query(self, window, view_generation, generation) -> None:
        self._historical_query_after_id = None
        if (view_generation != self._historical_query_view_generation or
                generation != self._historical_query_generation or
                self.historical_event_window is not window or not window.winfo_exists()):
            return
        initial = self._historical_query_service.take_initial_result(generation)
        if initial is not None and initial.succeeded:
            previous_result = self._historical_query_result
            self._cancel_historical_event_detail()
            self._cancel_historical_event_page()
            self._historical_query_result = initial.result
            self._historical_query_page_number = 1
            self._historical_event_records = initial.result.events
            self._historical_query_diagnostics = initial.result.diagnostics
            self._historical_showing_diagnostics = False
            self._historical_diagnostic_page_number = 1
            self._historical_event_selected_key = None
            self._historical_event_selected_detail = None
            self._historical_event_detail_status_key = None
            self._historical_query_status_key = "app.settings.history.preparing"
            self._historical_query_status_parameters = {}
            if previous_result is not None and previous_result is not initial.result:
                previous_result.close()
            self._refresh_historical_event_window()
            self._schedule_historical_query_poll(window, view_generation, generation)
            return
        completion = self._historical_query_service.take_result(generation)
        if completion is None and self._historical_query_service.is_pending(generation):
            self._schedule_historical_query_poll(window, view_generation, generation)
            return
        self._historical_query_generation = None
        self._historical_query_inflight_range = None
        self.historical_event_cancel_button.configure(state="disabled")
        if completion is not None and completion.succeeded:
            if completion.result is self._historical_query_result:
                preparation_error = completion.result.preparation_error
                if preparation_error is not None:
                    self._historical_query_status_key = (
                        "app.settings.history.preparation_failed")
                    self._historical_query_status_parameters = {
                        "reason": str(preparation_error)}
                else:
                    self._historical_query_status_key = ""
                    self._historical_query_status_parameters = {}
                self._refresh_historical_query_status()
                self._refresh_historical_event_window()
                return
            previous_result = self._historical_query_result
            self._cancel_historical_event_detail()
            self._cancel_historical_event_page()
            self._historical_query_result = completion.result
            self._historical_query_page_number = 1
            # The query worker publishes the prepared first batch; Tk never reads
            # the snapshot database while replacing the visible result.
            self._historical_event_records = completion.result.events
            self._historical_query_diagnostics = completion.result.diagnostics
            self._historical_showing_diagnostics = False
            self._historical_diagnostic_page_number = 1
            self._historical_event_selected_key = None
            self._historical_event_selected_detail = None
            self._historical_event_detail_status_key = None
            self._historical_query_status_key = ""
            self._historical_query_status_parameters = {}
            if previous_result is not None and previous_result is not completion.result:
                previous_result.close()
            self._refresh_historical_event_window()
        elif completion is not None:
            if completion.result is None and self._historical_query_result is not None and \
                    self._historical_query_result.date_range == completion.date_range:
                self._historical_query_status_key = (
                    "app.settings.history.snapshot_unavailable"
                    if isinstance(completion.error, HistoricalEventSnapshotUnavailable) else
                    "app.settings.history.preparation_failed")
                self._historical_query_status_parameters = {
                    "reason": str(completion.error)}
                self._refresh_historical_query_status()
                self._refresh_historical_event_window()
                return
            self._historical_query_status_key = "app.settings.history.query_failed"
            self._historical_query_status_parameters = {
                "reason": str(completion.error)}
            self._refresh_historical_query_status()
            self._refresh_historical_event_window()
        else:
            self._historical_query_status_key = "app.settings.history.query_cancelled"
            self._historical_query_status_parameters = {}
            self._refresh_historical_query_status()
            self._refresh_historical_event_window()

    def _refresh_historical_query_status(self) -> None:
        if self.historical_query_status is None:
            return
        result = self._historical_query_result
        if self._historical_query_status_key:
            text = self._t(self._historical_query_status_key,
                           **self._historical_query_status_parameters)
        elif result is None:
            text = self._t("app.settings.history.not_queried")
        elif result.source_issue_count or result.unclassified_count:
            text = self._t(
                "app.settings.history.incomplete_results",
                count=result.total_count, issues=result.source_issue_count,
                unclassified=result.unclassified_count)
        elif result.total_count == 0:
            text = self._t("app.settings.history.no_results")
        else:
            text = self._t("app.settings.history.result_count", count=result.total_count,
                           start=result.date_range.start.isoformat(),
                           end=result.date_range.end.isoformat())
        if (result is not None and self._historical_query_status_key in {
                "app.settings.history.querying", "app.settings.history.query_failed",
                "app.settings.history.query_cancelled"}):
            text += " " + self._t(
                "app.settings.history.previous_result_range",
                start=result.date_range.start.isoformat(),
                end=result.date_range.end.isoformat())
        if result is not None and result.index_degraded:
            text += " " + self._t("app.settings.history.index_degraded")
        self.historical_query_status.configure(text=text)

    def _refresh_historical_event_window(self) -> None:
        window = self.historical_event_window
        if window is None or not window.winfo_exists():
            return
        window.title(self._t("app.settings.history.title"))
        selected = self._historical_event_selected_key
        event_list = self.historical_event_list
        detail_view = self.historical_event_detail
        list_top_index = int(event_list.index("@0,0")) if event_list.size() else 0
        record_index = list_top_index - 1 if self._historical_showing_diagnostics else list_top_index
        list_top_key = (self._historical_event_records[record_index].key
                        if 0 <= record_index < len(self._historical_event_records) else
                        "__query_diagnostics__" if not self._historical_showing_diagnostics and
                        self._historical_query_result is not None and
                        self._historical_query_result.diagnostic_count and
                        list_top_index == len(self._historical_event_records) else None)
        detail_top = detail_view.index("@0,0")
        self.historical_event_heading.configure(text=self._t("app.settings.history.events"))
        self.historical_event_detail_heading.configure(
            text=self._t("app.settings.history.detail"))
        result = self._historical_query_result
        if result is None:
            self.historical_page_label.configure(
                text=self._t("app.settings.history.page_empty"))
            self.historical_previous_button.configure(state="disabled")
            self.historical_next_button.configure(state="disabled")
        elif self._historical_showing_diagnostics:
            page_count = max(1, (result.diagnostic_count + result.page_size - 1) //
                            result.page_size)
            current_page = self._historical_diagnostic_page_number
            page_label = (self._t(
                "app.settings.history.page_loading",
                page=self._historical_requested_page_number)
                if self._historical_page_request_id is not None else self._t(
                    "app.settings.history.page_status", page=current_page,
                    pages=page_count, count=result.diagnostic_count))
            self.historical_page_label.configure(text=page_label)
            self.historical_previous_button.configure(
                state="normal" if current_page > 1 else "disabled")
            self.historical_next_button.configure(
                state="normal" if current_page < page_count else "disabled")
        elif result.total_count == 0:
            self.historical_page_label.configure(
                text=self._t("app.settings.history.page_empty"))
            self.historical_previous_button.configure(state="disabled")
            self.historical_next_button.configure(state="disabled")
        else:
            page_count = result.page_count
            page_label = (self._t(
                "app.settings.history.page_loading",
                page=self._historical_requested_page_number)
                if self._historical_page_request_id is not None else self._t(
                    "app.settings.history.page_status",
                    page=self._historical_query_page_number,
                    pages=page_count, count=result.total_count))
            self.historical_page_label.configure(text=page_label)
            self.historical_previous_button.configure(
                state="normal" if self._historical_query_page_number > 1 else "disabled")
            self.historical_next_button.configure(
                state="normal" if self._historical_query_page_number < page_count else "disabled")
        self.historical_event_cancel_button.configure(
            text=self._t("app.settings.history.cancel_query"))
        result = self._historical_query_result
        retryable = (result is not None and result.preparation_complete and
                     result.preparation_error is not None and
                     result.prepared_count < result.total_count and
                     not isinstance(result.preparation_error,
                                    HistoricalEventSnapshotUnavailable))
        self.historical_event_retry_button.configure(
            text=self._t("app.settings.history.retry_remaining"),
            state="normal" if retryable and self._historical_query_generation is None
            else "disabled")
        self.historical_event_refresh_button.configure(
            text="🔍 {}".format(self._t("app.settings.history.search")))
        for hint in self._historical_control_hints:
            hint.refresh()
        self.historical_range_label.configure(text=self._t("app.settings.history.range"))
        self.historical_start_label.configure(text=self._t("app.settings.history.start"))
        self.historical_end_label.configure(text=self._t("app.settings.history.end"))
        self.historical_date_error.configure(
            text=self._t(self._historical_date_error_key)
            if self._historical_date_error_key else "")
        self._updating_historical_controls = True
        try:
            self.historical_range_choice.configure(values=self._historical_range_mode_labels())
            self.historical_range_choice.current(
                self._historical_range_mode_keys().index(self._historical_range_mode))
        finally:
            self._updating_historical_controls = False
        self._refresh_historical_query_status()
        event_list.delete(0, "end")
        selected_index = None
        if self._historical_showing_diagnostics:
            event_list.insert("end", self._t("app.settings.history.back_to_events"))
            for index, event in enumerate(self._historical_event_records, 1):
                presentation = render_historical_event_message(event, self.current_language)
                category = self._t("app.settings.history.source.error")
                event_list.insert("end", "{} · {} · {}".format(
                    event.occurred_at or "—", category, presentation.message))
                if event.key == selected:
                    selected_index = index
        else:
            for index, event in enumerate(self._historical_event_records):
                presentation = render_historical_event_message(event, self.current_language)
                category_id = ("app.settings.history.source.app" if event.source == "app" else
                               "app.settings.history.source.error" if event.source in {
                                   "read_error", "read_warning"} else
                               "app.settings.history.source.round" if event.round_id else
                               "app.settings.history.source.legacy")
                category = self._t(category_id)
                event_list.insert("end", "{} · {} · {}".format(
                    event.occurred_at or "—", category, presentation.message))
                if event.key == selected:
                    selected_index = index
        if not self._historical_showing_diagnostics and result is not None and \
                result.diagnostic_count:
            warning_index = len(self._historical_event_records)
            event_list.insert("end", "— · {} · {}".format(
                self._t("app.settings.history.source.error"),
                self._t("app.settings.history.diagnostic_list",
                        count=result.diagnostic_count)))
            if selected == "__query_diagnostics__":
                selected_index = warning_index
        if selected_index is None and self._historical_event_records:
            selected_index = 0
        elif (selected_index is None and self._historical_showing_diagnostics and
              self._historical_event_records):
            selected_index = 1
        elif (selected_index is None and not self._historical_showing_diagnostics and
              result is not None and result.diagnostic_count):
            selected_index = len(self._historical_event_records)
        if selected_index is not None:
            event_list.selection_clear(0, "end")
            event_list.selection_set(selected_index)
            event_list.activate(selected_index)
            if self._historical_showing_diagnostics:
                if selected_index > 0:
                    event = self._historical_event_records[selected_index - 1]
                    self._historical_event_selected_key = event.key
                    if (self._historical_event_selected_detail is not None and
                            self._historical_event_selected_detail.key == event.key):
                        self._render_historical_event_detail(
                            self._historical_event_selected_detail)
                    elif self._historical_event_detail_request_id is None and \
                            self._historical_page_request_id is None:
                        self._request_historical_event_detail(event.key)
            elif selected_index < len(self._historical_event_records):
                event = self._historical_event_records[selected_index]
                self._historical_event_selected_key = event.key
                if (self._historical_event_selected_detail is not None and
                        self._historical_event_selected_detail.key == event.key):
                    self._render_historical_event_detail(self._historical_event_selected_detail)
                elif self._historical_event_detail_request_id is not None:
                    self._set_historical_event_detail(
                        self._t("app.settings.history.detail_loading"))
                elif self._historical_page_request_id is not None:
                    # Keep the previous page's detail visible while its replacement
                    # is read; requesting it again would supersede the page request
                    # on the shared bounded result-reader worker.
                    pass
                elif self._historical_event_detail_status_key is not None:
                    self._set_historical_event_detail(
                        self._t(self._historical_event_detail_status_key))
                else:
                    self._request_historical_event_detail(event.key)
            elif not self._historical_showing_diagnostics:
                self._historical_event_selected_key = "__query_diagnostics__"
                self._set_historical_event_detail(
                    self._t("app.settings.history.diagnostic_list_detail"))
        elif self._historical_event_records:
            self._historical_event_selected_key = None
            self._set_historical_event_detail(self._t("app.settings.history.empty"))
        else:
            self._historical_event_selected_key = None
            self._set_historical_event_detail(
                self._t("app.settings.history.empty") if self._historical_query_result is None
                else self._t("app.settings.history.no_results"))
        if self._historical_restore_after_id is not None:
            self._cancel_ui_timer(self._historical_restore_after_id)

        def restore_view():
            self._historical_restore_after_id = None
            self._restore_historical_event_view(
                window, event_list, detail_view, list_top_key, detail_top)

        self._historical_restore_after_id = self._schedule_ui("idle", restore_view)

    def _restore_historical_event_view(self, window, event_list, detail_view,
                                       list_top_key: Optional[str], detail_top: str) -> None:
        if not window.winfo_exists():
            return
        if list_top_key == "__query_diagnostics__":
            list_top_index = (len(self._historical_event_records)
                              if self._historical_query_result is not None and
                              self._historical_query_result.diagnostic_count else 0)
        else:
            offset = 1 if self._historical_showing_diagnostics else 0
            list_top_index = next((index + offset for index, event in enumerate(
                self._historical_event_records) if event.key == list_top_key), 0)
        if event_list.size():
            target = min(max(0, list_top_index), event_list.size() - 1)
            event_list.yview_moveto(float(target) / event_list.size())
        detail_view.yview(detail_top)

    def _select_historical_event(self, _event=None) -> None:
        if self.historical_event_list is None:
            return
        selection = self.historical_event_list.curselection()
        if not selection:
            return
        self._cancel_historical_event_page()
        index = int(selection[0])
        if self._historical_showing_diagnostics:
            if index == 0:
                self._historical_showing_diagnostics = False
                self._historical_event_selected_key = None
                self._cancel_historical_event_detail()
                self._show_historical_event_page(self._historical_query_page_number)
            elif 1 <= index <= len(self._historical_event_records):
                record = self._historical_event_records[index - 1]
                self._historical_event_selected_key = record.key
                self._request_historical_event_detail(record.key)
        elif 0 <= index < len(self._historical_event_records):
            record = self._historical_event_records[index]
            self._historical_event_selected_key = record.key
            self._request_historical_event_detail(record.key)
        elif (index == len(self._historical_event_records) and
              self._historical_query_result is not None and
              self._historical_query_result.diagnostic_count):
            self._historical_event_selected_key = "__query_diagnostics__"
            self._historical_showing_diagnostics = True
            self._historical_diagnostic_page_number = 1
            self._show_historical_event_page(1)

    def _show_previous_historical_event_page(self) -> None:
        current = (self._historical_requested_page_number
                   if self._historical_requested_page_number is not None else
                   self._historical_diagnostic_page_number if
                   self._historical_showing_diagnostics else
                   self._historical_query_page_number)
        self._show_historical_event_page(current - 1)

    def _show_next_historical_event_page(self) -> None:
        current = (self._historical_requested_page_number
                   if self._historical_requested_page_number is not None else
                   self._historical_diagnostic_page_number if
                   self._historical_showing_diagnostics else
                   self._historical_query_page_number)
        self._show_historical_event_page(current + 1)

    def _show_historical_event_page(self, page_number: int) -> None:
        result = self._historical_query_result
        window = self.historical_event_window
        if result is None or window is None or not window.winfo_exists():
            return
        page_count = (max(1, (result.diagnostic_count + result.page_size - 1) //
                          result.page_size) if self._historical_showing_diagnostics
                      else result.page_count)
        if page_number < 1 or page_number > page_count:
            return
        self._cancel_historical_event_detail()
        self._cancel_historical_event_page()
        request_id = (self._historical_detail_service.submit_diagnostic_page(
            result, page_number) if self._historical_showing_diagnostics else
            self._historical_detail_service.submit_page(result, page_number))
        self._historical_page_request_id = request_id
        self._historical_requested_page_number = page_number
        self._refresh_historical_event_window()
        self._schedule_historical_event_page_poll(
            window, self._historical_query_view_generation, result, page_number, request_id)

    def _schedule_historical_event_page_poll(self, window, view_generation, result,
                                             page_number, request_id) -> None:
        self._historical_page_after_id = self._schedule_ui(
            35, self._poll_historical_event_page, window, view_generation,
            result, page_number, request_id)

    def _poll_historical_event_page(self, window, view_generation, result,
                                    page_number, request_id) -> None:
        self._historical_page_after_id = None
        if (view_generation != self._historical_query_view_generation or
                self.historical_event_window is not window or not window.winfo_exists() or
                self._historical_query_result is not result or
                self._historical_page_request_id != request_id):
            return
        completion = self._historical_detail_service.take_result(request_id)
        if completion is None and self._historical_detail_service.is_pending(request_id):
            self._schedule_historical_event_page_poll(
                window, view_generation, result, page_number, request_id)
            return
        self._historical_page_request_id = None
        self._historical_requested_page_number = None
        if completion is not None and completion.succeeded and completion.page is not None:
            if self._historical_showing_diagnostics:
                self._historical_diagnostic_page_number = completion.page.page_number
            else:
                self._historical_query_page_number = completion.page.page_number
            self._historical_event_records = completion.page.events
            self._historical_event_selected_key = None
            self._historical_event_selected_detail = None
            self._historical_event_detail_status_key = None
            self._refresh_historical_event_window()
        else:
            self._refresh_historical_event_window()

    def _cancel_historical_event_page(self) -> None:
        request_id = self._historical_page_request_id
        if request_id is not None:
            self._historical_detail_service.cancel(request_id)
            self._historical_page_request_id = None
        if self._historical_page_after_id is not None:
            self._cancel_ui_timer(self._historical_page_after_id)
            self._historical_page_after_id = None
        self._historical_requested_page_number = None

    def _cancel_historical_event_detail(self) -> None:
        request_id = self._historical_event_detail_request_id
        if request_id is not None:
            self._historical_detail_service.cancel(request_id)
            self._historical_event_detail_request_id = None
        if self._historical_detail_after_id is not None:
            self._cancel_ui_timer(self._historical_detail_after_id)
            self._historical_detail_after_id = None

    def _request_historical_event_detail(self, event_key: str) -> None:
        result = self._historical_query_result
        window = self.historical_event_window
        if (result is None or window is None or not window.winfo_exists() or
                event_key != self._historical_event_selected_key):
            return
        self._cancel_historical_event_detail()
        self._historical_event_selected_detail = None
        self._historical_event_detail_status_key = None
        request_id = (self._historical_detail_service.submit_diagnostic(
            result, event_key) if self._historical_showing_diagnostics else
            self._historical_detail_service.submit(result, event_key))
        self._historical_event_detail_request_id = request_id
        self._set_historical_event_detail(
            self._t("app.settings.history.detail_loading"))
        self._schedule_historical_event_detail_poll(
            window, self._historical_query_view_generation, result, event_key, request_id)

    def _schedule_historical_event_detail_poll(self, window, view_generation, result,
                                              event_key, request_id) -> None:
        self._historical_detail_after_id = self._schedule_ui(
            35, self._poll_historical_event_detail, window, view_generation,
            result, event_key, request_id)

    def _poll_historical_event_detail(self, window, view_generation, result,
                                      event_key, request_id) -> None:
        self._historical_detail_after_id = None
        if (view_generation != self._historical_query_view_generation or
                self.historical_event_window is not window or not window.winfo_exists() or
                self._historical_query_result is not result or
                self._historical_event_selected_key != event_key or
                self._historical_event_detail_request_id != request_id):
            return
        completion = self._historical_detail_service.take_result(request_id)
        if completion is None and self._historical_detail_service.is_pending(request_id):
            self._schedule_historical_event_detail_poll(
                window, view_generation, result, event_key, request_id)
            return
        self._historical_event_detail_request_id = None
        if completion is not None and completion.succeeded and completion.event is not None:
            self._historical_event_selected_detail = completion.event
            self._historical_event_detail_status_key = None
            self._render_historical_event_detail(completion.event)
        else:
            self._historical_event_selected_detail = None
            unavailable_key = (
                "app.settings.history.source_no_longer_available"
                if completion is not None and completion.error is None else
                "app.settings.history.detail_unavailable")
            self._historical_event_detail_status_key = unavailable_key
            self._set_historical_event_detail(
                self._t(unavailable_key))

    def _render_historical_event_detail(self, event: HistoricalEvent) -> None:
        presentation = render_historical_event(event, self.current_language)
        self._set_historical_event_detail(presentation.message + "\n\n" + presentation.detail)

    def _render_historical_query_diagnostics(self) -> None:
        sections = []
        for event in self._historical_query_diagnostics:
            presentation = render_historical_event(event, self.current_language)
            sections.append(presentation.message + "\n\n" + presentation.detail)
        remaining = (self._historical_query_result.unclassified_count -
                     len(self._historical_query_diagnostics))
        if remaining > 0:
            sections.append(self._t("app.settings.history.diagnostics_truncated",
                                    count=remaining))
        self._set_historical_event_detail("\n\n".join(sections))

    def _set_historical_event_detail(self, value: str) -> None:
        widget = self.historical_event_detail
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="disabled")

    def _close_historical_event_window(self) -> None:
        window = self.historical_event_window
        if window and window.winfo_exists():
            window.destroy()
        self._clear_historical_event_window(window)

    def _on_historical_event_destroy(self, event) -> None:
        if event.widget is self.historical_event_window:
            self._clear_historical_event_window(event.widget)

    def _clear_historical_event_window(self, window) -> None:
        if self.historical_event_window is not window:
            return
        unregister = self._unregister_historical_event_language_receiver
        self._unregister_historical_event_language_receiver = None
        if unregister is not None:
            unregister()
        for hint in self._historical_control_hints:
            hint.close()
        self._historical_control_hints = ()
        if self._historical_restore_after_id is not None:
            self._cancel_ui_timer(self._historical_restore_after_id)
            self._historical_restore_after_id = None
        if self._historical_query_after_id is not None:
            self._cancel_ui_timer(self._historical_query_after_id)
            self._historical_query_after_id = None
        self._cancel_historical_event_detail()
        self._cancel_historical_event_page()
        generation = self._historical_query_generation
        if generation is not None:
            self._historical_query_service.cancel(generation)
        result = self._historical_query_result
        if result is not None:
            result.close()
        self._historical_query_result = None
        self._historical_event_records = ()
        self._historical_query_diagnostics = ()
        self._historical_event_selected_detail = None
        self._historical_query_generation = None
        self._historical_query_view_generation += 1
        self._historical_query_inflight_range = None
        self.historical_event_window = None
        self.historical_event_list = None
        self.historical_event_detail = None
        self.historical_event_heading = None
        self.historical_event_detail_heading = None
        self.historical_event_refresh_button = None
        self.historical_event_cancel_button = None
        self.historical_event_retry_button = None
        self.historical_previous_button = None
        self.historical_next_button = None
        self.historical_page_label = None
        self.historical_range_label = None
        self.historical_start_label = None
        self.historical_end_label = None
        self.historical_range_choice = None
        self.historical_start_var = None
        self.historical_end_var = None
        self.historical_start_entry = None
        self.historical_end_entry = None
        self.historical_date_error = None
        self.historical_query_status = None
        self._historical_event_selected_key = None
        self._historical_event_selected_detail = None

    def _close_settings(self) -> None:
        window = self.settings_window
        if window and window.winfo_exists():
            window.destroy()
        self._clear_settings_window(window)

    def _on_settings_destroy(self, event) -> None:
        if event.widget is self.settings_window:
            self._clear_settings_window(event.widget)

    def _clear_settings_window(self, window) -> None:
        if self.settings_window is not window:
            return
        unregister = self._unregister_settings_language_receiver
        self._unregister_settings_language_receiver = None
        if unregister is not None:
            unregister()
        self.settings_window = None
        self.settings_log = None
        self.retention_cleanup_text = None
        self._settings_text_widgets = []
        self._settings_tab_ids = []
        self._profile_editor_status_message = None
        self._retention_status_message = None

    def open_session(self) -> None:
        path = self.rounds.session_path or self.session_root
        try:
            path.mkdir(parents=True, exist_ok=True)
            subprocess.Popen(["open", str(path)])
        except OSError as error:
            reason = str(error)
            self._record_app_event("app.settings.event.session.open_failed",
                                   {"reason": reason}, reason)
            self._show_notice("app.settings.session.open", "app.settings.session.open_failed",
                              {"reason": reason})

    def close(self) -> None:
        rounds = getattr(self, "rounds", None)
        if rounds is None:
            self._finish_close()
            return
        if self._closing_ui:
            return
        self._cancel_historical_event_query()
        try:
            self._save_preferences()
        except (OSError, ProfileError) as error:
            self._record_app_event("app.profile.save_failed", {"reason": str(error)}, str(error))
            self._show_notice("app.profile.save_title", "app.profile.save_failed",
                              {"reason": str(error)})
        self._closing_ui = True
        self._refresh_language_entry()
        self._set_monitor_controls(self._round_is_active())
        status = rounds.request_close()
        self._show_close_progress(status)
        self._schedule_close_poll(status.generation)

    def _show_close_progress(self, status) -> None:
        if self._close_window is None or not self._close_window.winfo_exists():
            window = tk.Toplevel(self.root)
            self._close_window = window
            window.title(self._t("app.close.title"))
            window.geometry("500x240")
            window.resizable(False, False)
            window.transient(self.root)
            window.protocol("WM_DELETE_WINDOW", self.cancel_close)
            self._close_status_label = ttk.Label(window, text="正在停止來源並確認所有輪次紀錄…",
                                                  wraplength=460, justify="left")
            self._close_status_label.pack(fill="x", padx=18, pady=(18, 8))
            self._close_language_reason_label = ttk.Label(
                window, text="", wraplength=460, justify="left")
            self._close_language_reason_label.pack(fill="x", padx=18, pady=(0, 6))
            self._close_error_label = ttk.Label(window, text="", wraplength=460, justify="left")
            self._close_error_label.pack(fill="x", padx=18, pady=6)
            actions = ttk.Frame(window)
            actions.pack(fill="x", padx=18, pady=(12, 16))
            self._close_retry_button = ttk.Button(
                actions, text=self._t("app.close.retry"), command=self.retry_close_saves,
                                                  state="disabled")
            self._close_retry_button.pack(side="left")
            self._close_cancel_button = ttk.Button(
                actions, text=self._t("app.close.cancel"), command=self.cancel_close)
            self._close_cancel_button.pack(side="right")
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
        self._close_language_reason_label.configure(
            text=self._t("app.close.language_disabled") if self._closing_ui else "")
        diagnostic = status.message if status.status == "failed" else ""
        self._close_error_label.configure(
            text=self._t("app.close.diagnostic", reason=diagnostic) if diagnostic else "")
        if self._close_retry_button:
            self._close_retry_button.configure(text=self._t("app.close.retry"))
            self._close_retry_button.configure(state="normal" if status.status == "failed" else "disabled")
        if self._close_cancel_button:
            self._close_cancel_button.configure(text=self._t("app.close.cancel"))

    def _schedule_close_poll(self, generation: int) -> None:
        self._close_poll_generation = generation
        self._cancel_ui_timer(self._close_after_id)
        self._close_after_id = self._schedule_ui(
            100, lambda: self._poll_close_status(generation))

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
        self._cancel_ui_timer(self._close_after_id)
        self._close_after_id = None
        self._refresh_language_entry()
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
