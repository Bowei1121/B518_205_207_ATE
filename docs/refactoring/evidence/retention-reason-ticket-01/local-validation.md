# C1 local validation — compatible cleanup reason reading

Date: 2026-10-12
Ticket: cleanup-reason C1, GitHub #33 (parent #28)
Branch: `LanguageRefresh/ticket-05`
Fixed review base: `14d7c23195d66962b86b8b301cdcc587b3a15c3d`
Implementation commit: `90fc58cc0516ff9c26a8dfb2e720297228fe4cda`
Final code/test commit: `7ceb746f39a9c5288459b8622a32ff40538043c7`

## Baseline and scope

The fixed base was confirmed as the current `B518-Log-Solution` ancestor before edits. C1 has no direct blocking ticket and does not depend on L4. The current mainline already includes L1–L4 and the M4/M7/M8/M9 saving, close, history, and cleanup contracts; C1 was kept independent of those tickets' later delivery and cleanup steps. C2 (#34) owns round/archive producer migration, C3 (#35) owns App-event producer migration, and C4 (#36) owns complete screen migration and parent second-item acceptance.

At the fixed base, `round-retention-ledger.json` uses `LEDGER_SCHEMA_VERSION = 2`, with `runs`, `active_plans`, and the schema-1 in-memory compatibility conversion from one `active_plan`. Summary rows store the original string `reason`; deletion recovery uses the separate `active_plans` field. `RoundRetentionStore._load_ledger`, `_write_ledger`, and `RoundCoordinator.retention_cleanup_summaries()` are the read/write/public-read path. The App-event journal has its own versioned records and public fresh-reader path. Archive eligibility is produced by `read_round_archive`; cleanup eligibility and final deletion remain in `round_retention.py` and its existing verification gates.

## Delivered contract

- `src/cleanup_reasons.py` exposes `capture_cleanup_reason()` and `present_cleanup_reason()`. New records use the existing `BilingualMessage` shape (record version, stable message id, fixed parameters, captured `en`/`zh-TW`, original diagnostic). The presenter checks fields and scalar parameter values, uses current catalog resources, falls back to captured English for absent/incompatible resources or incomplete render parameters, and returns the untouched source record for inspection.
- Exact legacy text and four producer-emitted diagnostic prefixes are mapped only when backed by the existing producer format. The source of the legacy strings is `app_event_store.py` cleanup validation/result paths (including lines 411–532), `round_retention.py` skip/delete/recovery paths (lines 205–511), and `round_archival.py` archive verification paths (lines 229–286). Diagnostic prefixes are exactly `App 事件紀錄無法讀取：`, `封存資訊無法讀取：`, `必要輪次紀錄缺失或無法讀取：`, and `必要輪次紀錄無法重建：`; all have matching format-string producers in those files. Near-match prefixes and empty diagnostic suffixes are rejected. Two strings present in the old UI-only map without a matching producer (`App 事件管理根目錄不是實體目錄` and `App 事件清理目標不是一般檔案或目錄`) were deliberately removed from the compatibility map and now use the unknown-reason path.
- Unrecognized or malformed data uses the selected-language outer text, then exposes the original reason data and raw diagnostic in the existing settings cleanup summary. Structured details omit the internal message id from visible UI text; the untouched source mapping remains available from the read model. No raw diagnostic, time, path, round id, count, outcome, or sequence is translated or regenerated.
- Ledger schema 2 remains unchanged. Optional `reason_message` fields on a summary result, App-event result, and summary-level message are additive; the reason record has its own version validation. Old summaries without these fields read identically. `RetentionSummary.to_record()` serializes controlled summary data through the actual ledger row serializer; `_summary_from_dict()` preserves both the reason value and all surrounding linkage. No active plan is migrated, reset, or discarded.
- The existing Settings retention tab now renders either the historical string or optional structured reason through the common presenter. No formal cleanup producer was changed, and the reason presenter is not called by retention eligibility or deletion code.

## Acceptance evidence

The complete suite was run on three code/test revisions. `90fc58cc0516ff9c26a8dfb2e720297228fe4cda` passed 393 tests in 155.197 seconds; `dfb7506f14cba351b78b047ed7c7c808ff9f99c8` passed 393 tests in 154.111 seconds. After adding localized display for completed-round reasons and tightening the Tk assertion, the required final suite passed on `7ceb746f39a9c5288459b8622a32ff40538043c7`:

```text
B518_TK_TESTS=1 PYTHONFAULTHANDLER=1 PYTHONPATH=src /opt/anaconda3/bin/python3 scripts/run_tests.py
Python 3.11.7 / Tk 8.6, accessible macOS desktop, exit 0
393 tests in 156.872 seconds — OK (desktop-authorized execution)
```

The additional C1 checks were:

| Ticket acceptance | Evidence and result |
| --- | --- |
| Ledger/recovery compatibility | `tests.test_round_retention.RoundRetentionTests.test_fresh_reader_preserves_structured_and_legacy_cleanup_reasons_without_rewriting_ledger`: fresh `RoundCoordinator` reads schema-2 ledger rows containing structured and legacy reasons plus an active plan; run id, round id, raw legacy text, new bilingual record, and failed/interrupted status remain; ledger bytes are identical. |
| New captured reasons and linkage | `tests.test_cleanup_reasons.CleanupReasonPresentationTests.test_new_reason_is_captured_once_and_rendered_from_current_catalog`; `tests.test_round_retention...test_fresh_reader_preserves_structured_and_legacy_cleanup_reasons_without_rewriting_ledger`: one fixed record renders in both languages, diagnostic and summary/result/App-event associations survive disk reconstruction. |
| Reliable legacy matching | `test_legacy_translation_requires_exact_contract_match` and `test_exact_producer_prefix_preserves_unmodified_diagnostic`: exact producer text/prefix translates; a similar suffix, missing delimiter, empty required diagnostic or near-match stays unknown. Producer inventory was checked against the three source modules above. |
| Unknown / incompatible / missing resources | `test_unknown_legacy_reason_has_localized_outer_message_and_verbatim_detail`, `test_malformed_new_reason_preserves_full_original_record_without_leaking_id`, `test_missing_current_resource_falls_back_to_captured_english`, `test_missing_or_incompatible_resource_falls_back_to_captured_english`, and `test_incomplete_required_parameter_and_empty_legacy_diagnostic_are_not_guessed`. |
| Display does not affect safety or identity | Presenter is only imported by the UI renderer; the cleanup decision methods and gates were not changed. Existing round retention, archive, App-event retention, symlink, cutoff, recovery and durability tests all passed in the 393-test run. Original time, outcome, round id, App-event sequence and counts are asserted by existing public cleanup/readback tests. |
| Real temporary ledger and actual Tk | `B518_TK_TESTS=1 PYTHONFAULTHANDLER=1 PYTHONPATH=src /opt/anaconda3/bin/python3 -m unittest tests.test_log_solution_ui.LogSolutionUiTests.test_real_tk_reads_mixed_cleanup_reason_ledger_and_keeps_raw_evidence_read_only -v` passed in 1.911 s on the desktop session with the final test code. A fresh reader opens the real Settings window with active recovery work, successful/deleted, failed and skipped round reasons, App-event reason, and archive verification reason; English/Traditional Chinese show the successful reason and details, raw diagnostic remains inspectable, the internal message id is absent from visible text, and the ledger bytes are unchanged. |
| Read-only language refresh; producers unchanged | The true-Tk test asserts `round-retention-ledger.json` bytes before/after rendering and switching are equal and patches the existing cleanup schedule off so reading cannot initiate cleanup. `round_retention.py`, `app_event_store.py`, and `round_archival.py` reason producers and deletion checks remain on the original path. The full existing cleanup suite passed. |
| Round, App-event and archive cases | Controlled ledger includes round-result, App-event and summary-level archive-verification reasons; existing full-suite tests exercise formal round/App-event/archive producer outcomes without migrating them. This does not claim C2/C3 producer migration. |

Targeted runs on the C1 implementation:

```text
PYTHONPATH=src /opt/anaconda3/bin/python3 -m unittest tests.test_cleanup_reasons tests.test_round_retention -v
36 tests passed across `tests.test_cleanup_reasons` and `tests.test_round_retention` (9.055 s after the completed-reason renderer was added).

B518_TK_TESTS=1 PYTHONPATH=src /opt/anaconda3/bin/python3 -m unittest \
  tests.test_log_solution_ui.LogSolutionUiTests.test_real_tk_reads_mixed_cleanup_reason_ledger_and_keeps_raw_evidence_read_only \
  tests.test_log_solution_ui.LogSolutionUiTests.test_real_tk_shows_startup_cleanup_summary_after_disk_deletion \
  tests.test_log_solution_ui.LogSolutionUiTests.test_real_tk_localizes_timezone_missing_app_event_cleanup_reason \
  tests.test_log_solution_ui.LogSolutionUiTests.test_real_tk_app_event_cleanup_failure_is_visible_and_retryable -v
4 true-Tk cleanup regressions passed in 5.214 seconds on the preceding C1 renderer; the final complete suite reran them along with the new successful-round reason assertion.
```

The first TDD run failed to import the not-yet-created `cleanup_reasons` module; the ledger round-trip test then failed because the result model did not yet carry `reason_message`. Both failures became passing after the minimal implementation. An intermediate four-test Tk regression found a legacy wording priority mismatch for `尚未到保存期限`; the original App-event wording was restored and all four passed on rerun. These are recorded as red-green evidence, not final failures.

## Environment and review

Interpreter used: `/opt/anaconda3/bin/python3`, Python 3.11.7, Tk 8.6. Two sandboxed attempts (a cleanup+Tk focused command and then the single true-Tk case) aborted during `LogSolutionUiTests.setUpClass` while constructing the class-level `tk.Tk()` root; both exited 134 with macOS `NSInternalInconsistencyException` in Tk/AppKit `NSMenuItem`/`TkpInit` and invalid LaunchServices XPC messages, before the C1 test body ran. After the user confirmed the desktop was unlocked, the sandboxed attempt reproduced the same startup abort. An authorized desktop smoke check then created and destroyed a Tk root successfully. The first desktop true-Tk run reached the new assertion and failed because the fixture had inserted a successful row before `round-c1`; the assertion was corrected to select by `round_id`. The final focused case then passed (1 test / 1.911 s), and the final desktop-authorized full suite passed all 393 tests with no crash or timeout. The earlier startup aborts are retained as environment/process-boundary failures, not counted as passes. No repository type-check configuration was found; no new type-check tooling was added.

Standards review against fixed base `14d7c23195d66962b86b8b301cdcc587b3a15c3d`: no documented-standard violation or blocker; one non-blocking observation notes parallel formatting of completed/failed/skipped outcome details. Spec review against the same fixed base: no remaining scope or behavior gap after completed-round reasons were added; the first pass identified this missing success visibility and it was fixed and retested. Final evidence wording was subsequently updated and requires a documentation-only confirmation review.

## Delivery boundary

This evidence covers C1 only. The parent second item is not complete. Round/archive producer migration C2, App-event producer migration C3, and all-screen integration/second-item acceptance C4 remain pending. Code/test commits `90fc58c`, `dfb7506`, `e1a7020`, and `7ceb746` were pushed to both configured GitHub and Gitea destinations. Each push reported the matching ticket ref; a fresh direct query still needs to confirm the final SHA after documentation commits. No mainline merge has been performed yet. The original uncommitted edits to `PROJECT_SUMMARY_2026-10-09.md` and `PROJECT_SUMMARY_2026-10-12.md` remain protected; only the appended C1 summary note will be staged with this ticket.
