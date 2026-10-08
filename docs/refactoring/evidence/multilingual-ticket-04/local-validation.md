# M4 local validation — no-round App diagnostics

Date: 2026-10-09 (Asia/Taipei)

## Baseline and dependency

- Fixed Standards/Spec review baseline: `648b0c2126aaa6ab29016f2f95deb24ca7c8145f`.
- M2 dependency is in GitHub `B518-Log-Solution` ancestry: merge `f128d9f963f60d416d0eaf5917fa5eda87408280`. Its shared bilingual event representation, immutable event identity/time/sequence/round linkage, live main-page rendering and save-before-close contract are present in the baseline. Evidence: [M2 local validation](../multilingual-ticket-02/local-validation.md).
- M3 is also present in the baseline (`fb4ffb2286d9c113511482b738a101a11616bd14`); it is not an M4 direct dependency. Evidence: [M3 local validation](../multilingual-ticket-03/local-validation.md).
- Work branch: `Multilingual/ticket-04`, based on `648b0c2126aaa6ab29016f2f95deb24ca7c8145f`. GitHub is the available remote for this work; company Gitea (`origin`) synchronization is deferred to Monday by user instruction. Keep local/GitHub ticket branches until direct Gitea synchronization is confirmed.

## App event producer inventory

All listed App-owned records use `RoundCoordinator.record_app_event`, carry no `round_id`, and are captured by the registered `AppEventStore`. UI feedback is routed through the current language; raw diagnostics remain in the details view.

| Producer / trigger | Message ID | Captured parameters and diagnostic | UI / persistence / evidence |
| --- | --- | --- | --- |
| App startup | `app.startup.started` | No parameters; App start time is captured by the store | Main event log and App diagnostics; `test_app_event_is_one_versioned_bilingual_record_without_round_identity`, `test_real_tk_app_diagnostic_is_bilingual_inspectable_and_saved_before_close` |
| Preference read / invalid stored language | `app.startup.preferences_read_failed`, `app.preferences.invalid_language` | Read error or unsupported value in `reason` and raw diagnostic | Startup warning and persistent diagnostics; `test_initialization_failure_retains_diagnostic_and_recovers_after_directory_repair`, `test_real_tk_unknown_saved_language_uses_english_and_shows_diagnostic` |
| App journal initialization | `app.event_store.initialize_failed` | Store initialization error in `reason` and diagnostic | Startup warning, retained record and retry/status; App store initialization recovery test |
| Language preference write | `app.language.preference_save_failed` | Write error in `reason` and raw diagnostic | Current-session language remains usable; disk preference stays unchanged; M4 real Tk language-save failure test |
| Hotkey registration unavailable | `app.hotkey.unavailable` | Original registration message in diagnostic | Existing warning retained; actual App diagnostics row/detail and disk record; `test_real_tk_hotkey_and_profile_failures_are_saved_and_inspectable` |
| Profile validation / selection / apply | `app.profile.validation_failed`, `app.profile.save_failed` | Validation or persistence error in `reason` and raw diagnostic | Existing confirmation/error effect retained; actual settings screen and App diagnostic store; same real Tk test and profile-start regression tests |
| Profile import / export | `app.profile.import_failed`, `app.profile.export_failed` | Original file/configuration error in `reason` and diagnostic | Actual Settings buttons and file dialogs exercised; import leaves profile catalog/selection intact, export failure is visible, and both bilingual events plus raw details are readable in App diagnostics; `test_real_tk_hotkey_and_profile_failures_are_saved_and_inspectable` |
| Preferences reload / close-time preference save | `app.startup.preferences_read_failed`, `app.profile.save_failed` | Original read/write error | Existing screen/close handling and App journal; producer call sites in `b518_log_solution.py` |
| App journal write / recovery | Status is exposed as `failed` / `complete`; historical failures remain in `error_history` after recovery | The journal's own write error is kept in public status/history and is not recursively logged into the same failing journal | Main status, diagnostics window with localized historical error list/current state, and nonblocking retry button; `test_failed_write_keeps_same_event_for_ordered_retry_and_disk_rebuild`, `test_real_tk_hotkey_and_profile_failures_are_saved_and_inspectable`, `test_real_tk_close_keeps_app_write_failure_open_and_retries_it` |

Shared round events remain round-owned and retain `round_id`; M3 platform events retain their existing shared event context. General no-round diagnostics not listed above are not silently assigned to the active or previous round. M5–M10 remain outside M4.

## Persistence and close contract

`app-events.json` is an App-owned JSON object with `record_type: "app_event_store"` and `schema_version: 1`. Each event has `record_type: "app_event"`, the same explicit schema version, unique `event_id`, contiguous `sequence`, timezone-aware ISO `occurred_at`, `kind`, the legacy English `message`, versioned `localized_message` (`message_id`, captured JSON parameters, `en`, and `zh-TW`), and original `diagnostic`. App events intentionally omit `round_id`. `read_app_event_store` validates version, event identity, sequence, bilingual payload, timestamp and timezone without rewriting old or damaged data.

The App store snapshots nested parameters at event creation. It writes ordered snapshots using same-directory atomic replacement, file flush/fsync, and parent-directory fsync. Directory open/fsync errors are save failures; after an atomic replace succeeded but directory fsync failed, the event remains pending and retry reconfirms the directory entry before reporting completion. A write error retains the original event and sequence for nonblocking retry; the retry checks disk identity to avoid duplicating an append that succeeded before its wrapper reported failure. The journal does not recursively emit a new event about its own write failure. A fresh reader reconstructs records from disk.

The App diagnostics window keeps the current save state separate from historical journal errors. After a successful retry it displays the recovered current state and retains the original failure reason for review; journal failures do not recursively generate more journal events.

`RoundCoordinator` exposes App record/status/list/retry operations and includes App save state in its existing close worker. Close completion checks all tracked round Session/audit work and the App journal; events arriving during close are serialized against the final completion decision. Failed App saves keep the window open and allow retry; cancellation invalidates the close generation without cancelling writes. Tk status, details, retry and destruction stay on the Tk event loop. This does not introduce product-result blocking or App event deletion.

## Acceptance evidence

| M4 acceptance | Evidence / result |
| --- | --- |
| 1. App event identity, time, same-record bilingual content, message ID/parameters/diagnostic, no invented round link | `tests/test_app_event_store.py`: `test_app_event_is_one_versioned_bilingual_record_without_round_identity`; `test_reader_rejects_invalid_or_timezone_naive_event_time`; `tests/test_monitoring_round.py`: `test_close_waits_for_no_round_app_events_and_retries_failed_app_store` |
| 2. Understandable no-round/startup errors with centralized resources and preserved existing dialog effects | `tests/test_language_catalog.py` catalog/fallback cases; `tests/test_log_solution_ui.py`: `test_real_tk_hotkey_and_profile_failures_are_saved_and_inspectable`, `test_real_tk_unknown_saved_language_uses_english_and_shows_diagnostic`. The real Tk case exercises import/export failure buttons and inspects persisted bilingual messages and raw diagnostics. |
| 3. Ordered, complete retry without loss/duplication or recursive failure events | `tests/test_app_event_store.py`: ordered retry, initialization recovery, replace-after-success detection, and directory-fsync failure; `tests/test_monitoring_round.py`: App event during close and retry after directory-fsync failure; true Tk retry case with historical error shown after recovery |
| 4. App work participates in normal save/close; no-round and round work both required | `tests/test_monitoring_round.py`: `test_close_waits_for_no_round_app_events_and_retries_failed_app_store` injects parent-directory fsync failure and proves close remains failed until retry confirms durability; `test_app_event_arriving_during_close_is_included_before_complete`; `tests/test_log_solution_ui.py`: true Tk failure-keeps-open and retry-to-destroy case |
| 5. Current-language explanation plus inspectable raw diagnostic and stable error identity | `tests/test_log_solution_ui.py`: real Tk App diagnostics, preference-save failure, hotkey/profile failures, details selection, fresh disk reader |
| 6. True Tk, temporary disk, injected initialization/write failures, retry and complete save | `B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py` (final result recorded below); M4-specific UI cases use temporary preference, App event and Session paths and actual Tk pointer events for language, settings, import/export, diagnostics, retry and close. |

Final complete-suite command: `B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py` — **328 tests passed** in 83.591 seconds, with the final real-Tk hotkey/profile coverage and temporary-root cleanup guard included. `python3 -m compileall -q src tests` and `git diff --check` also passed.

The sandboxed Tk attempt aborted with exit 134 before reporting assertions. The same focused cases and full suite passed with access to the desktop graphical session. No type-check configuration (`pyproject.toml`, mypy/pyright, setup/tox, pre-commit, Ruff config or Makefile) was found; no type-check pass is claimed.

The earliest M4 UI test runs occurred before all legacy UI tests were redirected from the default App data root into isolated temporary roots. Those early runs may have appended test startup diagnostics to the user's default local App event journal. No App data was inspected or deleted. All final verification uses isolated temporary App roots, preferences, events, sources, Session and audit data, and waits for public App save status before temporary-directory cleanup.

## Review and delivery tracking

- Standards/Spec review baseline remains `648b0c2126aaa6ab29016f2f95deb24ca7c8145f`.
- Final program/test validation SHA: `7990759` (`test: isolate app diagnostic UI recovery cases`).
- Review results and any follow-up validation: pending final fixed-baseline dual-axis review; update before merge.
- GitHub ticket branch / main synchronization: verify by direct remote SHA query after push/merge.
- Gitea synchronization is pending Monday and is not claimed here. Do not remove the local or GitHub ticket branch until Gitea is directly confirmed.
- No remote issue status was changed.

M4 does not claim M5–M10 complete, full App-wide translation, App event retention/deletion, complete bundle verification, OS-level global-hotkey hardware acceptance, or field-device acceptance.
