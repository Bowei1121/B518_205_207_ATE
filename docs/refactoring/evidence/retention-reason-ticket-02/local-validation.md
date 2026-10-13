# C2 local validation — round cleanup and archive reasons

Date: 2026-10-13 (Asia/Taipei)  
Ticket: cleanup-reason C2, GitHub #34 (parent #28)  
Branch: `LanguageRefresh/ticket-06`  
Fixed review base: `d3068bff31fb1f99422121cf9d48e3c925a1c3c2`  
Final code/test SHA before documentation: `316fc7005b3e1ca4992da5601a9882b543228177`

## Baseline, dependency, and repository state

The actual Git root is the B518 repository; the Python project is `B518 Log Solution/`. The dedicated C2 worktree is `/private/tmp/B518-LanguageRefresh-C2`; the main checkout has pre-existing edits in `PROJECT_SUMMARY_2026-10-09.md` and `PROJECT_SUMMARY_2026-10-12.md`, which were left untouched. C1's separate worktree and all other worktrees were preserved. C2 review base `d3068bf` is the current `B518-Log-Solution` ancestor and contains C1 (`5cf609d` is an ancestor); it also contains L1–L4. C1 evidence is [C1 validation](../../retention-reason-ticket-01/local-validation.md), whose final desktop full-suite and fixed-base review have no unresolved blockers.

Before C2, `round-retention-ledger.json` used schema 2, with `runs`, optional `active_plans`, and resumable deletion progress. C1 added optional `reason_message` fields without changing the ledger schema. C2 keeps schema 2 and the same ledger, active plans, deletion plan, retry, archive eligibility, and final deletion gates. Structured App-event cleanup producers remain C3 scope. Complete settings/history-screen unification remains C4 scope.

Configured push destinations are Gitea (`origin` primary URL) and GitHub (`origin` push URL; the `github` remote also identifies the same GitHub repository). At 2026-10-13 09:17 Asia/Taipei, direct `git ls-remote` queries showed both destinations at main `d3068bff31fb1f99422121cf9d48e3c925a1c3c2` and C2 branch `316fc7005b3e1ca4992da5601a9882b543228177`. These are branch refs, not a mainline merge. No remote issue was modified.

## Producer and display inventory

| Path | Producer / data contract | C2 change and proof |
| --- | --- | --- |
| Round cleanup | `RoundRetentionStore.run()` yields per-round `deleted` / `skipped` / `failed`, a run summary, and live `RetentionStatus`; run id, round id, timestamps, retention days, outcome, result counts, App-event counts and active deletion plans already belong to the ledger contract. | At the decision sites, C2 captures C1 `reason_message` (stable id, fixed parameters, same-record `en`/`zh-TW`, raw diagnostic) for success, protected/not-yet-expired/timezone/close skips, failures, run summary, recovery and live status. The reason is explanatory metadata only. |
| Archive verification | `read_round_archive()` and coordinator archive validation own trusted `archived_at`, manifest/component integrity and the `cleanup_eligible` result. | Invalid format/version, integrity, identity, timestamp, missing/changed component, incomplete contents and rebuild failures carry the existing snapshot's structured reason or a C1-compatible fallback. A live “saving” result carries `archive.saving`. Eligibility and protection are unchanged. |
| Cleanup discovery safety | `_discover()` verifies the manifest/components, managed paths and known files before admitting a round. | Unsafe manifests/components, path mismatch and unknown files use explicit C1 reason ids and remain `skipped`; no display text is parsed to infer deletion safety. Their files are preserved. |
| Persistence and recovery | Schema-2 ledger read/write, `active_plans`, staged deletion, resume, summary write and public retry/close coordination remain the existing path. | C2 adds only optional reason metadata to the already persisted summary/status fields; it does not reset, migrate, or discard plans or progress. |
| App display | The existing Settings retention summary and current live cleanup/archive status are the actual UI entry points. | The existing renderer presents the captured reason in the active language while exposing raw diagnostic details. Live status takes precedence over an older historical summary during a close/cleanup race. C2 does not claim all App-event rows or all screens are migrated. |

## Acceptance evidence

| C2 acceptance | Evidence / result | Limits |
| --- | --- | --- |
| 1. Formal round cleanup outcomes and archive-validation/live reasons use stable reason data. | `tests.test_round_retention.RoundRetentionTests.test_public_cleanup_removes_expired_round_and_persists_summary_for_fresh_reader`, `test_deadline_is_inclusive_and_a_round_before_deadline_is_preserved`, `test_corrupt_round_is_skipped_and_summary_write_failure_prevents_deletion`; `tests.test_round_archival.RoundArchivalTests.test_missing_or_unknown_archive_metadata_keeps_old_round_protected`, `test_failed_archive_write_stays_protected_then_retry_seals`; live status covered by `test_close_waits_for_inflight_archive_validation_before_reporting_complete` and the new archive-saving barrier assertion. Full suite: 394 passed. | App-event reason producers are intentionally not migrated here. |
| 2. One saved record keeps reason id/parameters, bilingual capture, diagnostic and existing linkage. | `test_public_cleanup_removes_expired_round_and_persists_summary_for_fresh_reader` checks the successful result in the persisted summary and a fresh coordinator; `test_fresh_reader_preserves_structured_and_legacy_cleanup_reasons_without_rewriting_ledger` covers run/round/time/outcome/counts, mixed legacy/structured data and active-plan preservation. `test_close_waits_for_inflight_archive_validation_before_reporting_complete` asserts the `archive.saving` reason id. Full suite passed. | The language record remains one field on the one cleanup result; no second cleanup/run is generated for the second language. |
| 3. Trusted archive time, deadlines, protected rounds, unknown/corrupt records and deletion gates remain intact. | `test_deadline_is_inclusive_and_a_round_before_deadline_is_preserved`, `test_new_retention_days_stop_inflight_cleanup_before_first_unlink`, `test_new_retention_days_win_race_at_final_unlink_gate`, `test_current_run_round_is_protected_and_close_suppresses_new_cleanup`, `test_corrupt_round_is_skipped_and_summary_write_failure_prevents_deletion`, `test_corrupt_persistent_progress_is_visible_and_prevents_deletion`; archive protection is covered by `test_missing_or_unknown_archive_metadata_keeps_old_round_protected`. | Existing policy tests are regression evidence; no new retention or deletion policy is introduced. |
| 4. Path, symlink, integrity, durable deletion-plan safety are preserved; reasons do not control eligibility. | `test_symlinked_component_to_external_data_is_preserved_and_reported`, `test_same_named_unknown_file_in_other_round_directory_blocks_deletion`, `test_parent_replaced_with_external_symlink_during_unlink_cannot_delete_external_file`, `test_replaced_file_after_hash_is_preserved_instead_of_unlinked`, `test_crash_after_staging_rename_resumes_from_fresh_coordinator`. The first two now also assert the precise `unsafe_component` and `unknown_file` reason ids while retaining `skipped` and file-preservation behavior. | No file/path/time/id/sequence/diagnostic is translated or regenerated. |
| 5. Existing summary persistence, failure recovery and retry remain authoritative. | `test_final_summary_failure_keeps_completed_plan_for_fresh_reader`, `test_partial_delete_progress_resumes_from_fresh_coordinator`, `test_crash_after_staging_rename_resumes_from_fresh_coordinator`, `test_corrupt_round_is_skipped_and_summary_write_failure_prevents_deletion`; archive write/retry uses `test_failed_archive_write_stays_protected_then_retry_seals` and `test_normal_close_waits_for_archive_write_repair_and_retry`. All pass in the final suite. | Tests exercise the existing public coordinator and fresh-reader paths; no new scheduler or retry system was added. |
| 6. Real archive/cleanup → durable summary → fresh reader → actual App/Tk inspection. | `tests.test_log_solution_ui.LogSolutionUiTests.test_real_tk_shows_startup_cleanup_summary_after_disk_deletion` produces and deletes an expired archived round through the public coordinator, saves to an isolated real ledger, reconstructs a new coordinator, and inspects the Settings summary through real Tk in English and Traditional Chinese. `test_real_tk_reads_mixed_cleanup_reason_ledger_and_keeps_raw_evidence_read_only` verifies mixed old/new data and raw detail. `test_real_tk_distinguishes_unsaved_saved_and_archived_round_states` injects archive-write failure, asserts the structured reason and protected outcome, then retries through the real UI. All pass in the final suite. | App-event producer migration and full-screen unification remain C3/C4. |
| 7. Before/after cleanup and preservation behavior. | Fixed-base checkout `d3068bf` and C2 branch each ran `PYTHONPATH=src /opt/anaconda3/bin/python3 -m unittest tests.test_round_archival tests.test_round_retention`: 45 tests passed on each side (baseline 18.384 s; C2 13.283 s). The unchanged public deadline, protected-round, symlink/path replacement, archive-integrity, durable-progress and retry assertions pass on both; the C2 build additionally asserts reason ids. | This is a focused code-path comparison, not a claim that every fixture permutation was exhaustively replayed against both versions. The full current suite covers remaining safety cases. |
| 8. Legacy summary compatibility, read-only behavior and scope boundary. | `test_fresh_reader_preserves_structured_and_legacy_cleanup_reasons_without_rewriting_ledger`; true-Tk mixed-ledger test above; `test_real_tk_shows_startup_cleanup_summary_after_disk_deletion`. Ledger bytes are unchanged by fresh reading and language switching; controlled cleanup changes only its isolated test ledger. Full regression suite passes. | Historical summaries are not rewritten. C3 App-event producers, C4 full UI migration, bundle/factory/field acceptance and parent-item completion are not claimed. |

The C2 reason ids use the C1 presenter/catalog and are captured where the formal round/archive outcome is produced. Old exact producer strings remain handled by C1 compatibility rules; C2 does not expand fuzzy matching. Missing/unknown/malformed reason data continues through C1's selected-language outer explanation, captured-English fallback and full raw detail. The newly explicit `unsafe_component`, `archive_path_mismatch`, and `unknown_file` reasons replace only generic reason labeling; their skip outcome and safety checks remain the same.

## Commands, runtime, and failures retained

Runtime: `/opt/anaconda3/bin/python3`, Python 3.11.7, Tcl/Tk 8.6, macOS desktop. No repository type-check configuration was found; no type checker was added.

TDD red-green for the specific safety-reason refinement:

```text
PYTHONPATH=src /opt/anaconda3/bin/python3 -m unittest \
  tests.test_round_retention.RoundRetentionTests.test_same_named_unknown_file_in_other_round_directory_blocks_deletion \
  tests.test_round_retention.RoundRetentionTests.test_symlinked_component_to_external_data_is_preserved_and_reported
```

Before implementation, both tests failed only because their structured ids were generic `cleanup.round_failed`; the observed outcomes remained `skipped`. After the minimal producer change, both passed, and the focused 45-test round/archive run passed.

The required complete suite was attempted first in the restricted runner and aborted during class setup at `tkinter.Tk()` with macOS AppKit/LaunchServices `NSException` (exit 134); it did not complete and is not counted as a pass. The same command was then run with authorized desktop access:

```text
B518_TK_TESTS=1 PYTHONFAULTHANDLER=1 PYTHONPATH=src \
  /opt/anaconda3/bin/python3 scripts/run_tests.py
Python 3.11.7 / Tk 8.6; 394 tests / 143.542 seconds / OK / exit 0
```

This final full-suite run is on code/test SHA `316fc7005b3e1ca4992da5601a9882b543228177`. The C1 dependency's earlier Tk notification-reopen issue was resolved before this base: its later final desktop suite and fixed-base review are recorded in the C1 evidence above. No type-check tool/config exists.

## Review, integration, and destination status

Standards/Spec reviews against fixed base `d3068bff31fb1f99422121cf9d48e3c925a1c3c2`: pending final review. Mainline integration and post-merge suite: pending. Merge SHA: pending. Documentation SHA: recorded in the final delivery update. Do not infer completion from the ticket branch's successful suite.

At the latest direct destination query, both Gitea and GitHub main refs were `d3068bff31fb1f99422121cf9d48e3c925a1c3c2`; both C2 refs were `316fc7005b3e1ca4992da5601a9882b543228177`. The verified implementation batch at `316fc70` was pushed to both destinations. Branch cleanup is pending post-merge validation and direct final SHA confirmation.
