# 歷史事件查詢開發票總覽

使用者已核可H1–H8的粒度與依賴。父規格為 [GitHub #37](https://github.com/Bowei1121/B518_205_207_ATE/issues/37)，父議題未修改或關閉。

所有開發票標記 ready-for-agent，GitHub 使用原生 blocked-by 關係；只有阻擋票已完成的票才可開始。目前可先開始H1。

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

H1 的日期條件、背景首批查詢與真正 Tk 驗收已在 `HistoricalEventQuery/ticket-01` 完成；完整含 Tk 套件及固定基準 Standards／Spec 審查已通過。程式分支已同步至設定的 GitHub 與 Gitea push 目的地；最終文件提交、合併、主線重驗、直接遠端查詢及分支清理仍待完成。逐項命令、runtime、來源 bytes 與日期邊界證據見 [H1 local validation](../evidence/historical-event-query-ticket-01/local-validation.md)。本階段只有最新 100 筆首批結果；完整多頁查閱屬 H3、持久索引與正常增量讀取成本屬 H4。此狀態不代表 H2–H8 或父規格 #37 全部完成，也不代表工廠容量／現場驗收完成。

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
