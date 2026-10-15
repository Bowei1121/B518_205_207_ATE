# QP4 local validation — 2026-10-15

Fixed ticket review base: `61dccbc088dab9e48a643c711d49c74d2abb520f`.

## Implemented behavior

- A visible “Retry remaining pages” action resumes preparation against the same query result and its immutable matching-event/content references. It does not parse source files or replace the query result.
- Prepared rows remain contiguous and are left in place. Retry reads only rows after the persisted prefix, so a failure after page 6 resumes at page 7.
- Before resuming, the app verifies the temporary snapshot, retained index lease/content, and contiguous prepared prefix. A missing snapshot/index/content is reported as unavailable and requires a new search; indexed reads and lease release use SQLite read-only/read-write modes that cannot create a replacement index.
- Retry preserves the selected result, page, and selected detail. A new search or cancel invalidates late retry completions without releasing a snapshot the UI still owns. Retry is user-triggered; cancellation does not schedule another attempt.
- Traditional Chinese and English status and button labels are present.

## Validation

- `python3 -m py_compile` on the query module, app module, language catalog, and the two changed test modules: passed.
- `PYTHONPATH='B518 Log Solution/src:B518 Log Solution/tests' python3 -m unittest test_historical_event_query test_language_catalog`: 63 tests passed.
- Controlled fixed-version test: fail after page 6, append a new source event, retry, then verify all 701 original events and detail are available in the original order while the appended event is absent: passed.
- Missing-index test: delete the retained index, retry, verify a typed “search again” failure, keep the first 500 rows readable, and verify neither retry nor closing the result recreates the index: passed.
- New-query-during-retry race test: verify the newer query wins, the old retry completion is discarded, and the displayed prior snapshot remains readable: passed.
- Existing later-batch failure preservation test: passed.
- True Tk bilingual acceptance test was added as `test_real_tk_history_retry_resumes_fixed_snapshot_and_keeps_reading_page`. It could not execute on this runner: Tk aborts in the suite's shared-root `tk.Tk()` setup (exit 134, Python 3.8.10 framework build; `DISPLAY` is unset and no interactive desktop is attached). This remains an environment-bound acceptance check for an interactive macOS session.

## Fixed-base review

Standards and Spec review against `61dccbc088dab9e48a643c711d49c74d2abb520f...HEAD` is pending.
