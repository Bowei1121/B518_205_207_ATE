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
- H8 的 Standards/Spec 已初審。Spec 先前要求 45 列矩陣更直接連結行為、Tk、容量命令/runtime/result/limit；現已有 evidence ID catalog 逐列解析。Standards 提出分頁 hash 被標成完整集合及 App 只有第一頁可見兩個阻擋；已改稱頁面錨點 hash，並擴充上述 App 頁面與真正箭頭測試，focused 50k/2160k 與 final suite 已通過。固定基準 Standards/Spec 複審均已完成且無未解阻擋；H8 ticket 前六項已依證據勾選，最後合併項待主線重驗證及同步後勾選。
- H8 尚未宣稱工廠資料量、設備效能、部署或父規格 #37 全面完成。每日運轉時數、事件/產品比例、三個月存量、來源大小、現場硬體與操作回應列為工廠 follow-up，不是 H8 開發合併阻擋。

## Git 同步及剩餘步驟

- Git root 共用 metadata 的遠端：`origin` 指向 Gitea `10.64.76.34:3000/8362/B518-205_207_ATE.git`，並額外 push 到 GitHub `Bowei1121/B518_205_207_ATE.git`；另有 `github` fetch/push remote。程式批次推送訊息成功，且直接 `ls-remote` 查詢於 H8 過程確認兩端 mainline 為固定基準、票分支為當前 H8 程式／測試提交；最後文件提交後需再次直接查詢全部 push 目的地。
- 待完成順序：在票分支提交並推送驗收文件；再次直接查所有目的地；確認 `B518-Log-Solution` 乾淨且納入遠端後 fast-forward；在主線跑必要完整 Tk 套件；兩端同步確認後正常刪除本票分支，回到 `B518-Log-Solution`。尚未完成前不刪 H8 分支、不移除其他 worktree/stash。

交付詳情：[H8 local validation](evidence/historical-event-query-ticket-08/local-validation.md)。H8 不改保存／清理／監控／裁決政策、不操作正式來源資料，不宣稱現場驗收完成。
