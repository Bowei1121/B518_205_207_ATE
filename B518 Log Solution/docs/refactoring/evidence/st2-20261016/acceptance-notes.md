# ST2 local acceptance record — 2026-10-16

System: macOS 15.7.9 (24G830). This record is local implementation evidence, not factory acceptance.

## Previously verified behavior

The actual B518 app's round-based acceptance scenario generated twelve same-slot conflicts and one archive/deadline alarm. After the current language-entry change, `test_conflict_review_tracks_same_slot_candidates_through_refresh_resolution_and_reopen` passed 1/1 in 37.1 seconds. It verified independent counts (12 and 1), that opening their respective windows did not clear either count, that manual conflict adjudication reduces only the conflict count, and that toolbar/KVM geometry stayed fixed. Fresh app-window captures are `st2-twelve-conflicts-en.png` and `st2-twelve-conflicts-zh-TW.png`; both show complete 12/1 badges, the arrowless globe, aligned settings/logo/badges/language, KVM controls and bottom actions. The measured logo slot remains 137×35.

In an earlier visible Aqua `ttk.Menubutton` probe, real Quartz Tab/Space opened the native menu, Down moved the active row, Return selected it and changed the language, and Escape cancelled without changing the language. The Aqua Menubutton indicator is drawn outside the ttk style layout, so filtering the style layout did not remove the arrow.

## Current implementation candidate

The production language entry is now an icon-only visible `ttk.Button` with a native Tk `Menu`. Space, Return, and Down invoke the enabled button's menu command; the button's Space key-up is suppressed to avoid a duplicate invocation. The native menu continues to own row navigation, Return selection, and Escape cancellation. The menu is positioned from the same visible button; no hidden menu owner or clipped native control is used. The UI regression now posts genuine Quartz key events directly to its own process using `CGEventPostToPid` and asserts that Space opens the menu before testing cancellation and selection.

Real desktop keyboard acceptance passed on 2026-10-16 using the escalated macOS Tk runner. `test_toolbar_keyboard_traverses_visual_order_and_leaves_toolbar` passed 1/1: actual PID-targeted Quartz Tab focused 🌐; Space opened the native menu; Escape closed it without changing the current language; a second path opened it with Down, moved the active row with a real Down key, and Return changed the language. The test also verified the focus/tooltip contract and destroyed the app with no menu callback error. Clean B518-only window captures of the native menu open/closed states are `toolbar-language-menu-zh-TW-{escape,active,return,close}-app.png`; Aqua native Menu is a separate surface and is not included in the root-window capture. `toolbar-language-menu-zh-TW-active-menu-crop.png` is an unaltered crop of only the native menu from a direct desktop capture (no composition or pixel edits). The clean root captures `toolbar-focus-language-{en,zh-TW}.png` show the globe without an Aqua arrow in focus.

Quartz pointer injection was attempted three times and failed to open the native menu; these failures are retained here as test-tool limitations, not treated as product passes. The final verification used the actual B518 App with isolated temporary preferences/session data and a visible, unobstructed window. The user clicked the 🌐 control and selected 繁體中文 with the mouse. The running App changed `current_language` from `en` to `zh-TW`; its clean single-window capture is `toolbar-language-menu-manual-pointer-zh-TW-app.png`. This directly verifies pointer opening and selection on the real application. No full-screen notification captures are included.

## Acceptance limits

- Captures and tests are from the actual B518 macOS app, not a prototype or isolated widget. Retained evidence is limited to clean app-window captures, the native-menu-only crop, header crops, and window geometry. Full-screen captures containing a private WeChat notification were excluded and deleted; they are neither linked nor included. `st2-twelve-conflicts-{en,zh-TW}-header-crop.png` magnifies genuine header pixels of the B518 app captures so both independent counters are easy to inspect. No screenshots were composited.
- The manual pointer acceptance used a disposable temporary profile and session directory; no production preferences or logs were changed.
- The pale-blue hover/focus treatment is still a visual trial; these captures do not record user approval of the final palette.
- macOS factory/KVM hardware acceptance is not performed in this local desktop environment.
- Factory display/scaling and physical KVM recognition remain on-site acceptance items; they do not block the locally verifiable implementation and desktop acceptance.
- This is implementation evidence; ticket #70 still requires the parent integrator's review, merge, and remote workflow.

## Reproduction commands

Run from `B518 Log Solution/`:

```sh
B518_TK_TESTS=1 B518_TK_EVIDENCE_DIR=docs/refactoring/evidence/st2-20261016 PYTHONPATH=src python3 -m unittest -v tests.test_log_solution_ui.LogSolutionUiTests.test_toolbar_keyboard_traverses_visual_order_and_leaves_toolbar
B518_TK_TESTS=1 B518_TK_EVIDENCE_DIR=docs/refactoring/evidence/st2-20261016 PYTHONPATH=src python3 -m unittest -v tests.test_log_solution_ui.LogSolutionUiTests.test_conflict_review_tracks_same_slot_candidates_through_refresh_resolution_and_reopen
```

Both were run serially with desktop permission after the final source/evidence cleanup. Latest independent results: keyboard path 1/1 passed in 6.7 seconds; conflict/alarm and screen evidence 1/1 passed in 5.0 seconds.

The corrected setup helper now sets the test locale through the normal language-refresh method rather than synthesizing a click that enters `tk_popup`'s nested event loop. The real native menu remains covered by the Quartz keyboard test above. Additional desktop regressions passed independently: `test_hm1_toolbar_title_status_and_kvm_geometry_stay_fixed` 1/1 (5.8s; tooltip focus retained); `test_real_tk_notification_badge_stays_until_alarm_is_acknowledged` 1/1 (6.4s); `test_real_tk_language_menu_switches_main_page_and_persists_across_app_instances` 1/1 (5.3s); and `test_hm1_logo_normal_missing_and_corrupt_keep_fixed_slot_without_dialog` 1/1 (2.3s). The tooltip test had two transient FocusIn misses during initial diagnosis, then passed with a focus-retention assertion on the standalone repeat and latest independent run. One combined multi-test process hung because the old locale setup helper synthesized a click which now correctly entered `tk_popup`'s nested event loop; it was terminated, the helper was corrected to set fixture locale directly, and all required cases subsequently passed in independent processes. The combined process hang is not recorded as a passing result.
