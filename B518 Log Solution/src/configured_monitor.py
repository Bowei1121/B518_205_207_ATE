"""Apply a profile's source-to-display mapping at the shared monitor seam."""

from __future__ import annotations

from dataclasses import replace
from typing import Callable, Dict, Mapping


class ConfiguredMonitor:
    """Expose a platform monitor using the display positions in its profile."""

    def __init__(self, monitor, source_to_display: Mapping[int, int]):
        self._monitor = monitor
        self._source_to_display = dict(source_to_display)
        self._display_to_source = {display: source for source, display in self._source_to_display.items()}

    @property
    def session(self):
        return self._monitor.session

    @property
    def started(self):
        return self._monitor.started

    @property
    def results(self):
        return {result.slot: result for result in self.round_results()}

    def deliver(self, event, callback: Callable):
        display = self._source_to_display.get(event.slot) if event.slot is not None else None
        if event.slot is not None and display is None:
            if event.kind in {"warning", "result", "result_candidate", "final", "unresolved_source_conflict"}:
                detail = dict(event.detail)
                detail["source_slot"] = str(event.slot)
                detail.setdefault("source_position", str(event.slot))
                if event.kind != "warning":
                    event = replace(event, kind="unmapped_source",
                                    message="未映射來源位置 {}：證據已保留，未套用至顯示位置".format(event.slot))
                callback(replace(event, slot=None, detail=detail))
            return "ignore"
        if event.slot is None:
            return callback(event)
        detail = dict(event.detail)
        detail.setdefault("source_position", str(event.slot))
        return callback(replace(event, slot=display, detail=detail))

    def round_results(self):
        return tuple(
            replace(result, slot=display)
            for result in self._monitor.round_results()
            for display in (self._source_to_display.get(result.slot),)
            if display is not None
        )

    def timeout_seconds(self, kind):
        return self._monitor.timeout_seconds(kind)

    def update_round_settings(self, settings):
        self._monitor.update_round_settings(settings)

    def publish_round_event(self, event):
        if event.slot is None:
            self._monitor.publish_round_event(event)
            return
        source_slot = self._source_slot(event.slot)
        if source_slot is not None:
            detail = dict(event.detail)
            detail.setdefault("source_position", str(source_slot))
            self._monitor.publish_round_event(replace(event, slot=source_slot, detail=detail))

    def poll_once(self):
        self._monitor.poll_once()

    def start(self):
        self._monitor.start()

    def stop_collection(self):
        self._monitor.stop_collection()

    def finish(self):
        self._monitor.finish()

    def stop(self):
        self._monitor.stop()

    def set_result(self, slot, status, sn=None, source="", detail=None, lock_terminal=False):
        """Apply a round decision expressed in display positions to its source slot."""
        source_slot = self._source_slot(slot)
        if source_slot is None:
            return
        evidence = dict(detail or {})
        evidence.setdefault("source_position", str(source_slot))
        self._monitor.set_result(source_slot, status, sn, source, evidence, lock_terminal)

    def apply_round_result(self, slot, status, sn="", source="", detail=None, lock_terminal=False):
        source_slot = self._source_slot(slot)
        if source_slot is None:
            return
        evidence = dict(detail or {})
        evidence.setdefault("source_position", str(source_slot))
        self._monitor.apply_round_result(source_slot, status, sn, source, evidence, lock_terminal)

    def _source_slot(self, display_slot):
        return self._display_to_source.get(display_slot)
