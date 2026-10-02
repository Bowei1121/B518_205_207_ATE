"""Apply a profile's source-to-display mapping at the shared monitor seam."""

from __future__ import annotations

from dataclasses import replace
from typing import Callable, Dict, Mapping


class ConfiguredMonitor:
    """Expose a platform monitor using the display positions in its profile."""

    def __init__(self, monitor, source_to_display: Mapping[int, int]):
        self._monitor = monitor
        self._source_to_display = dict(source_to_display)

    @property
    def results(self):
        return {
            display: replace(result, slot=display)
            for source, result in self._monitor.results.items()
            for display in (self._source_to_display.get(source),)
            if display is not None
        }

    def deliver(self, event, callback: Callable) -> None:
        display = self._source_to_display.get(event.slot) if event.slot is not None else None
        if event.slot is not None and display is None:
            if event.kind == "warning":
                detail = dict(event.detail)
                detail["source_slot"] = str(event.slot)
                callback(replace(event, slot=None, detail=detail))
            return
        callback(replace(event, slot=display) if event.slot is not None else event)

    def set_result(self, slot, status, sn=None, source="", detail=None, lock_terminal=False):
        """Apply a round decision expressed in display positions to its source slot."""
        source_slot = next((native for native, display in self._source_to_display.items()
                            if display == slot), None)
        if source_slot is None:
            return
        self._monitor.set_result(source_slot, status, sn, source, detail, lock_terminal)

    def emit_display_event(self, event) -> None:
        """Emit a round event whose optional slot is already a display position."""
        if event.slot is None:
            if hasattr(self._monitor, "emit"):
                self._monitor.emit(event)
            else:
                self._monitor.callback(event)
            return
        source_slot = next((native for native, display in self._source_to_display.items()
                            if display == event.slot), None)
        if source_slot is not None:
            source_event = replace(event, slot=source_slot)
            if hasattr(self._monitor, "emit"):
                self._monitor.emit(source_event)
            else:
                self._monitor.callback(source_event)

    def __getattr__(self, name):
        return getattr(self._monitor, name)
