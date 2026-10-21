# PR #117 第二輪修正驗證

對應 #110、#105 D5／T16／T17，以及第二輪審查 S3、S4、R2。此文件記錄實作端驗證，供獨立審查複查。

## 修正與實際行為

- S3：提示顯示前後比較同一失敗請求及 Coordinator snapshot；失敗投影維持空 round ID，沒有受理新輪次。
- S4：沿用完整 `ControlledConflictMonitor`，由真 Coordinator 執行開始、逾時、確認警報，取得可取消輪次。另直接抽取本案例 Monitor class，執行相同 Coordinator 路徑也通過。
- R2：使用 `CGEventPost` 移動原生滑鼠、`CGEventPostToPid` 發送 Tab；輪次及清單資料由測試設定，hover／焦點路徑由原生輸入驗證。停用開始按鈕仍由 Tab 略過；可用取消按鈕可由 Tab 到達，焦點提示不執行取消。
- 真實畫面發現短繁中提示可能遮住主頁狀態與下方操作，因此主頁操作提示優先放在主視窗側邊；側邊無空間時放在控制項上方。其他提示會在視窗寬度允許時對齊其邊界。

## 執行環境與結果

macOS 15.8.1、Intel x86_64、Python.org 3.12.10；臨時 `/private/tmp/hc5-ui-venv` 安裝 PyObjC Quartz／Cocoa 12.2.2。原生測試以桌面執行權限運行。

| 驗證 | 結果 |
| --- | --- |
| `test_real_tk_start_and_cancel_hints_cover_recovery_states` | 1 passed、0 skipped；11.108 秒，含主頁與取消提示不遮擋斷言及截圖 |
| 主頁、設定／恢復中心、警報／衝突／關閉流程三個原生案例 | 3 passed、0 skipped；42.660 秒 |
| 更新影像擷取後重跑主頁與設定／恢復中心 | 2 passed、0 skipped；24.888 秒 |
| 共用提示回歸 `test_real_tk_history_hover_hint_updates_language_and_closes_with_window` | 1 passed、0 skipped；2.847 秒 |
| `test_language_catalog`、`test_recovery_action_hints` | 14 passed |
| 五個相關 Python 檔 `py_compile`、`git diff --check` | passed |

原生案例名稱：

```text
test_log_solution_ui.LogSolutionUiTests.test_real_tk_start_and_cancel_hints_cover_recovery_states
test_log_solution_ui.LogSolutionUiTests.test_main_page_actions_explain_bilingual_behavior_without_invoking
test_log_solution_ui.LogSolutionUiTests.test_settings_and_recovery_actions_explain_bilingual_behavior_without_invoking
test_log_solution_ui.LogSolutionUiTests.test_real_tk_close_keeps_conflict_and_alarm_actions_available
```

重跑範例（需桌面執行權限及 Quartz／Cocoa）：

```sh
B518_TK_TESTS=1 \
B518_TK_EVIDENCE_DIR=docs/refactoring/evidence/hc5/ui \
/private/tmp/hc5-ui-venv/bin/python scripts/run_tests.py \
  test_log_solution_ui.LogSolutionUiTests.test_real_tk_start_and_cancel_hints_cover_recovery_states
```

先前 exit 134 的嘗試保留為歷史結果。本輪沒有重跑整套測試、M4 或 JetKVM 實機驗收。

## 原生影像索引

影像由 WindowServer 擷取 App 主視窗及其提示視窗，範圍包含兩者聯集。空白區呈透明／黑色；其他 App 視窗不在擷取清單內。影像可見提示全文；主頁計時、結果、KVM 與必要操作均保持可見，恢復中心的提示也保留操作按鈕及上方輪次說明。

| 情境 | English | 繁中 |
| --- | --- | --- |
| 開始可用，原生 Tab 焦點 | [影像](ui/hc5-main-start-focus-en.png) | [影像](ui/hc5-main-start-focus-zh-TW.png) |
| 啟動異常，開始停用，原生 hover | [影像](ui/hc5-start-disabled-failure-en.png) | [影像](ui/hc5-start-disabled-failure-zh-TW.png) |
| 待取消輪次，開始停用，原生 hover | [影像](ui/hc5-start-disabled-cancellation-en.png) | [影像](ui/hc5-start-disabled-cancellation-zh-TW.png) |
| 設定瀏覽按鈕可用，原生 hover | [影像](ui/hc5-settings-browse-enabled-en.png) | [影像](ui/hc5-settings-browse-enabled-zh-TW.png) |
| 解除異常停用，原生 hover | [影像](ui/hc5-startup-reset-disabled-en.png) | [影像](ui/hc5-startup-reset-disabled-zh-TW.png) |
| 解除異常可用，焦點提示 | [影像](ui/hc5-startup-reset-enabled-en.png) | [影像](ui/hc5-startup-reset-enabled-zh-TW.png) |
| 取消停用，原生 hover | [影像](ui/hc5-round-cancel-disabled-en.png) | [影像](ui/hc5-round-cancel-disabled-zh-TW.png) |
| 取消可用，原生 hover／即時語言刷新 | [影像](ui/hc5-cancel-enabled-en.png) | [影像](ui/hc5-cancel-enabled-zh-TW.png) |

另附[原生 Tab 到達取消按鈕](ui/hc5-cancel-tab-focus-en.png)、[停止按鈕停用](ui/hc5-main-stop-disabled-zh-TW.png)。

[protected-bounds.json](ui/protected-bounds.json) 保存兩語提示與受保護控制項的真實螢幕邊界。新案例斷言兩種開始停用提示均不與計時、結果、KVM、開始、停止、重試保存、診斷相交，並檢查取消提示不覆蓋取消／解除異常按鈕，且提示留在螢幕範圍內。
