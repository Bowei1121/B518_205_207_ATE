# M2 local validation: bilingual round events

Date: 2026-10-08 (Asia/Taipei)

## Baseline and dependency

- Fixed review baseline: `44567457f0c94ae4667ab0c06e82cbacc9a001a6` (`B518-Log-Solution`). The M2 branch was created from this commit after a live GitHub check; the worktree was clean. M1 is an ancestor of this baseline, and its implementation, six-criterion evidence, user-confirmed mouse operation, and keyboard selection/cancel evidence are present in the repository. This confirms the dependency from Git ancestry, source, and [M1 evidence](../multilingual-ticket-01/local-validation.md), rather than from a branch label alone.
- Working branch: `Multilingual/ticket-02`.
- Initial implementation slice: `ff7e3b64d7ef9f42c0f9a113727113101a7c2d70` (`feat: persist bilingual round result events`), pushed to GitHub. The remaining implementation and this evidence update are being validated on the same branch.
- Configured destinations at start: `github` and `origin`; `origin` has Gitea fetch/push plus a GitHub push URL. GitHub is the authorized reachable destination for this off-site session. Gitea at `10.64.76.34:3000` timed out during the current session. Do not merge to the main branch or delete this ticket branch until every existing push destination can be queried and confirmed in sync.
- No remote issue was changed.

## Event and persistence contract

The M2 event extension is an optional `localized_message` sibling on an existing event. Version 1 carries a stable `message_id`, JSON-captured `parameters`, fixed `en` and `zh-TW` text, and optional raw `diagnostic`. The existing `message`, event kind, machine fields, event ID, round ID, timestamp, ordering, result, and decision remain unchanged. Old events without the sibling remain readable and retain their original message.

The bilingual value is captured once when the common-round event is produced. The same captured value is written to the Session event and audit event; retries reuse that captured record. The UI renders identified events using the current language and the persisted text fallback, retaining raw diagnostic text. Language switching redraws the event display only; it does not call a producer, create a save, or rewrite Session/audit files.

The M2 producer inventory is the common-round path: round start/readiness/stop/finish/result, slot and whole-round timeout, alarm creation/acknowledgement, conflict detection/resolution, duplicate/unknown-source rejection, and Session/audit save failure and recovery notices. Platform parser/source-specific events that have not migrated, including platform-only diagnostics, remain on their compatible legacy path for M3. No-round application diagnostics remain for M4. Translating all conflict-window copy remains outside this ticket.

## Evidence by acceptance criterion

| Criterion | Evidence and result |
| --- | --- |
| 1. Common round events persist both languages, ID, parameters, diagnostics, and original identity/time/sequence. | `test_shared_round_result_is_one_versioned_bilingual_audit_event`; `test_real_tk_language_menu_switches_main_page_and_persists_across_app_instances`; audit event cases for start/readiness/stop/finish, result, timeout/alarm, conflicts, decisions, and save recovery. Session and audit contain the same captured localization object and round identity. **Pass.** |
| 2. Changing language refreshes existing visible events without rerunning or rewriting them. | The true-Tk integration test switches the actual language control while the app is running, checks visible event text, and compares saved audit/session bytes before and after. **Pass.** |
| 3. Existing message/machine fields and old readers remain compatible; one bilingual event is one operation. | Legacy payloads omit `localized_message`; existing reader/rebuild tests remain in the full suite. The new test rebuilds the same event from both temporary stores and verifies one event identity with both literals. **Pass.** |
| 4. Failures retain the complete bilingual unit and retry without loss or duplication. | `test_session_sync_failure_retains_original_event_for_nonblocking_retry`, `test_session_retry_failure_keeps_original_ahead_of_later_retained_writes`, `test_session_background_failure_retains_work_until_retry`, `test_append_completed_before_error_report_is_not_duplicated_on_retry`, and `test_successful_flush_does_not_allow_close_when_audit_is_incomplete`. The audit/session integration checks the recovered on-disk event. **Pass.** |
| 5. RUNNING/AWAITING_REVIEW switching preserves business state and policy. | The real-Tk integration keeps the same app/round active while changing language, then performs one actual conflict decision; it verifies the candidate/result state and reconstructed audit/session decision. Existing source-scope, unknown-source FAIL, KVM, and product-release tests pass in the full suite. **Pass.** |
| 6. Public round path, temporary disk, and real Tk demonstrate equivalent business behavior. | The test enters through the real app/common-round flow with isolated temporary source, Session, and audit storage, operates the language control and conflict decision, then rebuilds persisted records. **Pass.** |

## Commands and results

Commands ran from `B518 Log Solution/` (the Python project root):

```sh
PYTHONPATH=src python3 scripts/run_tests.py test_language_catalog test_audit_records test_log_monitoring
# 55 tests passed

B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py test_log_solution_ui.LogSolutionUiTests.test_real_tk_language_menu_switches_main_page_and_persists_across_app_instances
# Passed in an authorized desktop GUI session; actual Tk widgets, visible event refresh,
# disk-byte stability, and one actual conflict decision were exercised.

B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py
# 301 tests run, OK, 1 skipped (68.259s)
```

The skipped test is `test_real_tk_language_button_mouse_click_posts_menu_without_tk_error`: automated synthetic mouse posting enters macOS native Tk menu tracking and blocks the test harness. The full real-Tk language-menu flow above passed, and the user separately confirmed actual M1 mouse and keyboard menu operation on the merged application. This one automation limitation is recorded as skipped, not passed.

`python3 -m compileall -q src tests` and `git diff --check` are required final checks and will be recorded against the final validation SHA below. The repository has no configured mypy, pyright, or other type-check command; no type-check pass is claimed. Tk tests run in an authorized desktop GUI session because sandbox window creation aborts before test execution.

## Scope and outstanding release boundary

M2 covers common-round bilingual events and the main-page event display. Platform-specific producer migration is M3; no-round App diagnostics are M4; full conflict-window copy, other owned windows, close-language policy, historical fuzzy identification, cleanup, and packaged-release coverage remain in their assigned later tickets. M2 does not change event result/status codes, source values, timestamp semantics, product release conditions, KVM behavior, or lifecycle policy.

Final validated implementation SHA: pending final checks/commit. Fixed review baseline: `44567457f0c94ae4667ab0c06e82cbacc9a001a6`. Standards/Spec review result: pending. GitHub direct branch SHA and Gitea availability: pending final push verification.
