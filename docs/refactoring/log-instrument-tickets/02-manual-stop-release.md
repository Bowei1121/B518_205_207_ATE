## Parent

[父規格 #77：Log Solution 儀器狀態、人工停止與顯示契約 1.2](https://github.com/Bowei1121/B518_205_207_ATE/issues/77)

## What to build

操作員在監控或來源準備中按停止，都立即取得完整格位結果；保留已完成值，未完成為 STOPPED，無待確認後顯示獨立人工停止完成圖樣，磁碟可重建同一事實。

從停止操作到格位定案、結果放行、HMI／圖樣及稽核重建一次完成；未見監控就緒後取消本輪的本地操作由 LI5 接續。

主責使用者故事：22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 78。
依父規格實作決策：7, 8, 9, 10, 18, 19；測試決策：5, 6, 11, 12, 14。

本票只驗收本程式的公開輪次行為／磁碟資料與必要真App／Tk輸出；不要求KVM_Log、JetKVM或LabVIEW驗收。

## Acceptance criteria

- [x] 保留既有 PASS／FAIL／NOTEST／TIMEOUT 等終局值，只把未完成格定案為 STOPPED；通道文字與灰色色帶一致，不清空整輪、不轉成 FAIL、不替操作員決定重工範圍。
- [x] 來源尚未建立時停止也按固定配置立即產生完整格位，不等 factory 返回才呈現；配置容量與非恆等映射下結果均正確，空／缺格／重複格不得可交付。
- [x] 停止後延遲來源成功或失敗均不能重啟本輪、改掉 manual_stop 原因、覆蓋已定案格位或將輪次偽裝為啟動失敗。
- [x] 保留整輪人工停止種類，即使停止當下所有格位都已有終局且沒有 STOPPED 格，也不以顏色推測停止原因。
- [x] 仍有衝突／未確認警報時保持 REVIEW，不提前放行；處理既有可信衝突及警報後才 MANUAL_STOP_COMPLETE／READY，標記0011與公開結果一致。
- [x] 一般完成與人工停止的可交付判定都驗容量完整及無待確認；結果放行不以 Session／audit／封存成功作新前置。
- [x] 重複停止或重複已完成處理不重複定案／寫入；保留未知同輪來源原處置，不開放採用未知候選。
- [x] 透過公開停止、裁決與確認操作形成紀錄；新的磁碟讀取者能重建逐格狀態、manual_stop及交付種類，不假造一般finished、不重寫1.1歷史資料或推定其曾交付。
- [x] 保存失敗可見且可恢復、重試不漏寫不重複，仍完整保存才正常關閉；原雙語與資料保護規則保持。
- [x] 以正常監控、準備阻塞、混合終局、所有格位終局但仍待確認等情境做公開入口及真正App驗證；尚未定稿幾何不妨礙本機展示此停止路徑。

## Blocked by

- https://github.com/Bowei1121/B518_205_207_ATE/issues/78

## LI2 驗收紀錄

**整合內容：** 人工停止在監控中保留既有終局，只把未完成格寫成 STOPPED；準備阻塞時按凍結容量立即公開 STOPPED 格位。完整容量與無待確認才放行為 manual_stop，並透過獨立 `manual_stop_completed` 稽核事件讓新讀取者重建交付種類。衝突／警報未處理時留在 REVIEW；延遲來源成功或失敗、重複停止及重複裁決不改寫已結論。遲到 monitor 的 STOPPED 回報會記成 `manual_stop_late_result_ignored`，保留稽核序列但不重複定案產品格位。

**驗收條件對照：**

- 混合終局測試保留 PASS／FAIL／NOTEST／TIMEOUT，活動中的格位改為 STOPPED；TK 色帶顯示灰色 STOPPED，整輪 reason 保持 `manual_stop`。
- 準備阻塞測試使用固定 capacity 4 立即生成 4 個 STOPPED；真 App 額外以 capacity 2 驗證立即交付。非恆等來源／顯示 mapping 由現有輪次與配置回歸涵蓋。可交付性精確檢查容量位置集合和數量；空、缺格、重複格不會放行。
- 來源解除阻塞後成功仍不恢復監控；來源準備延遲失敗也不改寫為 `start_failed`。所有終局格但保留可信衝突時保持 REVIEW，裁決後才以人工停止種類放行。
- `manual_stop_completed` 不使用一般 `finished`，Audit reader 重建逐格值、manual_stop 與 `result_available`；保存／稽核重試與正常關閉規則沿用既有協調器。
- 真 App 透過實際開始／停止按鈕、可信來源事件、衝突裁決操作及 Tk marker Canvas 驗證，沒有依賴 KVM、JetKVM、LabVIEW 或 ATE。

**實際命令與結果：**

- TDD red：`PYTHONPATH=src python3 -m unittest tests.test_monitoring_round.MonitoringRoundTests.test_manual_stop_preserves_completed_results_and_marks_incomplete_stopped tests.test_monitoring_round.MonitoringRoundTests.test_manual_stop_keeps_mixed_terminals_and_stops_only_incomplete_positions tests.test_monitoring_round.MonitoringRoundTests.test_manual_stop_during_source_preparation_publishes_full_configured_results_immediately -v`，3 項按預期失敗（人工停止尚未放行、準備中沒有格位）。
- 輪次、磁碟與圖樣回歸：`PYTHONPATH=src python3 -m unittest tests.test_monitoring_round tests.test_audit_records tests.test_kvm_display_contract -v`，90/90 通過。
- 準備與來源映射回歸：`PYTHONPATH=src python3 -m unittest tests.test_round_start_preparation tests.test_configured_monitor tests.test_platform_registry -v`，26/26 通過；涵蓋延遲來源成功／失敗、準備中停止後關閉及非恆等來源映射。未 ready 的 Session 沒有有效起訖時間時，close 仍完整保存輪次 audit，該 Session 保持 protected 且不可清理，不偽造一般啟動或完成。
- 真 App/Tk：`PYTHONPATH=src /opt/anaconda3/bin/python3 tools/smoke_li2_manual_stop_app.py`，通過；macOS 15.8.1、x86_64、Python 3.11.7、Tk 8.6。檢查程序 PID 與主視窗標題，再以 Quartz 擷取真正 B518 Tk 視窗；四種情境的 Canvas 黑白格、HMI 文字／色帶均和公開 snapshot 一致；3 輪新讀取者 audit 重建均保留 manual_stop 和交付種類。
- 真 Tk 保存回歸：`B518_TK_TESTS=1 PYTHONPATH=src /opt/anaconda3/bin/python3 -m unittest tests.test_log_solution_ui.LogSolutionUiTests.test_real_tk_app_diagnostic_is_bilingual_inspectable_and_saved_before_close tests.test_log_solution_ui.LogSolutionUiTests.test_real_tk_close_keeps_app_write_failure_open_and_retries_it tests.test_log_solution_ui.LogSolutionUiTests.test_real_tk_close_waits_for_source_preparation_before_destroy tests.test_log_solution_ui.LogSolutionUiTests.test_real_tk_close_keeps_conflict_and_alarm_actions_available -v`，使用桌面 GUI 權限重跑後 4/4 通過。
- `git diff --check`：通過。

**證據：** `B518 Log Solution/docs/refactoring/evidence/li2-real-app/{preparing-stop,mixed-terminal-stop,all-terminal-review,manual-stop-released}.png`、`run.json` 及 `B518 Log Solution/tools/smoke_li2_manual_stop_app.py`。四張畫面均由 B518 主視窗截取；手動停止放行圖可見 PASS／FAIL 保留、Stopped 文案及 marker，待確認畫面顯示 REVIEW 與衝突數。

**限制：** 未執行外部 KVM、JetKVM、LabVIEW、ATE 驗收；這些不在本票範圍。準備中停止建立的未 ready Session 不具有效開始／完成時間，因此保留為 protected 而不產生歸檔；輪次 audit 已保存並可重建，close 流程仍完成。

**整合與 Issue 狀態：** 已整合至 `codex/log-instrument-1-2`，整合 commit `d3a9fca79b4ad9ab48efeef68ec59c60a4f18a4a`；整合分支核心回歸 90/90 與 26/26 通過，`git diff --check` 通過。GitHub 與內部 Gitea 遠端 SHA 均核對為 `d3a9fca79b4ad9ab48efeef68ec59c60a4f18a4a`。GitHub #79 已留下完成紀錄並以 completed 關閉，回讀確認 CLOSED/COMPLETED。
