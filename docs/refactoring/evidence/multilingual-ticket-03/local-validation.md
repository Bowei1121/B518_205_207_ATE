# M3 local validation: bilingual platform events

Date: 2026-10-08 (Asia/Taipei)

## Baseline, dependency, and destinations

- Fixed M3 review baseline: `c87c7bcefa334b96c420f255e8c1bf99e7a97370` (`B518-Log-Solution`). M2 is in its ancestry through merge `f128d9f963f60d416d0eaf5917fa5eda87408280`; the M2 implementation and evidence are present. The M2 dependency is resolved for this branch; the ticket README's older `Blocked by #15` text predates that merge.
- M2 evidence at this baseline records implementation `1d036f0339c2d37ac7907e46c31f92708909ea38`, 303 tests passing with Tk, no unresolved Standards/Spec findings, GitHub mainline merge, and Gitea synchronization deferred by the user until Monday. M3 does not include M2 fixes.
- M3 branch: `Multilingual/ticket-03`, created from the clean `B518-Log-Solution` baseline above. The fixed review base remains `c87c7bcefa334b96c420f255e8c1bf99e7a97370`.
- Program/test commits on the branch: `3c0b56f9f96196bdf4abc37cacebee68dea43233` (`Add bilingual platform event migration`), `ab09586d2a82108a1e56008e606afdc25b621f4c` (preserve Atlas/B482/RS-WMT source diagnostics), `a8cf2254daf95cb70c47ce2b2a59952a44694481` (true Tk bilingual refresh state assertions), `1394ea25f8dc0b88e896de0854bd0dccc074984e` (final test interaction adjustment), `35443b4` (true Tk unknown-source FAIL bilingual refresh and audit immutability), `5f1f4e8` (true Tk conflict candidates preserved through bilingual refresh), `65dcd18` (true Tk timeout event preserved through bilingual refresh), and `1ade6aba8bee543ce8e373cb54755aba5f244aa2` (final evidence update). A direct GitHub query after that push confirmed `refs/heads/Multilingual/ticket-03` at `1ade6aba8bee543ce8e373cb54755aba5f244aa2`.
- The evidence correction commit `8cb1d216e47aaef134cc307ebf8c178870f7de12` was also pushed and directly verified at GitHub `refs/heads/Multilingual/ticket-03`. It changes evidence and summary only; the last program/test validation remains `65dcd18`.
- Configured `origin` fetch URL is internal Gitea at `10.64.76.34:3000`; its push configuration also includes a GitHub push URL. A live `git ls-remote origin` attempt on 2026-10-08 waited 30 seconds without returning refs and was interrupted. Gitea state is unverified; no claim of synchronization is made. GitHub remains the only verified push destination for this batch.
- No GitHub issue was changed. Do not merge or remove the M3 branch until remaining acceptance, review, and destination checks complete.

## Producer inventory and event contract

| Platform | Migrated producers in this batch | Captured information |
| --- | --- | --- |
| Atlas DFU/FCT | source snapshot ready, trusted serial locked, final result, unresolved source-identity conflict, source read failure | Stable `platform.atlas.*` IDs, slot/status or filename parameters, raw source diagnostic; source observations still drive the existing result path. |
| B482 BT | batch observed, batch mismatch, source read failure | Stable `platform.b482.*` IDs, batch/slot or filename parameters, raw evidence/exception; existing same-round and FAIL behavior retained. |
| RS-WMT BT | batch and source warning/read/parse failures | Stable `platform.rswmt.*` IDs, filename parameter and raw warning diagnostic; existing polling and acceptance policy retained. |
| sample-json FCT | invalid/unsupported record, invalid fields/status, unreadable source | Stable `platform.sample_json.*` IDs, captured filename and raw diagnostic; source identity remains the filename and read failure is reported once. |

`MonitorEvent` accepts an optional stable message ID, parameters, and diagnostic. At the common monitor-to-Session enqueue boundary, the event captures the shared M2 `localized_message` (version 1, message ID, copied parameters, English/Traditional Chinese literals, optional diagnostic). The existing legacy `message`, event type, machine evidence, round identity, and persistence path remain available. This uses the common event contract rather than creating a platform-specific translation or persistence layer. Source values, paths, timestamps, parser output, status codes, and diagnostics are not translated. Language refresh uses the captured message and does not poll/reparse sources or rewrite saved bytes.

The inventory covers the producer paths touched by M3 and the exercised source/read/parse error paths. It does not claim exhaustive coverage of every platform diagnostic or every possible partial-source permutation.

## Evidence and acceptance status

| M3 criterion | Current evidence | Status |
| --- | --- | --- |
| 1. Supported platform events/errors use shared IDs/parameters and bilingual display/persistence. | Atlas, B482, RS-WMT and sample-json producers use the M2 event contract. A real Tk App test drives controlled Atlas CSV parse, B482 file-signature and RS-WMT source-read errors through the common round; it verifies visible English/Traditional Chinese text and matching Session/audit records. Sample-json read/parse errors have corresponding true Tk and disk tests. | Partial: the complete platform event producer inventory is not exhaustively exercised. |
| 2. Source values, identifiers and timestamps remain original. | Tests verify captured filenames, paths, diagnostics, platform/round identity, source event persistence and existing timestamp/slot contracts; `unknown` remains explicit where source facts are absent. No platform parser or source acceptance policy changed. | Partial: not every platform field is asserted in one integrated matrix. |
| 3. Equivalent English/Traditional Chinese operation preserves results, candidates, unknown-source FAIL, timeout and event identity. | In the true Tk per-platform diagnostic path, switching English → Traditional Chinese → English preserves `round_id`, coordinator events, results, Session/audit event identity, and audit bytes. The Atlas unknown-source identity-change FAIL test verifies FAIL/result/event state and audit bytes remain unchanged. The sample-json multi-candidate true Tk case verifies selected conflict, candidate snapshot, details, and audit bytes remain unchanged. A controlled shared-round timeout event is shown in true Tk; changing language preserves its round snapshot, event and audit bytes. | Partial: this controlled timeout and the candidate/normal-result policy scenarios are not replayed through every platform under both languages. |
| 4. Raw parser/system diagnostic remains inspectable, outer message is translated, and language changes do not rewrite saved records. | True Tk App tests cover Sample JSON invalid-record diagnostics plus Atlas CSV parse, B482 signature and RS-WMT source-read diagnostics. Fresh audit and Session records contain the same localized message and raw diagnostic; visible text refreshes in both languages while saved audit bytes remain unchanged. | Pass for exercised source-error paths; broader platform diagnostics remain partial. |
| 5. Real temporary source across platforms, normal/partial/read-error cases, common round path, Tk display, fresh disk reconstruction, and parser regressions. | Full suite passed 314 tests, including real Tk start/error-display paths for registered platforms, B482 normal result display, Sample JSON conflict/reconstruction, and source-adapter partial/normal/parser regressions. Atlas/B482/RS-WMT injected errors were reconstructed from Session/audit and displayed in the App. | Partial: there is not yet one complete all-platform matrix covering every normal, partial, candidate, timeout and disk-reconstruction combination. |

The ticket's acceptance checkboxes remain unchecked until the remaining matrix is closed. The prior review's Atlas/RS-WMT/B482 diagnostic defects are fixed. The remaining Spec gap is the full cross-platform normal/partial/candidate/unknown-source/timeout equivalence matrix under both languages. GitHub was directly confirmed at `8cb1d216e47aaef134cc307ebf8c178870f7de12`; company Gitea is not reachable from this offsite session and, per the user's instruction, synchronization is deferred until Monday. Keep the M3 branch until the remaining acceptance is complete and Gitea synchronization can be confirmed.

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
# Passed in authorized desktop GUI session; injected Atlas/B482/RS-WMT source failures were visible, persisted in Session/audit, and remained state-stable during language refresh.

B518_TK_TESTS=1 PYTHONPATH=src python3 -m unittest -v tests.test_log_solution_ui.LogSolutionUiTests.test_unknown_atlas_identity_change_is_visible_as_fail_and_audited_without_reason
# Passed in authorized desktop GUI session; actual language-menu refresh preserves the unknown-source FAIL, round state, event identity, and audit bytes.

B518_TK_TESTS=1 PYTHONPATH=src python3 -m unittest -v tests.test_log_solution_ui.LogSolutionUiTests.test_sample_platform_conflicts_stay_consistent_through_real_tk_and_disk_rebuild
# Passed in authorized desktop GUI session; selected conflict/details and audit bytes stay stable across bilingual refresh.

B518_TK_TESTS=1 PYTHONPATH=src python3 -m unittest -v tests.test_log_solution_ui.LogSolutionUiTests.test_real_tk_timeout_event_language_refresh_preserves_round_and_audit
# Passed twice individually and in the final suite; controlled shared-round timeout stays visible and unchanged in audit across language refresh.

PYTHONPATH=src python3 -m unittest -v tests.test_log_monitoring.LogMonitoringTests.test_atlas_csv_parse_failure_is_reported_without_changing_source_result_policy tests.test_log_monitoring.LogMonitoringTests.test_b482_file_signature_failure_is_reported_as_bilingual_source_error tests.test_rswmt_monitoring.RsWmtTests.test_malformed_csv_warning_preserves_parser_diagnostic tests.test_round_start_preparation.RoundStartPreparationTests.test_sample_json_parse_error_is_bilingual_in_session_and_audit
# 4 tests, OK; real temporary source and Session/audit reconstruction.

B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py
# 314 tests, OK (68.155s), including Tk tests, after test commit 65dcd18

python3 -m compileall -q src tests
# Passed after source diagnostic fixes.

git diff --check
# Passed before the program/test commits.
```

The actual language button is clicked to open the Tk menu; the tests then use `Menu.invoke` for deterministic selection and verify rendered event text and state. This does not claim native menu-entry mouse selection or keyboard navigation as M3 evidence; M1's separate user-confirmed interaction evidence remains in its own ticket record. The exact full runner passed after rerunning it in an authorized desktop GUI session. The ordinary shell still aborts at Tk initialization; that environment distinction is recorded rather than treated as a product defect. The repository has no configured `mypy`, `pyright`, or other type-check command; no type-check pass is claimed.

## Scope and remaining work

M3 changes platform-originated events only. M4 owns no-round App diagnostics; M5–M7 own other-window translation and close-language policy; M8 owns historical event recognition; M9 owns App-event retention; M10 owns full bundle/release verification. No parser acceptance, source identity policy, result/FAIL policy, timeout, product release, KVM, save, close, archival, or cleanup lifecycle was intentionally changed.

Final code review against fixed base `c87c7bcefa334b96c420f255e8c1bf99e7a97370`: Standards found no documented-standard violations; duplicated source-error handling is a non-blocking judgment call. Spec review confirms the three diagnostic gaps and cross-platform Tk error evidence are addressed, but calls the full two-language normal/partial/candidate/unknown-source/timeout matrix partial. Do not mark those acceptance items complete until that matrix has evidence. Project type-checker configuration was not found; no type-check pass is claimed. The evidence correction commit `8cb1d216e47aaef134cc307ebf8c178870f7de12` was directly confirmed on GitHub; company Gitea synchronization is deferred until Monday at the user's direction. Do not merge or delete branches while the matrix remains incomplete.
