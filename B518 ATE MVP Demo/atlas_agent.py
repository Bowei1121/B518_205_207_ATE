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
import struct
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

try:
    import AppKit
except ImportError:
    AppKit = None

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
    hid_delay: float = 0.5
    hid_scale_x: float = 1.0
    hid_scale_y: float = 1.0
    hid_offset_x: float = 0.0
    hid_offset_y: float = 0.0
    hid_mode: str = "relative"
    absolute_width: int = 1440
    absolute_height: int = 900
    auto_scale: bool = True

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


def batch_result_report(sns: Iterable[str], statuses: dict[str, str]) -> str:
    """Create one compact RESULT line, preserving the received SN order."""
    ordered = list(sns)
    if not ordered or any(sn not in statuses for sn in ordered):
        raise AgentError("批次結果尚未完整")
    return "RESULT:" + ";".join(f"{sn},{statuses[sn]}" for sn in ordered)


def dfu_ok_each_commands(sns: Iterable[str], barcode: tuple[int, int], button: tuple[int, int],
                         mode: str = "relative") -> list[str]:
    """Build DFU_2 HID commands, resetting the relative mouse before every target."""
    commands: list[str] = []
    for sn in sns:
        commands.extend(click_commands(barcode, mode) + [f"K_WRITE:{sn}"] + click_commands(button, mode))
    return commands


def absolute_click_commands(target: tuple[int, int]) -> list[str]:
    """Move from the top-left origin to a screen coordinate and left click."""
    return ["M_RESET", f"M_MOVE:{target[0]},{target[1]}", "M_CLICK:L"]


def click_commands(target: tuple[int, int], mode: str) -> list[str]:
    if mode == "absolute":
        return [f"M_ABS:{target[0]},{target[1]}", "M_ABS_CLICK:L"]
    return absolute_click_commands(target)


def hid_success_reply(command: str) -> str:
    """Map an Agent HID command to the Arduino completion reply."""
    if command.startswith("M_CLICK:") or command.startswith("M_ABS_CLICK:") or command.startswith("K_KEY:"):
        return "OK:" + command
    if command == "M_RESET":
        return "OK:M_RESET"
    return "OK:" + command.split(":", 1)[0]


def resolve_template_path(template_root: Path, required_name: str) -> Path:
    """Use the documented subfolder first, then support older root-level templates."""
    expected = template_root / required_name
    if expected.is_file():
        return expected
    root_level = template_root / Path(required_name).name
    return root_level if root_level.is_file() else expected


def hid_coordinate(point: tuple[int, int], scale_x: float, scale_y: float,
                   offset_x: float = 0.0, offset_y: float = 0.0) -> tuple[int, int]:
    """Convert screenshot pixels to Arduino HID screen coordinates."""
    if scale_x <= 0 or scale_y <= 0:
        raise AgentError("HID X／Y 比例必須大於 0")
    return round(point[0] * scale_x + offset_x), round(point[1] * scale_y + offset_y)


def absolute_hid_report_coordinate(point: tuple[int, int], width: int, height: int) -> tuple[int, int]:
    """Map a logical virtual-desktop point to the 16-bit absolute HID range."""
    if width < 2 or height < 2:
        raise AgentError("絕對 HID 虛擬桌面寬高必須至少為 2")
    x, y = point
    if not 0 <= x < width or not 0 <= y < height:
        raise AgentError(f"絕對 HID 座標 {point} 超出虛擬桌面 {width}×{height}；請調整比例、偏移或桌面寬高")
    return round(x * 32767 / (width - 1)), round(y * 32767 / (height - 1))


def screenshot_scale_for_displays(pixel_size: tuple[int, int],
                                  displays: Iterable[tuple[float, float, float]]) -> Optional[tuple[float, float]]:
    """Find a display whose logical size × backing scale equals a screenshot."""
    pixel_width, pixel_height = pixel_size
    for logical_width, logical_height, backing_scale in displays:
        expected_width = round(logical_width * backing_scale)
        expected_height = round(logical_height * backing_scale)
        if abs(expected_width - pixel_width) <= 2 and abs(expected_height - pixel_height) <= 2:
            return logical_width / pixel_width, logical_height / pixel_height
    return None


def png_retina_scale(image_path: Path) -> Optional[tuple[float, float]]:
    """Read a macOS PNG pHYs chunk; ScreenShot PNGs normally encode 72/144 DPI."""
    try:
        with image_path.open("rb") as source:
            if source.read(8) != b"\x89PNG\r\n\x1a\n":
                return None
            while True:
                length_data = source.read(4)
                if len(length_data) != 4:
                    return None
                length = struct.unpack(">I", length_data)[0]
                kind = source.read(4)
                data = source.read(length)
                source.read(4)  # CRC
                if kind == b"pHYs" and len(data) == 9 and data[8] == 1:
                    pixels_x, pixels_y = struct.unpack(">II", data[:8])
                    dpi_x, dpi_y = pixels_x * .0254, pixels_y * .0254
                    if dpi_x > 0 and dpi_y > 0:
                        return 72 / dpi_x, 72 / dpi_y
                if kind == b"IDAT":
                    return None
    except OSError:
        return None


def macos_screenshot_scale(image_path: Path) -> Optional[tuple[float, float]]:
    """Derive Retina/non-Retina pixel-to-logical scale for a screenshot's display."""
    if cv2 is None or AppKit is None:
        return None
    image = cv2.imread(str(image_path))
    if image is None:
        return None
    height, width = image.shape[:2]
    displays = []
    for screen in AppKit.NSScreen.screens():
        frame = screen.frame()
        displays.append((float(frame.size.width), float(frame.size.height), float(screen.backingScaleFactor())))
    return screenshot_scale_for_displays((width, height), displays) or png_retina_scale(image_path)


def rectangle_center(rectangle: tuple[int, int, int, int]) -> tuple[int, int]:
    x, y, width, height = rectangle
    return x + width // 2, y + height // 2


def write_match_overlay(image_path: Path, matches: Iterable[tuple[str, tuple[int, int, int, int], tuple[int, int]]],
                        output_path: Path) -> Path:
    """Save a diagnostic image with OpenCV match boxes and converted HID points."""
    if cv2 is None:
        raise AgentError("製作匹配疊圖需要 opencv-python")
    image = cv2.imread(str(image_path))
    if image is None:
        raise AgentError(f"無法讀取截圖：{image_path}")
    for label, (x, y, width, height), hid_point in matches:
        cv2.rectangle(image, (x, y), (x + width, y + height), (0, 255, 0), 3)
        center = (x + width // 2, y + height // 2)
        cv2.drawMarker(image, center, (0, 0, 255), cv2.MARKER_CROSS, 28, 2)
        text = f"{label} px={center[0]},{center[1]} target={hid_point[0]},{hid_point[1]}"
        cv2.putText(image, text, (x, max(24, y - 8)), cv2.FONT_HERSHEY_SIMPLEX, .65, (0, 0, 255), 2, cv2.LINE_AA)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_path), image):
        raise AgentError(f"無法儲存匹配疊圖：{output_path}")
    return output_path


def write_local_demo_results(csv_root: Path, sns: Iterable[str], station: str, fail_last: bool,
                             stop: threading.Event, delay: float = 0.75) -> list[Path]:
    """Create Atlas-shaped result files for a no-hardware local demonstration."""
    serials = list(sns)
    systems: list[tuple[str, Path]] = []
    for index, sn in enumerate(serials, start=1):
        stamp = datetime.now().strftime("%Y%m%d_%H-%M-%S")
        system = csv_root / sn / f"{stamp}.LOCALDEMO{index:02d}" / "system"
        system.mkdir(parents=True, exist_ok=True)
        (system / "device.log").write_text(f"{station} local demo started for {sn}\nTESTING\n", encoding="utf-8")
        systems.append((sn, system))
    if stop.wait(delay):
        return []
    records: list[Path] = []
    for index, (sn, system) in enumerate(systems, start=1):
        status = "FAIL" if fail_last and index == len(systems) else "PASS"
        record = system / "records.csv"
        with record.open("w", encoding="utf-8", newline="") as source:
            csv.writer(source).writerows([["test", "status"], [f"{station}_LOCAL_DEMO", status]])
        with (system / "device.log").open("a", encoding="utf-8") as source:
            source.write(f"TEST COMPLETE: {status}\n")
        records.append(record)
    return records


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


def new_screenshots(desktop: Path, after: float) -> list[Path]:
    """Find all post-command screenshots, including every macOS display."""
    def is_screenshot_name(path: Path) -> bool:
        normalized = re.sub(r"[ _-]", "", path.name.lower())
        return "screenshot" in normalized or "截圖" in path.name

    images = [p for p in desktop.iterdir() if p.is_file() and is_screenshot_name(p)
              and p.suffix.lower() in (".png", ".jpg", ".jpeg") and p.stat().st_mtime >= after]
    return sorted(images, key=lambda p: p.stat().st_mtime, reverse=True)


def latest_screenshot(desktop: Path, after: float) -> Optional[Path]:
    """Compatibility helper that returns the newest candidate only."""
    candidates = new_screenshots(desktop, after)
    return candidates[0] if candidates else None


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
    screen_height, screen_width = screen.shape[:2]
    needle_height, needle_width = needle.shape[:2]
    if not screen_width or not screen_height or needle_width > screen_width or needle_height > screen_height:
        raise AgentError(f"模板 {template.name} 尺寸 {needle_width}×{needle_height} 大於搜尋區域 "
                         f"{screen_width}×{screen_height}；請裁小模板或調整螢幕／模板解析度")
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


def preview_geometry(image_width: int, image_height: int, viewport_width: int, viewport_height: int) -> tuple[float, int, int]:
    """Fit a preview inside a bounded Tk canvas; never upscale source pixels."""
    if min(image_width, image_height, viewport_width, viewport_height) <= 0:
        raise AgentError("影像或預覽尺寸無效")
    scale = min(viewport_width / image_width, viewport_height / image_height, 1.0)
    return scale, max(1, round(image_width * scale)), max(1, round(image_height * scale))


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
    PREVIEW_SIZES = ((700, 400), (900, 520), (1200, 700))
    MAX_SOURCE_PIXELS = 24_000_000

    def __init__(self, parent: tk.Tk, template_root: Path, screenshot_root: Path,
                 suggested_names: Iterable[str] = ("test_window.png",)) -> None:
        self.window = tk.Toplevel(parent)
        self.window.title("製作圖像匹配模板")
        self.window.transient(parent)
        # macOS 15's Tk/AppKit path can abort while native window zoom creates
        # a new focus surface. Use bounded in-app preview sizes instead.
        self.window.resizable(False, False)
        self.template_root, self.screenshot_root = template_root, screenshot_root
        self.suggested_names = list(suggested_names) or ["test_window.png"]
        self.image_path: Optional[Path] = None
        self.original = None
        self.scale = 1.0
        self.preview_index = 1
        self.shown_width = self.shown_height = 0
        self.start: Optional[tuple[int, int]] = None
        self.selection: Optional[tuple[int, int, int, int]] = None
        self.photo = None
        controls = ttk.Frame(self.window, padding=10); controls.pack(fill="x")
        ttk.Button(controls, text="選擇截圖", command=self.choose_image).pack(side="left")
        ttk.Button(controls, text="使用最新截圖", command=self.use_latest).pack(side="left", padx=5)
        ttk.Button(controls, text="縮小預覽", command=lambda: self.change_preview_size(-1)).pack(side="left", padx=(10, 0))
        ttk.Button(controls, text="放大預覽", command=lambda: self.change_preview_size(1)).pack(side="left", padx=5)
        ttk.Label(controls, text="模板檔名：").pack(side="left", padx=(12, 0))
        self.name = tk.StringVar(value=self.suggested_names[0])
        ttk.Combobox(controls, textvariable=self.name, values=self.suggested_names,
                     width=32).pack(side="left", fill="x", expand=True)
        width, height = self.PREVIEW_SIZES[self.preview_index]
        self.canvas = tk.Canvas(self.window, width=width, height=height, bg="#333", cursor="crosshair", highlightthickness=0)
        self.canvas.pack(padx=10, pady=(0, 5))
        self.canvas.bind("<ButtonPress-1>", self.begin)
        self.canvas.bind("<B1-Motion>", self.drag)
        self.canvas.bind("<ButtonRelease-1>", self.end)
        self.info = tk.StringVar(value="選擇截圖後，以滑鼠拖曳框選模板區域；請使用本視窗的「放大預覽」。")
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
        height, width = image.shape[:2]
        if width * height > self.MAX_SOURCE_PIXELS:
            messagebox.showerror(TITLE, "截圖過大，請先縮小至 2400 萬像素以下再製作模板。", parent=self.window); return
        self.image_path, self.original = path, image
        self.selection = None
        self.render_preview()

    def change_preview_size(self, direction: int) -> None:
        target = max(0, min(len(self.PREVIEW_SIZES) - 1, self.preview_index + direction))
        if target == self.preview_index:
            return
        self.preview_index = target
        if self.original is not None:
            self.selection = None
            self.render_preview()

    def render_preview(self) -> None:
        assert self.original is not None
        height, width = self.original.shape[:2]
        viewport_width, viewport_height = self.PREVIEW_SIZES[self.preview_index]
        self.scale, self.shown_width, self.shown_height = preview_geometry(width, height, viewport_width, viewport_height)
        shown = cv2.resize(self.original, (self.shown_width, self.shown_height), interpolation=cv2.INTER_AREA) if self.scale != 1 else self.original
        # Delete the native image before creating the next one; repeated loads
        # must not leave AppKit image surfaces allocated.
        self.canvas.delete("all")
        self.photo = None
        self.canvas.config(width=viewport_width, height=viewport_height)
        try:
            self.photo = tk.PhotoImage(data=opencv_image_to_tk_png(shown))
        except (AgentError, tk.TclError) as exc:
            messagebox.showerror(TITLE, str(exc), parent=self.window); return
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw", tags="image")
        self.info.set(f"{self.image_path.name}；預覽 {self.shown_width} × {self.shown_height} px；請拖曳框選區域。")

    def clamp_to_image(self, event: tk.Event) -> tuple[int, int]:
        return min(max(event.x, 0), self.shown_width), min(max(event.y, 0), self.shown_height)

    def begin(self, event: tk.Event) -> None:
        if self.original is None: return
        if not (0 <= event.x <= self.shown_width and 0 <= event.y <= self.shown_height):
            return
        self.start = self.clamp_to_image(event); self.canvas.delete("selection")

    def drag(self, event: tk.Event) -> None:
        if self.start is None: return
        x, y = self.clamp_to_image(event)
        self.canvas.delete("selection")
        self.canvas.create_rectangle(*self.start, x, y, outline="#ff2d2d", width=2, tags="selection")

    def end(self, event: tk.Event) -> None:
        if self.start is None: return
        x1, y1 = self.start; x2, y2 = self.clamp_to_image(event); self.start = None
        left, right = sorted((x1, x2))
        top, bottom = sorted((y1, y2))
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
        self.root.geometry("940x720")
        self.pref_file = Path.home() / "Library" / "Application Support" / "AtlasAgentB518" / "preferences.json"
        pref = Preferences.load(self.pref_file)
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.hid_replies: queue.Queue[str] = queue.Queue()
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
        self.hid_delay = tk.StringVar(value=str(pref.hid_delay))
        self.hid_scale_x = tk.StringVar(value=str(pref.hid_scale_x))
        self.hid_scale_y = tk.StringVar(value=str(pref.hid_scale_y))
        self.hid_offset_x = tk.StringVar(value=str(pref.hid_offset_x))
        self.hid_offset_y = tk.StringVar(value=str(pref.hid_offset_y))
        self.hid_mode = tk.StringVar(value=pref.hid_mode if pref.hid_mode in ("relative", "absolute") else "relative")
        self.absolute_width = tk.StringVar(value=str(pref.absolute_width))
        self.absolute_height = tk.StringVar(value=str(pref.absolute_height))
        self.auto_scale = tk.BooleanVar(value=pref.auto_scale)
        self.overlay_path = self.pref_file.with_name("last_match_overlay.png")
        self.station = tk.StringVar(value=pref.station if pref.station in ("DFU", "FCT", "BT") else "DFU")
        self.dfu_profile = tk.StringVar(value=pref.dfu_profile if pref.dfu_profile in DFU_PROFILES else "b482_dfu2")
        self.sn_text = tk.StringVar()
        self.ip_text = tk.StringVar()
        self.demo_fail_last = tk.BooleanVar(value=False)
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
        calibration = ttk.Frame(panel); calibration.pack(fill="x", pady=(8, 0))
        ttk.Label(calibration, text="驗證 HID：每步延遲(s)").pack(side="left")
        ttk.Entry(calibration, textvariable=self.hid_delay, width=6).pack(side="left", padx=(4, 10))
        ttk.Label(calibration, text="X 比例").pack(side="left")
        ttk.Entry(calibration, textvariable=self.hid_scale_x, width=6).pack(side="left", padx=4)
        ttk.Label(calibration, text="Y 比例").pack(side="left")
        ttk.Entry(calibration, textvariable=self.hid_scale_y, width=6).pack(side="left", padx=4)
        ttk.Checkbutton(calibration, text="自動比例", variable=self.auto_scale).pack(side="left", padx=(4, 8))
        ttk.Label(calibration, text="X／Y 偏移").pack(side="left", padx=(8, 0))
        ttk.Entry(calibration, textvariable=self.hid_offset_x, width=6).pack(side="left", padx=4)
        ttk.Entry(calibration, textvariable=self.hid_offset_y, width=6).pack(side="left", padx=4)
        ttk.Button(calibration, text="查看匹配疊圖", command=self.show_match_overlay).pack(side="right")
        absolute = ttk.Frame(panel); absolute.pack(fill="x", pady=(4, 0))
        ttk.Label(absolute, text="HID 模式：").pack(side="left")
        ttk.Combobox(absolute, textvariable=self.hid_mode, values=("relative", "absolute"), width=10,
                     state="readonly").pack(side="left")
        ttk.Label(absolute, text="  absolute 虛擬桌面寬 × 高（邏輯點）：").pack(side="left")
        ttk.Entry(absolute, textvariable=self.absolute_width, width=7).pack(side="left", padx=(4, 0))
        ttk.Label(absolute, text="×").pack(side="left", padx=2)
        ttk.Entry(absolute, textvariable=self.absolute_height, width=7).pack(side="left")
        ttk.Label(absolute, text="  例：單一 Retina 1440×900", foreground="#555").pack(side="left", padx=8)
        profile = ttk.Frame(panel); profile.pack(fill="x", pady=(8, 0))
        ttk.Label(profile, text="DFU 畫面設定：").pack(side="left")
        ttk.Combobox(profile, textvariable=self.dfu_profile, width=30, state="readonly",
                     values=("b482_dfu2", "generic", "b482_dfu1_manual")).pack(side="left")
        ttk.Label(profile, text="  B482 DFU_2：每個 SN 輸入後按 OK；DFU_1 尚待確認輸入步驟。").pack(side="left")
        batch = ttk.LabelFrame(panel, text="當前測試條碼（由 Arduino TCP→USB CDC 收到；也可手動驗證）", padding=8); batch.pack(fill="x", pady=10)
        ttk.Entry(batch, textvariable=self.sn_text).pack(side="left", fill="x", expand=True)
        ttk.Button(batch, text="開始流程", command=lambda: self.start_batch(self.sn_text.get())).pack(side="left", padx=(5, 0))
        ttk.Button(batch, text="本機模擬", command=lambda: self.start_local_demo(self.sn_text.get())).pack(side="left", padx=(5, 0))
        ttk.Button(batch, text="停止監聽", command=self.stop_monitor).pack(side="left", padx=(5, 0))
        ttk.Checkbutton(panel, text="本機模擬最後一台 FAIL（僅寫入目前 CSV 根路徑）", variable=self.demo_fail_last).pack(anchor="w")
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

    def hid_settings(self) -> tuple[float, float, float, float, float, str, int, int]:
        try:
            delay = float(self.hid_delay.get())
            scale_x, scale_y = float(self.hid_scale_x.get()), float(self.hid_scale_y.get())
            offset_x, offset_y = float(self.hid_offset_x.get()), float(self.hid_offset_y.get())
            absolute_width, absolute_height = int(self.absolute_width.get()), int(self.absolute_height.get())
        except ValueError as exc:
            raise AgentError("HID 延遲、比例與偏移必須是數字") from exc
        if delay < 0:
            raise AgentError("HID 每步延遲不可小於 0")
        hid_coordinate((0, 0), scale_x, scale_y, offset_x, offset_y)
        mode = self.hid_mode.get()
        if mode not in ("relative", "absolute"):
            raise AgentError("HID 模式必須是 relative 或 absolute")
        if mode == "absolute":
            absolute_hid_report_coordinate((0, 0), absolute_width, absolute_height)
        return delay, scale_x, scale_y, offset_x, offset_y, mode, absolute_width, absolute_height

    def show_match_overlay(self) -> None:
        if not self.overlay_path.is_file():
            messagebox.showinfo(TITLE, "尚無匹配疊圖；請先執行一次 DFU 或 BT 開始流程。", parent=self.root)
            return
        if cv2 is None:
            messagebox.showerror(TITLE, "查看匹配疊圖需要 opencv-python", parent=self.root); return
        image = cv2.imread(str(self.overlay_path))
        if image is None:
            messagebox.showerror(TITLE, "無法讀取匹配疊圖", parent=self.root); return
        height, width = image.shape[:2]
        scale, shown_width, shown_height = preview_geometry(width, height, 1100, 650)
        shown = cv2.resize(image, (shown_width, shown_height), interpolation=cv2.INTER_AREA) if scale != 1 else image
        dialog = tk.Toplevel(self.root)
        dialog.title("OpenCV 匹配疊圖（綠框＝模板；紅十字＝截圖座標）")
        dialog.transient(self.root); dialog.resizable(False, False)
        try:
            photo = tk.PhotoImage(data=opencv_image_to_tk_png(shown))
        except (AgentError, tk.TclError) as exc:
            dialog.destroy(); messagebox.showerror(TITLE, str(exc), parent=self.root); return
        label = ttk.Label(dialog, image=photo)
        label.image = photo  # Keep the Tk image alive until this dialog closes.
        label.pack(padx=10, pady=10)
        ttk.Label(dialog, text=f"原圖 {width} × {height} px；檔案：{self.overlay_path}").pack(padx=10, pady=(0, 10))

    def open_template_maker(self) -> None:
        template_root = Path(self.template_path.get()).expanduser()
        screenshot_root = Path(self.screenshot_path.get()).expanduser()
        if not screenshot_root.is_dir():
            messagebox.showerror(TITLE, "請先選擇有效的螢幕截圖路徑"); return
        station = self.station.get()
        profile = VISUAL_PROFILES[self.dfu_profile.get() if station == "DFU" else "b482_bt"]
        suggested = [profile["window"]]
        suggested.extend(profile[key] for key in ("barcode", "ok", "start") if key in profile)
        TemplateMakerDialog(self.root, template_root, screenshot_root, suggested)

    def append(self, text: str) -> None:
        self.output.configure(state="normal"); self.output.insert("end", text + "\n"); self.output.see("end"); self.output.configure(state="disabled")

    def connect(self) -> None:
        try:
            self.link.connect(self.port.get().strip()); self.append("USB CDC 已連線")
        except (AgentError, OSError) as exc: messagebox.showerror(TITLE, str(exc))

    def safe_send(self, command: str) -> None:
        try: self.link.send(command); self.append("TX: " + command)
        except AgentError as exc: messagebox.showerror(TITLE, str(exc))

    def validate_batch(self, payload: str) -> Optional[tuple[Path, list[str]]]:
        try:
            root = Path(self.csv_path.get()).expanduser()
            if not root.is_dir(): raise AgentError("請選擇有效的 CSV 根路徑")
            sns = parse_barcodes(payload)
        except AgentError as exc:
            messagebox.showerror(TITLE, str(exc)); return None
        return root, sns

    def prepare_batch(self, payload: str) -> Optional[tuple[Path, list[str], int]]:
        validated = self.validate_batch(payload)
        if validated is None:
            return None
        root, sns = validated
        self.stop_monitor(); self.sns = sns; self.batch_results = {}; self.reported_batch_number = None
        self.sn_display.configure(text="當前 SN：" + "、".join(sns))
        self.batch_number += 1
        return root, sns, self.batch_number

    def start_batch(self, payload: str) -> Optional[list[str]]:
        prepared = self.prepare_batch(payload)
        if prepared is None:
            return None
        root, sns, batch_number = prepared
        if self.station.get() in ("DFU", "BT"):
            threading.Thread(target=self.visual_start, args=(self.station.get(), sns, root, batch_number), daemon=True).start()
        else:
            self.start_monitor(root, sns, batch_number)
        return sns

    def start_local_demo(self, payload: str) -> None:
        validated = self.validate_batch(payload)
        if validated is None:
            return
        root, sns = validated
        if not messagebox.askyesno(TITLE, f"將在下列 CSV 根路徑建立本機模擬資料：\n{root}\n\n不會使用 Arduino 或影像匹配。", parent=self.root):
            return
        prepared = self.prepare_batch(payload)
        if prepared is None:
            return
        root, sns, batch_number = prepared
        station = self.station.get()
        fail_last = self.demo_fail_last.get()
        self.start_monitor(root, sns, batch_number)

        def run() -> None:
            try:
                write_local_demo_results(root, sns, station, fail_last, self.monitor_stop)
            except OSError as exc:
                self.events.put(("log", f"本機模擬寫入失敗：{exc}"))
        threading.Thread(target=run, daemon=True).start()
        self.append(f"本機模擬已啟動：{station}／{', '.join(sns)}")

    def start_monitor(self, root: Path, sns: list[str], batch_number: int) -> None:
        self.monitor_stop = threading.Event()
        log_root = Path(self.log_path.get()).expanduser()
        if not log_root.is_dir(): log_root = root
        self.monitor = FolderMonitor(root, log_root, sns, lambda item: self.events.put(("log", item)),
                                     lambda result: self.events.put(("result", (batch_number, result))), self.monitor_stop)
        self.monitor.start()

    def send_hid_sequence(self, commands: Iterable[str], delay: float = 0.0, timeout: float = 8.0) -> None:
        """Wait for every Arduino HID completion before proceeding to CSV monitoring."""
        sequence = list(commands)
        while True:
            try: self.hid_replies.get_nowait()
            except queue.Empty: break
        for index, command in enumerate(sequence):
            expected = hid_success_reply(command)
            self.link.send(command)
            deadline = time.monotonic() + timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise AgentError(f"等待 Arduino 執行 {command} 逾時")
                reply = self.hid_replies.get(timeout=remaining)
                if reply == expected:
                    break
                if reply.startswith("ERR:"):
                    raise AgentError(f"Arduino 執行 {command} 失敗：{reply}")
            if delay and index < len(sequence) - 1:
                time.sleep(delay)

    def visual_start(self, station: str, sns: list[str], csv_root: Path, batch_number: int) -> None:
        """Ask Arduino HID for screenshot/actions; no Mac input API is invoked here."""
        try:
            if station == "DFU" and self.dfu_profile.get() == "b482_dfu1_manual":
                raise AgentError("B482 DFU_1 畫面尚未確認 SN 輸入方式；請選擇 b482_dfu2 或 generic")
            delay, scale_x, scale_y, offset_x, offset_y, hid_mode, absolute_width, absolute_height = self.hid_settings()
            profile = VISUAL_PROFILES[self.dfu_profile.get() if station == "DFU" else "b482_bt"]
            templates = Path(self.template_path.get()).expanduser()
            required = [profile["window"], profile["barcode"]] if station == "DFU" else [profile["window"], profile["start"]]
            required.append(profile["ok"] if station == "DFU" and profile["input_mode"] == "ok_each" else profile.get("start", ""))
            resolved = {item: resolve_template_path(templates, item) for item in required if item}
            missing = [item for item in required if item and not resolved[item].is_file()]
            if missing:
                expected = "、".join(str(Path(item)) for item in missing)
                raise AgentError(f"缺少 {station} 模板：{expected}\n目前模板根路徑：{templates}\n請用「製作模板」儲存為上述相對檔名。")
            root_fallbacks = [item for item, path in resolved.items() if path.parent == templates and Path(item).parent != Path(".")]
            if root_fallbacks:
                self.events.put(("log", "相容模式：使用模板根目錄檔案「" + "、".join(root_fallbacks) + "」"))
            before = time.time(); self.link.send("SCREENSHOT")
            screenshot_dir = Path(self.screenshot_path.get()).expanduser()
            if not screenshot_dir.is_dir(): raise AgentError("請選擇有效的螢幕截圖路徑")
            self.events.put(("log", f"等待 {SCREENSHOT_SETTLE_SECONDS:g} 秒讓 macOS 完成儲存螢幕截圖…"))
            time.sleep(SCREENSHOT_SETTLE_SECONDS)
            deadline = time.monotonic() + (SCREENSHOT_TIMEOUT_SECONDS - SCREENSHOT_SETTLE_SECONDS)
            shots: list[Path] = []
            while time.monotonic() < deadline and not shots:
                shots = new_screenshots(screenshot_dir, before); time.sleep(.25)
            if not shots: raise AgentError(f"等待 Arduino 產生螢幕截圖逾時（共 {SCREENSHOT_TIMEOUT_SECONDS:g} 秒）")
            window = resolved[profile["window"]]
            shot = None
            match_errors: list[str] = []
            for candidate in shots:
                try:
                    window_rect = template_match(candidate, window)
                    shot = candidate
                    break
                except AgentError as exc:
                    match_errors.append(f"{candidate.name}: {exc}")
            if shot is None:
                raise AgentError("所有新截圖均找不到測試視窗模板。\n" + "\n".join(match_errors))
            self.events.put(("log", f"使用截圖：{shot.name}（共找到 {len(shots)} 張螢幕截圖）"))
            if self.auto_scale.get():
                automatic_scale = macos_screenshot_scale(shot)
                if automatic_scale:
                    scale_x, scale_y = automatic_scale
                    self.events.put(("auto_scale", automatic_scale))
                    self.events.put(("log", f"自動比例：截圖 {scale_x:g} × {scale_y:g}（依 macOS 顯示器邏輯尺寸）"))
                else:
                    self.events.put(("log", "自動比例：未找到與截圖尺寸相符的顯示器，保留手動比例"))
            window_center = (window_rect[0] + window_rect[2] // 2, window_rect[1] + window_rect[3] // 2)
            # Template matching inside the window prevents matching a stale/other app control.
            bundled_templates = Path(__file__).with_name("templates").resolve()
            using_bundled_templates = templates.resolve() == bundled_templates
            if "window_size" in profile and using_bundled_templates:
                width, height = profile["window_size"]
                region = (window_rect[0], window_rect[1], width, height)
            elif "window_size" in profile:
                # A user-created template may come from a Retina display or a
                # full-screen HTML HMI. Its pixels do not share the 1011×600
                # B482 reference resolution, so search that screenshot only.
                region = None
                self.events.put(("log", "使用自訂 B482 模板：依整張匹配到的螢幕搜尋控制項"))
            else:
                region = window_rect
            def logical_for(source: tuple[int, int]) -> tuple[int, int]:
                return hid_coordinate(source, scale_x, scale_y, offset_x, offset_y)

            def target_for(source: tuple[int, int]) -> tuple[int, int]:
                logical = logical_for(source)
                return absolute_hid_report_coordinate(logical, absolute_width, absolute_height) if hid_mode == "absolute" else logical

            def match_label(name: str, source: tuple[int, int]) -> str:
                logical = logical_for(source)
                if hid_mode == "absolute":
                    return f"{name} logical={logical[0]},{logical[1]} ABS"
                return f"{name} HID"

            matches = [(match_label("window", rectangle_center(window_rect)), window_rect, target_for(rectangle_center(window_rect)))]
            if station == "DFU":
                barcode_rect = template_match(shot, resolved[profile["barcode"]], region=region)
                barcode_source = rectangle_center(barcode_rect)
                barcode = target_for(barcode_source)
                matches.append((match_label("SN input", barcode_source), barcode_rect, barcode))
                if profile["input_mode"] == "ok_each":
                    button_rect = template_match(shot, resolved[profile["ok"]], region=region)
                    button_source = rectangle_center(button_rect)
                    button = target_for(button_source)
                    matches.append((match_label("OK", button_source), button_rect, button))
                    write_match_overlay(shot, matches, self.overlay_path)
                    self.send_hid_sequence(dfu_ok_each_commands(sns, barcode, button, hid_mode), delay=delay)
                    self.events.put(("log", f"DFU（{hid_mode}）：截圖 SN {barcode_source} → HID {barcode}，OK {button_source} → HID {button}；全部 SN 輸入完成，啟動監聽"))
                else:
                    commands = click_commands(barcode, hid_mode)
                    for index, sn in enumerate(sns):
                        commands.append("K_WRITE:" + sn)
                        if index < len(sns) - 1:
                            commands.append("K_KEY:TAB")
                    button_rect = template_match(shot, resolved[profile["start"]], region=region)
                    button_source = rectangle_center(button_rect)
                    button = target_for(button_source)
                    matches.append((match_label("Start", button_source), button_rect, button))
                    write_match_overlay(shot, matches, self.overlay_path)
                    self.send_hid_sequence(commands + click_commands(button, hid_mode), delay=delay)
                    self.events.put(("log", f"DFU：視窗定位 {window_center}，開始按鈕 {button}；啟動監聽"))
            else:
                button_rect = template_match(shot, resolved[profile["start"]], region=region)
                button_source = rectangle_center(button_rect)
                button = target_for(button_source)
                matches.append((match_label("Start All", button_source), button_rect, button))
                write_match_overlay(shot, matches, self.overlay_path)
                self.send_hid_sequence(click_commands(button, hid_mode), delay=delay)
                self.events.put(("log", f"BT：截圖 Start All {button_source} → HID {button}；啟動監聽"))
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
                    self.hid_replies.put(line)
                    payload = incoming_barcode_payload(line)
                    if payload is not None:
                        try:
                            self.start_batch(payload)
                        except Exception as exc: self.append("ERR: 無法啟動批次：" + str(exc))
                    elif line.startswith("IP:") or "IP=" in line: self.ip_text.set(line)
                elif kind == "log": self.append(str(item))
                elif kind == "auto_scale":
                    scale_x, scale_y = item
                    self.hid_scale_x.set(f"{scale_x:g}")
                    self.hid_scale_y.set(f"{scale_y:g}")
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
        try:
            delay, scale_x, scale_y, offset_x, offset_y, hid_mode, absolute_width, absolute_height = self.hid_settings()
        except AgentError:
            delay, scale_x, scale_y, offset_x, offset_y, hid_mode, absolute_width, absolute_height = .5, 1.0, 1.0, 0.0, 0.0, "relative", 1440, 900
        Preferences(port=self.port.get(), csv_path=self.csv_path.get(), log_path=self.log_path.get(),
                    template_path=self.template_path.get(), station=self.station.get(),
                    dfu_profile=self.dfu_profile.get(), screenshot_path=self.screenshot_path.get(),
                    hid_delay=delay, hid_scale_x=scale_x, hid_scale_y=scale_y,
                    hid_offset_x=offset_x, hid_offset_y=offset_y, hid_mode=hid_mode,
                    absolute_width=absolute_width, absolute_height=absolute_height,
                    auto_scale=self.auto_scale.get()).save(self.pref_file)
        self.stop_monitor(); self.link.close(); self.root.destroy()


def main() -> int:
    parser = argparse.ArgumentParser(description=TITLE); parser.add_argument("--version", action="version", version=TITLE); parser.parse_args()
    root = tk.Tk(); AtlasAgentApp(root).root.mainloop(); return 0


if __name__ == "__main__": raise SystemExit(main())
