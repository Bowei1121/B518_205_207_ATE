# L1 local validation — 2026-10-12

## Git baseline and dependency check

- Repository root: `/Users/tsengbowei/Desktop/公司資料/專案/FQ III/2026/B518/專案名稱/3. 程式/0. PC/B518 Log Solution`.
- Python project: `B518 Log Solution/`; tests were run from that directory.
- Branch: `LanguageRefresh/ticket-01`; fixed review baseline: `0eebc3200e854a27c979ab003e3e6eda0a36461f` (the B518-Log-Solution checkout before L1 changes). Current tested code/test SHA: `1a2fb138dcf7ede875d8a3dcb033e5c6da8468fb`.
- The worktree was created from the formal B518-Log-Solution branch. The main, B518-Log-Solution and BT-Codex worktrees are separate; pre-existing summary edits in the formal checkout were not included in this ticket branch.
- At the fixed baseline, the actual source contains the centralized English/zh-TW catalogue and persisted language preference (`src/language_catalog.py`, `src/machine_profiles.py`), the main language menu, bilingual App event storage, and the existing `<<AppLanguageChanged>>` notice path. M1 and later work are in the baseline ancestry. This L1 migrates only the main page and App-owned acknowledgement notices onto the existing notification contract; it does not claim all windows have migrated.
- Existing destinations were retained: `github` fetch/push is `git@github.com:Bowei1121/B518_205_207_ATE.git`; `origin` fetch is Gitea `http://10.64.76.34:3000/8362/B518-205_207_ATE.git`, and its two push URLs are that Gitea URL and the GitHub SSH URL. No destination was removed.
- The final ticket branch commit `7b853830fd19990b87ae6be93beebdee909ab0bf` was directly confirmed on GitHub and Gitea at `refs/heads/LanguageRefresh/ticket-01` after push. It contains tested code/test SHA `1a2fb138dcf7ede875d8a3dcb033e5c6da8468fb` plus the reviewed delivery documentation. Main integration and post-merge checks are recorded below.

## Producer and refresh inventory

| Entry / producer | Current behavior and L1 result | Persistence / boundary |
| --- | --- | --- |
| Mouse language button, keyboard language menu and queued `<<AppLanguageChanged>>` | `_select_language` updates the single App language, then uses the existing root event. Main page registers one receiver. Language-entry close guard is unchanged. | Preference save still uses the existing profile store; refresh failure is recorded separately. |
| Main-page `_apply_main_language` | Now runs as a registered receiver through the same notifier as App notices. A failure is isolated and does not prevent later receivers. | It only rerenders existing main-page widgets/status; it does not restart monitoring or persist an event as a side effect of refresh. |
| App-owned `_show_notice` acknowledgement Toplevel | Registers while open, renders with the latest App language, preserves text reading position and the existing modal acknowledgement/grab/Return/Escape/WM-close behavior, and unregisters in `finally`. Reopen constructs a notice in the current language. | The original captured bilingual App event/diagnostic remains the source when applicable. No extra operation event is emitted on refresh. |
| Failed receiver aggregate and manual retry | Main status row displays one nonblocking aggregate and exposes the existing detail and retry buttons. Retry dispatches only still-live failed receivers using the current App language. No automatic retry loop is added; recovered failures clear from current status while App diagnostics remain queryable. | Failure diagnostics use `app.language.refresh_failed`, fixed bilingual content, original receiver/error detail, App event identity/time/sequence and no `round_id`. Existing AppEventStore pending/retry semantics are used. |
| App diagnostic detail and retry | The main-page detail button opens existing App diagnostics. Selection displays event ID, message ID, parameters and original diagnostic; the App event retry remains available for persistence recovery. | L1 does not migrate settings, diagnostics or history windows to the language receiver registry; those remain L2. |
| Conflict/alarm/close windows | Existing refresh path and interaction semantics are untouched. | L3. Removal of legacy manual refresh fanout and full first-parent-item verification remain L4. Cleanup-reason tickets C1–C4 are untouched. |

## Ten L1 acceptance items

1. **Existing entry and notifier retained — pass.** The existing App language preference/menu and Tk virtual event are used. No general event bus or per-window worker was introduced. Evidence: `test_language_refresh_failure_keeps_other_receiver_and_offers_retry`, `test_real_tk_language_menu_switches_main_page_and_persists_across_app_instances`.
2. **Main page and App notices share refresh contract — pass.** Main page is a receiver; App notices register through the same notifier. Injected main-page failure still updates another receiver. Evidence: `test_language_refresh_failure_keeps_other_receiver_and_offers_retry`, `test_open_notice_receives_language_refresh_and_keeps_modal_acknowledgement`.
3. **Registration lifecycle — pass.** Notice receiver exists only for its live window, unregisters on acknowledgement/Escape/close through `finally`, and reopening uses current language. Destroyed receiver is safely discarded. A real notice is withdrawn, refreshed to the current language, then deiconified as the same Tk window. Evidence: `test_notice_escape_hidden_reopen_and_current_language_lifecycle`, `test_language_refresh_failure_keeps_other_receiver_and_offers_retry`.
4. **Failure isolation and operation state — pass.** Main and a second receiver can fail independently; other receiver refreshes, retry only targets unresolved live windows, and the App-owned notice retains its modal grab and acknowledgement semantics. Input/detail reading position is preserved by in-place rendering. Evidence: the two receiver failure test and modal refresh test above.
5. **Nonblocking aggregate and detail entry — pass.** The main status row identifies failed receivers and retains the detail and manual retry controls; no repeated modal is emitted. The real diagnostic window is opened from the main-page button and the failure event is selected to inspect its message ID and raw diagnostic. Evidence: `test_language_refresh_failure_keeps_other_receiver_and_offers_retry`.
6. **Manual recovery uses current language — pass.** Consecutive language changes followed by manual retry refresh the same surviving window using the latest App language. Recovery clears the current banner when all active failures resolve; historical diagnostics remain in the App journal. Evidence: `test_language_refresh_failure_keeps_other_receiver_and_offers_retry`, `test_notice_escape_hidden_reopen_and_current_language_lifecycle`.
7. **Bilingual persisted diagnostic and recovery — pass.** A real Tk test injects App journal atomic-write failure, confirms failure remains visible/pending, retries through the App diagnostic control, and rebuilds the event using a new disk reader. Bilingual message, ID, diagnostic and sequence are retained; event has no `round_id`. Evidence: `test_language_refresh_diagnostic_store_failure_is_visible_and_retryable`.
8. **Preference and close policies — pass.** Existing language preference save failure remains distinct from refresh failure; current language behavior and close-save language-entry guard are covered by existing real-Tk preference and close tests. Refresh/retry does not bypass close protection. Evidence: `test_real_tk_preference_replace_failure_does_not_accept_round_or_leave_start_busy`, `test_visible_language_write_error_refresh_keeps_original_preferences`, and close tests in `test_log_solution_ui` / `test_m10_integration`.
9. **True Tk lifecycle, menu entry, retry and disk diagnostic — pass with stated input scope.** New cases operate actual widgets and a real Tk list selection/detail view; notice cancellation uses a real Escape key event, verifies modal grab release, and reopens in the current language. Existing real-Tk preference/menu and close-protection tests are included in the complete run. Menu entry activation was tested through the actual language button and Tk menu command; this is not claimed as a separate native macOS menu mouse-navigation test. The modal fixture also verifies focus target liveness and relies on the existing `show_notice` focus restoration in `finally`; it does not assert the platform's post-close focus query in this multi-root Tk harness.
10. **Single L1 refresh path and deferred windows — pass.** Main and owned notices use the notifier registry once; settings, diagnostics, history, conflict, alarm and close retain their pre-existing refresh paths pending L2/L3. L1 does not claim all-window migration or L4's legacy fanout removal. Evidence: `test_integrated_language_refresh_keeps_open_settings_diagnostics_and_history` and the L1 producer inventory above.

## Test commands and results

Focused true-Tk acceptance after the final test fixture cleanup:

```text
B518_TK_TESTS=1 PYTHONPATH=src python3 -X faulthandler scripts/run_tests.py test_log_solution_ui.LogSolutionUiTests.test_notice_escape_hidden_reopen_and_current_language_lifecycle test_monitoring_round.MonitoringRoundTests.test_close_waits_for_source_preparation_and_restarts_after_cancel
Ran 2 tests ... OK
```

The full required test suite passed on the installed Python 3.11.7/Tk 8.6 runtime (PATH selected `/opt/anaconda3/bin/python3`):

```text
B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py
Ran 378 tests in 133.706s
OK
```

The host-default Python 3.8.10/Tk 8.6 run aborts with `Tcl_AsyncDelete: async handler deleted by the wrong thread` while starting a close worker in `test_close_recovers_a_failed_previous_round_and_current_round_without_crossing_events` (one attempt reached the next close-worker test before aborting). The same abort was reproduced by running the full suite from an isolated archive of the fixed pre-L1 baseline `0eebc3200e854a27c979ab003e3e6eda0a36461f`, at the same UI-to-worker test transition. Therefore it is recorded as a baseline Python 3.8/Tk runtime-suite limitation, not as a passing 3.8 result or an L1 regression. The passing full run is the 3.11.7 run above.

`git diff --check` passed. No existing type-check configuration was found; type checking is not claimed, and no type-check project was added.

## Review and parent-spec coverage

- Fixed review base for Standards and Spec: `0eebc3200e854a27c979ab003e3e6eda0a36461f`.
- Standards review: no blocking issue; one low-priority maintainability note about positional tuples in the notifier state. No code-style blocker.
- Spec review: no remaining blocking L1 gap after the new true-Tk diagnostic selection and notice cancel/reopen coverage. Non-blocking note: the Tk harness verifies the captured focus widget remains alive, but cannot reliably assert that Tk reports it focused after modal return; production `show_notice` still restores the prior live focus widget in `finally`.
- Relevant parent-spec first-item evidence is partial: main page + App-owned notices, receiver failure isolation, aggregate, manual retry and diagnostic. This does not satisfy the parent-wide first item. Settings/diagnostics/history are L2, conflict/alarm/close are L3, and old refresh fanout removal/full first-item verification is L4.
- Applicable parent scenarios: first-item cases for main/notice refresh, failure isolation and retry have evidence above; the general bilingual diagnostic/storage contract is also exercised. Other-window refresh cases and all-window integration remain unverified here. No parent-wide checkbox is claimed by L1.

## Commits and remaining scope

Implementation/test commits on this branch:

- `8095335` — isolate and recover language refresh failures.
- `d1dd1da` — cover partial language refresh recovery.
- `844099b` — verify bilingual diagnostic retry after disk failure.
- `428d45c` — release notifier after Tk teardown.
- `51df106` — release registry references when App root is destroyed.
- `16b68a3` — verify diagnostic selection and notice lifecycle.
- `69b890b` — coordinate notice fixture shutdown.
- `1a2fb13` — cover hidden notice language refresh.

Full commit IDs are available in branch history. Latest tested program/test SHA: `1a2fb138dcf7ede875d8a3dcb033e5c6da8468fb`. The evidence, ticket, README and summary updates were committed as `7b853830fd19990b87ae6be93beebdee909ab0bf`. L1 does not include L2–L4, C1–C4, generalized event infrastructure, source-identity work, journal optimization, or bundle/factory acceptance.

## Main-branch integration and post-merge verification

- The formal `B518-Log-Solution` worktree was clean for integration after the two pre-existing user-edited project summaries were stashed by path. They were restored after the merge validation; they are not part of the L1 commits.
- Merge commit: `106da01a6fadf1a0b539f882726762c25c66e839` (`merge: deliver language refresh L1`). The target and both direct destination refs were `0eebc3200e854a27c979ab003e3e6eda0a36461f` immediately before merge.
- On the merged main branch, `PATH=/opt/anaconda3/bin:$PATH B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py` passed: 378 tests in 152.355 seconds, Python 3.11.7 / Tk 8.6.
- After pushing the merge commit, direct `git ls-remote` queries returned `106da01a6fadf1a0b539f882726762c25c66e839` for `refs/heads/B518-Log-Solution` on both GitHub and Gitea. At the same query, the ticket branch still existed at `7b853830fd19990b87ae6be93beebdee909ab0bf` on both. The later final documentation-only commit and its direct destination checks are reported in the delivery response; no force push or destination removal was used.
