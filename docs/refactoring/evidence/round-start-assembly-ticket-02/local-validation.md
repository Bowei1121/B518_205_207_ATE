# R2 local validation

Date: 2026-10-08 (Asia/Taipei)

## Baseline and scope

- Repository: `B518-Log-Solution`; Python root: `B518 Log Solution/`.
- Fixed Standards/Spec review base: `b2816400415364bd033bd4f784bfebf3cda58b2b`.
- The working tree was clean on `B518-Log-Solution` at that base before work. The dedicated branch `RoundStartAssembly/ticket-02` did not exist locally or at either push destination. Live Gitea (`origin`) and GitHub default branch tips both matched the base at the initial check.
- R1 was present in the base by ancestry and its implementation/evidence: the public `RoundStartPreparation`/`PreparedRoundStart` contract, frozen profile, selected registry, source mapping, and Session/audit evidence were reused.
- This work moves the formal Tk start entry to that contract. It does not claim R3 removal of every obsolete private detail or full field-device acceptance. No remote issue was modified.

## Implementation evidence

`B518LogSolutionApp.start_monitor` now validates/fixes the selected profile and paths through `RoundStartPreparation`, then keeps the existing Tk responsibilities and order: show busy state, synchronously persist preferences, and hand the prepared request to `RoundCoordinator`. Tk no longer assembles callback holders, adapters, source-slot mappings, or Session/audit evidence. `RoundStartPathError` preserves the existing path-error dialog while distinguishing path failures from other profile errors. The original registry remains the source of profile choices.

The initial R2 implementation was committed as `6429a87`; the fixed review base remains the pre-R2 SHA above. Test-only commits added true-Tk regression and failure evidence. Post-merge full runs exposed synchronization gaps: a Tk test asserted rendered rows before the next event-loop delivery, a delayed close `stopped` event could overwrite a source-preparation failure, and teardown needed to wait for archive workers before removing temporary data. These were addressed by `9cd6b4e`, `20d3874`, `36cfc6e`, `c17e6dc`, `8289563`, and `88b4484`; latest validated code/test SHA is `88b448438564e55f0ef57457b05b855bb30ea67c`.

## R2 acceptance results

| # | Acceptance | Result and evidence |
| --- | --- | --- |
| 1 | Formal Tk entry uses public preparation; UI no longer assembles preparation internals; no old/new switch | **Pass.** `test_real_tk_start_button_prepares_every_registered_platform_profile`, `test_real_tk_shortcuts_start_rounds_with_session_and_audit_profile_evidence`; source review of `src/b518_log_solution.py` and `src/round_start_preparation.py`. |
| 2 | Preserve validation, frozen config, busy display, synchronous preference write, round acceptance, background source creation and readiness order | **Pass.** Real start button and shortcut tests plus R1 controlled preparation/stop/timeout tests; `PreparedRoundStart.start` hands off to the existing coordinator. |
| 3 | Config/path/preference failure accepts no round and retains existing messages and restoration | **Pass.** `test_empty_paths_are_rejected_before_monitor_creation` and `test_real_tk_preference_replace_failure_does_not_accept_round_or_leave_start_busy`; real Tk controls/message and preference file bytes checked. |
| 4 | All registered platforms start in Tk and persist consistent profile evidence in Session/audit | **Pass.** `test_real_tk_start_button_prepares_every_registered_platform_profile` covers Atlas DFU/FCT, B482 BT, RS-WMT BT and sample-json FCT. Real temporary source results and fresh Session/audit readers verify the same frozen profile; B482 mapped position/result is rendered in Tk. `test_app_completes_rswmt_final_only_round_through_shared_entry` also uses a real Tk App and disk evidence. |
| 5 | Button, local shortcut, global request delivered back through Tk queue | **Pass for controlled Tk handoff.** Button and local keyboard event are operated in Tk; the registered global callback is delivered through its actual Tk event-queue bridge. **OS-level global-hotkey hardware/field acceptance is not claimed.** |
| 6 | Background source failure preserves existing UI recovery and durable failed round; slow preparation counts toward deadline; stop/timeout does not restart | **Pass.** Existing R1 `Event`-controlled coordinator tests and actual Tk failure/close regression tests are included in the full suite; preparation remains on coordinator's existing accepted-round background path. |
| 7 | RUNNING repeat start preserves round/result; start is refused while close-save is active | **Pass.** `test_real_tk_start_button_prepares_every_registered_platform_profile` exercises repeated button/local/global requests while RUNNING and checks the active result/round. Existing true-Tk closing-save guard regression is part of the full suite. |
| 8 | AWAITING_REVIEW direct start and both shortcuts preserve distinct baseline side effects | **Pass.** `test_awaiting_review_start_entrypoints_preserve_their_existing_side_effects` drives a real Tk App and real coordinator into review; it separately operates direct start, local shortcut, and the global callback/Tk handoff, checking preference and round state for each. |
| 9 | Delayed old-round events cannot overwrite the new UI; close during preparation waits for source handoff and complete save | **Pass.** Existing true-Tk stale-round isolation and preparation-close/coordinator persistence regressions run in the complete suite. The true-Tk teardown waits through the public close status and requires `complete` before temporary data is removed. |
| 10 | Preserve parser/mapping, unknown-source FAIL, conflicts, product release and KVM | **Pass as regression coverage.** Existing platform, configured-monitor, round, conflict, result release and KVM tests are included in the complete suite; no policy or lifecycle implementation was changed. |
| 11 | Each migration has behavior evidence and existing tests pass; formal overall release remains R3 | **Pass for R2 scope.** Evidence is linked above and in the scenario matrix below. R3's old-path removal and overall release checklist remain outstanding. |

## Mother-spec 14 scenario groups

| # | Scenario | R2 evidence / classification |
| --- | --- | --- |
| 1 | Invalid config / unknown platform | R1 preparation and Tk baseline regressions; R2 uses the same public preparation validation. |
| 2 | Required path blank, absent, unreadable | R2 real-Tk blank-path rejection; R1 temporary-path validation tests cover unusable paths. |
| 3 | Optional path blank / invalid nonblank | R1 public-interface tests; R2 does not change the optional-path policy. |
| 4 | Preference persistence failure | New R2 real-Tk atomic-replace failure test verifies unchanged disk prefs, no round and restored UI. |
| 5 | Frozen config and dual Session/audit evidence | New R2 platform/shortcut true-Tk tests read both records from disk and compare frozen config evidence. |
| 6 | Normal start on all platforms | New R2 real-Tk start-button matrix covers Atlas DFU/FCT, B482 BT, RS-WMT BT and controlled sample-json FCT; actual platform adapters are exercised. |
| 7 | Slow source preparation | R1 controlled source/Event and injected-clock coordinator tests retained; accepted and ready times remain separate. |
| 8 | Background creation failure | R1 coordinator durable-failure case and R2 UI recovery regression retained. |
| 9 | Stop/deadline during preparation | R1 Event-controlled stop/timeout/late-source tests retained. |
| 10 | Repeated start while RUNNING | New R2 actual Tk button/local/global entry check preserves round and result. |
| 11 | Repeated start while AWAITING_REVIEW | New R2 actual Tk test separately verifies direct, local and global-to-Tk entry behavior and baseline side-effect differences. |
| 12 | Start during close-save / close during preparation | Existing Tk closing guard and coordinator preparation-close tests retained. The final true-Tk suite also waits for successful close completion before temporary-data cleanup. |
| 13 | Stale old-round events / unmapped sources | Existing round/Tk stale-event and configured-monitor unmapped-source regressions retained. |
| 14 | Save, archive and retention regression | Existing lifecycle, archival and retention tests retained; R2 changes only start composition. |

R1 evidence is inherited only where identified; the matrix does not claim the R2 branch independently reimplemented those behaviors. None of these controlled tests constitutes physical factory-device acceptance.

## Commands and results

Executed from the Python root `B518 Log Solution/`:

```text
B518_TK_TESTS=1 python3 scripts/run_tests.py test_round_start_preparation test_machine_profiles test_platform_registry test_configured_monitor test_monitoring_round test_log_solution_ui
Ran 136 tests in 42.435s — OK

B518_TK_TESTS=1 python3 scripts/run_tests.py test_log_solution_ui.LogSolutionUiTests.test_real_tk_preference_replace_failure_does_not_accept_round_or_leave_start_busy
Ran 1 test — OK

B518_TK_TESTS=1 python3 scripts/run_tests.py test_log_solution_ui.LogSolutionUiTests.test_real_tk_start_button_prepares_every_registered_platform_profile
Ran 1 test in 8.278s — OK

B518_TK_TESTS=1 python3 scripts/run_tests.py
Ran 289 tests in 65.224s — OK (accessible desktop session, before the final race fix)

B518_TK_TESTS=1 python3 scripts/run_tests.py test_round_start_preparation.RoundStartPreparationTests.test_source_creation_failure_through_preparation_is_audited_before_close_completes test_log_solution_ui.LogSolutionUiTests.test_app_completes_rswmt_final_only_round_through_shared_entry
Ran 2 tests in 6.883s — OK (after final race fix)

B518_TK_TESTS=1 python3 scripts/run_tests.py
Ran 289 tests in 59.525s — OK (final branch verification in accessible desktop session, including successful close assertion)

B518_TK_TESTS=1 python3 scripts/run_tests.py test_log_solution_ui.LogSolutionUiTests.test_sample_platform_conflicts_stay_consistent_through_real_tk_and_disk_rebuild
Ran 1 test in 3.830s — OK (final successful-close teardown assertion)

B518_TK_TESTS=1 python3 scripts/run_tests.py test_log_solution_ui.LogSolutionUiTests.test_running_round_keeps_its_capacity_and_mapping_after_profile_update test_log_solution_ui.LogSolutionUiTests.test_real_tk_shortcuts_start_rounds_with_session_and_audit_profile_evidence test_log_solution_ui.LogSolutionUiTests.test_real_tk_start_button_prepares_every_registered_platform_profile test_log_solution_ui.LogSolutionUiTests.test_app_completes_rswmt_final_only_round_through_shared_entry
Ran 4 tests in 17.229s — OK (archive-status synchronization before temporary-data cleanup)

B518_TK_TESTS=1 python3 scripts/run_tests.py test_log_solution_ui.LogSolutionUiTests.test_running_round_keeps_its_capacity_and_mapping_after_profile_update
Ran 1 test in 3.267s — OK (requires archived status before cleanup)

B518_TK_TESTS=1 python3 scripts/run_tests.py
Ran 289 tests in 69.410s — OK (final branch verification at `88b4484`, accessible desktop session)

python3 -m compileall -q src tests
OK (syntax/bytecode compilation only)

git diff --check
OK
```

The focused 136-test run preceded the two separately passing tests listed afterwards. The first complete 289-test run passed before the final race fix, then the post-merge run exposed the two issues described above. An Event-controlled regression made the source-failure/close ordering reproducible; the test failed against the old code with `manual_stop` and passed after the guard. The final complete run after both fixes passed 289 tests. The project has no configured mypy/pyright type-check command; no type-check pass is claimed. Final Tk tests used an accessible desktop graphical session; sandboxed Tk initialization attempts aborted before escalation and are not counted as product failures.

## Final review and delivery record

- Final complete Tk suite: **289 tests passed in 69.410s** at `88b448438564e55f0ef57457b05b855bb30ea67c`; the four archive-synchronized Tk cases passed in 17.229s and the final profile-update archive assertion passed in 3.267s.
- Fixed-base re-review through `88b4484`: Standards found no documented-standard violations. Assertions in `finally` may mask an earlier test failure if teardown also fails; this remains a non-blocking maintainability suggestion. Spec found no unresolved implementation or scope issues. Both reviews used `b2816400415364bd033bd4f784bfebf3cda58b2b`.
- Final validated code/test SHA: `88b448438564e55f0ef57457b05b855bb30ea67c`.
- Merge SHA: `a4e051a18aa263456f437af724d8f05ea40f2863`.
- Post-merge main-branch command `B518_TK_TESTS=1 python3 scripts/run_tests.py`: **289 tests passed in 68.912s** in the accessible desktop session. `python3 -m compileall -q src tests` and `git diff --check` also passed on the merged tree.
- The post-merge push was directly verified on Gitea and GitHub: both `B518-Log-Solution` refs were `002c12a16a6fa744f3224b8d305a4382414f2be2`, and both ticket refs were `853ae10a8749d8bf83da8cbd8ff4636b057b5a5c`. After confirming this synchronization, the local and both remote `RoundStartAssembly/ticket-02` branches were safely deleted. The final delivery-document push was then directly rechecked on both destinations; the working tree remained clean on `B518-Log-Solution`.

Any Tk test temporary directory is isolated. Existing production round data, exports and source logs were not used for failure injection or cleanup.
