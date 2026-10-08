# 專案摘要 — 2026-10-09

## 前次討論與查證脈絡

延續 [2026-10-08 專案摘要](PROJECT_SUMMARY_2026-10-08.md)。前次完成 M1 真正 Tk 滑鼠／鍵盤驗收及合併；M2、M3 已納入 GitHub 主線並各自完成必要測試與雙軸審查。使用者已指定公司 Gitea 在週一同步；Gitea 未直接查證前，相關多語言票分支須保留。M4 不應把前票同步收尾混入本票。

## M4：無輪次 App 事件雙語保存（GitHub #17）

- 2026-10-08 開始 M4，實際 Git 根目錄為 `B518-Log-Solution`，Python 專案在其子目錄 `B518 Log Solution/`。以 Git ancestry 確認 M1、M2、M3 已在主線；M2 merge `f128d9f963f60d416d0eaf5917fa5eda87408280`、M3 merge `fb4ffb2286d9c113511482b738a101a11616bd14`，M3 文件整合主線 SHA `648b0c2126aaa6ab29016f2f95deb24ca7c8145f`。固定 M4 Standards／Spec review 基準為 `648b0c2126aaa6ab29016f2f95deb24ca7c8145f`。
- 建立 `Multilingual/ticket-04`；無既有同名票分支。起始 GitHub 主線 SHA 為 `648b0c2`。GitHub 遠端 `github` 可用；`origin` 的 Gitea 位址 `10.64.76.34:3000` 於 10/08 直接查詢連線拒絕，依使用者明示例外延至週一處理，不移除此 push destination。
- 程式批次一 `98525237d0de16f3ec74487b3317ddbd95cca654` 建立版本化 App 事件持久資料契約及讀取器，已推送 GitHub 同名票分支。
- 程式批次二 `9ddfe11` 接上 `RoundCoordinator` 公開 App 記錄／狀態／重試入口、真正主頁 App 診斷入口，以及 App 紀錄納入正常保存與關閉協調；若保存失敗視窗保持開啟，可在關閉流程非阻塞重試。時間資料讀取器驗證 ISO 格式與時區；診斷詳細區明示事件時間、事件／訊息識別、捕捉參數及原始診斷。此批已在桌面 Tk 下完成 2 個實際 Tk 案例及 83 個聚焦測試，並已推送 GitHub。推送完成訊息已確認；仍須直接查詢 GitHub SHA 作為證據。
- M4 中間程式／測試批次 `7990759`（`test: isolate app diagnostic UI recovery cases`）曾通過 328 tests（83.591 秒）；此數字已由下方最終複審修正後的 `be4f091`、330 tests（92.409 秒）取代。該批完成的 UI 暫存隔離仍保留，所有最終案例使用隔離 App 根目錄及暫存偏好、事件、來源與輪次資料。
- M4 六項本機驗收、producer 清單、持久格式及範圍界線已記於驗收紀錄；M4 ticket、拆票 README 及母規格適用覆蓋已更新。固定基準 `648b0c2126aaa6ab29016f2f95deb24ca7c8145f` 的 Standards／Spec 複審已完成且無未解問題，細節與最終文件提交見下方最終複審紀錄。型別檢查設定未找到，不宣稱通過。GitHub 主線合併及合併後驗證仍待完成。
- 首次沙盒真 Tk 執行曾於建窗後以 exit 134 中止；同一聚焦案例及最終完整套件皆在可存取桌面圖形工作階段通過。UI 測試隔離修正完成前的早期執行可能曾將測試啟動診斷追加到預設本機 App event journal；未檢視或刪除任何 App 資料。隔離後的最終驗證全程使用暫存 App 根目錄、偏好、事件、來源與輪次紀錄。
- `7990759` 推送狀態屬中間批次，最終票分支 SHA 與 GitHub 直接查詢結果以本摘要下方 M4 最終複審／交付紀錄為準。合併及 Gitea 同步狀態另以下方記錄更新。
- 交付界線：M4 不處理 M5～M10 全部設定／衝突視窗翻譯、完整關閉文案政策、歷史訊息遷移、App 事件清理或 bundle 發布；不啟用任何 App 事件刪除。公司 Gitea 同步未完成前保留本地與 GitHub `Multilingual/ticket-04` 分支，不執行分支清理。

## M4 最終複審與完整驗證（10/09 更新）

- Standards／Spec 先後發現並要求修正三項缺口：父目錄 fsync 失敗不能誤報完成、復原後歷史 journal 錯誤需在 Tk 診斷視窗可查、匯入／匯出故障需有實際 App 控制驗收。另 Standards 複審指出每 150 ms 複製完整 App 歷史會隨紀錄增長拖慢 Tk。均已修正並按固定基準 `648b0c2126aaa6ab29016f2f95deb24ca7c8145f` 複審；截至 `be4f091` 無未解 Standards 問題或 Spec 缺口。
- `06a4093` 修正目錄 fsync 耐久性、診斷歷史 UI，並補上真正 Tk 匯入／匯出錯誤檢查；`be4f091` 加入公開 revision token，避免視窗關閉時讀取診斷歷史、視窗開啟且沒有新事件時重複複製完整 journal。每批已先驗證、commit 並推送 GitHub 同名分支。
- 最終程式／測試驗證 SHA：`be4f091`。完整含 Tk 命令 `B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py` 通過 330 tests（92.409 秒）；`python3 -m compileall -q src tests`、`git diff --check` 通過。真正 Tk 涵蓋保存歷史故障與修復、匯入／匯出診斷、fsync／關閉重試。完整輸出與逐項連結見 M4 [本機驗收紀錄](evidence/multilingual-ticket-04/local-validation.md)。
- 型別檢查設定查無；未宣稱型別檢查通過。固定雙軸審查使用 M4 開始前基準 SHA，未沿用 M2／M3 基準。
- GitHub 已以合併提交 `f7e24cd265fc173d5d113e7fb122083602f5e5fa` 將 M4 併入 `B518-Log-Solution`；合併後完整含 Tk 套件 `B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py` 通過 330 tests（93.584 秒）。合併主線與驗收文件推送後直接查詢曾確認 SHA `a14548e4afa93f1ca00cba3eb165cb1bf4eab7ff`；之後的文件更新也已推送，最後直接查詢確認主線 SHA `8f8b3a1286bc561e239395f9e52bd19efb6244df`，GitHub 票分支仍為 `e663e430d9fed1541bc0e4c20447d2f630c698de`。公司 Gitea 同步延至週一；Gitea 直接確認前保留本地及 GitHub `Multilingual/ticket-04`，不清理票分支。M4 不修改任何 GitHub Issue 狀態。

## M5：設定與檔案對話框（GitHub #18）進度

- M4 依賴已由 ancestry 與實際交付證據確認：M4 merge `f7e24cd265fc173d5d113e7fb122083602f5e5fa` 是 M5 固定基準 `740b26c23f5fb6fcc0988272183159b4405df5da` 的祖先；M4 本機驗收記錄涵蓋雙語 App 事件、診斷、重試及正常關閉。README／M5 ticket 的 #17 阻擋描述已更新為已解除。
- 在乾淨的 GitHub 基準上建立 `Multilingual/ticket-05`。程式批次加入集中設定／配置／保存期限文案、既有設定視窗原地刷新、設定操作 M4 雙語事件、檔案選擇器 App 標題與類型文字，以及英文最小視窗重排。配置／語言／保存天數持久資料仍分開，未改設定格式或輪次生命週期。
- 真 Tk 驗收：設定頁英文／繁中即時切換保留草稿、選取、分頁與驗證狀態；保存期限與清理摘要、profile／匯入匯出錯誤、App 診斷磁碟讀取及 680×560 版面已驗。全套含 Tk 命令 `B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py` 通過 334 tests（80.972 秒）；完整 `test_log_solution_ui` 模組通過 57 tests（57.124 秒），`test_language_catalog` 與 `test_machine_profiles` 共 29 tests 通過。`compileall` 及 `git diff --check` 通過。型別檢查設定查無，不宣稱通過。
- M5 母規格案例 1、4、14 的設定畫面適用部分已通過；案例 6 僅完成真 Tk App 按鈕入口的受控返回值、標題／類型翻譯、取消不改資料測試。系統原生檔案對話框的實際操作與原生覆寫確認仍待桌面互動，故 M5 第五項驗收尚未通過，不能合併。所需人工步驟與逐項證據見 [M5 本機驗收](evidence/multilingual-ticket-05/local-validation.md)。
- 固定 M5 review baseline 為 `740b26c23f5fb6fcc0988272183159b4405df5da`。公司 Gitea 依使用者指示週一同步；在原生對話框驗收、雙軸審查與直接確認 Gitea 前，保留 M5 票分支。本票未更新任何遠端 Issue 狀態。
