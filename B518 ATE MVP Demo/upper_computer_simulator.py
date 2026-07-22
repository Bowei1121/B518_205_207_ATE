#!/usr/bin/env python3
"""Windows upper-computer simulator for the Atlas Arduino TCP bridge.

The Arduino is the TCP server.  This utility is the one active TCP client and
keeps the socket open until the test computer returns a CRLF-delimited RESULT.
"""
from __future__ import annotations

import json
import os
import queue
import re
import socket
import threading
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import tkinter as tk
from tkinter import messagebox, ttk

TITLE = "B518 ATE 上位機模擬器 V0.1.0"
DEFAULT_IP = "192.168.1.100"
DEFAULT_PORT = 5000
SN_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
RESULT_STATUSES = {"PASS", "FAIL", "TIMEOUT", "UNKNOWN"}


class ProtocolError(ValueError):
    pass


@dataclass
class Preferences:
    ip: str = DEFAULT_IP
    port: int = DEFAULT_PORT
    station: str = "DFU"


@dataclass(frozen=True)
class ResultFrame:
    station: str
    job_id: str
    results: dict[int, tuple[str, str]]


def preference_file() -> Path:
    root = Path(os.environ.get("APPDATA", Path.home() / ".config")) / "B518UpperComputerSimulator"
    return root / "preferences.json"


def load_preferences(path: Path) -> Preferences:
    try:
        return Preferences(**json.loads(path.read_text(encoding="utf-8")))
    except (OSError, TypeError, ValueError):
        return Preferences()


def save_preferences(path: Path, pref: Preferences) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(pref), ensure_ascii=False, indent=2), encoding="utf-8")


def make_batch(station: str, job_id: str, sns: list[str]) -> tuple[dict[int, str], bytes]:
    """Return explicit slot assignments and the exact TCP CRLF JOB frame."""
    station, job_id = station.strip().upper(), job_id.strip()
    if station not in ("DFU", "FCT", "BT"):
        raise ProtocolError("工站必須是 DFU、FCT 或 BT")
    if not SN_PATTERN.fullmatch(job_id) or len(job_id) > 64:
        raise ProtocolError("JOB ID 只可使用英數、點、底線或連字號，最多 64 字元")
    assignments = {index: value for index, item in enumerate(sns, start=1) if (value := item.strip())}
    values = list(assignments.values())
    if not 1 <= len(assignments) <= 4:
        raise ProtocolError("請輸入 1 至 4 個條碼")
    if len(set(values)) != len(values):
        raise ProtocolError("同一批條碼不可重複")
    if any(not SN_PATTERN.fullmatch(item) for item in values):
        raise ProtocolError("條碼只可使用英數、點、底線或連字號，且不可含空白")
    payload = ",".join(f"{slot}={sn}" for slot, sn in assignments.items())
    return assignments, f"{station}:JOB={job_id};{payload}\r\n".encode("utf-8")


def parse_result_frame(line: str) -> Optional[ResultFrame]:
    """Parse one RESULT frame; non-result bridge diagnostics return None."""
    line = line.strip()
    if not line.startswith("RESULT:"):
        return None
    try:
        header, payload = line[7:].split(";", 1)
        station, job_field = header.split(":", 1)
    except ValueError as exc:
        raise ProtocolError("RESULT 缺少工站、JOB 或 slot 結果") from exc
    station = station.upper()
    if station not in ("DFU", "FCT", "BT") or not job_field.upper().startswith("JOB="):
        raise ProtocolError("RESULT 工站或 JOB 欄位錯誤")
    job_id = job_field[4:].strip()
    if not SN_PATTERN.fullmatch(job_id) or not payload:
        raise ProtocolError("RESULT 沒有任何 SN 結果")
    parsed: dict[int, tuple[str, str]] = {}
    seen_sns: set[str] = set()
    for item in payload.split(";"):
        try:
            slot_sn, status = (part.strip() for part in item.split(",", 1))
            slot_text, sn = (part.strip() for part in slot_sn.split("=", 1))
            slot = int(slot_text)
        except ValueError as exc:
            raise ProtocolError(f"RESULT 格式錯誤：{item}") from exc
        status = status.upper()
        if not 1 <= slot <= 4 or not SN_PATTERN.fullmatch(sn) or status not in RESULT_STATUSES or slot in parsed or sn in seen_sns:
            raise ProtocolError(f"RESULT 欄位無效：{item}")
        parsed[slot] = (sn, status); seen_sns.add(sn)
    return ResultFrame(station, job_id, parsed)


class TcpClient:
    def __init__(self, on_event: Callable[[str, object], None]) -> None:
        self.on_event = on_event
        self.socket: Optional[socket.socket] = None
        self.stop = threading.Event()
        self.lock = threading.Lock()
        self.receiver: Optional[threading.Thread] = None

    @property
    def connected(self) -> bool:
        return self.socket is not None and not self.stop.is_set()

    def connect(self, ip: str, port: int) -> None:
        self.close()
        client = socket.create_connection((ip, port), timeout=5)
        client.settimeout(.5)
        self.socket, self.stop = client, threading.Event()
        self.receiver = threading.Thread(target=self._receive, daemon=True)
        self.receiver.start()

    def send(self, frame: bytes) -> None:
        if not self.connected or self.socket is None:
            raise ProtocolError("尚未連線 Arduino TCP server")
        with self.lock:
            self.socket.sendall(frame)

    def _receive(self) -> None:
        buffer = bytearray()
        try:
            while not self.stop.is_set() and self.socket is not None:
                try:
                    chunk = self.socket.recv(1024)
                except socket.timeout:
                    continue
                if not chunk:
                    break
                buffer.extend(chunk)
                while b"\n" in buffer:
                    ending = buffer.index(b"\n")
                    line = bytes(buffer[:ending]).rstrip(b"\r").decode("utf-8", errors="replace")
                    del buffer[:ending + 1]
                    if line:
                        self.on_event("line", line)
        except OSError as exc:
            if not self.stop.is_set():
                self.on_event("log", f"TCP 接收中斷：{exc}")
        finally:
            self.on_event("disconnected", None)

    def close(self) -> None:
        self.stop.set()
        if self.socket is not None:
            try:
                self.socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.socket.close()
        self.socket = None


class UpperComputerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(TITLE)
        self.root.geometry("760x580")
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.client = TcpClient(lambda kind, item: self.events.put((kind, item)))
        self.pref_path = preference_file()
        pref = load_preferences(self.pref_path)
        self.ip, self.port = tk.StringVar(value=pref.ip), tk.StringVar(value=str(pref.port))
        self.station = tk.StringVar(value=pref.station if pref.station in ("DFU", "FCT", "BT") else "DFU")
        self.job_id = tk.StringVar(value=self.new_job_id())
        self.sns = [tk.StringVar() for _ in range(4)]
        self.statuses = [tk.StringVar(value="—") for _ in range(4)]
        self.connection_status = tk.StringVar(value="未連線")
        self._build()
        self.root.after(100, self.process_events)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _build(self) -> None:
        panel = ttk.Frame(self.root, padding=14); panel.pack(fill="both", expand=True)
        network = ttk.LabelFrame(panel, text="Arduino TCP 連線", padding=10); network.pack(fill="x")
        ttk.Label(network, text="IP：").grid(row=0, column=0, sticky="w")
        ttk.Entry(network, textvariable=self.ip, width=22).grid(row=0, column=1, sticky="w")
        ttk.Label(network, text="Port：").grid(row=0, column=2, sticky="w", padx=(16, 0))
        ttk.Entry(network, textvariable=self.port, width=8).grid(row=0, column=3, sticky="w")
        ttk.Button(network, text="連線", command=self.connect).grid(row=0, column=4, padx=(16, 4))
        ttk.Button(network, text="中斷", command=self.disconnect).grid(row=0, column=5)
        ttk.Label(network, textvariable=self.connection_status).grid(row=1, column=0, columnspan=6, sticky="w", pady=(7, 0))

        job = ttk.Frame(panel); job.pack(fill="x", pady=(12, 0))
        ttk.Label(job, text="工站：").pack(side="left")
        ttk.Combobox(job, textvariable=self.station, values=("DFU", "FCT", "BT"), width=8,
                     state="readonly").pack(side="left")
        ttk.Label(job, text="  JOB ID：").pack(side="left")
        ttk.Entry(job, textvariable=self.job_id).pack(side="left", fill="x", expand=True)
        ttk.Button(job, text="產生新 JOB", command=lambda: self.job_id.set(self.new_job_id())).pack(side="left", padx=(6, 0))

        batch = ttk.LabelFrame(panel, text="測試條碼（最多四台）", padding=10); batch.pack(fill="x", pady=(12, 0))
        ttk.Label(batch, text="#").grid(row=0, column=0, padx=(0, 8))
        ttk.Label(batch, text="SN 條碼").grid(row=0, column=1, sticky="w")
        ttk.Label(batch, text="測試結果").grid(row=0, column=2, sticky="w", padx=(14, 0))
        for index in range(4):
            ttk.Label(batch, text=f"Slot {index + 1}").grid(row=index + 1, column=0, sticky="w")
            ttk.Entry(batch, textvariable=self.sns[index], width=44).grid(row=index + 1, column=1, sticky="ew", pady=3)
            ttk.Label(batch, textvariable=self.statuses[index], width=13).grid(row=index + 1, column=2, sticky="w", padx=(14, 0))
        batch.columnconfigure(1, weight=1)
        buttons = ttk.Frame(panel); buttons.pack(fill="x", pady=12)
        ttk.Button(buttons, text="發送測試條碼", command=self.send_batch).pack(side="left")
        ttk.Button(buttons, text="清除", command=self.clear).pack(side="left", padx=6)
        ttk.Label(buttons, text="送出格式：STATION:JOB=id;slot=SN,...\\r\\n", foreground="#555").pack(side="right")

        ttk.Label(panel, text="TCP 通訊紀錄：").pack(anchor="w")
        self.log = tk.Text(panel, height=16, wrap="word", state="disabled")
        self.log.pack(fill="both", expand=True)

    def append(self, text: str) -> None:
        self.log.configure(state="normal"); self.log.insert("end", text + "\n"); self.log.see("end"); self.log.configure(state="disabled")

    @staticmethod
    def new_job_id() -> str:
        return datetime.now().strftime("%Y%m%d-%H%M%S-%f")

    def connect(self) -> None:
        try:
            port = int(self.port.get())
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            messagebox.showerror(TITLE, "Port 必須是 1 至 65535 的整數"); return
        ip = self.ip.get().strip()
        try:
            self.client.connect(ip, port)
        except OSError as exc:
            messagebox.showerror(TITLE, f"無法連線 {ip}:{port}\n{exc}"); return
        self.connection_status.set(f"已連線：{ip}:{port}")
        self.append(f"TCP 已連線：{ip}:{port}")

    def disconnect(self) -> None:
        self.client.close(); self.connection_status.set("未連線"); self.append("TCP 已中斷")

    def send_batch(self) -> None:
        try:
            assignments, frame = make_batch(self.station.get(), self.job_id.get(), [item.get() for item in self.sns])
            self.client.send(frame)
        except (ProtocolError, OSError) as exc:
            messagebox.showerror(TITLE, str(exc)); return
        for index, status in enumerate(self.statuses, start=1):
            status.set("WAIT ACK" if index in assignments else "—")
        self.append("TX: " + frame.decode("utf-8").rstrip("\r\n") + " [CRLF]")

    def clear(self) -> None:
        for sn, status in zip(self.sns, self.statuses):
            sn.set(""); status.set("—")

    def process_events(self) -> None:
        try:
            while True:
                kind, item = self.events.get_nowait()
                if kind == "line":
                    line = str(item); self.append("RX: " + line)
                    try:
                        result = parse_result_frame(line)
                    except ProtocolError as exc:
                        self.append("RESULT 判讀失敗：" + str(exc)); continue
                    if result:
                        if result.station != self.station.get() or result.job_id != self.job_id.get().strip():
                            self.append(f"忽略非當前 JOB 的 RESULT：{result.station}/{result.job_id}")
                            continue
                        for slot, (sn, status_value) in result.results.items():
                            expected = self.sns[slot - 1].get().strip()
                            if expected != sn:
                                self.append(f"RESULT slot{slot} SN 不符：預期 {expected}，收到 {sn}")
                            self.statuses[slot - 1].set(status_value)
                    elif line == f"ACK:{self.station.get()}:JOB={self.job_id.get().strip()}":
                        for index, status in enumerate(self.statuses):
                            if self.sns[index].get().strip():
                                status.set("TESTING")
                elif kind == "log": self.append(str(item))
                elif kind == "disconnected":
                    self.connection_status.set("TCP 已由對端中斷")
        except queue.Empty:
            pass
        self.root.after(100, self.process_events)

    def close(self) -> None:
        try:
            save_preferences(self.pref_path, Preferences(self.ip.get().strip(), int(self.port.get()), self.station.get()))
        except (OSError, ValueError):
            pass
        self.client.close(); self.root.destroy()


def main() -> int:
    root = tk.Tk(); UpperComputerApp(root).root.mainloop(); return 0


if __name__ == "__main__":
    raise SystemExit(main())
