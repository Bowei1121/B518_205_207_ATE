# HC5：按鈕提示與停用原因覆蓋

範圍是主畫面、設定、通知與恢復中心，以及這些畫面已存在的子視窗按鈕。畫面標籤維持原樣，調整提示文案、浮動提示位置與提示驗收。繁中與 English 文字由 `src/language_catalog.py` 提供；下表列出目前每個操作入口使用的資源 key，方便逐項比對。

## 覆蓋清單

| 畫面／視窗 | 按鈕或入口 | English／繁中提示 key | 停用原因 |
| --- | --- | --- | --- |
| 主畫面工具列 | 設定、待確認、通知鈴鐺、語言 | `main.hint.settings`, `main.hint.review_count[.none]`, `main.hint.round_alarm`, `main.hint.language` | 待確認與鈴鐺入口在無事項時仍可開啟；提示會說明查看不會裁決或處理事項 |
| 主畫面操作 | 開始監控、停止、重試保存、診斷 | `main.hint.start[.active/.closing/.start_failure/.cancellation_pending]`, `main.hint.stop[.idle/.closing]`, `main.hint.retry_save[.none/.saving/.closing]`, `main.hint.diagnostics` | 開始停用時指出先解除啟動異常或先取消待處理輪次；其他動態狀態也會說明原因；無保存失敗時仍可查看提示 |
| 設定／工程師配置 | 瀏覽來源資料夾、載入、驗證、套用保存、匯入、匯出、重新載入、取消草稿 | `app.settings.hint.profile.*` | 按鈕皆有提示；說明草稿、目前輪次與後續輪次的差異 |
| 設定／事件與 Session | 開啟 Session 紀錄、歷史事件 | `app.settings.hint.session.open`, `app.settings.hint.history.open` | 按鈕皆有提示；說明只開啟資料，不改變紀錄 |
| 設定／保存期限 | 保存期限、重試背景清理 | `app.settings.hint.retention.save`, `app.settings.hint.retention.cleanup.retry` | 重試按鈕說明會移除已過保存期限的紀錄 |
| 歷史事件視窗 | 查詢、上一頁、下一頁、取消查詢、重試未完成頁面、事件清單 | `app.settings.history.*_hint`、`_historical_previous_hint`、`_historical_next_hint`、`_historical_cancel_hint`、`_historical_retry_hint` | 無前頁／後頁、查詢閒置／執行中、無未完成頁及載入中都有動態原因 |
| 通知與恢復／整輪警報 | 確認警報 | `recovery.hint.acknowledge` | 未選警報、準備中、已確認、關閉保存期間均說明原因 |
| 通知與恢復／保存與長期保存 | 重試保存、重試封存 | `recovery.hint.retry_save`, `recovery.hint.retry_archive` | 未選保存失敗輪次、所選輪次未失敗、沒有待重試的長期保存項目、關閉保存期間均說明原因 |
| 通知與恢復／啟動異常與輪次取消（HC1 搬入） | 確認並解除開始限制、取消本輪並保留紀錄 | `recovery.hint.reset_start_failure`, `recovery.hint.cancel_unverified_round` | 未選啟動異常／待取消輪次、關閉保存期間均說明原因 |
| 結果衝突視窗 | 保留原結果、採用新候選、關閉 | `conflict.hint.keep_original`, `conflict.hint.accept_candidate`, `conflict.hint.close` | 未選衝突時說明需先選取項目 |
| 警報子視窗 | 確認警報、關閉 | `alarm.hint.acknowledge`, `alarm.hint.close` | 沒有警報、準備尚未完成、警報已確認均說明原因 |
| 診斷視窗 | 重試保存診斷、重試語言更新、關閉 | `app.diagnostic.retry_hint.*`, `app.diagnostic.language_retry_hint.*`, `app.diagnostic.close_hint` | 沒有待重試錯誤、正在保存、App 正在關閉均說明原因 |
| 關閉前保存視窗 | 重試保存、取消關閉 | `app.close.hint.retry`, `app.close.hint.cancel` | 正在保存、尚無失敗、已完成、關閉已取消均說明原因 |
| 一般通知視窗 | 確認並關閉 | `app.notice.hint.dismiss` | 無停用狀態；說明此操作不改變監控結果 |

設定視窗共有 14 個帶提示控制項；路徑瀏覽按鈕共用同一組文案。所有上述提示同時提供繁中與 English。鍵盤焦點與滑鼠停留共用同一提示；提示顯示不執行按鈕命令。已開視窗切換語言會刷新可見提示，離開焦點／滑鼠或關窗會清除提示與其回呼。

## 重要操作文案

| 動作 | English | 繁體中文 |
| --- | --- | --- |
| 開始監控 | Start Log monitoring for the selected project and station. This does not start the ATE; wait for Log readiness before starting the test. | 依所選專案與機型開始監控 Log。這不會啟動 ATE；請等 Log 顯示就緒後再啟動測試。 |
| 停止監控 | Stop collecting results for this monitoring round. Unfinished positions are recorded as stopped and the round record is kept; this does not cancel or delete the round. | 停止收集本輪結果；未完成位置會記為已停止，輪次紀錄會保留；這不會取消輪次或刪除紀錄。 |
| 解除啟動異常 | After fixing the startup issue, confirm it to allow a new manual start. This does not retry monitoring or start the ATE. | 排除啟動問題後確認，即可解除限制並由人員手動重新開始；不會重試監控或啟動 ATE。 |
| 取消本輪 | Review the round, then confirm cancellation. This withdraws delivery but keeps its results and handling record; it does not delete records or mark products as failed. | 核對本輪後再確認取消。取消會撤回本輪結果交付，但保留結果與處置紀錄；不會刪除紀錄或把產品判為失敗。 |
| 開始按鈕停用（啟動異常） | A startup failure must be cleared in Notifications and Recovery before starting again. | 請先到「通知與恢復中心」解除啟動異常，才能再次開始。 |
| 開始按鈕停用（待取消輪次） | A round is awaiting cancellation; confirm its cancellation in Notifications and Recovery before starting another round. | 本輪待取消；請先到「通知與恢復中心」確認取消，才能開始下一輪。 |
| 重試長期保存 | Retry putting fully saved round records into long-term storage. Only records that need another attempt are included. | 重試將已完整保存的輪次紀錄放入長期保存區；只處理需要再次嘗試的紀錄。 |

啟動異常與輪次取消在尚未選取對應事項時，提示會先解釋操作，再補充停用原因，例如：

- **English:** “After fixing the startup issue, confirm it to allow a new manual start. This does not retry monitoring or start the ATE. Select a startup failure before confirming it.”
- **繁中：**「排除啟動問題後確認，即可解除限制並由人員手動重新開始；不會重試監控或啟動 ATE。請選取啟動異常，才能使用此操作。」
- **English:** “Review the round, then confirm cancellation. This withdraws delivery but keeps its results and handling record; it does not delete records or mark products as failed. Select a round awaiting cancellation to enable this action.”
- **繁中：**「核對本輪後再確認取消。取消會撤回本輪結果交付，但保留結果與處置紀錄；不會刪除紀錄或把產品判為失敗。請選取待取消輪次，才能使用此操作。」

真 App 驗收 `test_real_tk_start_and_cancel_hints_cover_recovery_states` 建立啟動異常及待取消輪次，以原生 CGEvent 滑鼠驗證停用開始與可用取消提示，並以原生 Tab 驗證停用控制項略過、可用取消控制項焦點提示。案例也檢查雙語即時刷新、離開／關窗清除、提示不觸發操作，以及提示與計時、結果、必要按鈕邊界不重疊。

先前受限執行的 exit 134 與缺 Quartz 為歷史結果；本輪使用桌面執行權限與臨時 PyObjC 環境，已完成四個原生 UI 案例並產生影像。[本輪驗證與影像索引](validation.md)記錄執行方式、結果與覆蓋範圍。
