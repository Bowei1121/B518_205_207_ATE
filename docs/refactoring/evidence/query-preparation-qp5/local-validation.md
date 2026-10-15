# QP5 local validation

Fixed review base: `f4fa96812ee5bae6cde33fb90de174ab0ab5ad2b`.

QP5 integrates the lifecycle, cancellation, retry, and reclamation behavior
introduced across QP1–QP4. The fixed-snapshot ownership and single-worker/latest-
pending request contracts already reside in the query services; this ticket adds
cross-feature acceptance evidence rather than duplicating those implementations.

## Query and source lifecycle

- `PYTHONPATH='B518 Log Solution/src:B518 Log Solution/tests' python3 -m unittest test_historical_event_query` — 58 tests passed in 16.811s.
- Coverage includes latest-generation publication and cancellation, coalesced work,
  retry cancellation while retaining the displayed snapshot, replacement while an
  old batch is in flight, closing during detail open, persistent-index reuse,
  reference-aware reclamation, source replacement/cleanup, immutable captured
  detail, and index degradation/repair.

## True Tk acceptance

Runtime: macOS Aqua Tk. Each test ran in the coordinator-assigned interactive Tk
slot with sandbox escalation; direct non-escalated Tk launches are not supported
in this environment.

- `B518_TK_TESTS=1 python3 'B518 Log Solution/scripts/run_tests.py' test_log_solution_ui.LogSolutionUiTests.test_real_tk_history_query_latest_request_cancel_and_window_lifecycle test_log_solution_ui.LogSolutionUiTests.test_real_tk_history_language_refresh_preserves_draft_snapshot_page_and_detail test_log_solution_ui.LogSolutionUiTests.test_real_tk_close_waits_for_source_preparation_before_destroy` — 3 tests passed in 11.366s.
- These exercise a slow obsolete query, cancellation and replacement, language
  switching without replacing the displayed snapshot/page/detail, and responsive
  normal close while source preparation is still active.
- QP3 cached-page/detail/language/cancel and QP4 same-snapshot retry True Tk
  acceptance passed on the same integration line immediately before this ticket.

## Static checks

- `python3 -m py_compile 'B518 Log Solution/src/historical_event_query.py' 'B518 Log Solution/tests/test_historical_event_query.py' 'B518 Log Solution/tests/test_log_solution_ui.py'` — passed.
- `git diff --check` — passed.

No production source changed for QP5; this ticket records the cross-feature
acceptance of the existing lifecycle contracts. QP6 cost acceptance remains
separate and is not represented as passed here.
