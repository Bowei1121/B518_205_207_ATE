# H3 local validation — complete paging and selected detail

Date: 2026-10-13 (Asia/Taipei)

## Baseline and dependency check

- Repository: `B518-Log-Solution`; Python project: `B518 Log Solution/`.
- H3 fixed review base before implementation: `d0a244b6b53a31e1fc9e57ceefcf9d9f1e959f79`.
- H1 and H2 were already ancestors of this base. H1 evidence is [H1 local validation](../historical-event-query-ticket-01/local-validation.md); H2 evidence is [H2 local validation](../historical-event-query-ticket-02/local-validation.md). The base contains their actual history-page search, date/local-time rules, mixed-source precedence, initial 100-row result, async query entry, generation/cancel lifecycle, and true-Tk evidence. H2 is preserved where present; H3 does not make H2 completion an extra dependency.
- Git ancestry and the checked-in evidence were cross-checked against the actual source and tests. The baseline history page still exposed only H1's initial result; H3 replaces that limitation. The root ticket, module docstring, and historical spec descriptions were updated where they were stale.
- This delivery adds no persistent index and makes no cross-query incremental-read claim. H4 owns those guarantees. H5–H8 and factory acceptance remain separate.

## Entry and responsibility inventory

| Route | Before / responsibility | H3 behavior and evidence |
| --- | --- | --- |
| Actual history page search | H1 validates and freezes date/timezone, reads saved audit, old `events.log`, and App events in the background, and publishes up to 100 summaries. H2 owns request generation/cancel/window lifecycle. | Same query entry and H2 lifecycle now publish an immutable paged snapshot; only successful current requests replace the visible result. |
| Audit / old log / App journal | Existing source precedence, event identity, time normalization, and de-duplication remain in `historical_event_display.py`. | Audit and App-event stores are validated and streamed; legacy lines are read incrementally. Query order is fixed once and stable across page boundaries. |
| Page navigation | H1 had a first-page stage hint and no complete page traversal. | Real history-window left/right buttons request a snapshot page; page info and first/last disabled directions reflect the fixed total. Navigation never calls the source readers again. |
| Selected detail | Existing detail/localization contract supplies original text and bilingual fields. | The selected event's raw record is retrieved from the snapshot only after selection and read asynchronously. A late detail request cannot replace the current selected row's detail. |
| Snapshot ownership | Not present in H1. | Query result owns a temporary SQLite database; replacement closes the old result, app-owned service closes on app/window destruction, and detail/page readers are bounded and shut down with their owner. |
| Language refresh / close | H1/H2 existing behavior preserves selected/read state and Tk lifecycle. | Page status is rendered in the current language without source rescan. All widget/variable updates are delivered by Tk polling on the UI thread. |

## Seven acceptance checks

1. **Page controls and boundaries — passed.** Public query result exposes page count and `get_page`; UI has only left/right arrows plus page information. Tests cover empty, one event, exactly 100, 101, 205 and multiple pages; first/last navigation is bounded and disabled correctly. The real Tk test clicks arrows through first, middle, last, and back to the prior page.
2. **Identity, stable order, no gaps/duplicates — passed.** The three-page audit/App fixture checks the concatenated page identity sequence and a numeric sequence ordering boundary. Query keys and sort values are fixed at submission; page navigation reads a SQL range from the snapshot and does not re-enumerate input sources.
3. **Compact result and on-demand detail — passed.** In-memory page records contain only list summary/identity fields. Raw event JSON and original diagnostics are held in the temporary snapshot, fetched only for the selected identity. `test_list_message_does_not_format_full_detail_until_record_is_selected` and the real Tk selection test cover this. A controlled 205-event fixture with 45,500-character detail strings produced 9,419,450 source bytes and a 28,590,080-byte SQLite snapshot; tracemalloc peak during query was 714,189 bytes, each requested page was 100/100/5, and the selected long detail was then retrieved intact. This is a reproducible engineering sample, not the H8 capacity claim.
4. **Fixed result boundary — passed.** Appending an event after query completion does not change the active snapshot or any page. A new query includes it. Source-file replacement after the streaming reader pins its opened file cannot redirect the active iteration to unrelated content. The real Tk test also verifies the set stays stable while paging.
5. **Mixed sources and original/bilingual display — passed.** The real Tk fixture combines audit and App events, traverses all pages, checks identity/order and selected long original detail, and confirms the H1 first-page-only hint is absent. Existing source priority and bilingual display are retained.
6. **Public flow, real Tk and read-only source — passed.** Verification uses the public query service and actual history window, true Tk widgets, controlled source data and page-button event input. Audit, legacy/App source bytes remain unchanged. A barrier-blocked selected-detail read does not prevent actual Tk date-field editing or pagination widgets from responding.
7. **Necessary tests and regressions — passed after final full-suite run.** H1/H2 lifecycle, existing historical display/localization, application UI, and complete suite are recorded below. No original records, monitoring, arbitration, retention, or cleanup policy was changed. Factory acceptance is separate.

## Commands and observed results

Commands run from `B518 Log Solution/`:

```text
PATH=/opt/anaconda3/bin:$PATH B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py
PYTHONPATH=src python3 -m unittest tests.test_app_event_store tests.test_historical_event_display tests.test_historical_event_query
python3 -m py_compile src/app_event_store.py src/audit_records.py src/b518_log_solution.py src/historical_event_display.py src/historical_event_query.py src/language_catalog.py
git diff --check
```

- Runtime used for real Tk: `/opt/anaconda3/bin/python3`, Python 3.11.7, Aqua Tcl/Tk 8.6.12, logged-in macOS desktop. The whole suite was run in the accessible desktop session; no Tk test was skipped. Final full-suite result after the review fix: 429 tests, 143.026 seconds, exit 0. An earlier full run on the same runtime had one error from `TemporaryDirectory` cleanup in `test_archive_check_racing_a_new_round_event_seals_the_latest_disk_contents`; the case passed alone and the 17-test `test_round_archival` module passed, then the complete suite passed. The initial failure is retained here rather than represented as a pass.
- Focused history/source tests: 55 tests passed after the final streaming-reader refactor.
- Four real-Tk H1/H2/H3 plus integrated language-refresh tests passed after the page/detail request race was fixed.
- `py_compile` and `git diff --check` passed after the final source-reader refactor.
- No repository type-checker configuration was found; no type-check pass is claimed.
- Source-byte checks are separated from the disposable SQLite snapshot bytes. Reading, paging, selection, and language refresh did not rewrite source audit/App-event files.

## Review, final revision, and limits

- Fixed Standards/Spec review base remains `d0a244b6b53a31e1fc9e57ceefcf9d9f1e959f79`. Standards found a close/open race where SQLite could create a new empty file after snapshot removal; the snapshot now opens read-only and a barrier-controlled regression proves that the path stays absent. Spec review found no blocking gaps or scope creep. Non-blocking notes: page-read failures leave the prior page visible without a localized recovery message (full recovery UX is H5); `HistoricalEventDetailService` also owns page-read coordination, so its name is slightly narrow. Program/test commits are `f8efec9` and `f17f62b`; the latter is the final code/test revision. Both configured push destinations accepted `f17f62b`. Final documentation commit and direct destination SHA checks are recorded after those steps occur.
- H3 may perform the initial query's background source scan. It does not provide H4's durable index, reuse after restart, or guarantee that a later query avoids scanning unchanged sources. H5's full recovery surface, H6's cleanup/save race integration, H7's complete icon/keyboard/localization contract, and H8 capacity/full-spec closeout are not claimed.
- Physical mouse hardware is not separately claimed: Tk event-driven widget input was used for the actual arrow controls. The app's real window and Tk lifecycle were exercised.
- No external parent issue was modified. The first complete-suite attempt's temporary-cleanup error was investigated as above and did not recur in the isolated case, archival module, or final full run. Commit, merge, direct remote SHA checks, ticket branch cleanup, and final document SHA are added after those steps occur.

## Mainline integration verification

- The H3 branch was fast-forward merged into `B518-Log-Solution`: base `d0a244b6b53a31e1fc9e57ceefcf9d9f1e959f79` → merge result `75adc7623fc0b2313cbfc231766b5e4edb15b017`; no merge commit was created.
- After switching to the merged mainline, the complete desktop Tk suite was run again with `PATH=/opt/anaconda3/bin:$PATH B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py` from `B518 Log Solution/`, using `/opt/anaconda3/bin/python3` 3.11.7 and Aqua Tcl/Tk 8.6.12. Result: 429 tests passed in 143.660 seconds, exit 0.
- Final code/test revision: `f17f62b` (`Prevent snapshot recreation during page reads`). Mainline integration result: `75adc7623fc0b2313cbfc231766b5e4edb15b017`. The post-merge run confirms the integrated code on the target branch; documentation-only finalization and direct push-destination checks are recorded in the final addendum below.
