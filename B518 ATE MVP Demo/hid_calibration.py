#!/usr/bin/env python3
"""Standalone Arduino HID distance calibration tool for B518 ATE."""
from __future__ import annotations

import queue
import re
import threading
import tkinter as tk
from collections.abc import Callable
from tkinter import messagebox, ttk

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    serial = None
    list_ports = None

try:
    from hid_calibration_version import VERSION as APP_VERSION
except ImportError:
    APP_VERSION = "0.0.0"


TITLE = "Atlas HID 座標校正 B518"
BAUD_RATE = 115200
SCREENSHOT_COMMAND = "SCREENSHOT"
USB_CDC_CONTROL_TERMINATOR = "\n"
KEYBOARD_DELAY_MAX_SECONDS = 120.0
EXPECTED_FIRMWARE_PRODUCT = "B518_ARDUINO_MVP"
EXPECTED_PROTOCOL_VERSION = 1
FIRMWARE_QUERY_DELAY_MS = 800
FIRMWARE_QUERY_MAX_ATTEMPTS = 3
FIRMWARE_QUERY_TIMEOUT_MS = 1400
FIRMWARE_QUERY_RETRY_DELAYS_MS = (350, 900)
COMMAND_TIMEOUT_MS = 3000
NONFATAL_CDC_DIAGNOSTICS = frozenset(("ERR:TCP_NOT_CONNECTED",))
ABSOLUTE_HID_MAX = 32767
ABS_UNSUPPORTED_REPLY = "ERR:ABS_UNSUPPORTED"
HID_NOT_READY_REPLY = "ERR:HID_NOT_READY"
DIAGNOSTIC_TEXT = "HID_DIAG"


def normalize_cdc_line(raw_line: str) -> str:
    """Remove only USB CDC framing bytes, never meaningful payload spacing."""
    return raw_line.strip("\x00\r\n")


def is_nonfatal_cdc_diagnostic(line: str) -> bool:
    """A disconnected TCP bridge does not mean the local HID command failed."""
    return line in NONFATAL_CDC_DIAGNOSTICS


def is_hid_progress_reply(command: str, line: str) -> bool:
    """Return true for a non-terminal firmware ACK for this HID command.

    ACKs remain optional so this tool still calibrates against firmware 1.0.4,
    which only emits them for M_DELTA/M_MOVE/M_RESET/SCREENSHOT.
    """
    if command.startswith("M_DELTA:"):
        return line == "ACK:M_DELTA"
    if command.startswith("M_MOVE:"):
        return line == "ACK:M_MOVE"
    if command.startswith("M_ABS:"):
        return line == "ACK:M_ABS"
    if command.startswith("K_WRITE:"):
        return line == "ACK:K_WRITE"
    return {
        "M_RESET": "ACK:M_RESET",
        "SCREENSHOT": "ACK:SCREENSHOT",
        "M_ABS_CLICK:L": "ACK:M_ABS_CLICK:L",
        "M_CLICK:L": "ACK:M_CLICK:L",
    }.get(command) == line

def parse_firmware_info(line: str) -> tuple[str, str, int, str] | None:
    """Parse the identity line emitted by the canonical B518 firmware."""
    value = line.strip()
    if not value.startswith("INFO:"):
        return None
    fields: dict[str, str] = {}
    for item in value[5:].split(";"):
        if "=" not in item:
            return None
        key, field_value = item.split("=", 1)
        key, field_value = key.strip().upper(), field_value.strip()
        if not key or not field_value or key in fields:
            return None
        fields[key] = field_value
    required = ("PRODUCT", "FW", "PROTO", "BOARD")
    if any(key not in fields for key in required):
        return None
    if not re.fullmatch(r"\d+\.\d+\.\d+", fields["FW"]) or not fields["PROTO"].isdigit():
        return None
    return fields["PRODUCT"], fields["FW"], int(fields["PROTO"]), fields["BOARD"]


def expected_success_reply(command: str) -> str:
    """Return the terminal reply that proves a HID command was executed."""
    if command.startswith("M_DELTA:"):
        return "OK:M_DELTA"
    if command.startswith("K_WRITE:"):
        return "OK:K_WRITE"
    if command.startswith("M_ABS:"):
        return "OK:M_ABS"
    return {
        "M_RESET": "OK:M_RESET",
        "SCREENSHOT": "OK:SCREENSHOT",
        "M_ABS_CLICK:L": "OK:M_ABS_CLICK:L",
        "M_CLICK:L": "OK:M_CLICK:L",
    }.get(command, "")


def parse_step(value: str) -> int:
    try:
        step = int(value)
    except ValueError as exc:
        raise ValueError("Step 必須是正整數") from exc
    if not 1 <= step <= 10000:
        raise ValueError("Step 範圍必須是 1 至 10000")
    return step


def delta_command(direction: str, step: int) -> str:
    x, y = direction_delta(direction, step)
    return f"M_DELTA:{x},{y}"


def direction_delta(direction: str, step: int) -> tuple[int, int]:
    deltas = {"Left": (-step, 0), "Right": (step, 0), "Up": (0, -step), "Down": (0, step)}
    if direction not in deltas:
        raise ValueError(f"不支援的方向：{direction}")
    return deltas[direction]


def parse_delay_seconds(value: str) -> float:
    try:
        delay = float(value)
    except ValueError as exc:
        raise ValueError("輸入延遲必須是 0 至 120 的數字（可含小數）") from exc
    if not 0 <= delay <= KEYBOARD_DELAY_MAX_SECONDS:
        raise ValueError("輸入延遲必須是 0 至 120 秒")
    return delay


def keyboard_write_command(text: str) -> str:
    if not text:
        raise ValueError("請輸入要驗證的文字")
    if any(ord(char) < 0x20 or ord(char) > 0x7E for char in text):
        raise ValueError("韌體僅支援可列印 ASCII 文字（不可含中文、換行或特殊字元）")
    return "K_WRITE:" + text


def absolute_command(x: str | int, y: str | int) -> str:
    """Build M_ABS from operator input, validating the 16-bit HID range."""
    try:
        x_value, y_value = int(x), int(y)
    except (TypeError, ValueError) as exc:
        raise ValueError("絕對座標必須是整數") from exc
    if not (0 <= x_value <= ABSOLUTE_HID_MAX and 0 <= y_value <= ABSOLUTE_HID_MAX):
        raise ValueError(f"絕對座標範圍必須是 0 至 {ABSOLUTE_HID_MAX}")
    return f"M_ABS:{x_value},{y_value}"


def firmware_supports_absolute(info_line: str) -> bool | None:
    """Read the ABS= field of an INFO line; None when the firmware predates it."""
    if not info_line.startswith("INFO:"):
        return None
    for item in info_line[5:].split(";"):
        key, _, value = item.partition("=")
        if key.strip().upper() == "ABS":
            return value.strip() != "0"
    return None


def command_stage_message(command: str, acked: bool, outcome: str) -> str:
    """Describe how far a command travelled: sent → parsed (ACK) → executed (OK).

    ``outcome`` is "ok", "timeout", or the terminal ERR line. The wording is
    the on-site BT triage: no ACK means CDC/framing, ACK without OK means the
    HID layer, ERR:HID_NOT_READY means macOS never bound the HID interface.
    """
    if outcome == "ok":
        return f"{command}：已送出 → 韌體已解析（ACK）→ HID 已執行（OK）"
    if outcome == "timeout":
        if acked:
            return (f"{command}：已送出 → 韌體已解析（ACK）→ HID 執行逾時："
                    "macOS 可能未綁定 HID 介面，或韌體已卡死（請改測 GET_INFO 確認）")
        return f"{command}：已送出 → 未收到 ACK：USB CDC 傳輸或指令 framing 問題"
    if outcome == HID_NOT_READY_REPLY:
        return (f"{command}：已送出 → 韌體已解析（ACK）→ {outcome}："
                "macOS 未綁定 Arduino 的 HID 介面（BT／10.14 症狀）")
    if outcome == ABS_UNSUPPORTED_REPLY:
        return f"{command}：此韌體停用絕對指標（BT 相容模式），非故障"
    if outcome.startswith("ERR:"):
        return f"{command}：韌體回覆錯誤 {outcome}"
    return f"{command}：{outcome}"


def diagnostic_plan(include_absolute: bool) -> list[tuple[str, str]]:
    """Ordered (label, command) steps for the one-click diagnostic run.

    The trailing GET_INFO is deliberate: firmware that hangs inside a HID
    report busy-wait stops answering CDC entirely, so a final GET_INFO timeout
    after an earlier HID timeout is the "firmware stuck — replug USB and flash
    1.1.0" detector.
    """
    steps = [
        ("CDC 通道", "GET_INFO"),
        ("滑鼠歸位", "M_RESET"),
        ("相對位移（右 30）", "M_DELTA:30,0"),
        ("相對位移（左 30）", "M_DELTA:-30,0"),
        ("鍵盤輸入", "K_WRITE:" + DIAGNOSTIC_TEXT),
    ]
    if include_absolute:
        steps.append(("絕對定位（畫面中央）",
                      f"M_ABS:{ABSOLUTE_HID_MAX // 2},{ABSOLUTE_HID_MAX // 2}"))
    steps.append(("CDC 通道（結尾複測）", "GET_INFO"))
    return steps


def format_diagnostic_report(results: list[tuple[str, str, bool, str]], app_version: str) -> str:
    """Render collected (label, command, acked, outcome) records as a verdict.

    Layer verdicts: CDC (leading GET_INFO), HID execution (M_/K_ steps),
    absolute pointer capability, and the trailing GET_INFO hang check.
    """
    lines = [f"Atlas HID 校正診斷報告（App {app_version}）", "=" * 44]
    for label, command, acked, outcome in results:
        lines.append(f"[{label}] {command_stage_message(command, acked, outcome)}")
    lines.append("-" * 44)

    def outcome_of(index: int) -> str | None:
        return results[index][3] if 0 <= index < len(results) else None

    first_info_ok = outcome_of(0) == "ok"
    lines.append("USB CDC 通道：" + ("正常" if first_info_ok else "異常——請先檢查串口、線材與韌體"))

    hid_steps = [item for item in results[1:] if item[1].startswith(("M_", "K_"))
                 and not item[1].startswith("M_ABS")]
    if hid_steps:
        if all(item[3] == "ok" for item in hid_steps):
            lines.append("相對滑鼠／鍵盤 HID：正常")
        elif any(item[3] == HID_NOT_READY_REPLY for item in hid_steps):
            lines.append("相對滑鼠／鍵盤 HID：macOS 未綁定 HID 介面（ERR:HID_NOT_READY）——"
                         "BT／10.14 已知症狀，請依二分流程換燒無絕對指標韌體確認")
        elif any(item[3] == "timeout" and item[2] for item in hid_steps):
            lines.append("相對滑鼠／鍵盤 HID：ACK 後逾時——HID report 未被 macOS 接受")
        else:
            lines.append("相對滑鼠／鍵盤 HID：異常（詳見上方逐項結果）")

    abs_steps = [item for item in results if item[1].startswith("M_ABS")]
    if abs_steps:
        abs_outcome = abs_steps[-1][3]
        if abs_outcome == "ok":
            lines.append("絕對指標（report ID 3）：正常")
        elif abs_outcome == ABS_UNSUPPORTED_REPLY:
            lines.append("絕對指標（report ID 3）：BT 相容模式（韌體停用），非故障")
        else:
            lines.append("絕對指標（report ID 3）：異常——" + abs_outcome)

    trailing_info = outcome_of(len(results) - 1)
    if results and results[-1][1] == "GET_INFO" and len(results) > 1:
        if trailing_info == "ok":
            lines.append("結尾 GET_INFO：正常——韌體仍在運作，未卡死")
        else:
            lines.append("結尾 GET_INFO：逾時——韌體疑似卡死在 HID 報告等待中；"
                         "請拔插 USB 並確認已燒錄 1.1.0（含 HID readiness 防護）")
    return "\n".join(lines)


class HidCalibrationApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title(TITLE)
        root.geometry("780x820")
        root.minsize(700, 720)
        self.connection = None
        self.serial_lock = threading.Lock()
        self.connection_generation = 0
        self.stop = threading.Event()
        self.events: queue.Queue[tuple[str, str]] = queue.Queue()
        self.port = tk.StringVar()
        self.step = tk.StringVar(value="5")
        self.keyboard_text = tk.StringVar(value="HID keyboard test")
        self.keyboard_delay = tk.StringVar(value="3")
        self.typing_after_id: str | None = None
        self.pending_timeout_id: str | None = None
        self.pending_command: str | None = None
        self.pending_reply: str | None = None
        self.pending_success: Callable[[], None] | None = None
        self.pending_failure: Callable[[str], None] | None = None
        self.pending_acked = False
        self.last_pending_acked = False
        self.abs_supported: bool | None = None
        self.abs_x = tk.StringVar(value=str(ABSOLUTE_HID_MAX // 2))
        self.abs_y = tk.StringVar(value=str(ABSOLUTE_HID_MAX // 2))
        self.diag_steps: list[tuple[str, str]] = []
        self.diag_results: list[tuple[str, str, bool, str]] = []
        self.diag_index = 0
        self.firmware_query_attempt = 0
        self.firmware_retry_after_id: str | None = None
        self.tcp_diagnostic_logged = False
        self.firmware_verified = False
        self.firmware = tk.StringVar(value="韌體：尚未驗證")
        self.hid_controls: list[tk.Widget] = []
        self.status = tk.StringVar(value="請選擇 Arduino USB CDC 並連線")
        self.position_x = 0
        self.position_y = 0
        self.position = tk.StringVar()
        self.update_position()
        self.build()
        self.set_hid_controls_enabled(False)
        self.refresh_ports()
        root.bind("<KeyPress-Left>", lambda event: self.key_move("Left"))
        root.bind("<KeyPress-Right>", lambda event: self.key_move("Right"))
        root.bind("<KeyPress-Up>", lambda event: self.key_move("Up"))
        root.bind("<KeyPress-Down>", lambda event: self.key_move("Down"))
        root.after(100, self.process_events)
        root.protocol("WM_DELETE_WINDOW", self.close)

    def build(self) -> None:
        panel = ttk.Frame(self.root, padding=16); panel.pack(fill="both", expand=True)
        connection = ttk.LabelFrame(panel, text="Arduino USB CDC", padding=10); connection.pack(fill="x")
        connection.columnconfigure(1, weight=1)
        ttk.Label(connection, text="串口：").grid(row=0, column=0, sticky="w")
        self.port_menu = ttk.Combobox(connection, textvariable=self.port, state="readonly")
        self.port_menu.grid(row=0, column=1, sticky="ew", padx=(4, 8))
        ttk.Button(connection, text="重新掃描", command=self.refresh_ports).grid(row=0, column=2, padx=3)
        ttk.Button(connection, text="連線", command=self.connect).grid(row=0, column=3, padx=3)
        ttk.Button(connection, text="中斷", command=self.disconnect).grid(row=0, column=4, padx=(3, 0))
        ttk.Label(connection, textvariable=self.firmware).grid(row=1, column=0, columnspan=4, sticky="w", pady=(8, 0))
        self.query_button = ttk.Button(connection, text="重新查詢韌體", command=self.query_firmware)
        self.query_button.grid(row=1, column=4, padx=(3, 0), pady=(8, 0))

        coordinate = ttk.LabelFrame(panel, text="目前 Arduino 控制座標", padding=10); coordinate.pack(fill="x", pady=(12, 0))
        ttk.Label(coordinate, textvariable=self.position, font=("TkDefaultFont", 20, "bold")).pack(side="left")
        ttk.Label(coordinate, text="從 Home 的 (0, 0) 累積；右／下為正值。", foreground="#555").pack(side="left", padx=14)

        controls = ttk.LabelFrame(panel, text="相對距離測試", padding=12); controls.pack(fill="x", pady=12)
        ttk.Label(controls, text="Step 距離：").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(controls, from_=1, to=10000, textvariable=self.step, width=9).grid(row=0, column=1, sticky="w")
        ttk.Label(controls, text="按方向鍵或按下方向按鈕，每次移動指定的 HID steps。", foreground="#555").grid(row=0, column=2, padx=10, sticky="w")
        self.home_button = ttk.Button(controls, text="Home：回左上角", command=self.home)
        self.home_button.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(12, 8))
        arrows = ttk.Frame(controls); arrows.grid(row=2, column=0, columnspan=3)
        self.arrow_buttons = [
            ttk.Button(arrows, text="↑  上", command=lambda: self.move("Up"), width=12),
            ttk.Button(arrows, text="←  左", command=lambda: self.move("Left"), width=12),
            ttk.Button(arrows, text="↓  下", command=lambda: self.move("Down"), width=12),
            ttk.Button(arrows, text="→  右", command=lambda: self.move("Right"), width=12),
        ]
        self.arrow_buttons[0].grid(row=0, column=1, padx=3, pady=3)
        self.arrow_buttons[1].grid(row=1, column=0, padx=3, pady=3)
        self.arrow_buttons[2].grid(row=1, column=1, padx=3, pady=3)
        self.arrow_buttons[3].grid(row=1, column=2, padx=3, pady=3)
        self.screenshot_button = ttk.Button(
            controls,
            text="一鍵截圖（Arduino ⌘⇧3）",
            command=self.take_screenshot,
        )
        self.screenshot_button.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(10, 0))

        keyboard = ttk.LabelFrame(panel, text="Arduino 鍵盤輸入驗證", padding=12)
        keyboard.pack(fill="x", pady=(0, 12))
        keyboard.columnconfigure(1, weight=1)
        ttk.Label(keyboard, text="測試文字：").grid(row=0, column=0, sticky="w")
        ttk.Entry(keyboard, textvariable=self.keyboard_text).grid(row=0, column=1, columnspan=3, sticky="ew", padx=(4, 8))
        ttk.Label(keyboard, text="延遲（秒）：").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Spinbox(keyboard, from_=0, to=KEYBOARD_DELAY_MAX_SECONDS, increment=.5,
                    textvariable=self.keyboard_delay, width=9).grid(row=1, column=1, sticky="w", padx=(4, 8), pady=(8, 0))
        self.keyboard_button = ttk.Button(keyboard, text="開始延遲輸入", command=self.schedule_keyboard_write)
        self.keyboard_button.grid(row=1, column=2, sticky="ew", pady=(8, 0))
        ttk.Label(keyboard, text="開始後請將滑鼠點到目標輸入框；文字不會自動送出 Enter。",
                  foreground="#555").grid(row=2, column=0, columnspan=4, sticky="w", pady=(8, 0))

        absolute = ttk.LabelFrame(panel, text="絕對指標測試 (M_ABS)", padding=12)
        absolute.pack(fill="x", pady=(0, 12))
        ttk.Label(absolute, text=f"X（0–{ABSOLUTE_HID_MAX}）：").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(absolute, from_=0, to=ABSOLUTE_HID_MAX, textvariable=self.abs_x,
                    width=9).grid(row=0, column=1, sticky="w", padx=(4, 12))
        ttk.Label(absolute, text=f"Y（0–{ABSOLUTE_HID_MAX}）：").grid(row=0, column=2, sticky="w")
        ttk.Spinbox(absolute, from_=0, to=ABSOLUTE_HID_MAX, textvariable=self.abs_y,
                    width=9).grid(row=0, column=3, sticky="w", padx=(4, 12))
        self.abs_move_button = ttk.Button(absolute, text="絕對定位 M_ABS", command=self.send_absolute_move)
        self.abs_move_button.grid(row=0, column=4, padx=(0, 6))
        self.abs_click_button = ttk.Button(absolute, text="絕對點擊 M_ABS_CLICK:L",
                                           command=self.send_absolute_click)
        self.abs_click_button.grid(row=0, column=5)
        self.abs_note = ttk.Label(
            absolute, text="report ID 3 絕對指標；(16384, 16384) 約為畫面中央。", foreground="#555")
        self.abs_note.grid(row=1, column=0, columnspan=6, sticky="w", pady=(8, 0))

        diagnostic = ttk.Frame(panel)
        diagnostic.pack(fill="x", pady=(0, 8))
        self.diagnostic_button = ttk.Button(diagnostic, text="一鍵診斷報告", command=self.run_diagnostics)
        self.diagnostic_button.pack(side="left")
        ttk.Label(diagnostic,
                  text="依序測 CDC → 相對滑鼠 → 鍵盤 → 絕對指標，並複測 CDC 判斷韌體是否卡死。",
                  foreground="#555").pack(side="left", padx=10)

        ttk.Label(panel, textvariable=self.status).pack(anchor="w")
        ttk.Label(panel, text="通訊紀錄：").pack(anchor="w", pady=(8, 0))
        self.output = tk.Text(panel, height=8, state="disabled", wrap="word")
        self.output.pack(fill="both", expand=True)
        self.abs_buttons = [self.abs_move_button, self.abs_click_button]
        self.hid_controls = [self.home_button, self.screenshot_button, self.keyboard_button,
                             self.diagnostic_button, *self.abs_buttons, *self.arrow_buttons]

    def set_hid_controls_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for control in self.hid_controls:
            control.configure(state=state)
        if enabled and self.abs_supported is False:
            for control in self.abs_buttons:
                control.configure(state="disabled")

    def set_absolute_supported(self, supported: bool) -> None:
        """Reflect the firmware's absolute-pointer capability in the UI."""
        if self.abs_supported == supported:
            return
        self.abs_supported = supported
        if supported:
            self.abs_note.configure(
                text="report ID 3 絕對指標；(16384, 16384) 約為畫面中央。")
            if self.firmware_verified:
                for control in self.abs_buttons:
                    control.configure(state="normal")
        else:
            self.abs_note.configure(text="此韌體停用絕對指標（BT 相容模式）。")
            for control in self.abs_buttons:
                control.configure(state="disabled")
            self.append("韌體停用絕對指標（BT 相容模式）；已停用 M_ABS 測試按鈕。")

    def refresh_ports(self) -> None:
        ports = [item.device for item in list_ports.comports()] if list_ports else []
        self.port_menu["values"] = ports
        if ports and self.port.get() not in ports:
            self.port.set(ports[0])

    def connect(self) -> None:
        if serial is None:
            messagebox.showerror(TITLE, "缺少 pyserial；請執行 python3 -m pip install -r requirements.txt"); return
        if not self.port.get():
            messagebox.showerror(TITLE, "請先選擇 Arduino 串口"); return
        self.disconnect()
        try:
            self.connection = serial.Serial(self.port.get(), BAUD_RATE, timeout=.2)
        except Exception as exc:
            self.connection = None; messagebox.showerror(TITLE, f"無法連線：{exc}"); return
        self.stop.clear()
        self.connection_generation += 1
        generation = self.connection_generation
        connection = self.connection
        threading.Thread(target=self.receive, args=(connection, generation), daemon=True).start()
        self.firmware_verified = False
        self.set_hid_controls_enabled(False)
        self.firmware.set("韌體：查詢中…")
        self.status.set("已連線；正在驗證 Arduino 韌體與控制協定。")
        self.append("已連線：" + self.port.get())
        self.start_firmware_verification(FIRMWARE_QUERY_DELAY_MS)

    def disconnect(self) -> None:
        self.cancel_pending_keyboard_write()
        self.cancel_firmware_retry()
        self.stop.set()
        self.connection_generation += 1
        if self.connection:
            self.connection.close()
        self.connection = None
        self.clear_pending()
        self.firmware_verified = False
        self.set_hid_controls_enabled(False)
        self.firmware.set("韌體：尚未驗證")
        self.status.set("未連線")

    def clear_received_events(self) -> None:
        """Discard replies that belonged to a prior connection or command."""
        while True:
            try:
                self.events.get_nowait()
            except queue.Empty:
                return

    def synchronize_cdc_channel(self, *, hard_reset: bool = False) -> None:
        """Discard stale CDC bytes without unnecessarily resetting a VM USB driver.

        A full pyserial reset is reserved for a new connection or a firmware
        discovery retry. Repeating it immediately before every HID command can
        drop the first packet on older macOS virtual USB implementations.
        """
        self.clear_received_events()
        if not self.connection:
            return
        try:
            with self.serial_lock:
                if hard_reset:
                    self.connection.reset_input_buffer()
                    self.connection.reset_output_buffer()
                else:
                    # The receive thread is the sole reader.  Clearing the
                    # app event queue above discards stale replies without
                    # racing it for USB bytes on older macOS VMs.
                    self.connection.flush()
        except Exception as exc:
            self.append("WARN: 無法清空 USB CDC buffer：" + str(exc))

    def cancel_firmware_retry(self) -> None:
        if self.firmware_retry_after_id is not None:
            self.root.after_cancel(self.firmware_retry_after_id)
        self.firmware_retry_after_id = None

    def start_firmware_verification(self, initial_delay_ms: int = 200) -> None:
        """Synchronize the session and verify GET_INFO with bounded retries."""
        if not self.connection:
            return
        self.cancel_firmware_retry()
        self.clear_pending()
        self.synchronize_cdc_channel(hard_reset=True)
        self.firmware_query_attempt = 0
        self.firmware_verified = False
        self.set_hid_controls_enabled(False)
        self.firmware.set("韌體：查詢中…")
        self.status.set("USB CDC 已同步；正在驗證 Arduino 韌體…")
        self.firmware_retry_after_id = self.root.after(initial_delay_ms, self.send_firmware_query_attempt)

    def send_firmware_query_attempt(self) -> None:
        self.firmware_retry_after_id = None
        if not self.connection or self.pending_command is not None:
            return
        self.synchronize_cdc_channel()
        self.firmware_query_attempt += 1
        self.append(f"韌體驗證第 {self.firmware_query_attempt}/{FIRMWARE_QUERY_MAX_ATTEMPTS} 次：GET_INFO")
        self.send_checked("GET_INFO", require_firmware=False, timeout_ms=FIRMWARE_QUERY_TIMEOUT_MS,
                          synchronize=False)

    def retry_firmware_query(self, reason: str) -> None:
        if not self.connection:
            return
        if self.firmware_query_attempt >= FIRMWARE_QUERY_MAX_ATTEMPTS:
            self.reject_firmware(
                f"韌體驗證失敗：已嘗試 {FIRMWARE_QUERY_MAX_ATTEMPTS} 次仍未取得有效 INFO（{reason}）。")
            return
        delay = FIRMWARE_QUERY_RETRY_DELAYS_MS[self.firmware_query_attempt - 1]
        self.status.set(f"韌體驗證未完成（{reason}）；{delay / 1000:g} 秒後自動重試。")
        self.append(f"WARN: GET_INFO 未完成：{reason}；將自動重試")
        self.firmware_retry_after_id = self.root.after(delay, self.send_firmware_query_attempt)

    def receive(self, connection, generation: int) -> None:
        while (not self.stop.is_set() and generation == self.connection_generation
               and connection is self.connection):
            try:
                raw_line = connection.readline().decode("utf-8", errors="replace")
                # Normalise only transport framing. Do not use str.strip(),
                # because a transparent TCP payload may legitimately contain
                # ordinary leading/trailing spaces.
                line = normalize_cdc_line(raw_line)
                if line: self.events.put(("rx", line))
            except Exception as exc:
                if not self.stop.is_set() and generation == self.connection_generation:
                    self.events.put(("error", str(exc)))
                return

    def send_checked(self, command: str, on_success: Callable[[], None] | None = None,
                     *, on_failure: Callable[[str], None] | None = None,
                     require_firmware: bool = True, timeout_ms: int | None = None,
                     synchronize: bool = True) -> bool:
        if not self.connection:
            messagebox.showwarning(TITLE, "請先連線 Arduino"); return False
        if require_firmware and not self.firmware_verified:
            messagebox.showwarning(TITLE, "Arduino 韌體尚未通過驗證，已阻止 HID 指令。")
            return False
        if self.pending_command is not None:
            messagebox.showwarning(TITLE, f"尚在等待 {self.pending_command} 回覆，請稍候。")
            return False
        expected = "INFO:" if command == "GET_INFO" else expected_success_reply(command)
        if not expected:
            raise ValueError(f"未定義成功回覆的指令：{command}")
        try:
            if synchronize:
                self.synchronize_cdc_channel()
            # UNO R4 on older macOS/VM USB paths can retain a trailing CR
            # after a command.  USB CDC controls are therefore LF-delimited.
            with self.serial_lock:
                self.connection.write((command.rstrip("\r\n") + USB_CDC_CONTROL_TERMINATOR).encode("utf-8"))
                self.connection.flush()
            self.append("TX: " + command)
            self.pending_command = command
            self.pending_reply = expected
            self.pending_success = on_success
            self.pending_failure = on_failure
            self.pending_acked = False
            self.pending_timeout_id = self.root.after(timeout_ms or COMMAND_TIMEOUT_MS, self.pending_timed_out)
            return True
        except Exception as exc:
            self.append("ERR: 傳送失敗：" + str(exc))
            return False

    def clear_pending(self) -> None:
        if self.pending_timeout_id is not None:
            self.root.after_cancel(self.pending_timeout_id)
        self.pending_timeout_id = None
        self.pending_command = None
        self.pending_reply = None
        self.pending_success = None
        self.pending_failure = None
        self.last_pending_acked = self.pending_acked
        self.pending_acked = False

    def pending_timed_out(self) -> None:
        command = self.pending_command
        acked = self.pending_acked
        failure = self.pending_failure
        self.pending_timeout_id = None
        self.clear_pending()
        if failure is not None:
            message = command_stage_message(command or "", acked, "timeout")
            self.append("逾時：" + message)
            self.status.set(message)
            failure("timeout")
        elif command == "GET_INFO":
            self.retry_firmware_query("等待 INFO 逾時")
        elif command:
            message = command_stage_message(command, acked, "timeout")
            self.append("逾時：" + message)
            self.status.set(message)

    def query_firmware(self) -> None:
        if not self.connection:
            messagebox.showwarning(TITLE, "請先連線 Arduino")
            return
        if self.pending_command is None:
            self.start_firmware_verification()

    def reject_firmware(self, reason: str) -> None:
        self.firmware_verified = False
        self.set_hid_controls_enabled(False)
        self.firmware.set("韌體：不相容／無法識別")
        self.status.set(reason)
        self.append("韌體驗證失敗：" + reason)

    def handle_received_line(self, line: str) -> None:
        if is_nonfatal_cdc_diagnostic(line):
            if not self.tcp_diagnostic_logged:
                self.append("WARN: Arduino TCP 尚未連線；不影響 USB HID 控制。")
                self.tcp_diagnostic_logged = True
            if self.pending_command is not None:
                self.status.set(
                    f"指令 {self.pending_command} 已送出；忽略未連線 TCP 診斷，等待 Arduino OK 回覆。")
            return
        self.append("RX: " + line)
        # The firmware keeps the USB CDC channel transparent for normal TCP
        # payloads.  A station without an upstream TCP client can therefore
        # emit this diagnostic independently of the HID command that was just
        # accepted.  It must not consume a pending M_/K_/SCREENSHOT command:
        # the following OK reply is the authoritative HID completion signal.
        if line.startswith("INFO:"):
            # A diagnostic-sequencer GET_INFO carries callbacks; capture them
            # before clear_pending so the run can continue after verification.
            pending_was_get_info = self.pending_command == "GET_INFO"
            success = self.pending_success if pending_was_get_info else None
            failure = self.pending_failure if pending_was_get_info else None
            identity = parse_firmware_info(line)
            if identity is None:
                self.clear_pending()
                if failure is not None:
                    failure("INFO 格式不正確")
                else:
                    self.retry_firmware_query("INFO 格式不正確")
                return
            product, version, protocol, board = identity
            self.clear_pending()
            abs_support = firmware_supports_absolute(line)
            if abs_support is not None:
                self.set_absolute_supported(abs_support)
            if product != EXPECTED_FIRMWARE_PRODUCT or protocol != EXPECTED_PROTOCOL_VERSION:
                self.reject_firmware(
                    f"韌體不相容：PRODUCT={product}，PROTO={protocol}；需要 "
                    f"{EXPECTED_FIRMWARE_PRODUCT}／PROTO={EXPECTED_PROTOCOL_VERSION}。")
                if failure is not None:
                    failure("韌體不相容")
                return
            self.firmware_verified = True
            self.cancel_firmware_retry()
            self.set_hid_controls_enabled(True)
            self.firmware.set(f"韌體：{version}｜協定：{protocol}｜板子：{board}")
            self.status.set("韌體驗證通過；請先按 Home，再測試滑鼠、截圖與鍵盤。")
            if success is not None:
                success()
            return
        if self.pending_command is None:
            return
        if line.startswith("ERR:"):
            command = self.pending_command
            acked = self.pending_acked
            failure = self.pending_failure
            self.clear_pending()
            if line == ABS_UNSUPPORTED_REPLY:
                self.set_absolute_supported(False)
            if failure is not None:
                self.status.set(command_stage_message(command or "", acked, line))
                failure(line)
            elif command == "GET_INFO":
                self.retry_firmware_query(line)
            else:
                self.status.set(command_stage_message(command or "", acked, line))
            return
        if is_hid_progress_reply(self.pending_command, line):
            self.pending_acked = True
            self.status.set(f"Arduino 已接收 {self.pending_command}，正在執行 HID…")
            return
        expected = self.pending_reply or ""
        if line == expected:
            callback = self.pending_success
            self.clear_pending()
            if callback is not None:
                callback()

    def home(self) -> None:
        self.send_checked("M_RESET", self.home_succeeded)

    def home_succeeded(self) -> None:
        self.position_x = self.position_y = 0
        self.update_position()
        self.status.set("Home 完成：已收到 OK:M_RESET。")

    def take_screenshot(self) -> None:
        if self.send_checked(SCREENSHOT_COMMAND, self.screenshot_succeeded):
            self.status.set("已送出截圖指令；等待 ACK／OK。")

    def screenshot_succeeded(self) -> None:
        self.status.set("已收到 OK:SCREENSHOT；請等待 macOS 完成儲存截圖。")

    def cancel_pending_keyboard_write(self) -> None:
        if self.typing_after_id is not None:
            self.root.after_cancel(self.typing_after_id)
            self.typing_after_id = None

    def schedule_keyboard_write(self) -> None:
        try:
            command = keyboard_write_command(self.keyboard_text.get())
            delay = parse_delay_seconds(self.keyboard_delay.get())
        except ValueError as exc:
            messagebox.showerror(TITLE, str(exc)); return
        if not self.connection:
            messagebox.showwarning(TITLE, "請先連線 Arduino"); return
        if self.typing_after_id is not None:
            self.cancel_pending_keyboard_write()
            self.append("已取消前一個延遲輸入工作。")
        milliseconds = round(delay * 1000)
        self.typing_after_id = self.root.after(milliseconds, lambda: self.send_keyboard_write(command))
        self.status.set(f"將於 {delay:g} 秒後透過 Arduino 輸入文字；請現在點選目標輸入框。")
        self.append(f"文字輸入倒數開始：{delay:g} 秒後執行 K_WRITE。")

    def send_keyboard_write(self, command: str) -> None:
        self.typing_after_id = None
        if self.send_checked(command, self.keyboard_write_succeeded):
            self.status.set("文字輸入指令已送出；等待 OK:K_WRITE。")

    def keyboard_write_succeeded(self) -> None:
        self.status.set("文字輸入完成：已收到 OK:K_WRITE。")

    def send_absolute_move(self) -> None:
        try:
            command = absolute_command(self.abs_x.get(), self.abs_y.get())
        except ValueError as exc:
            messagebox.showerror(TITLE, str(exc)); return
        if self.send_checked(command, lambda: self.status.set(
                "絕對定位完成：已收到 OK:M_ABS；游標應停在指定座標。")):
            self.status.set("絕對定位指令已送出；等待 OK:M_ABS。")

    def send_absolute_click(self) -> None:
        if self.send_checked("M_ABS_CLICK:L", lambda: self.status.set(
                "絕對點擊完成：已收到 OK:M_ABS_CLICK:L。")):
            self.status.set("絕對點擊指令已送出；等待 OK:M_ABS_CLICK:L。")

    def run_diagnostics(self) -> None:
        """Walk diagnostic_plan() through the pending machinery, one step at a time."""
        if not self.connection:
            messagebox.showwarning(TITLE, "請先連線 Arduino"); return
        if self.pending_command is not None:
            messagebox.showwarning(TITLE, f"尚在等待 {self.pending_command} 回覆，請稍候。")
            return
        self.diag_steps = diagnostic_plan(self.abs_supported is not False)
        self.diag_results = []
        self.diag_index = 0
        self.append(f"一鍵診斷開始（共 {len(self.diag_steps)} 步）。"
                    "鍵盤步驟會在目前聚焦處輸入 " + DIAGNOSTIC_TEXT + "。")
        self.status.set("診斷執行中…")
        self.run_next_diagnostic_step()

    def run_next_diagnostic_step(self) -> None:
        if self.diag_index >= len(self.diag_steps):
            self.finish_diagnostics()
            return
        label, command = self.diag_steps[self.diag_index]
        sent = self.send_checked(command,
                                 on_success=lambda: self.diagnostic_step_done("ok"),
                                 on_failure=self.diagnostic_step_done)
        if not sent:
            self.diag_results.append((label, command, False, "傳送失敗"))
            self.finish_diagnostics()

    def diagnostic_step_done(self, outcome: str) -> None:
        label, command = self.diag_steps[self.diag_index]
        acked = True if outcome == "ok" else self.last_pending_acked
        self.diag_results.append((label, command, acked, outcome))
        self.diag_index += 1
        if outcome == "timeout" and command.startswith(("M_", "K_")):
            # The firmware may already be hung inside a HID report busy-wait;
            # every further HID step would burn a full timeout. Jump straight
            # to the trailing GET_INFO, which is the hang detector.
            while self.diag_index < len(self.diag_steps) - 1:
                skip_label, skip_command = self.diag_steps[self.diag_index]
                self.diag_results.append((skip_label, skip_command, False, "略過（前一步 HID 逾時）"))
                self.diag_index += 1
        self.root.after(150, self.run_next_diagnostic_step)

    def finish_diagnostics(self) -> None:
        report = format_diagnostic_report(self.diag_results, APP_VERSION)
        self.append(report)
        self.status.set("診斷完成；報告視窗已開啟。")
        window = tk.Toplevel(self.root)
        window.title(TITLE + "｜診斷報告")
        window.geometry("640x480")
        text = tk.Text(window, wrap="word")
        text.insert("1.0", report)
        text.configure(state="disabled")
        text.pack(fill="both", expand=True, padx=12, pady=(12, 6))

        def copy_report() -> None:
            self.root.clipboard_clear()
            self.root.clipboard_append(report)
            self.status.set("診斷報告已複製到剪貼簿。")

        ttk.Button(window, text="複製報告", command=copy_report).pack(pady=(0, 12))

    def move(self, direction: str) -> None:
        try:
            step = parse_step(self.step.get())
            command = delta_command(direction, step)
            delta_x, delta_y = direction_delta(direction, step)
        except ValueError as exc:
            messagebox.showerror(TITLE, str(exc)); return
        self.send_checked(command, lambda: self.move_succeeded(delta_x, delta_y))

    def move_succeeded(self, delta_x: int, delta_y: int) -> None:
        self.position_x += delta_x
        self.position_y += delta_y
        self.update_position()
        self.status.set(f"移動完成：已收到 OK:M_DELTA；目前座標 {self.position.get()}。")

    def key_move(self, direction: str) -> str:
        self.move(direction)
        return "break"

    def update_position(self) -> None:
        self.position.set(f"({self.position_x}, {self.position_y})")

    def append(self, message: str) -> None:
        self.output.configure(state="normal")
        self.output.insert("end", message + "\n")
        self.output.see("end")
        self.output.configure(state="disabled")

    def process_events(self) -> None:
        try:
            while True:
                event_type, message = self.events.get_nowait()
                if event_type == "rx":
                    self.handle_received_line(message)
                else:
                    self.append("ERR: " + message)
        except queue.Empty:
            pass
        self.root.after(100, self.process_events)

    def close(self) -> None:
        self.disconnect()
        self.root.destroy()


def main() -> int:
    root = tk.Tk()
    HidCalibrationApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
