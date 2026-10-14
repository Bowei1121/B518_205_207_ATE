# 歷史事件查詢開發票總覽

使用者已核可H1–H8的粒度與依賴。父規格為 [GitHub #37](https://github.com/Bowei1121/B518_205_207_ATE/issues/37)，父議題未修改或關閉。

所有開發票標記 ready-for-agent，GitHub 使用原生 blocked-by 關係；只有阻擋票已完成的票才可開始。H1–H3 已完成並納入基準；H4 已完成整合後必要驗收，其同步紀錄見下方 H4 狀態及驗收證據。README 初始狀態曾記錄 H2 進行中及 H3 可由 H1 開始，現已過時，Git ancestry 與各票最終驗收證據顯示 H3 開始前 H2 已合併。

| 票 | GitHub | 本機文件 | 阻擋 |
| --- | --- | --- | --- |
| H1：日期查詢與首批結果 | [#38](https://github.com/Bowei1121/B518_205_207_ATE/issues/38) | [逐票內容](01-date-query.md) | 無 |
| H2：重新查詢、取消與視窗生命週期 | [#39](https://github.com/Bowei1121/B518_205_207_ATE/issues/39) | [逐票內容](02-query-lifecycle.md) | H1 #38 |
| H3：完整分頁與按需查看詳細資料 | [#40](https://github.com/Bowei1121/B518_205_207_ATE/issues/40) | [逐票內容](03-paged-history.md) | H1 #38 |
| H4：持久索引與增量查詢 | [#41](https://github.com/Bowei1121/B518_205_207_ATE/issues/41) | [逐票內容](04-incremental-index.md) | H3 #40 |
| H5：異常提示、索引降級與重試 | [#42](https://github.com/Bowei1121/B518_205_207_ATE/issues/42) | [逐票內容](05-query-recovery.md) | H2 #39、H4 #41 |
| H6：固定結果與保存、清理共存 | [#43](https://github.com/Bowei1121/B518_205_207_ATE/issues/43) | [逐票內容](06-retention-coexistence.md) | H3 #40、H4 #41 |
| H7：圖示操作與即時雙語整合 | [#44](https://github.com/Bowei1121/B518_205_207_ATE/issues/44) | [逐票內容](07-localized-query-ui.md) | H2 #39、H3 #40 |
| H8：大量資料驗收與舊流程收尾 | [#45](https://github.com/Bowei1121/B518_205_207_ATE/issues/45) | [逐票內容](08-capacity-and-contract.md) | H5 #42、H6 #43、H7 #44 |

## 依賴與分階段交付

H1建立可展示的背景日期查詢及首批結果；H2與H3在此基礎各自完成生命週期與完整分頁。H4接入持久索引後，H5及H6補齊恢復與保存清理競態；H7不需等索引，完成圖示及語言狀態整合。H8最後完成容量、全規格驗收及舊路徑收尾。

每票完成自己的必要測試、桌面驗證及相關回歸即可合併，不要求等待整個功能全部完成。中間階段不能宣稱父規格已完整交付。H1首批100筆只是第一階段；H3提供完整分頁，H4才保證跨重啟索引與正常增量成本。

### H1 delivery status — 2026-10-13

H1 的日期條件、背景首批查詢與真正 Tk 驗收已完成，固定基準 Standards／Spec 審查及合併後完整含 Tk 套件均通過。票分支已於兩個遠端直接核對後安全刪除；最終文件提交與同步資訊列於 [H1 local validation](../evidence/historical-event-query-ticket-01/local-validation.md) 及本次交付回報。本階段只有最新 100 筆首批結果；完整多頁查閱屬 H3、持久索引與正常增量讀取成本屬 H4。此狀態不代表 H2–H8 或父規格 #37 全部完成，也不代表工廠容量／現場驗收完成。

### H2 delivery status — 2026-10-13

H2 已完成查詢世代隔離、協作取消、最新待處理請求合併與歷史視窗關閉／重開收尾；在真正 Tk 慢讀下驗證重查、取消及 App 關閉仍可操作，並已快轉合併至 `B518-Log-Solution`。合併後完整含 Tk 套件在 Python 3.11.7／Tk 8.6 桌面再次通過；Python 3.8/Tk 的 Tcl abort 亦在固定基準重現，兩者分開記錄。逐項驗收、runtime 差異、審查、merge 及目的地同步證據見 [H2 local validation](../evidence/historical-event-query-ticket-02/local-validation.md)。H3–H8 與父規格 #37 尚未因此完成，完整分頁、持久索引及工廠驗收仍各依其票件範圍。

## 規格覆蓋

| 規格故事 | 主要票件 |
| --- | --- |
| 1–14、16、23、31 | H1；H3完成完整排序／多頁 |
| 15、25、30 | H7；H3提供分頁操作 |
| 17–22、42 | H2；H1建立背景查詢 |
| 24、26–29、41 | H3；H4持久索引，H6版本與來源競態 |
| 32–35、39–40 | H5；H4建立索引 |
| 36、43 | H6；全部票保持原契約 |
| 37–38 | H4 |
| 44–45 | 每票驗證，H8整體驗收 |

## 合併與現場驗收界線

必要開發／測試／桌面驗證是逐票合併條件。工廠實際資料量、硬碟與設備效能是後續部署驗收，不阻擋票件合併回 B518 Log Solution 工作樹。216萬筆合成事件是工程壓力規模，不等於實際產品件數或現場事件量。本次建立票件，不代表程式或驗收已完成。

### H3 delivery status — 2026-10-13

H3 extends H1's first page into a fixed query snapshot paged in batches of at most 100. The history window exposes pure left/right controls and page information. Compact summaries are retained for listing while original event payloads live in a temporary SQLite snapshot; pages are read by range, and full detail is loaded only for the selected event. Snapshot resources are released when replaced or when the app-owned query service shuts down. Real Tk navigation, mixed-source identity/order, fixed source boundary, selected-detail loading, source-byte preservation, memory observations, and cleanup are documented in [H3 local validation](../evidence/historical-event-query-ticket-03/local-validation.md). H4's persistent/restart-reusable index and cross-query incremental cost, H5–H8, full parent delivery, and factory acceptance are outside this delivery.

### H4 delivery status — 2026-10-14

H4 connects a versioned SQLite derivative index to the public historical-query service and the actual App. It records source identity/version and query event fields, validates versions around reads, reuses unchanged sources across newly created services, and refreshes changed sources while preserving the H3 fixed page/detail snapshot contract. Three-run source-reader byte counts, parsing, elapsed time, memory and SQLite sizes on a generated 450-event fixture, real Tk interaction, runtime differences, and remaining scope are in [H4 local validation](../evidence/historical-event-query-ticket-04/local-validation.md). The H4 branch's Python 3.11.7/Tk 8.6.12 suite and fixed-base Standards/Spec reviews passed. The earlier post-merge Aqua initialization abort was reproduced without project code and isolated to sandbox GUI-service access (three failed sandbox probes versus three successful desktop probes). The clean integrated mainline then passed all 439 Tk-enabled tests in 160.299 seconds with exit 0 and no skips. The accepted program/test revision is unchanged; fresh disk-cost and cleanup evidence is included in the resumption record. Final remote checks are recorded there. At H4 closeout, the user asked to stop after H4 acceptance, so its branch/baseline worktree and existing stashes were retained. A later explicit request started H5 from the accepted mainline; see H5 delivery status below. Reader byte counts are parser input counts, not OS-level physical disk I/O measurements. H5–H8, parent spec #37, capacity and factory acceptance are not claimed by H4.

### H5 delivery status — 2026-10-14

H5 adds index-fault fallback to the public background query path, visible localized acceleration-degraded and incomplete-result messages, and a paged anomaly list whose raw source/diagnostic details load only after selection. The query continues to use the established audit, legacy `events.log`, and App journal readers; unknown dates stay outside normal date results. Failed/unconfirmed source reads do not become valid index entries, and a later Search reuses the existing query path to retry after repair. H5's true-Tk/disk, corrupt/unsupported/readonly index, mixed-source, raw-diagnostic, source-byte and complete-suite evidence is in [H5 local validation](../evidence/historical-event-query-ticket-05/local-validation.md). H2/H4 were verified in ancestry and their accepted evidence before H5 changes. Current H5 branch, fixed-base Standards/Spec review, and merge state are reported in that evidence; H6–H8, capacity, complete parent delivery and factory acceptance remain separate.

H5 必要驗收已完成，固定基準 Standards／Spec 審查無阻擋；Python 3.11.7／Tk 8.6.12 桌面完整套件合併前 450 項、合併後 450 項均通過。指定系統 Python 3.8.10 的 H5 完整套件及固定基準對照亦分別通過 450／439 項；另一次未保存結束碼的 3.8 原生崩潰未能重現，測試及限制詳見驗收證據。H5 已 fast-forward 納入並推送至 `B518-Log-Solution`，合併 SHA `7ef1c3e5ceb69dea91a7fb0afb1dd4b8f6a2336f`；已刪除 H5 本地及兩遠端分支，最終文件同步資訊記於驗收證據。

### H6 implementation status — 2026-10-14

H6 已接入來源版本定位、查詢固定快照詳細資料、正式 App journal／輪次清理期間保持固定查詢集合，以及來源讀取期間變更的未確認提示；來源刪除後重新查詢會移除持久索引中的舊來源。依使用者釐清，可信 H3 暫存的完整原始 JSON 視為已取得，清理／同路徑替換後仍能讀取舊內容，不回讀或冒充新版本。聚焦查詢／輪次測試 80 tests 通過；先前的完整 Tk native abort 已定位到既有 M10 fault-injection traceback 的測試收尾循環，固定基準也重現。測試主執行緒 cleanup 修正及 subprocess red/green 回歸後，最終 Python 3.8.10/Tk 8.6.8 完整含 Tk 套件 461 tests / 139.240 sec / exit 0 / no skips，Standards/Spec 固定基準複審無阻擋。七項驗收、主線重驗、同步及清理結果記於 [H6 local validation](../evidence/historical-event-query-ticket-06/local-validation.md)。H7/H8、父規格與工廠驗收仍另追蹤。

本機 H6 已快轉整合至 `B518-Log-Solution` 的 `592310ee51d813111b2f02297a4a6756e97ce0ac`（無 merge commit），合併後同一 Python 3.8.10/Tk 8.6.8 主線完整套件 461 tests / 138.609 sec / exit 0 / no skips；同步與清理見 H6 evidence closeout。

### H7 delivery status — 2026-10-14

H7 adds a localized magnifier Search control, pure horizontal paging arrows, keyboard focus traversal/Space activation, and non-focusing hints that refresh in the current App language and close with their controls/window. The existing single App language receiver rerenders current date validation, query status, result range, page and details without submitting a query or changing the H2 generation/H3 fixed snapshot. Real Aqua Tk tests cover Tab traversal, disabled first/last arrows, hint hover/focus lifecycle, editing invalid unsent date text, page 2 selection/detail/scroll retention, a gated query across a language change, and byte-identical audit, legacy `events.log` and App journal sources. Exact test, runtime, initial transient cleanup exception, fixed-base comparison, dual review and limits are in [H7 local validation](../evidence/historical-event-query-ticket-07/local-validation.md). H2/H3 were verified as accepted ancestors with full-suite and Standards/Spec evidence before H7 work. H4–H6 remain as previously delivered; H8 full-state integration/capacity, physical keyboard/mouse hardware and accessibility certification, full parent #37, factory acceptance and deployment are not claimed.
