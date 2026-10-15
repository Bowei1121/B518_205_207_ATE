"""Measure fixed-base completion versus QP2 first-batch availability."""

import json
import sys
import time
from datetime import date
from pathlib import Path

from historical_event_query import HistoricalEventDateRange, HistoricalEventQueryService


mode, fixture_path, index_path = sys.argv[1:4]
fixture = Path(fixture_path)
service = HistoricalEventQueryService(
    fixture / "sessions", fixture / "app-events.json", index_path=Path(index_path))
started = time.perf_counter()
generation = service.submit(
    HistoricalEventDateRange(date(2026, 7, 16), date(2026, 10, 13)))
completion = None
while completion is None:
    completion = (service.take_initial_result(generation) if mode == "staged" else
                  service.take_result(generation))
    if completion is None:
        time.sleep(0.010)
published = time.perf_counter()
assert completion.succeeded, completion.error
result = completion.result
pages = [result.get_page(number) for number in range(1, 6)]
first_five_read = time.perf_counter()
assert sum(len(page.events) for page in pages) == 500
prepared_count_at_page_read = getattr(result, "prepared_count", result.total_count)
preparation_complete_at_page_read = getattr(result, "preparation_complete", True)
final = completion
finished = published
if mode == "staged":
    final = None
    while final is None:
        final = service.take_result(generation)
        if final is None:
            time.sleep(0.010)
    finished = time.perf_counter()
assert final.succeeded and getattr(result, "preparation_complete", True)
first_round = next(event for page in pages for event in page.events
                   if event.source == "round")
detail_started = time.perf_counter()
detail = result.get_detail(first_round.key)
detail_read = time.perf_counter()
assert detail is not None
print(json.dumps({
    "mode": mode,
    "total_count": result.total_count,
    "page_count": result.page_count,
    "initial_events": len(result.initial_events) if hasattr(result, "initial_events") else None,
    "prepared_count_at_page_read": prepared_count_at_page_read,
    "preparation_complete_at_page_read": preparation_complete_at_page_read,
    "submit_to_result_publish_seconds": round(published - started, 6),
    "submit_to_500_readable_seconds": round(first_five_read - started, 6),
    "five_page_api_seconds": round(first_five_read - published, 6),
    "detail_read_seconds": round(detail_read - detail_started, 6),
    "submit_to_detail_ready_seconds": round(detail_read - started, 6),
    "submit_to_full_completion_seconds": round(finished - started, 6),
}, sort_keys=True))
result.close()
service.shutdown()
