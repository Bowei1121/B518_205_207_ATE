"""B518 RS-WMT adapter: SmtCal per-DUT CSV results and optional live logs."""

import csv
import io
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from log_monitoring import BaseMonitor, MonitorEvent, TERMINAL, file_signature, snapshot_files

RESULT_NAME = re.compile(r"^(?!Summary_)(?P<sn>.*?)_(?P<end>\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})\.csv$", re.I)
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
    """Return one complete normalized DUT result; malformed/partial input is ignored."""
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
    return RsWmtRecord(int(raw_slot), sn, status, start, end, str(path))


def parse_rswmt_log(text, source):
    """Extract only evidenced RS-WMT markers, never item PASS as final PASS."""
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
                       records[-1][0], str(source))


class RsWmtLogMonitor(BaseMonitor):
    """One manually started round; final CSV wins over progress and timeout."""
    def __init__(self, output_root, slots=(1, 2, 3, 4), progress_root=None, **kwargs):
        self.output_root = Path(output_root)
        self.progress_root = Path(progress_root) if progress_root else self.output_root
        super().__init__('BT', {'format': 'B518 RS-WMT', 'output_root': str(output_root),
                               'progress_root': str(self.progress_root)}, slots, **kwargs)
        self.baseline = snapshot_files(self.output_root, '.csv')
        self.log_baseline = snapshot_files(self.progress_root, '.log')
        self.signatures = {}
        self.log_signatures = {}
        self.batch_start = None
        self.notices = set()
        self.begin_timeout_clock()

    def notice(self, path, message):
        key = (str(path), message)
        if key not in self.notices:
            self.notices.add(key)
            self.emit(MonitorEvent('warning', message, source=str(path)))

    def accept(self, record):
        if record.slot not in self.results or record.started < self.started - timedelta(seconds=30):
            return False
        if record.started > self.now() + timedelta(seconds=30):
            return False
        if self.batch_start is None:
            self.batch_start = record.started
            self.emit(MonitorEvent('batch', 'RS-WMT batch {}'.format(self.batch_start), source=record.source))
        if record.started != self.batch_start:
            self.notice(record.source, 'RS-WMT: different test start time; start a new monitoring round.')
            return False
        return True

    def poll_once(self):
        if self.finished or self._stop.is_set():
            return
        for path in sorted(self.output_root.rglob('*.csv')):
            if not RESULT_NAME.fullmatch(path.name):
                continue
            try:
                signature = file_signature(path)
            except OSError:
                continue
            key = str(path.resolve())
            if self.baseline.get(key) == signature:
                continue
            previous = self.signatures.get(key)
            stable_since = previous[1] if previous and previous[0] == signature else self.monotonic()
            self.signatures[key] = (signature, stable_since)
            record = parse_rswmt_csv(path)
            if record is None:
                if self.monotonic() - stable_since >= 5:
                    self.notice(path, 'RS-WMT: incomplete or unsupported CSV; result not accepted.')
                continue
            if not self.accept(record):
                continue
            current = self.results[record.slot]
            if current.sn and record.sn and current.sn != record.sn:
                self.notice(path, 'RS-WMT: serial conflict for slot; result not accepted.')
                continue
            if current.status in TERMINAL:
                if current.source != str(path):
                    self.notice(path, 'RS-WMT: duplicate/late slot result ignored; previous result retained.')
                continue
            if self.monotonic() - stable_since >= 5:
                self.set_result(record.slot, record.status, record.sn, str(path))
            elif current.status != 'COMPLETING' or current.sn != record.sn:
                self.set_result(record.slot, 'COMPLETING', record.sn, str(path))
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
            if not record or not self.accept(record) or self.results[record.slot].status in TERMINAL:
                continue
            current = self.results[record.slot]
            if current.sn and record.sn and current.sn != record.sn:
                self.notice(path, 'RS-WMT: serial conflict for slot; progress not accepted.')
                continue
            # An already observed final CSV remains COMPLETING during stable-write wait.
            status = 'COMPLETING' if current.status == 'COMPLETING' else record.status
            if status != current.status or (record.sn and record.sn != current.sn):
                self.set_result(record.slot, status, record.sn, str(path))
        self.check_timeouts()
        self.complete_if_stable()
