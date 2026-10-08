# R3 local validation

Date: 2026-10-08 (Asia/Taipei)

## Baseline and scope

- Git root: `B518-Log-Solution`; Python source and test root: `B518 Log Solution/`.
- Dedicated branch: `RoundStartAssembly/ticket-03`.
- Fixed Standards/Spec review base: `0fbbd01ddb627bdd9bdee413ca6d3dfc2ae23fc8`.
- Before edits the working tree was clean on `B518-Log-Solution`. A fresh fetch confirmed Gitea (`origin`) and GitHub (`github`) both had `B518-Log-Solution` at the same SHA as the local branch. Neither local nor remote had `RoundStartAssembly/ticket-03`.
- `git merge-base --is-ancestor` confirmed R1 merge `90e7c276f3ae28167f75d50a11b78cb973a061aa` and R2 merge `a4e051a18aa263456f437af724d8f05ea40f2863` are ancestors of the fixed base. The R1/R2 implementation and their validation records were read and checked against current code.
- The current branch uses one formal start preparation flow. R2 had already moved the Tk start action to `RoundStartPreparation`; R3 removed the fallback that constructed a second preparation object and inferred a default Session path when a partially initialized App was used. The normal App constructor owns both values.
- No platform parser, config format, schema, start-state policy, or save/close/archive/retention lifecycle was changed. No remote issue was read or modified.

## Caller and test inventory

| Responsibility or test detail | Decision | Evidence |
| --- | --- | --- |
| `RoundStartPreparation` validation, immutable profile capture, adapter creation, callback bridge, source/display mapping, and Session/audit config assembly | Keep as the sole formal start preparation path | `B518 Log Solution/src/round_start_preparation.py`; App `start_monitor`; public preparation, adapter, mapping, Tk, and disk tests below |
| `validate_profile`, profile editor validation, import/export and profile catalog checks | Keep; these still serve configuration management | `machine_profiles.py` call sites; true-Tk profile edit/import/export tests; `test_machine_profiles` |
| `PlatformRegistry` creation and `ConfiguredMonitor` mapping | Keep; these own platform creation and bidirectional mapping | Existing registry and mapping tests, including the real platform Tk matrix and unmapped-source test |
| `start_monitor` fallback using `getattr` to create another preparation object/default Session path | Remove; call-site search showed only incomplete `object.__new__` test fixtures depended on it | App constructor initializes both fields; all formal starts pass through the constructed App and its preparation interface |
| `install_test_profile` and mock-only “existing monitors start through shared entry” case | Remove as superseded by real Tk coverage for every registered platform | `test_real_tk_start_button_prepares_every_registered_platform_profile` |
| Mock-only repeated App start case | Remove as superseded by the real Tk button/local/global start checks while RUNNING | Same real Tk all-platform case; coordinator `test_repeated_start_while_running_keeps_the_same_round` |
| Previous-round UI event isolation case that called a private handler on an incomplete App | Replace with a real Tk App, two temporary rounds, a queued prior-round event, rendered-row assertions, and successful public archive status before cleanup | `test_queued_prior_round_event_cannot_change_the_new_round_ui` |
| Persisted project/machine selection case that asserted mock factory arguments | Replace with actual B482 BT source startup and fresh Session/audit readers | `test_operator_selects_project_and_machine_and_choice_survives_restart` |

The remaining unit tests that exercise event rendering helpers are supplementary checks for their event-specific behavior; the start-path, platform, cross-round UI, and persistent configuration acceptance above goes through the agreed public preparation, coordinator, real App/Tk, and disk-reader seams.

## R3 acceptance results

| # | Acceptance | Result and evidence |
| --- | --- | --- |
| 1 | One formal preparation rule; remove only uncalled old assembly and keep configuration-management capabilities | **Pass.** `start_monitor` uses its constructor-owned `RoundStartPreparation` and `session_root`. The normal Tk start, four registered production platforms plus controlled sample platform, and public preparation tests pass. Profile validation remains used by profile editing/catalog operations. |
| 2 | Remove obsolete private setup/mock details while retaining useful behavior | **Pass.** Removed three incomplete-App/mock start cases and their profile fixture. Their useful platform and RUNNING behavior is covered by real Tk and RoundCoordinator tests; prior-round isolation is now a two-round real Tk test. Profile restart coverage now checks actual Session/audit files. |
| 3 | No parallel or permanent compatibility start path; config parameters remain independently changeable and new source formats ship with the App | **Pass.** Static call-site review shows one App start preparation call. Existing editor/import/export tests and registered parser tests pass. No alternate start switch or parser loading path was added. |
| 4 | All 14 mother-spec program/desktop groups have current evidence | **Pass.** Each group is mapped in the mother-spec R3 coverage table below and in this record. All required cases were run in the final full Tk suite at `8f9b293`; per-group limitations are called out. |
| 5 | Atlas DFU/FCT, B482 BT, RS-WMT BT, and sample-json FCT regress | **Pass.** `test_real_tk_start_button_prepares_every_registered_platform_profile` creates real temporary sources and drives the actual Tk start button for all four; Session and audit are read back from disk. Atlas DFU/FCT, B482 and RS-WMT use their registered adapters; sample-json is controlled input and does not substitute for parser or equipment testing. |
| 6 | Preparation timing, stop/timeout, creation failure, preference failure, start guards and stale event isolation remain correct | **Pass.** R1 controlled Event/clock tests, R2 true-Tk preference and AWAITING_REVIEW tests, plus the new real Tk two-round stale-event test pass in the complete suite. |
| 7 | Save tracking/retry, complete-save-before-close, archival and retention safety regress | **Pass.** The full suite includes public coordinator save/retry/close/archive/retention tests and real Tk retry/close tests; no lifecycle implementation was modified. |
| 8 | Necessary project checks and current desktop validation are recorded | **Pass.** Full Tk suite, compileall, and diff check passed on the final code/test commit. The project has no configured mypy, pyright, or other type-check command; none is claimed. |
| 9 | A usable field acceptance checklist is delivered | **Pass.** See [field acceptance checklist](field-acceptance-checklist.md). It records device, OS, App/configuration, operator/date, operation, result, and evidence fields. |
| 10 | Field acceptance remains a separate stage; code delivery does not claim physical equipment acceptance | **Pass with field work pending.** No factory equipment or production source was used. The checklist remains unfilled and explicitly awaits scheduled engineering acceptance. |
| 11 | AWAITING_REVIEW no-side-effect change and multilingual work remain separate; parent issue is untouched | **Pass.** The three-entry-point true-Tk baseline test remains. No start-entry policy or multilingual behavior changed, and no issue tracker operation occurred. |

## Mother-spec 14 scenario coverage

The full command below was run at final code/test SHA `8f9b293ec7c90595c4bcd443daabf26e72049f0b`. Each scenario group has an identifiable test entry; the full-suite run confirms the integrated version, while the focused run results are listed later.

| # | Scenario | Test entry and evidence | Result / limit |
| --- | --- | --- | --- |
| 1 | Invalid config / unknown platform | `test_invalid_profile_matrix_is_rejected`; `test_unknown_platform_remains_rejected_after_registration`; true-Tk error path in `test_empty_paths_are_rejected_before_monitor_creation` | Pass; no new round or adapter on invalid input |
| 2 | Required path blank, missing, non-directory, unreadable/unenterable | `test_required_paths_must_be_present_directories_readable_and_enterable`; `test_empty_paths_are_rejected_before_monitor_creation` | Pass with real temporary paths and Tk dialog |
| 3 | Optional path blank vs invalid nonblank | `test_blank_optional_path_is_omitted_but_invalid_nonblank_path_is_rejected` | Pass through public preparation API |
| 4 | Preference write/atomic replace failure | `test_real_tk_preference_replace_failure_does_not_accept_round_or_leave_start_busy` | Pass; actual preference bytes, UI controls, message and absent round checked |
| 5 | Frozen config and dual durable Session/audit evidence | `test_prepared_profile_starts_real_round_and_persists_matching_session_and_audit`; `test_real_tk_start_button_prepares_every_registered_platform_profile`; `test_operator_selects_project_and_machine_and_choice_survives_restart` | Pass; new readers rebuild both records from temporary disk |
| 6 | Normal start on all platforms | `test_real_tk_start_button_prepares_every_registered_platform_profile`; `test_app_completes_rswmt_final_only_round_through_shared_entry` | Pass for Atlas DFU/FCT, B482 BT, RS-WMT BT and controlled sample-json. The sample adapter does not stand in for physical equipment. |
| 7 | Slow preparation and accepted/ready time separation | `test_source_preparation_time_counts_from_the_accepted_start`; `test_injected_round_deadline_during_preparation_stops_late_source_before_ready` | Pass using controlled preparation and injected clock |
| 8 | Background creation failure and durable failed round | `test_source_creation_failure_through_preparation_is_audited_before_close_completes`; `test_monitor_creation_error_is_visible_and_returns_to_standby` | Pass; failure event and audit are retained |
| 9 | Stop/timeout during preparation and late source | `test_stopping_while_source_is_preparing_keeps_round_stopped_after_factory_returns`; `test_injected_round_deadline_during_preparation_stops_late_source_before_ready` | Pass with Event-controlled factory and injected time |
| 10 | RUNNING repeat start | `test_real_tk_start_button_prepares_every_registered_platform_profile`; `test_repeated_start_while_running_keeps_the_same_round` | Pass; real button/shortcuts preserve active round and result |
| 11 | AWAITING_REVIEW direct start and two shortcuts | `test_awaiting_review_start_entrypoints_preserve_their_existing_side_effects` | Pass; actual direct, local, and global-to-Tk actions retain their distinct baseline side effects |
| 12 | Start while close-save runs; prepare-close, cancel and close again | `test_close_cannot_accept_a_new_round_before_completion_or_cancellation`; `test_close_waits_for_source_preparation_and_restarts_after_cancel`; `test_close_waits_responsively_and_cancellation_invalidates_old_completion`; `test_real_tk_close_waits_for_source_preparation_before_destroy` | Pass in full suite; successful-close/public archive status is awaited before temporary data cleanup |
| 13 | Prior-round delayed event and unmapped source | `test_queued_prior_round_event_cannot_change_the_new_round_ui`; `test_warning_for_unmapped_source_is_kept_without_claiming_a_display_slot` | Pass; real Tk renders two temporary rounds and ignores the stale result; mapping test retains evidence |
| 14 | Save tracking/retry, archive and retention protection | `test_graceful_close_waits_for_every_current_run_round_to_be_durable`; `test_successful_flush_does_not_allow_close_when_audit_is_incomplete`; `test_completed_round_is_archived_by_coordinator_using_actual_injected_time`; `test_public_cleanup_removes_expired_round_and_persists_summary_for_fresh_reader` and full lifecycle suite | Pass as regression; no lifecycle code changed |

## Commands and results

Working directory for Python commands: `B518 Log Solution/`.

```text
python3 scripts/run_tests.py test_round_start_preparation test_machine_profiles test_platform_registry test_configured_monitor
Ran 42 tests in 4.762s — OK (baseline before R3 edits)

B518_TK_TESTS=1 python3 scripts/run_tests.py test_queued_prior_round_event_cannot_change_the_new_round_ui test_real_tk_start_button_prepares_every_registered_platform_profile test_real_tk_shortcuts_start_rounds_with_session_and_audit_profile_evidence test_awaiting_review_start_entrypoints_preserve_their_existing_side_effects test_round_start_preparation test_machine_profiles test_platform_registry test_configured_monitor
Ran 46 tests in 14.590s — OK (at `26960a1`)

B518_TK_TESTS=1 python3 scripts/run_tests.py test_log_solution_ui.LogSolutionUiTests.test_operator_selects_project_and_machine_and_choice_survives_restart
Ran 1 test in 1.202s — OK (real B482 adapter and disk readers, at `8f9b293`)

B518_TK_TESTS=1 python3 scripts/run_tests.py
Ran 286 tests in 63.304s — OK (accessible desktop session, at `8f9b293ec7c90595c4bcd443daabf26e72049f0b`)

python3 -m compileall -q src tests
OK (syntax/bytecode compilation only)

git diff --check
OK
```

There is no project type-check configuration or command (`mypy`, `pyright`, and repository config search returned none); compileall is only syntax/bytecode validation. Tk tests ran in an accessible desktop graphical session. OS-level global-hotkey hardware testing and physical factory-device acceptance are not claimed.

## Review and delivery trace

- Fixed review base: `0fbbd01ddb627bdd9bdee413ca6d3dfc2ae23fc8`.
- Final validated program/test commit before evidence documentation: `8f9b293ec7c90595c4bcd443daabf26e72049f0b`.
- Implementation commits: `26960a1f18c3e28d06484d30e6c28e19598ac10d`, `8f9b293ec7c90595c4bcd443daabf26e72049f0b`.
- Standards review at fixed base: no documented-standard violations. One non-blocking test-maintenance observation noted duplicated `pump_until` and cleanup patterns in the two new Tk cases; no implementation change was requested.
- Spec review at fixed base: no blocking specification findings. The reviewer confirmed the constructor-owned preparation path, real Tk/disk evidence, fourteen-scenario matrix, and honest field/type-check limitations.
- Local batch pushes succeeded to the configured Gitea and GitHub destinations. Final mainline merge, post-merge test, live SHA verification and branch cleanup are pending the review gate.
- Field checklist status: pending scheduled factory acceptance; no equipment results are inferred.
