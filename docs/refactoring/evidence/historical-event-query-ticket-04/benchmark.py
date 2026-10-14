"""Reproducible disk-backed history-index cost sample; writes only to a temp root."""

import hashlib
import json
import tempfile
import time
import tracemalloc
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from audit_records import AuditEvent, RoundAuditStore
from historical_event_query import (HistoricalEventDateRange,
                                    HistoricalEventQueryService,
                                    query_historical_events)


def _source_hashes(paths):
    return {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


def _measure(callback):
    tracemalloc.start()
    started = time.perf_counter()
    value = callback()
    elapsed = time.perf_counter() - started
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return value, elapsed, peak


def _new_fixture(root):
    sessions = root / "sessions"
    audits = []
    detail_text = "raw engineering diagnostic evidence " * 600
    for source_number in range(3):
        audit = RoundAuditStore(
            sessions, "benchmark-round-{}".format(source_number + 1), "FCT",
            "2026-10-13T00:00:00+08:00", 0.0)
        for sequence in range(1, 151):
            detail = {"raw_diagnostic": detail_text} if sequence == 75 else {}
            occurred_at = (datetime(2026, 10, 13, 8, tzinfo=timezone.utc) +
                           timedelta(seconds=sequence)).isoformat()
            audit.append_event(AuditEvent(
                sequence, "round_ready", "benchmark event", None, detail=detail),
                occurred_at, float(sequence))
        if not audit.flush():
            raise RuntimeError("failed to save benchmark fixture")
        audits.append(audit)
    return sessions, audits


def _query(sessions, index_path):
    return query_historical_events(
        sessions, None,
        HistoricalEventDateRange(date(2026, 10, 13), date(2026, 10, 13)),
        index_path=index_path)


def main():
    measurements = []
    with tempfile.TemporaryDirectory(prefix="b518-h4-benchmark-") as temporary:
        root = Path(temporary)
        sessions, audits = _new_fixture(root)
        sources = [audit.audit_path for audit in audits]

        cold_index = root / "index-cold-1.sqlite3"
        for sample in range(1, 4):
            index_path = root / "index-cold-{}.sqlite3".format(sample)
            before = _source_hashes(sources)
            result, elapsed, peak = _measure(lambda: _query(sessions, index_path))
            metrics = result.index_metrics
            snapshot_size = result._store_path.stat().st_size
            index_size = index_path.stat().st_size
            result.close()
            measurements.append({
                "scenario": "first_build", "sample": sample, "elapsed_s": elapsed,
                "source_bytes_read": metrics.source_bytes_read,
                "parsed_sources": metrics.parsed_source_count,
                "reused_sources": metrics.reused_source_count,
                "source_version_checks": metrics.source_version_check_count,
                "peak_tracemalloc_bytes": peak, "index_bytes": index_size,
                "result_snapshot_bytes": snapshot_size,
                "sources_unchanged": before == _source_hashes(sources),
            })
            if sample == 1:
                cold_index = index_path

        for sample in range(1, 4):
            service = HistoricalEventQueryService(sessions, None, index_path=cold_index)

            def query_with_new_service():
                generation = service.submit(HistoricalEventDateRange(
                    date(2026, 10, 13), date(2026, 10, 13)))
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    completion = service.take_result(generation)
                    if completion is not None:
                        if not completion.succeeded:
                            raise completion.error
                        return completion.result
                    time.sleep(0.002)
                raise TimeoutError("fresh query service did not complete")

            before = _source_hashes(sources)
            result, elapsed, peak = _measure(query_with_new_service)
            metrics = result.index_metrics
            snapshot_size = result._store_path.stat().st_size
            index_size = cold_index.stat().st_size
            result.close()
            service.shutdown()
            measurements.append({
                "scenario": "fresh_service_reuse", "sample": sample,
                "elapsed_s": elapsed, "source_bytes_read": metrics.source_bytes_read,
                "parsed_sources": metrics.parsed_source_count,
                "reused_sources": metrics.reused_source_count,
                "source_version_checks": metrics.source_version_check_count,
                "peak_tracemalloc_bytes": peak, "index_bytes": index_size,
                "result_snapshot_bytes": snapshot_size,
                "sources_unchanged": before == _source_hashes(sources),
            })

        for sample in range(1, 4):
            before = _source_hashes(sources)
            result, elapsed, peak = _measure(lambda: _query(sessions, cold_index))
            metrics = result.index_metrics
            snapshot_size = result._store_path.stat().st_size
            result.close()
            measurements.append({
                "scenario": "unchanged_requery", "sample": sample,
                "elapsed_s": elapsed, "source_bytes_read": metrics.source_bytes_read,
                "parsed_sources": metrics.parsed_source_count,
                "reused_sources": metrics.reused_source_count,
                "source_version_checks": metrics.source_version_check_count,
                "peak_tracemalloc_bytes": peak, "index_bytes": cold_index.stat().st_size,
                "result_snapshot_bytes": snapshot_size,
                "sources_unchanged": before == _source_hashes(sources),
            })

        for sample in range(1, 4):
            audit = audits[0]
            sequence = 150 + sample
            audit.append_event(AuditEvent(
                sequence, "round_ready", "single source changed", None),
                "2026-10-13T12:00:00+00:00", float(sequence))
            if not audit.flush():
                raise RuntimeError("failed to append benchmark fixture")
            before = _source_hashes(sources)
            result, elapsed, peak = _measure(lambda: _query(sessions, cold_index))
            metrics = result.index_metrics
            snapshot_size = result._store_path.stat().st_size
            result.close()
            measurements.append({
                "scenario": "single_source_change", "sample": sample,
                "elapsed_s": elapsed, "source_bytes_read": metrics.source_bytes_read,
                "parsed_sources": metrics.parsed_source_count,
                "reused_sources": metrics.reused_source_count,
                "source_version_checks": metrics.source_version_check_count,
                "peak_tracemalloc_bytes": peak, "index_bytes": cold_index.stat().st_size,
                "result_snapshot_bytes": snapshot_size,
                "sources_unchanged_during_query": before == _source_hashes(sources),
            })

        result = _query(sessions, cold_index)
        page_samples = []
        for sample in range(1, 4):
            def read_pages_and_details():
                selected = []
                for page_number in range(1, result.page_count + 1):
                    page = result.get_page(page_number)
                    if page.events:
                        target = next((item for item in page.events if item.sequence == 75),
                                      page.events[0])
                        selected.append(result.get_detail(target.key))
                return selected

            details, elapsed, peak = _measure(read_pages_and_details)
            page_samples.append({
                "scenario": "pages_and_selected_details", "sample": sample,
                "elapsed_s": elapsed, "source_bytes_read": 0,
                "parsed_sources": 0, "reused_sources": 0,
                "pages": result.page_count, "selected_details": len(details),
                "peak_tracemalloc_bytes": peak,
                "index_bytes": cold_index.stat().st_size,
                "result_snapshot_bytes": result._store_path.stat().st_size,
                "selected_long_detail_preserved": any(
                    "raw_diagnostic" in item.detail for item in details if item),
            })
        snapshot_path = result._store_path
        result.close()
        measurements.extend(page_samples)
        print(json.dumps({
            "fixture_sources": len(sources), "fixture_events_before_changes": 450,
            "fixture_events_after_changes": 453, "page_size": 100,
            "cold_index_path": str(cold_index),
            "snapshot_removed_after_close": not snapshot_path.exists(),
            "measurements": measurements,
        }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
