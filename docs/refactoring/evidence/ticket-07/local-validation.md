# Ticket 07 本機實作與驗收紀錄

狀態：實作、聚焦測試、完整套件及真正 Tk 驗收通過；**Standards／Spec 審查與整合尚未完成，不可合併或清理分支**。固定主線起點為 `56f895af0b5bceab73582ab8fec95417068b468e`。Ticket 分支 `round/ticket-07` 在本票開始前已有提交 `495e8aaf84ce1af50bbcfd9bace793f955c67b22`（父提交為上述主線 SHA，含 2026-10-07 multilingual 文件草稿，已同步遠端）。該既存提交未改寫；本票審查基準固定為 `495e8aaf84ce1af50bbcfd9bace793f955c67b22`，審查範圍是其後的 Ticket 07 變更。分支含該既存提交，因此任何主線整合都必須先確認如何處理其無關文件內容。

## 實作內容

- 新增 `src/round_retention.py`，以可信 `round-archive.json`、帶時區封存時間、整輪組件 SHA-256／大小、App 管理根目錄及 Coordinator 保護狀態判定清理資格。只刪可信清單內的輪次檔案；未知組件、損壞、缺少封存、符號連結、外部參照及本次執行受保護輪次跳過。
- Coordinator 公開啟動、每 24 小時、有效設定變更後排程、請求、查詢摘要及關閉協調入口。工作在背景執行，多個執行中觸發合併成一次後續工作；關閉保存期間不開始新工作，並等待已進行工作安全結束。
- 以原子寫入持久保存執行摘要及每輪刪除意圖／進度；摘要寫入失敗會中止刪除並顯示錯誤，部分刪除後可由新 Coordinator 依持久計畫續作。復原時若出現計畫外新檔、符號連結、越界或不符原始檔案摘要的內容，保留進度並停止該輪刪除。
- 設定畫面顯示背景清理狀態及最近摘要、刪除／保留／失敗數與原因；設定保存成功後才通知 Coordinator 使用新期限。

## 已執行驗證

執行目錄：`B518 Log Solution/`（repository 內實際 Python 程式及測試目錄）。

- `python3 scripts/run_tests.py test_round_retention`：15 項通過。隔離暫存目錄、可信 archive 檔及新 Coordinator 涵蓋期限前／到期、startup／24 小時排程、設定修改、目前輪次保護、同輪多目錄、外部 symlink、摘要故障防刪、部分刪除後新 Coordinator 續作、單輪損壞不阻擋安全輪、復原時出現計畫外新檔即停止，以及清理／關閉競爭和觸發合併。刪除後用新 Coordinator 從 ledger 讀回摘要。
- `B518_TK_TESTS=1 python3 scripts/run_tests.py`：264 項完整套件通過（46.081 秒），在可存取桌面圖形工作階段執行。包含實際 Tk 設定從 365 改為 180 天、背景清理真實暫存輪次、重讀全域偏好、檢視清理摘要，並比對外部來源 Log／人工匯出內容未變。Tk 心跳持續更新。
- `B518_TK_TESTS=1 python3 scripts/run_tests.py test_log_solution_ui.LogSolutionUiTests.test_real_tk_shows_startup_cleanup_summary_after_disk_deletion`：獨立桌面 Tk 清理操作與摘要案例通過。測試等到公開清理狀態完成後才核對磁碟及顯示內容，避免讀到上一筆摘要。
- 曾在未提升桌面存取的執行環境遇到 Tk 初始化 fatal abort（exit 134）；後續已在可存取桌面的工作階段執行以上真正 Tk 測試並通過。先前 abort 不作為通過證據。
- 環境：macOS Darwin 24.6.0、Intel x86_64、Python 3.8.10、Tk 8.6。
- 最新聚焦測試後 `python3 -m compileall -q src tests` 與 `git diff --check` 均通過。
- Repository 未配置 mypy、pyright 或其他型別檢查器／命令；未宣稱型別檢查通過。`compileall` 只檢查 Python 語法。
- 固定基準 Standards／Spec `$code-review`、審查修正及必要複審：待執行。

## 規格覆蓋狀態

| 母規格必要案例 | Ticket 07 證據 | 狀態 |
| --- | --- | --- |
| 保存期限前、恰到期及新期限套用（9） | 注入時鐘、真實封存檔；設定改為 180 天及每日排程 | 聚焦證據通過，待複審 |
| 活躍／待確認／未保存／未知及損壞資料保留（10） | 本次執行保護、損壞 archive 與外部 symlink 跳過；Ticket 05 封存測試涵蓋準備中／待確認不得封存 | 部分；清理端完整保護矩陣待複審 |
| 同輪 audit／Session 分散多目錄（11） | audit 與 Session 置於不同資料夾，完整驗證及整輪移除 | 聚焦證據通過，待複審 |
| 配置、偏好、匯出、來源 Log、外部 symlink 保護（12） | 真 Tk 比對暫存偏好、人工匯出及來源 Log；symlink 外部目標未變 | 部分；完整正式資料佈局清單待複審 |
| 啟動／每日／設定觸發、合併及關閉協調（13） | 注入 monotonic clock、設定修改、Event 控制清理與關閉；真正 Tk 心跳持續 | 主要流程有證據；關閉競爭的完整 Tk 情境待複審 |
| 清理失敗、部分刪除復原及持久進度（14） | ledger 原子替換故障、部分刪除後新 Coordinator 續作、壞輪與安全輪並行、計畫外新檔使復原停止 | 聚焦證據通過，待複審 |
| 刪除後摘要可查、摘要失敗可見（15） | 新 Coordinator 讀取摘要；摘要寫入故障證明未刪資料 | 聚焦及 Tk 摘要證據通過，待複審 |
| 新舊格式讀取與非到期資料相容（16） | 既有 Ticket 05 舊資料測試及本票未到期案例；完整交互回歸待覆核 | 部分 |

受控測試沒有執行正式設備或現場驗收。產品結果放行與 KVM 契約由本票未改動，264 項完整測試通過；不能代替現場設備驗收。最終程式 commit SHA、雙軸審查結論與所有遠端同步狀態待完成後補記。

## 尚待完成

1. 依母規格逐項複核受保護資料矩陣、App 管理路徑所有權、競爭及部分刪除復原；修正缺口並重跑受影響測試。
2. 以固定基準 `495e8aaf84ce1af50bbcfd9bace793f955c67b22` 執行 Standards／Spec 雙軸審查、修正並複審。
3. 記錄最終程式 commit SHA、完整套件與文件檢查結果；repository 沒有型別檢查器設定，因此未宣稱型別檢查通過。
4. 合併前再次即時確認主線工作樹與所有 push 目的地；處理分支上既存 multilingual 文件提交如何避免混入 Ticket 07 無關內容。驗收及審查全通過前保留分支。
