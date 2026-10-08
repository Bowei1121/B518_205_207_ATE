# M5 local validation — settings and file dialogs

Date: 2026-10-09 (Asia/Taipei)

## Baseline and dependency

- Fixed Standards/Spec review baseline: `740b26c23f5fb6fcc0988272183159b4405df5da` (the GitHub `B518-Log-Solution` SHA checked before M5 changes).
- Python project directory: `B518 Log Solution/` inside the Git root.
- M4 dependency is present in the baseline ancestry at merge `f7e24cd265fc173d5d113e7fb122083602f5e5fa`. The M4 evidence verifies the App-owned event store, bilingual message IDs and captured parameters, raw diagnostic retention, public disk reader/retry/status API, and save-before-close coordination. M5 did not modify that persistence lifecycle.
- M1 language preference, actual main-page language control, and M2/M3 bilingual round/platform event contracts are present in the same baseline. Evidence: [M1](../multilingual-ticket-01/local-validation.md), [M2](../multilingual-ticket-02/local-validation.md), [M3](../multilingual-ticket-03/local-validation.md), [M4](../multilingual-ticket-04/local-validation.md).
- Current work branch: `Multilingual/ticket-05`, created from the verified GitHub mainline baseline; local base was clean. No existing local changes were included.
- Push destinations are `github` and `origin`; `origin` retains the company Gitea fetch/push URL and also has its GitHub push URL. Gitea remains deferred to Monday by the user. M5 pushes use the dedicated `github` remote; no destination is removed.

## Screen, operation, and event-producer inventory

| Screen / operation | Visible language behavior | Event / diagnostic and persistence route |
| --- | --- | --- |
| Settings window title and Configuration, Events & Session, Retention tabs | Central `language_catalog` IDs; existing window and selected tab remain in place | Opening the window does not create a business event |
| Project, Station Type, platform, capacity, mapping, paths, timeouts | Labels are translated; project IDs, station values, platform IDs, mapping, names, paths, and numeric input remain source values | Draft validation uses `app.settings.event.profile.validation_failed`; raw validation reason is retained as diagnostic |
| Choose local folder | App title is localized; OS-native controls remain owned by macOS | A non-empty selected path creates `app.settings.event.profile.path_selected`; cancellation leaves the draft unchanged |
| Load / validate / apply / cancel draft | Buttons and status messages translate; existing selection and operation policy remain | Success uses `app.settings.event.profile.loaded`, `.validated`, `.saved`, or `.cancelled`; failure retains the existing `app.profile.validation_failed` or `.save_failed` event and raw diagnostic |
| Import / export | App-provided chooser title and file-type names are localized; patterns/extensions remain `.json` and `*` | Success uses `app.settings.event.profile.imported` / `.exported`; failure uses existing M4 `app.profile.import_failed` / `.export_failed` events with raw diagnostics |
| Reload deployed configuration | Button and success/failure status translate | Success reuses `app.settings.event.profile.loaded`; read failure reuses `app.startup.preferences_read_failed` with the original diagnostic |
| Global retention | Effective value, editor label, save result/error, 24-hour/trusted-archive help, shortened-period notice, and cleanup heading/status/summary use centralized resources | Invalid, failed, and successful saves use `app.settings.event.retention.invalid`, `.save_failed`, and `.saved`; settings language and retention remain global preferences outside profile drafts |
| Open Session records | App button and App-owned error title/message translate; native OS file manager remains OS-owned | Failure uses `app.settings.event.session.open_failed` with raw diagnostic |
| Language preference write failure | The selected language remains usable for the current screen and the existing unsaved-preference indication remains visible | Existing M1 `app.language.preference_save_failed` event uses M4 persistence; the original preference file remains unchanged |

App event parameters are captured by the existing M4 API at operation time. M5 reuses the shared versioned bilingual event representation and does not add a second event or attach settings events to a round. Raw paths, project/station values, platform identifiers, SNs and diagnostics remain unchanged data.

## Acceptance evidence

| M5 acceptance | Result and evidence |
| --- | --- |
| 1. Settings, configuration, retention, import/export copy and glossary | Pass. `test_language_catalog.py` checks English baseline, Traditional Chinese fallback/keys, named parameters and approved glossary. Real settings UI coverage is in `test_open_settings_refreshes_language_in_place_and_keeps_invalid_draft`, `test_real_tk_global_retention_setting_validates_persists_and_preserves_round_files`, and `test_file_dialog_buttons_use_current_language_and_cancel_without_changes`. |
| 2. In-place refresh preserves draft, selection, tab, and validation state | Pass. Real Tk test `test_open_settings_refreshes_language_in_place_and_keeps_invalid_draft` clicks the actual language control while the settings view is open and verifies the same window, invalid draft text, selected tab and status remain; no save/reload occurs. |
| 3. Profile and global preference independence | Pass. `test_profile_save_and_import_keep_global_language_but_export_only_profiles`, `test_profile_save_and_import_preserve_global_retention_but_exports_do_not_include_it`, `test_profile_save_from_fresh_store_preserves_existing_global_retention`, and `test_real_tk_global_retention_setting_validates_persists_and_preserves_round_files` verify disk persistence with fresh stores and preserve round-file bytes. The profile editor uses “Station Type”; stored values are unchanged. |
| 4. Same-record bilingual settings events, diagnostic visibility, raw values | Pass. `test_real_tk_hotkey_and_profile_failures_are_saved_and_inspectable` exercises actual Settings actions, reads the bilingual App event journal from disk, and selects the raw import/export/profile diagnostic in the actual diagnostics detail pane. Retention success/failure and disk preservation are covered by `test_retention_setting_uses_visible_errors_and_persists_bilingual_app_events`. |
| 5. Native dialog OS boundary, app title/type, cancellation, overwrite, return path | Partial. Real Tk buttons call the actual `askdirectory`, `askopenfilename`, and `asksaveasfilename` entry points; controlled return-value tests confirm localized App title/type labels and cancellation leaves the draft/catalog unchanged. Actual OS-native chooser interaction and native overwrite confirmation were not exercised in this run, so the criterion remains open. |
| 6. True Tk switching, repeated switching, import/save failures, long English layout | Pass for tested App behavior. `test_real_tk_language_and_profile_controls_fit_fixed_hmi_width` and `test_english_profile_editor_controls_fit_the_existing_minimum_window` verify visible controls at the existing 680×560 minimum. `test_real_tk_global_retention_setting_validates_persists_and_preserves_round_files` and `test_real_tk_hotkey_and_profile_failures_are_saved_and_inspectable` cover retention/profile failures and import/export failure. The complete real Tk UI module passed. |

The complete real Tk UI module command was `B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py test_log_solution_ui` — **57 tests passed** (57.124 seconds). Focused catalog/profile checks passed: `PYTHONPATH=src python3 scripts/run_tests.py test_language_catalog test_machine_profiles` — **29 tests passed**. Focused real Tk regression checks passed after test isolation/locale corrections.

The required full suite was run from `B518 Log Solution/` with `B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py` — **334 tests passed** in 80.972 seconds. `python3 -m compileall -q 'B518 Log Solution/src' 'B518 Log Solution/tests'` and `git diff --check` passed. There is no project type-check configuration (no `pyproject.toml`, mypy/pyright config, `setup.cfg`, `tox.ini`, or `Makefile` found); no type-check pass is claimed.

Tk tests ran with access to the desktop graphical session after the sandboxed Tk process had previously aborted with exit 134. The native file chooser itself was not launched for human interaction in this run. Before M5 can merge, use the actual Settings buttons in each language to open/cancel the folder, import, and export native dialogs; verify localized App title/type labels, unchanged selected path/configuration on cancel, the operating-system-owned buttons, and the OS overwrite confirmation/decline path. Record the actual visible result here. This is an external UI confirmation only; no product defect has been inferred.

## Boundaries and review tracking

- M5 changes settings copy, in-place view refresh, translated retention summary presentation, App event producer IDs for settings actions, and real Tk coverage only.
- M5 does not translate OS-owned chooser UI, SN/path/custom values/raw diagnostics, or machine/platform data. It does not alter configuration schema, event format, round/session/audit/close/retention lifecycle, or background cleanup ownership.
- M6–M10 remain out of scope. M5 does not claim complete App translation or bundle verification.
- Fixed review baseline remains `740b26c23f5fb6fcc0988272183159b4405df5da`; record final reviewed commit and any post-review revalidation below.
- Company Gitea synchronization is deferred until Monday. Until direct Gitea SHA verification and the outstanding native-dialog interaction are complete, keep both local and remote `Multilingual/ticket-05` branches; do not merge or delete either branch.
