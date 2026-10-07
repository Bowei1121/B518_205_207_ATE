# Ticket 03 本機驗收紀錄

日期：2026-10-07（Asia/Taipei）  
固定 code-review 基準：`438dd951b6404c5a3f0a900ce08e4285066dd8ea`  
驗收分支：`round/ticket-03`  
目前實作提交：`abc5a8b152d56e7daf4ae60d1fee9049aae66fbe`  
環境：Python 3.8.10、macOS 15.7.9、x86_64、Git 2.50.1；完整套件及真正 Tk 測試在可存取桌面圖形工作階段執行。

## 基準與變更保護

- 開始前在原專案工作樹確認分支為 `B518-Log-Solution`，HEAD 為 `8ef240d`；該工作樹有一項既存未提交修改 `docs/refactoring/CONFLICT_DIALOG_DISCUSSION_2026-10-07.md`。本票在獨立 worktree 實作，沒有修改、暫存或提交該文件。
- 即時 fetch `origin` 與 `github` 後，兩者 `B518-Log-Solution` 均為 `438dd951b6404c5a3f0a900ce08e4285066dd8ea`；本地主線亦為同一 SHA。開始時兩個遠端均沒有 `round/ticket-03`，本地亦沒有同名分支。
- `origin` 設有 Gitea 與 GitHub 兩個 push URL；另有 fetch/push 指向 GitHub 的 `github` remote。實作提交推送後即時 `git ls-remote` 核對，兩個實際目的地的主線仍為固定基準、`round/ticket-03` 均為 `abc5a8b152d56e7daf4ae60d1fee9049aae66fbe`。
- 前次 Ticket 01／02 交付已有本機驗收紀錄，並在本次工作基準 `438dd951` 的歷史中；沒有以舊遠端同步紀錄替代本次 fetch／refs 查核。

## 驗收結果

| Ticket 03 驗收項目 | 結果 | 證據 |
| --- | --- | --- |
| 換輪保留前輪待保存資料、錯誤原因及重試入口，UI 辨識受影響輪次 | 通過 | `test_failed_previous_round_remains_queryable_and_retriable_after_new_round_starts` 先令前輪 audit 寫入失敗，再開始新輪，經公開 `unsaved_rounds()` 仍能按 round ID 讀到錯誤並呼叫指定輪次的 `retry_saves(round_id)`。真正 Tk 案例選取舊輪，於狀態列查看其錯誤原因並重試。 |
| 本次執行全部未保存輪次可查詢、指定重試及確認完整保存；新舊輪事件隔離 | 通過 | `test_multiple_failed_rounds_recover_independently_without_cross_round_records` 同時保留兩個舊輪及目前輪，逐輪恢復後分別從 audit 磁碟檔重建，檢查 `audit_complete`、輪次 ID、各自事件恰一筆且沒有對方事件。真正 Tk 案例重試舊輪後確認目前 round ID、結果與畫面仍屬於新輪。 |
| 已保存輪次釋放不必要物件及 worker；失敗／未保存輪次保留必要資料 | 通過 | `test_completed_round_objects_are_released_as_new_rounds_replace_them` 完成六輪並開始下一輪，以公開輪次行為及 monitor 弱參照確認前六輪不再被保留；未保存輪次則仍可查詢與重試。Audit worker 空閒退出與重啟生命週期沿用已合併 Ticket 01 並由其驗收紀錄及本次完整回歸套件覆蓋。 |
| 提供保存／封存／後續清理可共用的未保存輪次保護狀態，涵蓋全部追蹤而非目前輪次 | 通過 | `RoundCoordinator.unsaved_rounds()` 與 `has_unsaved_rounds` 對本次 coordinator 建立的所有輪次提供共同查詢及保護狀態；單輪失敗後狀態仍為 true，所有輪次完整保存後為 false。沒有加入 Ticket 04～07 的關閉、封存、期限或清理行為。 |
| 前輪故障、開始新輪、修復、磁碟重建、真正 Tk 跨輪重試，且不掃描歷史 Session | 通過 | `test_unsaved_tracking_is_limited_to_rounds_created_in_this_coordinator_run` 在暫存根目錄放入前次執行的歷史 audit 目錄，查詢結果只含本次建立的輪次。兩個跨輪故障案例以暫存磁碟及 `read_round_audit` 重建驗證；`test_real_tk_can_select_and_retry_previous_round_without_changing_current_board` 使用真實 Tk、SessionStore、audit 檔與受控 `Event` 暫停重試，確認視窗仍可處理 `after` 事件、重複點擊不會並行、修復後舊輪完整且新輪畫面不受污染。 |

## 執行命令與結果

以下命令於 `B518 Log Solution` 目錄執行：

- TDD 紅燈：`python3 scripts/run_tests.py test_monitoring_round.MonitoringRoundTests.test_failed_previous_round_remains_queryable_and_retriable_after_new_round_starts`。實作前以 `AttributeError: 'RoundCoordinator' object has no attribute 'unsaved_rounds'` 失敗，確認前輪無公開追蹤入口；實作後此案例通過。
- 聚焦驗收：`python3 scripts/run_tests.py test_monitoring_round test_log_solution_ui`，77 tests 通過，17.010 秒；包含真正 Tk 跨輪重試及目前輪畫面隔離。
- 完整套件：`python3 scripts/run_tests.py`，218 tests 通過，33.746 秒。於可存取桌面圖形工作階段執行，Tk 案例實際執行，不以待驗代替通過。
- 語法編譯：`python3 -m py_compile src/monitoring_round.py src/b518_log_solution.py tests/test_monitoring_round.py tests/test_log_solution_ui.py`，通過。
- 差異格式：`git diff --check 438dd951b6404c5a3f0a900ce08e4285066dd8ea...HEAD`，通過。
- 型別檢查設定查找：`rg --files -g 'mypy.ini' -g '.mypy.ini' -g 'pyrightconfig.json' -g 'pyproject.toml' -g 'setup.cfg' -g 'tox.ini' -g 'Makefile' -g 'Pipfile'`，沒有找到型別檢查器設定；未宣稱型別檢查通過。語法編譯僅代表 Python 語法有效。

程式只在 coordinator 存活期間追蹤該次執行建立的輪次，未從 Session 根目錄載入或掃描歷史資料。UI 僅透過 coordinator 公開入口讀取各輪摘要及指定重試，不接觸 store、queue 或 worker thread。

## 審查、提交與整合

Standards／Spec 雙軸 code review 尚待固定基準 `438dd951b6404c5a3f0a900ce08e4285066dd8ea` 審查完成後更新本節與 Ticket 核取狀態。完成審查後若修改程式，將重跑受影響測試；合併前另確認主線工作樹乾淨並重新納入兩個遠端最新主線提交。

目前實作提交 `abc5a8b152d56e7daf4ae60d1fee9049aae66fbe` 已推送至 origin 的 Gitea 與 GitHub 兩個 push URL；`git push -u origin round/ticket-03` 已建立 upstream。Ticket 文件、驗收紀錄及摘要提交將另行驗證後提交／推送。未執行合併或分支刪除。
