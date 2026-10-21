# HC6 Local Validation

Implementation branch: `codex/hc6-review-history-diagnostics`, based on `B518-Log-Solution` integration commit `1af60cf`.

## Executed

- Python syntax compilation passed for `language_catalog.py`, `test_log_solution_ui.py`, and `test_language_catalog.py` using `/opt/anaconda3/bin/python` 3.11.7.
- On the review-fix working tree, `test_language_catalog`, `test_historical_event_display`, and `test_historical_event_query` ran 85 tests; 84 passed and `test_page_reads_run_off_ui_and_latest_page_replaces_blocked_request` failed in `_write_audit()` because `audit.flush()` returned false. Re-running that test alone reproduced the same failure. This test does not exercise the changed hint resources or UI assertions.
- The four targeted desktop acceptance tests were attempted with `B518_TK_TESTS=1` and Python 3.11.7 (Tk 8.6; AppKit and Quartz import successfully). Tk aborted while constructing its first root window with `NSInternalInconsistencyException: Invalid parameter not satisfying: aString != nil` from `NSMenuItem initWithTitle:action:keyEquivalent:`; process exit status was 134. No UI assertions ran and no screenshots were captured in this shell session.
- The full `scripts/run_tests.py` suite was run once with Python 3.11.7. It passed through the historical query cases, then aborted when the UI test class created Tk with the same AppKit exception (exit status 134). The two H8 capacity UI tests and LI6 foreground acceptance test were reported skipped before the abort; later tests were not reached. There is no full-suite pass result.
- `git diff --check` passed.

## Desktop validation still needed

The true Tk acceptance cases for hover/focus, disabled reasons, live language refresh, and close/reopen were not executed successfully on this worktree. Although the selected runtime imports AppKit and Quartz, Tk cannot initialize a native menu in the current shell session and aborts before unittest output. This is an environment limitation, not a passing UI result. The requested bilingual screenshots and confirmation of the full T16/T17/T19 lifecycle remain outstanding.

The independent review of HEAD `646e40da497c49fec6f884efd0826067c69ecdce` reports four targeted Tk tests and 85 history/language tests passing, plus a two-test screenshot run that produced 22 captures. It identified two invalid captures: the Chinese disabled-cancel filename showed the search hint, and the Chinese alarm-close hint was obscured by an unrelated native window. The review artifacts are in `tmp/reviews/pr115-646e40d/`; they are prior-HEAD evidence and the two noted images are not accepted as visual proof. This revision makes screenshot capture verify the expected hint control and composes only the target app window and its tooltip, excluding unrelated windows. The revised screenshot flow still needs a fresh desktop run and visual check.

Existing acceptance entry points:

- `test_real_tk_close_keeps_conflict_and_alarm_actions_available`
- `test_real_tk_history_and_diagnostics_controls_explain_current_actions`
- `test_real_tk_history_language_refresh_preserves_draft_snapshot_page_and_detail`
- `test_app_diagnostics_scroll_position_survives_language_refresh`

Run these in a working macOS desktop session with `B518_TK_TESTS=1`; record skipped cases and bilingual screenshots separately. Prior ST5/ST6 evidence covers the unchanged shared tooltip lifecycle, but it predates this copy update and is not reported as a fresh HC6 desktop pass.
