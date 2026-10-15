# 專案摘要 — 2026-10-15

時區：Asia/Taipei。延續 [2026-10-14 摘要](PROJECT_SUMMARY_2026-10-14.md) 中已查證的 H4–H7 完成狀態及工作目錄保護資訊；沒有補造清除前對話的內容。H8 的規格、完整矩陣、容量原始報告及收尾狀態以本摘要連結的票件證據為準。

## 今日目標與固定基準

- 使用者指定完成歷史事件查詢 H8「大量資料驗收與舊流程收尾」（GitHub #45，父規格 #37），明確不是其他系列同號票。H8 要求與界線見 [H8 ticket](historical-event-query-tickets/08-capacity-and-contract.md)，45 項逐列對照見 [H8 matrix](evidence/historical-event-query-ticket-08/45-story-matrix.md)。不讀寫遠端 Issue。
- Git root 為本專案 repository；Python 測試目錄為 `B518 Log Solution/`。H8 修改前固定 Standards/Spec review base：`d671275f0c89cac92043942fe593e135e7fbfba1`。本票分支 `HistoricalEventQuery/ticket-08` 從基準建立。H5 `7ef1c3e5…`、H6 `592310ee…`、H7 `d671275…` 均在起始基準 ancestry；三票各有完整驗收、Tk suite、固定基準雙軸審查證據，連結於 [H5](evidence/historical-event-query-ticket-05/local-validation.md)、[H6](evidence/historical-event-query-ticket-06/local-validation.md)、[H7](evidence/historical-event-query-ticket-07/local-validation.md)。H1–H4 的依賴基礎於同一驗收鏈可查。
- H8 開始時共用 Git 元資料的 `Mac mini` worktree、`Mac mini-BT-Codex`、兩個語言刷新 validation worktree，以及三個既有 stash 均保留。沒有把舊修改、stash 或其他票 worktree 混入 H8。

## H8 實作與驗收

- H8 程式／測試批次依序提交：`da19ac7` 混合來源容量 fixture 與 reader/public-query contract 測試；`bdddd30` 可重現五情境容量 runner；`f4cc4ab` 情境摘要與 runtime 報告；`56a42c5` 修正完整套件重現的 Aqua modal notice 重映射後焦點遺失；`344b743` 真正 Tk 容量測試；`e076ff6` 比對實際 App 結果首／中／末頁身分並操作可見左右箭頭。均以一般 push 同步到 Gitea 及 GitHub。
- 50,000 事件 fixture：audit 47,250（94.5%）、legacy events.log 2,500（5%）、App 250（0.5%）；52 個邏輯來源、53 個實體檔、20,328,118 bytes；37,520 筆在查詢範圍、12,480 筆在外。216 萬合成事件 fixture：audit 2,041,200（94.5%）、legacy 108,000（5%）、App 10,800（0.5%）；2,151 邏輯來源、2,152 實體檔、881,916,094 bytes；範圍內 1,620,000、範圍外 540,000。兩組均固定 seed/生成規則、+08:00 日期、來源 hashes 和原檔 reader 全集合摘要；216 萬是工程合成事件數，不是產品件數或現場事件量。
- 每組容量 fixture 均完成首次建索引、全新服務重用、單來源變更、索引降級及分頁五個成本情境，每情境三次相同 fixture。50k 各情境 query median 為 18.998 / 3.030 / 3.444 / 24.998 / 4.826 秒；216 萬為 1,424.041 / 485.302 / 476.969 / 1,217.475 / 323.313 秒。未變更重查與分頁均解析 0 個來源、reader bytes 為 0；單來源變更只解析 1 個並重用其餘 2,150 個。完整原檔摘要比對在首次／重用／變更／降級一致。OS cache 未控制，parser bytes 不是物理 I/O，tracemalloc 不含所有 native allocations；沒有另訂規格以外的時間或 RAM 門檻。所有單次原始數據、RSS、索引／固定快照尺寸、分頁和清理在 [capacity reports](evidence/historical-event-query-ticket-08/) 保存。
- 真正 Aqua Tk 使用 50k 與 216 萬真實暫存 audit、legacy、App 來源及實際 `B518LogSolutionApp`。216 萬驗收確認 App 產生 16,200 頁，每頁最多 100 筆，App 結果 API 的第一／中間／末頁身分 SHA 都與獨立原檔基準一致；實際 Tk 箭頭顯示第 1／2 頁並返回第 1 頁，選取詳細可見。受控慢讀期間日期草稿可編輯；5 ms 心跳最大間隔 122.105 ms。來源/App journal hashes 不變，App store 與關閉狀態 complete，Tk 已銷毀。未宣稱實體滑鼠／鍵盤設備或工廠回應時間驗證。
- 系統預設 Python `/Library/Frameworks/Python.framework/Versions/3.8/bin/python3` 是 CPython 3.8.10 x86_64；Tk 8.6.8、Tcl 8.6.8、Aqua 桌面。最後 H8 程式／測試版本 `e076ff68005d52ec2e618c15b347506636862721` 的完整命令 `B518_TK_TESTS=1 B518_H8_CAPACITY_ROOT=/private/tmp/h8-capacity-2160000-fixture PYTHONPATH=src python3 -X faulthandler scripts/run_tests.py` 從 Python 目錄執行，**467 tests / 1,172.542 sec / exit 0 / no skips**。初次完整套件在既有模態提示 Escape 案例等待；受控 red 證明視窗 remap 後 grab 還在但 focus 為 None，修正後兩個 focused 案及完整套件均通過。初次 SIGTERM/143 及堆疊樣本也保留，未當成功證據。Repo 未配置型別檢查器。
- H8 的固定基準 Standards／Spec 複審均無未解阻擋。Spec 要求 45 列矩陣直接連結行為、Tk、容量命令/runtime/result/limit；現由 evidence ID catalog 逐列解析。Standards 提出的頁面 hash 標示及 App 首／中／末頁驗證缺口已修正，focused 50k／2160k 與最後 467-test suite 通過。
- H8 尚未宣稱工廠資料量、設備效能、部署或父規格 #37 全面完成。每日運轉時數、事件/產品比例、三個月存量、來源大小、現場硬體與操作回應列為工廠 follow-up，不是 H8 開發合併阻擋。

## Git 同步及收尾

- Git root 共用 metadata 的遠端：`origin` 指向 Gitea `10.64.76.34:3000/8362/B518-205_207_ATE.git`，並額外 push 到 GitHub `Bowei1121/B518_205_207_ATE.git`；另有 `github` fetch/push remote。主線程式提交 `bd94a22a7d654d70c4a64ce2212b3bcdf83fa518` 以 fast-forward 同步兩端，H8 分支保留至最終文件提交及直接核對後才正常清理。最終目的地 SHA 與查詢時間記於 H8 local validation。
- H8 已 fast-forward 合併至主線，主線合併後完整含 Tk 套件 467 tests / 1,092.897 seconds / exit 0 / no skips。驗收文件已提交並推送；Gitea 與 GitHub 均直接確認主線同步，H8 本地／遠端票分支已正常刪除且查無殘留。其他 worktree、stash 及既存修改維持原狀，細節見 H8 local validation。

交付詳情：[H8 local validation](evidence/historical-event-query-ticket-08/local-validation.md)。H8 不改保存／清理／監控／裁決政策、不操作正式來源資料，不宣稱現場驗收完成。

## 本對話：H8完成後架構優先順序與HMI方向

- 本次依 improve-codebase-architecture 重新分析，固定程式基準為主線 `0ac5575`。原自訂 skill 路徑已不存在，改讀已安裝 plugin 中 engineering/improve-codebase-architecture 的 SKILL／HTML-REPORT，以及 codebase-design；獨立只讀探索所得結論一致。
- 延續本對話前次查核：H8耗時主要為合成容量查詢與完整事件集合核對；當時仍在執行不等於本次仍卡住。目前H8已合併，主線467項含Tk回歸通過（1,092.897秒），票分支已依既有交付紀錄收尾。本次沒有重跑全套或大型容量測試，不將既有證據寫成新測試結果。
- P1／Strong：歷史查詢準備固定結果的成本。216萬合成事件／162萬符合範圍，有效索引重查中位數485.302秒、單來源變更476.969秒；查詢快照3,492,605,952 bytes、持久索引5,377,343,488 bytes。讀取原檔的重複解析已解決，但仍逐筆搬移summary與完整event_json到新快照並建排序索引。建議沿現有查詢interface與seam分段量測、減少重複處理，不取消固定集合、清理後既有詳細可讀與來源不改寫的契約。
- 換頁本身約4.1–100.6毫秒，Tk背景查詢／分頁已在，不再沿用「Tk同步讀全部歷史」的舊版結論。容量runner含tracemalloc、OS cache未控制；上述秒數不是正式設備每次必然等待時間，合成事件量也不是產品件數。
- P2／Worth exploring：AppEventStore逐筆整份journal讀取／驗證／替換及診斷深複製；缺少正常事件頻率、單次保存延遲及關閉等待量測，不升P1。Tk診斷有視窗存在與revision閘門，不是每150ms無條件深複製。保存module已有真正深度，不直接改為append或拆薄殼。
- 本次沒有發現新的、已重現的保存完整性或裁決缺陷，不建議全面架構重寫。HMI可並行做操作流程與原型，主頁固定376px寬與KVM格位／定位／狀態標記屬ADR0002辨識契約，不能當普通裝飾任意搬動；維持ADR0005既有Tk分工與ADR0009即時雙語。尚未進行現場可用性或新版畫面驗收。
- 啟始git status乾淨，沒有使用者未提交檔案可補交。本次只更新本摘要，產品程式不變；另產生繁體中文HTML報告於OS暫存目錄（見下方），不將報告放進repo。系統open失敗、內建瀏覽器file協定被政策拒絕，未改用伺服器或其他方式繞過；交付檔案連結供查看。
- 報告：/var/folders/gk/zpblb4q57bl24pt55p1m933h0000gn/T/architecture-review-20261015-124423.html

## P1局部改善訪談（待整體確認，之後接續HMI）

- 使用者已逐項確認 A1–A13，完整紀錄見 HISTORICAL_QUERY_RESULT_PREPARATION_DISCUSSION_2026-10-15.md；不是程式實作。實際查詢不頻繁、日期較短，故縮限局部改善，不把極端容量當現場急迫度。
- 最終順序是先確認可靠總筆數／全部頁數，再發布最新最多500筆、每頁100筆；替換舊結果後，後續內容背景分批整理，閱讀需求優先。早期先顯示結果、總數稍後補上的提議已被A12／A13取代。
- 列表記憶體最多目前閱讀位置附近500筆，詳細按需載入；重用未變更內容與有效索引、維持固定版本及來源清理後原文可讀，無引用時回收查詢衍生資料。不新增操作員快取設定。失敗重試未完成部分，不能混入新事件。
- 同資料／runtime比較首批時間、複製量與記憶體，先分段量測；大型容量不預設每票重跑數小時，依實際風險補驗，未跑據實說明。工廠驗收不阻擋開發合併。
- 領域詞彙補入固定查詢結果定義；待使用者確認P1整體理解後直接接續HMI訪談。未修改或發布遠端議題。

## HMI訪談與配置原型（待整體確認）

- 使用者逐項確認A1–A15，完整紀錄 HMI_DISCUSSION_2026-10-15.md。主頁376px，第一排「設定圖示＋Foxlink Logo」在左；「待確認圖示(n)、整輪警報、語言下拉」在右，純圖示與固定格位。待確認直接沿用當輪清單數，不按位置去重。
- 選定原型「操作區顯示狀態」，將監控文字放開始／停止附近。保留專案／機型選擇，移除重複 Log Monitoring 與B518 LOG小字。標題為專案、機型、ATE Log Solution與集中版本；設定標題設定／Setting，其他子視窗按功能命名不帶專案名。
- App自有視窗固定淺色且切語言不重排、不丟輸入／選取；唯讀一般文字同底色細黑框，輸入白底，結果色及KVM契約保留；系統原生介面例外。必要真Tk／桌面／回歸通過可合併，工廠驗收不阻擋。
- 已依要求將原圖複製為assets/foxlink_logo.png（137×35，bytes一致），Git僅豁免此PNG，提交5db15af已同步。Logo載入失敗保留格位但留白，不恢復品牌替代文字。
- 原型可切語言及待確認數、查看設定示意，不連設備、不寫偏好。選定來源另保存於codex/hmi-toolbar-prototype-20261015分支9637913，主線不混入原型。原型不是正式Tk或KVM幾何驗收，尚未實作HMI改版；討論文件待使用者整體確認後再規格化。

## 查詢結果準備與HMI分別規格化

- 使用者要求以to-spec將兩份討論各自轉為Spec，並明確核可兩份測試入口：查詢公開提交／取消／頁面／詳細、真實磁碟與真正Tk；HMI真正App操作、雙語bounds／可讀性／鍵盤與既有KVM契約。
- HISTORICAL_QUERY_RESULT_PREPARATION_SPEC_2026-10-15.md：42項使用者故事，發布GitHub #46、ready-for-agent。保留先可靠總數／全部頁數，再發布最新最多500筆與背景分批；列表窗口500、固定原文及版本重用／回收。成本比較以短區間為主，不預設每票重跑數小時極端容量。
- HMI_SPEC_2026-10-15.md：45項故事，發布GitHub #47、ready-for-agent。主頁376px、純圖示與Foxlink Logo、操作區監控狀態、固定雙語布局與App淺色、唯讀同底色黑框；KVM幾何／結果色與既有操作不變。原型來源9637913為配置依據，不當成真Tk驗收。
- 兩規格分開交付，不建立全面互相阻擋，不修改原#37與H1–H8議題；工廠驗收均不阻擋開發合併。此回合僅文件與發布，未修改正式程式、拆子票或執行產品測試。
