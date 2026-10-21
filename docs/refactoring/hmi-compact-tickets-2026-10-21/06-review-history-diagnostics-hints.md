# HC6：待確認、歷史與診斷的白話雙語提示

## Parent

https://github.com/Bowei1121/B518_205_207_ATE/issues/105

## What to build

操作員在待確認、歷史查詢及診斷視窗查看按鈕時，可理解操作及不能按的原因，切語言後仍保有目前的閱讀與操作內容。

父規格使用情境：35, 36, 37, 38, 39, 40, 44。驗收情境：T16, T17, T19。

## Acceptance criteria

- [x] 清點待確認、歷史查詢、診斷及其現有子視窗按鈕，交付提示／停用原因覆蓋清單與等義繁中英文文案。
- [x] 維持既有來源證據、結果裁決、查詢、分頁、重試與紀錄語意；白話提示不誤導為自動採用、強制交付或刪除證據。
- [x] 滑鼠停留、鍵盤焦點及停用原因提示皆可查看，不因查看觸發動作或修改資料；沿用既有共用提示生命週期。
- [x] 切換語言原地更新提示，沿用保留草稿、固定查詢結果、選取及閱讀位置的既有刷新流程。
- [x] 提示沿用既有位置與生命週期，關窗時清除提示與接收器，不留下失效回呼。
- [ ] 沿用各視窗既有真 App 驗收，涵蓋可用／停用、中英文及關窗；本票與 HC5 分工按使用情境，不另建第二套提示機制。

## Blocked by

None (can start immediately)

## HC6 提示覆蓋與文案

沿用 `_LocalizedControlHint`，不建立第二套提示元件。以下提示可由滑鼠停留或鍵盤焦點查看；狀態變動及切換語言時使用目前狀態重新整理。查看提示不執行按鈕命令。

| 視窗／控制項 | 狀態 | English | 繁體中文 |
| --- | --- | --- | --- |
| 待確認：保留原結果 | 可用 | Record that you are keeping the original result for this item. Other items awaiting review still need a decision. | 記錄你選擇保留這筆原結果；其他待確認項目仍需逐項決定。 |
| 待確認：選擇新候選 | 可用 | Record that you are choosing the new candidate for this item. Other items awaiting review still need a decision. | 記錄你選擇這筆新候選作為結果；其他待確認項目仍需逐項決定。 |
| 待確認：保留／選擇結果 | 未選取項目 | Select an item awaiting review before choosing a result. | 請先選取待確認項目，再選擇結果。 |
| 待確認：關閉 | 可用 | Close this window without deciding any result or removing an item awaiting review. | 關閉視窗，不會替你決定結果或移除待確認項目。 |
| 整輪警報：確認警報 | 可用 | Confirm that you have reviewed this round alarm. Result conflicts still need separate decisions. | 確認你已查看此輪警報；結果衝突仍須另外決定。 |
| 整輪警報：確認警報 | 沒有警報 | There is no round alarm to confirm. | 目前沒有需要確認的整輪警報。 |
| 整輪警報：確認警報 | 已確認 | This round alarm has already been confirmed. | 此輪警報已確認。 |
| 整輪警報：確認警報 | 來源準備中 | Source preparation is still in progress; wait until it finishes before confirming the alarm. | 來源仍在準備中；請等準備完成後再確認警報。 |
| 整輪警報：關閉 | 可用 | Close this window without confirming the alarm. | 關閉視窗，不會確認警報。 |
| 歷史查詢：搜尋 | 可用 | Search for events in the selected date range. This result stays fixed for this search; saved records are not changed. | 查詢所選日期範圍的事件；這次查詢的結果會固定保留，不會修改已保存的紀錄。 |
| 歷史查詢：上一頁／下一頁 | 可用 | Show the previous page of results. / Show the next page of results. | 顯示上一頁結果。／顯示下一頁結果。 |
| 歷史查詢：上一頁／下一頁 | 已在頁界或無結果 | There is no earlier page of results to show. / There is no later page of results to show. | 目前沒有更前一頁的結果可顯示。／目前沒有下一頁的結果可顯示。 |
| 歷史查詢：取消 | 查詢中 | Cancel the search in progress; results already shown remain available. | 取消目前的查詢；已顯示的結果仍可查看。 |
| 歷史查詢：取消 | 閒置 | There is no search in progress to cancel. | 目前沒有進行中的查詢可取消。 |
| 歷史查詢：重試未完成頁面 | 可重試 | Try loading the remaining pages for this search again; saved records are not changed. | 重新載入這次查詢尚未完成的頁面；不會修改已保存的紀錄。 |
| 歷史查詢：重試未完成頁面 | 無可重試頁面 | No history pages are currently available to retry. | 目前沒有可重試的歷史頁面。 |
| 歷史查詢：重試未完成頁面 | 載入中 | Pages are still loading; wait for this search to finish. | 頁面仍在載入，請等這次查詢完成。 |
| 歷史查詢：事件／異常清單 | 可用 | Select an event to see its original details and diagnostic information. / Select a source or date warning to see the original event and what went wrong. | 選取事件，查看原始內容及診斷資訊。／選取來源或日期異常項目，查看原始事件及發生問題的說明。 |
| App 診斷：重試保存 | 有未保存紀錄 | Try saving App troubleshooting records that did not save. | 重新嘗試保存尚未存好的 App 問題紀錄。 |
| App 診斷：重試保存 | 保存中 | App troubleshooting records are still being saved; wait for them to finish. | App 問題紀錄仍在保存，請等它完成。 |
| App 診斷：重試保存 | 無待重試紀錄 | There are no App troubleshooting records waiting to be saved again. | 目前沒有尚未存好的 App 問題紀錄。 |
| App 診斷：重試語言更新 | 有更新失敗 | Try applying the current language again after a text update failed. | 介面文字更新失敗時，可重新套用目前語言。 |
| App 診斷：重試語言更新 | App 關閉中 | The App is closing, so text updates cannot be retried. | App 正在關閉，暫時無法重試更新介面文字。 |
| App 診斷：重試語言更新 | 無待重試錯誤 | There are no text update failures to retry. | 目前沒有介面文字更新錯誤需要重試。 |
| App 診斷：關閉 | 可用 | Close this window without changing or deleting saved diagnostic records. | 關閉此視窗不會修改或刪除已保存的診斷紀錄。 |

HC5 負責主頁、設定、通知／恢復入口及其操作；HC6 負責上述待確認子視窗、歷史查詢及 App 診斷視窗，不重複新增主頁提示。歷史清單切語言時沿用現有固定查詢結果、草稿日期、選取、詳細內容與閱讀位置；診斷清單只重繪已載入的診斷快照。關窗時沿用各自的提示與語言接收器生命週期清理。

真 Tk 驗收入口：`test_real_tk_close_keeps_conflict_and_alarm_actions_available`、`test_real_tk_history_and_diagnostics_controls_explain_current_actions`、`test_real_tk_history_language_refresh_preserves_draft_snapshot_page_and_detail`、`test_app_diagnostics_scroll_position_survives_language_refresh`。其中實體停留、可用／停用、中英文、資料不變與關窗生命週期分別依測試內操作驗證；無真 App 桌面時須將這些測試明確標示為未執行。
