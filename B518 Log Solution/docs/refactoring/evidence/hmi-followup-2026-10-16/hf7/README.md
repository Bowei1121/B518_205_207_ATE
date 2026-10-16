# HF7 整合桌面驗收紀錄

狀態：HF7 原生 Aqua 整合驗收完成；驗收過程中唯一焦點斷言在批次執行失敗、隔離重跑通過，細節如下。

## 基準與驗收範圍

- 整合分支：`codex/hmi-followup-20261016`
- HF7 起始提交：`ed9432cd141b0bd1fe65adbada4ab56e4a2a7751`
- 實際環境：macOS 原生 Aqua、`/Library/Frameworks/Python.framework/Versions/3.8/bin/python3`、Python 3.8.10、Tcl/Tk 8.6。
- 以 HMI Follow-up Spec 的 44 個故事逐一核對；引用已保存於 HF1–HF6 的真正 App／Tk 行為、畫面及測試紀錄，只執行整合風險回歸與前票缺口，不重跑整套測試或大量歷史效能測試。

## 44 項故事證據對照

| 故事 | HF7 核對範圍 | 已保存證據 |
| --- | --- | --- |
| 1 | 設定圖示辨識 | `../../../../../../docs/refactoring/HF1_KEYBOARD_FIX_2026-10-16.md`；`../keyboard-fix/main-page-en.png`、`../keyboard-fix/main-page-zh-TW.png` |
| 2 | 待確認圖示辨識與獨立計數 | HF1 鍵盤修正紀錄；HF3 本地驗收及雙語徽章畫面 |
| 3 | 地球圖示與語言選單 | HF1 鍵盤修正紀錄、雙語主頁與頂列焦點圖 |
| 4 | 鈴鐺辨識 | HF1 鍵盤修正紀錄、HF3 雙語徽章畫面 |
| 5 | 頂列維持純圖示 | HF1 雙語主頁畫面 |
| 6 | 本地化提示與鍵盤焦點 | HF1 鍵盤修正紀錄、雙語四個焦點畫面 |
| 7 | 真 App 圖示呈現 | HF1 原生 Tk 雙語畫面 |
| 8 | 圖示及語言切換保持幾何 | HF1 原生 Tk 幾何與語言畫面；HF3 雙位數徽章幾何 |
| 9 | 整輪警報、查看及人工確認 | HF2 真 Tk 人工確認前後畫面與 `../../../../../../docs/refactoring/HF2_RECOVERY_ACCEPTANCE_2026-10-16.md` |
| 10 | 保存／封存集中處理 | HF2 雙語保存失敗、封存失敗及恢復畫面 |
| 11 | 未保存輪次選取與重試 | HF2 前輪重試及保存恢復測試紀錄 |
| 12 | 封存重試及原有範圍 | HF2 全部符合資格輪次封存重試測試及畫面 |
| 13 | 保存失敗與封存失敗區分 | HF2 保存／封存失敗證據；HF3 封存失敗狀態證據 |
| 14 | 未確認警報與保存輪次計數 | HF3 同輪警報加保存異常的計數矩陣與畫面 |
| 15 | 每項警報各計一筆 | HF3 人工確認前後計數與恢復測試 |
| 16 | 同輪多保存／封存錯誤去重 | HF3 通知徽章 Tk 行為測試與輪次狀態 |
| 17 | 一般保存中不計異常 | HF3 0 值及狀態測試 |
| 18 | ⚠️ 待確認獨立計數 | HF3 兩類異常分開計數證據 |
| 19 | 開窗不清除異常 | HF3 反覆開窗、確認及重試生命週期測試 |
| 20 | 修復後計數減少 | HF3 封存／保存恢復及徽章消失雙語畫面 |
| 21 | 零徽章仍可開通知中心 | HF2 零警報鈴鐺入口及 HF3 0 值主頁畫面 |
| 22 | 多位數徽章不移位／遮擋點擊區 | HF3 12 筆畫面、點擊 hitbox 及 KVM/header 幾何測試 |
| 23 | 主頁移除大型舊控制區 | HF4 使用者提供的雙語真正 App 主頁／診斷畫面與驗收紀錄 |
| 24 | 簡短底部 App 狀態 | HF4 英文 `App events saved`、繁中 `App 事件已保存` 畫面 |
| 25 | 故障狀態可察覺 | HF4 狀態與 App 診斷失敗／重試測試 |
| 26 | 主頁診斷連結可開啟事件視窗 | HF4 使用者在前景中英各以滑鼠開啟的實測畫面與操作記錄 |
| 27 | 診斷及語言刷新失敗可查看／重試 | HF4 原始診斷視窗及失敗恢復測試 |
| 28 | 完整保存才可關閉 | HF2/HF4 關閉等待與完整 audit 測試 |
| 29 | 關閉失敗重試或取消 | HF2/HF4 關閉失敗重試、取消關閉桌面測試 |
| 30 | 📂 瀏覽／Browse 文案 | HF5 設定頁雙語真正 App 畫面 |
| 31 | 瀏覽選擇資料夾更新草稿 | HF5 原生選擇器回傳及草稿行為驗收 |
| 32 | 取消選擇保留草稿 | HF5 原生選擇器取消及草稿保留驗收 |
| 33 | 上排三等分 | HF5 原生像素量測與英文畫面 |
| 34 | 下排三等分 | HF5 原生像素量測與雙語畫面 |
| 35 | 等高、間距與雙語可讀 | HF5 bounds、兩語標籤量測及視窗內檢查 |
| 36 | 取消草稿可見且可操作 | HF5 最小視窗畫面與配置草稿回歸 |
| 37 | 清理空狀態明確 | HF6 雙語真正 App 空狀態畫面 |
| 38 | 未變摘要／閱讀位置穩定 | HF6 多次 150ms 更新、選取與閱讀位置驗收 |
| 39 | 更新／切語言保留合理位置 | HF6 切語言、內容變更及 scrollbar 驗收 |
| 40 | 長摘要可捲動 | HF6 80 行原始診斷與摘要捲動畫面 |
| 41 | 空白原因有重現及修復證據 | HF6 原生 Aqua 根因診斷、前後畫面及修復記錄 |
| 42 | 開啟視窗切語言保留狀態 | HF1–HF6：工具列焦點、通知列表選取／閱讀位置、HF5 草稿、HF6 閱讀位置測試 |
| 43 | KVM 色帶、標記與位置契約 | HF1/HF3/HF4 幾何回歸及本次整合桌面 KVM 檢查 |
| 44 | 真 App 繁中／英文整體畫面與操作 | HF1–HF6 原生雙語畫面；HF4 使用者前景滑鼠操作；HF7 整合檢查待補 |

## 前票證據位置

- HF1：`../../../../../../docs/refactoring/HF1_KEYBOARD_FIX_2026-10-16.md` 與 `../keyboard-fix/`、`../keyboard-fix-conda/`。
- HF2：`../../../../../../docs/refactoring/HF2_RECOVERY_ACCEPTANCE_2026-10-16.md` 與 `../../../../../../docs/refactoring/evidence/hmi-followup-2026-10-16/hf2/`。
- HF3：`../../hf3/local-validation.md`、`../../hf3/*.png`、`../../hf3/window-bounds.json`。
- HF4：`../../../../../../docs/refactoring/evidence/hf4/local-validation.md`、`../../../../../../docs/refactoring/evidence/hf4/hf4-english-diagnostics-and-main.png`、`../../../../../../docs/refactoring/evidence/hf4/hf4-traditional-chinese-diagnostics-and-main.png`。
- HF5：`../hf5/README.md`、`../hf5/hf5-settings-en.png`、`../hf5/hf5-settings-zh-TW.png`、`../hf5/hf5-settings-bounds.json`。
- HF6：`../hf6/README.md`、`../hf6/hf6-cleanup-render-en.png`、`../hf6/hf6-cleanup-render-zh-TW.png`、`../hf6/hf6-cleanup-empty-en.png`、`../hf6/hf6-cleanup-empty-zh-TW.png`、`../hf6/hf6-window-bounds.json`。

## HF7 整合回歸

桌面使用者確認釋出 Aqua 後，以目前整合基準執行下列受影響入口：

- 工具列視覺 Tab 順序、KVM 幾何、通知徽章生命週期。
- 通知中心人工確認、保存／封存重試、恢復與雙語狀態。
- 主頁精簡、診斷入口及事件檢視。
- 設定頁瀏覽文案／三等分像素版面。
- 保存期限頁摘要可見且閱讀位置穩定。
- 關閉等待、取消關閉與失敗後重試；確認輪次／稽核保存完整。

### 執行結果

1. 原生 HF1 工具列與 KVM 幾何：`test_hm1_toolbar_title_status_and_kvm_geometry_stay_fixed`，1/1 通過（7.702 秒）。
2. 其餘 11 項整合 Tk 測試：10/11 通過（31.239 秒）。工具列 Tab 測試在該批次中唯一失敗，觀察值為 `root.focus_get() is None`，不是焦點移到錯誤控制項。
3. 隔離重跑同一個工具列 Tab 測試：1/1 通過（2.803 秒）。因此 12 個不同測試條件均至少有一次原生 Aqua 綠燈；批次的焦點未啟用現象保留在紀錄中，不隱去失敗。
4. 獨立 KVM 顯示契約：`test_kvm_display_contract`，7/7 通過（0.001 秒）。

整合 Tk 測試範圍為工具列 Tab 順序、通知計數生命週期、恢復中心跨語言選取／捲動、人工確認與重複保存故障恢復、未保存／已保存／已封存狀態、主頁診斷入口、雙語 App 診斷、設定三等分原生像素布局、清理摘要可見與閱讀位置、取消關閉及保存完整後重試關閉。故障使用受控檔案寫入邊界注入；檢查使用真正 `B518LogSolutionApp` 和磁碟紀錄，不直接指定徽章計數或 widget 文字。

#### HF7 執行命令

```sh
B518_TK_TESTS=1 \
B518_TK_EVIDENCE_DIR="$PWD/docs/refactoring/evidence/hmi-followup-2026-10-16/hf7" \
  ./scripts/run_macos_desktop.sh scripts/run_tests.py \
  test_log_solution_ui.LogSolutionUiTests.test_hm1_toolbar_title_status_and_kvm_geometry_stay_fixed \
  test_log_solution_ui.LogSolutionUiTests.test_toolbar_keyboard_traverses_visual_order_and_leaves_toolbar \
  test_log_solution_ui.LogSolutionUiTests.test_real_tk_notification_badge_stays_until_alarm_is_acknowledged \
  test_log_solution_ui.LogSolutionUiTests.test_recovery_archive_list_preserves_selection_and_scroll_across_poll_language_reopen \
  test_log_solution_ui.LogSolutionUiTests.test_recovery_acknowledges_only_manually_and_session_retry_keeps_evidence_once \
  test_log_solution_ui.LogSolutionUiTests.test_real_tk_distinguishes_unsaved_saved_and_archived_round_states \
  test_log_solution_ui.LogSolutionUiTests.test_hf4_dashboard_uses_compact_status_and_diagnostic_entry \
  test_log_solution_ui.LogSolutionUiTests.test_real_tk_app_diagnostic_is_bilingual_inspectable_and_saved_before_close \
  test_log_solution_ui.LogSolutionUiTests.test_profile_editor_uses_three_equal_action_columns_and_browse_label \
  test_log_solution_ui.LogSolutionUiTests.test_cleanup_summary_is_visibly_drawn_in_the_real_settings_window \
  test_log_solution_ui.LogSolutionUiTests.test_close_waits_responsively_and_cancellation_invalidates_old_completion \
  test_log_solution_ui.LogSolutionUiTests.test_close_failure_keeps_window_open_and_real_retry_rebuilds_complete_audit

./scripts/run_macos_desktop.sh scripts/run_tests.py test_kvm_display_contract
```

The initial non-escalated Aqua process aborted with exit 134 before test collection. Re-running with authorized desktop access produced the results above. The focused toolbar test failed only in the multi-test process with no focused widget, then passed alone; this activation race remains recorded as an observation.

### 畫面檢視與環境限制

檢視 HF7 原生擷取的繁中／英文主頁、兩筆徽章、整輪警報與診斷、設定三等分及保存期限清理摘要。四個 emoji 清楚可辨，雙語固定位置一致；紅徽章未遮蓋地球、KVM 狀態標記與色帶；清理摘要文字實際可見且可捲動。視窗及控件 bounds 存於 `window-bounds.json`。HF2/HF3/HF4/HF5/HF6 的其他場景沿用本頁 44 項矩陣所列真 App 證據。

本次以 Framework Python/Tk 驗收，並未驗證 Conda Tk 原生滑鼠問題、打包發行版、其他 macOS／Tk 版本、工廠 KVM 傳輸與現場操作。工廠驗收另列，不阻擋本地程式及桌面驗收。沒有重跑完整測試套件或數小時歷史效能測試。
