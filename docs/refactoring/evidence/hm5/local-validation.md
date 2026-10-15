# HM5 local validation

Fixed review base: `eda24aae7eac0197650ea7273b17870e7bc03e2d`.

## Layout changes

- General App notices use a fixed-size, scrollable read-only message area with a light background and thin border; acknowledgement remains in a reserved action row.
- Save-before-close uses fixed status and language-restriction rows, a scrollable read-only raw-diagnostic area, and fixed-width retry/cancel actions. The status and language labels fill their fixed rows so their own bounds remain stable across languages. The window title and actions continue to use current-language resources. Save/retry/cancel lifecycle code is unchanged.
- True Tk tests capture English and Traditional Chinese notice and close-progress windows, compare size and relative control bounds, and verify long diagnostics remain readable. Close-progress capture reuses the existing controlled audit-write failure, retry, and cancel flow.

## Non-Tk validation

- `python3 -m py_compile "B518 Log Solution/src/b518_log_solution.py" "B518 Log Solution/src/localized_notice.py" "B518 Log Solution/tests/test_log_solution_ui.py"` — passed.
- `git diff --check` — passed.
- `PYTHONPATH='B518 Log Solution/src:B518 Log Solution/tests' python3 -m unittest test_language_catalog -q` — 6 tests passed.
- `PYTHONPATH='B518 Log Solution/src:B518 Log Solution/tests' python3 -m unittest test_monitoring_round -q` — 48 tests passed.
- `PYTHONPATH='B518 Log Solution/src:B518 Log Solution/tests' python3 -m unittest test_round_retention -q` — 36 tests passed.

## True Tk validation

Runtime: macOS Aqua Tk, screen scale 2x. Both tests passed in the coordinator-assigned interactive Tk slot using sandbox escalation. Direct non-escalated launches exited with status 134 before test output.

- `B518_TK_TESTS=1 B518_TK_EVIDENCE_DIR=docs/refactoring/evidence/hm5/screenshots python3 'B518 Log Solution/scripts/run_tests.py' test_log_solution_ui.LogSolutionUiTests.test_close_failure_keeps_window_open_and_real_retry_rebuilds_complete_audit` — passed, 1 test in 2.361s.
- `B518_TK_TESTS=1 B518_TK_EVIDENCE_DIR=docs/refactoring/evidence/hm5/screenshots python3 'B518 Log Solution/scripts/run_tests.py' test_log_solution_ui.LogSolutionUiTests.test_hm5_long_notice_stays_scrollable_and_fixed_across_languages` — passed, 1 test in 2.167s.

The screenshot pairs are `screenshots/general-notice-en.png`, `screenshots/general-notice-zh-TW.png`, `screenshots/close-progress-en.png`, and `screenshots/close-progress-zh-TW.png`. `screenshots/window-bounds.json` records geometry, size, native capture bounds, and relative control bounds. Both language captures have the same size and control bounds: notice 640x400; close-progress 620x390; close status row [18, 12, 584, 64], language-reason row [18, 80, 584, 56], diagnostic area [18, 140, 569, 188], retry [18, 340, 224, 34], cancel [414, 340, 188, 34]. Screen positions vary by desktop placement and are recorded but not compared.
