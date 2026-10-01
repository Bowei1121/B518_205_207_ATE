"""Atlas active/archive discovery and source-evidence interpretation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

from log_monitoring import (
    file_signature,
    parse_archive_timestamp,
    records_status,
    snapshot_files,
    trusted_sn_from_records,
)


@dataclass(frozen=True)
class AtlasObservation:
    """A source fact for the round monitor to apply to its shared state."""

    kind: str
    slot: Optional[int] = None
    sn: str = ""
    status: str = ""
    source: str = ""


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
        self._inactive_since: Optional[datetime] = None
        self._prepared_reported = False

    def poll(self) -> Tuple[AtlasObservation, ...]:
        observations: List[AtlasObservation] = []
        if not self._prepared_reported:
            self._prepared_reported = True
            observations.append(AtlasObservation("source_prepared"))

        active_now: Set[int] = set()
        active_directories: Set[int] = set()
        for slot in self.slots:
            if (self.active_root / "group0-slot{}".format(slot)).is_dir():
                active_directories.add(slot)
            record = self._active_records(slot)
            if record and self._is_new_or_changed(record, self._baseline_active):
                active_now.add(slot)
                self._seen_slots.add(slot)
                sn = trusted_sn_from_records(record)
                if sn and slot not in self._locked_sn:
                    self._locked_sn[slot] = sn
                    observations.append(AtlasObservation("sn_locked", slot, sn, "TESTING", str(record)))
                elif slot not in self._locked_sn:
                    observations.append(AtlasObservation("activity", slot, status="TESTING", source=str(record)))
                else:
                    observations.append(AtlasObservation(
                        "activity", slot, self._locked_sn[slot], "TESTING", str(record),
                    ))

        for slot in sorted(self._seen_slots - active_now):
            if slot not in self._locked_sn:
                observations.append(AtlasObservation("sn_read_failed", slot, "SN 讀取失敗", "FAIL"))
                continue
            sn = self._locked_sn[slot]
            observations.append(AtlasObservation("completing", slot, sn, "COMPLETING"))
            candidate = self._final_csv(sn)
            if candidate:
                state = records_status(candidate)
                if state in {"PASS", "FAIL"}:
                    observations.append(AtlasObservation("final", slot, sn, state, str(candidate)))

        if self._seen_slots and not active_directories:
            if self._inactive_since is None:
                self._inactive_since = self.now()
            elif self.now() - self._inactive_since >= timedelta(seconds=3):
                for slot in sorted(set(self.slots) - self._seen_slots):
                    observations.append(AtlasObservation("notest", slot, status="NOTEST"))
        else:
            self._inactive_since = None
        return tuple(observations)

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
        candidates: List[Tuple[datetime, Path]] = []
        for folder in sn_root.iterdir():
            if not folder.is_dir():
                continue
            stamp = parse_archive_timestamp(folder.name)
            if stamp is None or stamp < threshold:
                continue
            for name in ("records.csv", "record.csv"):
                candidate = folder / "system" / name
                if candidate.is_file() and self._is_new_or_changed(candidate, self._baseline_final):
                    candidates.append((stamp, candidate))
        return max(candidates, key=lambda item: item[0])[1] if candidates else None
