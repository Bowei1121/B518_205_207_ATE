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
- 真 Tk 驗收：設定頁英文／繁中即時切換保留草稿、選取、分頁與驗證狀態；保存期限與清理摘要、profile／匯入匯出錯誤、App 診斷磁碟讀取及 680×560 版面已驗。修正關閉保存期間略過清理的可見狀態與封存保護原因翻譯，並讓測試在刪除暫存根目錄前等待公開清理狀態。最終完整含 Tk 命令 `B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py` 通過 334 tests（83.098 秒）；完整 `test_log_solution_ui` 模組通過 57 tests（58.704 秒），`test_language_catalog` 與 `test_machine_profiles` 共 29 tests 通過。`compileall` 及 `git diff --check` 通過。型別檢查設定查無，不宣稱通過。
- M5 母規格案例 1、4、14 的設定畫面適用部分已通過；案例 6 原有真 Tk 受控返回與標題／類型參數測試，於 2026-10-09 再由使用者完成兩語真原生選檔、取消、返回路徑及拒絕覆寫；兩份匯出一致、原檔雜湊不變，七筆 App 雙語事件由新讀取器核對。M5 六項產品驗收全部通過。所需人工步驟與逐項證據見 [M5 本機驗收](evidence/multilingual-ticket-05/local-validation.md)。
- 固定 M5 review baseline 為 `740b26c23f5fb6fcc0988272183159b4405df5da`。Standards／Spec 複審指出的可見狀態、封存原因本地化與測試收尾問題已修正；最終程式／測試提交 `a90be28c8b1615b408aaf6147572e603dff5338e` 已推送 GitHub `Multilingual/ticket-05`，並由 `git ls-remote` 直接確認。原生選檔人工驗收已通過；使用者確認隔離 App 正常關閉，程序 exit 0。依既有授權接續 GitHub 合併與主線完整驗證。公司 Gitea 依使用者指示週一同步；Gitea 直接確認前保留 M5 票分支。本票未更新任何遠端 Issue 狀態。

## M5 人工驗收與 GitHub 合併完成

- 使用者以實際 macOS 原生視窗完成英文／繁中資料夾選取、匯入、匯出、取消與拒絕覆寫，並確認隔離 App 正常關閉；程式 exit 0。兩份匯出與配置一致，原 sentinel SHA-256 不變；全新讀取器驗證七筆連續雙語 App 事件，不虛構 round_id、不因取消多出操作。原生資料夾視窗未渲染 App 提供標題的 OS 邊界如實記錄。
- 人工驗收文件提交 `240d8015fe4d7c22e87e8f0c7b54f1c2f155e848` 已推送 GitHub 票分支；固定基準至該 SHA 的 Standards／Spec 最終複審無未解阻擋。Standards 留一項非阻擋 exact-string reason-mapping 氣味。
- 合併前主線與 GitHub 最新 `740b26c` 一致、工作樹乾淨；合併提交 `cfb35480d890abeb8a03bc74360260dcd8d739e1`。合併後主線完整含 Tk 套件通過 334 tests（95.026 秒），compileall 與 diff check 通過。最終程式／測試內容仍與 `a90be28` 相同，沒有審查後產品修改。
- GitHub 合併推送後直接查詢確認主線 `cfb35480d890abeb8a03bc74360260dcd8d739e1`、票分支 `240d8015fe4d7c22e87e8f0c7b54f1c2f155e848`。這是該次查詢結果；最後文件提交另行推送與直接確認，不把合併 SHA 當成新增文件後的最終 HEAD。正式工作樹已切回 B518-Log-Solution。
- 六項產品驗收已通過；公司 Gitea 依使用者例外待週一同步並直接確認。在此之前保留本地與 GitHub Multilingual/ticket-05，未強推、未刪分支、未改遠端 Issue。

## M6：衝突與警報即時翻譯（GitHub #19）

- M6 固定 review baseline 為 `31a9bccd5cb1534f2d17b99ad6ed3b4f461ffdd4`。依 ancestry 確認 M2、M4、M5 與 C1～C3 已納入該基準；M5 原生選檔人工驗收已完成，不構成本票阻擋。M6 只翻譯既有衝突／警報自有 UI，保留證據、候選與裁決政策。
- 程式批次 `e641dd0` 新增共用中英資源及即時刷新；`8be176e` 整理重複刷新程式並修正共用術語／KVM 與持續收集驗收；`da94db3` 修正定期刷新遇到空選取時殘留舊比較與詳細內容、裁決按鈕仍可用的問題，並重用來源時間／檔名共用術語。每批均驗證、commit 並推送 GitHub 同名票分支。
- 最終程式／測試 SHA `da94db305547307b8a0370c9da9569f07f671986`。聚焦測試 13 項通過（11.538 秒）；完整含 Tk 命令 `B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py` 通過 335 tests（83.317 秒）；`python3 -m compileall -q src tests` 與 `git diff --check` 通過。真 Tk 覆蓋實際語言切換、候選選取及空狀態、受控 Atlas 衝突、警報不自動確認、逐項人工操作、其他位置繼續收集、KVM 可視性及全新 audit 讀取器重建。型別檢查設定未找到，未宣稱通過。
- 固定基準的最終 Standards／Spec 平行複審皆零項可執行發現。證據及五項驗收對照見 [M6 本機驗收](evidence/multilingual-ticket-06/local-validation.md)；ticket 五項驗收已據此勾選，母規格只更新案例 3、4、7、14、15 的 M6 適用部分，未宣稱全 App／bundle 完成。
- M6 程式／測試已推送並由 GitHub 直接查詢確認同名分支 SHA `da94db305547307b8a0370c9da9569f07f671986`。文件提交 `9d45ae4a333d3ca49d2fc122bfd9f613bc90d78e` 推送後，GitHub 直接查詢確認票分支為同一 SHA；本次查詢時間為 2026-10-09。公司 Gitea 依使用者指示延至週一；在 Gitea 直接確認前保留 M6 本地與 GitHub 票分支。遠端 Issue #19／#13 均未修改；M7～M10 仍待各票交付。
- 預合併查核時，GitHub `B518-Log-Solution` 直接查詢為固定基準 `31a9bccd5cb1534f2d17b99ad6ed3b4f461ffdd4`，M6 票分支為 `41bf0fc5ad5d19044cb6e4aae1b59490a156d786`，目標工作樹乾淨且票分支包含目標。合併提交為 `daba4822566f944e603d065b5319674f83c99311`；合併後完整含 Tk 套件通過 335 tests（85.007 秒），在 Python 子目錄的 compileall／diff check 通過。主線驗收文件提交 `8cdbbc0b0aa250e5c8d3c9f34316c41a840d45cf` 推送後，GitHub 直接查詢回傳同一 SHA。該文件的這筆遠端查詢記錄是後續最終摘要更新前的查核；最新推送 SHA 仍以最後直接查詢為準。

## M7：保存與關閉語言協調（GitHub #20）

- 固定 M7 Standards／Spec review baseline：`45df1e36895cdb8bbb313de0a4c038cdeef13ac4`。M4 merge `f7e24cd265fc173d5d113e7fb122083602f5e5fa` 已由 Git ancestry 確認為基準祖先，並核對 M4 本地驗收紀錄；M1～M6 程式基準均在主線。M7 起始工作樹乾淨、票分支原先不存在，從此主線建立 `Multilingual/ticket-07`。
- 真 Tk 新增／改寫 close-save 行為證據：關閉期間禁用語言按鈕及選單、拒絕呼叫／排入的切換並解除已展開選單；目前語言顯示禁用原因；close 標題、狀態與原始錯誤診斷採集中資源。取消後恢復語言入口，但保留待保存／重試工作，且不重啟已停止來源。被拒切換不增加 App 事件 revision。
- 新增驗收測試紅燈確認先前入口仍可於 close-save 中切換；修正後三個聚焦 Tk 測試通過：等待及取消後重關、跨輪保存失敗／非重入重試／取消後繁中重關、衝突與警報操作和 close-save 切換保護。測試使用 Event 控制寫入，並由全新 audit 讀取器確認完整紀錄。原 M4 App journal 雙語顯示、no-round 事件關閉等待及歷史錯誤恢復案例在完整回歸中重跑。
- 程式／測試最終驗證包含真 Tk 已排入事件迴圈的語言切換拒絕案例，測試／證據批次 `db1535259f64d68206b0a0badedf6d862dcedabf`；完整含 Tk 套件 `B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py` 最終通過 335 tests（86.356 秒）。中間一次遇到既有 detached-round archival 測試的暫存目錄清理競爭；該單例連續五次隔離通過，完整套件重跑通過。`python3 -m compileall -q src tests` 與 `git diff --check` 通過。專案無既有型別檢查設定；未宣稱型別檢查通過。固定基準 Standards／Spec 複審無未解問題。
- GitHub 同名票分支程式提交 `fb0598736bc83c9faa8ef1c3695554f2aefb1257`、`098d8cbebdf266d11fc5255eafd47c9971336487` 及測試／證據提交 `db1535259f64d68206b0a0badedf6d862dcedabf` 已推送；該測試批次推送後直接查詢票分支為 `db1535259f64d68206b0a0badedf6d862dcedabf`，同次主線為 `45df1e36895cdb8bbb313de0a4c038cdeef13ac4`。最終文件提交推送後另行直接確認。公司 Gitea `http://10.64.76.34:3000/8362/B518-205_207_ATE.git` 直接查詢連線失敗／無回應，透過 origin 多目的地推送無回應後停止；未移除 push URL。因一個既有目的地未同步，依要求不合併、不刪除票分支。週一重查 Gitea，可達後再同步、完成合併後主線驗證與直接 SHA 確認；確認全部目的地後才清理分支。無遠端 Issue 狀態變更。
- 完整證據：[M7 local validation](evidence/multilingual-ticket-07/local-validation.md)。M8 歷史辨識、M9 App 事件期限清理及 M10 bundle／發布驗證維持待交付。
