"""Pure local-file monitoring core for B518 DFU, FCT and BT stations.

This module deliberately has no device-control dependencies.  The Tk UI only
subscribes to events emitted here; the same core is used by unit tests.
"""

from __future__ import annotations

import csv
import json
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple


ARCHIVE_TIMESTAMP = re.compile(
    r"^(?P<date>\d{8})_(?P<hour>\d{1,2})-(?P<minute>\d{2})-(?P<second>\d{2})"
    r"(?:\.(?P<millisecond>\d{1,3}))?(?:-.+)?$"
)
BT_FILENAME = re.compile(
    r"^\[Thread(?P<thread>[0-3])\]\[(?P<config>[^\]]*)\]\["
    r"(?P<sn>[^\]]*)\]\[(?P<status>PASSED|FAILED)\]\["
    r"(?P<stamp>\d{14})\]\.csv$",
    re.IGNORECASE,
)
CASEINFO_FILE = re.compile(r"^thread(?P<thread>[1-4])CaseInfo_(?P<date>\d{4}-\d{2}-\d{2})\.txt$", re.I)
CASEINFO_EVENT = re.compile(
    r"(?P<time>\d{4}/\d{1,2}/\d{1,2}\s+\d{1,2}:\d{2}:\d{2}(?:\.\d+)?)\s+"
    r"(?P<message>.*?)(?=(?:\d{4}/\d{1,2}/\d{1,2}\s+\d{1,2}:\d{2}:\d{2})|\Z)",
    re.S,
)
TRUSTED_SN_FIELDS = {"mlb_sn", "primaryidentity", "serialnumber"}
INVALID_SN_VALUES = {"", "N/A", "NA", "NONE", "UNKNOWN", "NUMBER_SOF0"}
TERMINAL = {"PASS", "FAIL", "NOTEST", "STOPPED"}


@dataclass
class MonitorEvent:
    kind: str
    message: str
    slot: Optional[int] = None
    sn: str = ""
    status: str = ""
    source: str = ""
    detail: Dict[str, str] = field(default_factory=dict)


@dataclass
class SlotResult:
    slot: int
    sn: str = ""
    status: str = "WAITING"
    source: str = ""
    updated_at: str = ""


def file_signature(path: Path) -> Tuple[int, int]:
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns


def snapshot_files(root: Path, suffix: str = "") -> Dict[str, Tuple[int, int]]:
    if not root.is_dir():
        return {}
    answer: Dict[str, Tuple[int, int]] = {}
    for path in root.rglob("*"):
        if not path.is_file() or (suffix and path.suffix.lower() != suffix.lower()):
            continue
        try:
            answer[str(path.resolve())] = file_signature(path)
        except OSError:
            pass
    return answer


def parse_archive_timestamp(name: str) -> Optional[datetime]:
    match = ARCHIVE_TIMESTAMP.match(name)
    if not match:
        return None
    try:
        milliseconds = (match.group("millisecond") or "0").ljust(3, "0")[:3]
        return datetime.strptime(
            "{} {:02d}:{}:{}.{}".format(
                match.group("date"), int(match.group("hour")), match.group("minute"),
                match.group("second"), milliseconds,
            ),
            "%Y%m%d %H:%M:%S.%f",
        )
    except ValueError:
        return None


def normalise_sn(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "").upper())


def is_trusted_sn(value: object) -> bool:
    sn = normalise_sn(value)
    return len(sn) >= 6 and sn not in INVALID_SN_VALUES and not sn.startswith("NUMBER_")


def read_csv_rows(path: Path) -> List[Dict[str, str]]:
    for encoding in ("utf-8-sig", "utf-8", "big5", "latin-1"):
        try:
            with path.open("r", encoding=encoding, newline="") as handle:
                return [{str(k or "").strip(): str(v or "").strip() for k, v in row.items()}
                        for row in csv.DictReader(handle)]
        except (UnicodeError, csv.Error, OSError):
            continue
    return []


def trusted_sn_from_records(path: Path) -> str:
    rows = read_csv_rows(path)
    for row in rows:
        for key, value in row.items():
            if key.strip().lower().replace(" ", "_") in TRUSTED_SN_FIELDS and is_trusted_sn(value):
                return normalise_sn(value)
        values = list(row.values())
        if len(values) >= 2 and values[0].strip().lower().replace(" ", "_") in TRUSTED_SN_FIELDS:
            if is_trusted_sn(values[1]):
                return normalise_sn(values[1])
    return ""


def records_status(path: Path) -> str:
    rows = read_csv_rows(path)
    statuses: List[str] = []
    for row in rows:
        for key, value in row.items():
            if key.strip().lower() == "status" and value.strip():
                statuses.append(value.strip().upper())
    if not statuses:
        return "UNKNOWN"
    if any(value.startswith("FAIL") for value in statuses):
        return "FAIL"
    if all(value.startswith("PASS") for value in statuses):
        return "PASS"
    return "UNKNOWN"


def parse_bt_filename(path: Path) -> Optional[Dict[str, str]]:
    match = BT_FILENAME.match(path.name)
    if not match:
        return None
    result = {key: value or "" for key, value in match.groupdict().items()}
    result["thread"] = str(int(result["thread"]))
    return result


def parse_bt_csv(path: Path) -> Optional[Dict[str, str]]:
    name = parse_bt_filename(path)
    if not name:
        return None
    folder_status = path.parent.name.upper()
    if folder_status not in {"PASSED", "FAILED"} or folder_status != name["status"].upper():
        return None
    rows = read_csv_rows(path)
    values: Dict[str, str] = {}
    for row in rows:
        values.update({key.strip().lower(): value.strip() for key, value in row.items() if key})
    csv_status = values.get("test pass/fail status", "").upper()
    if csv_status and csv_status != name["status"].upper():
        return None
    csv_sn = normalise_sn(values.get("serialnumber", ""))
    file_sn = normalise_sn(name["sn"])
    if file_sn and csv_sn and file_sn != csv_sn:
        return None
    sn = file_sn or csv_sn
    if not sn and name["status"].upper() == "FAILED":
        state = "NOTEST"
    elif sn:
        state = "PASS" if name["status"].upper() == "PASSED" else "FAIL"
    else:
        return None
    return {"slot": str(int(name["thread"]) + 1), "sn": sn, "status": state,
            "stamp": name["stamp"], "source": str(path)}


class SessionStore:
    def __init__(self, session_id: str, settings: Dict[str, str], root: Optional[Path] = None):
        root = root or (Path.home() / "Library" / "Application Support" / "B518LogSolution" / "sessions")
        self.path = root / session_id
        self.path.mkdir(parents=True, exist_ok=True)
        self.settings = settings
        self.started_at = datetime.now().isoformat(timespec="seconds")
        self.sources: Set[str] = set()
        self.finished_at = ""
        self._write_metadata()

    def _write_metadata(self) -> None:
        payload = {"settings": self.settings, "started_at": self.started_at,
                   "finished_at": self.finished_at, "sources": sorted(self.sources)}
        (self.path / "session.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def event(self, message: str) -> None:
        with (self.path / "events.log").open("a", encoding="utf-8") as handle:
            handle.write("{} {}\n".format(datetime.now().isoformat(timespec="seconds"), message))

    def update_results(self, results: Iterable[SlotResult]) -> None:
        with (self.path / "results.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["slot", "sn", "status", "source", "updated_at"])
            writer.writeheader()
            writer.writerows(asdict(result) for result in sorted(results, key=lambda result: result.slot))

    def source(self, path: Path) -> None:
        self.sources.add(str(path))
        self._write_metadata()

    def finish(self) -> None:
        self.finished_at = datetime.now().isoformat(timespec="seconds")
        self._write_metadata()


class BaseMonitor:
    """Polling monitor with explicit ``poll_once`` for deterministic tests."""
    def __init__(self, station: str, settings: Dict[str, str], slots: Sequence[int],
                 callback: Optional[Callable[[MonitorEvent], None]] = None,
                 session_root: Optional[Path] = None, now: Callable[[], datetime] = datetime.now):
        self.station, self.settings, self.slots = station, settings, tuple(sorted(slots))
        self.callback, self.now = callback, now
        self.started = now()
        self.results = {slot: SlotResult(slot=slot) for slot in self.slots}
        session_id = "{}-{}".format(station.lower(), self.started.strftime("%Y%m%d-%H%M%S-%f"))
        self.session = SessionStore(session_id, settings, session_root)
        self.finished = False
        self._stable_since: Optional[datetime] = None
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def emit(self, event: MonitorEvent) -> None:
        self.session.event(event.message)
        if event.source:
            self.session.source(Path(event.source))
        if self.callback:
            self.callback(event)

    def set_result(self, slot: int, status: str, sn: Optional[str] = None, source: str = "") -> None:
        result = self.results[slot]
        if result.status in TERMINAL and status not in TERMINAL:
            return
        if sn:
            result.sn = sn
        result.status, result.source = status, source or result.source
        result.updated_at = self.now().isoformat(timespec="seconds")
        self.session.update_results(self.results.values())
        self.emit(MonitorEvent("result", "slot{} {}".format(slot, status), slot, result.sn, status, source))

    def _all_terminal(self) -> bool:
        return bool(self.results) and all(result.status in TERMINAL for result in self.results.values())

    def complete_if_stable(self) -> None:
        if not self._all_terminal():
            self._stable_since = None
            return
        if self._stable_since is None:
            self._stable_since = self.now()
        elif self.now() - self._stable_since >= timedelta(seconds=3):
            self.finished = True
            self.session.finish()
            self.emit(MonitorEvent("finished", "{} 本輪完成".format(self.station)))

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.wait(0.5):
            self.poll_once()
            if self.finished:
                return

    def stop(self) -> None:
        self._stop.set()
        if not self.finished:
            for slot, result in self.results.items():
                if result.status not in TERMINAL:
                    self.set_result(slot, "STOPPED")
            self.finished = True
            self.session.finish()
            self.emit(MonitorEvent("stopped", "{} 監控已由人員停止".format(self.station)))

    def poll_once(self) -> None:
        raise NotImplementedError


class AtlasActiveArchiveMonitor(BaseMonitor):
    """DFU/FCT monitor: active/group0-slotN followed by final archive data."""
    def __init__(self, station: str, active_root: Path, final_root: Path, slots: Sequence[int], **kwargs):
        super().__init__(station, {"active_root": str(active_root), "final_root": str(final_root)}, slots, **kwargs)
        self.active_root, self.final_root = active_root, final_root
        self.baseline_active = snapshot_files(active_root, ".csv")
        self.baseline_final = snapshot_files(final_root, ".csv")
        self.seen_slots: Set[int] = set()
        self.locked_sn: Dict[int, str] = {}
        self.last_active_at: Dict[int, datetime] = {}
        self._warned_stalled = False
        self._inactive_since: Optional[datetime] = None

    def _active_records(self, slot: int) -> Optional[Path]:
        root = self.active_root / "group0-slot{}".format(slot)
        if not root.is_dir():
            return None
        candidates = list(root.rglob("records.csv")) + list(root.rglob("record.csv"))
        return max(candidates, key=lambda path: path.stat().st_mtime_ns) if candidates else None

    def _is_new_or_changed(self, path: Path) -> bool:
        try:
            return self.baseline_final.get(str(path.resolve())) != file_signature(path)
        except OSError:
            return False

    def _active_is_new_or_changed(self, path: Path) -> bool:
        try:
            return self.baseline_active.get(str(path.resolve())) != file_signature(path)
        except OSError:
            return False

    def _final_csv(self, sn: str) -> Optional[Path]:
        sn_root = self.final_root / sn
        if not sn_root.is_dir():
            return None
        threshold = self.started - timedelta(seconds=30)
        candidates: List[Tuple[datetime, Path]] = []
        for folder in sn_root.iterdir():
            if not folder.is_dir():
                continue
            stamp = parse_archive_timestamp(folder.name)
            if stamp is None or stamp < threshold:
                continue
            for name in ("records.csv", "record.csv"):
                candidate = folder / "system" / name
                if candidate.is_file() and self._is_new_or_changed(candidate):
                    candidates.append((stamp, candidate))
        return max(candidates, key=lambda item: item[0])[1] if candidates else None

    def poll_once(self) -> None:
        active_now: Set[int] = set()
        active_directories: Set[int] = set()
        for slot in self.slots:
            if (self.active_root / "group0-slot{}".format(slot)).is_dir():
                active_directories.add(slot)
            record = self._active_records(slot)
            if record and self._active_is_new_or_changed(record):
                active_now.add(slot)
                self.seen_slots.add(slot)
                self.last_active_at[slot] = self.now()
                sn = trusted_sn_from_records(record)
                if sn and slot not in self.locked_sn:
                    self.locked_sn[slot] = sn
                    self.set_result(slot, "TESTING", sn, str(record))
                    self.emit(MonitorEvent("sn_locked", "slot{} 鎖定 SN {}".format(slot, sn), slot, sn, "TESTING", str(record)))
                elif slot not in self.locked_sn:
                    self.set_result(slot, "TESTING", "", str(record))
                elif self.results[slot].status not in TERMINAL:
                    self.set_result(slot, "TESTING", self.locked_sn[slot], str(record))
        for slot in sorted(self.seen_slots - active_now):
            if slot not in self.locked_sn:
                self.set_result(slot, "FAIL", "SN 讀取失敗")
                continue
            if self.results[slot].status in TERMINAL:
                continue
            sn = self.locked_sn[slot]
            self.set_result(slot, "COMPLETING", sn)
            candidate = self._final_csv(sn)
            if candidate:
                state = records_status(candidate)
                if state in {"PASS", "FAIL"}:
                    self.set_result(slot, state, sn, str(candidate))
                    self.emit(MonitorEvent("final", "slot{} 最終 {}".format(slot, state), slot, sn, state, str(candidate)))
        if self.seen_slots and not active_directories:
            if self._inactive_since is None:
                self._inactive_since = self.now()
            elif self.now() - self._inactive_since >= timedelta(seconds=3):
                for slot in set(self.slots) - self.seen_slots:
                    if self.results[slot].status == "WAITING":
                        self.set_result(slot, "NOTEST")
        else:
            self._inactive_since = None
        if self.seen_slots and active_now:
            # An active test is never killed by an arbitrary total timeout.
            elapsed = self.now() - min(self.last_active_at.values())
            if elapsed > timedelta(minutes=5) and not self._warned_stalled:
                self._warned_stalled = True
                self.emit(MonitorEvent("stalled", "{} active 長時間未更新，仍持續監控".format(self.station)))
        self.complete_if_stable()


class BtLogMonitor(BaseMonitor):
    """BT TestData monitor with timestamp batch locking and optional CaseInfo."""
    def __init__(self, testdata_root: Path, slots: Sequence[int], caseinfo_root: Optional[Path] = None, **kwargs):
        self.monotonic = kwargs.pop("monotonic", time.monotonic)
        super().__init__("BT", {"testdata_root": str(testdata_root), "caseinfo_root": str(caseinfo_root or "")}, slots, **kwargs)
        self.testdata_root, self.caseinfo_root = testdata_root, caseinfo_root
        self.baseline = snapshot_files(testdata_root, ".csv")
        self.batch_stamp = ""
        self.seen_signature: Dict[str, Tuple[int, int, float]] = {}
        self.review_pending: Optional[Dict[str, object]] = None
        self.review_decisions: Dict[str, str] = {}
        self._caseinfo_offsets: Dict[str, int] = {}

    def resolve_review(self, choice: str) -> None:
        """Apply the one pending UI decision on the next polling pass.

        A batch acceptance intentionally starts a new BT batch and clears only
        non-final rows.  A duplicate-thread acceptance replaces that thread's
        result; rejection ignores just the offered file.
        """
        if self.review_pending is None:
            return
        path = str(self.review_pending["path"])
        self.review_decisions[path] = choice.lower()
        self.emit(MonitorEvent("review_resolved", "BT 人工覆核：{}".format("接受" if choice.lower() == "accept" else "忽略"), source=path))
        self.review_pending = None

    def _csv_candidates(self) -> Iterable[Path]:
        if not self.testdata_root.is_dir():
            return []
        dates = {self.started.strftime("%Y-%m-%d"), self.now().strftime("%Y-%m-%d")}
        return [path for date in dates for status in ("PASSED", "FAILED")
                for path in (self.testdata_root / date / status).glob("*.csv") if path.is_file()]

    def _stable(self, path: Path) -> bool:
        try:
            signature = file_signature(path)
        except OSError:
            return False
        key = str(path.resolve())
        previous = self.seen_signature.get(key)
        now_seconds = self.monotonic()
        self.seen_signature[key] = (signature[0], signature[1], previous[2] if previous and previous[:2] == signature else now_seconds)
        return previous is not None and previous[:2] == signature and now_seconds - previous[2] >= 5.0

    def _emit_caseinfo(self) -> None:
        if not self.caseinfo_root or not self.caseinfo_root.is_dir():
            return
        threshold = self.started - timedelta(seconds=30)
        for path in self.caseinfo_root.glob("thread*CaseInfo_*.txt"):
            match = CASEINFO_FILE.match(path.name)
            if not match:
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            offset = self._caseinfo_offsets.get(str(path), 0)
            if offset >= len(content):
                continue
            self._caseinfo_offsets[str(path)] = len(content)
            slot = int(match.group("thread"))
            if slot not in self.results or self.results[slot].status in TERMINAL:
                continue
            for event in CASEINFO_EVENT.finditer(content[max(0, offset - 64):]):
                try:
                    event_time = datetime.strptime(event.group("time").split(".")[0], "%Y/%m/%d %H:%M:%S")
                except ValueError:
                    continue
                if event_time < threshold:
                    continue
                message = event.group("message")
                sn_match = re.search(r"(?:SNRead|SerialNumber|MLB_SN|PrimaryIdentity)\s*[:=]\s*([A-Za-z0-9_-]+)", message, re.I)
                sn = normalise_sn(sn_match.group(1)) if sn_match and is_trusted_sn(sn_match.group(1)) else ""
                status = "COMPLETING" if re.search(r"CloseFixture|complete|finish", message, re.I) else "TESTING"
                self.set_result(slot, status, sn, str(path))

    def poll_once(self) -> None:
        self._emit_caseinfo()
        threshold = self.started - timedelta(seconds=30)
        for path in self._csv_candidates():
            parsed = parse_bt_csv(path)
            if not parsed:
                continue
            stamp_dt = datetime.strptime(parsed["stamp"], "%Y%m%d%H%M%S")
            try:
                changed = self.baseline.get(str(path.resolve())) != file_signature(path)
            except OSError:
                changed = False
            if stamp_dt < threshold or not changed or not self._stable(path):
                continue
            if not self.batch_stamp:
                self.batch_stamp = parsed["stamp"]
                self.emit(MonitorEvent("batch", "BT 鎖定批次 {}".format(self.batch_stamp), source=str(path)))
            if parsed["stamp"] != self.batch_stamp:
                decision = self.review_decisions.get(str(path))
                if decision == "reject":
                    continue
                if decision == "accept":
                    self.batch_stamp = parsed["stamp"]
                    for result_slot, result in self.results.items():
                        if result.status not in TERMINAL:
                            self.set_result(result_slot, "WAITING", "")
                    self.emit(MonitorEvent("batch", "BT 人工確認切換批次 {}".format(self.batch_stamp), source=str(path)))
                else:
                    if self.review_pending is None:
                        self.review_pending = {"kind": "batch", "path": str(path), "stamp": parsed["stamp"], "locked": self.batch_stamp}
                        self.emit(MonitorEvent("review", "BT 偵測批次衝突，等待人工覆核", source=str(path), detail=self.review_pending))
                    continue
            slot = int(parsed["slot"])
            if slot not in self.results:
                continue
            current = self.results[slot]
            if current.status in TERMINAL and current.source != parsed["source"]:
                decision = self.review_decisions.get(str(path))
                if decision == "reject":
                    continue
                if decision != "accept":
                    if self.review_pending is None:
                        self.review_pending = {"kind": "duplicate", "path": str(path), "slot": slot,
                                               "old": current.source, "new": str(path)}
                        self.emit(MonitorEvent("review", "BT Thread{} 出現重複結果，等待人工覆核".format(slot - 1), slot,
                                               source=str(path), detail=self.review_pending))
                    continue
            self.set_result(slot, parsed["status"], parsed["sn"], parsed["source"])
        self.complete_if_stable()
