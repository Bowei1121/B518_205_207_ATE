#!/usr/bin/env python3
"""Standalone Arduino HID distance calibration tool for B518 ATE."""
from __future__ import annotations

import queue
import threading
import tkinter as tk
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
KEYBOARD_DELAY_MAX_SECONDS = 120.0


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
        self.stop = threading.Event()
        self.events: queue.Queue[str] = queue.Queue()
        self.port = tk.StringVar()
        self.step = tk.StringVar(value="5")
        self.keyboard_text = tk.StringVar(value="HID keyboard test")
        self.keyboard_delay = tk.StringVar(value="3")
        self.typing_after_id: str | None = None
        self.status = tk.StringVar(value="請選擇 Arduino USB CDC 並連線")
        self.position_x = 0
        self.position_y = 0
        self.position = tk.StringVar()
        self.update_position()
        self.build()
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

        coordinate = ttk.LabelFrame(panel, text="目前 Arduino 控制座標", padding=10); coordinate.pack(fill="x", pady=(12, 0))
        ttk.Label(coordinate, textvariable=self.position, font=("TkDefaultFont", 20, "bold")).pack(side="left")
        ttk.Label(coordinate, text="從 Home 的 (0, 0) 累積；右／下為正值。", foreground="#555").pack(side="left", padx=14)

        controls = ttk.LabelFrame(panel, text="相對距離測試", padding=12); controls.pack(fill="x", pady=12)
        ttk.Label(controls, text="Step 距離：").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(controls, from_=1, to=10000, textvariable=self.step, width=9).grid(row=0, column=1, sticky="w")
        ttk.Label(controls, text="按方向鍵或按下方向按鈕，每次移動指定的 HID steps。", foreground="#555").grid(row=0, column=2, padx=10, sticky="w")
        ttk.Button(controls, text="Home：回左上角", command=self.home).grid(row=1, column=0, columnspan=3, sticky="ew", pady=(12, 8))
        arrows = ttk.Frame(controls); arrows.grid(row=2, column=0, columnspan=3)
        ttk.Button(arrows, text="↑  上", command=lambda: self.move("Up"), width=12).grid(row=0, column=1, padx=3, pady=3)
        ttk.Button(arrows, text="←  左", command=lambda: self.move("Left"), width=12).grid(row=1, column=0, padx=3, pady=3)
        ttk.Button(arrows, text="↓  下", command=lambda: self.move("Down"), width=12).grid(row=1, column=1, padx=3, pady=3)
        ttk.Button(arrows, text="→  右", command=lambda: self.move("Right"), width=12).grid(row=1, column=2, padx=3, pady=3)
        ttk.Button(
            controls,
            text="一鍵截圖（Arduino ⌘⇧3）",
            command=self.take_screenshot,
        ).grid(row=3, column=0, columnspan=3, sticky="ew", pady=(10, 0))

        keyboard = ttk.LabelFrame(panel, text="Arduino 鍵盤輸入驗證", padding=12)
        keyboard.pack(fill="x", pady=(0, 12))
        keyboard.columnconfigure(1, weight=1)
        ttk.Label(keyboard, text="測試文字：").grid(row=0, column=0, sticky="w")
        ttk.Entry(keyboard, textvariable=self.keyboard_text).grid(row=0, column=1, columnspan=3, sticky="ew", padx=(4, 8))
        ttk.Label(keyboard, text="延遲（秒）：").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Spinbox(keyboard, from_=0, to=KEYBOARD_DELAY_MAX_SECONDS, increment=.5,
                    textvariable=self.keyboard_delay, width=9).grid(row=1, column=1, sticky="w", padx=(4, 8), pady=(8, 0))
        ttk.Button(keyboard, text="開始延遲輸入", command=self.schedule_keyboard_write).grid(
            row=1, column=2, sticky="ew", pady=(8, 0))
        ttk.Label(keyboard, text="開始後請將滑鼠點到目標輸入框；文字不會自動送出 Enter。",
                  foreground="#555").grid(row=2, column=0, columnspan=4, sticky="w", pady=(8, 0))

        ttk.Label(panel, textvariable=self.status).pack(anchor="w")
        ttk.Label(panel, text="通訊紀錄：").pack(anchor="w", pady=(8, 0))
        self.output = tk.Text(panel, height=8, state="disabled", wrap="word")
        self.output.pack(fill="both", expand=True)

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
        threading.Thread(target=self.receive, daemon=True).start()
        self.status.set("已連線；先按 Home，然後用方向鍵測試距離。")
        self.append("已連線：" + self.port.get())

    def disconnect(self) -> None:
        self.cancel_pending_keyboard_write()
        self.stop.set()
        if self.connection:
            self.connection.close()
        self.connection = None
        self.status.set("未連線")

    def receive(self) -> None:
        while not self.stop.is_set() and self.connection:
            try:
                line = self.connection.readline().decode("utf-8", errors="replace").strip()
                if line: self.events.put("RX: " + line)
            except Exception as exc:
                if not self.stop.is_set(): self.events.put("ERR: " + str(exc))
                return

    def send(self, command: str) -> bool:
        if not self.connection:
            messagebox.showwarning(TITLE, "請先連線 Arduino"); return False
        try:
            self.connection.write((command + "\r\n").encode("utf-8"))
            self.connection.flush()
            self.append("TX: " + command)
            return True
        except Exception as exc:
            self.append("ERR: 傳送失敗：" + str(exc))
            return False

    def home(self) -> None:
        if self.send("M_RESET"):
            self.position_x = self.position_y = 0
            self.update_position()

    def take_screenshot(self) -> None:
        if self.send(SCREENSHOT_COMMAND):
            self.status.set("已送出截圖指令；請等待 macOS 將螢幕截圖儲存至預設路徑。")

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
        if self.send(command):
            self.status.set("文字輸入指令已送出；請在通訊紀錄確認 RX: OK:K_WRITE。")

    def move(self, direction: str) -> None:
        try:
            step = parse_step(self.step.get())
            command = delta_command(direction, step)
            delta_x, delta_y = direction_delta(direction, step)
        except ValueError as exc:
            messagebox.showerror(TITLE, str(exc)); return
        if self.send(command):
            self.position_x += delta_x
            self.position_y += delta_y
            self.update_position()

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
            while True: self.append(self.events.get_nowait())
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
