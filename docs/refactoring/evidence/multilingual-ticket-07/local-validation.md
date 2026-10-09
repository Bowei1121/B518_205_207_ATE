# M7 local validation: save and close language coordination

## Baseline and dependency

- M7 fixed review baseline: `45df1e36895cdb8bbb313de0a4c038cdeef13ac4` (`B518-Log-Solution` before M7 changes). The official Python project is `B518 Log Solution/` inside the Git root.
- The working tree was clean at the start. Local and GitHub `Multilingual/ticket-07` did not exist, so the ticket branch was created from the verified mainline. The local mainline and directly queried GitHub `B518-Log-Solution` were both `45df1e36895cdb8bbb313de0a4c038cdeef13ac4`.
- M4 dependency is included by Git ancestry: `f7e24cd265fc173d5d113e7fb122083602f5e5fa` is an ancestor of the M7 baseline. Its [local validation](../multilingual-ticket-04/local-validation.md) documents versioned no-round bilingual App events, public status/retry, disk reconstruction, failure recovery, and close coordination across App and rounds. M1–M6 are present in the M7 baseline; their feature-specific regressions were rerun in the complete suite.
- The M7 baseline does not inherit M4 or M6 review baselines. Standards/Spec review for this ticket is recorded separately below after completion.

## Producer and UI scope

M7 updates the existing main language entry and App-owned close/save progress dialog. The dialog presents its localized title and saving/waiting/failed state, an explicit localized explanation that language changes are unavailable while close-and-save remains active, the existing retry and cancel actions, and the original failure detail under a localized diagnostic label. The App Diagnostics window continues to refresh its existing status, selected record and detail in place through the M4 public display path.

The close/save producer remains the existing `RoundCoordinator` close request/status/retry/cancel contract. This ticket does not add a second save queue or event format. The retry and cancel actions have stable shared resource IDs; the real controls render English or Traditional Chinese. Raw coordinator/storage error text remains diagnostic data; it is shown intact after the localized outer explanation. Language selection does not create an App event or save job. Close cancellation invalidates only the close attempt and leaves existing save work intact; no source is restarted.

## M7 acceptance and evidence

| Criterion | Evidence and result |
| --- | --- |
| 1. Bilingual save state, failure, original diagnostic, retry and close operation | `tests/test_log_solution_ui.py`: `test_close_failure_keeps_window_open_and_real_retry_rebuilds_complete_audit`, `test_real_tk_close_keeps_app_write_failure_open_and_retries_it`, and `test_real_tk_app_diagnostic_is_bilingual_inspectable_and_saved_before_close`. Real Tk shows localized state/retry controls and retains the raw storage diagnostic. **Pass.** |
| 2. Open App save/diagnostic view refreshes normally; language is blocked during close/save with localized reason | Existing `test_real_tk_app_diagnostic_is_bilingual_inspectable_and_saved_before_close` and the M7 close-wait/failure tests. During saving, the button and menu entries are disabled, an already queued/direct selection is rejected, the menu is unposted, and the current-language reason is visible. **Pass.** |
| 3. Cancel restores language entry and necessary resources without discarding saves or restarting stopped sources | `test_close_waits_responsively_and_cancellation_invalidates_old_completion`: Event-controlled audit write keeps Tk responsive; cancellation leaves the hotkey/root alive, restores language entry, preserves save work and confirms source start count remains one. A subsequent close uses the newly selected language. **Pass.** |
| 4. Retry is non-reentrant; recovery is complete and prior errors do not permanently block close, including App events | `test_close_failure_keeps_window_open_and_real_retry_rebuilds_complete_audit` issues repeated retry requests under an Event-controlled write, cancels and retries in the other language, then verifies complete audit reconstruction for the old and current rounds with one stop event and recovery records. Existing M4 tests cover a no-round App event save failure included in close and retried to completion. **Pass.** |
| 5. Real Tk waiting/failure/retry/cancel/reclose and disk results | The three M7 real Tk tests above exercise visible waiting/failure/retry/cancel states in both English and Traditional Chinese, language-entry lockout, kept-open behavior, reclose and final destroy. Fresh audit readers verify complete bilingual operation events and round results. **Pass.** |

The added M7 tests use actual Tk widgets and the desktop graphical session. The ordinary sandboxed Tk run aborted with exit 134 during window setup before assertions; the focused tests and complete suite were then run with authorized desktop-session access and passed. This was an environment access issue, not reported as a product failure.

## Verification

- Red phase: the new real Tk assertions failed before implementation because the language button remained `normal`, `_select_language()` accepted a language change during close/save, and close language control had no localized disabled reason.
- Green phase: focused command from `B518 Log Solution/`:
  `B518_TK_TESTS=1 PYTHONPATH=src:tests python3 -m unittest -v test_log_solution_ui.LogSolutionUiTests.test_close_waits_responsively_and_cancellation_invalidates_old_completion test_log_solution_ui.LogSolutionUiTests.test_close_failure_keeps_window_open_and_real_retry_rebuilds_complete_audit test_log_solution_ui.LogSolutionUiTests.test_real_tk_close_keeps_conflict_and_alarm_actions_available` — **3 passed**.
- Review found the retry and cancel captions were still hard-coded Traditional Chinese. Added `app.close.retry` and `app.close.cancel` to the shared English/Traditional Chinese catalog, retained the actual controls, and added real Tk assertions. The revised focused tests passed (**3 tests**).
- Spec follow-up identified that the first test only called the language selection entry point directly. The test now also schedules `root.after(0, ...)` during close/save, pumps the Tk event loop, and confirms the queued callback runs without changing language, selected choice, or App-event revision. Focused real-Tk test passed.
- Complete suite after that correction from `B518 Log Solution/`:
  `B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py` — **335 tests passed** in 86.356 seconds, including the real Tk suite. One earlier run encountered a transient `TemporaryDirectory` cleanup race in an existing detached-round archival test; that test passed five consecutive isolated runs, and this complete rerun passed.
- `python3 -m compileall -q src tests` and `git diff --check` — passed.
- No project type-check configuration was found; no type-check pass is claimed.
- Program/test commits: `fb0598736bc83c9faa8ef1c3695554f2aefb1257` and `098d8cbebdf266d11fc5255eafd47c9971336487`. The queued-request test and its passing full-suite result are in test-bearing commit `db1535259f64d68206b0a0badedf6d862dcedabf`.
- Review baseline: `45df1e36895cdb8bbb313de0a4c038cdeef13ac4`. Final Standards and Spec follow-up reviews found no actionable findings. The original Spec evidence gap was closed by the queued Tk event test above.

## Remote delivery

- After pushing the test-bearing commit, direct `git ls-remote github refs/heads/B518-Log-Solution refs/heads/Multilingual/ticket-07` returned mainline `45df1e36895cdb8bbb313de0a4c038cdeef13ac4` and ticket branch `db1535259f64d68206b0a0badedf6d862dcedabf`. The final documentation commit is pushed and directly queried after this snapshot; see final delivery report for that latest SHA.
- The configured `origin` push URLs include internal Gitea `http://10.64.76.34:3000/8362/B518-205_207_ATE.git` and the same GitHub repository. Direct Gitea queries failed/refused to connect or did not return; a push through `origin` did not respond and was interrupted after no progress. Gitea synchronization is unconfirmed and is not claimed. No push destination was removed.
- Since a configured push destination is unavailable, M7 is not merged and neither the local nor GitHub ticket branch is deleted. No remote Issue status was changed.

## Scope boundary

M7 does not change M4's App/round persistence format, retry coordinator, source handoff, close-generation isolation, archive or cleanup lifecycle. M8 historical message recognition, M9 App-event expiry cleanup, and M10 bundle/release verification remain pending.
