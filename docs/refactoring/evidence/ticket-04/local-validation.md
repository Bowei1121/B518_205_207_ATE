# Ticket 04 本機驗收紀錄

日期：2026-10-07（Asia/Taipei）  
固定 code-review 基準：`ddd19f979dc1d241e3bf66c45f15ff4c0e831bb5`  
驗收分支：`round/ticket-04`  
實作提交：`67e8a15`、`ea1f11e`、`945162a`、`74f9029`、`7a241be380b55cd237908554d60fcb584f3ebfc8`；測試 fixture 後續提交：`60ddc79c27c1517b416b2748729b4e23784d2ab2`
環境：Python 3.8.10、macOS 15.7.9、x86_64、Git 2.50.1；完整套件與 Tk 案例在可存取桌面圖形工作階段執行。

## 基準與變更保護

- 從主線 `B518-Log-Solution` 的固定程式基準 `ddd19f979dc1d241e3bf66c45f15ff4c0e831bb5` 建立專用分支及隔離 worktree。Ticket 01～03 已在該基準中；沒有覆寫既有工作目錄修改。
- 開始前即時 fetch 並核對本地、Gitea `origin`、GitHub `github` 的主線 refs；當時均為固定基準。遠端沒有 `round/ticket-04`，故建立新分支。`origin` 的兩個 push URL 分別是 Gitea 與 GitHub；`github` remote 也指向同一 GitHub 目的地，目的地按實際服務計為兩個。
- Ticket 04 修改提交 `67e8a15`、`ea1f11e`、`945162a`、`74f9029`、`7a241be` 均推送成功。每次 `git push origin round/ticket-04` 後，對 Gitea 與 GitHub 執行 `git ls-remote --heads ... round/ticket-04`，兩者均核對到相同提交；首次 push 已設定 upstream。
- 合併前仍須再次即時檢查主線工作樹與兩個 push 目的地。開始時的遠端資料不代表合併當下狀態。

## 六項驗收結果

| Ticket 04 驗收項目 | 結果 | 證據 |
| --- | --- | --- |
| 取代兩秒等待後警告並關閉；檢查本次全部前輪與目前輪；audit 不完整不得關閉 | 通過 | `test_close_recovers_a_failed_previous_round_and_current_round_without_crossing_events` 驗證跨輪重試。`test_successful_flush_does_not_allow_close_when_audit_is_incomplete` 覆蓋 flush 成功但 `audit_complete=False`。真正 Tk 的 `test_close_waits_responsively_and_cancellation_invalidates_old_completion` 將 audit 寫入以 Event 暫停超過原兩秒界線，確認視窗存活且 `after` 事件執行；之後重試及磁碟重建成功才銷毀。 |
| 等待、失敗、重試時 Tk 可操作；關閉與重試不重入 | 通過 | 真正 Tk 的 `test_close_failure_keeps_window_open_and_real_retry_rebuilds_complete_audit` 保持保存故障、重複點擊重試、等待及取消時持續泵送 Tk；同一輪不並行重試。重複關閉由 `test_close_waits_responsively_and_cancellation_invalidates_old_completion` 覆蓋。 |
| 取消保留保存資料與操作資源，不重啟來源；熱鍵只在成功關閉時釋放 | 通過 | 上述真實 Tk 測試在來源停止保存交接中取消，確認 hotkey 未關閉、來源 start 次數不增加；放行原寫入後重試關閉，完成後才關 hotkey。另一案例在保存重試中取消，確認原重試繼續並可再次請求關閉。 |
| 故障修復後可正常關閉；歷史錯誤不永久阻擋；沒有略過保存選項 | 通過 | 真實 Tk 持續故障案例解除磁碟寫入故障、按 UI 重試後，Session 與 audit 皆由暫存磁碟重建，audit 有序且 `audit_complete=True`，視窗隨後正常銷毀。UI 提供取消及重試，沒有略過未保存資料的正常關閉操作。 |
| 共同入口可查詢關閉狀態；不掃描歷史 Session、不改變產品放行條件 | 通過 | `RoundCoordinator.request_close()`、`close_status()`、`retry_close_saves()`、`cancel_close()` 提供公開協調與狀態。`test_graceful_close_waits_for_every_current_run_round_to_be_durable` 在 audit 根目錄放入歷史目錄，關閉只等待本次追蹤輪次且不觸碰歷史檔。全套產品放行測試仍通過。 |
| 真正 Tk 成功、暫時／持續故障、跨輪故障、取消及再次關閉流程 | 通過 | `test_close_waits_responsively_and_cancellation_invalidates_old_completion`、`test_close_failure_keeps_window_open_and_real_retry_rebuilds_complete_audit`、`test_real_tk_close_waits_for_source_preparation_before_destroy`、`test_real_tk_close_keeps_conflict_and_alarm_actions_available` 均建立實際 `tk.Tk`／`B518LogSolutionApp`、操作實際關閉／取消／重試及人工處理按鈕，使用暫存 Session/audit 路徑並由磁碟讀取器重建。 |

來源準備競爭以 Event 阻塞真正 Tk 關閉流程：Tk `after` 持續執行、視窗不被銷毀；來源交接完成且 audit 重建完整後才完成關閉。另一真正 Tk 案例在關閉等待期間逐一操作衝突裁決及警報確認，確認事件保留正確 round ID 且落盤後才能關閉。`test_close_waits_for_inflight_operator_resolution_and_freezes_after_completion` 以 Event 控制人工裁決與關閉交錯，確認進行中的裁決先完成並落盤，完整快照後的重複操作不新增事件。

## 執行命令與結果

以下命令於 `B518 Log Solution` 程式目錄執行：

- 聚焦套件：`PYTHONPATH=src:tests python3 -m unittest test_monitoring_round test_log_solution_ui`，85 tests 通過，24.022 秒；包含真正 Tk 案例。
- 完整套件：`python3 scripts/run_tests.py`，225 tests 通過，34.943 秒；在可存取桌面圖形工作階段執行，所有 Tk 案例實際執行。
- 語法編譯及差異：`python3 -m compileall -q src tests && git diff --check`，通過。
- TDD 修正證據：來源準備 Tk 案例首次重現關閉狀態停留在 saving 的問題，修正後等待狀態可見且案例通過；關閉人工操作案例先確認衝突與警報可由實際 UI 操作並保存，後續另加入受控操作競爭測試。
- 完整套件初次執行曾在既有「平台監控由共同入口啟動」案例逾時；該案例單獨執行通過。進一步查出該案例曾讀取共用 `/tmp/b518-ticket15-test-preferences.json`，會受其他測試留下的設定影響；改為每次呼叫使用隔離的 `TemporaryDirectory` 後，完整套件於 Ticket 分支通過 225 tests（39.615 秒）。啟動等待保留 8 秒上限並在失敗時輸出輪次快照診斷，沒有放寬產品行為驗收。
- 型別檢查設定查找：`rg --files -g 'mypy.ini' -g '.mypy.ini' -g 'pyrightconfig.json' -g 'pyproject.toml' -g 'setup.cfg' -g 'tox.ini' -g 'Makefile' -g 'Pipfile'`，沒有找到型別檢查器設定；未宣稱型別檢查通過。`compileall` 僅驗證語法。

## 審查與交付狀態

固定基準 `ddd19f979dc1d241e3bf66c45f15ff4c0e831bb5` 的 Standards／Spec 雙軸複審已完成，均無未解問題。Standards 初審指出 coordinator 直接使用準備事件私有欄位，改以 `MonitoringRound.wait_until_prepared()` 公開能力處理；複審指出 operator 狀態判定重複及 `CloseSnapshot.error` 名稱不符合 waiting 訊息，已抽出共用判定並改名 `message`。Spec 初審指出關閉完成快照與人工操作間有競爭，及缺少真正 Tk 來源準備案例；已加入輪次原子完成凍結、Event 控制的競爭回歸與真正 Tk 準備案例，Spec 最終複審確認已解決且無其他發現。

目前最新實作 commit `7a241be380b55cd237908554d60fcb584f3ebfc8` 及測試 fixture follow-up `60ddc79c27c1517b416b2748729b4e23784d2ab2` 已同步至 Gitea、GitHub；最終雙軸複審涵蓋此 branch HEAD，無未解問題。初次合併後完整套件發現上述測試 fixture 隔離問題，故分支保留並補上修正；Ticket 分支完整測試現已通過。最終合併後驗證、合併 SHA、同步 refs 與分支清理結果將在此處追加。
