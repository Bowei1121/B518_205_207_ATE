"""Read RS-WMT result and progress files as timestamped source evidence."""

import csv
import io
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

from monitoring_files import file_signature, snapshot_files

RESULT_NAME = re.compile(
    r"^(?!Summary_)(?P<sn>.*?)_(?P<end>\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})\.csv$", re.I,
)
LOG_LINE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) (.*)$")
SLOT_COLUMN = re.compile(r"^tc=Slot(?:[:;]|$)", re.I)


def serial_number(value):
    value = value.strip().upper()
    return value if re.fullmatch(r"[A-Z0-9]{6,64}", value) and value not in {
        "UNKNOWN", "NUMBER_SOF0", "SERIALNUMBER"} else ""


@dataclass(frozen=True)
class RsWmtRecord:
    slot: int
    sn: str
    status: str
    started: datetime
    stopped: datetime
    source: str
    source_kind: str
    batch_time: Optional[datetime] = None

    def evidence(self):
        """Return only timestamps and source types present in the source."""
        precision = "milliseconds" if self.source_kind == "live_log" else "seconds"
        return {
            "source_time": self.stopped.isoformat(timespec=precision),
            "batch_evidence": (self.batch_time or self.started).isoformat(timespec=precision),
            "source_kind": self.source_kind,
        }


@dataclass(frozen=True)
class RsWmtObservation:
    kind: str
    source: str
    record: Optional[RsWmtRecord] = None
    message: str = ""
    stable: bool = False


def csv_time(value, reference):
    # The supplied export uses YYYY/DD/MM, while log/file names use YYYY-MM-DD.
    # Accept either export convention only when its date agrees with the filename.
    candidates = set()
    for fmt in ("%Y/%d/%m %H:%M:%S", "%Y/%m/%d %H:%M:%S"):
        try:
            parsed = datetime.strptime(value, fmt)
        except ValueError:
            continue
        if timedelta(0) <= reference - parsed <= timedelta(days=1):
            candidates.add(parsed)
    return next(iter(candidates)) if len(candidates) == 1 else None


def parse_rswmt_csv(path):
    """Parse one complete per-DUT final result; partial and summary files are ignored."""
    path = Path(path)
    match = RESULT_NAME.fullmatch(path.name)
    if not match:
        return None
    try:
        stopped = datetime.strptime(match['end'], "%Y-%m-%d_%H-%M-%S")
        text = path.read_text(encoding="utf-8-sig")
        if not text.endswith(('\n', '\r')):
            return None
        rows = list(csv.reader(io.StringIO(text), strict=True))
    except (OSError, UnicodeError, ValueError, csv.Error):
        return None
    headers = [i for i, row in enumerate(rows) if row and row[0].strip() == "Serial Number"]
    if len(headers) != 1:
        return None
    header = [v.strip() for v in rows[headers[0]]]
    required = ("Serial Number", "Test Pass/Fail Status", "Test Start Time", "Test Stop Time", "PRODUCT")
    if any(header.count(key) != 1 for key in required):
        return None
    slot_indexes = [i for i, key in enumerate(header) if SLOT_COLUMN.match(key)]
    if len(slot_indexes) != 1:
        return None
    data = [row for row in rows[headers[0] + 1:] if row and not row[0].strip().endswith("----->")]
    if len(data) != 1 or len(data[0]) != len(header):
        return None
    row = data[0]
    values = dict(zip(header, (v.strip() for v in row)))
    raw_slot = row[slot_indexes[0]].strip()
    if raw_slot not in ("1", "2", "3", "4") or values["PRODUCT"] != "B518":
        return None
    status = {"pass": "PASS", "fail": "FAIL"}.get(values["Test Pass/Fail Status"].lower())
    if not status:
        return None
    sn = serial_number(values["Serial Number"])
    if status == "PASS" and not sn:
        return None
    if sn and serial_number(match['sn']) != sn:
        return None
    end = csv_time(values['Test Stop Time'], stopped)
    start = csv_time(values['Test Start Time'], stopped)
    if end != stopped or start is None or start > end:
        return None
    # A genuine FAIL without a serial is still FAIL (initialization can fail).
    return RsWmtRecord(int(raw_slot), sn, status, start, end, str(path), "final_csv")


def parse_rswmt_log(text, source):
    """Extract evidenced activity only; an individual item PASS is never final."""
    records = []
    for line in text.splitlines(keepends=True):
        if not line.endswith(('\n', '\r')):
            continue
        match = LOG_LINE.match(line.rstrip('\r\n'))
        if match:
            try:
                records.append((datetime.strptime(match[1], '%Y-%m-%d %H:%M:%S,%f'), match[2]))
            except ValueError:
                pass
    starts = [stamp for stamp, line in records if line == "STATE:TestRunner Add-in 'initialize'..."]
    slots = {int(m[1]) for _, line in records
             for m in [re.search(r'VARiable:DEFine "instance_active_([1-4])",', line)] if m}
    sns = {m[1] for _, line in records
           for m in [re.search(r'DEBUG:HciCommunication << .*MLB#\.\.([A-Z0-9]{6,64})(?:\s|$)', line)] if m}
    if len(starts) != 1 or len(slots) != 1 or len(sns) > 1:
        return None
    closing = any(line == "STATE:TestRunner Add-in 'shutdown'..." for _, line in records)
    return RsWmtRecord(next(iter(slots)), next(iter(sns), ''),
                       'COMPLETING' if closing else 'TESTING', starts[0].replace(microsecond=0),
                       records[-1][0], str(source), "live_log", starts[0])


class RsWmtSourceAdapter:
    """Own RS-WMT discovery, source snapshots, parsing, stability and batch evidence."""

    def __init__(self, output_root: Path, slots: Sequence[int], round_started: datetime,
                 progress_root: Optional[Path] = None,
                 now: Callable[[], datetime] = datetime.now,
                 monotonic: Callable[[], float] = None):
        import time

        self.output_root = Path(output_root)
        self.progress_root = Path(progress_root) if progress_root else self.output_root
        self.slots = frozenset(slots)
        self.round_started = round_started
        self.now = now
        self.monotonic = monotonic or time.monotonic
        self.csv_baseline = snapshot_files(self.output_root, '.csv')
        self.log_baseline = snapshot_files(self.progress_root, '.log')
        self.csv_signatures: Dict[str, Tuple[Tuple[int, int], float]] = {}
        self.csv_candidates: Dict[str, Tuple[Tuple[int, int], bool]] = {}
        self.log_signatures: Dict[str, Tuple[int, int]] = {}
        self.announced: Set[Tuple[str, str]] = set()
        self.batch_start: Optional[datetime] = None

    def _warning(self, path: Path, message: str) -> List[RsWmtObservation]:
        key = (str(path), message)
        if key in self.announced:
            return []
        self.announced.add(key)
        return [RsWmtObservation("warning", str(path), message=message)]

    def _round_evidence(self, record: RsWmtRecord) -> Optional[List[RsWmtObservation]]:
        if record.slot not in self.slots or record.started < self.round_started - timedelta(seconds=30):
            return None
        if record.started > self.now() + timedelta(seconds=30):
            return None
        if self.batch_start is None:
            self.batch_start = record.started
            return [RsWmtObservation("batch", record.source, record=record)]
        if record.started != self.batch_start:
            return [RsWmtObservation(
                "warning", record.source,
                message="RS-WMT: different test start time; start a new monitoring round.",
            )]
        return []

    def poll(self) -> List[RsWmtObservation]:
        observations: List[RsWmtObservation] = []
        for path in sorted(self.output_root.rglob('*.csv')):
            if not RESULT_NAME.fullmatch(path.name):
                continue
            try:
                signature = file_signature(path)
            except OSError:
                continue
            key = str(path.resolve())
            if self.csv_baseline.get(key) == signature:
                continue
            previous = self.csv_signatures.get(key)
            changed = previous is None or previous[0] != signature
            stable_since = previous[1] if previous and not changed else self.monotonic()
            self.csv_signatures[key] = (signature, stable_since)
            record = parse_rswmt_csv(path)
            if record is None:
                if self.monotonic() - stable_since >= 5:
                    observations.extend(self._warning(path, 'RS-WMT: incomplete or unsupported CSV; result not accepted.'))
                continue
            batch_events = self._round_evidence(record)
            if batch_events is None:
                continue
            if batch_events and batch_events[0].kind == "warning":
                observations.extend(batch_events)
                continue
            observations.extend(batch_events)
            stable = self.monotonic() - stable_since >= 5
            announced = self.csv_candidates.get(key)
            if announced is None or announced[0] != signature or (stable and not announced[1]):
                observations.append(RsWmtObservation("final", str(path), record=record, stable=stable))
                self.csv_candidates[key] = (signature, stable)
        for path in sorted(self.progress_root.rglob('*.log')):
            try:
                signature = file_signature(path)
                key = str(path.resolve())
                if self.log_baseline.get(key) == signature or self.log_signatures.get(key) == signature:
                    continue
                text = path.read_text(encoding='utf-8-sig')
            except (OSError, UnicodeError):
                continue
            self.log_signatures[key] = signature
            record = parse_rswmt_log(text, path)
            if record is None:
                continue
            batch_events = self._round_evidence(record)
            if batch_events is None:
                continue
            if batch_events and batch_events[0].kind == "warning":
                observations.extend(batch_events)
                continue
            observations.extend(batch_events)
            observations.append(RsWmtObservation("progress", str(path), record=record))
        return observations
