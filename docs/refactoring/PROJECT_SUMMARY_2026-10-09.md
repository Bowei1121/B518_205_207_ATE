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
- M7 合併前真 Tk 測試驗證關閉等待／失敗／重試／取消／再次關閉及直接／排入事件迴圈的語言切換拒絕；原始程式／測試提交 `db1535259f64d68206b0a0badedf6d862dcedabf` 時完整套件通過 335 tests（86.356 秒）。使用者授權後，本機 merge commit `35fb3ab640356c5277e2026285757a20cc87c98a` 將票併回 `B518-Log-Solution`。合併後完整 Tk 套件找出舊 close worker 可覆寫取消後新關閉 generation 狀態的競爭；修正及 Event 控制封存等待測試在 commit `d8e105e2ac83463c95176d3138bff26c598208cb`，最終完整套件通過 336 tests（95.425 秒），compileall／diff check 通過。固定基準 `45df1e36895cdb8bbb313de0a4c038cdeef13ac4` Standards／Spec 最終複審無未解問題；專案無型別檢查設定，未宣稱通過。
- 修正已 fast-forward 到本地 `Multilingual/ticket-07` 並推送 GitHub 同名分支；推送命令成功，但隨後直接 `git ls-remote` 遇到 GitHub DNS 解析失敗，故最新 SHA 尚未直接確認。GitHub 主線未推送，本機主線停在 `d8e105e2ac83463c95176d3138bff26c598208cb`。公司 Gitea 依使用者指示週一同步；週一直接確認兩個目的地 SHA 前保留本地及遠端票分支，不做清理。遠端 Issue 未變更。詳見 [M7 驗收紀錄](evidence/multilingual-ticket-07/local-validation.md)。
- 完整證據：[M7 local validation](evidence/multilingual-ticket-07/local-validation.md)。M8 歷史辨識、M9 App 事件期限清理及 M10 bundle／發布驗證維持待交付。

## M8：歷史事件顯示（GitHub #21）

- 固定 review baseline `98a3e5c388cb993154d3302c70c10cbb608398c2`。Git ancestry、實際程式及已提交交付證據確認 M3 merge `fb4ffb2286d9c113511482b738a101a11616bd14` 與 M4 merge `f7e24cd265fc173d5d113e7fb122083602f5e5fa` 都在基準內；M3/M4 直接依賴解除。README／M8 ticket 舊 #16/#17 blocked 描述已按可查證依據修正。
- 新增唯讀歷史事件入口，可查看 round audit、舊 Session `events.log` 及 App event store。新格式依目前資源重呈現，資源缺少／參數無效／版本不適用回退捕捉英文；舊格式只按 audit schema、穩定 producer kind、header platform 和必要欄位精確匹配。無穩定 kind 的舊 `events.log` 及不符合條件的內容保留原文，詳細區保留 raw record／診斷。語言刷新不重讀來源、不改 bytes。
- TDD 加入混合資料真正 Tk 選取／切語案例，涵蓋舊 Session `events.log`、列表／詳細閱讀位置及原文；同時間序號 2／10 順序 regression 紅燈時得到 `[10, 2]`，修正後按數字排序，舊 `events.log` 同時間維持行序。審查後補足 malformed source/station/status/timeout、重複壞行 key 與捲動位置修正。程式／測試 SHA `06c65592958970f38aa9330fb218ab2da66a3581`；完整含 Tk 套件 350 tests（100.778 秒）及歷史讀取聚焦 13 tests 通過，compileall／diff check 通過。型別檢查設定未找到，未宣稱通過。
- M8 五項驗收逐項記錄；固定 baseline `98a3e5c388cb993154d3302c70c10cbb608398c2` 的 Standards／Spec 複審無未解必要問題。本機 merge SHA `dd4306f07a853abbf2a7647f26c7ed3ce3854ccf`；合併後完整含 Tk 套件 350 tests（98.606 秒）通過。2026-10-09 15:29（台北）直接查詢確認 GitHub main 已同步至 merge SHA，票分支此前為 `f762360dc8e709de9945cbf721fd08e7dc412b16`；最後文件提交及分支快轉後會再次查詢。Gitea 內網直接查詢未於 10 秒內回應，週一同步並確認前保留本地／GitHub ticket ref。M9 清理及 M10 完整發布驗收未包含在 M8。
- 詳細 producer／格式辨識規則、拒絕條件、測試結果、真 Tk／磁碟證據及遠端查核見 [M8 本機驗收](evidence/multilingual-ticket-08/local-validation.md)。

## M9：App 事件保存期限清理（GitHub #22）

- M9 固定 Standards／Spec review baseline：`01ab62993cdbc79b3a38a56a7218e63e4ac4ca7f`。以 Git ancestry 核對 M4 `8f8b3a1286bc561e239395f9e52bd19efb6244df` 與既有輪次清理 Ticket 07 `d8e105e2ac83463c95176d3138bff26c598208cb` 均為基準祖先；M4 App 事件雙語／保存／關閉及 #8 可信封存／背景清理依賴已解除。
- M9 依 App 事件原始帶時區 `occurred_at` 清理；輪次仍用可信封存時間。保存容器無退休序號時維持 schema v1，清理後有退休序號範圍時使用 v2，讀取器兼讀並驗證連續序號解釋。混合 journal 只移除確定到期事件，保護 pending、保存／耐久性故障、未知／損壞資料；沿用既有 RoundCoordinator 清理協調、每日排程及摘要 ledger，不新建 scheduler。
- 固定基準複審期間修正三項問題：清理逐層以 `O_NOFOLLOW` pin 管理路徑，並新增呼叫前已存在的祖先 symlink 測試，確認外部 journal bytes 不變、清理不回報完成；容器有退休序號範圍時明確升為 schema v2；期限格式／時區缺失及清理目標類型原因加入中英資源，真 Tk 設定狀態 label 可切換且保留診斷。
- Spec 複審另找出 rename 成功但父目錄 fsync 失敗後，重試可能未重新確認耐久性；以 red-green 增加故障測試，修正無到期事件的重試仍須 fsync pin 住的目錄並以磁碟序號狀態同步記憶體。最後程式／測試 commit `523660779d20b375c1c3f925ed9fce78e381532f`；聚焦 44 tests 通過（12.102 秒），兩項真正 Tk M9 案例通過，完整命令 `B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py` 通過 363 tests（104.336 秒）。`compileall`、`git diff --check` 通過；本專案沒有既有型別檢查設定，未宣稱型別檢查通過。
- 固定基準 `01ab62993cdbc79b3a38a56a7218e63e4ac4ca7f` 的 Standards／Spec 最終複審均無未解阻擋；Standards 留一項非阻擋建議，認為 `cleanup_expired` orchestration 較密集，但同一流程共同保護路徑、資料完整性與耐久性，未為行數拆開。
- 本機 merge commit `d891dd10925e1074d2674b2ed68b36847250fd87` 已將程式與首版驗收文件合入 `B518-Log-Solution`。合併後完整含 Tk 套件 363 tests 通過（97.541 秒）；sandbox 建窗程序曾 exit 134，確認須有桌面存取後，以授權桌面能力重跑並通過。最終文件提交 `2108e41c0fbcbb062a3a179aef30f32bbbdd0fb9` 推送至 GitHub main 與保留票分支；2026-10-09 16:48（台北）直接查詢兩 refs 均為該 SHA。公司 Gitea 週一內網同步並直接確認前保留本地與 GitHub 票分支。詳見 [M9 本機驗收](evidence/multilingual-ticket-09/local-validation.md)。
- M9 六項驗收命令、細節及限制見 [M9 本機驗收](evidence/multilingual-ticket-09/local-validation.md)。M9 只覆蓋母規格案例 12／13 適用部分；M10 全 App／bundle 發布驗收仍待交付。

## M10：全 App 翻譯整合與發布驗證（GitHub #23）—進行中

- 固定 Standards／Spec review baseline 為 `95b791c2cf1a54b10db4f07cbc606ddd06db8280`。M5～M9 實作／合併提交皆以 ancestry 確認納入固定基準，逐票核對 local-validation；M10 直接依賴未阻擋。新建 `Multilingual/ticket-10`，本 Python 專案位於 repo 子目錄 `B518 Log Solution/`。
- GitHub `B518-Log-Solution` 固定起點為 `95b791c2cf1a54b10db4f07cbc606ddd06db8280`。M10 批次 `68379866d09dc8709cd9249665bcd2c0f837f269` 修正來源準備失敗固定中文提示：明確產生 `round.start_failed` 同筆雙語事件、保留原始 exception，真正 Tk 測試驗證繁中提示及 audit 全新讀取器重建；批次 `f58c0a6252e438da8fa67a74ba1feb916516732d` 把主頁監控狀態參數改為穩定 message ID，不再用中文顯示字串反查狀態。各批完成聚焦驗證、commit 並 push GitHub 票分支。
- M10 多視窗真 Tk 案例紅燈發現已開啟 App 診斷與歷史視窗標題不隨語言刷新；`3cebd090d4ec8a6c70c7cc09f69b07b43061f480` 更新視窗原標題，新增設定／App 診斷／歷史視窗同時開啟的實際 Tk 測試：快速英中切換檢查事件列及詳細文字更新，保留草稿、事件選取及視窗實例，App event bytes 與 revision 不變。補強後 source 程式／測試 SHA `e8a309fd1fac186832c5825c803e4299932f206b` 的完整含 Tk 套件通過 365 tests（97.910 秒）；同一聚焦真 Tk 案例另通過 1 test。catalog 兩語各 317 keys 且 `validate_translations()==()`。沒有既有型別檢查設定，未宣稱通過。
- M10 仍未完成：全自有入口整合覆蓋、16 組完整驗收（第 16 組未驗）及正式 bundle／目標環境受政策驗證。固定 SHA 雙軸複審確認 checkbox、可見事件文字斷言、提示證據界線及 SHA 問題已修正。不能合併，應保留票分支。逐票與十六組矩陣見 [M10 驗收](evidence/multilingual-ticket-10/local-validation.md) 及 [發布驗收](evidence/multilingual-ticket-10/release-validation.md)。
- 正式 bundle 尚未建置或驗收，不是測試通過即可替代。實際環境為 Intel macOS 15.7.9／x86_64、系統 Python 3.8.10，Homebrew Python 3.12.13 使用 Tk 9；Python.org 3.12.10 指定路徑不存在，且 macOS／CPU 不符合 Intel Catalina、Apple Silicon 15 或 26 build matrix。build／dist 與目標 venv 不存在；沒有執行會遞增 `VERSION` 及清理輸出目錄的 build script。產物／目標 OS 驗收仍阻擋 M10 合併，具體合規主機步驟見 [M10 發布驗收](evidence/multilingual-ticket-10/release-validation.md)。
- `68379866d09dc8709cd9249665bcd2c0f837f269`、`f58c0a6252e438da8fa67a74ba1feb916516732d`、`3cebd090d4ec8a6c70c7cc09f69b07b43061f480` 及 `e8a309fd1fac186832c5825c803e4299932f206b` 均已推送 GitHub 同名票分支；最新已知 push 回應指向 `e8a309f`。文件批次推送後需直接查詢 GitHub refs。Gitea 內網同步延至週一，未直接確認前保留票分支。無 merge、Issue 變更或分支刪除。M10 尚未完成，source 驗收不代表 bundle／HMI／現場驗收。
