# HC6 驗收紀錄

產品程式與截圖來源：`04dffe9c8e0e633db7abe489cbd79cff689ccafb`。基準：`1af60cfa4991cf5af146df9c1cbbefed8965278c`。後續僅同步人工 hover 分支的一處中文預期及提交本份證據，產品程式未再變動。

## 環境與結果

Intel x86_64、macOS 15.8.1 (24H32)、`/opt/anaconda3/bin/python` 3.11.7、Tk 8.6、AppKit／Quartz、桌面 1440×900 points。執行需允許連接 macOS WindowServer；先前 sandbox 內的 AppKit exit 134 已透過 sandbox 外執行排除，不再列為桌面驗收阻擋。

| 執行 | 結果 | 證據 |
| --- | --- | --- |
| `B518_TK_TESTS=1` + `B518_TK_EVIDENCE_DIR`，六項審查指定案例、刷新期間關閉回歸、未完成頁重試提示 | 8/8 通過，0 skipped，71.117 秒 | [完整 log](review-r4/ui-8-tests.log) |
| 標準全套（未開啟桌面 opt-in） | 582 項，5 failures、1 error、78 skipped，501.052 秒；非全綠 | [完整 log](review-r4/full-suite.log) |
| 全套中的 `test_language_catalog`、`test_historical_event_display`、`test_historical_event_query` | 85/85 通過，0 skipped | 同上 |
| 修改檔案語法、`git diff --check` | 通過 | 提交前執行 |

標準模式會跳過要求 `B518_TK_TESTS=1`、容量 fixture、外部系統或人工外觀切換的案例；上表八項已用獨立證據模式實跑。未進行 M4／arm64 或 JetKVM 驗收；`B518_MANUAL_HOVER=1` 的真人操作分支未執行，其中文預期已與實際 catalog 核對。

## 審查問題與圖片核對

- S2：恢復從目標原生主視窗取得 `bounds`。`native_bounds` 是主視窗座標；`image_pixels` 是合成影像尺寸，兩者可能因 tooltip 超出視窗而不同。八項證據模式均已執行 helper 返回路徑，沒有 NameError。
- R3：同步鍵盤分頁、hover 搜尋及未完成頁重試的舊英文斷言；保留查詢、鍵盤作用範圍、原始資料不變與關窗斷言。
- R4／R2：WindowServer 視窗陣列依前到後排列為 `[tooltip, app]`，避免主視窗蓋過 tooltip。截圖前確認提示對象，將目標視窗移至前景，並在移開滑鼠的操作測試後重新 hover 再拍。
- 實跑另發現提示刷新處理 Tk layout 事件時，提示可能已關閉。刷新保留當次視窗參照，讓既有 TclError 清理生效；新增真 Tk 回歸測試驗證期間關閉不拋錯、不重現提示。
- 兩個 205 筆 UI fixture 的磁碟準備在本機接近預設 10 秒上限（同樣 fixture 實測 9.98 秒、沒有保存錯誤）；僅把這兩處測試資料等待改為 60 秒，產品 flush 預設及 UI 行為斷言未改。

已逐張檢查 22 張原始 PNG（[檔名與 SHA-256 清單](review-r4/manifest.json)），提示文字、對應控制項與完整可讀性均已核對。原圖依 `.gitignore` 保留在本機 `/Users/tsengbowei/Documents/B518 ATE 205-207/tmp/reviews/pr115-04dffe9/screenshots/`；文字 log 與 manifest 已提交。PNG 直接由 WindowServer 指定 App／tooltip 原生視窗合成，沒有後製；它排除其他 App 視窗，不能用來推論整個桌面沒有外部遮擋。

| 必查對象 | English | 繁體中文 |
| --- | --- | --- |
| 歷史取消停用提示 | `st6-history-cancel-disabled-hint-en.png` | `st6-history-cancel-disabled-hint-zh-TW.png` |
| 整輪警報關閉提示 | `st5-round-alarm-close-hint-en.png` | `st5-round-alarm-close-hint-zh-TW.png` |
| 待確認關閉提示 | `st5-conflict-close-hint-en.png` | `st5-conflict-close-hint-zh-TW.png` |
| App 診斷保存重試停用 | `st6-diagnostics-save-retry-disabled-hint-en.png` | `st6-diagnostics-save-retry-disabled-hint-zh-TW.png` |

## 全套失敗與早期嘗試

全套失敗為歷史容量 worker 回收、快捷鍵保存等待、平台啟動時背景事件變化、準備逾時取消完成原因、分離輪次保存驗證，以及 retention 完成等待。詳細 traceback 保留在全套 log；另以 `6e605b5` 的獨立程式快照及本版隔離比對，[前版六項全過](review-r4/baseline-6-tests.log)；[本版隔離執行五項通過、一項容量回收錯誤](review-r4/current-6-tests.log)。該容量案例改用獨立 `TMPDIR` 後 [1/1 通過](review-r4/capacity-isolated-temp.log)。容量測試會比較系統暫存目錄中全域 snapshot 檔案集合，這個結果符合共享暫存干擾的可能性；尚未證明完整因果，沒有修改容量／查詢程式，也不把全套結果標為通過。

[早期失敗 log](review-r4/attempts/) 保留刷新關閉例外、滑鼠目標視窗遮擋與 fixture 保存逾時的診斷過程，不能當成通過結果。有效的八項執行紀錄為 `ui-8-tests.log`。圖片、log 與程式來源 SHA-256 在 [manifest.json](review-r4/manifest.json)。
