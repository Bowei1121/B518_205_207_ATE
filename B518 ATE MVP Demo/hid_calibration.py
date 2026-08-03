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


TITLE = "Atlas HID 座標校正 B518"
BAUD_RATE = 115200
SCREENSHOT_COMMAND = "SCREENSHOT"
USB_CDC_CONTROL_TERMINATOR = "\n"
KEYBOARD_DELAY_MAX_SECONDS = 120.0
EXPECTED_FIRMWARE_PRODUCT = "B518_ARDUINO_MVP"
EXPECTED_PROTOCOL_VERSION = 1
FIRMWARE_QUERY_DELAY_MS = 800
COMMAND_TIMEOUT_MS = 3000

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
    return {
        "M_RESET": "OK:M_RESET",
        "SCREENSHOT": "OK:SCREENSHOT",
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


class HidCalibrationApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title(TITLE)
        root.geometry("760x650")
        root.minsize(680, 600)
        self.connection = None
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

        ttk.Label(panel, textvariable=self.status).pack(anchor="w")
        ttk.Label(panel, text="通訊紀錄：").pack(anchor="w", pady=(8, 0))
        self.output = tk.Text(panel, height=8, state="disabled", wrap="word")
        self.output.pack(fill="both", expand=True)
        self.hid_controls = [self.home_button, self.screenshot_button, self.keyboard_button, *self.arrow_buttons]

    def set_hid_controls_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for control in self.hid_controls:
            control.configure(state=state)

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
            self.connection.reset_input_buffer()
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
        self.root.after(FIRMWARE_QUERY_DELAY_MS, self.query_firmware)

    def disconnect(self) -> None:
        self.cancel_pending_keyboard_write()
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

    def receive(self, connection, generation: int) -> None:
        while (not self.stop.is_set() and generation == self.connection_generation
               and connection is self.connection):
            try:
                line = connection.readline().decode("utf-8", errors="replace").strip()
                if line: self.events.put(("rx", line))
            except Exception as exc:
                if not self.stop.is_set() and generation == self.connection_generation:
                    self.events.put(("error", str(exc)))
                return

    def send_checked(self, command: str, on_success: Callable[[], None] | None = None,
                     *, require_firmware: bool = True) -> bool:
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
            # UNO R4 on older macOS/VM USB paths can retain a trailing CR
            # after a command.  USB CDC controls are therefore LF-delimited.
            self.connection.write((command.rstrip("\r\n") + USB_CDC_CONTROL_TERMINATOR).encode("utf-8"))
            self.connection.flush()
            self.append("TX: " + command)
            self.pending_command = command
            self.pending_reply = expected
            self.pending_success = on_success
            self.pending_timeout_id = self.root.after(COMMAND_TIMEOUT_MS, self.pending_timed_out)
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

    def pending_timed_out(self) -> None:
        command = self.pending_command
        self.pending_timeout_id = None
        self.pending_command = None
        self.pending_reply = None
        self.pending_success = None
        if command == "GET_INFO":
            self.reject_firmware("查詢逾時：Arduino 未回覆 INFO，可能為舊韌體或燒錄錯誤。")
        elif command:
            self.status.set(f"指令 {command} 逾時；未收到執行成功回覆。")

    def query_firmware(self) -> None:
        if not self.connection:
            messagebox.showwarning(TITLE, "請先連線 Arduino")
            return
        if self.pending_command is not None:
            return
        self.firmware_verified = False
        self.set_hid_controls_enabled(False)
        self.firmware.set("韌體：查詢中…")
        self.send_checked("GET_INFO", require_firmware=False)

    def reject_firmware(self, reason: str) -> None:
        self.firmware_verified = False
        self.set_hid_controls_enabled(False)
        self.firmware.set("韌體：不相容／無法識別")
        self.status.set(reason)
        self.append("韌體驗證失敗：" + reason)

    def handle_received_line(self, line: str) -> None:
        self.append("RX: " + line)
        if line.startswith("INFO:"):
            identity = parse_firmware_info(line)
            if identity is None:
                self.clear_pending()
                self.reject_firmware("INFO 格式不正確，請確認燒錄來源。")
                return
            product, version, protocol, board = identity
            self.clear_pending()
            if product != EXPECTED_FIRMWARE_PRODUCT or protocol != EXPECTED_PROTOCOL_VERSION:
                self.reject_firmware(
                    f"韌體不相容：PRODUCT={product}，PROTO={protocol}；需要 "
                    f"{EXPECTED_FIRMWARE_PRODUCT}／PROTO={EXPECTED_PROTOCOL_VERSION}。")
                return
            self.firmware_verified = True
            self.set_hid_controls_enabled(True)
            self.firmware.set(f"韌體：{version}｜協定：{protocol}｜板子：{board}")
            self.status.set("韌體驗證通過；請先按 Home，再測試滑鼠、截圖與鍵盤。")
            return
        if self.pending_command is None:
            return
        if line.startswith("ERR:"):
            command = self.pending_command
            self.clear_pending()
            if command == "GET_INFO":
                self.reject_firmware(
                    f"Arduino 回覆 {line}；這通常表示目前不是支援 GET_INFO 的正式韌體。")
            else:
                self.status.set(f"指令 {command} 失敗：{line}；畫面座標未變更。")
            return
        if self.pending_command == "SCREENSHOT" and line == "ACK:SCREENSHOT":
            self.status.set("Arduino 已接收截圖指令，正在執行 HID 組合鍵…")
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
