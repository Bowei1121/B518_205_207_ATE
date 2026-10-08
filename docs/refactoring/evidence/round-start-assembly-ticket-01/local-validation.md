# R1 local validation — concentrated round-start preparation

Date: 2026-10-08 (Asia/Taipei)  
Ticket: R1 / GitHub #25, parent specification #24  
Fixed review base: `c71fb5583364f0a7c4e71d9806cfdec04160cb11`  
Last code/test commit currently validated: `f5e3ff5` (`f5e3ff5` is the R1 branch tip before this evidence-only update).

## Baseline and scope

The worktree was clean on `B518-Log-Solution` at `c71fb5583364f0a7c4e71d9806cfdec04160cb11`; live main refs at both configured push destinations matched that SHA. No existing `RoundStartAssembly/ticket-01` branch was present. The ticket branch was created from that main commit. R1 leaves the formal Tk start entry on its pre-existing assembly path. It does not perform R2 desktop integration, R3 old-path removal, or field-device acceptance.

The code diff adds `src/round_start_preparation.py`, adjusts profile validation to use the selected PlatformRegistry, and narrowly marks a completed failed-source preparation as persistence-ready so an already durable audit-only failed round does not remain indefinitely “waiting.” The public preparation interface receives a profile and storage/clock dependencies, not Tk widgets. It validates and freezes paths, nested timeouts and position mappings; builds the adapter via PlatformRegistry; bridges its callback through ConfiguredMonitor; and supplies Session/audit configuration evidence to the existing RoundCoordinator start API. Original configured paths remain in persisted evidence while adapters receive validated paths. Existing record structures/schema versions are retained.

## Verification commands and results

All commands below ran from `B518 Log Solution/` (the Python program directory), using temporary source and session roots for the new tests.

| Command | Result |
| --- | --- |
| `python3 scripts/run_tests.py test_round_start_preparation test_platform_registry test_configured_monitor test_machine_profiles test_monitoring_round` | 88 tests passed after the final registry-validation change. |
| `B518_TK_TESTS=1 python3 scripts/run_tests.py` | Passed: 287 tests in 50.528 seconds in the desktop-enabled environment. This includes real Tk tests and existing platform, round, audit, archive, retention, and KVM regressions. |
| `python3 -m compileall -q src tests` | Passed. No mypy, pyright, or other project type-checker configuration was found; this is a syntax/bytecode compilation check, not a type check. |
| `git diff --check` | Passed for the implementation batches. |

Real registered adapters were built using isolated temporary directories for Atlas DFU/FCT, B482 BT, RS-WMT BT, and sample-json FCT. The sample-json end-to-end test changed the original profile paths/timeouts/mapping after preparation, then checked the resulting Session JSON, audit JSONL and mapped round result. A separate test proves the selected registry definition is also used for profile validation. A source factory controlled by Events exercises slow setup, stop, deadline handoff and setup failure. The tests read back persisted audit events and wait for archive status plus a stable archive file before temporary-directory teardown.

The existing formal Tk app start regression was run in the desktop-enabled execution environment. The focused real Tk Atlas conflict-flow case passed in 4.038 seconds, and the final full suite passed all 287 tests in 50.528 seconds. This verifies the existing Tk entry remains operational; R1 did not switch it to the new preparation module.

## R1 acceptance evidence

| # | Acceptance | Evidence / status |
| --- | --- | --- |
| 1 | Baseline flow checked; non-Tk preparation interface; formal Tk entry unchanged. | `B518_TK_TESTS=1 python3 scripts/run_tests.py` (287 passed) and `test_round_start_preparation`; R1 does not edit the app entry. Covered. |
| 2 | Central validation/freeze, path checks, adapter construction, callback bridge, source/display mapping. | `test_prepared_profile_starts_real_round_and_persists_matching_session_and_audit`, `test_all_registered_platforms_start_through_the_preparation_interface`, and existing ConfiguredMonitor tests. Covered. |
| 3 | Required and optional path rules, blank-path handling, labels/errors. | `test_required_paths_must_be_present_directories_readable_and_enterable`, `test_blank_optional_path_is_omitted_but_invalid_nonblank_path_is_rejected`. Covered. |
| 4 | Frozen configuration drives platform, capacity, mapping, paths, timeouts and version; Session/audit contracts and raw configured paths stay compatible. | Real temporary Session/audit readback in `test_prepared_profile_starts_real_round_and_persists_matching_session_and_audit`; original profile mutation after prepare; unchanged record readers. Covered. |
| 5 | Public preparation interface starts through RoundCoordinator and proves source/result/mapping/config on disk. | Real sample-json source and fresh Session/audit readers in `test_prepared_profile_starts_real_round_and_persists_matching_session_and_audit`. Covered. |
| 6 | All registered platform families covered; sample-json does not stand in for production parser tests. | Adapter creation test covers Atlas DFU/FCT, B482 BT, RS-WMT BT and sample-json; full suite separately runs Atlas/B482/RS-WMT parser tests. Covered. |
| 7 | Source creation remains after round acceptance in the coordinator preparation worker; accepted time and ready time remain distinct. | Event-controlled setup in `test_injected_round_deadline_during_preparation_stops_late_source_before_ready`; existing `test_source_preparation_time_counts_from_the_accepted_start`. Covered. |
| 8 | Slow setup, stop and timeout; late source cannot restart collection; event order and round identity retained. | Controlled Event tests `test_stopping_while_source_is_preparing_keeps_round_stopped_after_factory_returns` and `test_injected_round_deadline_during_preparation_stops_late_source_before_ready`, with audit reconstruction. Covered. |
| 9 | Setup failure retains failed round/event and close-save responsibility, with durable evidence and no duplicate event. | `test_source_creation_failure_through_preparation_is_audited_before_close_completes`; existing `test_source_preparation_failure_is_audited_before_close_completes`. Covered. |
| 10 | Bidirectional mapping and unmapped-source evidence remain; result, unknown-source and KVM policy unchanged. | Existing `test_capacity_fixtures_publish_mapped_positions_through_shared_round`, `test_out_of_order_native_positions_map_to_configured_displays_in_round`, `test_warning_for_unmapped_source_is_kept_without_claiming_a_display_slot`, plus product/KVM full-suite regressions. Covered as regression. |
| 11 | Actual commands and limitations documented; no claim of desktop migration or field acceptance. | This record; formal Tk start path intentionally remains unchanged. R2/R3 and physical equipment acceptance remain outstanding. Covered. |

## Mother-spec 14 scenario coverage

This matrix distinguishes new R1 evidence from inherited regression and work left to later tickets. It is not a blanket completion claim for the whole mother specification.

| Scenario group | Evidence | R1 result |
| --- | --- | --- |
| Invalid profile and unknown platform keep existing validation/errors. | `test_machine_profiles`; `test_unknown_platform_remains_rejected_after_registration`. | Inherited regression passed. |
| Required path blank/missing/non-directory/unreadable. | Real temporary paths in `test_required_paths_must_be_present_directories_readable_and_enterable`. | R1 covered. |
| Optional path blank vs invalid nonblank. | `test_blank_optional_path_is_omitted_but_invalid_nonblank_path_is_rejected`. | R1 covered. |
| Preference-save failure blocks acceptance and restores existing UI state. | Existing configuration/UI tests in full suite; R1 does not change preference or Tk entry flow. | Inherited regression; no R1 migration claim. |
| Configuration remains fixed and both durable records correspond. | Session JSON and audit JSONL reconstruction after mutating original configuration. | R1 covered. |
| All real platform adapters retain their parser behavior. | Platform-specific parser test groups in the full suite, plus all-registry preparation test. | R1 plus inherited parser regression. |
| Slow preparation counts from accepted start. | Controlled preparation Event and injected monotonic clock; `test_source_preparation_time_counts_from_the_accepted_start`. | R1 covered. |
| Background preparation failure is durable and tracked. | Controlled factory failure plus audit reconstruction and close status. | R1 covered. |
| Stop/deadline during preparation prevents late collection restart. | Two controlled Event tests plus existing coordinator regressions. | R1 covered. |
| RUNNING repeat start keeps current round and rows. | `test_repeated_start_while_running_keeps_the_same_round`, `test_repeated_app_start_keeps_the_round_and_does_not_reset_rows`. | Inherited Tk/coordinator regression passed. |
| AWAITING_REVIEW start entry differences remain as baseline behavior. | Existing entry flow is unchanged; the full Tk suite is the regression command. | No policy change; detailed entry behavior remains part of R2 integration coverage. |
| Close-save in progress rejects new start. | Existing `test_close_cannot_accept_a_new_round_before_completion_or_cancellation` and close/Tk regressions. | Inherited regression passed. |
| Old-round events, unknown source, product release and KVM remain isolated. | Round event isolation, unknown-source and KVM contract tests in full suite. | Inherited regression passed. |
| Formal Tk start still uses original assembly; full desktop migration and field validation. | R1 did not change app start entry; R1 Tk regression only. | R2/R3 and physical equipment acceptance remain pending. |

## Review and delivery trace

Fixed Standards/Spec base: `c71fb5583364f0a7c4e71d9806cfdec04160cb11`. Final Standards re-review found no documented-standard violation. One non-blocking duplicate path-helper smell remains because R1 intentionally keeps the old Tk path. Final Spec re-review confirmed the earlier registry-validation mismatch is fixed: both profile validation and adapter preparation use the selected PlatformRegistry, covered by `test_profile_validation_uses_the_same_platform_registry_as_adapter_preparation`. No unresolved Standards or Spec blocker remains.

Implementation batches: `a9fc77c`, `8a7a46c`, `1b23bc5`, `1ca7533`, `f5e3ff5`. The ticket branch was pushed to both configured destinations (Gitea and GitHub) after each validated implementation batch. No remote issue was edited. Merge and branch cleanup are pending final test/review and synchronization checks.
