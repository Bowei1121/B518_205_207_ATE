# L2 local validation — 2026-10-12

## Git baseline and dependency

- Repository root: `/Users/tsengbowei/Desktop/公司資料/專案/FQ III/2026/B518/專案名稱/3. 程式/0. PC/B518 Log Solution`; Python application: `B518 Log Solution/`.
- Dedicated worktree: `/private/tmp/B518-LanguageRefresh-ticket-02`; branch: `LanguageRefresh/ticket-02`.
- Fixed Standards/Spec review base: `7071ea1065c21fa93612a30ccca64d85840e185b` (the `B518-Log-Solution` source/test baseline before L2 changes). Do not advance this base when adding evidence or commits.
- Initial direct query: GitHub and Gitea `B518-Log-Solution` both resolved to `7071ea1065c21fa93612a30ccca64d85840e185b`; neither had a `LanguageRefresh/ticket-02` ref. Existing `github` points to GitHub; `origin` fetches Gitea and has Gitea plus GitHub push URLs. No destination was removed. Re-query every push destination after each push and record final refs below.
- The formal `B518-Log-Solution` worktree had pre-existing edits to `docs/refactoring/PROJECT_SUMMARY_2026-10-09.md` and `PROJECT_SUMMARY_2026-10-12.md`. L2 was isolated in a separate worktree; those edits are excluded from all L2 commits. Other existing worktrees (`Mac mini` / `main`, `Mac mini-BT-Codex` / `BT-Codex`) were left unchanged.
- L1 is an ancestor of the fixed base. Its delivered code, tests and evidence were checked in the source and in [L1 local validation](../language-refresh-ticket-01/local-validation.md); L1 acceptance and review are complete. This confirms the direct dependency without relying on the branch name or checkbox alone. M1–M9 and C1–C4 remain outside L2 changes.

## Window, entry and refresh inventory

| View / entry | Before L2 | L2 change and proof | Boundary |
| --- | --- | --- | --- |
| Main language menu / `<<AppLanguageChanged>>` | L1 owns the global current language, preference persistence, root notification, receiver isolation, aggregate status and manual retry. | Kept unchanged. Actual language-button/menu interaction is used in the three-window Tk integration test. | No new language preference or event bus. |
| Settings Toplevel: configuration, events/Session, retention tabs | Main refresh manually called `_apply_settings_language`; opening built current text. Profile draft and validation statuses are separate Tk variables. | Settings now registers its in-place label/tab/status renderer as an L1 receiver. Root-language fanout no longer calls it. The live test retains an unsubmitted project draft and selected tab; existing invalid-draft test remains in the focused regression set. | Normal profile, retention and file-dialog operations are unchanged; no M5 behavior rework. |
| App diagnostics Toplevel | Main refresh forced a fresh event-store read and rebuilt the list/detail. Close button and WM close destroyed directly. | Diagnostics registers once per Toplevel. Event rows/details render from the last public App-event snapshot on language change; event ID selection and list/detail reading position are retained. Close/WM/external destroy all detach that view. | Normal store revision refresh, user selection, save retry and App-event collection still use existing behavior. |
| Historical events Toplevel | Main refresh called the historical renderer directly; the renderer reads `_historical_event_records`, which is populated at open or explicit Reload. | History registers once per Toplevel and translates the in-memory read snapshot. Selected `HistoricalEvent.key`, list/detail reading position and existing source order remain. Repeated language notifications coalesce the owned idle scroll-restore callback. WM close, explicit close and external destruction detach the view. | Explicit Reload and existing hidden-window reopen still perform the existing read; the language notification does not call the source reader. |
| App-owned notices | L1 registers and unregisters each live notice with its original modal behavior. | Untouched; the three L2 views join the same public registration boundary. | Other not-yet-migrated L3 views retain their old refresh path. |
| Refresh failure / retry | L1 aggregates active failures and logs fixed bilingual App diagnostics with its existing durable retry path. | A forced settings-title failure demonstrates that diagnostics/history still update, the main aggregate remains visible, and the same settings window recovers on manual retry in the latest language without losing its draft. The failure record is rebuilt from a fresh disk reader and has no `round_id`. | No automatic retry or refresh-generated business operation. |

### Language vs. normal data refresh

The language receiver only re-renders the settings widgets, the diagnostics window's cached App-event records and the historical window's cached `HistoricalEvent` records. It does not read historical sources or ask `RoundCoordinator` for a new diagnostics record collection. New App events still use the normal public revision refresh; user-selected historical Reload still calls the existing reader. The main receiver still refreshes main-page, conflict, alarm and close surfaces because those are not migrated until L3. Their migration and L4 removal of every old language fanout remain pending.

## TDD and runtime

- TDD red phase: against the fixed `7071ea1` baseline in a temporary detached worktree, the new Tk failure-isolation test failed: the legacy main-page callback stopped on the settings failure, so the aggregate named only the main page and later receivers did not finish. The temporary baseline worktree was removed after this check.
- Green phase: same real-Tk acceptance passed after settings, diagnostics and history registered independently with L1.
- Spec-review evidence additions: actual App-diagnostics detail scrolling was moved to a non-default position over a long persisted raw diagnostic and remained at that position after a real language-menu switch. A real-Tk failure matrix now injects a refresh exception independently into Settings, App Diagnostics, History, and simultaneously into Settings plus Diagnostics; other views update, the retry remains visible, and the real retry button refreshes the same windows in the latest language while retaining the settings draft.
- `python3` resolves to `/Library/Frameworks/Python.framework/Versions/3.8/bin/python3` (Python 3.8.10, Tk 8.6). A restricted Tk attempt aborts before window creation; with authorized desktop command execution, the full required suite ran successfully on that interpreter. The focused real-Tk tests also passed with `/opt/anaconda3/bin/python3.11` (Python 3.11.9, Tk 8.6). Record the exact interpreter used for each command.
- Type-check configuration search found no `pyproject.toml`, `setup.cfg`, `tox.ini`, mypy/ruff config or project type-check command. Type checking is not claimed and no type-check setup was added.

## Acceptance evidence

1. **Settings, diagnostics and history use L1; redundant language fanout removed — pass.** `test_integrated_language_refresh_keeps_open_settings_diagnostics_and_history` opens all three actual Toplevels and switches via the actual language button/menu. Titles, settings labels, diagnostic/history rows and details update in place. The test blocks both App-event and historical-source reads during the language notification; the views still refresh from snapshots. Other L3 surfaces retain the legacy path.
2. **Drafts/input/validation survive, no auto-submit or source reload — pass for covered flows.** The integrated test retains an unsaved project name and selected tab through both languages; `test_open_settings_refreshes_language_in_place_and_keeps_invalid_draft` verifies an invalid draft remains invalid and unchanged. The first test also forbids source reads during language refresh. Existing apply/cancel/load and configuration tests are included in the full suite. Exhaustive valid/partial/empty field permutations are not claimed.
3. **Diagnostic/history selection, reading and scroll preserved — pass for tested flows.** The integrated test keeps selected App-event and historical-event rows and compares details in both languages. `test_real_tk_historical_reader_selects_and_localizes_disk_records_without_rewriting` checks selected event key, long diagnostic text and list/detail reading positions while comparing audit bytes. `test_app_diagnostics_scroll_position_survives_language_refresh` scrolls a long raw diagnostic in the actual App diagnostics Toplevel and verifies the same event and visible text position after a real menu switch.
4. **Close/destroy/hide/reopen lifecycle — pass for covered entry points.** The real-Tk integration test closes Settings through its registered WM protocol, destroys Diagnostics directly, hides and re-shows History, then reopens Settings/Diagnostics and confirms the live current language. `<Destroy>` handlers release only their own registration, and History hide retains its live Toplevel. Existing root-destroy/Tk lifecycle regression also ran in the full suite. Native window-manager close interaction is represented by invoking its registered Tcl protocol; a separate physical title-bar click is not claimed.
5. **Failure isolation, aggregate, diagnostics and latest-language retry — pass.** `test_settings_refresh_failure_isolated_and_retried_from_main_window` injects a settings Toplevel failure and verifies diagnostics/history continue. `test_each_reader_refresh_failure_isolated_and_retryable` separately fails each of the three L2 receivers and then two simultaneously; the other receivers still update, the nonblocking main banner stays available, and real manual retry updates the same windows in the latest language without losing the draft. The bilingual failure event is checked in memory and after `read_app_event_store` rebuild; raw exception and no-round linkage are retained.
6. **Real Tk, bytes and diagnostic disk behavior — pass for tested records.** The integrated test compares App-event file bytes and store revision before/after ordinary language switches. The historical reader test compares audit bytes before/after language switches and retains original long diagnostic / legacy content. The failure-recovery test separately confirms its newly created diagnostic is persisted and visible through a fresh reader. A separate explicit bytes hash for every App, Session and maintenance-summary file was not needed beyond these fixtures and is not claimed.
7. **Existing settings/readers/save behavior and native file-dialog boundary — pass by regression suite.** Focused settings, history and App diagnostics tests passed; `test_file_dialog_buttons_use_current_language_and_cancel_without_changes` confirms App-supplied labels follow the selected language and cancel preserves the path draft. Existing M5–M9, persistence and close regression cases ran in the full suite. Actual native system dialog visual text is OS-controlled; this ticket does not claim an OS-level dialog screenshot or file pick.

## Commands and results

Focused green real-Tk set (Python 3.11.9 / Tk 8.6):

```text
B518_TK_TESTS=1 PYTHONPATH=src /opt/anaconda3/bin/python3.11 scripts/run_tests.py \
  test_log_solution_ui.LogSolutionUiTests.test_integrated_language_refresh_keeps_open_settings_diagnostics_and_history \
  test_log_solution_ui.LogSolutionUiTests.test_settings_refresh_failure_isolated_and_retried_from_main_window \
  test_log_solution_ui.LogSolutionUiTests.test_open_settings_refreshes_language_in_place_and_keeps_invalid_draft \
  test_log_solution_ui.LogSolutionUiTests.test_real_tk_historical_reader_selects_and_localizes_disk_records_without_rewriting
Ran 4 tests ... OK
```

Additional review-gap real-Tk tests (Python 3.11.9 / Tk 8.6):

```text
B518_TK_TESTS=1 PYTHONPATH=src:tests /opt/anaconda3/bin/python3.11 scripts/run_tests.py \
  test_log_solution_ui.LogSolutionUiTests.test_each_reader_refresh_failure_isolated_and_retryable \
  test_log_solution_ui.LogSolutionUiTests.test_app_diagnostics_scroll_position_survives_language_refresh
Ran 2 tests ... OK
```

`PYTHONPATH=src /opt/anaconda3/bin/python3.11 scripts/run_tests.py test_language_catalog` passed 6 tests. `python3 -m compileall -q src tests` and `git diff --check` passed.

Required full suite (from `B518 Log Solution/`, desktop Tk access):

```text
B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py
Ran 381 tests in 108.360s — OK
Interpreter: /Library/Frameworks/Python.framework/Versions/3.8/bin/python3, Python 3.8.10; Tk 8.6
Tested implementation/test SHA: 3b80c0c23e662c0c8cb218a845fa86c714e87998
```

Full suite attempts before the final additional L2 tests: 379 tests each, with one temporary-directory teardown failure per run. The failure signatures were `test_destroyed_ui_is_safe_when_next_worker_collects_cycles` and `test_unknown_atlas_identity_change_is_visible_as_fail_and_audited_without_reason`; both failing tests passed when run alone immediately afterward. The destroyed-UI test was also rerun on the fixed pre-L2 baseline and exhibited the same cleanup exception once in three isolated runs (other attempts passed), confirming that failure is pre-existing and intermittent. The new per-view failure and diagnostics-scroll tests then passed in a focused real-Tk run. Final full-suite run after these additions passed 381 tests in 108.360 seconds with Tk enabled; earlier failures remain reported and are not counted as passes.

## Review / parent-spec coverage / delivery

- Fixed review base: `7071ea1065c21fa93612a30ccca64d85840e185b`.
- Standards source documents checked: `AGENTS.md`, `docs/agents/domain.md`, and `docs/agents/issue-tracker.md`; no separate contributing/style/type-check configuration was found.
- Final Standards review against fixed base `7071ea1065c21fa93612a30ccca64d85840e185b` found no documented-standard violation. Its only observation is non-blocking: the new real-Tk tests repeat a small language-menu setup; extracting a helper is optional.
- Final Spec review against the same fixed base found no blocking requirement gap, behavior defect or scope creep. It confirmed the per-view failure matrix, simultaneous failures, latest-language retry, reader snapshot rendering and non-default App Diagnostics scroll evidence. The review noted that lifecycle evidence invokes Settings' WM protocol, directly destroys Diagnostics, and hides/reopens History; it does not physically click the Diagnostics close button/title-bar. Both the button and WM route to the same cleanup helper, and the evidence does not claim a physical title-bar click.
- The final reviews inspected the delivered source, tests and documentation at `8690529118fa3e121097cda0d240562ce066b4af`, using the unchanged fixed baseline above. The earlier Spec evidence gaps were closed in `3b80c0c`; no source or test changes followed. The remaining lifecycle observation is an evidence limitation only, not an identified product defect or ticket blocker.
- Direct remote query before merge (2026-10-12 09:28 UTC): Gitea and GitHub both reported `B518-Log-Solution` at `7071ea1065c21fa93612a30ccca64d85840e185b` and `LanguageRefresh/ticket-02` at `8690529118fa3e121097cda0d240562ce066b4af`.
- Applicable parent scenario coverage is limited to: settings draft preservation; diagnostic/history reading and unchanged bytes; window-open/close/hide/reopen behavior; individual failure isolation and retry; native-dialog App/system text boundary; existing bilingual diagnostic/storage regression. Conflict/alarm/close-window migration remains L3; removal of every old fanout and parent-wide first criterion remains L4. This is not a claim that the parent first criterion or all windows are complete.
- L2 does not modify C1–C4, generic event infrastructure, configuration behavior, monitor/adjudication/save/close/archive/cleanup/KVM policy or bundle validation. L3/L4 remain outstanding.

## Integration on `B518-Log-Solution`

- After the seven L2 acceptance items and both fixed-base reviews passed, the clean formal worktree fast-forwarded from `7071ea1065c21fa93612a30ccca64d85840e185b` to `a4552be503af64a2e14e4fb2bf975906cfe40ed7` on 2026-10-12. This is a fast-forward delivery SHA, not a separately created merge commit.
- Before merging, the two pre-existing dirty project-summary edits were copied to `/private/tmp`, checksum-verified, and stashed by exact path. After merge and test, the stash was restored. `PROJECT_SUMMARY_2026-10-09.md` matches its pre-merge SHA `4e94ce21a95925ca0d16c825bc7e1d8ba6452442e139e6ba4c755e3f22973bc1`; the restored `PROJECT_SUMMARY_2026-10-12.md` contains its original seven-line edit and remains modified only by that pre-existing content. Neither file is included in the L2 commits.
- The first complete-suite run on the merged worktree terminated with `Tcl_AsyncDelete: async handler deleted by the wrong thread` while executing `test_close_recovers_a_failed_previous_round_and_current_round_without_crossing_events`; it did not produce a passing test summary. A full retry, `B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py`, from `B518 Log Solution/` with desktop Tk access passed: 381 tests in 264.102 seconds, exit code 0, Python 3.8.10 / Tk 8.6. The retry log is `/private/tmp/language-refresh-l2-main-suite-retry.log`. This intermittent Python 3.8/Tk teardown signature had also been observed against the fixed pre-L2 baseline; the failed attempt is reported, not counted as a pass.
- Main-branch test SHA: `a4552be503af64a2e14e4fb2bf975906cfe40ed7`. The review base remained `7071ea1065c21fa93612a30ccca64d85840e185b` throughout.
- Before main push, a direct query found both destination main refs still at `7071ea1065c21fa93612a30ccca64d85840e185b` and both ticket refs at `a4552be503af64a2e14e4fb2bf975906cfe40ed7`. Main evidence commit `a56661e4477234999587eddc9fb5e4933c6dafe4` records the post-merge run and was pushed to both configured destinations. A direct query immediately after that push confirmed Gitea and GitHub `B518-Log-Solution` at `a56661e4477234999587eddc9fb5e4933c6dafe4` and both ticket refs at `a4552be503af64a2e14e4fb2bf975906cfe40ed7`. Both destinations therefore contain the same main and ticket SHAs before safe ticket-branch cleanup.
