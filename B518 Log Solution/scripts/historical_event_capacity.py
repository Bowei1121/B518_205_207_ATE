"""Build reproducible mixed-source fixtures for historical-event capacity checks."""

import argparse
import hashlib
import json
import platform
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path


_AUDIT_SCHEMA_VERSION = 1
_APP_EVENT_RECORD_VERSION = 1
_EVENTS_PER_ROUND = 1000
_DATE_SPAN_DAYS = 120
_QUERY_WINDOW_DAYS = 90


def _json_line(payload):
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True,
                        separators=(",", ":")) + "\n").encode("utf-8")


def _event_time(as_of, ordinal):
    days_ago = ordinal % _DATE_SPAN_DAYS
    event_date = as_of - timedelta(days=days_ago)
    if ordinal == 0:
        local_time = time(0, 0, 0)
    elif ordinal == 1:
        local_time = time(23, 59, 59, 999999)
    else:
        seconds = ordinal % 43200
        local_time = time(8 + seconds // 3600, seconds % 3600 // 60,
                          seconds % 60)
    local_zone = timezone(timedelta(hours=8))
    return datetime.combine(event_date, local_time, local_zone).isoformat()


def _write_records(path, records):
    digest = hashlib.sha256()
    byte_count = 0
    with path.open("wb") as handle:
        for record in records:
            content = _json_line(record)
            handle.write(content)
            digest.update(content)
            byte_count += len(content)
    return byte_count, digest.hexdigest()


def _write_audit_source(sessions, source_number, first_ordinal, event_count, as_of):
    round_id = "h8-capacity-round-{:06d}".format(source_number)
    directory = sessions / round_id
    directory.mkdir(parents=True)
    header = {
        "record_type": "round",
        "schema_version": _AUDIT_SCHEMA_VERSION,
        "round_id": round_id,
        "station": "FCT",
        "accepted_start_at": "2026-10-14T00:00:00+08:00",
        "accepted_start_monotonic": 0.0,
        "config": {"platform": "capacity-fixture"},
        "time_contract": {
            "accepted_start_at": "app wall-clock observation time",
            "source_time": "platform-provided source time; null when unavailable",
            "observed_at": "app wall-clock observation time",
            "operation_at": "operator action wall-clock time",
            "elapsed_seconds": "monotonic elapsed time from accepted start",
        },
        "legacy_session_path": None,
    }

    def records():
        yield header
        for sequence in range(1, event_count + 1):
            ordinal = first_ordinal + sequence - 1
            detail = {}
            if ordinal % 1000 == 0:
                detail["raw_diagnostic"] = (
                    "Synthetic preserved diagnostic for capacity event {}. ".format(ordinal) * 32)
            yield {
                "record_type": "event",
                "schema_version": _AUDIT_SCHEMA_VERSION,
                "round_id": round_id,
                "sequence": sequence,
                "kind": "round_ready",
                "message": "Synthetic round event {}".format(ordinal),
                "observed_at": _event_time_from_ordinal(as_of, ordinal),
                "elapsed_seconds": float(sequence),
                "display_position": None,
                "source_position": None,
                "sn": None,
                "status": None,
                "source": None,
                "source_id": None,
                "source_time": None,
                "operation_at": None,
                "date_evidence": None,
                "batch_evidence": None,
                "detail": detail,
            }

    source_path = directory / "audit.jsonl"
    byte_count, digest = _write_records(source_path, records())
    if source_number == 0 and event_count:
        duplicate = {
            "timestamp": _event_time_from_ordinal(as_of, first_ordinal),
            "message": "Lower-priority legacy duplicate for audit event",
            "round_id": round_id,
            "sequence": 1,
        }
        _write_records(directory / "events.log", (duplicate,))
    return source_path, event_count, byte_count, digest


def _event_time_from_ordinal(as_of, ordinal):
    # The fixture uses a fixed local offset so its date boundaries are stable.
    return _event_time(as_of, ordinal)


def _write_legacy_source(sessions, source_number, first_ordinal, event_count, as_of):
    round_id = "h8-capacity-legacy-{:06d}".format(source_number)
    directory = sessions / round_id
    directory.mkdir(parents=True)
    source_path = directory / "events.log"
    records = ({
        "timestamp": _event_time_from_ordinal(as_of, first_ordinal + offset),
        "message": "Synthetic legacy event {}".format(first_ordinal + offset),
        "round_id": round_id,
        "sequence": offset + 1,
    } for offset in range(event_count))
    byte_count, digest = _write_records(source_path, records)
    return source_path, event_count, byte_count, digest


def _write_app_source(path, first_ordinal, event_count, as_of):
    localized_template = {
        "version": 1,
        "message_id": "h8.capacity.synthetic",
        "parameters": {},
        "en": "Synthetic App event",
        "zh-TW": "合成 App 事件",
    }
    digest = hashlib.sha256()
    byte_count = 0
    with path.open("wb") as handle:
        prefix = b'{"record_type":"app_event_store","schema_version":1,"events":['
        handle.write(prefix)
        digest.update(prefix)
        byte_count += len(prefix)
        for sequence in range(1, event_count + 1):
            ordinal = first_ordinal + sequence - 1
            if sequence > 1:
                handle.write(b",")
                digest.update(b",")
                byte_count += 1
            localized = dict(localized_template)
            localized["parameters"] = {"ordinal": str(ordinal)}
            event = {
                "record_type": "app_event",
                "schema_version": _APP_EVENT_RECORD_VERSION,
                "event_id": "h8-capacity-app-{:09d}".format(sequence),
                "sequence": sequence,
                "occurred_at": _event_time_from_ordinal(as_of, ordinal),
                "kind": "h8.capacity.synthetic",
                "message": localized["en"],
                "localized_message": localized,
                "diagnostic": ("Synthetic App diagnostic {}".format(ordinal)
                               if ordinal % 5000 == 0 else ""),
            }
            content = json.dumps(event, ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":")).encode("utf-8")
            handle.write(content)
            digest.update(content)
            byte_count += len(content)
        suffix = b"]}\n"
        handle.write(suffix)
        digest.update(suffix)
        byte_count += len(suffix)
    return byte_count, digest.hexdigest()


def generate_fixture(root, event_count, as_of):
    """Create a strict-reader-compatible, deterministic mixed-source fixture."""
    root = Path(root)
    if type(event_count) is not int or event_count < 3:
        raise ValueError("event_count must be an integer of at least three")
    if not isinstance(as_of, date) or isinstance(as_of, datetime):
        raise TypeError("as_of must be a date")
    root.mkdir(parents=True, exist_ok=True)
    if any(root.iterdir()):
        raise FileExistsError("capacity fixture root must be empty: {}".format(root))

    app_count = max(1, event_count // 200)
    legacy_count = max(1, event_count // 20)
    audit_count = event_count - app_count - legacy_count
    sessions = root / "sessions"
    sessions.mkdir()
    app_path = root / "app-events.json"
    source_hashes = {}
    source_bytes_by_type = {"round_audit": 0, "legacy_events_log": 0,
                            "app_journal": 0}
    source_counts = {"round_audit": audit_count,
                     "legacy_events_log": legacy_count,
                     "app_journal": app_count}

    global_ordinal = 0
    audit_file_count = 0
    remaining = audit_count
    while remaining:
        current_count = min(_EVENTS_PER_ROUND, remaining)
        source_number = audit_file_count
        path, _, size, digest = _write_audit_source(
            sessions, source_number, global_ordinal, current_count, as_of)
        relative_path = path.relative_to(root).as_posix()
        source_hashes[relative_path] = digest
        source_bytes_by_type["round_audit"] += size
        if source_number == 0 and current_count:
            duplicate_path = path.parent / "events.log"
            duplicate_bytes = duplicate_path.read_bytes()
            source_hashes[duplicate_path.relative_to(root).as_posix()] = (
                hashlib.sha256(duplicate_bytes).hexdigest())
            source_bytes_by_type["ignored_legacy_precedence"] = len(duplicate_bytes)
        audit_file_count += 1
        global_ordinal += current_count
        remaining -= current_count

    legacy_file_count = 0
    remaining = legacy_count
    while remaining:
        current_count = min(_EVENTS_PER_ROUND, remaining)
        path, _, size, digest = _write_legacy_source(
            sessions, legacy_file_count, global_ordinal, current_count, as_of)
        relative_path = path.relative_to(root).as_posix()
        source_hashes[relative_path] = digest
        source_bytes_by_type["legacy_events_log"] += size
        legacy_file_count += 1
        global_ordinal += current_count
        remaining -= current_count

    app_bytes, app_digest = _write_app_source(app_path, global_ordinal, app_count, as_of)
    source_hashes[app_path.relative_to(root).as_posix()] = app_digest
    source_bytes_by_type["app_journal"] = app_bytes

    start_date = as_of - timedelta(days=_QUERY_WINDOW_DAYS - 1)
    in_range_count = sum(1 for ordinal in range(event_count)
                         if ordinal % _DATE_SPAN_DAYS < _QUERY_WINDOW_DAYS)
    # The audit source's header has a fixed provenance timestamp for readability;
    # event times and the acceptance range use the explicit fixture date.
    manifest = {
        "format_version": 1,
        "generator": "scripts/historical_event_capacity.py",
        "seed_rule": "source type blocks; 1000 records per round source; day = ordinal modulo 120",
        "event_count": event_count,
        "event_count_unit": "synthetic saved events, not product units",
        "source_event_counts": source_counts,
        "source_counts_by_type": {
            "round_audit_files": audit_file_count,
            "legacy_events_log_files": legacy_file_count,
            "app_journal_files": 1,
        },
        "source_count": audit_file_count + legacy_file_count + 1,
        "physical_source_file_count": len(source_hashes),
        "ignored_precedence_duplicate_count": 1,
        "range_start": start_date.isoformat(),
        "range_end": as_of.isoformat(),
        "range_start_inclusive_local_midnight": True,
        "range_end_inclusive_full_local_day": True,
        "source_date_span_days": _DATE_SPAN_DAYS,
        "expected_in_range_event_count": in_range_count,
        "expected_out_of_range_event_count": event_count - in_range_count,
        "fixture_local_offset": "+08:00",
        "source_bytes_by_type": source_bytes_by_type,
        "source_bytes_total": sum(source_bytes_by_type.values()),
        "source_sha256": source_hashes,
        "sessions_path": str(sessions),
        "app_event_path": str(app_path),
        "runtime": {"python": sys.version, "executable": sys.executable,
                    "platform": platform.platform(), "machine": platform.machine()},
    }
    manifest_path = root / "fixture-manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2,
                                        sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def _prepare_command(arguments):
    manifest = generate_fixture(arguments.root, arguments.events, arguments.as_of)
    print(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command")
    prepare = subparsers.add_parser("prepare", help="create an isolated capacity fixture")
    prepare.add_argument("--root", type=Path, required=True)
    prepare.add_argument("--events", type=int, required=True)
    prepare.add_argument("--as-of", type=date.fromisoformat, required=True)
    prepare.set_defaults(run=_prepare_command)
    arguments = parser.parse_args(argv)
    if not hasattr(arguments, "run"):
        parser.error("choose a command")
    arguments.run(arguments)


if __name__ == "__main__":
    main()
