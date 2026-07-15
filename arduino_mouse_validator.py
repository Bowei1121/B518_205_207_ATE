#!/usr/bin/env python3
"""MVP validator for an Arduino serial-controlled USB mouse."""

from __future__ import annotations

import argparse
import math
import os
import select
import statistics
import sys
import time
import tkinter as tk
from tkinter import ttk
from dataclasses import dataclass
from typing import Callable, List, Optional, Protocol, Sequence, Tuple

try:
    import serial
    from serial.tools import list_ports
except ImportError:  # Keep the module importable for unit tests.
    serial = None
    list_ports = None

try:
    import msvcrt
except ImportError:
    msvcrt = None

try:
    import termios
    import tty
except ImportError:
    termios = None
    tty = None


START_ACK = "ACK: Mouse movement started."
STOP_ACK = "ACK: Mouse movement stopped."


class ValidationError(RuntimeError):
    """A user-facing validation failure."""


class SerialConnection(Protocol):
    timeout: float

    def write(self, data: bytes) -> int: ...

    def flush(self) -> None: ...

    def readline(self) -> bytes: ...

    def reset_input_buffer(self) -> None: ...

    def close(self) -> None: ...


class PointerReader(Protocol):
    def position(self) -> Tuple[int, int]: ...

    def close(self) -> None: ...


class KeyReader(Protocol):
    def read_key(self) -> Optional[str]: ...

    def close(self) -> None: ...


class TkPointerReader:
    """Read the system pointer without requiring an extra mouse package."""

    def __init__(self) -> None:
        self._root = tk.Tk()
        self._root.withdraw()
        self._root.update_idletasks()

    def position(self) -> Tuple[int, int]:
        self._root.update()
        return self._root.winfo_pointerxy()

    def close(self) -> None:
        self._root.destroy()


class TerminalKeyReader:
    """Read single key presses from a terminal without requiring Enter."""

    def __init__(self) -> None:
        self._stdin = sys.stdin
        self._fd = self._stdin.fileno()
        self._old_settings = None

        if msvcrt is None:
            if termios is None or tty is None or not self._stdin.isatty():
                raise ValidationError("互動模式需要在可讀取單鍵輸入的終端機中執行")
            self._old_settings = termios.tcgetattr(self._fd)
            tty.setcbreak(self._fd)

    def read_key(self) -> Optional[str]:
        if msvcrt is not None:
            if not msvcrt.kbhit():
                time.sleep(0.05)
                return None
            return msvcrt.getwch()

        ready, _, _ = select.select([self._stdin], [], [], 0.05)
        if not ready:
            return None
        return os.read(self._fd, 1).decode("utf-8", errors="replace")

    def close(self) -> None:
        if self._old_settings is not None:
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old_settings)


@dataclass(frozen=True)
class ValidationConfig:
    active_duration: float = 2.0
    stopped_duration: float = 1.0
    sample_interval: float = 0.05
    stop_settle_time: float = 0.0
    ack_timeout: float = 3.0
    minimum_active_changes: int = 3
    expected_movement_interval: float = 0.20
    movement_interval_tolerance: float = 0.12
    line_ending: bytes = b"\n"


@dataclass(frozen=True)
class ValidationResult:
    active_changes: int
    median_active_interval: float
    stopped_changes: int


class ArduinoMouseValidator:
    def __init__(
        self,
        connection: SerialConnection,
        pointer: PointerReader,
        config: ValidationConfig,
        *,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        output: Callable[[str], None] = print,
    ) -> None:
        self.connection = connection
        self.pointer = pointer
        self.config = config
        self.sleep = sleep
        self.monotonic = monotonic
        self.output = output

    def _send(self, command: bytes) -> None:
        self.connection.write(command + self.config.line_ending)
        self.connection.flush()

    def _wait_for_ack(self, expected: str) -> None:
        deadline = self.monotonic() + self.config.ack_timeout
        received: List[str] = []

        while self.monotonic() < deadline:
            raw_line = self.connection.readline()
            if not raw_line:
                continue
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            received.append(line)
            self.output(f"  RX: {line}")
            if line == expected:
                return

        detail = ", ".join(received) if received else "沒有收到任何資料"
        raise ValidationError(f"未在 {self.config.ack_timeout:g} 秒內收到「{expected}」；{detail}")

    def _sample_changes(self, duration: float) -> Tuple[int, List[float]]:
        sample_count = max(1, math.ceil(duration / self.config.sample_interval))
        previous = self.pointer.position()
        changes = 0
        change_times: List[float] = []

        for _ in range(sample_count):
            self.sleep(self.config.sample_interval)
            current = self.pointer.position()
            if current != previous:
                changes += 1
                change_times.append(self.monotonic())
            previous = current

        intervals = [
            later - earlier
            for earlier, later in zip(change_times, change_times[1:])
        ]
        return changes, intervals

    def run(self) -> ValidationResult:
        stop_sent = False
        try:
            self.output("[1/4] 傳送 S，等待啟動 ACK...")
            self._send(b"S")
            self._wait_for_ack(START_ACK)

            self.output("[2/4] 取樣滑鼠座標，請勿碰觸滑鼠...")
            active_changes, active_intervals = self._sample_changes(self.config.active_duration)
            if active_changes < self.config.minimum_active_changes:
                raise ValidationError(
                    "啟動後只偵測到 "
                    f"{active_changes} 次座標變化，低於門檻 "
                    f"{self.config.minimum_active_changes} 次"
                )
            median_interval = statistics.median(active_intervals)
            minimum_interval = (
                self.config.expected_movement_interval
                - self.config.movement_interval_tolerance
            )
            maximum_interval = (
                self.config.expected_movement_interval
                + self.config.movement_interval_tolerance
            )
            if not minimum_interval <= median_interval <= maximum_interval:
                raise ValidationError(
                    "滑鼠座標變化週期中位數為 "
                    f"{median_interval * 1000:.0f} ms，未落在約 200 ms 的允收範圍 "
                    f"({minimum_interval * 1000:.0f}–{maximum_interval * 1000:.0f} ms)"
                )

            self.output("[3/4] 傳送 P，等待停止 ACK...")
            self._send(b"P")
            stop_sent = True
            self._wait_for_ack(STOP_ACK)

            self.output("[4/4] 確認滑鼠已停止，請勿碰觸滑鼠...")
            self.sleep(self.config.stop_settle_time)
            stopped_changes, _ = self._sample_changes(self.config.stopped_duration)
            if stopped_changes:
                raise ValidationError(
                    f"收到停止 ACK 後仍偵測到 {stopped_changes} 次座標變化"
                )

            return ValidationResult(active_changes, median_interval, stopped_changes)
        finally:
            # Fail safe: if validation aborts while movement may still be active,
            # make one best-effort stop request.
            if not stop_sent:
                try:
                    self._send(b"P")
                except Exception:
                    pass


class InteractiveSpaceController:
    def __init__(
        self,
        connection: SerialConnection,
        config: ValidationConfig,
        key_reader: KeyReader,
        *,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        output: Callable[[str], None] = print,
    ) -> None:
        self.connection = connection
        self.config = config
        self.key_reader = key_reader
        self.output = output
        self._validator = ArduinoMouseValidator(
            connection,
            pointer=_NullPointerReader(),
            config=config,
            sleep=sleep,
            monotonic=monotonic,
            output=output,
        )

    def _send_and_wait(self, command: bytes, expected_ack: str) -> None:
        self._validator._send(command)
        try:
            self._validator._wait_for_ack(expected_ack)
        except ValidationError as exc:
            command_text = command.decode("ascii", errors="replace")
            raise ValidationError(
                f"已送出 {command_text}，但沒有收到預期 ACK。{exc}。"
                "若 Arduino 程式只在狀態變更時回 ACK，請先確認板子目前狀態，"
                "或將韌體改成收到 S/P 一律回 ACK。"
            ) from exc

    def run(self) -> None:
        started = False
        self.output("互動模式已啟動。按空白鍵切換 S/P；按 q 或 Esc 離開。")
        self.output("下一次空白鍵：發送 S")

        try:
            while True:
                key = self.key_reader.read_key()
                if key is None:
                    continue
                if key == "\x03":
                    raise KeyboardInterrupt
                if key in ("q", "Q", "\x1b"):
                    return
                if key != " ":
                    continue

                if started:
                    self.output("偵測到空白鍵，TX: P")
                    self._send_and_wait(b"P", STOP_ACK)
                    started = False
                    self.output("下一次空白鍵：發送 S")
                else:
                    self.output("偵測到空白鍵，TX: S")
                    self._send_and_wait(b"S", START_ACK)
                    started = True
                    self.output("下一次空白鍵：發送 P")
        finally:
            if started:
                try:
                    self.output("離開前送出 P...")
                    self._send_and_wait(b"P", STOP_ACK)
                except Exception:
                    pass


class _NullPointerReader:
    def position(self) -> Tuple[int, int]:
        return (0, 0)

    def close(self) -> None:
        pass


class ArduinoMouseValidatorGui:
    """Small, non-blocking Tk user interface for the automatic validator."""

    def __init__(self, config: ValidationConfig, boot_wait: float = 2.0) -> None:
        self.config = config
        self.boot_wait = max(0.0, boot_wait)
        self.root = tk.Tk()
        self.root.title("Arduino Mouse Validator")
        self.root.resizable(False, False)
        self._configure_style()
        self.connection: Optional[SerialConnection] = None
        self.port_map: dict[str, str] = {}
        self.port_labels: List[str] = []
        self.phase = "idle"
        self.deadline = 0.0
        self.sample_end = 0.0
        self.previous_position: Optional[Tuple[int, int]] = None
        self.active_changes = 0
        self.stopped_changes = 0
        self.change_times: List[float] = []
        self.may_be_moving = False
        self.rx_buffer = ""
        self._build_widgets()
        self.refresh_ports()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(30, self.poll)

    def _configure_style(self) -> None:
        """Use explicit colours so macOS dark mode cannot hide ttk button text."""
        background = "#2b2b2b"
        foreground = "#f3f4f6"
        control_background = "#f8fafc"
        control_foreground = "#111827"

        self.root.configure(background=background)
        style = ttk.Style(self.root)
        # The Aqua theme can render white button text on a white control in
        # macOS dark mode. clam honours the colours below consistently.
        style.theme_use("clam")
        style.configure("TFrame", background=background)
        style.configure("TLabel", background=background, foreground=foreground)
        style.configure(
            "TButton",
            background=control_background,
            foreground=control_foreground,
            padding=(10, 6),
        )
        style.map(
            "TButton",
            background=[("active", "#dbeafe"), ("disabled", "#9ca3af")],
            foreground=[("disabled", "#4b5563")],
        )
        style.configure(
            "TCombobox",
            fieldbackground=control_background,
            background=control_background,
            foreground=control_foreground,
            arrowcolor=control_foreground,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", control_background), ("disabled", "#9ca3af")],
            foreground=[("readonly", control_foreground), ("disabled", "#4b5563")],
            selectforeground=[("readonly", control_foreground)],
            selectbackground=[("readonly", control_background)],
        )

    def _build_widgets(self) -> None:
        frame = ttk.Frame(self.root, padding=12)
        frame.grid(sticky="nsew")
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="USB CDC 序列埠：").grid(row=0, column=0, sticky="nw")
        # A Listbox is more reliable than ttk.Combobox on macOS: opening a
        # themed native popup can require multiple clicks before it accepts a
        # selection. The validator normally has only a few serial devices.
        self.port_list = tk.Listbox(
            frame,
            height=3,
            width=62,
            selectmode=tk.BROWSE,
            exportselection=False,
            background="#f8fafc",
            foreground="#111827",
            selectbackground="#2563eb",
            selectforeground="#ffffff",
            highlightthickness=1,
            highlightbackground="#94a3b8",
            relief="flat",
        )
        self.port_list.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        self.refresh_button = ttk.Button(frame, text="重新掃描", command=self.refresh_ports)
        self.refresh_button.grid(row=0, column=2)

        self.status_value = tk.StringVar(value="請選擇 Arduino 序列埠")
        ttk.Label(frame, textvariable=self.status_value).grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(8, 6)
        )

        buttons = ttk.Frame(frame)
        buttons.grid(row=2, column=0, columnspan=3, sticky="w", pady=(0, 8))
        self.validate_button = ttk.Button(buttons, text="開始完整驗證", command=self.start_validation)
        self.validate_button.grid(row=0, column=0, padx=(0, 8))
        self.start_button = ttk.Button(buttons, text="手動送出 S", command=lambda: self.manual_send(b"S"))
        self.start_button.grid(row=0, column=1, padx=(0, 8))
        self.stop_button = ttk.Button(buttons, text="送出 P／中止驗證", command=self.stop_or_abort)
        self.stop_button.grid(row=0, column=2)

        ttk.Label(frame, text="執行紀錄：").grid(row=3, column=0, columnspan=3, sticky="w")
        self.log_box = tk.Text(frame, width=68, height=14, state="disabled", wrap="word")
        self.log_box.grid(row=4, column=0, columnspan=3, pady=(3, 0))

    def log(self, message: str) -> None:
        self.log_box.configure(state="normal")
        self.log_box.insert("end", message + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def refresh_ports(self) -> None:
        try:
            ports = list(available_ports())
        except ValidationError as exc:
            self.status_value.set(f"FAIL：{exc}")
            return

        selected_devices = [
            self.port_map.get(self.port_labels[index])
            for index in self.port_list.curselection()
            if index < len(self.port_labels)
        ]
        self.port_map = {describe_port(item): item.device for item in ports}
        self.port_labels = list(self.port_map)
        self.port_list.delete(0, tk.END)
        for label in self.port_labels:
            self.port_list.insert(tk.END, label)
        if self.port_labels:
            try:
                selected_index = self.port_labels.index(selected_devices[0])
            except (IndexError, ValueError):
                selected_index = 0
            self.port_list.selection_set(selected_index)
            self.port_list.activate(selected_index)
            self.status_value.set(f"找到 {len(self.port_labels)} 個序列埠；波特率固定為 115200")
        else:
            self.status_value.set("找不到序列埠；請確認 Arduino 已透過 USB 連線")

    def selected_port(self) -> str:
        selection = self.port_list.curselection()
        port = self.port_map.get(self.port_labels[selection[0]]) if selection else None
        if not port:
            raise ValidationError("請先選擇 Arduino 序列埠")
        return port

    def _connect(self, on_ready: Callable[[], None]) -> None:
        if self.connection is not None:
            on_ready()
            return
        if serial is None:
            self.fail("尚未安裝 pyserial，請先執行：python3 -m pip install -r requirements.txt")
            return
        try:
            port = self.selected_port()
            self.connection = serial.Serial(port=port, baudrate=115200, timeout=0)
            self.connection.reset_input_buffer()
            self.status_value.set(f"已開啟 {port}，等待 Arduino 就緒…")
            self.log(f"連線：{port} @ 115200 baud")
            self.root.after(round(self.boot_wait * 1000), on_ready)
        except (OSError, ValidationError) as exc:
            self.fail(str(exc))

    def _send(self, command: bytes) -> None:
        if self.connection is None:
            raise ValidationError("序列埠尚未連線")
        self.connection.write(command + self.config.line_ending)
        self.connection.flush()
        self.log(f"TX: {command.decode('ascii')}")

    def manual_send(self, command: bytes) -> None:
        if self.phase != "idle":
            self.log("驗證進行中，請等待完成或關閉視窗（會嘗試送出 P）。")
            return
        self._connect(lambda: self._manual_send_ready(command))

    def stop_or_abort(self) -> None:
        """Keep P available as an emergency stop while an automatic run is active."""
        if self.phase != "idle":
            try:
                self._send(b"P")
                self.log("驗證已由使用者中止。")
            except (OSError, ValidationError) as exc:
                self.log(f"送出 P 失敗：{exc}")
            self.may_be_moving = False
            self.phase = "idle"
            self._set_busy(False)
            self.status_value.set("驗證已中止，已嘗試送出 P")
            return
        self.manual_send(b"P")

    def _manual_send_ready(self, command: bytes) -> None:
        try:
            self._send(command)
            self.may_be_moving = command == b"S"
            self.status_value.set(f"已送出 {command.decode('ascii')}，等待 Arduino ACK…")
        except (OSError, ValidationError) as exc:
            self.fail(str(exc))

    def start_validation(self) -> None:
        if self.phase != "idle":
            return
        self._set_busy(True)
        self.phase = "connecting"
        self.status_value.set("準備開始驗證…")
        self._connect(self._start_validation_ready)

    def _start_validation_ready(self) -> None:
        try:
            self._send(b"S")
            self.may_be_moving = True
            self.phase = "wait_start_ack"
            self.deadline = time.monotonic() + self.config.ack_timeout
            self.status_value.set("[1/4] 已送出 S，等待啟動 ACK…")
        except (OSError, ValidationError) as exc:
            self.fail(str(exc))

    def _begin_active_sample(self) -> None:
        self.phase = "sample_active"
        self.previous_position = self.root.winfo_pointerxy()
        self.active_changes = 0
        self.change_times = []
        self.sample_end = time.monotonic() + self.config.active_duration
        self.status_value.set("[2/4] 正在取樣滑鼠座標；請勿碰觸滑鼠…")
        self.root.after(round(self.config.sample_interval * 1000), self.sample_active)

    def sample_active(self) -> None:
        if self.phase != "sample_active":
            return
        current = self.root.winfo_pointerxy()
        if current != self.previous_position:
            self.active_changes += 1
            self.change_times.append(time.monotonic())
        self.previous_position = current
        if time.monotonic() < self.sample_end:
            self.root.after(round(self.config.sample_interval * 1000), self.sample_active)
            return

        intervals = [later - earlier for earlier, later in zip(self.change_times, self.change_times[1:])]
        try:
            if self.active_changes < self.config.minimum_active_changes:
                raise ValidationError(f"啟動後只偵測到 {self.active_changes} 次座標變化，低於門檻 {self.config.minimum_active_changes} 次")
            median_interval = statistics.median(intervals)
            low = self.config.expected_movement_interval - self.config.movement_interval_tolerance
            high = self.config.expected_movement_interval + self.config.movement_interval_tolerance
            if not low <= median_interval <= high:
                raise ValidationError(f"滑鼠座標變化週期中位數為 {median_interval * 1000:.0f} ms，未落在約 200 ms 的允收範圍 ({low * 1000:.0f}–{high * 1000:.0f} ms)")
            self.log(f"啟動期間偵測到 {self.active_changes} 次座標變化，週期中位數 {median_interval * 1000:.0f} ms")
            self._send(b"P")
            self.phase = "wait_stop_ack"
            self.deadline = time.monotonic() + self.config.ack_timeout
            self.status_value.set("[3/4] 已送出 P，等待停止 ACK…")
        except (OSError, ValidationError) as exc:
            self.fail(str(exc), send_stop=True)

    def _begin_stopped_sample(self) -> None:
        self.phase = "sample_stopped"
        self.previous_position = self.root.winfo_pointerxy()
        self.stopped_changes = 0
        self.sample_end = time.monotonic() + self.config.stopped_duration
        self.status_value.set("[4/4] 確認滑鼠已停止；請勿碰觸滑鼠…")
        self.root.after(round(self.config.sample_interval * 1000), self.sample_stopped)

    def sample_stopped(self) -> None:
        if self.phase != "sample_stopped":
            return
        current = self.root.winfo_pointerxy()
        if current != self.previous_position:
            self.stopped_changes += 1
        self.previous_position = current
        if time.monotonic() < self.sample_end:
            self.root.after(round(self.config.sample_interval * 1000), self.sample_stopped)
            return
        if self.stopped_changes:
            self.fail(f"收到停止 ACK 後仍偵測到 {self.stopped_changes} 次座標變化")
            return
        self.phase = "idle"
        self.may_be_moving = False
        self._set_busy(False)
        self.status_value.set("PASS：Arduino S/P、ACK 與滑鼠移動／停止皆正常")
        self.log("PASS：完整驗證成功")

    def poll(self) -> None:
        try:
            if self.connection is not None:
                waiting = getattr(self.connection, "in_waiting", 0)
                if waiting:
                    raw = self.connection.read(waiting)
                    self.rx_buffer += raw.decode("utf-8", errors="replace")
                    while "\n" in self.rx_buffer:
                        line, self.rx_buffer = self.rx_buffer.split("\n", 1)
                        self.handle_line(line.strip())
            if self.phase in ("wait_start_ack", "wait_stop_ack") and time.monotonic() >= self.deadline:
                expected = START_ACK if self.phase == "wait_start_ack" else STOP_ACK
                self.fail(f"未在 {self.config.ack_timeout:g} 秒內收到「{expected}」", send_stop=True)
        except OSError as exc:
            self.fail(str(exc), send_stop=False)
        finally:
            self.root.after(30, self.poll)

    def handle_line(self, line: str) -> None:
        if not line:
            return
        self.log(f"RX: {line}")
        if self.phase == "wait_start_ack" and line == START_ACK:
            self._begin_active_sample()
        elif self.phase == "wait_stop_ack" and line == STOP_ACK:
            self.may_be_moving = False
            self.root.after(round(self.config.stop_settle_time * 1000), self._begin_stopped_sample)

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self.validate_button.configure(state=state)
        self.start_button.configure(state=state)
        self.refresh_button.configure(state=state)
        self.port_list.configure(state="disabled" if busy else "normal")

    def fail(self, message: str, send_stop: bool = False) -> None:
        if send_stop and self.may_be_moving:
            try:
                self._send(b"P")
            except (OSError, ValidationError):
                pass
        self.phase = "idle"
        self._set_busy(False)
        self.status_value.set(f"FAIL：{message}")
        self.log(f"FAIL：{message}")

    def close(self) -> None:
        if self.connection is not None:
            if self.may_be_moving:
                try:
                    self._send(b"P")
                except (OSError, ValidationError):
                    pass
            self.connection.close()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def available_ports() -> Sequence[object]:
    if list_ports is None:
        raise ValidationError("尚未安裝 pyserial，請先執行：python3 -m pip install -r requirements.txt")
    return sorted(list_ports.comports(), key=lambda item: item.device)


def describe_port(port: object) -> str:
    device = getattr(port, "device", "?")
    description = getattr(port, "description", "") or "未知裝置"
    manufacturer = getattr(port, "manufacturer", "") or ""
    suffix = f" / {manufacturer}" if manufacturer else ""
    return f"{device}: {description}{suffix}"


def choose_port(requested: str) -> str:
    if requested != "auto":
        return requested

    ports = list(available_ports())
    if not ports:
        raise ValidationError("找不到任何序列埠；請確認 Arduino 已接上 USB")
    if len(ports) == 1:
        return ports[0].device

    keywords = ("arduino", "ch340", "cp210", "usb serial", "usb-serial")
    candidates = [
        item
        for item in ports
        if any(
            keyword in " ".join(
                str(getattr(item, name, "") or "")
                for name in ("description", "manufacturer", "product")
            ).lower()
            for keyword in keywords
        )
    ]
    if len(candidates) == 1:
        return candidates[0].device

    choices = "\n".join(f"  {describe_port(item)}" for item in ports)
    raise ValidationError(
        "無法自動判斷 Arduino 序列埠，請使用 --port 指定：\n" + choices
    )


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="驗證 Arduino 序列命令與 USB 滑鼠抖動功能")
    parser.add_argument("--port", default="auto", help="序列埠，例如 /dev/cu.usbmodem1101（預設：auto）")
    parser.add_argument("--baud", type=int, default=115200, help="波特率（預設：115200）")
    parser.add_argument("--list-ports", action="store_true", help="列出序列埠後結束")
    parser.add_argument("--gui", action="store_true", help="以圖形介面執行驗證器")
    parser.add_argument("--boot-wait", type=float, default=2.0, help="開啟序列埠後等待板子重啟的秒數")
    parser.add_argument("--ack-timeout", type=float, default=3.0, help="等待每個 ACK 的秒數")
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="改用空白鍵切換發送 S/P，不做自動滑鼠座標驗證",
    )
    parser.add_argument("--active-duration", type=float, default=2.0, help="啟動後觀察滑鼠的秒數")
    parser.add_argument("--stopped-duration", type=float, default=1.0, help="停止後觀察滑鼠的秒數")
    parser.add_argument(
        "--line-ending",
        choices=("none", "newline", "crlf"),
        default="newline",
        help="命令結尾（預設：newline）",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    connection: Optional[SerialConnection] = None
    pointer: Optional[PointerReader] = None

    try:
        endings = {"none": b"", "newline": b"\n", "crlf": b"\r\n"}
        config = ValidationConfig(
            active_duration=args.active_duration,
            stopped_duration=args.stopped_duration,
            ack_timeout=args.ack_timeout,
            line_ending=endings[args.line_ending],
        )
        if args.gui:
            ArduinoMouseValidatorGui(config, args.boot_wait).run()
            return 0

        if args.list_ports:
            ports = available_ports()
            if not ports:
                print("找不到任何序列埠")
                return 1
            for item in ports:
                print(describe_port(item))
            return 0

        if serial is None:
            raise ValidationError("尚未安裝 pyserial，請先執行：python3 -m pip install -r requirements.txt")

        port = choose_port(args.port)
        print(f"使用序列埠：{port} @ {args.baud} baud")
        connection = serial.Serial(port=port, baudrate=args.baud, timeout=0.1)
        time.sleep(max(0.0, args.boot_wait))
        connection.reset_input_buffer()

        if args.interactive:
            key_reader = TerminalKeyReader()
            try:
                InteractiveSpaceController(connection, config, key_reader).run()
            finally:
                key_reader.close()
            print("互動模式已結束。")
            return 0

        pointer = TkPointerReader()
        result = ArduinoMouseValidator(connection, pointer, config).run()
        print(
            "PASS：S/P ACK 正確，啟動期間偵測到 "
            f"{result.active_changes} 次座標變化（週期中位數 "
            f"{result.median_active_interval * 1000:.0f} ms），停止後為 "
            f"{result.stopped_changes} 次。"
        )
        return 0
    except (ValidationError, OSError) as exc:
        print(f"FAIL：{exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n測試已取消；已嘗試送出 P。", file=sys.stderr)
        return 130
    finally:
        if pointer is not None:
            pointer.close()
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
