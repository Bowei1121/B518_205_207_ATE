# QP4 local validation — 2026-10-15

Fixed ticket review base: `61dccbc088dab9e48a643c711d49c74d2abb520f`.

## Implemented behavior

- A visible “Retry remaining pages” action resumes preparation against the same query result and its immutable matching-event/content references. It does not parse source files or replace the query result.
- Prepared rows remain contiguous and are left in place. Retry reads only rows after the persisted prefix, so a failure after page 6 resumes at page 7.
- Before resuming, the app verifies the temporary snapshot, retained index lease/content, and contiguous prepared prefix. A missing snapshot/index/content is reported as unavailable and requires a new search; indexed reads and lease release use SQLite read-only/read-write modes that cannot create a replacement index.
- Retry preserves the selected result, page, and selected detail. A new search or cancel invalidates late retry completions without releasing a snapshot the UI still owns. Retry is user-triggered; cancellation does not schedule another attempt.
- Traditional Chinese and English status and button labels are present.

## Validation

- `python3 -m py_compile` on the query module, app module, language catalog, and the two changed test modules: passed, including the final Tk assertion edit.
- `PYTHONPATH='B518 Log Solution/src:B518 Log Solution/tests' python3 -m unittest test_historical_event_query test_language_catalog`: 63 tests passed.
- Controlled fixed-version test: fail after page 6, append a new source event, retry, then verify all 701 original events and detail are available in the original order while the appended event is absent: passed.
- Missing-index test: delete the retained index, retry, verify a typed “search again” failure, keep the first 500 rows readable, and verify neither retry nor closing the result recreates the index: passed.
- New-query-during-retry race test: verify the newer query wins, the old retry completion is discarded, and the displayed prior snapshot remains readable: passed.
- Retry-cancel race test: cancel an in-flight preparation retry, verify the prior fixed snapshot remains open, then explicitly retry it to completion: passed at the query-service level.
- Existing later-batch failure preservation test: passed.
- True Tk bilingual acceptance test `test_real_tk_history_retry_resumes_fixed_snapshot_and_keeps_reading_page` covers failure, cancellation while retrying, button recovery, same-snapshot retry, page/detail preservation, and source-version isolation: passed in 1.906 seconds in the coordinator's approved interactive desktop session.
- `git diff --check`: passed.

## Fixed-base review

- Standards review against `61dccbc088dab9e48a643c711d49c74d2abb520f...6fc8ff4aa5ac0cb13e4dd109f74d778b912a9e61`: no documented-standard violations or actionable smells.
- Spec review against the same fixed range: no confirmed implementation blocker. The reviewer initially flagged a missing cancel refresh, then withdrew it after confirming `_refresh_cancelled_preparation_state`; the true Tk cancellation case above now passes.
- Final review range after the test/evidence-only follow-up commits is `61dccbc088dab9e48a643c711d49c74d2abb520f...HEAD`; reviewers should verify that these additions do not change the prior conclusions.
