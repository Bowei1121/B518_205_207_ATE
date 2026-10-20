# LS8 整合桌面驗收證據

Issue：[#94 — LS8：整體桌面驗收、打包與交付證據](https://github.com/Bowei1121/B518_205_207_ATE/issues/94)

## 版本與執行環境

- App 版本：`0.1.0`（`VERSION`）
- App 整合 commit：`b24ab21c3bd498518fbff2a036e8e2d85dc5dd26`（PR [#102](https://github.com/Bowei1121/B518_205_207_ATE/pull/102) 的 merge commit）。完整套件實際執行於 PR head `7168e5eae414d0a1394b8ab4da4d02b591b886aa`，輸出見 [`full-suite-rerun.log`](full-suite-rerun.log)。後續 `f8043c608e73432e1a6551cc34bc7db1a7690639` 僅修正本 README 的 requirements 連結，`src/`、`tests/` 未變，且完整測試 log blob 相同；整合 commit `b24ab21` 與 `f8043c6` 的 tree 相同。這些關係用於追溯相同的整合內容，不表示套件曾在後兩個 SHA 重新執行。
- 顯示契約：`1.3`，定義見 [`KVM_DISPLAY_CONTRACT.md`](../../KVM_DISPLAY_CONTRACT.md)。
- Claude 橋接交接：[`CLAUDE_KVM_HANDOFF.md`](../../CLAUDE_KVM_HANDOFF.md)。交接描述的 bridge snapshot 尚宣告契約 `1.1`，跨專案配對／部署未驗收。
- 主機：macOS `15.8.1`、`x86_64`（Intel）；M4/Apple Silicon 目標機未提供。
- Python：`3.12.10`，使用專案 `.venv-python31210`。
- macOS arm64 指定依賴：PyInstaller `6.16.0`，desktop test requirements 中 PyObjC Core/Cocoa/Quartz `11.1`；requirements 檔為 [`requirements-macos15-arm64.txt`](../../../../requirements/requirements-macos15-arm64.txt) 及其引用檔。
- `check_macos_build_python.py --exact-version 3.12.10 --architecture "$(uname -m)" --requirements requirements/requirements-macos15-arm64.txt --require-virtualenv` 通過。
- preflight 完整輸出：[`python-preflight.txt`](python-preflight.txt)。
- `check_macos_native_test_access.py` 在登入桌面取得原生事件送出與監聽權限，未變更系統權限；完整輸出：[`native-test-access.txt`](native-test-access.txt)。
- arm64 建置腳本在架構檢查處依預期拒絕 Intel 主機；輸出：[`arm64-build-blocker.txt`](arm64-build-blocker.txt)。腳本在此 gate 前尚未遞增 `VERSION` 或建立 bundle。

## 自動化驗收

完整命令：

```sh
B518_TK_TESTS=1 .venv-python31210/bin/python scripts/run_tests.py
```

完整輸出：[`full-suite-rerun.log`](full-suite-rerun.log)。結果：580 tests、351.704 秒、`OK (skipped=3)`。三個 skip 分別是兩項需要預先建置 H8 fixture 的容量測試，以及需人工切換 macOS 外觀的測試；log 記錄了原因。測試涵蓋應用、round coordinator、資料保存、歷史查詢、計時、心跳、顯示契約及多個真實 Tk/native input 案例；不得將 skipped 個案計為通過。

修正前的 580 項基線輸出保存在 [`full-suite.log`](full-suite.log)，其中兩個 UI failure 和一個 coordinator 清理 error。修正後下列三個原失敗測試獨立重跑均通過：

- `test_m10_integration.M10SourceIntegrationTests.test_visible_start_validation_notice_refreshes_without_accepting_a_round`
- `test_m10_integration.M10SourceIntegrationTests.test_visible_prevalidation_failure_preserves_previous_complete_result_until_explicit_restart`
- `test_round_start_preparation.RoundStartPreparationTests.test_all_registered_platforms_start_through_the_preparation_interface`

## T01–T19 驗收狀態

本機完整自動化測試提供整合回歸證據；這不等於逐項現場操作紀錄。以下硬體／人工項目仍須在指定目標設備完成：

| 項目 | 狀態 | 證據／限制 |
| --- | --- | --- |
| T01 開始與準備 | App 自動化覆蓋 | `test_monitoring_elapsed_includes_preparation_then_freezes_and_round_trips`、`test_accepted_round_stays_preparing_until_background_source_baseline_is_ready` |
| T02 完成與待確認 | App 自動化覆蓋 | `test_completed_round_stops_timer_before_review_and_archive_wait`、`test_round_with_pending_conflict_is_protected_until_operator_resolves_it` |
| T03 人工停止、逾時、取消、啟動失敗 | App/Tk 自動化覆蓋 | `test_real_tk_abort_paths_keep_accepted_round_time_frozen`、`test_round_deadline_alarm_is_created_once_and_acknowledgement_releases_results`、`test_accepted_source_start_failure_requires_reset_and_audits_cancellation` |
| T04 未受理失敗、新輪歸零、按鈕／快捷鍵 | App/Tk 自動化覆蓋 | `test_unaccepted_start_failure_keeps_previous_round_elapsed_time`、`test_real_tk_button_and_hotkey_share_start_admission` |
| T05 保存重試、重開、舊紀錄相容 | App 自動化覆蓋 | `test_failed_stop_event_write_retries_once_with_original_round_and_frozen_time`、`test_normal_round_can_be_rebuilt_from_a_fresh_disk_reader`、audit schema compatibility tests |
| T06 時間單調、忙碌恢復、超過 15 分 | App/Tk 自動化覆蓋 | `test_monitoring_elapsed_includes_preparation_then_freezes_and_round_trips`、`test_monitoring_elapsed_format_keeps_full_minutes`、`test_real_tk_round_timer_stays_fixed_through_language_and_long_minutes` |
| T07 固定計時區與語言／容量／縮放 | 真 Tk 自動化覆蓋 | `test_real_tk_round_timer_stays_fixed_through_language_and_long_minutes`、`test_li7_geometry_at_both_scalings_and_all_capacities` |
| T08 心跳狀態矩陣及銷毀 | 真 Tk 自動化覆蓋 | `test_ls6_real_tk_heartbeat_cycles_blocks_tracks_states_and_cleans_up`、KVM display contract tests |
| T09 畫面阻塞與恢復 | 真 Tk 自動化覆蓋 | `test_ls6_real_tk_heartbeat_cycles_blocks_tracks_states_and_cleans_up`；原生事件權限檢查成功 |
| T10 KVM 幾何／每格至少 12×12 遠端像素 | App 幾何已測；遠端像素未驗收 | `test_li7_geometry_at_both_scalings_and_all_capacities` 驗證本機幾何；沒有配對擷取，不能證明遠端像素尺寸 |
| T11 遮擋、可讀性、壓縮雜訊 | App 分類自動化覆蓋；遠端影像未驗收 | `test_low_contrast_missing_or_unknown_marker_is_not_recognized`、KVM frame classification tests；真實 KVM 壓縮樣本缺席 |
| T12 橋接取樣與交接 | 部分完成；bridge 未驗收 | [`CLAUDE_KVM_HANDOFF.md`](../../CLAUDE_KVM_HANDOFF.md) 提供 App 契約交接；三張新鮮影像與 bridge 行為須另行配對 |
| T13 計時、就緒與結果證據區分 | App 自動化覆蓋 | `test_source_preparation_time_counts_toward_round_deadline_without_blocking_ui_caller`、`test_real_tk_start_button_prepares_every_registered_platform_profile` |
| T14 查詢交錯與舊回覆 | 真 Tk 自動化覆蓋 | `test_real_tk_qp3_cached_pages_detail_language_and_cancelled_requery`、`test_real_tk_reads_five_pages_while_remaining_batches_are_paused` |
| T15 固定查詢結果、取消、語言切換 | 真 Tk 自動化覆蓋 | `test_real_tk_qp3_cached_pages_detail_language_and_cancelled_requery`、`test_language_refresh_preserves_event_log_reading_position` |
| T16 關窗與查詢資源生命週期 | 真 Tk 自動化覆蓋 | `test_real_tk_close_waits_responsively_and_cancellation_invalidates_old_completion`、`test_real_tk_qp3_cached_pages_detail_language_and_cancelled_requery` |
| T17 啟動錯誤分類與畫面失敗保留輪次 | 真 Tk 自動化覆蓋 | `test_visible_source_failure_notice_and_fixed_bilingual_audit`、`test_real_tk_presentation_failure_keeps_accepted_round_and_diagnostic`、本次修正的兩個 M10 integration tests |
| T18 防重入與晚到準備工作 | App/Tk 自動化覆蓋 | `test_repeated_start_while_running_keeps_the_same_round`、`test_start_during_preparation_can_stop_and_late_source_does_not_restart_round` |
| T19 Python／套件／bundle／目標發布 | 本機 preflight 與 checker 自動化已測；arm64/M4 未驗收 | Python `3.12.10` preflight 通過；`test_verify_macos_bundle` 驗證器測試通過。Intel x86_64 無法產生目標 arm64 bundle、簽章或 M4 證據；架構 gate 輸出見 `arm64-build-blocker.txt` |

## 已修正的整合問題

啟動失敗時，Tk modal notice 會進入巢狀事件迴圈。舊順序先顯示對話框，之後才更新 round snapshot，因此對話框期間按鈕與狀態標記仍呈現前一狀態。現在先套用失敗後的 snapshot、更新控制項，再顯示提示，避免重新啟動與顯示狀態過期。

另外，round preparation 測試先前停止 coordinator 後仍未關閉 session writer，就刪除暫存目錄；測試現在等 coordinator close 完成再清理。兩個非同步 monitoring round 測試也在結束時停止輪次並 flush audit，避免背景 monitor 留到 deadline 後才報錯。

## 交付限制

此證據僅支持 Intel macOS 15.8.1 上的 App 本機自動化與 Tk 驗收。Issue #94 的 arm64/M4 打包、bundle 簽章、目標機及 bridge 配對項目仍未驗收；本 PR 不應用來宣稱這些項目已通過，也不代表可以關閉 #94。
