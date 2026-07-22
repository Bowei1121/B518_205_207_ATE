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
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Optional

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from build_version import VERSION

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

try:
    import Vision
    from Foundation import NSURL
except ImportError:
    Vision = None
    NSURL = None

TITLE = f"Atlas Agent B518 ATE-V{VERSION}"
TIME_FOLDER = re.compile(r"^(\d{8}_\d{2}-\d{2}-\d{2})(?:\.[^/]*)?$")
# The Arduino TCP bridge deliberately transfers upper-computer payloads without
# adding a DATA: frame.  Keep the raw payload acceptance narrow enough that a
# CDC control reply (OK:, IP:, ERR:) can never accidentally start a test.
RAW_SN_BATCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}(?:\s*,\s*[A-Za-z0-9][A-Za-z0-9._-]{0,127}){0,3}$")
SN_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
JOB_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
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
        "ok": "b482/dfu2_ok.png", "checkbox_checked": "b482/slot_checkbox_checked.png",
        "checkbox_unchecked": "b482/slot_checkbox_unchecked.png", "window_size": (1011, 600), "input_mode": "ok_each",
    },
    "b482_bt": {
        "window": "b482/bt_window.png", "start": "b482/bt_start_all.png",
        "starts": {1: "b482/bt_start_1.png", 2: "b482/bt_start_2.png",
                   3: "b482/bt_start_3.png", 4: "b482/bt_start_4.png"},
        "status": {"PASS": "b482/bt_status_pass.png", "FAIL": "b482/bt_status_fail.png",
                   "TESTING": "b482/bt_status_testing.png", "NOTSET": "b482/bt_status_notset.png"},
        "window_size": (1568, 727),
    },
}

# FCT does not need a Start-button template: the fixture starts the real test.
# These two small crops identify the four native checkbox controls before a
# sparse JOB begins.  They are shared with DFU_2 because the simulated HMI uses
# the same checkbox rendering; create them from the target HMI when necessary.
FCT_CHECKBOX_TEMPLATES = {
    "window": "b482/fct_window.png",
    "checked": "b482/slot_checkbox_checked.png",
    "unchecked": "b482/slot_checkbox_unchecked.png",
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
    result_timeout_seconds: float = 300.0

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


@dataclass(frozen=True)
class BtStatusRow:
    status: str
    rectangle: tuple[int, int, int, int]


@dataclass(frozen=True)
class OcrText:
    text: str
    rectangle: tuple[int, int, int, int]


@dataclass(frozen=True)
class BtSnReview:
    expected_sns: list[str]
    machine_sns: list[str]
    slots: list[int]
    results: dict[str, str]


@dataclass(frozen=True)
class TestCommand:
    station: str
    job_id: str
    assignments: tuple[tuple[int, str], ...]

    @property
    def slots(self) -> list[int]:
        return [slot for slot, _ in self.assignments]

    @property
    def sns(self) -> list[str]:
        return [sn for _, sn in self.assignments]


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


def parse_test_command(line: str) -> TestCommand:
    """Parse STATION:JOB=id;slot=SN,... and preserve explicit slot mapping."""
    value = line.strip()
    try:
        header, assignment_text = value.split(";", 1)
        station, job_field = header.split(":", 1)
    except ValueError as exc:
        raise AgentError("工作指令格式應為 STATION:JOB=id;slot=SN,...") from exc
    station = station.upper()
    if station not in ("DFU", "FCT", "BT") or not job_field.upper().startswith("JOB="):
        raise AgentError("工作指令的工站或 JOB 欄位無效")
    job_id = job_field[4:].strip()
    if not JOB_PATTERN.fullmatch(job_id):
        raise AgentError("JOB ID 只可使用英數、點、底線或連字號，最多 64 字元")
    assignments: list[tuple[int, str]] = []
    for item in assignment_text.split(","):
        try:
            slot_text, sn = (part.strip() for part in item.split("=", 1))
            slot = int(slot_text)
        except (TypeError, ValueError) as exc:
            raise AgentError(f"slot 指派格式錯誤：{item}") from exc
        if not 1 <= slot <= 4 or not SN_PATTERN.fullmatch(sn):
            raise AgentError(f"slot 或 SN 無效：{item}")
        assignments.append((slot, sn))
    if not 1 <= len(assignments) <= 4:
        raise AgentError("工作指令必須包含 1 至 4 個 slot")
    if len({slot for slot, _ in assignments}) != len(assignments):
        raise AgentError("工作指令不可重複指定 slot")
    if len({sn for _, sn in assignments}) != len(assignments):
        raise AgentError("同一 JOB 的 SN 不可重複")
    return TestCommand(station, job_id, tuple(sorted(assignments)))


def arduino_ip_reply(line: str) -> Optional[str]:
    """Extract a valid IPv4 address from supported Arduino network replies."""
    value = line.strip()
    candidate: Optional[str] = None
    if value.startswith("IP:"):
        candidate = value[3:].strip()
    elif value.startswith("OK:NET_SET:"):
        candidate = value[len("OK:NET_SET:"):].strip()
    elif "IP=" in value:
        candidate = value.rsplit("IP=", 1)[1].strip()
    if candidate is None:
        return None
    parts = candidate.split(".")
    if len(parts) != 4 or any(not part.isdigit() or not 0 <= int(part) <= 255 for part in parts):
        return None
    return candidate


def batch_result_report(station: str, job_id: str, assignments: Iterable[tuple[int, str]],
                        statuses: dict[str, str]) -> str:
    """Create a slot-aware RESULT line for one station JOB."""
    ordered = list(assignments)
    if station not in ("DFU", "FCT", "BT") or not JOB_PATTERN.fullmatch(job_id):
        raise AgentError("批次結果的工站或 JOB ID 無效")
    if not ordered or any(sn not in statuses for _, sn in ordered):
        raise AgentError("批次結果尚未完整")
    return f"RESULT:{station}:JOB={job_id};" + ";".join(
        f"{slot}={sn},{statuses[sn]}" for slot, sn in ordered)


def dfu_ok_each_commands(sns: Iterable[str], barcode: tuple[int, int], button: tuple[int, int],
                         mode: str = "relative") -> list[str]:
    """Build DFU_2 HID commands, resetting the relative mouse before every target."""
    commands: list[str] = []
    for sn in sns:
        commands.extend(click_commands(barcode, mode) + [f"K_WRITE:{sn}"] + click_commands(button, mode))
    return commands


def dfu_tab_slot_commands(assignments: Iterable[tuple[int, str]]) -> list[str]:
    """Type sparse generic-DFU slots, using Tab to preserve empty positions."""
    commands: list[str] = []
    current_slot = 1
    for slot, sn in assignments:
        if not current_slot <= slot <= 4:
            raise AgentError("DFU generic slot 必須遞增且介於 1～4")
        commands.extend(["K_KEY:TAB"] * (slot - current_slot))
        commands.append("K_WRITE:" + sn)
        current_slot = slot
    return commands


def absolute_click_commands(target: tuple[int, int]) -> list[str]:
    """Move from the top-left origin to a screen coordinate and left click."""
    return ["M_RESET", f"M_MOVE:{target[0]},{target[1]}", "M_CLICK:L"]


def click_commands(target: tuple[int, int], mode: str) -> list[str]:
    if mode == "absolute":
        # macOS accepts this report for cursor positioning, but a standard
        # relative-mouse button report is required for a reliable UI click.
        return [f"M_ABS:{target[0]},{target[1]}", "M_CLICK:L"]
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


def nearest_timestamp_folder(sn_dir: Path, now: Optional[datetime] = None, created_after: Optional[float] = None) -> Optional[Path]:
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
            if created_after is not None and child.stat().st_mtime <= created_after:
                continue
        except OSError:
            continue
        try:
            stamp = datetime.strptime(match.group(1), "%Y%m%d_%H-%M-%S")
        except ValueError:
            continue
        choices.append((abs((stamp - now).total_seconds()), stamp, child))
    # Nearest prevents stale rework selection; timestamp breaks same-distance ties.
    return min(choices, key=lambda item: (item[0], -item[1].timestamp()))[2] if choices else None


def delete_screenshots(paths: Iterable[Path]) -> tuple[list[Path], list[Path]]:
    """Delete only screenshots generated for the current visual-start request."""
    deleted, failed = [], []
    for path in paths:
        try:
            path.unlink()
            deleted.append(path)
        except OSError:
            failed.append(path)
    return deleted, failed


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


def template_matches(image: Path, template: Path, threshold: float = 0.80,
                     region: Optional[tuple[int, int, int, int]] = None) -> list[tuple[int, int, int, int, float]]:
    """Return distinct occurrences of one template, ordered by match confidence."""
    if cv2 is None:
        raise AgentError("BT STATUS 辨識需要 opencv-python")
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
        return []
    result = cv2.matchTemplate(screen, needle, cv2.TM_CCOEFF_NORMED)
    ys, xs = (result >= threshold).nonzero()
    candidates = sorted(((float(result[y, x]), int(x), int(y)) for y, x in zip(ys, xs)), reverse=True)
    found: list[tuple[int, int, int, int, float]] = []
    # A single cell gives many adjacent high-score points.  Keep only one
    # representative per overlapping template rectangle (non-max suppression).
    for score, x, y in candidates:
        if any(x < old_x + old_w and x + needle_width > old_x and y < old_y + old_h and y + needle_height > old_y
               for old_x, old_y, old_w, old_h, _ in found):
            continue
        found.append((offset_x + x, offset_y + y, needle_width, needle_height, score))
    return found


def slot_checkbox_states(image: Path, checked_template: Path, unchecked_template: Path,
                         region: Optional[tuple[int, int, int, int]] = None) -> list[tuple[bool, tuple[int, int, int, int]]]:
    """Return the four horizontal slot checkbox states and their rectangles.

    A checked and an unchecked checkbox need separate templates.  Matching both
    states means the Agent only clicks controls whose current state differs from
    the sparse JOB assignment, rather than blindly toggling slot 2/3.
    """
    hits: list[tuple[int, int, bool, tuple[int, int, int, int], float]] = []
    for checked, template in ((True, checked_template), (False, unchecked_template)):
        for x, y, width, height, score in template_matches(image, template, region=region):
            hits.append((x + width // 2, y + height // 2, checked, (x, y, width, height), score))
    if not hits:
        raise AgentError("找不到任何 Slot 測試 checkbox 模板")
    # In the unlikely event both templates overlap at the same location, retain
    # the better score.  The HMI cards are arranged left-to-right as slot 1..4.
    rows: list[tuple[int, int, bool, tuple[int, int, int, int], float]] = []
    for hit in sorted(hits, key=lambda item: item[0]):
        if rows and abs(hit[0] - rows[-1][0]) <= max(hit[3][2], rows[-1][3][2]):
            if hit[4] > rows[-1][4]:
                rows[-1] = hit
        else:
            rows.append(hit)
    if len(rows) != 4:
        raise AgentError(f"Slot checkbox 僅辨識到 {len(rows)} 個；請從同一張、同一解析度 HMI 截圖製作 checked / unchecked 模板")
    return [(item[2], item[3]) for item in rows]


def bt_status_rows_from_screen(image: Path, status_templates: dict[str, Path],
                               region: Optional[tuple[int, int, int, int]] = None) -> list[BtStatusRow]:
    """Read the four top-to-bottom BT STATUS cells and retain their geometry."""
    hits: list[tuple[int, int, str, tuple[int, int, int, int], float]] = []
    for status, template in status_templates.items():
        for x, y, width, height, score in template_matches(image, template, region=region):
            hits.append((y + height // 2, x + width // 2, status, (x, y, width, height), score))
    if not hits:
        raise AgentError("找不到任何 BT STATUS 模板")
    # A crop that includes the cell background and text creates one match per
    # row.  Sort by y to preserve slot 1→4 order, retaining the best hit when
    # two state templates overlap around the same row.
    rows: list[tuple[int, int, str, tuple[int, int, int, int], float]] = []
    for hit in sorted(hits):
        if rows and abs(hit[0] - rows[-1][0]) <= 12:
            if hit[4] > rows[-1][4]:
                rows[-1] = hit
        else:
            rows.append(hit)
    if len(rows) < 4:
        raise AgentError(f"BT STATUS 僅辨識到 {len(rows)} 列；請確認四個狀態模板均從同一解析度畫面裁切")
    return [BtStatusRow(row[2], row[3]) for row in rows[:4]]


def bt_statuses_from_screen(image: Path, status_templates: dict[str, Path],
                            region: Optional[tuple[int, int, int, int]] = None) -> list[str]:
    """Compatibility helper that returns only STATUS names."""
    return [row.status for row in bt_status_rows_from_screen(image, status_templates, region)]


def normalize_ocr_sn(value: str) -> str:
    """Normalize BT OCR serials for the agreed customer barcode alphabet.

    Customer serial numbers intentionally exclude the letter ``O`` while
    retaining digits 0–9.  Vision therefore reading an ``O`` is the known,
    deterministic OCR representation of ``0``; convert only that character.
    ``I`` remains untouched so the software never guesses 1 from I.
    """
    return re.sub(r"\s+", "", value).upper().replace("O", "0")


def vision_rectangle_components(rectangle: object) -> tuple[float, float, float, float]:
    """Return a Vision CGRect as x, y, width, height across PyObjC versions.

    Older PyObjC versions exposed a CGRect as a flat four-value tuple, while
    current versions expose it as ``((x, y), (width, height))``.  Keep the
    OCR pipeline independent of that bridge representation.
    """
    try:
        if len(rectangle) == 4:  # type: ignore[arg-type]
            x, y, width, height = rectangle  # type: ignore[misc]
        elif len(rectangle) == 2:  # type: ignore[arg-type]
            (x, y), (width, height) = rectangle  # type: ignore[misc]
        else:
            raise ValueError("unexpected component count")
        return float(x), float(y), float(width), float(height)
    except (TypeError, ValueError) as exc:
        raise AgentError(f"無法解析 Vision OCR 座標：{rectangle!r}") from exc


def pair_bt_sn_text(status_rows: list[BtStatusRow], ocr_texts: Iterable[OcrText]) -> list[str]:
    """Assign OCR SN text to each STATUS row, preferring the adjacent SN column."""
    candidates = [OcrText(normalize_ocr_sn(item.text), item.rectangle) for item in ocr_texts
                  if RAW_SN_BATCH.fullmatch(normalize_ocr_sn(item.text))
                  and not re.fullmatch(r"SLOT[1-4]", normalize_ocr_sn(item.text))]
    machine_sns: list[str] = []
    for row in status_rows:
        status_x, status_y, status_width, status_height = row.rectangle
        row_center = status_y + status_height / 2
        nearby = [item for item in candidates
                  if item.rectangle[0] + item.rectangle[2] / 2 < status_x
                  and abs(item.rectangle[1] + item.rectangle[3] / 2 - row_center) <= max(48, status_height * 1.5)]
        if not nearby:
            machine_sns.append("")
            continue
        # Both the SLOT label and its SN have the same vertical position.
        # The SN column is immediately to the left of STATUS, so select the
        # rightmost candidate rather than relying on Vision's return order.
        machine_sns.append(max(nearby, key=lambda item: (item.rectangle[0] + item.rectangle[2] / 2,
                                                          -abs(item.rectangle[1] + item.rectangle[3] / 2 - row_center))).text)
    return machine_sns


def recognize_text_vision(image: Path) -> list[OcrText]:
    """Read screenshot text with macOS Vision; no screen-recording permission is used."""
    if Vision is None or NSURL is None:
        raise AgentError("缺少 macOS Vision OCR；請重新建置並安裝 pyobjc-framework-Vision")
    if cv2 is None:
        raise AgentError("Vision OCR 需要 opencv-python 取得截圖尺寸")
    pixels = cv2.imread(str(image))
    if pixels is None:
        raise AgentError(f"無法讀取 OCR 截圖：{image}")
    height, width = pixels.shape[:2]
    recognition_image = image
    coordinate_scale = 1.0
    temporary_image: Optional[Path] = None
    # Vision can reject a large Retina screenshot before it reaches OCR.  The
    # text remains clear at this size; coordinates are converted back below.
    maximum_dimension = 800
    if max(width, height) > maximum_dimension:
        coordinate_scale = maximum_dimension / max(width, height)
        scaled = cv2.resize(pixels, (round(width * coordinate_scale), round(height * coordinate_scale)), interpolation=cv2.INTER_AREA)
        handle = tempfile.NamedTemporaryFile(prefix="atlas_bt_ocr_", suffix=".png", delete=False)
        handle.close(); temporary_image = Path(handle.name)
        if not cv2.imwrite(str(temporary_image), scaled):
            temporary_image.unlink(missing_ok=True)
            raise AgentError("無法建立 Vision OCR 暫存影像")
        recognition_image = temporary_image
        height, width = scaled.shape[:2]
    results = []

    def completed(request, error) -> None:
        if error is not None:
            return
        for observation in request.results() or []:
            candidates = observation.topCandidates_(1)
            if not candidates:
                continue
            text = str(candidates[0].string())
            x, y, box_width, box_height = vision_rectangle_components(observation.boundingBox())
            results.append(OcrText(text, (round(x * width), round((1 - y - box_height) * height),
                                          round(box_width * width), round(box_height * height))))

    try:
        request = Vision.VNRecognizeTextRequest.alloc().initWithCompletionHandler_(completed)
        request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
        request.setUsesLanguageCorrection_(False)
        handler = Vision.VNImageRequestHandler.alloc().initWithURL_options_(NSURL.fileURLWithPath_(str(recognition_image)), {})
        success, error = handler.performRequests_error_([request], None)
        if not success:
            raise AgentError("macOS Vision OCR 失敗：" + str(error or "未知錯誤"))
        if coordinate_scale != 1.0:
            return [OcrText(item.text, tuple(round(value / coordinate_scale) for value in item.rectangle)) for item in results]
        return results
    finally:
        if temporary_image is not None:
            temporary_image.unlink(missing_ok=True)


def bt_completed_results(sns: list[str], slots: list[int], statuses: list[str], testing_seen: set[str]) -> dict[str, str]:
    """Return final BT results only after the entire selected batch has ended.

    A BT HMI often retains the previous PASS/FAIL until its next run starts.
    Requiring TESTING is the protocol guard that separates a new test from
    that stale screen state.
    """
    selected: dict[str, str] = {}
    for sn, slot in zip(sns, slots):
        if not 1 <= slot <= len(statuses):
            raise AgentError(f"BT slot {slot} 不在畫面 STATUS 範圍內")
        current = statuses[slot - 1]
        selected[sn] = current
        if current == "TESTING":
            testing_seen.add(sn)
    # Never return a partial batch: stale results are possible before TESTING,
    # and early PASS/FAIL is not a final batch result while another slot runs.
    if any(sn not in testing_seen for sn in sns) or any(status == "TESTING" for status in selected.values()):
        return {}
    if any(status not in ("PASS", "FAIL") for status in selected.values()):
        return {}
    return selected


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
    def __init__(self, csv_root: Path, log_root: Path, sns: Iterable[str], on_log: Callable[[str], None], on_result: Callable[[TestResult], None], stop: threading.Event,
                 created_after: float = 0.0, timeout_seconds: float = 0.0,
                 on_timeout: Optional[Callable[[list[str]], None]] = None) -> None:
        super().__init__(daemon=True)
        self.csv_root, self.log_root, self.sns, self.on_log, self.on_result, self.stop = csv_root, log_root, list(sns), on_log, on_result, stop
        self.reported: set[Path] = set()
        self.reported_sns: set[str] = set()
        self.log_positions: dict[Path, int] = {}
        self.created_after, self.timeout_seconds, self.on_timeout = created_after, timeout_seconds, on_timeout

    def run(self) -> None:
        self.on_log("監聽已啟動：" + ", ".join(self.sns) + f"；僅接受開始後建立的資料" +
                    (f"；逾時 {self.timeout_seconds:g} 秒" if self.timeout_seconds else "；不設定逾時"))
        deadline = time.monotonic() + self.timeout_seconds if self.timeout_seconds else None
        while not self.stop.is_set():
            for sn in self.sns:
                folder = nearest_timestamp_folder(self.csv_root / sn, created_after=self.created_after)
                if folder is None:
                    continue
                # Separate log roots are supported, but the CSV folder name is
                # retained so log and result always represent the same run.
                log_file = self.log_root / sn / folder.name / "system" / "device.log"
                if not log_file.is_file(): log_file = folder / "system" / "device.log"
                self._render_log(log_file)
                records = locate_records(folder)
                if records:
                    try:
                        if records.stat().st_mtime <= self.created_after:
                            continue
                    except OSError:
                        continue
                if records and records not in self.reported:
                    try:
                        status, detail = parse_records(records)
                    except (OSError, AgentError) as exc:
                        self.on_log(f"{sn}: CSV 尚未可讀取：{exc}")
                        continue
                    if status != "UNKNOWN":
                        self.reported.add(records)
                        self.reported_sns.add(sn)
                        self.on_result(TestResult(sn, status, folder, records, detail))
            if deadline is not None and time.monotonic() >= deadline:
                pending = [sn for sn in self.sns if sn not in self.reported_sns]
                if pending:
                    self.on_log("測試結果逾時：" + "、".join(pending))
                    if self.on_timeout:
                        self.on_timeout(pending)
                return
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


class BtStatusMonitor(threading.Thread):
    """Permission-free BT result monitor using Arduino-created screenshots.

    macOS may defer writing a screenshot for several seconds.  Therefore the
    one-second interval is measured *after a fresh image has been analysed*,
    rather than repeatedly analysing an old image.
    """
    def __init__(self, screenshot_root: Path, status_templates: dict[str, Path],
                 sns: list[str], slots: list[int], request_screenshot: Callable[[], None],
                 on_log: Callable[[str], None], on_result: Callable[[TestResult], None],
                 on_review: Callable[[BtSnReview], None],
                 delete_shots: Callable[[Iterable[Path]], None], stop: threading.Event,
                 timeout_seconds: float = 0.0, on_timeout: Optional[Callable[[list[str]], None]] = None) -> None:
        super().__init__(daemon=True)
        self.screenshot_root, self.status_templates = screenshot_root, status_templates
        self.sns, self.slots, self.request_screenshot = sns, slots, request_screenshot
        self.on_log, self.on_result, self.on_review, self.delete_shots, self.stop = on_log, on_result, on_review, delete_shots, stop
        self.timeout_seconds, self.on_timeout = timeout_seconds, on_timeout
        self.reported: set[str] = set()
        self.testing_seen: set[str] = set()
        self.machine_sns: Optional[list[str]] = None
        self.sn_mismatch = False

    def run(self) -> None:
        self.on_log("BT 畫面 STATUS 監聽已啟動：" + "、".join(self.sns) + "；先等待 TESTING，再接受 PASS／FAIL；每張新截圖分析後間隔 1 秒")
        deadline = time.monotonic() + self.timeout_seconds if self.timeout_seconds else None
        while not self.stop.is_set():
            before = time.time()
            try:
                self.request_screenshot()
                shots = self._wait_for_screenshots(before)
                if not shots:
                    self.on_log("BT：等待螢幕截圖逾時，將重試")
                else:
                    if self._analyse_screenshots(shots):
                        return
            except Exception as exc:
                self.on_log(f"BT STATUS 畫面分析失敗：{exc}")
            if deadline is not None and time.monotonic() >= deadline:
                pending = [sn for sn in self.sns if sn not in self.reported]
                if pending and self.on_timeout:
                    self.on_timeout(pending)
                return
            if self.stop.wait(1.0):
                return

    def _wait_for_screenshots(self, before: float) -> list[Path]:
        # Do not assume that a five-second macOS thumbnail delay is exact.
        deadline = time.monotonic() + SCREENSHOT_TIMEOUT_SECONDS
        while not self.stop.is_set() and time.monotonic() < deadline:
            shots = new_screenshots(self.screenshot_root, before)
            if shots:
                return shots
            self.stop.wait(.25)
        return []

    def _analyse_screenshots(self, shots: list[Path]) -> bool:
        selected: Optional[Path] = None
        statuses: list[str] = []
        status_rows: list[BtStatusRow] = []
        errors: list[str] = []
        for shot in shots:
            try:
                # The BT window template is needed only once to find the Start
                # button.  During a test the browser can resize/reflow, while
                # the status-cell templates remain sufficient and avoid a
                # false failure caused by the decorative "BT" title.
                status_rows = bt_status_rows_from_screen(shot, self.status_templates)
                statuses = [row.status for row in status_rows]
                selected = shot
                break
            except AgentError as exc:
                errors.append(f"{shot.name}: {exc}")
        if selected is None:
            self.delete_shots(shots)
            raise AgentError("；".join(errors) or "沒有可分析的 BT 截圖")
        summary = ", ".join(f"slot{index + 1}={status}" for index, status in enumerate(statuses))
        self.on_log(f"BT STATUS：{summary}")
        completed = bt_completed_results(self.sns, self.slots, statuses, self.testing_seen)
        waiting = [sn for sn in self.sns if sn not in self.testing_seen]
        if waiting:
            self.on_log("BT：等待所有指定 slot 進入新一輪 TESTING：" + "、".join(waiting))
        elif any(statuses[slot - 1] == "TESTING" for slot in self.slots):
            self.on_log("BT：所有指定 slot 已開始，等待全部 TESTING 結束")
        if len(self.testing_seen) == len(self.sns) and self.machine_sns is None:
            try:
                all_machine_sns = pair_bt_sn_text(status_rows, recognize_text_vision(selected))
                self.machine_sns = [all_machine_sns[slot - 1] for slot in self.slots]
            except AgentError as exc:
                self.machine_sns = ["" for _ in self.sns]
                self.on_log("BT SN OCR 失敗：" + str(exc))
            # Apply the documented O→0 OCR normalization to both values for
            # comparison.  Production barcodes exclude O; this additionally
            # keeps the older BTDEMO simulator names from becoming false
            # mismatches solely because Vision saw their letter O as digit 0.
            expected_for_comparison = [normalize_ocr_sn(sn) for sn in self.sns]
            self.sn_mismatch = self.machine_sns != expected_for_comparison
            self.on_log("BT SN 比對：" + "；".join(
                f"slot{slot} 上位機={expected or '（空）'}／設備={actual or '（未辨識）'}"
                for slot, expected, actual in zip(self.slots, self.sns, self.machine_sns)))
            self.on_log("BT SN 比對結果：" + ("不符，完成後等待人工覆核" if self.sn_mismatch else "一致"))
        # The images have now been read (including OCR if needed) and are not
        # retained on the locked-down production Mac.
        self.delete_shots(shots)
        if not completed:
            return False
        if self.sn_mismatch:
            assert self.machine_sns is not None
            self.on_review(BtSnReview(self.sns, self.machine_sns, self.slots, completed))
            return True
        for sn, slot in zip(self.sns, self.slots):
            if sn in completed and sn not in self.reported:
                self.reported.add(sn)
                status = completed[sn]
                self.on_result(TestResult(sn, status, selected.parent, selected, f"BT 畫面 slot{slot} STATUS={status}"))
        return all(sn in self.reported for sn in self.sns)


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
                 suggested_names: Iterable[str] = ("test_window.png",),
                 capture_screenshot: Optional[Callable[[], Path]] = None) -> None:
        self.window = tk.Toplevel(parent)
        self.window.title("製作圖像匹配模板")
        self.window.transient(parent)
        # macOS 15's Tk/AppKit path can abort while native window zoom creates
        # a new focus surface. Use bounded in-app preview sizes instead.
        self.window.resizable(False, False)
        self.template_root, self.screenshot_root = template_root, screenshot_root
        self.suggested_names = list(suggested_names) or ["test_window.png"]
        self.capture_screenshot = capture_screenshot
        self.capture_results: queue.Queue[tuple[bool, object]] = queue.Queue()
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
        self.capture_button = ttk.Button(controls, text="擷取螢幕截圖", command=self.capture_new_screenshot)
        self.capture_button.pack(side="left", padx=5)
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

    def capture_new_screenshot(self) -> None:
        if self.capture_screenshot is None:
            messagebox.showerror(TITLE, "目前沒有可用的 Arduino 擷取功能", parent=self.window); return
        self.capture_button.state(["disabled"])
        self.info.set("Arduino 正在擷取螢幕截圖，等待 macOS 完成儲存…")

        def run() -> None:
            try:
                image = self.capture_screenshot()
                self.capture_results.put((True, image))
            except Exception as exc:
                self.capture_results.put((False, str(exc)))
        threading.Thread(target=run, daemon=True).start()
        self.window.after(100, self._poll_capture)

    def _poll_capture(self) -> None:
        try:
            success, value = self.capture_results.get_nowait()
        except queue.Empty:
            if self.window.winfo_exists():
                self.window.after(100, self._poll_capture)
            return
        if success:
            self._captured_screenshot(value)
        else:
            self._capture_failed(str(value))

    def _captured_screenshot(self, image: Path) -> None:
        self.capture_button.state(["!disabled"])
        self.load(image)

    def _capture_failed(self, message: str) -> None:
        self.capture_button.state(["!disabled"])
        self.info.set("擷取截圖失敗")
        messagebox.showerror(TITLE, message, parent=self.window)

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
        self.root.geometry("940x700")
        self.pref_file = Path.home() / "Library" / "Application Support" / "AtlasAgentB518" / "preferences.json"
        pref = Preferences.load(self.pref_file)
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.hid_replies: queue.Queue[str] = queue.Queue()
        self.link = SerialLink(lambda line: self.events.put(("serial", line)))
        self.monitor_stop = threading.Event()
        self.monitor: Optional[threading.Thread] = None
        self.sns: list[str] = []
        self.slots: list[int] = []
        self.current_job_id = ""
        self.current_station = "DFU"
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
        self.result_timeout = tk.StringVar(value=str(pref.result_timeout_seconds))
        self.overlay_path = self.pref_file.with_name("last_match_overlay.png")
        self.station = tk.StringVar(value=pref.station if pref.station in ("DFU", "FCT", "BT") else "DFU")
        self.current_station = self.station.get()
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
        hid = ttk.Frame(panel); hid.pack(fill="x", pady=(8, 0))
        ttk.Button(hid, text="設定 HID", command=self.open_hid_settings).pack(side="left")
        ttk.Label(hid, text="設定滑鼠模式、比例、偏移與每步延遲", foreground="#555").pack(side="left", padx=8)
        ttk.Button(hid, text="查看匹配疊圖", command=self.show_match_overlay).pack(side="right")
        profile = ttk.Frame(panel); profile.pack(fill="x", pady=(8, 0))
        ttk.Label(profile, text="DFU 畫面設定：").pack(side="left")
        ttk.Combobox(profile, textvariable=self.dfu_profile, width=30, state="readonly",
                     values=("b482_dfu2", "generic", "b482_dfu1_manual")).pack(side="left")
        ttk.Label(profile, text="  B482 DFU_2：每個 SN 輸入後按 OK；DFU_1 尚待確認輸入步驟。").pack(side="left")
        timeout = ttk.Frame(panel); timeout.pack(fill="x", pady=(6, 0))
        ttk.Label(timeout, text="測試結果逾時(s)：").pack(side="left")
        ttk.Entry(timeout, textvariable=self.result_timeout, width=8).pack(side="left", padx=4)
        ttk.Label(timeout, text="0 表示不逾時；逾時的未完成 SN 回報 TIMEOUT。", foreground="#555").pack(side="left")
        batch = ttk.LabelFrame(panel, text="當前測試條碼（由 Arduino TCP→USB CDC 收到；也可手動驗證）", padding=8); batch.pack(fill="x", pady=10)
        ttk.Entry(batch, textvariable=self.sn_text).pack(side="left", fill="x", expand=True)
        ttk.Button(batch, text="開始流程", command=lambda: self.start_batch(self.sn_text.get())).pack(side="left", padx=(5, 0))
        self.bt_channel_buttons = ttk.Frame(batch); self.bt_channel_buttons.pack(side="left", padx=(5, 0))
        for slot in range(1, 5):
            ttk.Button(self.bt_channel_buttons, text=f"BT Start {slot}", command=lambda n=slot: self.start_bt_channel(n)).pack(side="left", padx=2)
        ttk.Button(batch, text="本機模擬", command=lambda: self.start_local_demo(self.sn_text.get())).pack(side="left", padx=(5, 0))
        ttk.Button(batch, text="停止監聽", command=self.stop_monitor).pack(side="left", padx=(5, 0))
        ttk.Checkbutton(panel, text="本機模擬最後一台 FAIL（僅寫入目前 CSV 根路徑）", variable=self.demo_fail_last).pack(anchor="w")
        self.sn_display = ttk.Label(panel, text="尚無測試中的 SN", anchor="w"); self.sn_display.pack(fill="x")
        ip = ttk.LabelFrame(panel, text="Arduino 網路設定", padding=8); ip.pack(fill="x", pady=10)
        ttk.Label(ip, textvariable=self.ip_text).pack(side="left", fill="x", expand=True)
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
        return self.parse_hid_settings_values(self.hid_delay.get(), self.hid_scale_x.get(), self.hid_scale_y.get(),
                                              self.hid_offset_x.get(), self.hid_offset_y.get(), self.hid_mode.get(),
                                              self.absolute_width.get(), self.absolute_height.get())

    @staticmethod
    def parse_hid_settings_values(delay_text: str, scale_x_text: str, scale_y_text: str,
                                  offset_x_text: str, offset_y_text: str, mode: str,
                                  absolute_width_text: str, absolute_height_text: str) -> tuple[float, float, float, float, float, str, int, int]:
        try:
            delay = float(delay_text)
            scale_x, scale_y = float(scale_x_text), float(scale_y_text)
            offset_x, offset_y = float(offset_x_text), float(offset_y_text)
            absolute_width, absolute_height = int(absolute_width_text), int(absolute_height_text)
        except ValueError as exc:
            raise AgentError("HID 延遲、比例與偏移必須是數字") from exc
        if delay < 0:
            raise AgentError("HID 每步延遲不可小於 0")
        hid_coordinate((0, 0), scale_x, scale_y, offset_x, offset_y)
        if mode not in ("relative", "absolute"):
            raise AgentError("HID 模式必須是 relative 或 absolute")
        if mode == "absolute":
            absolute_hid_report_coordinate((0, 0), absolute_width, absolute_height)
        return delay, scale_x, scale_y, offset_x, offset_y, mode, absolute_width, absolute_height

    def open_hid_settings(self) -> None:
        """Keep advanced HID calibration out of the compact main HMI."""
        dialog = tk.Toplevel(self.root)
        dialog.title("HID 設定")
        dialog.transient(self.root)
        dialog.resizable(False, False)
        frame = ttk.Frame(dialog, padding=14); frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Arduino HID 控制設定", font=("TkDefaultFont", 14, "bold")).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 10))
        ttk.Label(frame, text="這些值只影響 Arduino 的滑鼠 HID 指令，不會使用 macOS 軟體鍵盤／滑鼠控制。", foreground="#555").grid(row=1, column=0, columnspan=4, sticky="w", pady=(0, 12))

        delay = tk.StringVar(value=self.hid_delay.get())
        scale_x, scale_y = tk.StringVar(value=self.hid_scale_x.get()), tk.StringVar(value=self.hid_scale_y.get())
        offset_x, offset_y = tk.StringVar(value=self.hid_offset_x.get()), tk.StringVar(value=self.hid_offset_y.get())
        mode = tk.StringVar(value=self.hid_mode.get())
        absolute_width, absolute_height = tk.StringVar(value=self.absolute_width.get()), tk.StringVar(value=self.absolute_height.get())
        auto_scale = tk.BooleanVar(value=self.auto_scale.get())

        ttk.Label(frame, text="每步延遲（秒）：").grid(row=2, column=0, sticky="w", pady=3)
        ttk.Entry(frame, textvariable=delay, width=10).grid(row=2, column=1, sticky="w")
        ttk.Checkbutton(frame, text="依截圖／顯示器自動計算比例", variable=auto_scale).grid(row=2, column=2, columnspan=2, sticky="w", padx=(16, 0))
        ttk.Label(frame, text="X / Y 比例：").grid(row=3, column=0, sticky="w", pady=3)
        ttk.Entry(frame, textvariable=scale_x, width=10).grid(row=3, column=1, sticky="w")
        ttk.Entry(frame, textvariable=scale_y, width=10).grid(row=3, column=2, sticky="w", padx=(8, 0))
        ttk.Label(frame, text="X / Y 偏移：").grid(row=4, column=0, sticky="w", pady=3)
        ttk.Entry(frame, textvariable=offset_x, width=10).grid(row=4, column=1, sticky="w")
        ttk.Entry(frame, textvariable=offset_y, width=10).grid(row=4, column=2, sticky="w", padx=(8, 0))
        ttk.Label(frame, text="HID 模式：").grid(row=5, column=0, sticky="w", pady=3)
        ttk.Combobox(frame, textvariable=mode, values=("relative", "absolute"), width=12, state="readonly").grid(row=5, column=1, sticky="w")
        ttk.Label(frame, text="absolute 虛擬桌面（邏輯點）：").grid(row=6, column=0, sticky="w", pady=3)
        ttk.Entry(frame, textvariable=absolute_width, width=10).grid(row=6, column=1, sticky="w")
        ttk.Label(frame, text="×").grid(row=6, column=2, sticky="w", padx=(8, 2))
        ttk.Entry(frame, textvariable=absolute_height, width=10).grid(row=6, column=3, sticky="w")
        ttk.Label(frame, text="例：單一 Retina 顯示器為 1440 × 900", foreground="#555").grid(row=7, column=0, columnspan=4, sticky="w", pady=(3, 0))

        def save() -> None:
            try:
                self.parse_hid_settings_values(delay.get(), scale_x.get(), scale_y.get(), offset_x.get(), offset_y.get(),
                                               mode.get(), absolute_width.get(), absolute_height.get())
            except AgentError as exc:
                messagebox.showerror(TITLE, str(exc), parent=dialog); return
            self.hid_delay.set(delay.get()); self.hid_scale_x.set(scale_x.get()); self.hid_scale_y.set(scale_y.get())
            self.hid_offset_x.set(offset_x.get()); self.hid_offset_y.set(offset_y.get()); self.hid_mode.set(mode.get())
            self.absolute_width.set(absolute_width.get()); self.absolute_height.set(absolute_height.get())
            self.auto_scale.set(auto_scale.get())
            dialog.destroy()

        buttons = ttk.Frame(frame); buttons.grid(row=8, column=0, columnspan=4, sticky="e", pady=(14, 0))
        ttk.Button(buttons, text="取消", command=dialog.destroy).pack(side="right")
        ttk.Button(buttons, text="套用", command=save).pack(side="right", padx=(0, 6))
        dialog.grab_set()

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
        if station == "FCT":
            TemplateMakerDialog(self.root, template_root, screenshot_root,
                                list(FCT_CHECKBOX_TEMPLATES.values()), self.capture_template_screenshot)
            return
        profile = VISUAL_PROFILES[self.dfu_profile.get() if station == "DFU" else "b482_bt"]
        suggested = [profile["window"]]
        suggested.extend(profile[key] for key in ("barcode", "ok", "start", "checkbox_checked", "checkbox_unchecked") if key in profile)
        if station == "BT":
            suggested.extend(profile["starts"].values())
            suggested.extend(profile["status"].values())
        TemplateMakerDialog(self.root, template_root, screenshot_root, suggested, self.capture_template_screenshot)

    def capture_template_screenshot(self) -> Path:
        """Ask Arduino for a fresh screenshot and return the newest generated file."""
        screenshot_root = Path(self.screenshot_path.get()).expanduser()
        if not screenshot_root.is_dir():
            raise AgentError("請先選擇有效的螢幕截圖路徑")
        before = time.time()
        self.link.send("SCREENSHOT")
        self.events.put(("log", "TX: SCREENSHOT（製作模板）"))
        time.sleep(SCREENSHOT_SETTLE_SECONDS)
        deadline = time.monotonic() + (SCREENSHOT_TIMEOUT_SECONDS - SCREENSHOT_SETTLE_SECONDS)
        shots: list[Path] = []
        while time.monotonic() < deadline and not shots:
            shots = new_screenshots(screenshot_root, before)
            time.sleep(.25)
        if not shots:
            raise AgentError(f"等待 Arduino 產生螢幕截圖逾時（共 {SCREENSHOT_TIMEOUT_SECONDS:g} 秒）")
        self.events.put(("log", f"模板截圖完成：{shots[0].name}（共 {len(shots)} 張）"))
        return shots[0]

    def append(self, text: str) -> None:
        self.output.configure(state="normal"); self.output.insert("end", text + "\n"); self.output.see("end"); self.output.configure(state="disabled")

    def connect(self) -> None:
        try:
            self.link.connect(self.port.get().strip())
            self.append("USB CDC 已連線；自動查詢 Arduino IP")
            self.ip_text.set("IP：查詢中…")
            self.safe_send("GET_IP")
        except (AgentError, OSError) as exc: messagebox.showerror(TITLE, str(exc))

    def safe_send(self, command: str) -> None:
        try: self.link.send(command); self.append("TX: " + command)
        except AgentError as exc: messagebox.showerror(TITLE, str(exc))

    def command_from_payload(self, payload: str, bt_slot: Optional[int] = None) -> TestCommand:
        value = payload.strip()
        if re.match(r"^(DFU|FCT|BT):", value, re.IGNORECASE):
            if bt_slot is not None:
                raise AgentError("結構化 JOB 指令不可再指定手動 BT slot")
            return parse_test_command(value)
        sns = parse_barcodes(value)
        if bt_slot is not None:
            if len(sns) != 1 and len(sns) < bt_slot:
                raise AgentError(f"BT Start {bt_slot} 需要輸入第 {bt_slot} 個 SN（以逗號排列 slot 1～4）")
            sns = [sns[0] if len(sns) == 1 else sns[bt_slot - 1]]
            slots = [bt_slot]
        else:
            slots = list(range(1, len(sns) + 1))
        job_id = "LOCAL-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        return TestCommand(self.station.get(), job_id, tuple(zip(slots, sns)))

    def validate_batch(self, payload: str, bt_slot: Optional[int] = None) -> Optional[tuple[Path, TestCommand]]:
        try:
            root_text = self.csv_path.get().strip()
            root = Path(root_text).expanduser() if root_text else Path(".")
            if self.station.get() != "BT" and not root.is_dir():
                raise AgentError("請選擇有效的 CSV 根路徑")
            command = self.command_from_payload(payload, bt_slot)
            if command.station != self.station.get():
                raise AgentError(f"收到 {command.station} JOB，但本機工站設定為 {self.station.get()}")
        except AgentError as exc:
            messagebox.showerror(TITLE, str(exc)); return None
        return root, command

    def prepare_batch(self, payload: str, bt_slot: Optional[int] = None) -> Optional[tuple[Path, TestCommand, int, float, float]]:
        validated = self.validate_batch(payload, bt_slot)
        if validated is None:
            return None
        try:
            result_timeout = float(self.result_timeout.get())
            if result_timeout < 0:
                raise ValueError
        except ValueError:
            messagebox.showerror(TITLE, "測試結果逾時必須是大於或等於 0 的秒數"); return None
        root, command = validated
        self.stop_monitor()
        self.sns, self.slots = command.sns, command.slots
        self.current_job_id, self.current_station = command.job_id, command.station
        self.batch_results = {}; self.reported_batch_number = None
        self.sn_display.configure(text=f"當前 JOB：{command.job_id}；" + "、".join(
            f"slot{slot}={sn}" for slot, sn in command.assignments))
        self.batch_number += 1
        return root, command, self.batch_number, time.time(), result_timeout

    def start_batch(self, payload: str, bt_slot: Optional[int] = None) -> Optional[list[str]]:
        prepared = self.prepare_batch(payload, bt_slot)
        if prepared is None:
            return None
        root, command, batch_number, created_after, result_timeout = prepared
        if command.station in ("DFU", "BT"):
            threading.Thread(target=self.visual_start,
                             args=(command.station, command.sns, command.slots, root, batch_number,
                                   created_after, result_timeout), daemon=True).start()
        elif command.slots != [1, 2, 3, 4]:
            # A full FCT tray uses the normal fixture workflow.  A sparse JOB
            # must first synchronize the visible checkbox state with the
            # requested slots, otherwise a fixture insertion can test stale
            # slot 2/3 selections.
            threading.Thread(target=self.configure_fct_sparse_slots,
                             args=(command.slots, root, command.sns, batch_number,
                                   created_after, result_timeout), daemon=True).start()
        else:
            self.start_monitor(root, command.sns, batch_number, created_after, result_timeout)
        return command.sns

    def start_bt_channel(self, slot: int) -> None:
        if self.station.get() != "BT":
            messagebox.showinfo(TITLE, "請先將工站切換為 BT，再使用個別通道 Start 按鈕。", parent=self.root)
            return
        self.start_batch(self.sn_text.get(), bt_slot=slot)

    def start_local_demo(self, payload: str) -> None:
        validated = self.validate_batch(payload)
        if validated is None:
            return
        root, command = validated
        sns = command.sns
        if not messagebox.askyesno(TITLE, f"將在下列 CSV 根路徑建立本機模擬資料：\n{root}\n\n不會使用 Arduino 或影像匹配。", parent=self.root):
            return
        prepared = self.prepare_batch(payload)
        if prepared is None:
            return
        root, command, batch_number, created_after, result_timeout = prepared
        sns = command.sns
        station = self.station.get()
        fail_last = self.demo_fail_last.get()
        self.start_monitor(root, sns, batch_number, created_after, result_timeout)

        def run() -> None:
            try:
                write_local_demo_results(root, sns, station, fail_last, self.monitor_stop)
            except OSError as exc:
                self.events.put(("log", f"本機模擬寫入失敗：{exc}"))
        threading.Thread(target=run, daemon=True).start()
        self.append(f"本機模擬已啟動：{station}／{', '.join(sns)}")

    def start_monitor(self, root: Path, sns: list[str], batch_number: int, created_after: float, result_timeout: float) -> None:
        self.monitor_stop = threading.Event()
        log_root = Path(self.log_path.get()).expanduser()
        if not log_root.is_dir(): log_root = root
        self.monitor = FolderMonitor(root, log_root, sns, lambda item: self.events.put(("log", item)),
                                     lambda result: self.events.put(("result", (batch_number, result))), self.monitor_stop,
                                     created_after, result_timeout,
                                     lambda pending: self.events.put(("timeout", (batch_number, pending))))
        self.monitor.start()

    def start_bt_status_monitor(self, sns: list[str], slots: list[int], batch_number: int, result_timeout: float,
                                status_templates: dict[str, Path]) -> None:
        screenshot_root = Path(self.screenshot_path.get()).expanduser()
        if not screenshot_root.is_dir():
            self.append("BT STATUS 監聽未啟動：請選擇有效的螢幕截圖路徑")
            return
        self.monitor_stop = threading.Event()

        def request() -> None:
            self.link.send("SCREENSHOT")
            self.events.put(("log", "TX: SCREENSHOT（BT STATUS）"))

        self.monitor = BtStatusMonitor(screenshot_root, status_templates, sns, slots, request,
                                       lambda item: self.events.put(("log", item)),
                                       lambda result: self.events.put(("result", (batch_number, result))),
                                       lambda review: self.events.put(("bt_sn_review", (batch_number, review))),
                                       self.delete_processed_screenshots, self.monitor_stop, result_timeout,
                                       lambda pending: self.events.put(("timeout", (batch_number, pending))))
        self.monitor.start()

    def review_bt_sn_mismatch(self, review: BtSnReview) -> Optional[list[str]]:
        """Ask a human to confirm/correct machine SNs after BT has finished."""
        dialog = tk.Toplevel(self.root)
        dialog.title("BT SN 不符人工覆核")
        dialog.transient(self.root)
        dialog.resizable(False, False)
        result: dict[str, Optional[list[str]]] = {"sns": None}
        frame = ttk.Frame(dialog, padding=14); frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="BT 已完成測試，但設備畫面 SN 與上位機 SN 不一致。\n請核對設備實際 SN；確認後將以此處 SN 回傳 RESULT。",
                  foreground="#9b1c1c").grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 10))
        for column, label in enumerate(("Slot", "上位機 SN", "設備 OCR SN（可修正）", "測試結果")):
            ttk.Label(frame, text=label).grid(row=1, column=column, sticky="w", padx=(0, 12), pady=(0, 4))
        fields: list[tk.StringVar] = []
        for index, (slot, expected, actual) in enumerate(zip(review.slots, review.expected_sns, review.machine_sns), start=2):
            field = tk.StringVar(value=actual)
            fields.append(field)
            ttk.Label(frame, text=f"slot{slot}").grid(row=index, column=0, sticky="w")
            ttk.Label(frame, text=expected or "（空）").grid(row=index, column=1, sticky="w", padx=(0, 12))
            ttk.Entry(frame, textvariable=field, width=30).grid(row=index, column=2, sticky="ew", padx=(0, 12), pady=3)
            ttk.Label(frame, text=review.results.get(expected, "—")).grid(row=index, column=3, sticky="w")

        def confirm() -> None:
            try:
                values = [normalize_ocr_sn(item.get()) for item in fields]
                parsed = parse_barcodes(",".join(values))
                if len(parsed) != len(values) or len(set(parsed)) != len(parsed):
                    raise AgentError("設備實際 SN 必須完整且不可重複")
            except AgentError as exc:
                messagebox.showerror(TITLE, str(exc), parent=dialog); return
            result["sns"] = parsed
            dialog.destroy()

        buttons = ttk.Frame(frame); buttons.grid(row=len(fields) + 2, column=0, columnspan=4, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="取消並回報 NACK", command=dialog.destroy).pack(side="right")
        ttk.Button(buttons, text="確認並以設備 SN 回報", command=confirm).pack(side="right", padx=6)
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        dialog.grab_set(); self.root.wait_window(dialog)
        return result["sns"]

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

    def delete_processed_screenshots(self, shots: Iterable[Path]) -> None:
        deleted, failed = delete_screenshots(shots)
        if deleted:
            self.events.put(("log", "已刪除本次分析截圖：" + "、".join(item.name for item in deleted)))
        if failed:
            self.events.put(("log", "無法刪除截圖：" + "、".join(item.name for item in failed)))

    def ensure_slot_checkbox_states(self, slots: list[int], screenshot_dir: Path, window_template: Path,
                                    checked_template: Path, unchecked_template: Path,
                                    target_for: Callable[[tuple[int, int]], tuple[int, int]],
                                    hid_mode: str, delay: float) -> None:
        """Verify sparse-slot checkbox state after HID clicks, correcting once.

        Sending a click command is not evidence that a browser accepted it.
        Read a new Arduino screenshot after the click and refuse to continue to
        barcode entry unless all four visible controls match the JOB exactly.
        """
        for attempt in range(2):
            before = time.time(); self.link.send("SCREENSHOT")
            self.events.put(("log", f"驗證 Slot checkbox（第 {attempt + 1} 次截圖）…"))
            time.sleep(SCREENSHOT_SETTLE_SECONDS)
            deadline = time.monotonic() + (SCREENSHOT_TIMEOUT_SECONDS - SCREENSHOT_SETTLE_SECONDS)
            shots: list[Path] = []
            while time.monotonic() < deadline and not shots:
                shots = new_screenshots(screenshot_dir, before); time.sleep(.25)
            if not shots:
                raise AgentError(f"驗證 Slot checkbox 時等待螢幕截圖逾時（共 {SCREENSHOT_TIMEOUT_SECONDS:g} 秒）")
            selected = None; states = None; errors: list[str] = []
            for shot in shots:
                try:
                    template_match(shot, window_template)
                    selected, states = shot, slot_checkbox_states(shot, checked_template, unchecked_template)
                    break
                except AgentError as exc:
                    errors.append(f"{shot.name}: {exc}")
            self.delete_processed_screenshots(shots)
            if selected is None or states is None:
                raise AgentError("無法驗證四個 Slot checkbox。" + "；".join(errors))
            mismatches = [(index, rectangle, required) for index, (checked, rectangle) in enumerate(states, start=1)
                          for required in (index in slots,) if checked != required]
            current = "、".join(f"slot{index}={'勾選' if checked else '取消'}" for index, (checked, _) in enumerate(states, start=1))
            if not mismatches:
                self.events.put(("log", "Slot checkbox 驗證成功：" + current))
                return
            if attempt:
                raise AgentError("Slot checkbox 驗證失敗，HMI 實際狀態為：" + current +
                                 "；已停止，未輸入任何條碼。請檢查 checkbox 模板與 HMI 焦點。")
            self.events.put(("log", "Slot checkbox 尚未符合 JOB，補正：" + "、".join(
                f"slot{index}={'勾選' if required else '取消'}" for index, _, required in mismatches)))
            commands: list[str] = []
            for _, rectangle, _ in mismatches:
                commands.extend(click_commands(target_for(rectangle_center(rectangle)), hid_mode))
            self.send_hid_sequence(commands, delay=delay)
        raise AgentError("Slot checkbox 驗證流程異常")

    def configure_fct_sparse_slots(self, slots: list[int], csv_root: Path, sns: list[str], batch_number: int,
                                   created_after: float, result_timeout: float) -> None:
        """Set FCT's four visible test checkboxes before beginning file monitoring."""
        try:
            delay, scale_x, scale_y, offset_x, offset_y, hid_mode, absolute_width, absolute_height = self.hid_settings()
            templates = Path(self.template_path.get()).expanduser()
            resolved = {name: resolve_template_path(templates, item) for name, item in FCT_CHECKBOX_TEMPLATES.items()}
            missing = [FCT_CHECKBOX_TEMPLATES[name] for name, path in resolved.items() if not path.is_file()]
            if missing:
                raise AgentError("缺少 FCT sparse slot 模板：" + "、".join(missing) +
                                 f"\n目前模板根路徑：{templates}\n請切換 FCT 後用「製作模板」建立 fct_window、slot_checkbox_checked、slot_checkbox_unchecked。")
            screenshot_dir = Path(self.screenshot_path.get()).expanduser()
            if not screenshot_dir.is_dir():
                raise AgentError("請選擇有效的螢幕截圖路徑")
            before = time.time(); self.link.send("SCREENSHOT")
            self.events.put(("log", f"FCT sparse slot：等待 {SCREENSHOT_SETTLE_SECONDS:g} 秒讓 macOS 完成儲存螢幕截圖…"))
            time.sleep(SCREENSHOT_SETTLE_SECONDS)
            deadline = time.monotonic() + (SCREENSHOT_TIMEOUT_SECONDS - SCREENSHOT_SETTLE_SECONDS)
            shots: list[Path] = []
            while time.monotonic() < deadline and not shots:
                shots = new_screenshots(screenshot_dir, before); time.sleep(.25)
            if not shots:
                raise AgentError(f"等待 Arduino 產生螢幕截圖逾時（共 {SCREENSHOT_TIMEOUT_SECONDS:g} 秒）")
            shot = None; window_rect = None; states = None; errors: list[str] = []
            for candidate in shots:
                try:
                    candidate_window = template_match(candidate, resolved["window"])
                    candidate_states = slot_checkbox_states(candidate, resolved["checked"], resolved["unchecked"])
                    shot, window_rect, states = candidate, candidate_window, candidate_states
                    break
                except AgentError as exc:
                    errors.append(f"{candidate.name}: {exc}")
            if shot is None or window_rect is None or states is None:
                raise AgentError("所有新截圖均無法定位 FCT 視窗與四個 checkbox。\n" + "\n".join(errors))
            if self.auto_scale.get():
                automatic_scale = macos_screenshot_scale(shot)
                if automatic_scale:
                    scale_x, scale_y = automatic_scale; self.events.put(("auto_scale", automatic_scale))
            def target_for(source: tuple[int, int]) -> tuple[int, int]:
                logical = hid_coordinate(source, scale_x, scale_y, offset_x, offset_y)
                return absolute_hid_report_coordinate(logical, absolute_width, absolute_height) if hid_mode == "absolute" else logical
            focus = target_for(rectangle_center(window_rect))
            commands = click_commands(focus, hid_mode)
            changes: list[str] = []
            for index, (is_checked, rectangle) in enumerate(states, start=1):
                required = index in slots
                if is_checked != required:
                    commands.extend(click_commands(target_for(rectangle_center(rectangle)), hid_mode))
                    changes.append(f"slot{index}={'勾選' if required else '取消'}")
            write_match_overlay(shot, [("FCT window", window_rect, focus),
                                       *((f"slot{index} {'checked' if checked else 'unchecked'}", rect,
                                          target_for(rectangle_center(rect)))
                                         for index, (checked, rect) in enumerate(states, start=1))], self.overlay_path)
            self.delete_processed_screenshots(shots)
            self.send_hid_sequence(commands, delay=delay)
            self.ensure_slot_checkbox_states(slots, screenshot_dir, resolved["window"], resolved["checked"],
                                             resolved["unchecked"], target_for, hid_mode, delay)
            self.events.put(("log", "FCT sparse slot 已同步：" + ("、".join(changes) if changes else "checkbox 已符合 JOB") + "；啟動 CSV 監聽"))
            self.events.put(("begin_monitor", (csv_root, sns, batch_number, created_after, result_timeout)))
        except Exception as exc:
            self.events.put(("log", f"FCT sparse slot 流程失敗：{exc}"))
            self.events.put(("start_failed", ("FCT", batch_number)))

    def visual_start(self, station: str, sns: list[str], slots: list[int], csv_root: Path, batch_number: int,
                     created_after: float, result_timeout: float) -> None:
        """Ask Arduino HID for screenshot/actions; no Mac input API is invoked here."""
        try:
            if station == "DFU" and self.dfu_profile.get() == "b482_dfu1_manual":
                raise AgentError("B482 DFU_1 畫面尚未確認 SN 輸入方式；請選擇 b482_dfu2 或 generic")
            delay, scale_x, scale_y, offset_x, offset_y, hid_mode, absolute_width, absolute_height = self.hid_settings()
            profile = VISUAL_PROFILES[self.dfu_profile.get() if station == "DFU" else "b482_bt"]
            templates = Path(self.template_path.get()).expanduser()
            if station == "DFU":
                required = [profile["window"], profile["barcode"]]
                if slots != [1, 2, 3, 4] and profile["input_mode"] == "ok_each":
                    required.extend((profile["checkbox_checked"], profile["checkbox_unchecked"]))
            else:
                start_templates = ([profile["start"]] if slots == [1, 2, 3, 4]
                                   else [profile["starts"][slot] for slot in slots])
                required = [profile["window"], *start_templates, *profile["status"].values()]
            if station == "DFU" and profile["input_mode"] == "ok_each":
                required.append(profile["ok"])
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
                # Bring the HMI/browser to the foreground before the first
                # input click. The matched title region is deliberately a
                # non-interactive, safe part of the test window.
                focus_commands = click_commands(target_for(window_center), hid_mode)
                sparse_checkbox_job = slots != [1, 2, 3, 4] and profile["input_mode"] == "ok_each"
                if sparse_checkbox_job:
                    states = slot_checkbox_states(shot, resolved[profile["checkbox_checked"]],
                                                   resolved[profile["checkbox_unchecked"]], region=region)
                    for index, (is_checked, rectangle) in enumerate(states, start=1):
                        target = target_for(rectangle_center(rectangle))
                        matches.append((match_label(f"slot{index} {'checked' if is_checked else 'unchecked'}",
                                                    rectangle_center(rectangle)), rectangle, target))
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
                    self.delete_processed_screenshots(shots)
                    self.send_hid_sequence(focus_commands, delay=delay)
                    if sparse_checkbox_job:
                        self.ensure_slot_checkbox_states(slots, screenshot_dir, window,
                                                         resolved[profile["checkbox_checked"]],
                                                         resolved[profile["checkbox_unchecked"]],
                                                         target_for, hid_mode, delay)
                    self.send_hid_sequence(dfu_ok_each_commands(sns, barcode, button, hid_mode), delay=delay)
                    self.events.put(("log", f"DFU（{hid_mode}）：已點擊測試視窗取得焦點；截圖 SN {barcode_source} → HID {barcode}，OK {button_source} → HID {button}；全部 SN 輸入完成，啟動監聽"))
                else:
                    commands = focus_commands + click_commands(barcode, hid_mode)
                    commands.extend(dfu_tab_slot_commands(zip(slots, sns)))
                    button_rect = template_match(shot, resolved[profile["start"]], region=region)
                    button_source = rectangle_center(button_rect)
                    button = target_for(button_source)
                    matches.append((match_label("Start", button_source), button_rect, button))
                    write_match_overlay(shot, matches, self.overlay_path)
                    self.delete_processed_screenshots(shots)
                    self.send_hid_sequence(commands + click_commands(button, hid_mode), delay=delay)
                    self.events.put(("log", f"DFU：視窗定位 {window_center}，開始按鈕 {button}；啟動監聽"))
            else:
                use_start_all = slots == [1, 2, 3, 4]
                selected_starts = ([("Start All", profile["start"])] if use_start_all else
                                   [(f"Start {slot}", profile["starts"][slot]) for slot in slots])
                buttons: list[tuple[str, tuple[int, int]]] = []
                for button_label, template_name in selected_starts:
                    button_rect = template_match(shot, resolved[template_name], region=region)
                    button_source = rectangle_center(button_rect)
                    button = target_for(button_source)
                    buttons.append((button_label, button))
                    matches.append((match_label(button_label, button_source), button_rect, button))
                write_match_overlay(shot, matches, self.overlay_path)
                self.delete_processed_screenshots(shots)
                # Click the harmless BT title first.  This brings the Safari/
                # instrument window to the foreground so the following Start
                # click is not lost to another focused application.
                focus = target_for(rectangle_center(window_rect))
                commands = click_commands(focus, hid_mode)
                for _, button in buttons:
                    commands.extend(click_commands(button, hid_mode))
                self.send_hid_sequence(commands, delay=delay)
                self.events.put(("log", "BT：已點擊測試畫面取得焦點並啟動 " +
                                 "、".join(label for label, _ in buttons) + "；啟動畫面 STATUS 監聽"))
            if station == "BT":
                self.events.put(("begin_bt_status_monitor", (sns, slots, batch_number, result_timeout,
                                                               {state: resolved[name] for state, name in profile["status"].items()})))
            else:
                self.events.put(("begin_monitor", (csv_root, sns, batch_number, created_after, result_timeout)))
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

    def report_if_batch_complete(self, batch_number: int) -> None:
        if self.reported_batch_number == batch_number or not all(sn in self.batch_results for sn in self.sns):
            return
        report = batch_result_report(self.current_station, self.current_job_id,
                                     zip(self.slots, self.sns), self.batch_results)
        self.reported_batch_number = batch_number
        self.monitor = None
        if self.link.connection:
            self.safe_send(report)
        else:
            self.append("未連線 Arduino，略過上報：" + report)

    def remote_batch_active(self) -> bool:
        return bool(self.sns) and self.reported_batch_number != self.batch_number

    def accept_remote_command(self, line: str) -> None:
        try:
            command = parse_test_command(line)
        except AgentError as exc:
            self.append("工作指令拒絕：" + str(exc))
            self.safe_send("NACK:INVALID_COMMAND")
            return
        nack_header = f"NACK:{command.station}:JOB={command.job_id};"
        if command.station != self.station.get():
            self.append(f"拒絕 JOB {command.job_id}：指令工站 {command.station} 與本機 {self.station.get()} 不符")
            self.safe_send(nack_header + "WRONG_STATION")
            return
        if self.remote_batch_active():
            self.append(f"拒絕 JOB {command.job_id}：目前 JOB {self.current_job_id} 尚未完成")
            self.safe_send(nack_header + "BUSY")
            return
        accepted = self.start_batch(line)
        if accepted is None:
            self.safe_send(nack_header + "REJECTED")
            return
        self.safe_send(f"ACK:{command.station}:JOB={command.job_id}")

    def process_events(self) -> None:
        try:
            while True:
                kind, item = self.events.get_nowait()
                if kind == "serial":
                    line = str(item); self.append("RX: " + line)
                    self.hid_replies.put(line)
                    if re.match(r"^(DFU|FCT|BT):", line, re.IGNORECASE):
                        try:
                            self.accept_remote_command(line)
                        except Exception as exc: self.append("ERR: 無法啟動批次：" + str(exc))
                    else:
                        payload = incoming_barcode_payload(line)
                        if payload is not None:
                            try:
                                self.start_batch(payload)
                            except Exception as exc: self.append("ERR: 無法啟動批次：" + str(exc))
                        else:
                            ip = arduino_ip_reply(line)
                            if ip:
                                self.ip_text.set("IP:" + ip)
                elif kind == "log": self.append(str(item))
                elif kind == "auto_scale":
                    scale_x, scale_y = item
                    self.hid_scale_x.set(f"{scale_x:g}")
                    self.hid_scale_y.set(f"{scale_y:g}")
                elif kind == "begin_monitor":
                    root, sns, batch_number, created_after, result_timeout = item
                    if batch_number == self.batch_number:
                        self.start_monitor(root, sns, batch_number, created_after, result_timeout)
                    else:
                        self.append("略過已被新批次取代的影像流程")
                elif kind == "begin_bt_status_monitor":
                    sns, slots, batch_number, result_timeout, status_templates = item
                    if batch_number == self.batch_number:
                        self.start_bt_status_monitor(sns, slots, batch_number, result_timeout, status_templates)
                    else:
                        self.append("略過已被新批次取代的 BT 影像流程")
                elif kind == "bt_sn_review":
                    batch_number, review = item; assert isinstance(review, BtSnReview)
                    if batch_number != self.batch_number:
                        self.append("略過舊批次的 BT SN 覆核")
                        continue
                    actual_sns = self.review_bt_sn_mismatch(review)
                    self.monitor = None
                    if actual_sns is None:
                        self.append("BT SN 覆核取消：不回傳 RESULT，改送 NACK:BT_SN_MISMATCH")
                        if self.link.connection:
                            self.safe_send(f"NACK:BT:JOB={self.current_job_id};BT_SN_MISMATCH")
                        self.reported_batch_number = batch_number
                        continue
                    self.append("BT SN 覆核確認：以設備 SN 回傳：" + "、".join(actual_sns))
                    self.sns, self.batch_results = actual_sns, {}
                    for expected, actual in zip(review.expected_sns, actual_sns):
                        self.batch_results[actual] = review.results[expected]
                    self.report_if_batch_complete(batch_number)
                elif kind == "start_failed":
                    station, batch_number = item
                    if batch_number == self.batch_number and self.link.connection:
                        self.safe_send(f"NACK:{station}:JOB={self.current_job_id};START_FAILED")
                        self.reported_batch_number = batch_number
                elif kind == "result":
                    batch_number, result = item; assert isinstance(result, TestResult)
                    if batch_number != self.batch_number:
                        self.append(f"略過舊批次結果：{result.sn}")
                        continue
                    self.append(f"{result.sn}: {result.status} — {result.detail}")
                    self.batch_results[result.sn] = result.status
                    self.report_if_batch_complete(batch_number)
                elif kind == "timeout":
                    batch_number, pending = item
                    if batch_number != self.batch_number:
                        continue
                    for sn in pending:
                        if sn not in self.batch_results:
                            self.batch_results[sn] = "TIMEOUT"
                            self.append(f"{sn}: TIMEOUT — 等待結果逾時")
                    self.monitor = None
                    self.report_if_batch_complete(batch_number)
        except queue.Empty: pass
        self.root.after(100, self.process_events)

    def close(self) -> None:
        try:
            delay, scale_x, scale_y, offset_x, offset_y, hid_mode, absolute_width, absolute_height = self.hid_settings()
        except AgentError:
            delay, scale_x, scale_y, offset_x, offset_y, hid_mode, absolute_width, absolute_height = .5, 1.0, 1.0, 0.0, 0.0, "relative", 1440, 900
        try:
            result_timeout = max(0.0, float(self.result_timeout.get()))
        except ValueError:
            result_timeout = 300.0
        Preferences(port=self.port.get(), csv_path=self.csv_path.get(), log_path=self.log_path.get(),
                    template_path=self.template_path.get(), station=self.station.get(),
                    dfu_profile=self.dfu_profile.get(), screenshot_path=self.screenshot_path.get(),
                    hid_delay=delay, hid_scale_x=scale_x, hid_scale_y=scale_y,
                    hid_offset_x=offset_x, hid_offset_y=offset_y, hid_mode=hid_mode,
                    absolute_width=absolute_width, absolute_height=absolute_height,
                    auto_scale=self.auto_scale.get(), result_timeout_seconds=result_timeout).save(self.pref_file)
        self.stop_monitor(); self.link.close(); self.root.destroy()


def main() -> int:
    parser = argparse.ArgumentParser(description=TITLE); parser.add_argument("--version", action="version", version=TITLE); parser.parse_args()
    root = tk.Tk(); AtlasAgentApp(root).root.mainloop(); return 0


if __name__ == "__main__": raise SystemExit(main())
