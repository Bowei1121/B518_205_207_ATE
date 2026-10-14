"""Build reproducible mixed-source fixtures for historical-event capacity checks."""

import argparse
import copy
import glob
import hashlib
import json
import platform
import resource
import subprocess
import sys
import tempfile
import threading
import time as monotonic_time
import tracemalloc
import os
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
        "accepted_start_at": _event_time(as_of, 0),
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


def _key_digest(result, pages=None):
    digest = hashlib.sha256()
    if pages is None:
        pages = range(1, result.page_count + 1)
    count = 0
    for page_number in pages:
        page = result.get_page(page_number)
        if len(page.events) > 100:
            raise AssertionError("query returned a page larger than 100 events")
        for event in page.events:
            digest.update(event.key.encode("utf-8"))
            digest.update(b"\n")
            count += 1
    return count, digest.hexdigest()


def _index_size(index_path):
    total = 0
    for candidate in (index_path, Path(str(index_path) + "-wal"),
                      Path(str(index_path) + "-shm")):
        try:
            total += candidate.stat().st_size
        except FileNotFoundError:
            pass
    return total


def _sample_command(arguments):
    # Import after the CLI starts so this script remains usable via PYTHONPATH=src:scripts.
    from historical_event_query import (HistoricalEventDateRange,
                                        HistoricalEventQueryService)

    root = arguments.root.resolve()
    manifest = json.loads((root / "fixture-manifest.json").read_text(encoding="utf-8"))
    date_range = HistoricalEventDateRange(
        date.fromisoformat(manifest["range_start"]),
        date.fromisoformat(manifest["range_end"]))
    index_path = arguments.index.resolve()
    snapshot_glob = Path(tempfile.gettempdir()).glob("b518-history-query-*.sqlite3")
    before_snapshots = {path: path.stat().st_size for path in snapshot_glob}
    tracemalloc.start()
    service = HistoricalEventQueryService(
        Path(manifest["sessions_path"]), Path(manifest["app_event_path"]),
        index_path=None if arguments.no_index else index_path)
    started = monotonic_time.perf_counter()
    generation = service.submit(date_range)
    deadline = monotonic_time.monotonic() + arguments.timeout
    completion = None
    while monotonic_time.monotonic() < deadline:
        completion = service.take_result(generation)
        if completion is not None:
            break
        monotonic_time.sleep(0.01)
    completed_at = monotonic_time.perf_counter()
    if completion is None:
        service.cancel(generation)
        service.shutdown()
        tracemalloc.stop()
        raise TimeoutError("public historical query did not complete")
    if not completion.succeeded:
        service.shutdown()
        tracemalloc.stop()
        raise completion.error
    result = completion.result
    key_started = monotonic_time.perf_counter()
    if arguments.digest == "full":
        verified_count, identity_sha256 = _key_digest(result)
    elif arguments.digest == "anchors":
        selected_pages = sorted(set((1, max(1, (result.page_count + 1) // 2),
                                     max(1, result.page_count))))
        verified_count, identity_sha256 = _key_digest(result, selected_pages)
    else:
        verified_count, identity_sha256 = 0, ""
    digest_seconds = monotonic_time.perf_counter() - key_started
    detail_seconds = 0.0
    detail_size = 0
    page_latencies = []
    if arguments.scenario == "page" and result.page_count:
        for page_number in sorted(set((1, max(1, (result.page_count + 1) // 2),
                                       result.page_count))):
            page_started = monotonic_time.perf_counter()
            result.get_page(page_number)
            page_latencies.append({"page_number": page_number,
                                   "seconds": monotonic_time.perf_counter() -
                                   page_started})
    if result.total_count:
        first = result.get_page(1)
        detail_started = monotonic_time.perf_counter()
        detail = result.get_detail(first.events[0].key)
        detail_seconds = monotonic_time.perf_counter() - detail_started
        if detail is None:
            raise AssertionError("selected first-page event has no detail")
        detail_size = len(detail.message.encode("utf-8"))
    snapshots_during_query = {
        path: path.stat().st_size
        for path in Path(tempfile.gettempdir()).glob("b518-history-query-*.sqlite3")
        if path not in before_snapshots
    }
    metrics = result.index_metrics
    sample = {
        "scenario": arguments.scenario,
        "run": arguments.run_number,
        "command": arguments.command_text,
        "started_at_local": datetime.now().astimezone().isoformat(),
        "query_seconds": completed_at - started,
        "identity_digest_seconds": digest_seconds,
        "first_middle_last_page_latencies": page_latencies,
        "selected_detail_seconds": detail_seconds,
        "selected_detail_json_bytes": detail_size,
        "total_count": result.total_count,
        "page_size": result.page_size,
        "page_count": result.page_count,
        "verified_event_count": verified_count,
        "identity_sha256": identity_sha256,
        "index_degraded": result.index_degraded,
        "index_issue": result.index_issue,
        "parsed_source_count": metrics.parsed_source_count,
        "reused_source_count": metrics.reused_source_count,
        "source_bytes_read_by_reader": metrics.source_bytes_read,
        "source_version_check_count": metrics.source_version_check_count,
        "index_bytes_after_query": _index_size(index_path),
        "query_snapshot_bytes": sum(snapshots_during_query.values()),
        "python_peak_tracemalloc_bytes": tracemalloc.get_traced_memory()[1],
        "process_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "worker_threads_at_result": sorted(
            thread.name for thread in threading.enumerate()
            if thread.name == "HistoricalEventDateQuery"),
        "detail_materialized_count": 1 if result.total_count else 0,
        "os_cache_condition": "uncontrolled; no claim of cold disk",
    }
    result.close()
    service.shutdown()
    # The worker publishes completion before it exits; wait on public worker liveness only
    # through process-wide thread inventory, with a bounded drain window.
    drain_deadline = monotonic_time.monotonic() + 5
    while (any(thread.name == "HistoricalEventDateQuery"
               for thread in threading.enumerate()) and
           monotonic_time.monotonic() < drain_deadline):
        monotonic_time.sleep(0.01)
    sample["worker_threads_after_cleanup"] = sorted(
        thread.name for thread in threading.enumerate()
        if thread.name == "HistoricalEventDateQuery")
    after_snapshots = set(Path(tempfile.gettempdir()).glob("b518-history-query-*.sqlite3"))
    sample["snapshot_removed"] = not (
        after_snapshots - set(before_snapshots))
    sample["elapsed_seconds_including_verification"] = (
        monotonic_time.perf_counter() - started)
    tracemalloc.stop()
    if sample["worker_threads_after_cleanup"] or not sample["snapshot_removed"]:
        raise AssertionError("query worker or temporary snapshot was not reclaimed")
    if arguments.scenario == "degraded" and not result.index_degraded:
        raise AssertionError("corrupt index did not report safe degradation")
    if arguments.scenario in ("reuse", "page") and metrics.parsed_source_count:
        raise AssertionError("normal indexed query unexpectedly parsed source files")
    if arguments.scenario == "single-source-change" and metrics.parsed_source_count != 1:
        raise AssertionError("single-source update reparsed an unexpected source count")
    print(json.dumps(sample, ensure_ascii=False, sort_keys=True))


def _append_audit_event(source_path, as_of):
    original = source_path.read_bytes()
    lines = original.splitlines()
    last_event = json.loads(lines[-1].decode("utf-8"))
    event = copy.deepcopy(last_event)
    event["sequence"] += 1
    event["message"] = "Synthetic single-source capacity append"
    event["observed_at"] = datetime.combine(
        as_of, time(12, 34, 56), timezone(timedelta(hours=8))).isoformat()
    event["elapsed_seconds"] += 1.0
    event["detail"] = {"raw_diagnostic": "Single-source append diagnostic"}
    with source_path.open("ab") as handle:
        handle.write(_json_line(event))
    return original


def _run_sample_process(script, root, index_path, scenario, run_number,
                        digest, timeout, no_index=False):
    command = [sys.executable, str(script), "sample", "--root", str(root),
               "--index", str(index_path), "--scenario", scenario,
               "--run-number", str(run_number), "--digest", digest,
               "--timeout", str(timeout)]
    if no_index:
        command.append("--no-index")
    environment = dict(os.environ)
    existing_path = environment.get("PYTHONPATH", "")
    script_root = str(script.parent.parent / "src") + os.pathsep + str(script.parent)
    environment["PYTHONPATH"] = (script_root + os.pathsep + existing_path
                                 if existing_path else script_root)
    started_at = datetime.now().astimezone().isoformat()
    completed = subprocess.run(command, cwd=str(script.parent.parent), env=environment,
                               text=True, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, timeout=timeout + 60)
    ended_at = datetime.now().astimezone().isoformat()
    if completed.returncode:
        raise RuntimeError("capacity sample failed: {}\n{}".format(
            " ".join(command), completed.stderr))
    sample = json.loads(completed.stdout)
    sample.update({"process_started_at_local": started_at,
                   "process_ended_at_local": ended_at,
                   "process_exit_code": completed.returncode,
                   "full_command": command,
                   "stderr": completed.stderr})
    return sample


def _benchmark_command(arguments):
    root = arguments.root.resolve()
    output = arguments.output.resolve()
    manifest = json.loads((root / "fixture-manifest.json").read_text(encoding="utf-8"))
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("benchmark output must be empty: {}".format(output))
    output.mkdir(parents=True, exist_ok=True)
    script = Path(__file__).resolve()
    measured = []

    def record(label, index_path, number, digest="full", no_index=False):
        sample = _run_sample_process(
            script, root, index_path, label, number, digest,
            arguments.timeout, no_index=no_index)
        measured.append(sample)
        with (output / "raw-measurements.jsonl").open(
                "a", encoding="utf-8") as measurements:
            measurements.write(json.dumps(sample, ensure_ascii=False,
                                          sort_keys=True) + "\n")
        return sample

    baseline = record("raw-file-baseline", output / "no-index.sqlite3", 1,
                      no_index=True)
    expected_count = manifest["expected_in_range_event_count"]
    if baseline["total_count"] != expected_count:
        raise AssertionError("raw-file baseline disagrees with fixture manifest")

    initial_samples = []
    for run_number in range(1, 4):
        index_path = output / "initial-{}.sqlite3".format(run_number)
        sample = record("initial", index_path, run_number)
        if sample["index_degraded"] or sample["total_count"] != expected_count:
            raise AssertionError("initial index build returned an invalid result")
        initial_samples.append(sample)
    baseline_digest = baseline["identity_sha256"]
    if any(sample["identity_sha256"] != baseline_digest
           for sample in initial_samples):
        raise AssertionError("initial index result differs from safe raw-file baseline")

    reusable_index = output / "initial-3.sqlite3"
    for run_number in range(1, 4):
        sample = record("reuse", reusable_index, run_number)
        if (sample["identity_sha256"] != baseline_digest or
                sample["parsed_source_count"] != 0):
            raise AssertionError("normal requery failed identity or incremental-cost check")

    source_candidates = sorted((root / "sessions").glob("*/audit.jsonl"))
    if not source_candidates:
        raise AssertionError("fixture has no audit source for mutation measurement")
    changed_source = source_candidates[0]
    original = changed_source.read_bytes()
    change_results = []
    try:
        for run_number in range(1, 4):
            changed_source.write_bytes(original)
            _append_audit_event(changed_source, date.fromisoformat(manifest["range_end"]))
            changed_baseline = record(
                "single-source-raw-baseline", output / "changed-no-index.sqlite3",
                run_number, no_index=True)
            sample = record("single-source-change", reusable_index, run_number)
            if (sample["total_count"] != changed_baseline["total_count"] or
                    sample["identity_sha256"] != changed_baseline["identity_sha256"] or
                    sample["parsed_source_count"] != 1):
                raise AssertionError("single-source update failed identity/cost check")
            change_results.append(sample)
            changed_source.write_bytes(original)
            # Refresh only the changed source's recorded signature for the same baseline.
            restored = record("restore-index-state", reusable_index, run_number,
                              digest="none")
            if restored["parsed_source_count"] != 1:
                raise AssertionError("fixture reset did not restore the index signature")
    finally:
        changed_source.write_bytes(original)

    degraded_samples = []
    for run_number in range(1, 4):
        reusable_index.write_bytes("H8 controlled corrupt index run {}".format(
            run_number).encode("ascii"))
        sample = record("degraded", reusable_index, run_number)
        if (not sample["index_degraded"] or
                sample["identity_sha256"] != baseline_digest):
            raise AssertionError("degraded raw-file fallback differs from baseline")
        degraded_samples.append(sample)

    page_samples = []
    for run_number in range(1, 4):
        sample = record("page", reusable_index, run_number, digest="anchors")
        if sample["parsed_source_count"] != 0:
            raise AssertionError("page navigation reparsed the source files")
        page_samples.append(sample)

    source_hashes_after = {}
    for relative_path in manifest["source_sha256"]:
        path = root / relative_path
        source_hashes_after[relative_path] = hashlib.sha256(path.read_bytes()).hexdigest()
    if source_hashes_after != manifest["source_sha256"]:
        raise AssertionError("capacity query changed or failed to restore source bytes")
    report = {
        "format_version": 1,
        "fixture_manifest": str(root / "fixture-manifest.json"),
        "fixture_event_count": manifest["event_count"],
        "fixture_source_count": manifest["source_count"],
        "fixture_source_bytes": manifest["source_bytes_total"],
        "raw_file_baseline_sha256": baseline_digest,
        "raw_file_baseline_count": baseline["total_count"],
        "scenario_runs": {
            "initial_index_build": initial_samples,
            "normal_requery_fresh_process": [sample for sample in measured
                                               if sample["scenario"] == "reuse"],
            "single_source_change": change_results,
            "index_degradation": degraded_samples,
            "normal_page_navigation": page_samples,
        },
        "unmeasured_setup_and_restore_samples": [sample for sample in measured
                                                   if sample["scenario"] in (
                                                       "raw-file-baseline",
                                                       "single-source-raw-baseline",
                                                       "restore-index-state")],
        "source_hashes_after": source_hashes_after,
        "sources_unchanged_after_measurements": True,
        "os_disk_cache_controlled": False,
        "measurement_limits": [
            "reader source bytes are logical bytes read by the parser; physical device I/O is not isolated",
            "Darwin ru_maxrss is process peak RSS; tracemalloc excludes some native allocations",
            "OS file cache was not flushed or controlled; initial means absent index, not cold disk",
            "Tk event-loop interval is measured separately by the interactive desktop acceptance",
        ],
        "runtime": {"python": sys.version, "executable": sys.executable,
                    "platform": platform.platform(), "machine": platform.machine()},
    }
    (output / "benchmark-report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    print(json.dumps({"output": str(output / "benchmark-report.json"),
                      "runs_by_scenario": {
                          key: len(value) for key, value in report["scenario_runs"].items()},
                      "raw_file_baseline_sha256": baseline_digest},
                     ensure_ascii=False, sort_keys=True))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command")
    prepare = subparsers.add_parser("prepare", help="create an isolated capacity fixture")
    prepare.add_argument("--root", type=Path, required=True)
    prepare.add_argument("--events", type=int, required=True)
    prepare.add_argument("--as-of", type=date.fromisoformat, required=True)
    prepare.set_defaults(run=_prepare_command)
    sample = subparsers.add_parser("sample", help="run one isolated query measurement")
    sample.add_argument("--root", type=Path, required=True)
    sample.add_argument("--index", type=Path, required=True)
    sample.add_argument("--scenario", choices=("initial", "reuse", "single-source-change",
                                                  "degraded", "page", "raw-file-baseline",
                                                  "single-source-raw-baseline",
                                                  "restore-index-state"), required=True)
    sample.add_argument("--run-number", type=int, required=True)
    sample.add_argument("--digest", choices=("full", "anchors", "none"),
                        default="full")
    sample.add_argument("--timeout", type=float, default=3600)
    sample.add_argument("--command-text", default="")
    sample.add_argument("--no-index", action="store_true")
    sample.set_defaults(run=_sample_command)
    benchmark = subparsers.add_parser(
        "benchmark", help="run the five three-sample capacity scenarios")
    benchmark.add_argument("--root", type=Path, required=True,
                           help="existing prepared fixture root")
    benchmark.add_argument("--output", type=Path, required=True,
                           help="empty directory for raw measurements and report")
    benchmark.add_argument("--timeout", type=float, default=7200)
    benchmark.set_defaults(run=_benchmark_command)
    arguments = parser.parse_args(argv)
    if not hasattr(arguments, "run"):
        parser.error("choose a command")
    arguments.run(arguments)


if __name__ == "__main__":
    main()
