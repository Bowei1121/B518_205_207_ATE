"""B482 TestData and CaseInfo source discovery and evidence parsing."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

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


class B482ObservationKind(str, Enum):
    CASEINFO_ACTIVITY = "caseinfo_activity"
    TESTDATA_RESULT = "testdata_result"


@dataclass(frozen=True)
class B482Observation:
    """One source fact, with only the evidence present in B482 files."""

    kind: B482ObservationKind
    slot: int
    status: str
    sn: str
    source: str
    source_id: str
    source_time: str
    batch_id: str = ""
    batch_evidence: str = ""

    def evidence(self) -> Dict[str, str]:
        fields = {
            "source_id": self.source_id,
            "source_time": self.source_time,
        }
        if self.batch_id:
            fields["batch_id"] = self.batch_id
        if self.batch_evidence:
            fields["batch_evidence"] = self.batch_evidence
        return fields


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
    return {
        "slot": str(int(name["thread"]) + 1),
        "sn": sn,
        "status": state,
        "stamp": name["stamp"],
        "source": str(path),
        "source_id": path.name,
        "source_time": datetime.strptime(name["stamp"], "%Y%m%d%H%M%S").isoformat(sep=" "),
        "batch_evidence": "thread={};config={}".format(name["thread"], name["config"]),
    }


def _caseinfo_source_time(value: str) -> Optional[Tuple[datetime, str]]:
    normalized = value.replace("/", "-")
    main = normalized[:19]
    try:
        parsed = datetime.strptime(main, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    fraction = normalized[19:]
    digits = fraction[1:] if fraction.startswith((".", ":")) else ""
    if digits:
        parsed = parsed.replace(microsecond=int(digits[:6].ljust(6, "0")))
        rendered = parsed.isoformat(sep=" ", timespec="milliseconds" if len(digits) <= 3 else "microseconds")
    else:
        rendered = parsed.isoformat(sep=" ", timespec="seconds")
    return parsed, rendered


class B482SourceAdapter:
    """Own startup isolation, incremental input handling, and B482 file evidence."""

    def __init__(self, testdata_root: Path, caseinfo_root: Optional[Path], slots: Sequence[int],
                 started: datetime, now: Callable[[], datetime], monotonic: Callable[[], float]):
        self.testdata_root = testdata_root
        self.caseinfo_root = caseinfo_root
        self.slots = tuple(sorted(slots))
        self.started = started
        self.now = now
        self.monotonic = monotonic
        self._baseline = snapshot_files(testdata_root, ".csv")
        self._seen_signatures: Dict[str, Tuple[int, int, float]] = {}
        self._caseinfo_offsets: Dict[str, int] = {}
        self._caseinfo_tails: Dict[str, str] = {}

    def poll(self) -> Tuple[B482Observation, ...]:
        return tuple(self._caseinfo_observations() + self._testdata_observations())

    def _csv_candidates(self) -> List[Path]:
        if not self.testdata_root.is_dir():
            return []
        dates = {self.started.strftime("%Y-%m-%d"), self.now().strftime("%Y-%m-%d")}
        return [
            path
            for date in sorted(dates)
            for status in ("PASSED", "FAILED")
            for path in (self.testdata_root / date / status).glob("*.csv")
            if path.is_file()
        ]

    def _stable(self, path: Path) -> bool:
        try:
            signature = file_signature(path)
        except OSError:
            return False
        key = str(path.resolve())
        previous = self._seen_signatures.get(key)
        now_seconds = self.monotonic()
        self._seen_signatures[key] = (
            signature[0], signature[1],
            previous[2] if previous and previous[:2] == signature else now_seconds,
        )
        return previous is not None and previous[:2] == signature and now_seconds - previous[2] >= 5.0

    def _testdata_observations(self) -> List[B482Observation]:
        observations = []
        threshold = self.started - timedelta(seconds=30)
        for path in self._csv_candidates():
            parsed = parse_bt_csv(path)
            if not parsed:
                continue
            source_time = datetime.strptime(parsed["stamp"], "%Y%m%d%H%M%S")
            try:
                changed_since_start = self._baseline.get(str(path.resolve())) != file_signature(path)
            except OSError:
                changed_since_start = False
            if source_time < threshold or not changed_since_start or not self._stable(path):
                continue
            observations.append(B482Observation(
                B482ObservationKind.TESTDATA_RESULT,
                int(parsed["slot"]), parsed["status"], parsed["sn"], parsed["source"],
                str(path.relative_to(self.testdata_root)), parsed["source_time"], parsed["stamp"],
                parsed["batch_evidence"],
            ))
        return observations

    def _caseinfo_observations(self) -> List[B482Observation]:
        if not self.caseinfo_root or not self.caseinfo_root.is_dir():
            return []
        observations = []
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
            events = list(CASEINFO_TIMESTAMP.finditer(chunk))
            if not events:
                self._caseinfo_tails[key] = chunk
                continue
            complete_last = bool(re.search(r"[\r\n]\s*$", chunk))
            final_event = len(events) if complete_last else len(events) - 1
            self._caseinfo_tails[key] = "" if complete_last else chunk[events[-1].start():]
            for index, event in enumerate(events[:final_event]):
                parsed_time = _caseinfo_source_time(event.group("time"))
                if not parsed_time:
                    continue
                event_time, rendered_time = parsed_time
                if event_time < threshold:
                    continue
                end = events[index + 1].start() if index + 1 < len(events) else len(chunk)
                message = chunk[event.end():end]
                sn_match = re.search(
                    r"(?:SNRead|SerialNumber|MLB_SN|PrimaryIdentity)\s*[:=]\s*([A-Za-z0-9_-]+)",
                    message, re.I,
                )
                sn = normalise_sn(sn_match.group(1)) if sn_match and is_trusted_sn(sn_match.group(1)) else ""
                fields = next(csv.reader([message.lstrip(" ,\r\n")]), [])
                if (not sn and len(fields) > 5 and fields[3].strip() == "--"
                        and fields[4].strip().lower() == "snread" and is_trusted_sn(fields[5])):
                    sn = normalise_sn(fields[5])
                status = "COMPLETING" if re.search(r"CloseFixture|complete|finish", message, re.I) else "TESTING"
                observations.append(B482Observation(
                    B482ObservationKind.CASEINFO_ACTIVITY, slot, status, sn, str(path), path.name,
                    rendered_time, batch_evidence="caseinfo_date={};thread={}".format(match.group("date"), slot),
                ))
        return observations
