"""RS-WMT monitor lifecycle, driven by its platform source adapter."""

from pathlib import Path
from typing import Optional, Sequence

from log_monitoring import BaseMonitor, MonitorEvent, TERMINAL
from rswmt_source_adapter import (
    RsWmtRecord,
    RsWmtSourceAdapter,
    parse_rswmt_csv,
    parse_rswmt_log,
)


class RsWmtLogMonitor(BaseMonitor):
    """Translate RS-WMT source evidence into the shared BT round contract."""

    def __init__(self, output_root: Path, slots: Sequence[int] = (1, 2, 3, 4),
                 progress_root: Optional[Path] = None, **kwargs):
        self.output_root = Path(output_root)
        self.progress_root = Path(progress_root) if progress_root else self.output_root
        super().__init__('BT', {'format': 'B518 RS-WMT', 'output_root': str(output_root),
                               'progress_root': str(self.progress_root)}, slots, **kwargs)
        self.source_adapter = RsWmtSourceAdapter(
            self.output_root, self.slots, self.started, self.progress_root, self.now, self.monotonic,
        )

    def _notice(self, source: str, message: str, detail=None) -> None:
        self.emit(MonitorEvent('warning', message, source=source, detail=detail or {}))

    def _accept_final(self, record: RsWmtRecord, stable: bool) -> None:
        current = self.results[record.slot]
        if current.sn and record.sn and current.sn != record.sn:
            self._notice(record.source, 'RS-WMT: serial conflict for slot; result not accepted.')
            return
        if current.status in TERMINAL:
            if current.source != record.source:
                self._notice(record.source, 'RS-WMT: duplicate/late slot result ignored; previous result retained.')
            return
        status = record.status if stable else 'COMPLETING'
        if status != current.status or record.sn != current.sn or record.source != current.source:
            self.set_result(record.slot, status, record.sn, record.source, record.evidence())

    def _accept_progress(self, record: RsWmtRecord) -> None:
        current = self.results[record.slot]
        if current.status in TERMINAL:
            return
        if current.sn and record.sn and current.sn != record.sn:
            self._notice(record.source, 'RS-WMT: serial conflict for slot; progress not accepted.')
            return
        # A final export stays COMPLETING during its stable-write interval.
        status = 'COMPLETING' if current.status == 'COMPLETING' else record.status
        if status != current.status or (record.sn and record.sn != current.sn):
            self.set_result(record.slot, status, record.sn, record.source, record.evidence())

    def poll_once(self) -> None:
        if self.finished or self._stop.is_set():
            return
        for observation in self.source_adapter.poll():
            if observation.kind == 'warning':
                evidence = observation.evidence
                if evidence is None and observation.record is not None:
                    evidence = observation.record.evidence()
                self._notice(observation.source, observation.message, evidence)
            elif observation.kind == 'batch' and observation.record:
                self.emit(MonitorEvent(
                    'batch', 'RS-WMT batch {}'.format(observation.record.started),
                    source=observation.record.source, detail=observation.record.evidence(),
                ))
            elif observation.kind == 'final' and observation.record:
                self._accept_final(observation.record, observation.stable)
            elif observation.kind == 'progress' and observation.record:
                self._accept_progress(observation.record)
