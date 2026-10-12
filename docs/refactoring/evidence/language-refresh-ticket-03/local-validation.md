# L3 local validation — 2026-10-12

## Result

**Partial; not merge-ready.** The conflict/alarm implementation and focused real-Tk tests are committed on `LanguageRefresh/ticket-03`. The required full suite did not complete, an L1 lifecycle test timed out on L1's own recorded tested SHA in this environment, and one long wrapped-detail reading-position case is still missing. No L1 repair is included. Keep this branch and worktree; do not merge or delete either until the dependency and required-validation gates are resolved.

## Git baseline and direct dependency

- Repository root: `/Users/tsengbowei/Desktop/公司資料/專案/FQ III/2026/B518/專案名稱/3. 程式/0. PC/B518 Log Solution`.
- Python project and test cwd: `B518 Log Solution/` beneath the repository root.
- L3 worktree: `/private/tmp/B518-LanguageRefresh-ticket-03`; branch: `LanguageRefresh/ticket-03`.
- L3 fixed Standards/Spec review base: `93ac9e47903649c4098c1423c2496f86ac685a03` (captured before L3 edits; `git merge-base` remains this SHA).
- Final code/test SHA in this validation: `48f14dca68894147cd1ba0afa43a8e9edc331145`.
- Commits: `c12f20526111dc2fabfe5a65c1ae4764eb729a97` (receiver integration); `6682c621751973d9ff16505699bf39822db62b58` (receiver lifecycle); `48f14dca68894147cd1ba0afa43a8e9edc331145` (single language refresh path).
- The L1 dependency commit `7b853830fd19990b87ae6be93beebdee909ab0bf` is an ancestor of the fixed L3 base. L2 is also already in the base. The L1 evidence claims the modal notice lifecycle case passed earlier and the full L1 suite passed on Python 3.11.7/Tk 8.6; these historical results do not establish a pass in the current run.
- Existing worktrees at the start were preserved. The formal `B518-Log-Solution` worktree contains the user's pre-existing changes to `docs/refactoring/PROJECT_SUMMARY_2026-10-09.md` and `PROJECT_SUMMARY_2026-10-12.md`; L3 work was isolated and those edits were not staged or included.
- Existing remotes were retained: `origin` fetches from Gitea (`http://10.64.76.34:3000/8362/B518-205_207_ATE.git`) and has Gitea plus GitHub push URLs; `github` points to `git@github.com:Bowei1121/B518_205_207_ATE.git`.
- Earlier push commands reported `48f14dca…` pushed to both destinations. Direct queries first failed in the sandbox (Gitea unreachable; GitHub DNS unavailable). After the documentation commit and explicit network access, direct `git ls-remote` on 2026-10-12 confirmed GitHub and Gitea `refs/heads/LanguageRefresh/ticket-03` both at `8e8e6a6b06ef6b880dc74cbdaa9731222ce7f67e`; both `refs/heads/B518-Log-Solution` were `93ac9e47903649c4098c1423c2496f86ac685a03`. The final evidence-only commit still requires its own push and direct SHA query.

## Window and refresh inventory

| Entry | L3 behavior after changes | Normal data/operation behavior retained |
| --- | --- | --- |
| Main language control and L1 notifier | Remains the sole current-language source. Conflict and round-alarm views register their own live receiver and use the current language on notification/retry. | Existing preference save, close-time language guard, aggregate failure, diagnosis and retry remain L1 responsibilities. |
| Conflict review | In-place title, controls, list, position, four-column comparison and detailed snapshot render. Receiver unregisters on actual destroy; withdraw remains hidden. | Round polling refreshes conflict data only when captured conflict identities/data change. Candidate updates, selection by `conflict_id`, resolution and audit remain coordinator operations. |
| Round alarm | In-place title/body/button render for the current alarm/readiness. Does not reopen, raise, acknowledge or change identity on language notification. Unregisters on destroy; withdraw remains hidden. | New alarm/readiness changes still render through the normal round/alarm path; acknowledgment remains the existing single operation. |
| Close progress | Uses the existing App language for progress and status. It is not made a language receiver that would permit changing language during close. | Existing close generation, retry, cancel, stale completion guard and complete-save-before-destroy coordination remain unchanged. |
| Main-page legacy refresh calls | The conflict/alarm manual language fanout is removed. | Main refresh still updates its own controls; ordinary event/round changes still render conflict/alarm data. L4 owns all remaining legacy-path cleanup and parent-wide acceptance. |

## Focused true-Tk validation

Interpreter: `/opt/anaconda3/bin/python3.11`, Python 3.11.7, Tcl/Tk 8.6. Tests were run with desktop access from `B518 Log Solution/` using:

```text
B518_TK_TESTS=1 PYTHONPATH=src /opt/anaconda3/bin/python3.11 scripts/run_tests.py \
  test_log_solution_ui.LogSolutionUiTests.test_conflict_and_alarm_refresh_fail_independently_and_retry_latest_language \
  test_log_solution_ui.LogSolutionUiTests.test_real_tk_close_keeps_conflict_and_alarm_actions_available \
  test_log_solution_ui.LogSolutionUiTests.test_conflict_review_tracks_same_slot_candidates_through_refresh_resolution_and_reopen \
  test_log_solution_ui.LogSolutionUiTests.test_real_tk_timeout_event_language_refresh_preserves_round_and_audit \
  test_log_solution_ui.LogSolutionUiTests.test_real_tk_conflict_selection_keeps_both_sections_on_same_snapshot
```

Result: **5 tests passed in 4.870 seconds** on 2026-10-12. These use actual Tk widgets and a public `RoundCoordinator` path with an isolated controlled FCT source. The new main test injects each conflict/alarm refresh failure in turn, confirms the other receiver continues, exercises the main-page banner and manual retry after consecutive language changes, verifies the same windows and conflict selection remain, confirms alarm identity is still pending, confirms audit bytes do not change during language refresh, reads the appended fixed bilingual App diagnostic, exercises close-time language rejection, then resolves the conflict and acknowledges the alarm once each and rebuilds the audit from disk. Separate focused tests cover candidate refresh/resolution/reopen, same-snapshot comparison, timeout/alarm rendering and close action availability.

A sandboxed Tk initialization attempt aborted inside macOS AppKit before any test ran (`NSInternalInconsistencyException`, `NSMenuItem initWithTitle:action:keyEquivalent:`); rerunning with desktop access succeeded for the five focused cases. Do not count the sandbox attempt as a product failure or a pass.

## Required full suite and dependency blocker

Required command from the Python project directory:

```text
B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py
```

- Host-default Python 3.8.10 / Tk 8.6: Tk class setup aborted in native initialization (exit 134); no complete suite result.
- Python 3.11.7 / Tk 8.6 with desktop access: the run advanced through preceding tests but stalled for over two minutes at `test_notice_escape_hidden_reopen_and_current_language_lifecycle`. The run was stopped; it is **not** a pass.
- Isolated reproduction using the same test from the accepted L1 code/test SHA `1a2fb138dcf7ede875d8a3dcb033e5c6da8468fb` also timed out. `faulthandler` showed the main thread inside `tkinter.Tk.wait_window`, called by `src/localized_notice.py:132` from `src/b518_log_solution.py:585`, test `tests/test_log_solution_ui.py:342`, while opening the second notice. This confirms that the current blocker is reproducible without the L3 code; it does not by itself establish whether the cause is product lifecycle behavior, test behavior, or this desktop runtime. The ticket requires resolving/characterizing the dependency issue without folding an L1 fix into L3.

No complete full-suite result is claimed. No type-check configuration was found in the project; type checking is not claimed and no new type-check project was introduced.

## L3 acceptance status

| # | Acceptance | Status and evidence |
| --- | --- | --- |
| 1 | Conflict/alarm notification and close-language basis; no close-time retry/switch bypass | **Partial.** Five focused true-Tk cases prove conflict/alarm notifications and close-time refusal. Full close/save regression is not revalidated because the required suite is blocked. |
| 2 | Candidate set/selection, details, comparison/style and same window retained | **Partial.** Focused tests verify same `conflict_id`, captured detail, comparison, same window and ordinary candidate changes. Long wrapped-detail reading-anchor behavior has not been verified; the logical-line/fraction restoration has this evidence limitation. |
| 3 | Refresh never acknowledges alarm, resolves candidate, changes results/KVM; other positions continue | **Partial.** Tests verify the alarm remains pending and the conflict remains unresolved until the explicit action. Full multi-position/KVM regression remains unverified in this run. |
| 4 | Open/hide/show/destroy/reopen receiver lifecycle and focus/effects | **Partial.** Focused test covers hide/reopen and external destroy/recreate while retaining pending state. Physical title-bar input and the full repeated lifecycle matrix are not claimed. |
| 5 | Injected operation-window failures are isolated; manual retry uses same live window | **Pass for tested conflict/alarm paths.** Both directions were injected; the other window updated, aggregate stayed available, and manual retry refreshed the same instance using the latest language. |
| 6 | Refresh preserves unsaved tracking/save retry/close generation/full-save-before-close | **Partial.** The new test confirms close-time language rejection and preserves pending diagnostic/audit state. Complete save/retry/generation races depend on the blocked full regression suite. |
| 7 | True Tk/public round path: monitoring/review, candidate/alarm, recovery, close guard, disk result | **Partial.** Real Tk/public coordinator/controlled FCT/disk audit path passed for timeout, conflict, retry, close guard and reconstruction. The full matrix and clean required suite remain incomplete. |
| 8 | Remove duplicate L3 language fanout while keeping round/save rendering | **Partial.** Focused regression proves a failed language receiver stays stale until manual retry while normal conflict/alarm data changes still render. Full round/save suite was not completed. |

## Review and scope

- Fixed review base: `93ac9e47903649c4098c1423c2496f86ac685a03`; final code/test SHA reviewed: `48f14dca68894147cd1ba0afa43a8e9edc331145`.
- Standards review: no blocking findings; `git diff --check` clean.
- Spec review: no scope creep or code-level gap found after this evidence was added. The earlier missing-evidence blocker is resolved. The required full-suite/L1 modal timeout and missing long wrapped-detail reading-anchor evidence remain explicit acceptance blockers; acceptance #2 is partial. The reviewer also noted that opening the real menu and then using `Menu.invoke` does not prove native menu navigation; no such claim is made here.
- No updates were made to the L1 implementation, cleanup-reason C1–C4, general event infrastructure, per-window workers, KVM policy, or product behavior outside L3.
- L2 is already in the fixed base. L4 still owns complete removal of legacy fanout and the parent first-item nine-scenario acceptance. Cleanup-reason tickets C1–C4 and release/bundle acceptance remain separate.
- Parent first-item scenarios supported by this L3 evidence: conflict/alarm selection and pending state under language refresh (partial scenario 3); hidden/reopen lifecycle (partial scenario 5); individual conflict/alarm failure isolation and retry (scenarios 6–8, limited to these windows). Scenarios 1–2, 4, 9 and parent-wide completeness are not claimed passed here.

## Commits, merge and remotes

- Code/test commits: `c12f20526111dc2fabfe5a65c1ae4764eb729a97`, `6682c621751973d9ff16505699bf39822db62b58`, `48f14dca68894147cd1ba0afa43a8e9edc331145`.
- This validation does not merge L3. There is no merge SHA.
- Earlier per-batch push commands reported the ticket branch pushed to GitHub and Gitea at `48f14dca…`; the latest direct query attempted on 2026-10-12 could not reach either host, so remote equality is not currently verified. The branch and worktree must remain until direct checks, full validation and review are complete.
- This document is an evidence update, not a claim that L3 is complete. The evidence commit `8e8e6a6…` is directly confirmed on both remotes as stated above. The subsequent evidence-only commit SHA and its post-push direct query are reported separately in the final delivery status.
