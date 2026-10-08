"""Atlas active/archive discovery and source-evidence interpretation."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

from monitoring_files import file_signature, is_trusted_sn, normalise_sn, read_csv_rows, snapshot_files


ARCHIVE_TIMESTAMP = re.compile(
    r"^(?P<date>\d{8})_(?P<hour>\d{1,2})-(?P<minute>\d{2})-(?P<second>\d{2})"
    r"(?:\.(?P<millisecond>\d{1,3}))?(?:-.+)?$"
)
TRUSTED_SN_FIELDS = {"mlb_sn", "primaryidentity", "serialnumber"}
MAX_SOURCE_POSITION = 20


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


def trusted_sn_from_records(path: Path, on_error=None) -> str:
    for row in read_csv_rows(path, on_error):
        for key, value in row.items():
            if key.strip().lower().replace(" ", "_") in TRUSTED_SN_FIELDS and is_trusted_sn(value):
                return normalise_sn(value)
        values = list(row.values())
        if len(values) >= 2 and values[0].strip().lower().replace(" ", "_") in TRUSTED_SN_FIELDS:
            if is_trusted_sn(values[1]):
                return normalise_sn(values[1])
    return ""


def records_status(path: Path, on_error=None) -> str:
    statuses = [
        value.strip().upper()
        for row in read_csv_rows(path, on_error)
        for key, value in row.items()
        if key.strip().lower() == "status" and value.strip()
    ]
    if not statuses:
        return "UNKNOWN"
    if any(value.startswith("FAIL") for value in statuses):
        return "FAIL"
    if all(value.startswith("PASS") for value in statuses):
        return "PASS"
    return "UNKNOWN"


class AtlasObservationKind(str, Enum):
    SOURCE_PREPARED = "source_prepared"
    SN_LOCKED = "sn_locked"
    ACTIVITY = "activity"
    SN_READ_FAILED = "sn_read_failed"
    COMPLETING = "completing"
    FINAL = "final"
    NOTEST = "notest"
    UNRESOLVED_CONFLICT = "unresolved_conflict"
    SOURCE_ERROR = "source_error"


@dataclass(frozen=True)
class AtlasObservation:
    """A source fact for the round monitor to apply to its shared state."""

    kind: AtlasObservationKind
    slot: Optional[int] = None
    sn: str = ""
    status: str = ""
    source: str = ""
    detail: Dict[str, str] = None


class AtlasSourceAdapter:
    """Own Atlas paths, startup snapshots, identity locking, and final evidence."""

    def __init__(self, active_root: Path, final_root: Path, slots: Sequence[int],
                 started: datetime, now):
        self.active_root = active_root
        self.final_root = final_root
        self.slots = tuple(sorted(slots))
        self.started = started
        self.now = now
        self._baseline_active = snapshot_files(active_root, ".csv")
        self._baseline_final = snapshot_files(final_root, ".csv")
        self._seen_slots: Set[int] = set()
        self._locked_sn: Dict[int, str] = {}
        self._locked_source: Dict[int, str] = {}
        self._active_signatures: Dict[str, Tuple[int, int]] = {}
        self._completion_reported_slots: Set[int] = set()
        self._prepared_reported = False
        self._final_signatures: Dict[str, Tuple[int, int]] = {}
        self._delivered_final_signatures: Dict[str, Tuple[int, int]] = {}
        self._pending_source_errors = []
        self._reported_source_errors = set()

    def _record_source_error(self, path: Path, error: Exception) -> None:
        key = (str(path), str(error))
        if key not in self._reported_source_errors:
            self._reported_source_errors.add(key)
            self._pending_source_errors.append((path, error))

    def poll(self) -> Tuple[AtlasObservation, ...]:
        observations: List[AtlasObservation] = []
        if not self._prepared_reported:
            self._prepared_reported = True
            observations.append(AtlasObservation(AtlasObservationKind.SOURCE_PREPARED))

        active_directories: Set[int] = set()
        for slot in self.slots:
            if (self.active_root / "group0-slot{}".format(slot)).is_dir():
                active_directories.add(slot)
            record = self._active_records(slot)
            if record and self._is_new_or_changed(record, self._baseline_active):
                self._seen_slots.add(slot)
                try:
                    signature = file_signature(record)
                except OSError:
                    continue
                key = str(record.resolve())
                if self._active_signatures.get(key) == signature:
                    continue
                self._active_signatures[key] = signature
                sn = trusted_sn_from_records(
                    record, lambda error, source=record: self._record_source_error(source, error),
                )
                if sn and slot not in self._locked_sn:
                    self._locked_sn[slot] = sn
                    self._locked_source[slot] = str(record)
                    evidence = self._active_evidence(slot, sn, record)
                    observations.append(AtlasObservation(
                        AtlasObservationKind.SN_LOCKED, slot, sn, "TESTING", str(record), evidence,
                    ))
                elif slot in self._locked_sn and sn and sn != self._locked_sn[slot]:
                    observations.append(AtlasObservation(
                        AtlasObservationKind.UNRESOLVED_CONFLICT, slot, sn, "TESTING", str(record),
                        {"source_id": record.name, "source_time": "unknown", "source_slot": str(slot),
                         "original_sn": self._locked_sn[slot], "candidate_sn": sn,
                         "original_source_id": Path(self._locked_source[slot]).name,
                         "candidate_status": "TESTING", "original_status": "TESTING",
                         "reason": "active_record_identity_changed_without_round_link"},
                    ))
                elif slot not in self._locked_sn:
                    observations.append(AtlasObservation(
                        AtlasObservationKind.ACTIVITY, slot, status="TESTING", source=str(record),
                        detail=self._active_evidence(slot, "", record),
                    ))
                else:
                    observations.append(AtlasObservation(
                        AtlasObservationKind.ACTIVITY, slot, self._locked_sn[slot], "TESTING", str(record),
                        self._active_evidence(slot, self._locked_sn[slot], record),
                    ))

        # A quiet or unchanged records.csv is still active while its slot tree
        # exists. Only disappearance of the active directory starts finalization.
        for slot in sorted(self._seen_slots - active_directories):
            if slot not in self._locked_sn:
                if slot not in self._completion_reported_slots:
                    active_record = self._active_records(slot)
                    observations.append(AtlasObservation(
                        AtlasObservationKind.SN_READ_FAILED, slot, "SN 讀取失敗", "FAIL",
                        str(active_record) if active_record else "",
                        self._active_evidence(slot, "", active_record),
                    ))
                    self._completion_reported_slots.add(slot)
                continue
            sn = self._locked_sn[slot]
            if slot not in self._completion_reported_slots:
                observations.append(AtlasObservation(
                    AtlasObservationKind.COMPLETING, slot, sn, "COMPLETING",
                    detail=self._active_evidence(slot, sn, None),
                ))
                self._completion_reported_slots.add(slot)
            candidate = self._final_csv(sn)
            if candidate:
                state = records_status(
                    candidate, lambda error, source=candidate: self._record_source_error(source, error),
                )
                if state in {"PASS", "FAIL"}:
                    key = str(candidate.resolve())
                    signature = file_signature(candidate)
                    if self._delivered_final_signatures.get(key) != signature:
                        stamp = parse_archive_timestamp(candidate.parent.parent.name)
                        detail = self._active_evidence(slot, sn, candidate)
                        detail["source_id"] = candidate.name
                        detail["source_time"] = stamp.isoformat(timespec="milliseconds") if stamp else ""
                        self._delivered_final_signatures[key] = signature
                        observations.append(AtlasObservation(
                            AtlasObservationKind.FINAL, slot, sn, state, str(candidate), detail,
                        ))

        observations.extend(AtlasObservation(
            AtlasObservationKind.SOURCE_ERROR, source=str(path),
            detail={"raw_diagnostic": str(error), "source_id": path.name},
        ) for path, error in self._pending_source_errors)
        self._pending_source_errors.clear()
        return tuple(observations)

    @staticmethod
    def _active_evidence(slot: int, sn: str, source: Optional[Path]) -> Dict[str, str]:
        detail = {
            "source_id": source.name if source is not None else "unknown",
            "source_time": "unknown",
            "source_slot": str(slot),
        }
        if sn:
            # A trusted SN observed in this active slot lifecycle links its
            # archived result back to the same source round. Paths and app
            # round IDs alone are deliberately insufficient evidence.
            detail["round_evidence_id"] = "atlas:{}:{}".format(slot, sn)
            detail["same_round_evidence"] = "active_slot_trusted_sn"
        return detail

    def _active_records(self, slot: int) -> Optional[Path]:
        root = self.active_root / "group0-slot{}".format(slot)
        if not root.is_dir():
            return None
        candidates = list(root.rglob("records.csv")) + list(root.rglob("record.csv"))
        return max(candidates, key=lambda path: path.stat().st_mtime_ns) if candidates else None

    @staticmethod
    def _is_new_or_changed(path: Path, baseline: Dict[str, Tuple[int, int]]) -> bool:
        try:
            return baseline.get(str(path.resolve())) != file_signature(path)
        except OSError:
            return False

    def _final_csv(self, sn: str) -> Optional[Path]:
        sn_root = self.final_root / sn
        if not sn_root.is_dir():
            return None
        threshold = self.started - timedelta(seconds=30)
        candidates: List[Tuple[datetime, Path, Tuple[int, int]]] = []
        for folder in sn_root.iterdir():
            if not folder.is_dir():
                continue
            stamp = parse_archive_timestamp(folder.name)
            if stamp is None or stamp < threshold:
                continue
            for name in ("records.csv", "record.csv"):
                candidate = folder / "system" / name
                if candidate.is_file() and self._is_new_or_changed(candidate, self._baseline_final):
                    try:
                        candidates.append((stamp, candidate, file_signature(candidate)))
                    except OSError:
                        continue
        if not candidates:
            return None
        _stamp, candidate, signature = max(candidates, key=lambda item: item[0])
        key = str(candidate.resolve())
        if self._final_signatures.get(key) != signature:
            self._final_signatures[key] = signature
            return None
        return candidate
