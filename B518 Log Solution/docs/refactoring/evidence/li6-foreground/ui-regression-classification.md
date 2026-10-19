# LI6 UI 回歸分類 / LI6 UI Regression Classification

## Branch run

命令：

```sh
B518_TK_TESTS=1 /opt/anaconda3/bin/python3 scripts/run_tests.py test_log_solution_ui
```

整套結果：109 tests、7 failures、2 errors、1 skipped。失敗摘要：

- `test_empty_paths_are_rejected_before_monitor_creation`: 測試預期 `RoundCoordinator.snapshot()` 為 `None`；實際回傳 `start_failed` / `AWAITING_REVIEW` 的 `RoundSnapshot`。
- `test_final_result_brings_dashboard_to_front_without_permanent_topmost`: 仍要求舊的 `focus_force()` 行為。已更新為驗證結果事件不直接提升或搶焦點，單獨重跑通過。
- `test_main_page_actions_explain_bilingual_behavior_without_invoking`: 等候 Tk 呈現逾時。
- `test_monitor_creation_error_is_visible_and_returns_to_standby`: 預期 `_round_is_active()` 為 false，實際為 true。
- `test_real_tk_notification_badge_stays_until_alarm_is_acknowledged`: 第二輪因前輪待人工核對而被拒絕，後續等待關閉逾時；清理階段另有兩個 `TclError: can't delete Tcl command`。
- `test_real_tk_preference_replace_failure_does_not_accept_round_or_leave_start_busy`: 預期沒有 round snapshot；實際為 `start_failed` / `AWAITING_REVIEW` snapshot。
- `test_toolbar_keyboard_traverses_visual_order_and_leaves_toolbar`: 完整批次中語言切換 UI 等候逾時。

## 固定基底比較

從整合基底 `b2be9c66f0eb54796bf35c1f0016a64850131a28` 匯出乾淨快照，使用同一 Python/Tk/Quartz 環境重跑上述六個非 LI6 舊行為測試（排除已更新的舊 focus-force 預期）。實際命令輸出為 `Ran 6 tests`、`FAILED (failures=5, errors=2)`。這裡的 6 是測試方法數；`test_real_tk_notification_badge_stays_until_alarm_is_acknowledged` 在自身清理與 `tearDownClass` 各額外拋出一個 Tcl cleanup error，因此 unittest 的 failure/error 記錄合計 7 筆，並非 7 個不同測試方法：

- `test_empty_paths_are_rejected_before_monitor_creation`、`test_monitor_creation_error_is_visible_and_returns_to_standby`、`test_real_tk_notification_badge_stays_until_alarm_is_acknowledged`、`test_real_tk_preference_replace_failure_does_not_accept_round_or_leave_start_busy` 四個測試方法失敗；通知 badge 測試另外產生兩個 Tcl cleanup error（一個測試清理、一個 `tearDownClass`）。
- `test_main_page_actions_explain_bilingual_behavior_without_invoking` 在基底上失敗，該次為原生滑鼠按下狀態未顯示 (`pressed` assertion)；branch 批次則於同一測試的 Tk presentation 等候逾時。
- `test_toolbar_keyboard_traverses_visual_order_and_leaves_toolbar` 在基底單獨分類批次及 branch 單獨分類批次都通過，屬完整批次的時序失敗。

branch 單獨分類命令：

```sh
B518_TK_TESTS=1 /opt/anaconda3/bin/python3 scripts/run_tests.py test_log_solution_ui.LogSolutionUiTests.test_empty_paths_are_rejected_before_monitor_creation test_log_solution_ui.LogSolutionUiTests.test_result_event_updates_dashboard_without_forcing_window_or_focus test_log_solution_ui.LogSolutionUiTests.test_main_page_actions_explain_bilingual_behavior_without_invoking test_log_solution_ui.LogSolutionUiTests.test_monitor_creation_error_is_visible_and_returns_to_standby test_log_solution_ui.LogSolutionUiTests.test_real_tk_notification_badge_stays_until_alarm_is_acknowledged test_log_solution_ui.LogSolutionUiTests.test_real_tk_preference_replace_failure_does_not_accept_round_or_leave_start_busy test_log_solution_ui.LogSolutionUiTests.test_toolbar_keyboard_traverses_visual_order_and_leaves_toolbar
```

結果：7 tests，包含新合約舊單元測試通過；其他 5 個既有故障重現；toolbar 測試單獨分類時通過。

基底比較命令使用同一測試名稱（略去已更新的 `test_result_event_updates_dashboard_without_forcing_window_or_focus`，因基底沒有該測試）。以上對照用於區分預存 UI 回歸與 LI6 前景修改；新 LI6 真正桌面驗收與相鄰 71 個測試均另有通過記錄。
