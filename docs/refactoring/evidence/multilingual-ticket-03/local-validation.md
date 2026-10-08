# M3 local validation: bilingual platform events

Date: 2026-10-08 (Asia/Taipei)

## Baseline, dependency, and destinations

- Fixed M3 review baseline: `c87c7bcefa334b96c420f255e8c1bf99e7a97370` (`B518-Log-Solution`). M2 is in its ancestry through merge `f128d9f963f60d416d0eaf5917fa5eda87408280`; the M2 implementation and evidence are present. The M2 dependency is resolved for this branch; the ticket README's older `Blocked by #15` text predates that merge.
- M2 evidence at this baseline records implementation `1d036f0339c2d37ac7907e46c31f92708909ea38`, 303 tests passing with Tk, no unresolved Standards/Spec findings, GitHub mainline merge, and Gitea synchronization deferred by the user until Monday. M3 does not include M2 fixes.
- M3 branch: `Multilingual/ticket-03`, created from the clean `B518-Log-Solution` baseline above. The fixed review base remains `c87c7bcefa334b96c420f255e8c1bf99e7a97370`.
- The latest program/test changes are commits `5bad98a`, `6125015`, `885e20c`, `30f8702`, and `9d35db3`; the last adds assertions for all five Sample JSON warning producers. The final full Tk suite after `9d35db3` passed 317 tests in 88.328 seconds.
- Earlier evidence commits `8cb1d21`, `3c5f9a6`, `c9a348d`, and `3455d48` were pushed and directly checked at their respective times. The latest direct GitHub query on 2026-10-08 confirmed `refs/heads/Multilingual/ticket-03` at `9d35db36af225ce6faf56eafbe2e8554917e1a66`; GitHub `B518-Log-Solution` remained at `c87c7bcefa334b96c420f255e8c1bf99e7a97370` before merge.
- Configured `origin` fetch URL is internal Gitea at `10.64.76.34:3000`; its push configuration also includes GitHub. A live Gitea query on 2026-10-08 timed out; at the user's direction Gitea sync is deferred until Monday. No Gitea synchronization claim is made. GitHub is directly verified as the current push destination.
- No GitHub issue was changed. The five acceptance criteria are evidenced below. Final review of `99556a784a50e91262cb340ba89fcb8cfccd5555` against fixed base `c87c7bcefa334b96c420f255e8c1bf99e7a97370` found 0 Spec findings and 0 hard Standards violations; Standards noted one non-blocking possible duplication smell in Atlas/B482 source-error tracking. GitHub merge `fb4ffb2286d9c113511482b738a101a11616bd14` passed the full Tk suite (317 tests, 89.830 seconds) and was directly confirmed on `B518-Log-Solution`. The M3 and M2 ticket branches remain until Gitea synchronization is directly confirmed Monday.

## Producer inventory and event contract

| Platform / producer | Stable ID and complete captured parameters | Persistence and exercising evidence |
| --- | --- | --- |
| Atlas DFU/FCT: source prepared, trusted SN locked, final result, unresolved identity conflict, source read/parse error | `platform.atlas.source_prepared` (`station`); `.sn_locked` (`slot`, `station`); `.final` (`slot`, `status`, `station`); `.unresolved_conflict` (`slot`, `station`); `.source_error` (`source_filename`, `station`); diagnostic stays raw | `tests/test_log_monitoring.py` producer and error cases; `tests/test_log_solution_ui.py::test_real_tk_start_button_prepares_every_registered_platform_profile` drives both DFU/FCT through R1 preparation, partial active CSV, archived PASS, injected parser failure, bilingual Tk refresh, and fresh audit reconstruction. `test_unknown_atlas_identity_change_is_visible_as_fail_and_audited_without_reason` covers the applicable unlinked identity candidate/FAIL policy. |
| B482 BT: batch observed, batch mismatch, TestData/CaseInfo result, source read/signature error | `platform.b482.batch` (`batch_id`, `station`); `.batch_mismatch` (`slot`, `station`); `.source_error` (`source_filename`, `station`); result uses shared `round.result` (`slot`, `status`, `station`) | `tests/test_log_monitoring.py::test_atlas_and_b482_producers_capture_platform_message_ids`, `::test_b482_batch_mismatch_producer_captures_localized_slot_and_diagnostic`, and producer/error cases; `tests/test_b482_source_adapter.py` partial CaseInfo; the Tk matrix covers a partial CaseInfo record, TestData PASS, injected signature error, Session/audit rebuild, and language refresh. Batch mismatch has no candidate-resolution behavior; it remains a source warning under existing policy. |
| RS-WMT BT: live/final batch observed, partial/unsupported/read/parse warning, final result | `platform.rswmt.batch` (`station`); `.warning` (`source_filename`, `station`) with original warning/exception diagnostic; result uses shared `round.result` (`slot`, `status`, `station`) | `tests/test_rswmt_monitoring.py::test_rs_wmt_batch_producer_captures_stable_message_id`, partial live log, stable CSV, malformed CSV, and read error cases; the Tk matrix covers partial live log → same-run final CSV PASS, injected read error, fresh audit result reconstruction, and language refresh. A different-run CSV remains a warning, not a conflict candidate. |
| sample-json FCT: invalid, unsupported, invalid fields/status, unreadable source, result | `platform.sample_json.invalid_record`, `.unsupported_record`, `.invalid_fields`, `.invalid_status`, `.unreadable` (`source_filename`, `station`) with raw parse/read diagnostic; result uses shared `round.result` (`slot`, `status`, `station`) | `tests/test_platform_registry.py::test_sample_json_warning_producers_capture_ids_parameters_and_raw_diagnostics` asserts all five warning IDs, complete parameters, bilingual literals and raw diagnostics; source tests also cover complete-line handling, read failure, unknown-source FAIL, and conflict. `tests/test_round_start_preparation.py::test_sample_json_parse_error_is_bilingual_in_session_and_audit` covers parser diagnostics and disk reconstruction; the Tk matrix covers incomplete JSONL → PASS, injected read failure, result persistence, and language refresh. `test_sample_platform_conflicts_stay_consistent_through_real_tk_and_disk_rebuild` covers applicable candidate resolution and bilingual refresh. |

`MonitorEvent` accepts an optional stable message ID, parameters, and diagnostic. `BaseMonitor` adds the station to each localized event's parameters before it captures the shared M2 `localized_message` (version 1, message ID, copied parameters, English/Traditional Chinese literals, optional diagnostic) at the common monitor-to-Session enqueue boundary. The table lists complete persisted parameters, including that shared station value. The existing legacy `message`, event type, machine evidence, round identity, and persistence path remain available. This uses the common event contract rather than creating a platform-specific translation or persistence layer. Source values, paths, timestamps, parser output, status codes, and diagnostics are not translated. Language refresh uses the captured message and does not poll/reparse sources or rewrite saved bytes. The table enumerates every platform-specific message ID currently declared in the two language catalogs; source-independent result, timeout, conflict and unknown-source decisions use M2's shared round event contract.

The inventory covers every declared M3 platform message ID and the real source/consumer paths named in the ticket. Platform-specific partial fixtures stay format-specific; candidates apply to Atlas and sample-json, while B482 batch mismatch and RS-WMT different-run cases remain warnings. Timeout is a shared RoundCoordinator behavior, covered once through the public round path rather than repeated as an unsupported platform-by-platform permutation.

## Evidence and acceptance status

| M3 criterion | Current evidence | Status |
| --- | --- | --- |
| 1. Supported platform events/errors use shared IDs/parameters and bilingual display/persistence. | The producer inventory above lists every declared ID and complete persisted parameters, including `station`, with producer, Session/audit and test links. Focused tests assert B482 batch/mismatch, RS-WMT batch, and all Sample JSON warning IDs and parameters. The real Tk matrix exercises normal result, partial source, and controlled read/parse error for Atlas DFU/FCT, B482, RS-WMT and sample-json through public preparation and RoundCoordinator, with fresh Session/audit readers. | Pass: every declared producer family and registered profile has linked evidence. |
| 2. Source values, identifiers and timestamps remain original. | Distributed platform and App tests verify captured filenames, paths, diagnostics, platform/round identity, source event persistence, timestamp/slot contracts, and explicit `unknown` where source facts are absent. No platform parser or source acceptance policy changed. | Pass: the criterion is covered across focused source and integration tests; a single combined matrix is not required. |
| 3. Equivalent English/Traditional Chinese operation preserves results, candidates, unknown-source FAIL, timeout and event identity. | Same-round source results for every registered platform are displayed and toggled English → Traditional Chinese → English in the Tk matrix; event IDs/order, round results and saved audit bytes stay fixed. Atlas unknown-identity FAIL and sample-json candidate/conflict behavior have dedicated real-Tk bilingual refresh cases. Shared Coordinator timeout has a dedicated controlled real-Tk refresh case. | Pass: each applicable policy branch is tested; candidate/unknown-source policies are only tested on platforms that produce those cases, and timeout is tested at its shared Coordinator seam. |
| 4. Raw parser/system diagnostic remains inspectable, outer message is translated, and language changes do not rewrite saved records. | True Tk App tests cover Sample JSON invalid-record diagnostics plus Atlas CSV parse, B482 signature and RS-WMT source-read diagnostics. Producer tests also assert each Sample JSON warning's raw diagnostic and bilingual message. Fresh audit and Session records contain the same localized message and raw diagnostic; visible text refreshes in both languages while saved audit bytes remain unchanged. | Pass: translated outer messages and original diagnostics are preserved and inspectable across source error families. |
| 5. Real temporary source across platforms, normal/partial/read-error cases, common round path, Tk display, fresh disk reconstruction, and parser regressions. | The true Tk matrix now drives all registered platform profiles through the public start/preparation path: Atlas DFU and FCT partial active CSV → final PASS, B482 partial CaseInfo and TestData PASS, RS-WMT partial live log → final CSV PASS, sample-json incomplete JSONL → PASS. Each platform also has a controlled source read/parse error displayed in Tk and reconstructed from fresh Session/audit readers. Existing Atlas/sample-json conflict/FAIL and shared timeout tests cover their applicable paths. Full suite result below. | Pass: normal, partial and read/parse error paths are exercised for every supported platform; source-format-specific candidate and shared timeout policies have separate evidence. |

The earlier review's Atlas/RS-WMT/B482 diagnostic defects and evidence gaps in criteria 1, 3 and 5 are addressed by the focused producer assertions and platform matrix above. Final fixed-base review of HEAD `99556a784a50e91262cb340ba89fcb8cfccd5555` found 0 Spec findings and 0 hard Standards violations; Standards recorded one non-blocking possible duplicate-error-reporting smell. The earlier inventory/test evidence wording was corrected and all five Sample JSON warning IDs have direct ID/parameter/diagnostic assertions. GitHub directly confirmed the ticket branch at `99556a784a50e91262cb340ba89fcb8cfccd5555`. Company Gitea synchronization is deferred until Monday at the user's direction; retain the M3 branch until Gitea is directly confirmed.

## Commands and results

Commands ran from `B518 Log Solution/` (the Python project root):

```sh
PYTHONPATH=src python3 -m unittest tests.test_log_monitoring tests.test_rswmt_monitoring tests.test_round_start_preparation tests.test_platform_registry tests.test_language_catalog tests.test_audit_records
# 95 tests, OK

PYTHONPATH=src python3 -m unittest tests.test_platform_registry.PlatformRegistryTests.test_sample_json_source_read_failure_is_reported_once_and_keeps_filename tests.test_log_monitoring tests.test_rswmt_monitoring tests.test_round_start_preparation tests.test_language_catalog
# 58 tests, OK after the final Sample JSON read-error adjustment

PYTHONPATH=src:tools:scripts:tests python3 -c 'import sys, unittest; suite=unittest.defaultTestLoader.discover("tests"); selected=unittest.TestSuite(); stack=[suite]; exec("while stack:\\n node=stack.pop()\\n if isinstance(node, unittest.TestSuite): stack.extend(list(node))\\n elif \"test_log_solution_ui\" not in node.id(): selected.addTest(node)"); result=unittest.TextTestRunner(verbosity=1).run(selected); sys.exit(not result.wasSuccessful())'
# 260 tests, OK; excludes the entire test_log_solution_ui module

B518_TK_TESTS=1 PYTHONPATH=src python3 -u -m unittest -v tests.test_log_solution_ui.LogSolutionUiTests.test_real_tk_language_menu_switches_main_page_and_persists_across_app_instances
# Initial sandbox run aborted while creating Tk, exit 134. Retried below in the authorized desktop session.

B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py
# Initial sandbox run aborted while creating Tk, exit 134. Retried below in the authorized desktop session.

python3 -c 'import tkinter as tk; root=tk.Tk(); root.destroy()'
# The ordinary shell cannot create Tk (exit 134); the authorized desktop run below succeeded.

B518_TK_TESTS=1 PYTHONPATH=src python3 -u -m unittest -v tests.test_log_solution_ui.LogSolutionUiTests.test_real_tk_language_menu_switches_main_page_and_persists_across_app_instances
# Passed in authorized desktop GUI session after correcting the audit-byte snapshot point.

B518_TK_TESTS=1 PYTHONPATH=src python3 -u -m unittest -v tests.test_log_solution_ui.LogSolutionUiTests.test_real_tk_start_button_prepares_every_registered_platform_profile
# Passed in authorized desktop GUI session; normal, partial and controlled source failure paths ran through Tk for every registered platform and rebuilt from Session/audit.

B518_TK_TESTS=1 PYTHONPATH=src python3 -m unittest -v tests.test_log_solution_ui.LogSolutionUiTests.test_unknown_atlas_identity_change_is_visible_as_fail_and_audited_without_reason
# Passed in authorized desktop GUI session; actual language-menu refresh preserves the unknown-source FAIL, round state, event identity, and audit bytes.

B518_TK_TESTS=1 PYTHONPATH=src python3 -m unittest -v tests.test_log_solution_ui.LogSolutionUiTests.test_sample_platform_conflicts_stay_consistent_through_real_tk_and_disk_rebuild
# Passed in authorized desktop GUI session; selected conflict/details and audit bytes stay stable across bilingual refresh.

B518_TK_TESTS=1 PYTHONPATH=src python3 -m unittest -v tests.test_log_solution_ui.LogSolutionUiTests.test_real_tk_timeout_event_language_refresh_preserves_round_and_audit
# Passed twice individually and in the final suite; controlled shared-round timeout stays visible and unchanged in audit across language refresh.

PYTHONPATH=src python3 -m unittest -v tests.test_log_monitoring.LogMonitoringTests.test_atlas_csv_parse_failure_is_reported_without_changing_source_result_policy tests.test_log_monitoring.LogMonitoringTests.test_b482_file_signature_failure_is_reported_as_bilingual_source_error tests.test_rswmt_monitoring.RsWmtTests.test_malformed_csv_warning_preserves_parser_diagnostic tests.test_round_start_preparation.RoundStartPreparationTests.test_sample_json_parse_error_is_bilingual_in_session_and_audit
# 4 tests, OK; real temporary source and Session/audit reconstruction.

B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py
# First run: 317 tests, one timeout UI snapshot race exposed. The test now waits for public round_ready state.
# Intermediate run after timeout-test fix: 317 tests, OK (79.404s), after 30f8702.
# Final run after all producer assertions: 317 tests, OK (88.328s), including Tk tests, after 9d35db3.

python3 -m compileall -q src tests
# Passed after source diagnostic fixes.

git diff --check
# Passed before the program/test commits.
```

The actual language button is clicked to open the Tk menu; the tests then use `Menu.invoke` for deterministic selection and verify rendered event text and state. This does not claim native menu-entry mouse selection or keyboard navigation as M3 evidence; M1's separate user-confirmed interaction evidence remains in its own ticket record. The exact full runner passed after rerunning it in an authorized desktop GUI session. The ordinary shell still aborts at Tk initialization; that environment distinction is recorded rather than treated as a product defect. The repository has no configured `mypy`, `pyright`, or other type-check command; no type-check pass is claimed.

Post-merge verification on `B518-Log-Solution`:

```sh
B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py
# Ran from B518 Log Solution/B518 Log Solution/: 317 tests, OK (89.830s)
```

Merge commit: `fb4ffb2286d9c113511482b738a101a11616bd14`. GitHub was directly queried after the push and returned this SHA for `refs/heads/B518-Log-Solution`; ticket branch `Multilingual/ticket-03` was directly confirmed at `c4f89723fe9bf0389b8df947c940eeeef2b2e537`. The Python project is nested under the Git root at `B518 Log Solution/`; the full-suite command must run from that directory. No program or test changes were made after the final review, only delivery-status documentation.

## Scope and remaining work

M3 changes platform-originated events only. M4 owns no-round App diagnostics; M5–M7 own other-window translation and close-language policy; M8 owns historical event recognition; M9 owns App-event retention; M10 owns full bundle/release verification. No parser acceptance, source identity policy, result/FAIL policy, timeout, product release, KVM, save, close, archival, or cleanup lifecycle was intentionally changed.

The earlier fixed-base review's criteria 1, 3 and 5 gaps were closed by producer inventory assertions, complete persisted-parameter evidence, the per-platform real Tk matrix, and bilingual refresh checks. All five Sample JSON warning IDs now have direct ID/parameter/diagnostic assertions. The final full suite passed 317 tests after `9d35db3`; the same full suite passed after GitHub merge `fb4ffb2286d9c113511482b738a101a11616bd14`. The fixed-base Standards review found no documented-standard violations and one non-blocking possible duplicated-error-reporting smell. The Spec review found no remaining product gap. GitHub directly confirmed the merged mainline and M3 branch. Company Gitea synchronization is deferred until Monday at the user's direction; retain the M3 and M2 ticket branches until Gitea is directly confirmed.
