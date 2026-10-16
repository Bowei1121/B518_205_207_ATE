# ST7 — Recovery window appearance validation

Environment: macOS 15.7.9, Python 3.8.10, Tk/Aqua, actual `B518LogSolutionApp` process. The user's original macOS appearance was Dark and was restored after verification.

## Reproduction and implementation

Before the change, a real recovery-window test under system Dark read the App-owned `Toplevel` background as Aqua's dynamic `systemWindowBody`, and the regression test failed against the required `#f3f4f6` light surface. The corresponding native screenshot is `st7-baseline-recovery-en.png` in the initial local run. Its visible surface was still light at initial launch, so this confirms a system-bound background value but does not by itself establish that it explains every reported repaint.

The recovery `Toplevel` now sets its own background to the App light palette. `test_recovery_window_outer_surface_uses_the_app_light_palette` passes in actual Tk and captures English and Traditional Chinese views of both tabs. The before/after light-palette screenshot is `st7-baseline-recovery-en.png`; its original `systemWindowBody` background can be compared with the now-explicit surface in `st7-light-before-tab1-en.png`.

## Open-window system appearance transition

`test_recovery_window_stays_light_during_real_system_appearance_changes` is an opt-in interactive Tk test. It leaves the same real window mapped while the operator changes macOS appearance through Control Center or System Settings, checks the actual system preference with `defaults`, and captures both tabs in both languages before and after each transition. No Accessibility/System Events automation was used.

The real transition passed: the same mapped Recovery window was captured in actual Light and Dark modes, in English and Traditional Chinese, on both the Round Alarms and Save and Archive tabs. The accepted Light set is `st7-light-open-tab0/1-{en,zh-TW}.png`; the accepted restored-Dark set is `st7-dark-after-tab0/1-{en,zh-TW}.png`. `appearance-evidence.json` records each view and window bounds, and the test read back the actual mode through `defaults` before capture. One earlier Light/Traditional-Chinese/Save-and-Archive frame (`st7-light-before-tab1-zh-TW-invalid-capture.png`) contained the native title and tab strip but a blank content area despite mapped widgets. It is retained as a failed capture, not acceptance evidence. A later capture of that same view while the same Recovery window remained open is complete (`st7-light-open-tab1-zh-TW.png`). The capture helper now activates and raises the actual App window and pumps Tk/Aqua for 0.8 seconds before native capture. The underlying timing/repaint cause is not confirmed. The user's original Dark appearance was read back after the final capture. The surrounding OS title bar remains OS-managed.

The transition did not alter pending work or trigger actions: the interactive run's empty alarm/save/archive state remained unchanged and all three buttons stayed disabled. Separate real-Tk checks passed for pending alarm acknowledgement only on explicit action, session retry retaining exactly-once evidence, archive selection and reading position across language refresh/reopen, and tab retention across reopen. Screenshots of pending and acknowledged alarm states in both languages are `hf2-alarm-{pending,acknowledged}-{en,zh-TW}.png`.

## Test results

- Real Tk before the final capture-helper hardening: `test_recovery_window_outer_surface_uses_the_app_light_palette`, `test_recovery_window_stays_light_during_real_system_appearance_changes`, `test_recovery_zero_alarm_language_and_reopen_preserve_tab`, `test_recovery_archive_list_preserves_selection_and_scroll_across_poll_language_reopen`, and `test_recovery_acknowledges_only_manually_and_session_retry_keeps_evidence_once` passed. The interactive appearance test completed 1/1 in 60.133s; its saved result confirms the original Dark appearance was restored.
- A replay after capture-helper hardening could not initialize Tk: macOS AppKit terminated Python with `NSInternalInconsistencyException` while Tk was creating its application menu (`NSMenuItem`/`TkSetWindowMenuBar`); unittest produced no test result. This is an environment startup failure, not a passing verification. The already captured complete Light and Dark native screenshots remain the visual acceptance evidence. Python `py_compile` and `git diff --check` pass for the final sources.
- System mode: Dark → Light while the app was open, then restored to the user's original Dark. Both modes were confirmed from macOS preferences, not inferred from Tk styles.
- Factory computer, KVM hardware, and other macOS versions/display scaling were not tested.
