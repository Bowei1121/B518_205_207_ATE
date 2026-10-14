"""Read and render historical event records without changing their source files."""

from __future__ import annotations

import json
import os
import stat
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from app_event_store import iter_app_event_store_events
from audit_records import iter_round_audit_events
from language_catalog import (capture_round_event_message, make_bilingual_message, translate)


@dataclass(frozen=True)
class HistoricalEvent:
    key: str
    source: str
    occurred_at: str
    message: str
    kind: str = ""
    round_id: Optional[str] = None
    sequence: Optional[int] = None
    localized_message: Optional[dict] = None
    diagnostic: str = ""
    detail: object = None
    raw_record: object = None
    station: str = ""
    platform: str = ""
    unrecognized: bool = False
    source_order: int = 0


@dataclass(frozen=True)
class HistoricalEventPresentation:
    message: str
    detail: str
    unrecognized: bool = False


@dataclass(frozen=True)
class HistoricalEventSource:
    """One precedence-resolved source file used by history queries."""

    key: str
    kind: str
    path: Path


def read_historical_events(session_root: Path, app_event_path: Optional[Path] = None
                           ) -> Tuple[HistoricalEvent, ...]:
    """Reconstruct disk history using the existing strict readers; never repair or write."""
    return tuple(sorted(iter_historical_events(session_root, app_event_path), key=_event_sort_key))


def iter_historical_events(session_root: Path, app_event_path: Optional[Path] = None,
                          read_observer=None, source_observer=None):
    """Yield disk history source by source without retaining a combined history collection."""
    root = Path(session_root)
    if root.exists():
        try:
            directories = sorted(path for path in root.iterdir() if path.is_dir())
        except OSError as error:
            directories = []
            yield _read_error("round", root, str(error))
        for directory in directories:
            audit_path = directory / "audit.jsonl"
            legacy_path = directory / "events.log"
            if audit_path.is_file():
                if source_observer is not None:
                    source_observer(audit_path)
                try:
                    header, audit_events = iter_round_audit_events(
                        audit_path, read_observer=read_observer)
                except Exception as error:
                    yield _read_error("round", audit_path, str(error))
                    continue
                round_id = header["round_id"]
                station = header.get("station", "")
                platform = header.get("config", {}).get("platform", "")
                try:
                    for event in audit_events:
                        yield HistoricalEvent(
                            "round:{}:{}".format(round_id, event["sequence"]), "round",
                            event["observed_at"], event["message"], event["kind"], round_id,
                            event["sequence"], event.get("localized_message"),
                            _diagnostic(event), event.get("detail", {}), event,
                            station, platform,
                        )
                except Exception as error:
                    yield _read_error("round", audit_path, str(error))
                    continue
                if not header.get("audit_complete", False):
                    yield HistoricalEvent(
                        "warning:round:{}".format(round_id), "read_warning", "",
                        "Audit records report an incomplete save", round_id=round_id,
                        station=station, platform=platform,
                        raw_record={"audit_path": str(audit_path),
                                    "reason": "audit_complete is false"},
                    )
            elif legacy_path.is_file():
                if source_observer is not None:
                    source_observer(legacy_path)
                yield from _read_legacy_session_events(
                    legacy_path, read_observer=read_observer)

    if app_event_path is not None and Path(app_event_path).exists():
        path = Path(app_event_path)
        if source_observer is not None:
            source_observer(path)
        try:
            app_events = iter_app_event_store_events(path, read_observer=read_observer)
        except Exception as error:
            yield _read_error("app", path, str(error))
        else:
            try:
                for event in app_events:
                    yield HistoricalEvent(
                        "app:{}".format(event["event_id"]), "app", event["occurred_at"],
                        event["message"], event["kind"], None, event["sequence"],
                        event.get("localized_message"), event.get("diagnostic", ""),
                        event.get("localized_message", {}).get("parameters", {}), event,
                    )
            except Exception as error:
                yield _read_error("app", path, str(error))


def iter_historical_event_sources(session_root: Path,
                                  app_event_path: Optional[Path] = None):
    """Discover read-only files after applying audit-over-legacy source priority."""
    root = Path(session_root)
    root_before = _path_version(root)
    directory_versions = {}
    if root_before is not None:
        directories = []
        for path in root.iterdir():
            try:
                details = path.stat()
            except FileNotFoundError:
                continue
            if stat.S_ISDIR(details.st_mode):
                directories.append(path)
                directory_versions[path] = _stat_version(details)
        for directory in sorted(directories):
            audit_path = directory / "audit.jsonl"
            legacy_path = directory / "events.log"
            if _is_regular_file(audit_path):
                yield HistoricalEventSource(_source_key("round-audit", audit_path),
                                            "round-audit", audit_path)
            elif _is_regular_file(legacy_path):
                yield HistoricalEventSource(_source_key("legacy", legacy_path),
                                            "legacy", legacy_path)
        if (_path_version(root) != root_before or any(
                _path_version(path) != version for path, version in directory_versions.items())):
            raise OSError("Historical source list changed during discovery")
    elif _path_version(root) is not None:
        raise OSError("Historical source directory appeared during discovery")
    if app_event_path is not None:
        path = Path(app_event_path)
        if _is_regular_file(path):
            yield HistoricalEventSource(_source_key("app", path), "app", path)


def _is_regular_file(path: Path) -> bool:
    try:
        details = path.stat()
    except FileNotFoundError:
        return False
    if not stat.S_ISREG(details.st_mode):
        raise OSError("Historical source is not a regular file: {}".format(path))
    return True


def _path_version(path: Path):
    try:
        details = path.stat()
    except FileNotFoundError:
        return None
    return _stat_version(details)


def _stat_version(details: os.stat_result):
    return (details.st_dev, details.st_ino, details.st_size,
            details.st_mtime_ns, details.st_ctime_ns)


def _source_key(kind: str, path: Path) -> str:
    return "{}:{}".format(kind, path.resolve())


def iter_historical_source_events(source: HistoricalEventSource, read_observer=None):
    """Read one discovered source with its existing strict reader and diagnostics."""
    path = Path(source.path)
    if source.kind == "round-audit":
        try:
            header, events = iter_round_audit_events(path, read_observer=read_observer)
        except Exception as error:
            yield _read_error("round", path, str(error))
            return
        round_id = header["round_id"]
        station = header.get("station", "")
        platform = header.get("config", {}).get("platform", "")
        try:
            for event in events:
                yield HistoricalEvent(
                    "round:{}:{}".format(round_id, event["sequence"]), "round",
                    event["observed_at"], event["message"], event["kind"], round_id,
                    event["sequence"], event.get("localized_message"), _diagnostic(event),
                    event.get("detail", {}), event, station, platform)
        except Exception as error:
            yield _read_error("round", path, str(error))
            return
        if not header.get("audit_complete", False):
            yield HistoricalEvent(
                "warning:round:{}".format(round_id), "read_warning", "",
                "Audit records report an incomplete save", round_id=round_id,
                station=station, platform=platform,
                raw_record={"audit_path": str(path), "reason": "audit_complete is false"})
        return
    if source.kind == "legacy":
        yield from _read_legacy_session_events(path, read_observer=read_observer)
        return
    if source.kind == "app":
        try:
            app_events = iter_app_event_store_events(path, read_observer=read_observer)
            for event in app_events:
                yield HistoricalEvent(
                    "app:{}".format(event["event_id"]), "app", event["occurred_at"],
                    event["message"], event["kind"], None, event["sequence"],
                    event.get("localized_message"), event.get("diagnostic", ""),
                    event.get("localized_message", {}).get("parameters", {}), event)
        except Exception as error:
            yield _read_error("app", path, str(error))
        return
    raise ValueError("unsupported historical event source kind")


def _event_sort_key(event: HistoricalEvent):
    timestamp = _timestamp_sort_key(event.occurred_at)
    sequence = event.sequence if type(event.sequence) is int else event.source_order
    return timestamp, sequence, event.key


def _timestamp_sort_key(value: str):
    if not value:
        return 1, ""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return 1, value
        return 0, parsed.timestamp()
    except (TypeError, ValueError, OverflowError, OSError):
        return 1, value


def render_historical_event(event: HistoricalEvent, language: str
                            ) -> HistoricalEventPresentation:
    """Render with current resources, preserving capture-time text and raw evidence."""
    message = render_historical_event_message(event, language)
    return HistoricalEventPresentation(message.message, _format_detail(event),
                                       message.unrecognized)


def render_historical_event_message(event: HistoricalEvent, language: str
                                    ) -> HistoricalEventPresentation:
    """Render only the list message; detailed raw evidence is prepared on selection."""
    if event.source == "read_error":
        return HistoricalEventPresentation(
            translate("history.read_error", language, reason=event.message), "")
    if event.source == "read_warning":
        return HistoricalEventPresentation(translate("history.incomplete", language), "")

    if event.localized_message is not None:
        return HistoricalEventPresentation(_render_captured_message(
            event.localized_message, event.message, language), "")

    legacy = _recognize_legacy_audit_event(event)
    if legacy is not None:
        return HistoricalEventPresentation(
            _render_captured_message(legacy.as_record(), legacy.english, language), "")
    return HistoricalEventPresentation(translate("history.unrecognized", language), "", True)


def legacy_historical_event_message_record(event: HistoricalEvent) -> Optional[dict]:
    """Return the established bilingual display for a reliably recognized old event.

    The projection is safe to retain in a paged summary; original evidence remains
    available only through the selected event's detail lookup.
    """
    message = _recognize_legacy_audit_event(event)
    return message.as_record() if message is not None else None


def _render_captured_message(localized: dict, saved_message: str, language: str) -> str:
    """Use current catalog when applicable; otherwise show capture-time English."""
    saved_english = localized.get("en")
    fallback = saved_english if isinstance(saved_english, str) and saved_english else saved_message
    if type(localized.get("version")) is not int or localized.get("version") != 1:
        return fallback
    message_id = localized.get("message_id")
    parameters = localized.get("parameters")
    if not isinstance(message_id, str) or not message_id or not isinstance(parameters, dict):
        return fallback
    try:
        return translate(message_id, language, **parameters)
    except (KeyError, TypeError, ValueError, IndexError):
        return fallback


def _read_legacy_session_events(path: Path, read_observer=None):
    try:
        handle = path.open("r", encoding="utf-8")
    except (OSError, UnicodeError) as error:
        yield _read_error("legacy_session", path, str(error))
        return
    with handle:
        try:
            for index, line in enumerate(handle, 1):
                if read_observer is not None:
                    read_observer(len(line.encode("utf-8")))
                try:
                    raw = json.loads(line)
                    if not isinstance(raw, dict) or not isinstance(raw.get("message"), str):
                        raise ValueError("事件欄位格式不正確")
                    timestamp = raw.get("timestamp", "")
                    if not isinstance(timestamp, str):
                        raise ValueError("事件時間格式不正確")
                except (json.JSONDecodeError, ValueError) as error:
                    yield _read_error(
                        "legacy_session", path, "第 {} 行：{}".format(index, error),
                        view_key="line:{}".format(index), source_order=index,
                        raw_record={"path": str(path), "line_number": index,
                                    "raw_line": line, "reason": str(error)},
                    )
                    continue
                # Legacy Session events.log did not carry a stable kind. Do not infer an ID from prose.
                localized = raw.get("localized_message")
                yield HistoricalEvent(
                    "legacy:{}:{}".format(path.parent.name, index), "legacy_session", timestamp,
                    raw["message"], "", raw.get("round_id"),
                    raw.get("sequence") if type(raw.get("sequence")) is int else None,
                    localized if isinstance(localized, dict) else None,
                    _diagnostic(raw), raw.get("detail", {}), raw, source_order=index,
                )
        except (OSError, UnicodeError) as error:
            yield _read_error("legacy_session", path, str(error))


def _read_error(source: str, path: Path, reason: str, view_key: str = "",
                source_order: int = 0, raw_record=None) -> HistoricalEvent:
    suffix = ":{}".format(view_key) if view_key else ""
    return HistoricalEvent("error:{}:{}{}".format(source, path, suffix), "read_error", "", reason,
                           diagnostic=reason,
                           raw_record=(raw_record if raw_record is not None else
                                       {"path": str(path), "reason": reason}),
                           source_order=source_order)


def _diagnostic(record: dict) -> str:
    value = record.get("diagnostic", "")
    if value:
        return str(value)
    detail = record.get("detail", {})
    if isinstance(detail, dict):
        return str(detail.get("raw_diagnostic", ""))
    return ""


def _recognize_legacy_audit_event(event: HistoricalEvent):
    """Translate only version-1 audit kinds whose old producer contract is explicit."""
    if (event.source != "round" or not isinstance(event.station, str) or
            not event.station or not event.kind):
        return None
    detail = event.detail if isinstance(event.detail, dict) else {}
    display_position = event.raw_record.get("display_position") if isinstance(event.raw_record, dict) else None
    status = event.raw_record.get("status", "") if isinstance(event.raw_record, dict) else ""
    platform_message = _recognize_legacy_platform_event(event, detail, display_position, status)
    if platform_message is not None:
        return platform_message
    if event.kind == "result":
        if type(display_position) is not int or display_position < 1 or not isinstance(status, str) or not status:
            return None
    if event.kind == "timeout":
        if "elapsed_seconds" not in event.raw_record or "deadline_seconds" not in detail:
            return None
        if display_position is not None and (
                type(display_position) is not int or display_position < 1 or
                not isinstance(status, str) or not status):
            return None
    if event.kind == "conflict_resolved" and detail.get("choice") not in {
            "accept_candidate", "keep_original"}:
        return None
    if event.kind in {"conflict_detected", "duplicate_source", "unknown_round_candidate_rejected"}:
        if display_position is not None and (type(display_position) is not int or display_position < 1):
            return None
    if event.kind not in {
            "result", "round_started", "round_ready", "collection_stopped", "stopped",
            "finished", "timeout", "round_alarm_created", "round_alarm_acknowledged",
            "round_alarm_acknowledgement_ignored", "conflict_detected", "conflict_resolved",
            "duplicate_source", "unknown_round_candidate_rejected", "audit_write_failed",
            "session_write_failed", "save_recovered", "start_failed"}:
        return None
    return capture_round_event_message(
        event.kind, event.station, display_position, status, detail, event.message,
        display_position,
    )


def _recognize_legacy_platform_event(event: HistoricalEvent, detail: dict,
                                     display_position, status: str):
    """Use the v1 round header's platform and producer kind, never message similarity."""
    platform = event.platform.lower() if isinstance(event.platform, str) else ""
    message_id = None
    parameters = {}
    if platform == "atlas":
        if event.kind == "source_prepared":
            message_id = "platform.atlas.source_prepared"
        elif event.kind == "sn_locked" and type(display_position) is int and display_position > 0:
            message_id = "platform.atlas.sn_locked"
            parameters["slot"] = display_position
        elif (event.kind == "final" and type(display_position) is int and
              display_position > 0 and isinstance(status, str) and status):
            message_id = "platform.atlas.final"
            parameters.update(slot=display_position, status=status)
        elif (event.kind == "unresolved_source_conflict" and
              type(display_position) is int and display_position > 0):
            message_id = "platform.atlas.unresolved_conflict"
            parameters["slot"] = display_position
        elif event.kind == "warning" and event.message.startswith("Atlas source read failed: "):
            filename = _source_filename(event.raw_record.get("source"))
            if filename:
                message_id = "platform.atlas.source_error"
                parameters["source_filename"] = filename
    elif platform == "b482":
        if event.kind == "batch":
            batch_id = detail.get("batch_id") or event.raw_record.get("batch_evidence")
            if isinstance(batch_id, str) and batch_id:
                message_id = "platform.b482.batch"
                parameters["batch_id"] = batch_id
        elif event.kind == "batch_observed" and type(display_position) is int and display_position > 0:
            message_id = "platform.b482.batch_mismatch"
            parameters["slot"] = display_position
        elif event.kind == "warning" and event.message.startswith("B482 source read failed: "):
            filename = _source_filename(event.raw_record.get("source"))
            if filename:
                message_id = "platform.b482.source_error"
                parameters["source_filename"] = filename
    elif platform == "rswmt":
        if event.kind == "batch":
            message_id = "platform.rswmt.batch"
        elif event.kind == "warning" and _is_rswmt_warning(event.message):
            filename = _source_filename(event.raw_record.get("source"))
            if filename:
                message_id = "platform.rswmt.warning"
                parameters["source_filename"] = filename
    if message_id is None:
        return None
    try:
        return make_bilingual_message(message_id, parameters)
    except (KeyError, TypeError, ValueError):
        return None


def _source_filename(source) -> Optional[str]:
    if not isinstance(source, str) or not source:
        return None
    try:
        return Path(source).name or None
    except (TypeError, ValueError, OSError):
        return None


def _is_rswmt_warning(message: str) -> bool:
    return isinstance(message, str) and message.startswith((
        "RS-WMT: source log could not be read:",
        "RS-WMT: source file could not be inspected:",
        "RS-WMT: incomplete or unsupported CSV;",
        "RS-WMT: different test start time;",
        "RS-WMT: source round is incomplete or ambiguous;",
    ))


def _format_detail(event: HistoricalEvent) -> str:
    values = {"original_message": event.message}
    if event.round_id is not None:
        values["round_id"] = event.round_id
    if event.station:
        values["station"] = event.station
    if event.platform:
        values["platform"] = event.platform
    if event.sequence is not None:
        values["sequence"] = event.sequence
    if event.occurred_at:
        values["occurred_at"] = event.occurred_at
    if event.diagnostic:
        values["diagnostic"] = event.diagnostic
    values["record"] = event.raw_record
    return json.dumps(values, ensure_ascii=False, indent=2, default=str)
