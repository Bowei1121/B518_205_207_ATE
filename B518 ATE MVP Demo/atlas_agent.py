#!/usr/bin/env python3
"""Atlas Agent B518 ATE MVP.

The Mac never uses Accessibility, AppleScript, or synthetic input.  It only
uses USB CDC to request an Arduino HID action, then watches Atlas result files.
"""
from __future__ import annotations

import argparse
import base64
import csv
import json
import queue
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Optional

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    serial = None
    list_ports = None

try:
    import cv2
except ImportError:
    cv2 = None

VERSION = "0.1.0"
TITLE = f"Atlas Agent B518 ATE-V{VERSION}"
TIME_FOLDER = re.compile(r"^(\d{8}_\d{2}-\d{2}-\d{2})(?:\.[^/]*)?$")
# The Arduino TCP bridge deliberately transfers upper-computer payloads without
# adding a DATA: frame.  Keep the raw payload acceptance narrow enough that a
# CDC control reply (OK:, IP:, ERR:) can never accidentally start a test.
RAW_SN_BATCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}(?:\s*,\s*[A-Za-z0-9][A-Za-z0-9._-]{0,127}){0,3}$")
DEFAULT_BAUD = 115200
SCREENSHOT_SETTLE_SECONDS = 5.0
SCREENSHOT_TIMEOUT_SECONDS = 15.0
DFU_PROFILES = ("b482_dfu2", "generic", "b482_dfu1_manual")

# Dynamic PASS / FAIL / NOTSET / TESTING cells are deliberately excluded from
# every template.  They change throughout a real test and must not be used for
# window matching.
VISUAL_PROFILES = {
    "generic": {
        "window": "test_window.png", "barcode": "barcode_field.png",
        "start": "start_button.png", "input_mode": "tab",
    },
    "b482_dfu2": {
        "window": "b482/dfu2_window.png", "barcode": "b482/dfu2_sn_input.png",
        "ok": "b482/dfu2_ok.png", "window_size": (1011, 600), "input_mode": "ok_each",
    },
    "b482_bt": {
        "window": "b482/bt_window.png", "start": "b482/bt_start_all.png",
        "window_size": (1568, 727),
    },
}


class AgentError(RuntimeError):
    pass


@dataclass
class Preferences:
    port: str = ""
    csv_path: str = ""
    log_path: str = ""
    template_path: str = ""
    station: str = "DFU"
    dfu_profile: str = "b482_dfu2"
    screenshot_path: str = ""

    @classmethod
    def load(cls, path: Path) -> "Preferences":
        try:
            return cls(**json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError):
            return cls()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.__dict__, ensure_ascii=False, indent=2), encoding="utf-8")


@dataclass
class TestResult:
    sn: str
    status: str
    folder: Path
    records: Path
    detail: str = ""


def parse_barcodes(payload: str) -> list[str]:
    """Accept DATA:SN1,SN2 and plain SN1,SN2; reject malformed batches."""
    payload = payload.strip()
    if payload.upper().startswith("DATA:"):
        payload = payload[5:].strip()
    if payload.upper().startswith("SN:"):
        payload = payload[3:].strip()
    values = [part.strip() for part in payload.split(",") if part.strip()]
    if not 1 <= len(values) <= 4:
        raise AgentError("條碼數量必須為 1 至 4 個，以逗號分隔")
    if any("/" in item or "\\" in item or item in (".", "..") for item in values):
        raise AgentError("SN 不可包含路徑字元")
    return values


def incoming_barcode_payload(line: str) -> Optional[str]:
    """Return a TCP barcode payload, accepting framed or safe raw batches.

    `DATA:` and `SN:` are useful for future framed upper-computer protocols.
    The delivered Arduino firmware is intentionally transparent, therefore a
    bare comma-separated SN batch is also a valid input.  Diagnostics and HID
    acknowledgements contain a colon and consequently never match raw input.
    """
    value = line.strip()
    if value.upper().startswith(("DATA:", "SN:")):
        return value
    return value if RAW_SN_BATCH.fullmatch(value) else None


def accepted_ack(station: str, sns: Iterable[str]) -> str:
    """Immediate TCP-level acknowledgement for a validated test batch."""
    return f"ACK:ACCEPTED,{station}," + ",".join(sns)


def batch_result_report(sns: Iterable[str], statuses: dict[str, str]) -> str:
    """Create one compact RESULT line, preserving the received SN order."""
    ordered = list(sns)
    if not ordered or any(sn not in statuses for sn in ordered):
        raise AgentError("批次結果尚未完整")
    return "RESULT:" + ";".join(f"{sn},{statuses[sn]}" for sn in ordered)


def nearest_timestamp_folder(sn_dir: Path, now: Optional[datetime] = None) -> Optional[Path]:
    """Return the latest valid timestamp directory nearest to current system time."""
    if not sn_dir.is_dir():
        return None
    now = now or datetime.now()
    choices: list[tuple[float, datetime, Path]] = []
    for child in sn_dir.iterdir():
        match = TIME_FOLDER.match(child.name)
        if not child.is_dir() or not match:
            continue
        try:
            stamp = datetime.strptime(match.group(1), "%Y%m%d_%H-%M-%S")
        except ValueError:
            continue
        choices.append((abs((stamp - now).total_seconds()), stamp, child))
    # Nearest prevents stale rework selection; timestamp breaks same-distance ties.
    return min(choices, key=lambda item: (item[0], -item[1].timestamp()))[2] if choices else None


def locate_records(folder: Path) -> Optional[Path]:
    for name in ("records.csv", "record.csv"):
        candidate = folder / "system" / name
        if candidate.is_file():
            return candidate
    return None


def parse_records(records: Path) -> tuple[str, str]:
    """Any FAIL is FAIL; a non-empty complete PASS column is PASS."""
    with records.open("r", encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    if not rows or not rows[0]:
        raise AgentError("records.csv 沒有可判讀的資料")
    status_key = next((key for key in rows[0] if key and key.strip().lower() == "status"), None)
    if status_key is None:
        raise AgentError("records.csv 缺少 status 欄位")
    statuses = [str(row.get(status_key, "")).strip().upper() for row in rows]
    if any(value == "FAIL" for value in statuses):
        return "FAIL", "status 欄位含 FAIL"
    if statuses and all(value == "PASS" for value in statuses):
        return "PASS", "全部 status 為 PASS"
    return "UNKNOWN", "status 尚未完成或存在未知值"


def latest_screenshot(desktop: Path, after: float) -> Optional[Path]:
    """Find the screenshot produced by the Arduino after SCREENSHOT was sent."""
    def is_screenshot_name(path: Path) -> bool:
        normalized = re.sub(r"[ _-]", "", path.name.lower())
        return "screenshot" in normalized or "截圖" in path.name

    images = [p for p in desktop.iterdir() if p.is_file() and is_screenshot_name(p)
              and p.suffix.lower() in (".png", ".jpg", ".jpeg") and p.stat().st_mtime >= after]
    return max(images, key=lambda p: p.stat().st_mtime) if images else None


def template_match(image: Path, template: Path, threshold: float = 0.80,
                   region: Optional[tuple[int, int, int, int]] = None) -> tuple[int, int, int, int]:
    """Locate a template with OpenCV; coordinates are sent only to Arduino HID."""
    if cv2 is None:
        raise AgentError("DFU/BT 影像匹配需要 opencv-python")
    screen, needle = cv2.imread(str(image)), cv2.imread(str(template))
    if screen is None or needle is None:
        raise AgentError(f"無法讀取截圖或模板：{template}")
    offset_x = offset_y = 0
    if region:
        x, y, width, height = region
        screen = screen[y:y + height, x:x + width]
        offset_x, offset_y = x, y
    result = cv2.matchTemplate(screen, needle, cv2.TM_CCOEFF_NORMED)
    _, score, _, point = cv2.minMaxLoc(result)
    if score < threshold:
        raise AgentError(f"找不到模板 {template.name}（相似度 {score:.2f}）")
    return offset_x + point[0], offset_y + point[1], needle.shape[1], needle.shape[0]


def template_center(image: Path, template: Path, threshold: float = 0.80,
                    region: Optional[tuple[int, int, int, int]] = None) -> tuple[int, int]:
    x, y, width, height = template_match(image, template, threshold, region)
    return x + width // 2, y + height // 2


def opencv_image_to_tk_png(image) -> str:
    """Encode an OpenCV BGR image for Tk without swapping red/blue channels."""
    if cv2 is None:
        raise AgentError("顯示模板預覽需要 opencv-python")
    # cv2.imencode expects BGR, exactly the representation returned by imread.
    # Converting it to RGB first would make the PNG encoder swap the channels.
    ok, data = cv2.imencode(".png", image)
    if not ok:
        raise AgentError("無法轉換圖片")
    return base64.b64encode(data.tobytes()).decode("ascii")


class FolderMonitor(threading.Thread):
    def __init__(self, csv_root: Path, log_root: Path, sns: Iterable[str], on_log: Callable[[str], None], on_result: Callable[[TestResult], None], stop: threading.Event) -> None:
        super().__init__(daemon=True)
        self.csv_root, self.log_root, self.sns, self.on_log, self.on_result, self.stop = csv_root, log_root, list(sns), on_log, on_result, stop
        self.reported: set[Path] = set()
        self.log_positions: dict[Path, int] = {}

    def run(self) -> None:
        self.on_log("監聽已啟動：" + ", ".join(self.sns))
        while not self.stop.is_set():
            for sn in self.sns:
                folder = nearest_timestamp_folder(self.csv_root / sn)
                if folder is None:
                    continue
                # Separate log roots are supported, but the CSV folder name is
                # retained so log and result always represent the same run.
                log_file = self.log_root / sn / folder.name / "system" / "device.log"
                if not log_file.is_file(): log_file = folder / "system" / "device.log"
                self._render_log(log_file)
                records = locate_records(folder)
                if records and records not in self.reported:
                    try:
                        status, detail = parse_records(records)
                    except (OSError, AgentError) as exc:
                        self.on_log(f"{sn}: CSV 尚未可讀取：{exc}")
                        continue
                    if status != "UNKNOWN":
                        self.reported.add(records)
                        self.on_result(TestResult(sn, status, folder, records, detail))
            # Polling is deliberately permission-free and has no FSEvents setup.
            if self.stop.wait(0.25):
                break

    def _render_log(self, log_file: Path) -> None:
        try:
            size = log_file.stat().st_size
            offset = self.log_positions.get(log_file, 0)
            if size < offset:
                offset = 0
            if size <= offset:
                return
            with log_file.open("r", encoding="utf-8", errors="replace") as source:
                source.seek(offset)
                content = source.read()
                self.log_positions[log_file] = source.tell()
            if content:
                self.on_log(content.rstrip())
        except OSError:
            pass


class SerialLineFramer:
    """Accumulate a stream into newline-delimited CDC messages.

    USB CDC and TCP preserve bytes, not application messages.  CRLF is the
    documented wire terminator; accepting LF too keeps ordinary serial tools
    compatible.  Waiting for the line ending prevents a TCP fragment such as
    ``SN001,SN`` from becoming a false batch.
    """
    def __init__(self, maximum: int = 1024) -> None:
        self.maximum = maximum
        self.buffer = bytearray()

    def feed(self, raw: bytes) -> list[str]:
        self.buffer.extend(raw)
        messages: list[str] = []
        while b"\n" in self.buffer:
            end = self.buffer.index(b"\n")
            line = bytes(self.buffer[:end]).rstrip(b"\r")
            del self.buffer[:end + 1]
            if line:
                messages.append(line.decode("utf-8", errors="replace"))
        if len(self.buffer) > self.maximum:
            self.buffer.clear()
            messages.append("ERR: CDC 訊框超過長度上限，已丟棄")
        return messages


class SerialLink:
    def __init__(self, on_line: Callable[[str], None]) -> None:
        self.connection = None
        self.on_line = on_line
        self.stop = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.lock = threading.Lock()

    def connect(self, port: str) -> None:
        if serial is None:
            raise AgentError("缺少 pyserial；請執行 python3 -m pip install -r requirements.txt")
        self.close()
        self.connection = serial.Serial(port, DEFAULT_BAUD, timeout=0.2)
        self.connection.reset_input_buffer()
        self.stop.clear()
        self.thread = threading.Thread(target=self._receive, daemon=True)
        self.thread.start()

    def _receive(self) -> None:
        framer = SerialLineFramer()
        while not self.stop.is_set() and self.connection:
            try:
                raw = self.connection.read(256)
                if raw:
                    for line in framer.feed(raw):
                        self.on_line(line)
            except Exception as exc:
                self.on_line(f"ERR: USB CDC 中斷：{exc}")
                return

    def send(self, command: str) -> None:
        if not self.connection:
            raise AgentError("尚未連線 Arduino")
        with self.lock:
            # CRLF lets LabVIEW use its built-in TCP "CRLF terminated" mode.
            # The Arduino also accepts LF-only input for terminal compatibility.
            self.connection.write((command.rstrip("\r\n") + "\r\n").encode("utf-8"))
            self.connection.flush()

    def close(self) -> None:
        self.stop.set()
        if self.connection:
            self.connection.close()
        self.connection = None


class TemplateMakerDialog:
    """Crop a repeatable OpenCV template from a screenshot without extra GUI libs."""
    MAX_WIDTH, MAX_HEIGHT = 900, 520

    def __init__(self, parent: tk.Tk, template_root: Path, screenshot_root: Path) -> None:
        self.window = tk.Toplevel(parent)
        self.window.title("製作圖像匹配模板")
        self.window.transient(parent)
        self.template_root, self.screenshot_root = template_root, screenshot_root
        self.image_path: Optional[Path] = None
        self.original = None
        self.scale = 1.0
        self.start: Optional[tuple[int, int]] = None
        self.selection: Optional[tuple[int, int, int, int]] = None
        self.photo = None
        controls = ttk.Frame(self.window, padding=10); controls.pack(fill="x")
        ttk.Button(controls, text="選擇截圖", command=self.choose_image).pack(side="left")
        ttk.Button(controls, text="使用最新截圖", command=self.use_latest).pack(side="left", padx=5)
        ttk.Label(controls, text="模板檔名：").pack(side="left", padx=(12, 0))
        self.name = tk.StringVar(value="test_window.png")
        ttk.Entry(controls, textvariable=self.name, width=32).pack(side="left", fill="x", expand=True)
        self.canvas = tk.Canvas(self.window, width=self.MAX_WIDTH, height=self.MAX_HEIGHT, bg="#333", cursor="crosshair")
        self.canvas.pack(padx=10, pady=(0, 5))
        self.canvas.bind("<ButtonPress-1>", self.begin)
        self.canvas.bind("<B1-Motion>", self.drag)
        self.canvas.bind("<ButtonRelease-1>", self.end)
        self.info = tk.StringVar(value="選擇截圖後，以滑鼠拖曳框選模板區域。")
        ttk.Label(self.window, textvariable=self.info).pack(padx=10, anchor="w")
        footer = ttk.Frame(self.window, padding=10); footer.pack(fill="x")
        ttk.Button(footer, text="儲存模板", command=self.save).pack(side="right")
        ttk.Button(footer, text="取消", command=self.window.destroy).pack(side="right", padx=5)

    def choose_image(self) -> None:
        selected = filedialog.askopenfilename(parent=self.window, initialdir=str(self.screenshot_root),
                                               filetypes=[("Images", "*.png *.jpg *.jpeg"), ("All files", "*")])
        if selected: self.load(Path(selected))

    def use_latest(self) -> None:
        try:
            candidates = [item for item in self.screenshot_root.iterdir() if item.is_file() and item.suffix.lower() in (".png", ".jpg", ".jpeg")]
            if not candidates: raise AgentError("截圖資料夾內沒有 PNG／JPG 圖片")
            self.load(max(candidates, key=lambda item: item.stat().st_mtime))
        except OSError as exc:
            messagebox.showerror(TITLE, f"無法讀取截圖資料夾：{exc}", parent=self.window)
        except AgentError as exc:
            messagebox.showerror(TITLE, str(exc), parent=self.window)

    def load(self, path: Path) -> None:
        if cv2 is None:
            messagebox.showerror(TITLE, "製作模板需要 opencv-python", parent=self.window); return
        image = cv2.imread(str(path))
        if image is None:
            messagebox.showerror(TITLE, "無法讀取圖片", parent=self.window); return
        self.image_path, self.original = path, image
        height, width = image.shape[:2]
        self.scale = min(self.MAX_WIDTH / width, self.MAX_HEIGHT / height, 1.0)
        shown = cv2.resize(image, (round(width * self.scale), round(height * self.scale))) if self.scale != 1 else image
        try:
            self.photo = tk.PhotoImage(data=opencv_image_to_tk_png(shown))
        except AgentError as exc:
            messagebox.showerror(TITLE, str(exc), parent=self.window); return
        self.canvas.delete("all"); self.canvas.config(width=shown.shape[1], height=shown.shape[0])
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw", tags="image")
        self.selection = None; self.info.set(f"{path.name}；請拖曳框選區域。")

    def begin(self, event: tk.Event) -> None:
        if self.original is None: return
        self.start = (event.x, event.y); self.canvas.delete("selection")

    def drag(self, event: tk.Event) -> None:
        if self.start is None: return
        self.canvas.delete("selection")
        self.canvas.create_rectangle(*self.start, event.x, event.y, outline="#ff2d2d", width=2, tags="selection")

    def end(self, event: tk.Event) -> None:
        if self.start is None: return
        x1, y1 = self.start; x2, y2 = event.x, event.y; self.start = None
        left, right = sorted((max(0, x1), min(self.canvas.winfo_width(), x2)))
        top, bottom = sorted((max(0, y1), min(self.canvas.winfo_height(), y2)))
        if right - left < 8 or bottom - top < 8:
            self.selection = None; self.info.set("選取範圍太小，請重新框選。 "); return
        self.selection = (round(left / self.scale), round(top / self.scale), round(right / self.scale), round(bottom / self.scale))
        self.info.set(f"已選取原圖 {self.selection[2]-self.selection[0]} × {self.selection[3]-self.selection[1]} px")

    def save(self) -> None:
        if self.original is None or self.selection is None:
            messagebox.showerror(TITLE, "請先選擇截圖並框選模板區域。", parent=self.window); return
        name = self.name.get().strip().replace("\\", "/")
        if not name.endswith(".png") or name.startswith("/") or ".." in Path(name).parts:
            messagebox.showerror(TITLE, "模板檔名需為相對 .png 路徑，例如 b482/dfu2_ok.png。", parent=self.window); return
        x1, y1, x2, y2 = self.selection
        crop = self.original[y1:y2, x1:x2]
        target = self.template_root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(target), crop):
            messagebox.showerror(TITLE, "無法儲存模板。", parent=self.window); return
        self.info.set(f"已儲存：{target}"); messagebox.showinfo(TITLE, f"模板已儲存：\n{target}", parent=self.window)


class AtlasAgentApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(TITLE)
        self.root.geometry("940x650")
        self.pref_file = Path.home() / "Library" / "Application Support" / "AtlasAgentB518" / "preferences.json"
        pref = Preferences.load(self.pref_file)
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.link = SerialLink(lambda line: self.events.put(("serial", line)))
        self.monitor_stop = threading.Event()
        self.monitor: Optional[FolderMonitor] = None
        self.sns: list[str] = []
        self.batch_number = 0
        self.batch_results: dict[str, str] = {}
        self.reported_batch_number: Optional[int] = None
        self.port = tk.StringVar(value=pref.port)
        self.csv_path = tk.StringVar(value=pref.csv_path)
        self.log_path = tk.StringVar(value=pref.log_path)
        self.template_path = tk.StringVar(value=pref.template_path or str(Path(__file__).with_name("templates")))
        self.screenshot_path = tk.StringVar(value=pref.screenshot_path or str(Path.home() / "Desktop"))
        self.station = tk.StringVar(value=pref.station if pref.station in ("DFU", "FCT", "BT") else "DFU")
        self.dfu_profile = tk.StringVar(value=pref.dfu_profile if pref.dfu_profile in DFU_PROFILES else "b482_dfu2")
        self.sn_text = tk.StringVar()
        self.ip_text = tk.StringVar()
        self._build()
        self.refresh_ports()
        self.root.after(100, self.process_events)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _build(self) -> None:
        panel = ttk.Frame(self.root, padding=12); panel.pack(fill="both", expand=True)
        top = ttk.Frame(panel); top.pack(fill="x")
        ttk.Label(top, text="工站：").pack(side="left")
        ttk.Combobox(top, textvariable=self.station, values=("DFU", "FCT", "BT"), width=8, state="readonly").pack(side="left")
        ttk.Label(top, text="  USB CDC：").pack(side="left")
        self.port_menu = ttk.Combobox(top, textvariable=self.port, width=35)
        self.port_menu.pack(side="left", fill="x", expand=True)
        ttk.Button(top, text="重新掃描", command=self.refresh_ports).pack(side="left", padx=4)
        ttk.Button(top, text="連線", command=self.connect).pack(side="left")
        ttk.Button(top, text="中斷", command=self.link.close).pack(side="left", padx=(4, 0))
        for label, variable in (("CSV 根路徑：", self.csv_path), ("Log 根路徑（選填）：", self.log_path)):
            row = ttk.Frame(panel); row.pack(fill="x", pady=(8, 0))
            ttk.Label(row, text=label).pack(side="left")
            ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True)
            ttk.Button(row, text="選擇", command=lambda v=variable: self.choose_dir(v)).pack(side="left", padx=(4, 0))
        row = ttk.Frame(panel); row.pack(fill="x", pady=(8, 0))
        ttk.Label(row, text="OpenCV 模板路徑：").pack(side="left")
        ttk.Entry(row, textvariable=self.template_path).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="選擇", command=lambda: self.choose_dir(self.template_path)).pack(side="left", padx=(4, 0))
        ttk.Button(row, text="製作模板", command=self.open_template_maker).pack(side="left", padx=(4, 0))
        row = ttk.Frame(panel); row.pack(fill="x", pady=(8, 0))
        ttk.Label(row, text="螢幕截圖路徑：").pack(side="left")
        ttk.Entry(row, textvariable=self.screenshot_path).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="選擇", command=lambda: self.choose_dir(self.screenshot_path)).pack(side="left", padx=(4, 0))
        profile = ttk.Frame(panel); profile.pack(fill="x", pady=(8, 0))
        ttk.Label(profile, text="DFU 畫面設定：").pack(side="left")
        ttk.Combobox(profile, textvariable=self.dfu_profile, width=30, state="readonly",
                     values=("b482_dfu2", "generic", "b482_dfu1_manual")).pack(side="left")
        ttk.Label(profile, text="  B482 DFU_2：每個 SN 輸入後按 OK；DFU_1 尚待確認輸入步驟。").pack(side="left")
        batch = ttk.LabelFrame(panel, text="當前測試條碼（由 Arduino TCP→USB CDC 收到；也可手動驗證）", padding=8); batch.pack(fill="x", pady=10)
        ttk.Entry(batch, textvariable=self.sn_text).pack(side="left", fill="x", expand=True)
        ttk.Button(batch, text="開始流程", command=lambda: self.start_batch(self.sn_text.get())).pack(side="left", padx=(5, 0))
        ttk.Button(batch, text="停止監聽", command=self.stop_monitor).pack(side="left", padx=(5, 0))
        self.sn_display = ttk.Label(panel, text="尚無測試中的 SN", anchor="w"); self.sn_display.pack(fill="x")
        ip = ttk.LabelFrame(panel, text="Arduino 網路設定", padding=8); ip.pack(fill="x", pady=10)
        ttk.Label(ip, textvariable=self.ip_text).pack(side="left", fill="x", expand=True)
        ttk.Button(ip, text="查詢 IP", command=lambda: self.safe_send("GET_IP")).pack(side="left")
        ttk.Button(ip, text="修改 IP", command=self.change_ip).pack(side="left", padx=(5, 0))
        ttk.Label(panel, text="即時 device.log / 通訊紀錄：").pack(anchor="w")
        self.output = tk.Text(panel, height=22, wrap="word", state="disabled")
        self.output.pack(fill="both", expand=True)

    def refresh_ports(self) -> None:
        ports = [item.device for item in list_ports.comports()] if list_ports else []
        self.port_menu["values"] = ports
        if not self.port.get() and len(ports) == 1: self.port.set(ports[0])

    def choose_dir(self, variable: tk.StringVar) -> None:
        selected = filedialog.askdirectory(initialdir=variable.get() or str(Path.home()))
        if selected: variable.set(selected)

    def open_template_maker(self) -> None:
        template_root = Path(self.template_path.get()).expanduser()
        screenshot_root = Path(self.screenshot_path.get()).expanduser()
        if not screenshot_root.is_dir():
            messagebox.showerror(TITLE, "請先選擇有效的螢幕截圖路徑"); return
        TemplateMakerDialog(self.root, template_root, screenshot_root)

    def append(self, text: str) -> None:
        self.output.configure(state="normal"); self.output.insert("end", text + "\n"); self.output.see("end"); self.output.configure(state="disabled")

    def connect(self) -> None:
        try:
            self.link.connect(self.port.get().strip()); self.append("USB CDC 已連線")
        except (AgentError, OSError) as exc: messagebox.showerror(TITLE, str(exc))

    def safe_send(self, command: str) -> None:
        try: self.link.send(command); self.append("TX: " + command)
        except AgentError as exc: messagebox.showerror(TITLE, str(exc))

    def start_batch(self, payload: str) -> Optional[list[str]]:
        try:
            root = Path(self.csv_path.get()).expanduser()
            if not root.is_dir(): raise AgentError("請選擇有效的 CSV 根路徑")
            sns = parse_barcodes(payload)
        except AgentError as exc:
            messagebox.showerror(TITLE, str(exc)); return None
        self.stop_monitor(); self.sns = sns; self.batch_results = {}; self.reported_batch_number = None
        self.sn_display.configure(text="當前 SN：" + "、".join(sns))
        self.batch_number += 1
        batch_number = self.batch_number
        if self.station.get() in ("DFU", "BT"):
            threading.Thread(target=self.visual_start, args=(self.station.get(), sns, root, batch_number), daemon=True).start()
        else:
            self.start_monitor(root, sns, batch_number)
        return sns

    def start_monitor(self, root: Path, sns: list[str], batch_number: int) -> None:
        self.monitor_stop = threading.Event()
        log_root = Path(self.log_path.get()).expanduser()
        if not log_root.is_dir(): log_root = root
        self.monitor = FolderMonitor(root, log_root, sns, lambda item: self.events.put(("log", item)),
                                     lambda result: self.events.put(("result", (batch_number, result))), self.monitor_stop)
        self.monitor.start()

    def visual_start(self, station: str, sns: list[str], csv_root: Path, batch_number: int) -> None:
        """Ask Arduino HID for screenshot/actions; no Mac input API is invoked here."""
        try:
            before = time.time(); self.link.send("SCREENSHOT")
            screenshot_dir = Path(self.screenshot_path.get()).expanduser()
            if not screenshot_dir.is_dir(): raise AgentError("請選擇有效的螢幕截圖路徑")
            self.events.put(("log", f"等待 {SCREENSHOT_SETTLE_SECONDS:g} 秒讓 macOS 完成儲存螢幕截圖…"))
            time.sleep(SCREENSHOT_SETTLE_SECONDS)
            deadline = time.monotonic() + (SCREENSHOT_TIMEOUT_SECONDS - SCREENSHOT_SETTLE_SECONDS)
            shot = None
            while time.monotonic() < deadline and shot is None:
                shot = latest_screenshot(screenshot_dir, before); time.sleep(.25)
            if shot is None: raise AgentError(f"等待 Arduino 產生螢幕截圖逾時（共 {SCREENSHOT_TIMEOUT_SECONDS:g} 秒）")
            if station == "DFU" and self.dfu_profile.get() == "b482_dfu1_manual":
                raise AgentError("B482 DFU_1 畫面尚未確認 SN 輸入方式；請選擇 b482_dfu2 或 generic")
            profile = VISUAL_PROFILES[self.dfu_profile.get() if station == "DFU" else "b482_bt"]
            templates = Path(self.template_path.get()).expanduser()
            window = templates / profile["window"]
            window_rect = template_match(shot, window)
            window_center = (window_rect[0] + window_rect[2] // 2, window_rect[1] + window_rect[3] // 2)
            # Template matching inside the window prevents matching a stale/other app control.
            if "window_size" in profile:
                width, height = profile["window_size"]
                region = (window_rect[0], window_rect[1], width, height)
            else:
                region = window_rect
            if station == "DFU":
                barcode = template_center(shot, templates / profile["barcode"], region=region)
                if profile["input_mode"] == "ok_each":
                    button = template_center(shot, templates / profile["ok"], region=region)
                    for sn in sns:
                        self.link.send(f"M_MOVE:{barcode[0]},{barcode[1]}")
                        self.link.send("M_CLICK:L")
                        self.link.send("K_WRITE:" + sn)
                        self.link.send(f"M_MOVE:{button[0]},{button[1]}")
                        self.link.send("M_CLICK:L")
                    self.events.put(("log", f"DFU：視窗定位 {window_center}，SN 欄位 {barcode}，OK {button}；啟動監聽"))
                else:
                    self.link.send(f"M_MOVE:{barcode[0]},{barcode[1]}")
                    self.link.send("M_CLICK:L")
                    for index, sn in enumerate(sns):
                        self.link.send("K_WRITE:" + sn)
                        if index < len(sns) - 1:
                            self.link.send("K_KEY:TAB")
                    button = template_center(shot, templates / profile["start"], region=region)
                    self.link.send(f"M_MOVE:{button[0]},{button[1]}")
                    self.link.send("M_CLICK:L")
                    self.events.put(("log", f"DFU：視窗定位 {window_center}，開始按鈕 {button}；啟動監聽"))
            else:
                button = template_center(shot, templates / profile["start"], region=region)
                self.link.send(f"M_MOVE:{button[0]},{button[1]}")
                self.link.send("M_CLICK:L")
                self.events.put(("log", f"BT：視窗定位 {window_center}，Start All {button}；啟動監聽"))
            self.events.put(("begin_monitor", (csv_root, sns, batch_number)))
        except Exception as exc:
            self.events.put(("log", f"{station} 影像流程失敗：{exc}"))
            self.events.put(("start_failed", (station, batch_number)))

    def stop_monitor(self) -> None:
        self.monitor_stop.set(); self.monitor = None

    def change_ip(self) -> None:
        value = simpledialog.askstring(TITLE, "新 Arduino IPv4 位址：", parent=self.root)
        if value:
            parts = value.split(".")
            if len(parts) != 4 or any(not p.isdigit() or not 0 <= int(p) <= 255 for p in parts):
                messagebox.showerror(TITLE, "IPv4 格式不正確"); return
            self.safe_send("NET_SET:" + value)

    def process_events(self) -> None:
        try:
            while True:
                kind, item = self.events.get_nowait()
                if kind == "serial":
                    line = str(item); self.append("RX: " + line)
                    payload = incoming_barcode_payload(line)
                    if payload is not None:
                        try:
                            sns = self.start_batch(payload)
                            if sns:
                                self.safe_send(accepted_ack(self.station.get(), sns))
                            else:
                                self.safe_send("NACK:REJECTED")
                        except Exception as exc: self.append("ERR: 無法啟動批次：" + str(exc))
                    elif line.startswith("IP:") or "IP=" in line: self.ip_text.set(line)
                elif kind == "log": self.append(str(item))
                elif kind == "begin_monitor":
                    root, sns, batch_number = item
                    if batch_number == self.batch_number:
                        self.start_monitor(root, sns, batch_number)
                    else:
                        self.append("略過已被新批次取代的影像流程")
                elif kind == "start_failed":
                    station, batch_number = item
                    if batch_number == self.batch_number and self.link.connection:
                        self.safe_send(f"NACK:START_FAILED,{station}")
                elif kind == "result":
                    batch_number, result = item; assert isinstance(result, TestResult)
                    if batch_number != self.batch_number:
                        self.append(f"略過舊批次結果：{result.sn}")
                        continue
                    self.append(f"{result.sn}: {result.status} — {result.detail}")
                    self.batch_results[result.sn] = result.status
                    if self.reported_batch_number != batch_number and all(sn in self.batch_results for sn in self.sns):
                        report = batch_result_report(self.sns, self.batch_results)
                        self.reported_batch_number = batch_number
                        if self.link.connection:
                            self.safe_send(report)
                        else:
                            self.append("未連線 Arduino，略過上報：" + report)
        except queue.Empty: pass
        self.root.after(100, self.process_events)

    def close(self) -> None:
        Preferences(port=self.port.get(), csv_path=self.csv_path.get(), log_path=self.log_path.get(),
                    template_path=self.template_path.get(), station=self.station.get(),
                    dfu_profile=self.dfu_profile.get(), screenshot_path=self.screenshot_path.get()).save(self.pref_file)
        self.stop_monitor(); self.link.close(); self.root.destroy()


def main() -> int:
    parser = argparse.ArgumentParser(description=TITLE); parser.add_argument("--version", action="version", version=TITLE); parser.parse_args()
    root = tk.Tk(); AtlasAgentApp(root).root.mainloop(); return 0


if __name__ == "__main__": raise SystemExit(main())
