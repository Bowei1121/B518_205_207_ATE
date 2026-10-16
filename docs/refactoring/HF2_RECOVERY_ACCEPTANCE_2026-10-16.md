# HF2 鈴鐺恢復中心實作及桌面驗收

日期：2026-10-16（Asia/Taipei）。工作分支 `codex/hf2-acceptance-fix`，基準 `e4cd033a2d98ea7945592017f6ea9a76e5e29fbc`。本文件只記錄 HF2，不代表後續 HF3～HF7 已完成。

## 修復與根因

1. 零警報分支僅停用確認按鈕，未重新翻譯文字；真正 Tk RED 為 `確認整輪警報 != Acknowledge Round Alarm`。補上零狀態翻譯後雙語、停用條件及重開通過。
2. 恢復清單每 150ms 刪除重填，破壞捲動位置；改為可見文字變更時才更新、按輪次識別保留選取並還原捲動。24 個真正暫存 Session／可信封存輪次測試，在 760×520 最小視窗選第 18 筆、捲動、經多輪 polling、切兩語、隱藏重開，位置及選取一致。
3. 無界限 Label 顯示完整長原始診斷，會膨脹布局，舊主頁摘要同樣受影響。80 行磁碟錯誤初次驗證曾在 Tk 更新停滯約 36 秒，被中斷並記為失敗，未作通過證據。恢復中心詳細區改唯讀可捲動 Text；主頁舊恢復控制完整保留，僅把舊摘要限制為第一行最多 120 字，完整 raw 診斷仍保留於新視窗及磁碟。最後以原本完整 80 行故障重驗通過，未靠縮短 fixture 交付。
4. 逐張檢視原生截圖發現英文欄位自然寬度會把右側重試按鈕推出視窗；設定等寬欄、可換行標題。證據擷取同步檢查按鈕四邊位於實際視窗內，900×620 與 760×520 均通過。
5. 已封存輪次的空原因原本送到「未知清理原因」翻譯；真正 Tk RED 重現已封存卻顯示 `Cleanup reason is not recognized`。改為顯示可信封存時間，失敗仍分別呈現本地化原因及完整原始診斷。
6. 真正 Session 寫入故障成功重試後，`read_round_audit` 與串流 `iter_round_audit_events` 原本因任意歷史 `session_write_failed` 永久判不完整，導致「完整保存／受保護」且不能可信封存。兩種 reader 現在依事件順序追蹤尚未恢復的保存故障；後續已耐久的 `save_recovered` 才解除該故障。事件序號仍須從 1 連續完整，恢復事件不豁免缺失、格式、身分或順序檢查。歷史錯誤保留。

## 驗收入口與操作結果

使用完整 `B518LogSolutionApp`，真 Aqua Tk 視窗、真暫存 Session／audit 寫入，僅在作業系統檔案開啟／寫入／replace 邊界注入可控故障。未建立測試專用業務接口。

- 鈴鐺零警報可開，兩頁雙語空狀態可讀。
- 整輪逾時警報顯示 alarm ID、round ID、原因。反覆開關／切語言都不確認；實際呼叫新 `recovery_alarm_ack_button.invoke()` 才產生單筆確認事件。確認當下 Session 故障仍是 failed，未假裝保存成功。
- Session `events.log` 連續兩次開啟失敗，從新「重試所選」恢復；再注入一次 `save_recovered` 自身 audit 寫入失敗，確認仍 failed、不能可信封存，再按新按鈕才恢復。最終 probe 只保存一次、確認事件只一筆、事件序號連續、兩種 reader 一致完整，可信封存與正常關閉成功。
- 磁碟變體反證：缺序號但有 recovered、沒有 recovered、recovered 後有新失敗，兩種 reader 皆拒絕完整性。
- audit 寫入首次失敗、重試再次失敗、再重試成功，全部由新按鈕完成；背景重試時 Tk after callback 可繼續執行，重複按停用按鈕不重複送件。完整 80 行 raw 仍可捲動閱讀；polling／切語言／隱藏重開維持閱讀位置。
- 選擇前一輪失敗紀錄後從新按鈕保存，磁碟 probe 只一筆，當前 active round 與 WAITING 結果板不變。
- 兩個獨立 Session 的封存皆先失敗，選取一輪後按「重試所有符合資格的封存（2）」；兩輪均產生真正 round-archive.json、audit 連續無重複序號。保存失敗與封存失敗各有獨立可讀狀態。
- 未追蹤的歷史 Session sentinel 保留且不出現在恢復輪次清單；沒有擴大歷史掃描。
- 主頁原有保存、選輪及封存恢復入口仍保留。沿用關閉保存失敗、重試、取消關閉與雙語失敗隔離回歸，不改 KVM／判定／保存政策。

## 環境、命令及結果

macOS 15.7.9（24G830）；`/Library/Frameworks/Python.framework/Versions/3.8/bin/python3`，Tk 8.6.8。真正 Tk 需沙盒外桌面存取。Conda Tk 8.6.12 原生滑鼠差異仍沿用 HF1 文件限制；這份 HF2 驗收使用已驗證的 Framework runtime。

工作目錄為 repo 下 `B518 Log Solution`。

```zsh
PYTHONPATH=src /Library/Frameworks/Python.framework/Versions/3.8/bin/python3 scripts/run_tests.py \
  test_language_catalog test_round_archival test_monitoring_round test_audit_records
# 101 tests / 21.249s / OK（audit reader 修正後）

PYTHONPATH=src /Library/Frameworks/Python.framework/Versions/3.8/bin/python3 scripts/run_tests.py \
  test_historical_event_query test_historical_event_display
# 74 tests / 28.085s / OK（兩種 reader 影響的有界歷史查詢回歸）
```

最後桌面驗收 **8/8 通過（56.656 秒）**。最後桌面命令與逐項結果完整保存於 [tk-tests.txt](evidence/hmi-followup-2026-10-16/hf2/tk-tests.txt)，八個測試方法均在 `test_log_solution_ui.LogSolutionUiTests`：

```zsh
B518_TK_TESTS=1 \
B518_TK_EVIDENCE_DIR="$PWD/../docs/refactoring/evidence/hmi-followup-2026-10-16/hf2" \
PYTHONPATH=src /Library/Frameworks/Python.framework/Versions/3.8/bin/python3 scripts/run_tests.py \
  test_log_solution_ui.LogSolutionUiTests.test_recovery_archive_list_preserves_selection_and_scroll_across_poll_language_reopen \
  test_log_solution_ui.LogSolutionUiTests.test_recovery_zero_alarm_language_and_reopen_preserve_tab \
  test_log_solution_ui.LogSolutionUiTests.test_recovery_acknowledges_only_manually_and_session_retry_keeps_evidence_once \
  test_log_solution_ui.LogSolutionUiTests.test_real_tk_distinguishes_unsaved_saved_and_archived_round_states \
  test_log_solution_ui.LogSolutionUiTests.test_real_tk_retry_button_recovers_disk_record_once_without_blocking_ui \
  test_log_solution_ui.LogSolutionUiTests.test_real_tk_can_select_and_retry_previous_round_without_changing_current_board \
  test_log_solution_ui.LogSolutionUiTests.test_conflict_and_alarm_refresh_fail_independently_and_retry_latest_language \
  test_log_solution_ui.LogSolutionUiTests.test_close_failure_keeps_window_open_and_real_retry_rebuilds_complete_audit
```

## 原生畫面證據

[證據目錄](evidence/hmi-followup-2026-10-16/hf2/) 中各情境都有 `-en.png`、`-zh-TW.png`：`hf2-zero-alarm`、`hf2-zero-recovery`、`hf2-alarm-pending`、`hf2-alarm-acknowledged`、`hf2-save-failure`、`hf2-archive-failure`、`hf2-archive-recovered`、`hf2-session-recovered`、`hf2-list-reading`，另有既有關閉保存雙語回歸畫面。`hf2-window-bounds.json` 保留每個恢復場景的實際幾何；`window-bounds.json` 是關閉保存回歸幾何。

圖像來自 Quartz 擷取同 PID 真 App 原生視窗。擷取前讓 Aqua 完成畫面更新，逐張檢視關鍵英／中畫面；原先錯分頁、過早擷取及欄寬溢出的產物已由修正後重拍結果取代，未當驗收證據。

## 工廠範圍

仍需現場確認正式打包 App、正式工站磁碟／權限／網路分享位置、實際逾時與人工處理，以及 KVM 傳輸辨識。以上獨立於已完成的本機程式與真正桌面驗收，不聲稱已到廠測試。不重跑數小時歷史資料容量驗收。
