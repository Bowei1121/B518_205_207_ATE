# Ticket 07 本機實作與驗收紀錄

狀態：Ticket 07 實作與驗收完成；25 項清理聚焦測試、274 項含真正 Tk 的完整套件、Standards／Spec 固定基準複審均通過。固定主線起點為 `56f895af0b5bceab73582ab8fec95417068b468e`。Ticket 分支 `round/ticket-07` 在本票開始前已有提交 `495e8aaf84ce1af50bbcfd9bace793f955c67b22`（父提交為上述主線 SHA，內容為 2026-10-07 多語言票草稿）。該既存提交未改寫；固定審查基準為 `495e8aaf84ce1af50bbcfd9bace793f955c67b22`，Standards／Spec 審查範圍是其後的 Ticket 07 變更。正常合併 commit 為 `3c07e1e371c8e7f0467c39e591ab84df591d9ad0`；合併樹僅納入 Ticket 07 交付，排除無關草稿檔案並移除其摘要段落。合併後 274 項含真正 Tk 的完整套件通過；主線及驗收文件已同步至 Gitea／GitHub；兩端遠端分支、本地分支及 stale tracking refs 均已安全清理。最終主線文件 commit 為 `e621daf9bd735171f68467a4f2d9a2541de6211b`。

## 實作內容

- 新增 `src/round_retention.py`，以可信 `round-archive.json`、帶時區封存時間、整輪組件 SHA-256／大小、App 管理根目錄及 Coordinator 保護狀態判定清理資格。只刪可信清單內的輪次檔案；未知組件、損壞、缺少封存、符號連結、外部參照及本次執行受保護輪次跳過。
- Coordinator 公開啟動、每 24 小時、有效設定變更後排程、請求、查詢摘要及關閉協調入口。工作在背景執行，多個執行中觸發合併成一次後續工作；關閉保存期間不開始新工作，並等待已進行工作安全結束。
- 以原子寫入持久保存執行摘要及每輪刪除意圖／進度；摘要寫入失敗會中止刪除並顯示錯誤，部分刪除後可由新 Coordinator 依持久計畫續作。復原時若出現計畫外新檔、符號連結、越界或不符原始檔案摘要的內容，保留進度並停止該輪刪除。
- 每次暫置改名之前先持久記錄穩定 stage 名稱與步驟；程序在改名前、改名後及刪除前中斷均可依檔案雜湊和持久進度安全復原。若期間期限延長，先還原尚未刪除的暫置檔，再按新期限跳過；無法確認的檔案組合保留並回報。Stage／原檔開啟失敗時關閉檔案與目錄描述符。
- 設定畫面顯示背景清理狀態及最近摘要、刪除／保留／失敗數與原因；設定保存成功後才通知 Coordinator 使用新期限。

## 已執行驗證

執行目錄：`B518 Log Solution/`（repository 內實際 Python 程式及測試目錄）。

- `python3 scripts/run_tests.py test_round_retention`：25 項通過。隔離暫存磁碟及全新 Coordinator 涵蓋期限前／恰到／逾期、startup／24 小時排程、期限縮短／延長、目前輪次保護、同輪多目錄、未知檔、損壞資料與外部 symlink、清理摘要故障防刪、多目錄部分刪除續作、單輪失敗不阻擋其他輪次、觸發合併與關閉競爭。另以 Event 故障注入涵蓋 stage 意圖寫入後但 rename 前、rename 後、期限延長後復原、摘要重讀與 FD 關閉。刪除後用新 Coordinator 從 ledger 讀回摘要。
- 合併後 `B518_TK_TESTS=1 python3 scripts/run_tests.py`：274 項完整套件通過（43.684 秒），於可存取桌面圖形工作階段執行。真正 Tk 操作設定輸入與保存、驗證失敗／持久化失敗、保存天數變更觸發背景清理、檢視啟動清理摘要；以暫存輪次確認刪除及未刪檔案內容，外部來源 Log／人工匯出保持不變，Tk `after` 心跳持續更新。
- `B518_TK_TESTS=1 python3 scripts/run_tests.py test_log_solution_ui.LogSolutionUiTests.test_real_tk_shows_startup_cleanup_summary_after_disk_deletion`：獨立桌面 Tk 清理操作與摘要案例通過。測試等到公開清理狀態完成後才核對磁碟及顯示內容。
- 曾在未提升桌面存取的執行環境遇到 Tk 初始化 fatal abort（exit 134）；後續已在可存取桌面的工作階段執行以上真正 Tk 測試並通過。先前 abort 不作為通過證據。
- 環境：macOS Darwin 24.6.0、Intel x86_64、Python 3.8.10、Tk 8.6。
- `python3 -m compileall -q src tests` 與 `git diff --check`：最終程式／測試版本通過。
- Repository 未配置 mypy、pyright 或其他型別檢查器／命令；未宣稱型別檢查通過。`compileall` 只檢查語法。
- 固定基準 `495e8aaf84ce1af50bbcfd9bace793f955c67b22` 的 Standards／Spec 雙軸審查完成，最終複審沒有未解問題。審查曾指出期限延長與 stage 中斷復原、rename 交易冪等性、摘要重複計數及檔案／目錄 FD 洩漏；均已修正，受影響聚焦測試及完整桌面套件重跑通過。

## 規格覆蓋狀態

| 母規格必要案例 | Ticket 07 證據 | 狀態 |
| --- | --- | --- |
| writer 空閒退出、重啟及 enqueue 競爭（1） | Ticket 01 的 writer 生命週期／競爭測試及本票 274 項完整回歸：[Ticket 01 驗收](../ticket-01/local-validation.md) | 回歸通過 |
| 停止讀檔後人工操作仍保存並可重建（2） | Ticket 01／02 真實磁碟重建與 Tk 操作測試：[Ticket 01 驗收](../ticket-01/local-validation.md)、[Ticket 02 驗收](../ticket-02/local-validation.md) | 回歸通過 |
| 寫入故障、部分寫入及有序重試（3） | Ticket 02 故障注入、磁碟重建及有序復原證據：[Ticket 02 驗收](../ticket-02/local-validation.md) | 回歸通過 |
| 前輪失敗換輪後仍追蹤，關閉等待並回收（4） | Ticket 03／04 跨輪追蹤、資源回收與關閉證據：[Ticket 03 驗收](../ticket-03/local-validation.md)、[Ticket 04 驗收](../ticket-04/local-validation.md) | 回歸通過 |
| UI 可回應、取消及重試（5） | Ticket 02／04 真 Tk 重試、取消、事件迴圈回應測試：[Ticket 02 驗收](../ticket-02/local-validation.md)、[Ticket 04 驗收](../ticket-04/local-validation.md) | 回歸通過 |
| 全部保存後才關閉；產品放行及 KVM 不變（6） | Ticket 04 關閉契約及 KVM 回歸測試：[Ticket 04 驗收](../ticket-04/local-validation.md) | 回歸通過 |
| 保存天數預設／持久化／提示（7） | Ticket 06 真 Tk 設定、磁碟重讀及 import/export 測試：[Ticket 06 驗收](../ticket-06/local-validation.md) | 回歸通過 |
| 待確認後以實際封存時間起算（8） | Ticket 05 注入時鐘、人工確認及可信封存證據：[Ticket 05 驗收](../ticket-05/local-validation.md) | 回歸通過 |
| 保存期限前、恰到期及新期限套用（9） | 注入時鐘及磁碟封存檔；期限邊界、縮短／延長及每日排程測試 | 通過 |
| 活躍／待確認／未保存／未知及損壞資料保留（10） | Coordinator 保護中輪次、缺少／損壞封存、未知檔與 symlink 測試；Ticket 05 驗證準備中及待確認不可封存 | 通過；現場部署狀態不在本票驗收範圍 |
| 同輪 audit／Session 分散多目錄（11） | 真實暫存磁碟跨目錄聚合、完整性驗證及整輪刪除／部分失敗續作 | 通過 |
| 配置、偏好、匯出、來源 Log、外部 symlink 保護（12） | 真 Tk 操作前後檔案比對、App 管理範圍驗證及外部 symlink 替換測試 | 通過 |
| 啟動／每日／設定觸發、合併及關閉協調（13） | 注入時鐘、成功設定變更、Event 觸發合併、關閉競爭及 Tk `after` 心跳 | 通過；Tk 真實 UI 案例驗證設定及摘要操作 |
| 清理失敗、部分刪除復原及持久進度（14） | ledger 寫入故障、單輪失敗隔離、多目錄部分刪除、新 Coordinator 復原、stage crash／期限延長及競爭測試 | 通過 |
| 刪除後摘要可查、摘要失敗可見（15） | 刪除後由新 Coordinator 讀取 ledger；摘要寫入故障證明不虛報刪除；真 Tk 顯示摘要 | 通過 |
| 新舊格式讀取與非到期資料相容（16） | 舊格式讀取由 Ticket 05／既有 reader 測試覆蓋；本票未到期／受保護資料保留及完整回歸 | 通過；受控測試不代表現場設備驗收 |

受控測試沒有執行正式設備或現場驗收。產品結果放行與 KVM 契約由本票未改動，274 項完整測試通過；不能代替現場設備驗收。最終程式／測試提交為 `1243450b957fb326c8941f63ba3f9f367c853a66`，已推送到 Gitea 與 GitHub 的 `round/ticket-07`；這份文件提交完成後更新文件同步狀態。

## 整合待辦

驗收及固定基準雙軸審查均已完成。合併前即時核對 Gitea、GitHub 的主線均為 `56f895af0b5bceab73582ab8fec95417068b468e`，專用分支均為 `fd746ed5071abfec6264e69170d6b4c566167f4c`。正常兩父提交合併 SHA `3c07e1e371c8e7f0467c39e591ab84df591d9ad0`，父提交為主線 `56f895af0b5bceab73582ab8fec95417068b468e` 與 Ticket 分支 `fd746ed5071abfec6264e69170d6b4c566167f4c`。合併樹排除票前十張多語言草稿檔案及其摘要段落，Ticket 分支歷史未改寫。合併後於可存取桌面的環境執行 `B518_TK_TESTS=1 python3 scripts/run_tests.py`，274 項通過（43.684 秒）。主線 commit `3c07e1e371c8e7f0467c39e591ab84df591d9ad0` 與驗收文件 commit `e621daf9bd735171f68467a4f2d9a2541de6211b` 均已推送至 origin 的 Gitea／GitHub push URL；`git ls-remote origin` 與 `git ls-remote github` 均確認主線為 `e621daf9bd735171f68467a4f2d9a2541de6211b`，`round/ticket-07` ref 不存在。之後以非強制方式刪除兩端遠端分支、本地分支，並 fetch prune 清除追蹤 refs。最終工作樹乾淨，位於 `B518-Log-Solution`。
