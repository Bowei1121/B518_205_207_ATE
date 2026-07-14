#!/usr/bin/env python3
"""Receive TCP payloads forwarded by Arduino over USB Serial."""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from typing import Callable, Optional, Protocol, Sequence, TextIO

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    serial = None
    list_ports = None


DATA_PREFIX = "DATA:"
EVENT_PREFIX = "EVT:"
ERROR_PREFIX = "ERR:"


class ReceiverError(RuntimeError):
    """A user-facing receiver failure."""


class SerialConnection(Protocol):
    def readline(self) -> bytes: ...

    def reset_input_buffer(self) -> None: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class ReceivedLine:
    kind: str
    payload: str
    raw: str


def parse_serial_line(raw_line: bytes) -> Optional[ReceivedLine]:
    text = raw_line.decode("utf-8", errors="replace").strip()
    if not text:
        return None
    if text.startswith(DATA_PREFIX):
        return ReceivedLine("data", text[len(DATA_PREFIX):], text)
    if text.startswith(EVENT_PREFIX):
        return ReceivedLine("event", text[len(EVENT_PREFIX):].strip(), text)
    if text.startswith(ERROR_PREFIX):
        return ReceivedLine("error", text[len(ERROR_PREFIX):].strip(), text)
    return ReceivedLine("raw", text, text)


class UsbSerialReceiver:
    def __init__(
        self,
        connection: SerialConnection,
        *,
        output: Callable[[str], None] = print,
        data_file: Optional[TextIO] = None,
        show_raw: bool = False,
    ) -> None:
        self.connection = connection
        self.output = output
        self.data_file = data_file
        self.show_raw = show_raw

    def read_once(self) -> Optional[ReceivedLine]:
        line = parse_serial_line(self.connection.readline())
        if line is None:
            return None

        if line.kind == "data":
            self.output(f"DATA: {line.payload}")
            if self.data_file is not None:
                self.data_file.write(line.payload + "\n")
                self.data_file.flush()
        elif self.show_raw or line.kind in ("event", "error"):
            self.output(f"{line.kind.upper()}: {line.payload}")

        return line

    def run(self, *, count: int = 0, timeout: float = 0.0) -> int:
        received_data = 0
        deadline = time.monotonic() + timeout if timeout > 0 else None

        while count <= 0 or received_data < count:
            if deadline is not None and time.monotonic() >= deadline:
                raise ReceiverError(
                    f"等待資料逾時：{timeout:g} 秒內只收到 {received_data} 筆 DATA"
                )

            line = self.read_once()
            if line is None:
                continue
            if line.kind == "data":
                received_data += 1

        return received_data


def available_ports() -> Sequence[object]:
    if list_ports is None:
        raise ReceiverError("尚未安裝 pyserial，請先執行：python3 -m pip install -r requirements.txt")
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
        raise ReceiverError("找不到任何序列埠；請確認 Arduino 已接上 USB")
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
    raise ReceiverError("無法自動判斷 Arduino 序列埠，請使用 --port 指定：\n" + choices)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="接收 Arduino 從 TCP 轉送到 USB Serial 的資料")
    parser.add_argument("--port", default="auto", help="序列埠，例如 /dev/cu.usbmodem1101（預設：auto）")
    parser.add_argument("--baud", type=int, default=115200, help="波特率（預設：115200）")
    parser.add_argument("--list-ports", action="store_true", help="列出序列埠後結束")
    parser.add_argument("--count", type=int, default=0, help="收到幾筆 DATA 後結束；0 代表持續接收")
    parser.add_argument("--timeout", type=float, default=0.0, help="等待 DATA 的逾時秒數；0 代表不逾時")
    parser.add_argument("--output-file", help="將 DATA payload 另存成文字檔，每筆一行")
    parser.add_argument("--raw", action="store_true", help="顯示未分類或狀態行")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    connection: Optional[SerialConnection] = None
    data_file: Optional[TextIO] = None

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
            raise ReceiverError("尚未安裝 pyserial，請先執行：python3 -m pip install -r requirements.txt")

        port = choose_port(args.port)
        print(f"使用序列埠：{port} @ {args.baud} baud")
        connection = serial.Serial(port=port, baudrate=args.baud, timeout=0.1)
        time.sleep(1.0)
        connection.reset_input_buffer()

        if args.output_file:
            data_file = open(args.output_file, "a", encoding="utf-8")

        receiver = UsbSerialReceiver(
            connection,
            data_file=data_file,
            show_raw=args.raw,
        )
        received = receiver.run(count=args.count, timeout=args.timeout)
        if args.count > 0:
            print(f"完成：收到 {received} 筆 DATA")
        return 0
    except (ReceiverError, OSError) as exc:
        print(f"FAIL：{exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n接收已停止。", file=sys.stderr)
        return 130
    finally:
        if data_file is not None:
            data_file.close()
        if connection is not None:
            connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
