"""Pure local-file monitoring core for B518 DFU, FCT and BT stations.

This module deliberately has no device-control dependencies.  The Tk UI only
subscribes to events emitted here; the same core is used by unit tests.
"""

from __future__ import annotations

import csv
import json
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Set

from b482_source_adapter import (
    B482ObservationKind,
    B482SourceAdapter,
    CASEINFO_FILE,
    CASEINFO_TIMESTAMP,
    parse_bt_csv,
    parse_bt_filename,
)
from atlas_source_adapter import (
    AtlasObservationKind,
    AtlasSourceAdapter,
    parse_archive_timestamp,
    records_status,
    trusted_sn_from_records,
)
from monitoring_files import (
    file_signature,
    is_trusted_sn,
    normalise_sn,
    snapshot_files,
)

TERMINAL = {"PASS", "FAIL", "NOTEST", "STOPPED", "TIMEOUT"}
DEFAULT_TIMEOUTS = {
    "DFU": {"start": 30, "test": 480, "round": 7200},
    "FCT": {"start": 30, "test": 480, "round": 7200},
    "BT": {"start": 30, "test": 240, "round": 7200},
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

    def event(self, message: str, detail: Optional[Dict[str, str]] = None) -> None:
        with (self.path / "events.log").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "message": message,
                "detail": detail or {},
            }, ensure_ascii=False) + "\n")

    def update_results(self, results: Iterable[SlotResult]) -> None:
        with (self.path / "results.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["slot", "sn", "status", "source", "updated_at"])
            writer.writeheader()
            writer.writerows(asdict(result) for result in sorted(results, key=lambda result: result.slot))

    def source(self, path: Path) -> None:
        self.sources.add(str(path))
        self._write_metadata()

    def update_settings(self, settings: Dict[str, object]) -> None:
        self.settings.update(settings)
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
                 test_timeout_seconds: Optional[int] = None,
                 round_timeout_seconds: Optional[int] = None,
                 round_started_monotonic: Optional[float] = None):
        self.station, self.settings, self.slots = station, settings, tuple(sorted(slots))
        defaults = DEFAULT_TIMEOUTS.get(station.upper(), DEFAULT_TIMEOUTS["FCT"])
        self.start_timeout_seconds = int(start_timeout_seconds or defaults["start"])
        self.test_timeout_seconds = int(test_timeout_seconds or defaults["test"])
        self.round_timeout_seconds = int(round_timeout_seconds or defaults["round"])
        if min(self.start_timeout_seconds, self.test_timeout_seconds, self.round_timeout_seconds) <= 0:
            raise ValueError("逾時秒數必須為正整數")
        self.settings.update({"start_timeout_seconds": str(self.start_timeout_seconds),
                              "test_timeout_seconds": str(self.test_timeout_seconds),
                              "round_timeout_seconds": str(self.round_timeout_seconds)})
        self.callback, self.now, self.monotonic = callback, now, monotonic
        self.started = now()
        self._started_monotonic = (monotonic() if round_started_monotonic is None
                                   else round_started_monotonic)
        self._deadline_locked_slots: Set[int] = set()
        self.results = {slot: SlotResult(slot=slot) for slot in self.slots}
        session_id = "{}-{}".format(station.lower(), self.started.strftime("%Y%m%d-%H%M%S-%f"))
        self.session = SessionStore(session_id, settings, session_root)
        self.finished = False
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def emit(self, event: MonitorEvent) -> None:
        self.session.event(event.message, event.detail)
        if event.source:
            self.session.source(Path(event.source))
        if self.callback:
            self.callback(event)

    def set_result(self, slot: int, status: str, sn: Optional[str] = None, source: str = "",
                   detail: Optional[Dict[str, str]] = None, lock_terminal: bool = False) -> None:
        if self.finished:
            return
        if slot in self._deadline_locked_slots:
            return
        result = self.results[slot]
        if result.status in TERMINAL and status not in TERMINAL:
            return
        if sn:
            result.sn = sn
        result.status, result.source = status, source or result.source
        result.updated_at = self.now().isoformat(timespec="seconds")
        self.session.update_results(self.results.values())
        self.emit(MonitorEvent("result", "slot{} {}".format(slot, status), slot, result.sn, status,
                               source, detail or {}))
        if lock_terminal:
            self._deadline_locked_slots.add(slot)

    def start(self) -> None:
        """Mark adapter readiness; MonitoringRound owns the polling schedule."""
        return

    def stop_collection(self) -> None:
        """Stop source reads while leaving round result-release policy to the round."""
        self._stop.set()

    def finish(self) -> None:
        self.stop_collection()
        if not self.finished:
            self.finished = True
            self.session.finish()

    def stop(self) -> None:
        self._stop.set()
        if not self.finished:
            for slot, result in self.results.items():
                if result.status not in TERMINAL:
                    self.set_result(slot, "STOPPED")
            self.finish()
            self.emit(MonitorEvent("stopped", "{} 監控已由人員停止".format(self.station)))

    def poll_once(self) -> None:
        raise NotImplementedError


class AtlasActiveArchiveMonitor(BaseMonitor):
    """DFU/FCT monitor: active/group0-slotN followed by final archive data."""
    def __init__(self, station: str, active_root: Path, final_root: Path, slots: Sequence[int], **kwargs):
        super().__init__(station, {"active_root": str(active_root), "final_root": str(final_root)}, slots, **kwargs)
        self.source = AtlasSourceAdapter(active_root, final_root, slots, self.started, self.now)

    def poll_once(self) -> None:
        if self.finished or self._stop.is_set():
            return
        for observation in self.source.poll():
            if observation.kind == AtlasObservationKind.SOURCE_PREPARED:
                self.emit(MonitorEvent("source_prepared", "Atlas 來源啟動前快照完成，監控準備就緒。"))
            elif observation.kind == AtlasObservationKind.SN_LOCKED:
                self.set_result(observation.slot, observation.status, observation.sn, observation.source)
                self.emit(MonitorEvent(
                    "sn_locked", "slot{} 已鎖定可信 SN".format(observation.slot),
                    observation.slot, observation.sn, observation.status, observation.source,
                ))
            elif observation.kind == AtlasObservationKind.ACTIVITY:
                self.set_result(observation.slot, observation.status, observation.sn, observation.source)
            elif observation.kind == AtlasObservationKind.SN_READ_FAILED:
                self.set_result(observation.slot, observation.status, observation.sn)
            elif observation.kind in {AtlasObservationKind.COMPLETING, AtlasObservationKind.NOTEST}:
                self.set_result(observation.slot, observation.status, observation.sn)
            elif observation.kind == AtlasObservationKind.FINAL:
                self.set_result(observation.slot, observation.status, observation.sn, observation.source)
                self.emit(MonitorEvent(
                    "final", "slot{} 最終 {}".format(observation.slot, observation.status),
                    observation.slot, observation.sn, observation.status, observation.source,
                ))



class BtLogMonitor(BaseMonitor):
    """BT TestData monitor with timestamp batch locking and optional CaseInfo."""
    def __init__(self, testdata_root: Path, slots: Sequence[int], caseinfo_root: Optional[Path] = None, **kwargs):
        monotonic = kwargs.pop("monotonic", time.monotonic)
        super().__init__("BT", {"testdata_root": str(testdata_root), "caseinfo_root": str(caseinfo_root or "")}, slots,
                         monotonic=monotonic, **kwargs)
        self.testdata_root, self.caseinfo_root = testdata_root, caseinfo_root
        self.source_adapter = B482SourceAdapter(
            testdata_root, caseinfo_root, self.started, self.now, self.monotonic,
        )
        self.batch_stamp = ""
        self.review_pending: Optional[Dict[str, object]] = None
        self.review_decisions: Dict[str, str] = {}

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

    def poll_once(self) -> None:
        if self.finished or self._stop.is_set():
            return
        for observation in self.source_adapter.poll():
            if observation.kind == B482ObservationKind.CASEINFO_ACTIVITY:
                if observation.slot not in self.results or self.results[observation.slot].status in TERMINAL:
                    continue
                self.set_result(observation.slot, observation.status, observation.sn,
                                observation.source, observation.evidence())
                continue
            if not self.batch_stamp:
                self.batch_stamp = observation.batch_id
                self.emit(MonitorEvent(
                    "batch", "BT 鎖定批次 {}".format(self.batch_stamp), source=observation.source,
                    detail=observation.evidence(),
                ))
            if observation.batch_id != self.batch_stamp:
                decision = self.review_decisions.get(observation.source)
                if decision == "reject":
                    continue
                if decision == "accept":
                    self.batch_stamp = observation.batch_id
                    for result_slot, result in self.results.items():
                        if result.status not in TERMINAL:
                            self.set_result(result_slot, "WAITING", "")
                    self.emit(MonitorEvent(
                        "batch", "BT 人工確認切換批次 {}".format(self.batch_stamp), source=observation.source,
                        detail=observation.evidence(),
                    ))
                else:
                    if self.review_pending is None:
                        self.review_pending = {
                            "kind": "batch", "path": observation.source, "stamp": observation.batch_id,
                            "locked": self.batch_stamp,
                        }
                        self.emit(MonitorEvent(
                            "review", "BT 偵測批次衝突，等待人工覆核", source=observation.source,
                            detail={"batch_id": observation.batch_id, "locked_batch_id": self.batch_stamp,
                                    "source_id": observation.source_id},
                        ))
                    continue
            slot = observation.slot
            if slot not in self.results:
                continue
            current = self.results[slot]
            if current.status in TERMINAL and current.source != observation.source:
                decision = self.review_decisions.get(observation.source)
                if decision == "reject":
                    continue
                if decision != "accept":
                    if self.review_pending is None:
                        self.review_pending = {"kind": "duplicate", "path": observation.source, "slot": slot,
                                               "old": current.source, "new": observation.source}
                        self.emit(MonitorEvent(
                            "review", "BT Thread{} 出現重複結果，等待人工覆核".format(slot - 1), slot,
                            source=observation.source, detail=observation.evidence(),
                        ))
                    continue
            self.set_result(slot, observation.status, observation.sn, observation.source, observation.evidence())
