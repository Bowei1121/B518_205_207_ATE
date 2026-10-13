# H1 local validation — date query and first page

Date: 2026-10-13 (Asia/Taipei)

## Scope and fixed baseline

- Ticket: H1 / GitHub #38, parent #37. H1 has no direct blocking ticket.
- Repository root: `/Users/tsengbowei/Desktop/公司資料/專案/FQ III/2026/B518/專案名稱/3. 程式/0. PC/B518 Log Solution`.
- Python project/test directory: `B518 Log Solution/` below the repository root.
- Branch: `HistoricalEventQuery/ticket-01`.
- Fixed Standards/Spec review base: `5aa83e2438dca802706aaba9aa10daa09bbee150` (`B518-Log-Solution` before H1 changes). The base was not advanced during review.
- Implementation/test commits: `7be0fade5643e5cc8fe5343d76fb197562612164` (`fix: preserve query semantics and bounded history display`) and `714d7239ba60bf55fd337b7f270eca7f51d24892` (`fix: freeze local timezone for history queries`); preceding H1 commits are `bc224b3`, `82af891`, and `73da818`.
- The program/test tip `714d7239ba60bf55fd337b7f270eca7f51d24892` is pushed to both configured destinations. Documentation commit, merge, final direct remote-ref query and branch cleanup are recorded in the delivery update below.
- Push destinations configured on `origin`: Gitea `http://10.64.76.34:3000/8362/B518-205_207_ATE.git` and GitHub `git@github.com:Bowei1121/B518_205_207_ATE.git`. Separate `github` remote points to that same GitHub repository; it is not an additional destination. Both push destinations were directly queried before merge: at the pre-merge check, each reported `B518-Log-Solution` at `5aa83e2438dca802706aaba9aa10daa09bbee150` and `HistoricalEventQuery/ticket-01` at `714d7239ba60bf55fd337b7f270eca7f51d24892`.
- Initial worktree inspection found unrelated worktrees and branches. They were not modified or removed. The primary target worktree had no pre-existing changes before H1.

## Entrypoints and behavior

| Concern | Verified behavior | Evidence |
| --- | --- | --- |
| History page entry | Opens the existing history window, initializes the recent-90-day range through today, and displays “not queried”; opening does not read sources. | Real-Tk integration test below. |
| Date controls | Today, recent 7/30/90 days, one day, and editable custom range. Editing does not submit. | Real-Tk integration test; public date-range tests. |
| Submission | Magnifier button and Return use the public date-query submission flow. Input is validated before a worker is started. | Real-Tk integration; `parse_historical_event_date_range`. |
| Source reading | Reuses `iter_historical_events`: audit takes precedence over the corresponding old `events.log`; standalone legacy and App event records remain included. Selection keys and original sequence/time are retained. | Mixed-source query tests and real-Tk disk fixture. |
| Date rules | Aware timestamps are converted by local epoch boundaries; naive records use their local calendar date and wall-time ordering. End is next local midnight, exclusive. | Offset, DST 23/25-hour, month/year rollover, and fall-back-fold tests. |
| Results | Newest first, stable identity and numeric sequence tie-breakers, at most 100 retained/displayed first-page events; detailed raw text is formatted only for selection or the bounded diagnostic detail view. | Query limit/stable ordering tests, summary-only rendering test, real-Tk 151-record fixture. |
| Responsiveness | File reading/query and sorting execute in a worker. Tk polls the result on the UI thread; a controlled slow source proves date fields remain editable before the read is released. | Real-Tk integration with `Event`-controlled read. |
| Read failures | Undated records remain in a diagnostic row. Source/read issues cause an explicit incomplete-result status; zero readable matches is not described as a confirmed empty range. | Query and real-Tk unreadable-source cases. |
| Old result retention | Invalid input does not submit or replace old results. While a new request is pending and after a failed request, the prior committed date range is named beside the retained rows. | Real-Tk invalid, slow-read and failed-query cases. |
| Read-only guarantee | Query performs no forced flush or source rewrite. | Before/after bytes for audit, legacy `events.log`, and App journal in the real-Tk fixture. |

## Acceptance results

1. **Default and controls — PASS.** Opened history showed the inclusive last 90 local calendar days through today without reading. Real widget selection exercised Today, 7, 30, 90 days and single-day mode; editing and custom ranges (including a range longer than 90 days) did not auto-submit.
2. **Validation and empty/not-queried distinction — PASS.** Missing and invalid start/end values and reversed intervals are rejected by the public parser with the relevant field. The real Tk test confirmed invalid/reversed submission preserves the previously committed result. Initial not-queried and a completed empty range display different states.
3. **Local dates and boundaries — PASS.** Tests cover offset conversion, naive local-wall-time interpretation, start-of-day inclusion, final second inclusion, next local midnight exclusion, month/year rollover, DST spring 23-hour and fall 25-hour days. During a repeated fall-back wall time, a naive record is not assigned a guessed absolute fold; known offset-aware events remain ordered by their actual instants and the naive record receives deterministic wall-time placement. The submitted date range captures the local timezone rules used for worker sorting; a regression test changes process TZ from New York to Tokyo after submission and confirms ordering still uses the submitted rules.
4. **Mixed sources and identity — PASS.** Real temporary audit, legacy and App event stores were queried together. Existing audit-over-legacy precedence avoided duplicate inclusion. The result retained event keys, round association, source and numeric sequence; no file or round-directory timestamp was used as the event date.
5. **Bounded first page — PASS.** A 151-event fixture returned and displayed only the newest 100 plus one warning row; the status explicitly says that more pages are for a later update. Equal timestamps use stable identity and numeric sequence. List message rendering does not prepare complete raw-detail text; detail is prepared on selection. H3 owns full pagination and H4 owns persistent indexing/normal incremental-read costs.
6. **Background query and true Tk — PASS.** A real Tk window used the actual date widgets and magnifier button. While a controlled source reader was blocked on an `Event`, the test edited the date fields and inspected the visible pending status before releasing the reader. Source bytes remained unchanged. A sandbox-only Tk launch previously exited 134 without a test result; rerunning in the authorized unlocked desktop session completed the real Tk and full-suite runs. This environment-only abort is not represented as a passing run.
7. **Ticket regression and boundary — PASS.** Existing history/language, preservation, closing, round, cleanup, KVM and application regressions ran in the full suite. H1 is eligible for merge after final fixed-base Standards/Spec review and post-merge verification. Factory volume/device performance remains follow-up work. H1 does not claim H2-H8, durable indexing, complete multi-page history, capacity acceptance, or full parent #37 delivery.

## Commands and results

Project README identifies `B518 Log Solution/` as the Python project and `scripts/run_tests.py` as the test runner. Runtime used for this ticket:

- Interpreter: `/Library/Frameworks/Python.framework/Versions/3.8/bin/python3`
- Python: 3.8.10; Tk/Tcl: 8.6/8.6
- Desktop session: accessible macOS Aqua session, 2026-10-13; actual root/window create, update, widget interaction and teardown succeeded.
- Focused non-Tk query/display tests: `PYTHONPATH=src python3 -m unittest tests.test_historical_event_display tests.test_historical_event_query` — 25 tests, passed after the timezone snapshot fix.
- Real Tk history query: `B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py test_log_solution_ui.LogSolutionUiTests.test_real_tk_historical_reader_selects_and_localizes_disk_records_without_rewriting` — 1 test, passed.
- Full suite on final program/test source `714d7239ba60bf55fd337b7f270eca7f51d24892`: `B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py` — 417 tests, 130.078 seconds, `OK`, exit code 0. This was run in the unlocked macOS Aqua desktop session with a bash wrapper preserving the child process exit code.
- Syntax and whitespace: `python3 -m py_compile` on changed source modules and `git diff --check` — passed.
- No project type-checker configuration was found; no type-checker pass is claimed.

The fixed-base Spec review initially found three actionable gaps (ambiguous naive fall-back ordering, missing prior-date label during requery/failure, and unreadable sources potentially appearing empty). These were corrected in `7be0fad`; the list/detail preparation cost was also separated and tested. A later review found that aware-record sorting could read a changed process timezone after submission; `714d723` freezes the named timezone with the submitted range and adds a fall-back transition regression test. The fixed-base Spec re-review after `714d723` passed with no blockers. Earlier full-suite runs had two stale tests that assumed opening history reads automatically and that the test runner need not pump the Tk event loop; the tests were updated to explicit-search behavior and wait for the UI result. A sandbox GUI run exited 134 before producing a test result; this is recorded as a failure, not a pass. The final accessible-desktop run completed all 417 tests in 130.078 seconds (`OK`, exit 0). Intermediate assertion/wait failures while developing the unreadable-source Tk case were fixed; the final real-Tk case passed.

## Delivery and remaining boundaries

- Cumulative program/test SHA: `714d7239ba60bf55fd337b7f270eca7f51d24892`.
- Standards review: PASS, no actionable documented-standard findings.
- Spec review: PASS on the verified macOS/Python 3.8 target, no blockers. Nonblocking portability note: if both `zoneinfo` and macOS Foundation are unavailable, or `TZ` is an unrecognized POSIX rule, the fallback stores the current fixed offset and does not model historical/future DST rules. This does not apply to the verified target runtime.
- Documentation SHA, merge SHA, post-merge suite, final direct destination query timestamps and branch cleanup are added after those steps; no merge or cleanup is claimed until they have actually completed.
- No GitHub issue was edited. Parent #37 and factory deployment/volume verification remain unchanged.
- H2 owns full cancellation/latest-generation/window-lifecycle behavior; H3 owns complete pagination/detail management; H4 owns persistent indexing and normal incremental-read cost; H5-H8 retain their stated scope.
