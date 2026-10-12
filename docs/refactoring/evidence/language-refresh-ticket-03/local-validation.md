# L3 local validation — 2026-10-12

## Result and version

**L3 implementation and all eight acceptance items pass on the final code/test version.** The required desktop suite completed: **383 tests in 160.014 seconds, OK, exit 0**, including L1 notice lifecycle, real-source conflict/alarm, App/cross-round close, archival, retention and KVM regression. Final delivery documentation review and mainline merge verification are tracked separately below; L4/parent-wide acceptance and cleanup-reason C1–C4 are not claimed complete.

- Fixed Standards/Spec base: `93ac9e47903649c4098c1423c2496f86ac685a03` (captured before L3 edits; never advanced).
- Final code/test SHA: `04c2b0d04f1d6e634b57628b58306abdcd43bcdb`.
- Formal repository: `/Users/tsengbowei/Desktop/公司資料/專案/FQ III/2026/B518/專案名稱/3. 程式/0. PC/B518 Log Solution`; Python/test cwd is its nested `B518 Log Solution/` directory.
- Ticket worktree/branch: `/private/tmp/B518-LanguageRefresh-ticket-03`, `LanguageRefresh/ticket-03`.
- L1 dependency commit `7b853830fd19990b87ae6be93beebdee909ab0bf` is an ancestor of the fixed base; its notification, isolated failure, aggregate/retry, fixed bilingual diagnostics and close guards are present in actual code and pass in this final suite. L2 is also already in the base, but is not a direct dependency.
- The formal worktree's pre-existing user changes to `PROJECT_SUMMARY_2026-10-09.md` and `PROJECT_SUMMARY_2026-10-12.md` were left untouched while implementing in the ticket worktree. They are excluded from ticket commits and must be preserved through merging.
- Remotes retained: origin fetch/push Gitea `http://10.64.76.34:3000/8362/B518-205_207_ATE.git`; additional origin push/GitHub remote `git@github.com:Bowei1121/B518_205_207_ATE.git`. Both code/test pushes succeeded. Direct destination checks are dated snapshots, not assertions about a future HEAD.

## Window, operation and producer inventory

| Entry | Language responsibility | Normal data/lifecycle responsibility retained |
| --- | --- | --- |
| Main language menu, keyboard/queued requests | App current language and L1 notification remain authoritative. | Existing preference persistence/error separation and close guard remain. Actual menu button opens the menu; test selection uses Menu.invoke, not a claim of native menu mouse/keyboard navigation. |
| Conflict review | Direct live L1 receiver renders title, position/candidate list, controls, four-field comparison, snapshot detail and empty state in place. | Normal polling still renders changed candidate data; selection uses conflict_id. Keep/adopt remain coordinator operations. Hidden views remain registered; actual Destroy unregisters and clears view references. |
| Round alarm | Direct live L1 receiver renders current alarm/readiness title, body and acknowledgment controls, without raising/reopening or acknowledgment. | New round/alarm/readiness changes use the normal path; original round_id/alarm_id, preparation protection and acknowledgment remain. Withdraw stays hidden; Destroy unregisters only that view. |
| Close progress | Uses the same App current-language basis on initialization and ordinary status updates; no close-time language switching is introduced. | Public close/retry/cancel, generation and stale completion isolation remain. Refresh retry is visually disabled and queued public requests are refused while closing; cancel restores retry only if failures remain. |
| Main legacy fanout | Duplicate conflict/alarm language rendering removed. | Main renders its own controls. Normal event/round/save rendering remains; full legacy cleanup is L4. |
| Failure diagnostics | Existing L1 aggregate, safe diagnosis and manual latest-language retry. | Existing AppEventStore captures message identity, fixed parameters, both languages, raw diagnostic, own event identity/time/sequence and no invented round_id; original ordered retention/retry remains. |
| Artificial operation events | Language rendering produces none. | Conflict keep/adopt and alarm acknowledgment each remain one coordinator operation and one fixed bilingual round record. |

Four-field order remains result, SN, source time, source filename. Both differing sides retain actual red/bold fonts; equal/unknown cases, empty state, directory disambiguation and immutable captured evidence remain covered by existing true-Tk cases. Raw source IDs, paths, platform identifiers, time values and diagnostics are never translated.

## Final commands, runtime and evidence

Interpreter `/opt/anaconda3/bin/python3.11`, Python **3.11.7**, Tcl/Tk **8.6**, desktop session. PATH resolves python3 to that runtime. From the nested Python project directory:

```sh
PATH=/opt/anaconda3/bin:$PATH PYTHONFAULTHANDLER=1 B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py
```

Final result: **383 tests / 160.014 s / OK / exit 0** at `04c2b0d…`. Full output: [final code Tk suite](logs/final-code-tk-suite.log). It contains no Traceback, RuntimeError, Tcl_AsyncDelete or invalid-command warning. `git diff --check` and Python compile checks pass. No project type-check configuration exists; type checking is not claimed and no new type-check project was added.

Focused invocation uses the same environment and appends public unittest test names to `scripts/run_tests.py`. Actual runs included:

- Wrapped-reading/snapshot/failure cases: 3 tests, 7.440 s, pass.
- List-top/sash plus real sample-json source-to-Tk/disk: 3 tests, 10.839 s, pass.
- Simultaneous failure/partial/full recovery and WM lifecycle: 1 test, 6.085 s, pass.
- Final close-time controls, L1 failure, close generation/cancel and GC cleanup: 4 tests, 10.778 s, pass.
- Original destroyed-UI worker-GC subprocess repeated six times: 6 tests, 8.102 s, pass.
- Previously stalled L1 notice lifecycle: isolated 1 test, 4.295 s, pass; six instrumented repeats, 7.111 s, pass; final whole-suite case also pass. Probe recorded visible notice and acknowledgment-button focus at each Escape. No L1 notice product modification was made.

Tests use isolated preferences, App journal, Session/audit, actual temporary sources and fresh readers. Real sample-json and Atlas paths run through public start/round and actual Tk; synthesized long content supplements boundary/layout evidence. `test_m10_integration.M10SourceIntegrationTests.test_real_source_all_windows_switch_cancel_and_single_decisions` additionally checks real source, coexisting windows, pending conflict/alarm, close/cancel/reclose and disk decisions on this final version. Successful teardown waits public complete/archived status before temporary data removal.

## Eight-item acceptance matrix

| # | Result | Final-version evidence |
| --- | --- | --- |
| 1 | **Pass** | `test_conflict_and_alarm_refresh_fail_independently_and_retry_latest_language`: both direct receivers, actual disabled retry during close, queued public retry refused, current-language progress and cancel restoration. Existing language-close guards pass. |
| 2 | **Pass** | Same integration tests preserve original window/conflict_id/snapshot, actual comparison font/color, wrapped raw reading anchor at non-default view. `test_scrolled_conflict_candidates_keep_reading_position_on_language_change` holds 28 candidates, selected candidate 17, visible top identity and sash 200 through repeated switching. |
| 3 | **Pass** | Pending alarm/conflict unchanged through notifications/retry. Real Atlas other-slot collection, real sample source decisions and all KVM/unknown-source/product-release regressions pass. |
| 4 | **Pass** | Actual close buttons, registered WM_DELETE_WINDOW Tcl protocol (withdraw), hidden switch/reopen, external Destroy and new-window recreation verified. Same pending identity and appropriate live registration survive; physical title-bar clicking is not claimed. Existing modal focus/notice regressions pass. |
| 5 | **Pass** | Each receiver and both together fail; other views/main operations continue. Manual button retries latest language on same views, partial recovery retains remaining alarm failure, full recovery clears current banner; 350 ms Tk ticks show no automatic retry/diagnostic loop. |
| 6 | **Pass** | Existing `test_close_waits_responsively_and_cancellation_invalidates_old_completion`, real App failure/retry, source preparation, previous-round audit and complete-save regressions pass. New close/cancel test retains failures/pending work and stopped collection; stale generation cannot destroy UI. |
| 7 | **Pass** | Actual sample-json/Atlas sources, public coordinator, real Tk and fresh App/Session/audit readers reconstruct final results, single manual decisions/ack, immutable bilingual diagnostics and original identity/time/sequence. Audit/source evidence bytes unchanged by refresh; new diagnostics checked separately. |
| 8 | **Pass** | Failed receiver stays stale until explicit retry (no duplicate main language path), while real new candidates, removals, alarm/readiness and save status still render. All 383 existing/new tests pass without skips introduced by L3. |

## Red-green changes and retained earlier failures

- `d3814f8`: long wrapped evidence test first failed (visible raw line 10 became 9). Capture top Text logical line/column and offset within the immutable raw suffix; restore that raw reading anchor after localized labels change.
- `4f672dc`: list top identity and sash moved during translation. Capture current visible candidate identity and sash, restore after in-place translated geometry settles; no persistent layout setting or candidate policy change.
- `3f0031fd44a0e82548406c7cf5367de47de2c13a`: simultaneous/partial recovery and actual WM protocol evidence added.
- `04c2b0d…`: actual close showed retry button visually enabled despite public guard. Disable it while closing; restore only valid pending-failure state after cancel.
- Intermediate 3f suite: **383 tests / 151.573 s / FAILED (2)**, retained in [previous failed suite](logs/previous-failed-tk-suite.log). One new assertion incorrectly compared pending App `.events` as it drained; changed to public complete `.records`. Existing destroyed-UI GC subprocess deleted its temp root before public background close completed (`Directory not empty`); added public request_close/complete wait after retaining all original object-lifetime/worker-GC assertions. No production lifecycle rewrite, removed assertion, skip or weakened test. Six focused repeats and final whole suite pass after these corrections.
- Earlier d381 full suite: **382 tests / 152.769 s / OK**; not substituted for the final 383 result.
- User reports the earlier timeout likely followed Python abnormal shutdown. This is recorded as an observation, not a proved root cause. Earlier traces are retained below; repeated fresh and final complete runs resolve the present validation gate, without claiming the original cause is diagnosed conclusively.

## Earlier attempts (historical, superseded by final validation)

Required command from the Python project directory:

```text
B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py
```

- Host-default Python 3.8.10 / Tk 8.6: Tk class setup aborted in native initialization (exit 134); no complete suite result.
- Python 3.11.7 / Tk 8.6 with desktop access: the run advanced through preceding tests but stalled for over two minutes at `test_notice_escape_hidden_reopen_and_current_language_lifecycle`. The run was stopped; it is **not** a pass.
- Isolated reproduction using the same test from the accepted L1 code/test SHA `1a2fb138dcf7ede875d8a3dcb033e5c6da8468fb` also timed out. `faulthandler` showed the main thread inside `tkinter.Tk.wait_window`, called by `src/localized_notice.py:132` from `src/b518_log_solution.py:585`, test `tests/test_log_solution_ui.py:342`, while opening the second notice. This confirms that the current blocker is reproducible without the L3 code; it does not by itself establish whether the cause is product lifecycle behavior, test behavior, or this desktop runtime. The ticket requires resolving/characterizing the dependency issue without folding an L1 fix into L3.

At that earlier checkpoint no complete full-suite result was available. No type-check configuration was found in the project; type checking is not claimed and no new type-check project was introduced.


## Standards / Spec and scope

Fixed diff: `git diff 93ac9e47903649c4098c1423c2496f86ac685a03...HEAD`. Parallel Standards and Spec code/test reviews at `04c2b0d…` both report **zero unresolved findings**; delivery-document re-review is recorded in the later delivery section. Standards confirms local changes, domain vocabulary, main-thread Tk and behavior tests. Spec confirms all L3 paths, immutable evidence/selection, failure/retry, lifecycle, close guards and scope. Native Menu.invoke and WM protocol limitations are explicitly separate from physical interaction claims.

No L1 dependency repair, general bus, per-window worker, cleanup-reason feature, KVM policy or bundle/field deployment is included. L2 remains intact. L4 owns parent-wide nine-scenario integration and all remaining legacy fanout cleanup. Parent scenarios 3, 5, 6–8 and the L3 portion of 9 have final evidence; scenarios 1–2/4 and parent-wide completeness remain L4 responsibilities. Cleanup-reason C1–C4 stays separate. Remote issues #28/#31 are not changed or closed.

## Commit, merge and destination history

Initial code/test commits: `c12f20526111dc2fabfe5a65c1ae4764eb729a97`, `6682c621751973d9ff16505699bf39822db62b58`, `48f14dca68894147cd1ba0afa43a8e9edc331145`. Initial evidence commits through `1e7660984268073aa01324e5e3a117e9889fec9d` recorded Partial truthfully at that checkpoint; current results supersede their completion status, not their failure observations.

Direct queries after 1e76609 confirmed both ticket refs there and both main refs at 93ac9e4. New verified code batches d3814f8, 4f672dc, 3f0031f and 04c2b0d were each committed and pushed to both destinations. Merge is pending final delivery-document review and latest main checks; no merge SHA is asserted yet. Later query/merge/mainline-validation results will be added without presenting historical queries as final HEAD.
