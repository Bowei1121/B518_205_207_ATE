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

        endings = {"none": b"", "newline": b"\n", "crlf": b"\r\n"}
        config = ValidationConfig(
            active_duration=args.active_duration,
            stopped_duration=args.stopped_duration,
            ack_timeout=args.ack_timeout,
            line_ending=endings[args.line_ending],
        )
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
