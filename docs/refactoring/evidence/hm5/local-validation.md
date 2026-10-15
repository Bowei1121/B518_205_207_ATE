# HM5 local validation

Fixed review base: `eda24aae7eac0197650ea7273b17870e7bc03e2d`.

## Layout changes

- General App notices use a fixed-size, scrollable read-only message area with a light background and thin border; acknowledgement remains in a reserved action row.
- Save-before-close uses fixed status and language-restriction rows, a scrollable read-only raw-diagnostic area, and fixed-width retry/cancel actions. The window title and actions continue to use current-language resources. Save/retry/cancel lifecycle code is unchanged.
- True Tk tests capture English and Traditional Chinese notice and close-progress windows, compare geometry and control bounds, and verify long diagnostics remain readable. Close-progress capture reuses the existing controlled audit-write failure, retry, and cancel flow.

## Non-Tk validation

- `python3 -m py_compile "B518 Log Solution/src/b518_log_solution.py" "B518 Log Solution/src/localized_notice.py" "B518 Log Solution/tests/test_log_solution_ui.py"` — passed.
- `git diff --check` — passed.
- `PYTHONPATH='B518 Log Solution/src:B518 Log Solution/tests' python3 -m unittest test_language_catalog -q` — 6 tests passed.
- `PYTHONPATH='B518 Log Solution/src:B518 Log Solution/tests' python3 -m unittest test_monitoring_round -q` — 48 tests passed.
- `PYTHONPATH='B518 Log Solution/src:B518 Log Solution/tests' python3 -m unittest test_round_retention -q` — 36 tests passed.

## True Tk validation pending

The app UI tests below require an interactive macOS Tk session and have not yet run in this worktree. The coordinator is arranging the Tk slot.

- `B518_TK_TESTS=1 B518_TK_EVIDENCE_DIR=docs/refactoring/evidence/hm5/screenshots python3 "B518 Log Solution/scripts/run_tests.py" test_log_solution_ui.LogSolutionUiTests.test_hm5_long_notice_stays_scrollable_and_fixed_across_languages`
- `B518_TK_TESTS=1 B518_TK_EVIDENCE_DIR=docs/refactoring/evidence/hm5/screenshots python3 "B518 Log Solution/scripts/run_tests.py" test_log_solution_ui.LogSolutionUiTests.test_close_failure_keeps_window_open_and_real_retry_rebuilds_complete_audit`
- Related Tk regressions: `test_real_tk_app_diagnostic_is_bilingual_inspectable_and_saved_before_close`, `test_real_tk_close_keeps_app_write_failure_open_and_retries_it`, `test_real_tk_distinguishes_unsaved_saved_and_archived_round_states`, and `test_notice_escape_hidden_reopen_and_current_language_lifecycle`.

Successful Tk runs should produce `screenshots/general-notice-en.png`, `screenshots/general-notice-zh-TW.png`, `screenshots/close-progress-en.png`, `screenshots/close-progress-zh-TW.png`, and their geometry/control comparison in `screenshots/window-bounds.json`.
