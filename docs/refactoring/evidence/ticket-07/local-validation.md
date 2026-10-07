# Ticket 07 本機實作與驗收紀錄

狀態：Ticket 07 實作與驗收完成；25 項清理聚焦測試、274 項含真正 Tk 的完整套件、Standards／Spec 固定基準複審均通過。提交／推送與安全整合尚待完成，因此尚不刪除分支。固定主線起點為 `56f895af0b5bceab73582ab8fec95417068b468e`。Ticket 分支 `round/ticket-07` 在本票開始前已有提交 `495e8aaf84ce1af50bbcfd9bace793f955c67b22`（父提交為上述主線 SHA，含 2026-10-07 multilingual 文件草稿，已同步遠端）。該既存提交未改寫；固定審查基準為 `495e8aaf84ce1af50bbcfd9bace793f955c67b22`，Standards／Spec 審查範圍是其後的 Ticket 07 變更。分支含該既存提交，整合時須避免將無關文件混入 Ticket 07 主線提交。

## 實作內容

- 新增 `src/round_retention.py`，以可信 `round-archive.json`、帶時區封存時間、整輪組件 SHA-256／大小、App 管理根目錄及 Coordinator 保護狀態判定清理資格。只刪可信清單內的輪次檔案；未知組件、損壞、缺少封存、符號連結、外部參照及本次執行受保護輪次跳過。
- Coordinator 公開啟動、每 24 小時、有效設定變更後排程、請求、查詢摘要及關閉協調入口。工作在背景執行，多個執行中觸發合併成一次後續工作；關閉保存期間不開始新工作，並等待已進行工作安全結束。
- 以原子寫入持久保存執行摘要及每輪刪除意圖／進度；摘要寫入失敗會中止刪除並顯示錯誤，部分刪除後可由新 Coordinator 依持久計畫續作。復原時若出現計畫外新檔、符號連結、越界或不符原始檔案摘要的內容，保留進度並停止該輪刪除。
- 每次暫置改名之前先持久記錄穩定 stage 名稱與步驟；程序在改名前、改名後及刪除前中斷均可依檔案雜湊和持久進度安全復原。若期間期限延長，先還原尚未刪除的暫置檔，再按新期限跳過；無法確認的檔案組合保留並回報。Stage／原檔開啟失敗時關閉檔案與目錄描述符。
- 設定畫面顯示背景清理狀態及最近摘要、刪除／保留／失敗數與原因；設定保存成功後才通知 Coordinator 使用新期限。

## 已執行驗證

執行目錄：`B518 Log Solution/`（repository 內實際 Python 程式及測試目錄）。

- `python3 scripts/run_tests.py test_round_retention`：25 項通過。隔離暫存磁碟及全新 Coordinator 涵蓋期限前／恰到／逾期、startup／24 小時排程、期限縮短／延長、目前輪次保護、同輪多目錄、未知檔、損壞資料與外部 symlink、清理摘要故障防刪、多目錄部分刪除續作、單輪失敗不阻擋其他輪次、觸發合併與關閉競爭。另以 Event 故障注入涵蓋 stage 意圖寫入後但 rename 前、rename 後、期限延長後復原、摘要重讀與 FD 關閉。刪除後用新 Coordinator 從 ledger 讀回摘要。
- `B518_TK_TESTS=1 python3 scripts/run_tests.py`：274 項完整套件通過（42.825 秒），於可存取桌面圖形工作階段執行。真正 Tk 操作設定輸入與保存、驗證失敗／持久化失敗、保存天數變更觸發背景清理、檢視啟動清理摘要；以暫存輪次確認刪除及未刪檔案內容，外部來源 Log／人工匯出保持不變，Tk `after` 心跳持續更新。
- `B518_TK_TESTS=1 python3 scripts/run_tests.py test_log_solution_ui.LogSolutionUiTests.test_real_tk_shows_startup_cleanup_summary_after_disk_deletion`：獨立桌面 Tk 清理操作與摘要案例通過。測試等到公開清理狀態完成後才核對磁碟及顯示內容。
- 曾在未提升桌面存取的執行環境遇到 Tk 初始化 fatal abort（exit 134）；後續已在可存取桌面的工作階段執行以上真正 Tk 測試並通過。先前 abort 不作為通過證據。
- 環境：macOS Darwin 24.6.0、Intel x86_64、Python 3.8.10、Tk 8.6。
- 最新聚焦測試後 `python3 -m compileall -q src tests` 與 `git diff --check` 均通過。
- Repository 未配置 mypy、pyright 或其他型別檢查器／命令；未宣稱型別檢查通過。`compileall` 只檢查 Python 語法。
- `python3 -m compileall -q src tests` 與 `git diff --check`：最終程式／測試版本通過。
- Repository 未配置 mypy、pyright 或其他型別檢查器／命令；未宣稱型別檢查通過。`compileall` 只檢查語法。
- 固定基準 `495e8aaf84ce1af50bbcfd9bace793f955c67b22` 的 Standards／Spec 雙軸審查完成，最終複審沒有未解問題。審查曾指出期限延長與 stage 中斷復原、rename 交易冪等性、摘要重複計數及檔案／目錄 FD 洩漏；均已修正，受影響聚焦測試及完整桌面套件重跑通過。

## 規格覆蓋狀態

| 母規格必要案例 | Ticket 07 證據 | 狀態 |
| --- | --- | --- |
| 保存期限前、恰到期及新期限套用（9） | 注入時鐘及磁碟封存檔；期限邊界、縮短／延長及每日排程測試 | 通過 |
| 活躍／待確認／未保存／未知及損壞資料保留（10） | Coordinator 保護中輪次、缺少／損壞封存、未知檔與 symlink 測試；Ticket 05 驗證準備中及待確認不可封存 | 通過；現場部署狀態不在本票驗收範圍 |
| 同輪 audit／Session 分散多目錄（11） | 真實暫存磁碟跨目錄聚合、完整性驗證及整輪刪除／部分失敗續作 | 通過 |
| 配置、偏好、匯出、來源 Log、外部 symlink 保護（12） | 真 Tk 操作前後檔案比對、App 管理範圍驗證及外部 symlink 替換測試 | 通過 |
| 啟動／每日／設定觸發、合併及關閉協調（13） | 注入時鐘、成功設定變更、Event 觸發合併、關閉競爭及 Tk `after` 心跳 | 通過；Tk 真實 UI 案例驗證設定及摘要操作 |
| 清理失敗、部分刪除復原及持久進度（14） | ledger 寫入故障、單輪失敗隔離、多目錄部分刪除、新 Coordinator 復原、stage crash／期限延長及競爭測試 | 通過 |
| 刪除後摘要可查、摘要失敗可見（15） | 刪除後由新 Coordinator 讀取 ledger；摘要寫入故障證明不虛報刪除；真 Tk 顯示摘要 | 通過 |
| 新舊格式讀取與非到期資料相容（16） | 舊格式讀取由 Ticket 05／既有 reader 測試覆蓋；本票未到期／受保護資料保留及完整回歸 | 通過；受控測試不代表現場設備驗收 |

受控測試沒有執行正式設備或現場驗收。產品結果放行與 KVM 契約由本票未改動，274 項完整測試通過；不能代替現場設備驗收。最終程式 commit SHA 與推送狀態於提交後補記。

## 整合待辦

驗收及固定基準雙軸審查均已完成。提交本地驗收證據後，即時 fetch 並確認 `B518-Log-Solution`、Gitea／GitHub push 目的地與工作樹狀態；既存提交 `495e8aa` 是票前 multilingual 文件草稿，整合時須明確避免混入無關文件內容。只有確認主線乾淨且遠端基準一致、合併後驗證及所有 push 目的地同步成功，才清理專用分支。最終程式 commit SHA、整合 SHA 及分支清理結果待執行後補記。
