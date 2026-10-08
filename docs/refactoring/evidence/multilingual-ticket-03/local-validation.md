# M3 local validation: bilingual platform events

Date: 2026-10-08 (Asia/Taipei)

## Baseline, dependency, and destinations

- Fixed M3 review baseline: `c87c7bcefa334b96c420f255e8c1bf99e7a97370` (`B518-Log-Solution`). M2 is in its ancestry through merge `f128d9f963f60d416d0eaf5917fa5eda87408280`; the M2 implementation and evidence are present. The M2 dependency is resolved for this branch; the ticket README's older `Blocked by #15` text predates that merge.
- M2 evidence at this baseline records implementation `1d036f0339c2d37ac7907e46c31f92708909ea38`, 303 tests passing with Tk, no unresolved Standards/Spec findings, GitHub mainline merge, and Gitea synchronization deferred by the user until Monday. M3 does not include M2 fixes.
- M3 branch: `Multilingual/ticket-03`, created from the clean `B518-Log-Solution` baseline above. The fixed review base remains `c87c7bcefa334b96c420f255e8c1bf99e7a97370`.
- First program batch: `3c0b56f9f96196bdf4abc37cacebee68dea43233` (`Add bilingual platform event migration`), pushed to GitHub branch `Multilingual/ticket-03`; direct GitHub ref checks confirmed the branch at that SHA and mainline at the fixed baseline before documentation work.
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

This producer list is based on the changed platform paths and tests in this batch, not a claim that every possible platform diagnostic has been exhaustively enumerated. Remaining producer inventory and UI diagnostic review are open acceptance work.

## Evidence and acceptance status

| M3 criterion | Current evidence | Status |
| --- | --- | --- |
| 1. Supported platform events/errors use shared IDs/parameters and bilingual display/persistence. | Stable producer IDs added across Atlas, B482, RS-WMT, sample-json; common `BaseMonitor` captures localized values before Session enqueue. Focused tests cover common capture, migrated errors, platform registry and prepared-round persistence. Full GUI display and all producer inventory still need completion. | Partial |
| 2. Source values, identifiers and timestamps remain original. | New parameters use captured source names, slots, batch/status values or parser diagnostics; tests protect sample-json filename identity and existing platform/round behavior. The full cross-platform source/value matrix has not yet been run. | Partial |
| 3. Equivalent English/Traditional Chinese operation preserves results, candidates, unknown-source FAIL, timeout and event identity. | Existing M2 round contract plus focused platform and preparation tests pass; no complete two-language, all-platform equivalence matrix has been run for M3. | Partial |
| 4. Raw parser/system diagnostic remains inspectable, outer message is translated, and language changes do not rewrite saved records. | The true-Tk sample-json App test reads an invalid source record through the actual app and common round, checks the bilingual audit/session diagnostic, changes language through the visible menu, and compares audit bytes immediately before and after the language-only refresh. Its first run exposed a test snapshot taken before later legitimate source events; after moving the byte baseline immediately before the language operation, it passed. | Pass for sample-json path; broader platform UI detail remains partial |
| 5. Real temporary source across platforms, normal/partial/read-error cases, common round path, Tk display, fresh disk reconstruction, and parser regressions. | The complete suite, including real Tk UI tests and source adapter/preparation/audit reconstruction regressions, passed 310 tests. The true-Tk language refresh integration passed. Platform-specific normal/partial/read-error adapter coverage is present in focused/full tests; the full product-level error-display matrix across every platform has not been run as one integrated matrix. | Partial |

No M3 acceptance checkbox is marked complete in the ticket. The true-Tk sample-json path and complete suite now pass, but the full cross-platform equivalence and error-display matrix and fixed-base review remain open.

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

B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py
# 310 tests, OK (69.502s), including Tk tests

git diff --check
# Passed before the program commit
```

The exact full runner passed after rerunning it in an authorized desktop GUI session. The ordinary shell still aborts at Tk initialization; that environment distinction is recorded rather than treated as a product defect. The repository has no configured `mypy`, `pyright`, or other type-check command; no type-check pass is claimed.

## Scope and remaining work

M3 changes platform-originated events only. M4 owns no-round App diagnostics; M5–M7 own other-window translation and close-language policy; M8 owns historical event recognition; M9 owns App-event retention; M10 owns full bundle/release verification. No parser acceptance, source identity policy, result/FAIL policy, timeout, product release, KVM, save, close, archival, or cleanup lifecycle was intentionally changed.

Before merge: complete the all-platform two-language equivalence and integrated error-display evidence, run fixed-base Standards/Spec review and resolve findings, rerun affected tests, refresh evidence with final verified SHA, then recheck all push destinations. Keep the branch if any requirement remains blocked.
