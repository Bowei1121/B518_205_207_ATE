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

from atlas_source_adapter import (
    AtlasSourceAdapter,
    parse_archive_timestamp,
    records_status,
    trusted_sn_from_records,
)
from monitoring_files import (
    file_signature,
    is_trusted_sn,
    normalise_sn,
    read_csv_rows,
    snapshot_files,
)

BT_FILENAME = re.compile(
    r"^\[Thread(?P<thread>[0-3])\]\[(?P<config>[^\]]*)\]\["
    r"(?P<sn>[^\]]*)\]\[(?P<status>PASSED|FAILED)\]\["
    r"(?P<stamp>\d{14})\]\.csv$",
    re.IGNORECASE,
)
CASEINFO_FILE = re.compile(r"^thread(?P<thread>[1-4])CaseInfo_(?P<date>\d{4}-\d{2}-\d{2})\.txt$", re.I)
CASEINFO_TIMESTAMP = re.compile(
    r"(?P<time>\d{4}[-/]\d{1,2}[-/]\d{1,2}\s+\d{1,2}:\d{2}:\d{2}(?:(?:\.|:)\d+)?)"
)
TERMINAL = {"PASS", "FAIL", "NOTEST", "STOPPED", "TIMEOUT"}
DEFAULT_TIMEOUTS = {
    "DFU": {"start": 30, "test": 480},
    "FCT": {"start": 30, "test": 480},
    "BT": {"start": 30, "test": 240},
}


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
                 session_root: Optional[Path] = None, now: Callable[[], datetime] = datetime.now,
                 monotonic: Callable[[], float] = time.monotonic,
                 start_timeout_seconds: Optional[int] = None,
                 test_timeout_seconds: Optional[int] = None):
        self.station, self.settings, self.slots = station, settings, tuple(sorted(slots))
        defaults = DEFAULT_TIMEOUTS.get(station.upper(), DEFAULT_TIMEOUTS["FCT"])
        self.start_timeout_seconds = int(start_timeout_seconds or defaults["start"])
        self.test_timeout_seconds = int(test_timeout_seconds or defaults["test"])
        if self.start_timeout_seconds <= 0 or self.test_timeout_seconds <= 0:
            raise ValueError("逾時秒數必須為正整數")
        self.settings.update({"start_timeout_seconds": str(self.start_timeout_seconds),
                              "test_timeout_seconds": str(self.test_timeout_seconds)})
        self.callback, self.now, self.monotonic = callback, now, monotonic
        self.started = now()
        self._started_monotonic = monotonic()
        self._activity_seen = False
        self._test_started_monotonic: Dict[int, float] = {}
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
        if self.finished:
            return
        result = self.results[slot]
        if result.status in TERMINAL and status not in TERMINAL:
            return
        if status in {"TESTING", "COMPLETING"}:
            self._activity_seen = True
            self._test_started_monotonic.setdefault(slot, self.monotonic())
        elif status in {"PASS", "FAIL", "NOTEST"}:
            self._activity_seen = True
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

    def begin_timeout_clock(self) -> None:
        """Start timeout measurement only after a monitor has made its snapshots."""
        self.started = self.now()
        self._started_monotonic = self.monotonic()

    def check_timeouts(self) -> None:
        """Stop the session when it never starts or one active slot runs too long."""
        if self.finished:
            return
        elapsed = self.monotonic() - self._started_monotonic
        if not self._activity_seen and elapsed >= self.start_timeout_seconds:
            self._finish_timeout("start", None, elapsed)
            return
        timed_out_slots = []
        for slot in sorted(self._test_started_monotonic):
            if self.results[slot].status in TERMINAL:
                continue
            test_elapsed = self.monotonic() - self._test_started_monotonic[slot]
            if test_elapsed >= self.test_timeout_seconds:
                timed_out_slots.append((slot, test_elapsed))
        for slot, test_elapsed in timed_out_slots:
            self._finish_timeout("test", slot, test_elapsed)

    def _finish_timeout(self, kind: str, timed_out_slot: Optional[int], elapsed: float) -> None:
        if kind == "start":
            for slot, result in self.results.items():
                if result.status not in TERMINAL:
                    self.set_result(slot, "TIMEOUT")
            message = "{} 未進入測試逾時：{} 秒（經過 {} 秒）".format(
                self.station, self.start_timeout_seconds, int(elapsed),
            )
        else:
            assert timed_out_slot is not None
            self.set_result(timed_out_slot, "TIMEOUT")
            message = "{} slot{} 測試逾時：{} 秒（上限 {} 秒）".format(
                self.station, timed_out_slot, int(elapsed), self.test_timeout_seconds,
            )
        self.emit(MonitorEvent("timeout", message, timed_out_slot, status="TIMEOUT",
                               detail={"kind": kind, "elapsed_seconds": str(int(elapsed))}))
        if kind == "start":
            self._stop.set()
            self.finished = True
            self.session.finish()

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
        self.source = AtlasSourceAdapter(active_root, final_root, slots, self.started, self.now)
        self.begin_timeout_clock()

    def poll_once(self) -> None:
        for observation in self.source.poll():
            if observation.kind == "source_prepared":
                self.emit(MonitorEvent("source_prepared", "Atlas 來源啟動前快照完成，監控準備就緒。"))
            elif observation.kind == "sn_locked":
                self.set_result(observation.slot, observation.status, observation.sn, observation.source)
                self.emit(MonitorEvent(
                    "sn_locked", "slot{} 已鎖定可信 SN".format(observation.slot),
                    observation.slot, observation.sn, observation.status, observation.source,
                ))
            elif observation.kind == "activity":
                self.set_result(observation.slot, observation.status, observation.sn, observation.source)
            elif observation.kind == "sn_read_failed":
                self.set_result(observation.slot, observation.status, observation.sn)
            elif observation.kind in {"completing", "notest"}:
                self.set_result(observation.slot, observation.status, observation.sn)
            elif observation.kind == "final":
                self.set_result(observation.slot, observation.status, observation.sn, observation.source)
                self.emit(MonitorEvent(
                    "final", "slot{} 最終 {}".format(observation.slot, observation.status),
                    observation.slot, observation.sn, observation.status, observation.source,
                ))
        self.check_timeouts()
        self.complete_if_stable()


class BtLogMonitor(BaseMonitor):
    """BT TestData monitor with timestamp batch locking and optional CaseInfo."""
    def __init__(self, testdata_root: Path, slots: Sequence[int], caseinfo_root: Optional[Path] = None, **kwargs):
        monotonic = kwargs.pop("monotonic", time.monotonic)
        super().__init__("BT", {"testdata_root": str(testdata_root), "caseinfo_root": str(caseinfo_root or "")}, slots,
                         monotonic=monotonic, **kwargs)
        self.testdata_root, self.caseinfo_root = testdata_root, caseinfo_root
        self.baseline = snapshot_files(testdata_root, ".csv")
        self.begin_timeout_clock()
        self.batch_stamp = ""
        self.seen_signature: Dict[str, Tuple[int, int, float]] = {}
        self.review_pending: Optional[Dict[str, object]] = None
        self.review_decisions: Dict[str, str] = {}
        self._caseinfo_offsets: Dict[str, int] = {}
        self._caseinfo_tails: Dict[str, str] = {}

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
            key = str(path)
            offset = self._caseinfo_offsets.get(key, 0)
            if len(content) < offset:
                offset = 0
                self._caseinfo_tails.pop(key, None)
            if offset >= len(content):
                continue
            chunk = self._caseinfo_tails.get(key, "") + content[offset:]
            self._caseinfo_offsets[key] = len(content)
            slot = int(match.group("thread"))
            if slot not in self.results or self.results[slot].status in TERMINAL:
                continue
            events = list(CASEINFO_TIMESTAMP.finditer(chunk))
            if not events:
                self._caseinfo_tails[key] = chunk
                continue
            complete_last = bool(re.search(r"[\r\n]\s*$", chunk))
            final_event = len(events) if complete_last else len(events) - 1
            self._caseinfo_tails[key] = "" if complete_last else chunk[events[-1].start():]
            for index, event in enumerate(events[:final_event]):
                try:
                    event_time = datetime.strptime(
                        event.group("time")[:19].replace("/", "-"), "%Y-%m-%d %H:%M:%S",
                    )
                except ValueError:
                    continue
                if event_time < threshold:
                    continue
                end = events[index + 1].start() if index + 1 < len(events) else len(chunk)
                message = chunk[event.end():end]
                sn_match = re.search(r"(?:SNRead|SerialNumber|MLB_SN|PrimaryIdentity)\s*[:=]\s*([A-Za-z0-9_-]+)", message, re.I)
                sn = normalise_sn(sn_match.group(1)) if sn_match and is_trusted_sn(sn_match.group(1)) else ""
                fields = next(csv.reader([message.lstrip(" ,\r\n")]), [])
                # CaseInfo CSV uses column 3 for the state-machine state and
                # column 5 for the action.  Only ``...,--,SNRead,<barcode>``
                # means that column 6 carries the physical material barcode.
                if (not sn and len(fields) > 5 and fields[3].strip() == "--"
                        and fields[4].strip().lower() == "snread"
                        and is_trusted_sn(fields[5])):
                    sn = normalise_sn(fields[5])
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
        self.check_timeouts()
        self.complete_if_stable()
