# H2 local validation — 2026-10-13

## Scope and fixed baseline

- Ticket: H2 / GitHub #39, “重新查詢、取消與視窗生命週期”. This is the historical-event-query series, not a same-number ticket in another series.
- H1 dependency: fixed review base `0699ab74b96e43a60e53f0cd7f7e2fabdbebde05` is the current `B518-Log-Solution` H1 delivery. Its ancestry includes the H1 date query implementation and delivery records. The H1 source at this base exposes the real History page, valid date submission, timezone-frozen range, mixed-source reader, 100-row initial result and read-only background scan. H1 evidence: [local validation](../historical-event-query-ticket-01/local-validation.md).
- H2 fixed Standards/Spec review base: `0699ab74b96e43a60e53f0cd7f7e2fabdbebde05`; this remains fixed regardless of later commits.
- H2 implementation commit: `dd6b08796cf6ce0025979531fb7ea4c855299764` (`Add cancellable historical query lifecycle`). Additional real-Tk test commits: `19e628a` (`test: cover cancelling initial history query`) and a follow-up asserting audit/App-event source bytes are unchanged. All are on `HistoricalEventQuery/ticket-02`; pushes to Gitea and GitHub succeeded, and the initial push configured upstream tracking. Documentation/review/final remote results will be recorded in the final delivery update.
- The working tree was checked before documenting: H2 branch clean at the program/test commit. Other worktrees, branches, and pre-existing project-summary changes were left untouched.

## Entry points and responsibilities

| Path | Current responsibility | H2 behavior and evidence |
| --- | --- | --- |
| History page open / date editing | Build the real Tk history window and edit draft dates | No query starts from open or edits. Draft values stay independent of the submitted request and displayed result range. |
| Magnifier query button | Validate through H1 and submit a frozen date/timezone range | Assigns a fresh generation. The worker reads the immutable `HistoricalEventDateRange`, never Tk variables. |
| Re-query while reading | Display progress while the old result remains readable | Signals cooperative cancellation to the active read and replaces the single pending request with the latest submission. One service worker is used; queued intermediate requests are discarded. |
| Cancel button | Cancel the currently displayed request | Immediately invalidates its generation and signals its cancellation event. Old results and their date range remain visible; without old results the page shows a cancelled/empty state rather than presenting the query as successful. |
| Worker completion and Tk poll | Publish current success/error/progress | Only the current generation can be taken or displayed. Late completion/error from stale, cancelled, closed, or prior-window work is discarded. Widget operations remain in the Tk poll path. |
| Window close, destroy, hide/reopen | Own only this history window's query lifecycle | Close/destroy invalidates the view generation and cancels its request. Reopen creates a new window lifecycle; it does not inherit old results or accept old deliveries. Existing hide behavior is not repurposed as destroy. |
| App close | Existing coordinator owns save/close policy | History query service signals cancellation and shuts down without joining a reader. It does not stop monitoring, enqueue persistence work, or block complete App close on a reader that is currently stuck in I/O. |
| Existing source reader | Read audit, legacy events, and App events under H1 rules | Kept read-only and unchanged in precedence, identity, local-day filtering and first-page cap. Cooperative cancellation checks are additive; source records are not flushed or rewritten. |

## Acceptance evidence

| H2 acceptance | Evidence and result |
| --- | --- |
| Freeze submitted date/timezone and generation; drafts do not invalidate or relabel current result | Real Tk lifecycle case submits January, edits to February without submitting, and asserts the existing result, selection and its prior date label remain. March is submitted and the worker records the frozen March range. H1 timezone snapshot behavior remains covered by H1 tests. |
| Latest request wins; stale result/progress/error cannot publish | With a controlled Event gate, A is held while B then C are submitted. B never starts; after A is released, C starts. A then returns a controlled late error; the actual page accepts only C and keeps its status/result. The service unit case separately verifies one active worker and latest-pending coalescing. |
| Actual cancellation preserves old result/range and visibly reports cancellation | Before any successful query, the test blocks a real read, activates the real Cancel button and checks the visible cancelled state with no result still present; it then releases the reader and proves the late completion does not change the state. Later, with a prior March result, it cancels blocked D and verifies the previous result/range remains, then releases D and confirms the stale completion changes neither status nor result. |
| Window close/reopen invalidates old work and bounds requests | The test invokes the registered WM-close callback while E is blocked, confirms its cancellation was signalled, opens a distinct new window, and sends F while E remains blocked. Releasing E does not update the new page; F becomes the only pending/latest work and then populates the new page. The page button path and registered WM protocol are tested separately from a physical title-bar click, which was not claimed. |
| Real Tk remains usable during slow read; only Tk path updates widgets | While Event gates block the source, the test edits date widgets, submits newer requests, activates Cancel, closes/reopens the window and later closes the App. These are actual widget events and Tk updates, not `Menu.invoke` or mock widgets. The controlled reader releases in cleanup. |
| No accumulating workers/resources; monitoring and App save/close contract remain intact | The service test observes max one simultaneous read across repeated submissions and verifies intermediate requests coalesce. The Tk test leaves a reader blocked and calls the public App close path; UI reaches `close_status().status == "complete"` without waiting for the source gate. Monitoring and persistence implementation/policy were not changed. H2 does not add saves or alter close generation. |
| Required regressions and desktop acceptance | Focused H2/H1 language/history cases and the complete Tk-enabled suite passed on Python 3.11.7 as below. No factory acceptance is claimed. |

Tests exercised: `tests.test_historical_event_query`, `LogSolutionUiTests.test_real_tk_history_query_latest_request_cancel_and_window_lifecycle`, and `LogSolutionUiTests.test_integrated_language_refresh_keeps_open_settings_diagnostics_and_history`.

## Runtime and commands

- Desktop: macOS Aqua, Python 3.11.7 at `/opt/anaconda3/bin/python3`, Tcl/Tk 8.6.12; real root/window creation, event processing and destruction succeeded.
- Focused command from `B518 Log Solution/`:

  ```sh
  PATH=/opt/anaconda3/bin:$PATH B518_TK_TESTS=1 PYTHONPATH=src python3 -m unittest tests.test_log_solution_ui.LogSolutionUiTests.test_real_tk_history_query_latest_request_cancel_and_window_lifecycle tests.test_log_solution_ui.LogSolutionUiTests.test_integrated_language_refresh_keeps_open_settings_diagnostics_and_history tests.test_historical_event_query
  ```

  Result after adding the no-previous-result cancellation scenario: **14 tests passed**.
- Required complete command from `B518 Log Solution/`:

  ```sh
  PATH=/opt/anaconda3/bin:$PATH B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py
  ```

  Initial complete run: **419 tests passed**, 130.396 seconds, exit 0. After adding the initial-cancellation assertion, a full rerun passed 419 tests / 127.940 seconds / exit 0. After adding explicit source-byte equality assertions, the final full rerun passed **419 tests**, 129.330 seconds, exit 0.
- `git diff --check` and `python3 -m py_compile` for the changed Python files passed. The repository has no configured mypy/pyright/type-check command; no new type-check tooling was added.

### Python 3.8/Tk aborts and fixed-base comparison

The default `/usr/bin/python3` is Python 3.8.10 with Tk 8.6. In this environment, the full current suite aborted with exit 134/139 during `Tcl_AsyncDelete`/cross-thread Tk shutdown. This was not counted as a pass. A separate, isolated worktree at the fixed H2 base reproduced the runtime issue: one run completed 417 tests; a second `-X faulthandler` run aborted with exit 139 and showed the existing audit/event writer and conflict-notice path invoking Tk `event_generate` from the wrong thread. One sandboxed Python 3.11.7 focused attempt also aborted during Aqua/AppKit Tk initialization (exit 134, before test cases); rerunning the same tests through the authorized desktop succeeded. The first run after adding the initial-cancel check failed with `StopIteration` because the test fixture left its draft date at the cancelled date; resetting the draft to the default H1 range fixed the fixture, and the final focused and full runs passed. The H2 branch's final full suite was run on the accessible Python 3.11.7 desktop and completed successfully. These failures remain visible here rather than being hidden by the successful runs.

Cooperative cancellation does not forcibly interrupt an individual source-file read: the existing `iter_historical_events` reader consumes a source before yielding its events. Cancellation sets the query request's cancellation event and invalidates the generation immediately; if an in-progress file read cannot stop at that point, its eventual completion is discarded and the worker releases its request before taking the latest pending one. No thread is terminated and Tk does not wait for the read.

## Persistence, scope, review and delivery status

- Querying reads saved audit, old `events.log`, and App-event data through existing read APIs. It does not force-flush, mutate a source, save a query, or touch monitoring decisions. The H2 real-Tk lifecycle test compares the isolated audit and App-event files byte-for-byte before the first query and after repeated queries/cancel/window reopen; H1 also has its own real-Tk source-byte evidence. Production journals and operator exports were never used.
- No monitoring, arbitration, alarm confirmation, persistence format, retention, archive, cleanup, or KVM policy was changed. No issue was published, edited or closed. The parent #37 was not modified.
- H3 owns complete pagination; H4 indexing/incremental-read guarantees; H5 complete error/recovery UI; H6 persistence/retention race integration; H7 icon/keyboard/full query-state localization; H8 capacity and full legacy-flow closeout. H2 does not claim those or parent delivery.
- Fixed-base review results: Standards reported no blocking documented-rule issue; one nonblocking judgment call suggested a single completion slot might be simpler than the generation-keyed completion map. Spec found no missing H2 requirement or scope creep; it called out the individual-file read cancellation limit above. Both reviews used fixed base `0699ab74b96e43a60e53f0cd7f7e2fabdbebde05` against the final diff. Final docs SHA, merge SHA and post-push direct GitHub/Gitea refs remain to be appended after synchronization. Final app/full-suite verification applies to program/test commit `3ff786bb2db7124d794f6ab216ff3ca10cea1168` (initial implementation commit `dd6b087`).
