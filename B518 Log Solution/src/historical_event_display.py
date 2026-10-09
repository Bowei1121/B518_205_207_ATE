"""Read and render historical event records without changing their source files."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from app_event_store import read_app_event_store
from audit_records import read_round_audit
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


@dataclass(frozen=True)
class HistoricalEventPresentation:
    message: str
    detail: str
    unrecognized: bool = False


def read_historical_events(session_root: Path, app_event_path: Optional[Path] = None
                           ) -> Tuple[HistoricalEvent, ...]:
    """Reconstruct disk history using the existing strict readers; never repair or write."""
    root = Path(session_root)
    records = []
    if root.exists():
        try:
            directories = sorted(path for path in root.iterdir() if path.is_dir())
        except OSError as error:
            directories = []
            records.append(_read_error("round", root, str(error)))
        for directory in directories:
            audit_path = directory / "audit.jsonl"
            legacy_path = directory / "events.log"
            if audit_path.is_file():
                try:
                    audit = read_round_audit(audit_path)
                except Exception as error:
                    records.append(_read_error("round", audit_path, str(error)))
                    continue
                header = audit["round"]
                round_id = header["round_id"]
                station = header.get("station", "")
                platform = header.get("config", {}).get("platform", "")
                for event in audit["events"]:
                    records.append(HistoricalEvent(
                        "round:{}:{}".format(round_id, event["sequence"]), "round",
                        event["observed_at"], event["message"], event["kind"], round_id,
                        event["sequence"], event.get("localized_message"),
                        _diagnostic(event), event.get("detail", {}), event, station, platform,
                    ))
                if not audit.get("audit_complete", False):
                    records.append(HistoricalEvent(
                        "warning:round:{}".format(round_id), "read_warning", "",
                        "Audit records report an incomplete save", round_id=round_id,
                        station=station, platform=platform,
                        raw_record={"audit_path": str(audit_path),
                                    "reason": "audit_complete is false"},
                    ))
            elif legacy_path.is_file():
                records.extend(_read_legacy_session_events(legacy_path))

    if app_event_path is not None and Path(app_event_path).exists():
        path = Path(app_event_path)
        try:
            store = read_app_event_store(path)
        except Exception as error:
            records.append(_read_error("app", path, str(error)))
        else:
            for event in store["events"]:
                records.append(HistoricalEvent(
                    "app:{}".format(event["event_id"]), "app", event["occurred_at"],
                    event["message"], event["kind"], None, event["sequence"],
                    event.get("localized_message"), event.get("diagnostic", ""),
                    event.get("localized_message", {}).get("parameters", {}), event,
                ))

    return tuple(sorted(records, key=lambda item: (item.occurred_at, item.key)))


def render_historical_event(event: HistoricalEvent, language: str
                            ) -> HistoricalEventPresentation:
    """Render with current resources, preserving capture-time text and raw evidence."""
    detail = _format_detail(event)
    if event.source == "read_error":
        return HistoricalEventPresentation(
            translate("history.read_error", language, reason=event.message), detail)
    if event.source == "read_warning":
        return HistoricalEventPresentation(translate("history.incomplete", language), detail)

    if event.localized_message is not None:
        return HistoricalEventPresentation(_render_captured_message(
            event.localized_message, event.message, language), detail)

    legacy = _recognize_legacy_audit_event(event)
    if legacy is not None:
        return HistoricalEventPresentation(
            _render_captured_message(legacy.as_record(), legacy.english, language), detail)
    return HistoricalEventPresentation(translate("history.unrecognized", language), detail, True)


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


def _read_legacy_session_events(path: Path):
    records = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        return [_read_error("legacy_session", path, str(error))]
    for index, line in enumerate(lines, 1):
        try:
            raw = json.loads(line)
            if not isinstance(raw, dict) or not isinstance(raw.get("message"), str):
                raise ValueError("事件欄位格式不正確")
            timestamp = raw.get("timestamp", "")
            if not isinstance(timestamp, str):
                raise ValueError("事件時間格式不正確")
        except (json.JSONDecodeError, ValueError) as error:
            records.append(_read_error("legacy_session", path, "第 {} 行：{}".format(index, error)))
            continue
        # Legacy Session events.log did not carry a stable kind. Do not infer an ID from prose.
        localized = raw.get("localized_message")
        records.append(HistoricalEvent(
            "legacy:{}:{}".format(path.parent.name, index), "legacy_session", timestamp,
            raw["message"], "", raw.get("round_id"), raw.get("sequence"),
            localized if isinstance(localized, dict) else None,
            _diagnostic(raw), raw.get("detail", {}), raw,
        ))
    return records


def _read_error(source: str, path: Path, reason: str) -> HistoricalEvent:
    return HistoricalEvent("error:{}:{}".format(source, path), "read_error", "", reason,
                           diagnostic=reason, raw_record={"path": str(path), "reason": reason})


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
    if event.source != "round" or not event.station or not event.kind:
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
        if display_position is not None and (type(display_position) is not int or not status):
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
        elif event.kind == "final" and type(display_position) is int and display_position > 0 and status:
            message_id = "platform.atlas.final"
            parameters.update(slot=display_position, status=status)
        elif (event.kind == "unresolved_source_conflict" and
              type(display_position) is int and display_position > 0):
            message_id = "platform.atlas.unresolved_conflict"
            parameters["slot"] = display_position
        elif event.kind == "warning" and event.message.startswith("Atlas source read failed: "):
            filename = Path(event.raw_record.get("source") or "").name
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
            filename = Path(event.raw_record.get("source") or "").name
            if filename:
                message_id = "platform.b482.source_error"
                parameters["source_filename"] = filename
    elif platform == "rswmt":
        if event.kind == "batch":
            message_id = "platform.rswmt.batch"
        elif event.kind == "warning" and event.raw_record.get("source"):
            message_id = "platform.rswmt.warning"
            parameters["source_filename"] = Path(event.raw_record["source"]).name
    if message_id is None:
        return None
    try:
        return make_bilingual_message(message_id, parameters)
    except (KeyError, TypeError, ValueError):
        return None


def _format_detail(event: HistoricalEvent) -> str:
    values = {"original_message": event.message}
    if event.round_id is not None:
        values["round_id"] = event.round_id
    if event.sequence is not None:
        values["sequence"] = event.sequence
    if event.occurred_at:
        values["occurred_at"] = event.occurred_at
    if event.diagnostic:
        values["diagnostic"] = event.diagnostic
    values["record"] = event.raw_record
    return json.dumps(values, ensure_ascii=False, indent=2, default=str)
