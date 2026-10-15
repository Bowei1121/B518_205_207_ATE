"""Compare fixed-base full reads with QP2+ staged reads on one fixture."""

import hashlib
import json
import sqlite3
import sys
import threading
import time
import tracemalloc
from datetime import date
from pathlib import Path

from historical_event_query import HistoricalEventDateRange, HistoricalEventQueryService


mode, fixture_arg, index_arg, start_arg, end_arg = sys.argv[1:6]
fixture = Path(fixture_arg)
index_path = Path(index_arg)
manifest = json.loads((fixture / "fixture-manifest.json").read_text(encoding="utf-8"))
date_range = HistoricalEventDateRange(date.fromisoformat(start_arg), date.fromisoformat(end_arg))
source_hashes = manifest["source_sha256"]


def source_digest():
    digest = hashlib.sha256()
    for relative_path in sorted(source_hashes):
        digest.update(relative_path.encode("utf-8"))
        digest.update(hashlib.sha256((fixture / relative_path).read_bytes()).digest())
    return digest.hexdigest()


source_before = source_digest()
tracemalloc.start()
service = HistoricalEventQueryService(
    Path(manifest["sessions_path"]), Path(manifest["app_event_path"]),
    index_path=index_path)
started = time.perf_counter()
generation = service.submit(date_range)
completion = None
while completion is None:
    if mode == "staged" and hasattr(service, "take_initial_result"):
        completion = service.take_initial_result(generation)
    else:
        completion = service.take_result(generation)
    if completion is None:
        time.sleep(0.005)
first_publish = time.perf_counter()
if not completion.succeeded:
    raise completion.error
result = completion.result
first_pages_started = time.perf_counter()
pages = [result.get_page(number) for number in range(1, min(5, result.page_count) + 1)]
first_pages_finished = time.perf_counter()
readable_count = sum(len(page.events) for page in pages)
prepared_at_read = getattr(result, "prepared_count", result.total_count)
complete_at_read = getattr(result, "preparation_complete", True)

full_completion = completion
finished = first_publish
if mode == "staged" and hasattr(service, "take_initial_result"):
    full_completion = None
    while full_completion is None:
        full_completion = service.take_result(generation)
        if full_completion is None:
            time.sleep(0.005)
    finished = time.perf_counter()
if not full_completion.succeeded:
    raise full_completion.error

all_keys = []
digest_started = time.perf_counter()
for page_number in range(1, result.page_count + 1):
    all_keys.extend(item.key for item in result.get_page(page_number).events)
digest = hashlib.sha256("\n".join(all_keys).encode("utf-8")).hexdigest()
digest_seconds = time.perf_counter() - digest_started
detail_seconds = None
if all_keys:
    detail_started = time.perf_counter()
    if result.get_detail(all_keys[0]) is None:
        raise AssertionError("first result has no detail")
    detail_seconds = time.perf_counter() - detail_started

metrics = result.index_metrics
snapshot_bytes = result._store_path.stat().st_size if result._store_path.exists() else 0
index_bytes = index_path.stat().st_size if index_path.exists() else 0
with sqlite3.connect(str(result._store_path)) as snapshot_connection:
    matching_columns = {row[1] for row in snapshot_connection.execute(
        "PRAGMA table_info(matching_events)")}
    if "event_json" in matching_columns:
        event_json_rows, event_json_bytes = snapshot_connection.execute(
            "SELECT COUNT(*), COALESCE(SUM(length(event_json)), 0) "
            "FROM matching_events").fetchone()
    else:
        event_json_rows, event_json_bytes = 0, 0
result.close()
service.shutdown()
deadline = time.monotonic() + 5
while any(thread.name == "HistoricalEventDateQuery" for thread in threading.enumerate()):
    if time.monotonic() >= deadline:
        raise AssertionError("query worker did not stop after close")
    time.sleep(0.005)
tracemalloc_peak = tracemalloc.get_traced_memory()[1]
tracemalloc.stop()

if source_before != source_digest():
    raise AssertionError("query modified a fixture source")
if len(all_keys) != result.total_count or readable_count != min(500, result.total_count):
    raise AssertionError("public pages do not match the reliable total")

print(json.dumps({
    "mode": mode,
    "date_range": [start_arg, end_arg],
    "total_count": result.total_count,
    "page_count": result.page_count,
    "first_batch_count": readable_count,
    "prepared_count_when_first_pages_read": prepared_at_read,
    "complete_when_first_pages_read": complete_at_read,
    "submit_to_total_count_seconds": getattr(result, "total_count_ready_seconds", None),
    "submit_to_sorted_initial_batch_seconds": getattr(result, "initial_batch_ready_seconds", None),
    "submit_to_first_readable_pages_seconds": first_pages_finished - started,
    "first_pages_read_seconds": first_pages_finished - first_pages_started,
    "submit_to_full_completion_seconds": finished - started,
    "full_page_order_digest_seconds": digest_seconds,
    "full_page_order_sha256": digest,
    "index_degraded": result.index_degraded,
    "index_issue": result.index_issue,
    "selected_detail_seconds": detail_seconds,
    "parsed_sources": metrics.parsed_source_count,
    "reused_sources": metrics.reused_source_count,
    "source_version_checks": metrics.source_version_check_count,
    "source_bytes_read": metrics.source_bytes_read,
    "query_content_copy_count": getattr(metrics, "query_content_copy_count", None),
    "query_content_copy_bytes": getattr(metrics, "query_content_copy_bytes", None),
    "indexed_content_write_count": getattr(metrics, "indexed_content_write_count", None),
    "indexed_content_write_bytes": getattr(metrics, "indexed_content_write_bytes", None),
    "event_json_copied_rows": event_json_rows,
    "event_json_copied_bytes": event_json_bytes,
    "query_snapshot_bytes": snapshot_bytes,
    "index_bytes": index_bytes,
    "detail_materialized_count": 1 if all_keys else 0,
    "tracemalloc_peak_bytes": tracemalloc_peak,
    "worker_threads_after_cleanup": [thread.name for thread in threading.enumerate()
                                      if thread.name == "HistoricalEventDateQuery"],
    "source_manifest_digest": source_before,
    "os_cache_condition": "uncontrolled; no claim of cold disk",
}, ensure_ascii=False, sort_keys=True))
