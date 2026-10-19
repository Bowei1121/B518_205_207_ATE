# ST4 真實 App 驗收紀錄（2026-10-16）

環境：macOS，Python 3.8，Tk/Aqua。畫面使用真正的 B518 Log Solution App；視窗與包含停用提示的畫面均以 Quartz 擷取，沒有拼貼或重繪。

驗收命令：

```sh
PYTHONPATH=src B518_TK_TESTS=1 B518_TK_EVIDENCE_DIR=docs/refactoring/evidence/st4-20261016 /usr/local/bin/python3.8 -X faulthandler -m unittest -v \
  tests.test_log_solution_ui.LogSolutionUiTests.test_settings_and_recovery_actions_explain_bilingual_behavior_without_invoking \
  tests.test_log_solution_ui.LogSolutionUiTests.test_main_page_actions_explain_bilingual_behavior_without_invoking \
  tests.test_log_solution_ui.LogSolutionUiTests.test_file_dialog_buttons_use_current_language_and_cancel_without_changes \
  tests.test_log_solution_ui.LogSolutionUiTests.test_real_tk_global_retention_setting_validates_persists_and_preserves_round_files \
  tests.test_log_solution_ui.LogSolutionUiTests.test_engineer_can_apply_and_cancel_a_complete_profile_draft \
  tests.test_log_solution_ui.LogSolutionUiTests.test_engineer_can_load_an_existing_profile_before_editing_it \
  tests.test_log_solution_ui.LogSolutionUiTests.test_recovery_zero_alarm_language_and_reopen_preserve_tab \
  tests.test_log_solution_ui.LogSolutionUiTests.test_recovery_archive_list_preserves_selection_and_scroll_across_poll_language_reopen \
  tests.test_log_solution_ui.LogSolutionUiTests.test_recovery_acknowledges_only_manually_and_session_retry_keeps_evidence_once \
  tests.test_log_solution_ui.LogSolutionUiTests.test_close_failure_keeps_window_open_and_real_retry_rebuilds_complete_audit
```

結果：10 tests passed。Settings 三分頁和 Recovery 兩分頁的中英文畫面、disabled Retry Selected 的中英原因提示均有對應 PNG。Quartz 原生滑鼠移入停用按鈕可讀提示，按下不呼叫 retry；焦點導覽與語言切換會更新提示。關閉 Settings／Recovery 後，測試確認註冊的全域 `<Motion>` callback 已移除。既有回歸也通過保存期限持久化、配置載入／套用／取消、Recovery 重開及選取／捲動保留、人工警報確認、保存重試與失敗時保留視窗。

原生 macOS `NSOpenPanel` Cancel 已於真正英文 Settings 現場驗收：直接從 `_choose_profile_editor_path('active')` 開啟系統面板並以滑鼠點擊 Cancel；handler 回傳路徑與最後讀回皆為 `/draft/active`，Settings 仍開啟。未修改原生螢幕證據為 `st4-native-chooser-cancel-en.png`（Cancel 面板）與 `st4-native-settings-after-cancel-en.png`（關閉後 Settings 草稿路徑）。

試行的淺藍 hover 與藍色 focus 樣式沒有在本票改色或宣稱核可。系統外觀切換由 ST7 驗收；工廠桌面與 KVM 實機另列工廠驗收。

## 證據索引

- `st4-settings-configuration-{en,zh-TW}.png`：設定配置頁。
- `st4-settings-events-{en,zh-TW}.png`：設定通知頁。
- `st4-settings-retention-{en,zh-TW}.png`：設定保存期限頁。
- `st4-recovery-alarms-{en,zh-TW}.png`：恢復警報頁。
- `st4-recovery-saves-archives-{en,zh-TW}.png`：恢復保存／封存頁。
- `st4-recovery-disabled-save-tooltip-{en,zh-TW}.png`：真實畫面同時顯示停用的重試按鈕及完整中／英文停用原因。
- `st4-native-chooser-cancel-en.png`、`st4-native-settings-after-cancel-en.png`：原生 NSOpenPanel 滑鼠點擊 Cancel 前後的未修改螢幕證據；草稿路徑讀回為 `/draft/active`，Settings 仍開啟。
- `window-bounds.json`：畫面擷取時視窗、控制項與幾何資訊。

結果：修正英文分頁擷取後，完整 10 項真 Tk/Aqua 回歸 10/10 通過（24.399 秒），focused ST4 提示／畫面測試亦 1/1 通過。`py_compile`、`git diff --check` 與 language catalog 8/8 通過。真實 NSOpenPanel 點擊取消另完成桌面驗收。

畫面證據源自實作者工作樹 `codex/st4-settings-recovery-hints`、提交 `a868369afe8ebc7aea1e75b45e370347678477ae`。原始 12 張真 App PNG 曾逐張比對 SHA-256；檢查發現原測試把英文 Settings 的 Events／Retention 檔名截在 Configuration 分頁，因此測試已修正為逐頁選取，英文三頁由真 App 重新擷取。其餘畫面保留來源擷取。兩張 NSOpenPanel 現場驗收 PNG 由桌面操作者原樣複製並檢視；它們與上述 12 張功能畫面一併由整合分支納入。PNG 原先因全域 `*.png` ignore 規則未進實作提交。
