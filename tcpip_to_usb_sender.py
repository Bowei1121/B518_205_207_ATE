#!/usr/bin/env python3
"""Send newline-terminated test messages to the Arduino TCP-to-USB bridge."""

from __future__ import annotations

import argparse
import socket
import sys
import time
from typing import Optional, Sequence


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="送測試資料到 Arduino TCP server")
    parser.add_argument("host", help="Arduino IP，例如 192.168.1.80")
    parser.add_argument("message", nargs="*", help="要送出的文字；多個參數會用空白串接")
    parser.add_argument("--port", type=int, default=5000, help="TCP port（預設：5000）")
    parser.add_argument("--timeout", type=float, default=3.0, help="連線/讀取逾時秒數")
    parser.add_argument("--connect-only", action="store_true", help="只測試 TCP 是否可連線，不送資料")
    parser.add_argument("--no-readback", action="store_true", help="送出後不等待 Arduino TCP ACK")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    if not args.connect_only and not args.message:
        print("FAIL：請提供要送出的 message，或使用 --connect-only 只測 TCP 連線", file=sys.stderr)
        return 1

    payload = " ".join(args.message)
    address = (args.host, args.port)

    try:
        print(f"CONNECT: {args.host}:{args.port} timeout={args.timeout:g}s")
        with socket.create_connection(address, timeout=args.timeout) as sock:
            print("CONNECTED")
            sock.settimeout(args.timeout)

            if args.connect_only:
                return 0

            print(f"TX: {payload}")
            sock.sendall((payload + "\n").encode("utf-8"))

            if not args.no_readback:
                expected_ack = "ACK " + payload
                deadline = time.monotonic() + args.timeout
                buffer = ""
                print(f"WAIT_ACK: {expected_ack}")

                while time.monotonic() < deadline:
                    try:
                        chunk = sock.recv(1024)
                    except socket.timeout:
                        break
                    if not chunk:
                        break

                    buffer += chunk.decode("utf-8", errors="replace")
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.strip()
                        if not line:
                            continue
                        print(line)
                        if line == expected_ack:
                            return 0

                print(f"FAIL：未收到 {expected_ack!r}", file=sys.stderr)
                return 1
        return 0
    except socket.timeout:
        print(
            "FAIL：TCP 連線逾時。請先確認 Arduino IP/port、電腦是否同網段、"
            "網路線/WI5100 link 燈號、以及 Arduino 是否已印出 TCP server ready。",
            file=sys.stderr,
        )
        return 1
    except ConnectionRefusedError:
        print(
            "FAIL：TCP 連線被拒絕。代表 IP 可到，但 Arduino 端沒有在該 port listen。",
            file=sys.stderr,
        )
        return 1
    except OSError as exc:
        print(f"FAIL：TCP 連線失敗：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
