# ST6 歷史查詢與診斷提示驗收

日期：2026-10-16。環境：macOS、Python 3.8、系統 Aqua/Tk、真實 B518 Tk App。

## 交付行為

- 歷史查詢搜尋、上／下一頁、取消、後續頁重試、事件／來源日期診斷清單皆有繁中與英文提示。提示會依查詢是否執行、頁界、續頁整理及目前資料狀態更新；Search 說明固定結果與不修改保存記錄的效果。
- App 診斷的保存重試、文字重試及關閉均有雙語提示；保存與文字重試會依保存失敗、保存中、文字更新失敗及 App 關閉狀態顯示可用原因。短按鈕標籤與查詢／保存操作維持原樣。
- 提示不執行按鈕命令、不取得鍵盤焦點、不改變輸入、查詢 generation、已選事件或閱讀位置。切語言會更新可見提示；視窗關閉會清理提示及語言接收器。
- 沒有修改歷史查詢、索引、輪次資料、App 診斷資料或其保存政策。

## 真實 App 操作與證據

新擷取的真 Tk 視窗 PNG 以 `st6-` 開頭。`st6-history-cancel-disabled-hint-en.png` 是實際系統滑鼠停在停用「Cancel search」按鈕後的英文提示；實際螢幕座標為 `(295, 796)`。同一實體滑鼠驗收未按下按鈕，未啟動或取消查詢。`st6-history-cancel-active-hint-zh-TW.png` 顯示查詢進行中之中文取消說明；此提示期間 query generation 保持不變。`st6-history-cancel-disabled-hint-zh-TW.png` 展示同一停用原因的中文文字。

`st6-history-retry-disabled-hint-zh-TW.png` 顯示沒有未完成頁面時的續頁停用原因。`st6-diagnostics-save-retry-disabled-hint-en.png` 與 `st6-diagnostics-save-retry-disabled-hint-zh-TW.png` 顯示 App 診斷保存重試在完整保存時停用的雙語原因；`st6-diagnostics-close-hint-zh-TW.png` 顯示關閉不會修改或移除已保存診斷的說明。截圖均在真正 Tk App 視窗取得，畫面沒有系統權限對話框遮擋。

`window-bounds.json` 由同次真 Tk 歷史資料／詳細內容語言保留測試產生，記錄中英歷史與 App 診斷視窗、控制項的實際桌面幾何及來源 SHA-256，供 ST8 比對版面與資料不變性。

停用 Cancel search 已由實體滑鼠驗證；其餘提示畫面由真 Tk 視窗操作／事件測試擷取，沒有逐一以實體滑鼠移入每個控制。測試視窗內的日期及診斷記錄為臨時資料。

## 測試結果

`test_log_solution_ui` 中的 12 個受影響案例及 `test_language_catalog` 的 8 個案例全部通過，合計 **20 tests，113.215s，OK**。其後增加續頁失敗時啟用提示斷言，單獨重跑該真 Tk 案例亦通過（2.067s）。Python 3.8 `py_compile` 及 `git diff --check` 通過。真 Tk 案例包含：

- 歷史查詢最新請求、取消與關窗生命週期；查詢取消、分頁、已快取頁、後續頁重試與固定結果。
- 暫停後續批次時先閱讀首五頁；後續準備失敗仍保留首批結果；未知日期診斷、不可讀來源及診斷分頁。
- 歷史控制鍵盤巡覽及翻頁、搜尋／取消／續頁停用原因、查詢中取消提示、語言切換後提示更新與關窗清理。
- 切換語言時保留日期草稿、固定結果、所選事件、原始詳細內容及閱讀位置；App 診斷清單捲動位置維持。

未重跑數小時大量歷史效能測試。工廠桌面與 KVM 實機仍由 ST8 另列。
