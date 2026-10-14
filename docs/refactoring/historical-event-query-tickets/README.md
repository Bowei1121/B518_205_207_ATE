# 歷史事件查詢開發票總覽

使用者已核可H1–H8的粒度與依賴。父規格為 [GitHub #37](https://github.com/Bowei1121/B518_205_207_ATE/issues/37)，父議題未修改或關閉。

所有開發票標記 ready-for-agent，GitHub 使用原生 blocked-by 關係；只有阻擋票已完成的票才可開始。H1–H3 已完成並納入基準；H4 依 H3 開始交付。README 初始狀態曾記錄 H2 進行中及 H3 可由 H1 開始，現已過時，Git ancestry 與各票最終驗收證據顯示 H3 開始前 H2 已合併。

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

H4 connects a versioned SQLite derivative index to the public historical-query service and the actual App. It records source identity/version and query event fields, validates versions around reads, reuses unchanged sources across newly created services, and refreshes changed sources while preserving the H3 fixed page/detail snapshot contract. Three-run source-reader byte counts, parsing, elapsed time, memory and SQLite sizes on a generated 450-event fixture, real Tk interaction, runtime differences, and remaining scope are in [H4 local validation](../evidence/historical-event-query-ticket-04/local-validation.md). The complete Python 3.11.7/Tk 8.6.12 suite and fixed-base Standards/Spec review passed; merge and direct remote synchronization will be added after those steps. Reader byte counts are parser input counts, not OS-level disk I/O measurements. H5–H8, parent spec #37, capacity and factory acceptance are not claimed.
