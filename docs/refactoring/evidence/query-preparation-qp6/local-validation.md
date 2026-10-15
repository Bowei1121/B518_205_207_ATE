# QP6 local validation

Fixed ticket review base: `990a3d87193035e9dc235fb8f765267fdd8f820a`.
Measured implementation: `c816286e1d17bac92192634d3717cae5e10df22c`.

## Matched cost fixture

- Fixture: 10,000 synthetic mixed-source events, 12 logical sources, 13 physical files including the ignored legacy-precedence duplicate; source manifest total 4,057,369 bytes. This is engineering data, not an asserted field distribution.
- Rebuild command: `python3 'B518 Log Solution/scripts/historical_event_capacity.py' prepare --root /private/tmp/qp6-fixture --events 10000 --as-of 2026-10-13`.
- One-day range `2026-10-13`: 84 results (under 500). Near-seven-day range `2026-10-07..2026-10-13`: 588 results (over 500).
- Runtime for both revisions: Python 3.8.10, macOS 10.16 x86_64. OS file cache was neither flushed nor controlled; no cold-disk claim is made.
- For each range and revision: three new-index builds, three warm-index re-queries, and three corrupted-index recoveries: 36 measured processes total. Warmups were excluded. The baseline and current source used the same fixture bytes and staged public query path.
- Every run verified all returned page keys and the full-order SHA-256; baseline/current hashes matched in every range and lifecycle. The runner also checked fixture-source hashes before and after each sample and found no source edits. All query workers were gone after cleanup.
- Raw rows and medians are in `raw-measurements.jsonl` and `benchmark-report.json`; the command is `python3 docs/refactoring/evidence/query-preparation-qp6/run-phase-benchmark.py --fixture /private/tmp/qp6-fixture --baseline /private/tmp/b518-qp6-base --current /private/tmp/b518-qp6 --output /private/tmp/qp6-runs-4`.

## QP6 fixed-base result

Warm-index end-to-first-readable-page medians decreased from 122.920 ms to 65.051 ms for the 84-row day (47.1%), and from 161.461 ms to 120.132 ms for the 588-row seven-day range (25.6%). Full completion decreased from 122.952 ms to 65.068 ms and from 172.303 ms to 132.540 ms respectively. The elapsed path includes source confirmation, reliable count, sorted initial-batch preparation, and reading the first pages.

The warm-query change skips the global content-table sweep when every indexed source is unchanged and no dead query owner was found. It retains global reclamation after source/index changes and when dead-process query leases are removed. The new test `test_warm_query_skips_global_reclamation_while_live_snapshots_are_owned` verifies the warm path; `test_index_reclaims_contents_owned_only_by_abandoned_query` and `test_indexed_requery_reclaims_unreferenced_generation_when_owner_closes` verify reclamation still occurs when needed.

| Lifecycle | One day, fixed base → current | Near seven days, fixed base → current |
|---|---:|---:|
| Initial index build, first readable | 4.613 s → 4.925 s | 4.851 s → 4.425 s |
| Warm re-query, first readable | 122.920 ms → 65.051 ms | 161.461 ms → 120.132 ms |
| Corrupt-index recovery, first readable | 4.959 s → 4.504 s | 4.521 s → 4.568 s |

The QP6 optimization gives lower warm-query latency in both tested ranges; first build/recovery remain source-scan bound and do not improve uniformly.

First-index-build time did not improve for every sample: the one-day median was 4.925 s current vs 4.613 s fixed base (+6.8%); the seven-day median was 4.425 s vs 4.851 s (-8.8%). Corrupt-index recovery was 4.504 s vs 4.959 s for one day and 4.568 s vs 4.521 s for seven days. These source scans dominate first-build/recovery; the warm-query optimization does not claim a uniform speedup there.

## Copy, storage, and memory accounting

- At the QP6 ticket base, both revisions already reuse indexed event content from QP1, so both report zero repeated event-JSON copy bytes. The QP6 change preserves that result while reducing warm-query time.
- Historical context against the fixed pre-QP1 implementation (`31d08141add7bf9a936e701d99f193455bf40ede`) is recorded separately in `historical-original-comparison.json` and `historical-original-comparison.jsonl`. On warm re-query it copied 100,415 JSON bytes for the 84-row day and 574,711 bytes for 588 rows; current copies zero query-event JSON bytes. Current initial index creation instead writes 9,459,562 bytes once into the persistent shared content index. This is an upfront derivative-store cost, not free work.
- Warm temporary query snapshots are 102,400 bytes for one day and 544,768 bytes for seven days; historical pre-QP1 snapshots were 225,280 and 1,306,624 bytes. The QP6 persistent index is 27,893,760 bytes for this fixture (about 3.7 MB larger than the historical baseline index).
- Median Python `tracemalloc` peak for the QP6 fixed-base comparison was about 437 KB for one day and 2.080 MB for seven days, essentially unchanged by this optimization. Against the historical pre-QP1 baseline, one-day peak fell from about 694 KB to 437 KB; seven-day peak rose from about 1.673 MB to 2.079 MB. No RAM threshold is asserted.

No 2.16-million-event run was done: QP6 explicitly rejects making that multi-hour capacity workload the default, while the 10,000-event mixed-source fixture exercises both sides of the 500-row boundary, source-version confirmation, index reuse, corruption recovery, page ordering, and detail reads. Existing H8 capacity artifacts remain historical evidence and are not relabeled as current QP6 runs.

## Functional and desktop acceptance

- `PYTHONPATH='B518 Log Solution/src:B518 Log Solution/tests' python3 -m unittest test_historical_event_query` — 59 tests passed after the QP6 code change.
- `B518_TK_TESTS=1 python3 'B518 Log Solution/scripts/run_tests.py' test_log_solution_ui.LogSolutionUiTests.test_real_tk_history_query_latest_request_cancel_and_window_lifecycle test_log_solution_ui.LogSolutionUiTests.test_real_tk_qp3_cached_pages_detail_language_and_cancelled_requery test_log_solution_ui.LogSolutionUiTests.test_real_tk_history_retry_resumes_fixed_snapshot_and_keeps_reading_page test_log_solution_ui.LogSolutionUiTests.test_real_tk_history_language_refresh_preserves_draft_snapshot_page_and_detail test_log_solution_ui.LogSolutionUiTests.test_real_tk_close_waits_for_source_preparation_before_destroy` — 5 true Tk tests passed in 13.046s.
- `python3 -m py_compile 'B518 Log Solution/src/historical_event_query.py' 'B518 Log Solution/tests/test_historical_event_query.py'` and `git diff --check` — passed.
- Related display/capacity/retention/language/monitoring suites and the repository-wide final regression are scheduled for the final integration pass; their final results are recorded in the integration ledger, not claimed here.

The 42-story mapping is in `42-story-matrix.md`. Factory/physical-station acceptance remains a separate deployment activity and is not claimed as software acceptance.
