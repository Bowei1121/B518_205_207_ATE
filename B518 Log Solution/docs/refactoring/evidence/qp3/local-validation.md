# QP3 local validation

Fixed review base: `61dccbc088dab9e48a643c711d49c74d2abb520f`.

## Behaviour and capacity

- `PYTHONPATH='src:tests:scripts' python3 -m unittest test_historical_event_query test_historical_event_display test_historical_event_capacity -q` — 72 tests passed.
- The added gated-preparation test holds a selected detail read while the background reader reaches page 6, then requests page 8. Prefetch pauses for the detail; after it completes, reads proceed at offsets 500, 700, then 600. The requested page is prepared before sequential prefetch resumes. Its database lookup uses ordinal ranges so a prepared page beyond a gap is readable without assuming all prior rows exist.
- The same test checks repeated visits across pages 1–8, the five-page compatibility view, and the 500-summary cache ceiling; preparation batches stay at or below 100 summaries.
- `python3 -m py_compile src/historical_event_query.py tests/test_historical_event_query.py` and `git diff --check` passed.

An isolated capacity sample used the public query API with the capacity fixture generator: 2,000 fixture events yielded 1,520 matching events across 16 pages. After warming six page positions, 12 more round trips (72 page requests) retained 616,206 bytes under `tracemalloc`; after those trips it retained 616,234 bytes, a 28-byte difference. Peak traced allocation during navigation was 723,911 bytes. The result held 420 list summaries at the end (hard limit 500), and each page returned at most 100. The matching index contained identities/content IDs and ordering fields, not summary or raw-event JSON. Query metrics reported 0 query content copies and 2,007,544 bytes of indexed content writes. This is a single-process Python allocation sample, not a physical-RSS or cold-disk benchmark.

## Desktop validation limitation

Attempted the real-Tk UI page/detail tests with `B518_TK_TESTS=1`; the Python process aborted with exit code 134 before producing test output. The regular non-Tk query, display, and capacity suites passed. A successful real desktop Tk run remains required before QP3 acceptance.
