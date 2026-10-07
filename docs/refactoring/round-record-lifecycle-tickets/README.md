# 輪次紀錄生命週期票號與依賴

來源：[正式規格](../ROUND_RECORD_LIFECYCLE_SPEC_2026-10-06.md)，對應 [GitHub 規格 Issue #1](https://github.com/Bowei1121/B518_205_207_ATE/issues/1)。已查核議題完整內容與本機規格一致，沒有留言。

狀態：使用者已確認拆票方案，7 張票已發布為 GitHub #2～#8，全部標記 ready-for-agent。T1、T2 已完成本機實作、驗收及雙軸 code review，並已合併至 `B518-Log-Solution`。T3 已完成本機實作、五項驗收、218 項完整套件測試及固定基準 Standards／Spec 雙軸複審；無未解審查問題。合併 commit `d424470` 及驗收狀態更新已同步至 Gitea、GitHub；本地與兩遠端專用分支已清理。T4～T7 尚未開始。T1～T7 保留作本機代號；直接阻擋關係已設定為 GitHub 原生 blocked-by，正文也附真實票號。原規格 Issue #1 僅在各票正文作 Parent 參考，沒有修改、關閉或新增其原生子議題關係。

| 本機票 | GitHub | 標題 | 直接阻擋票 | 可驗證交付 |
| --- | --- | --- | --- | --- |
| [T1](01-idle-audit-writer.md) | [#2](https://github.com/Bowei1121/B518_205_207_ATE/issues/2) | 完成輪次後回收 audit writer，人工操作仍可保存 | 無 | 多輪不累積 writer，退出競爭不漏寫；已合併，見 Ticket 01 驗收紀錄 |
| [T2](02-current-round-save-recovery.md) | [#3](https://github.com/Bowei1121/B518_205_207_ATE/issues/3) | 本輪保存失敗可有序重試，且不漏寫或重複 | #2 | 單輪故障、修復、UI 重試及磁碟重建完整路徑；已合併，見 [本機驗收紀錄](../evidence/ticket-02/local-validation.md) |
| [T3](03-unsaved-round-tracking.md) | [#4](https://github.com/Bowei1121/B518_205_207_ATE/issues/4) | 換輪後仍追蹤並補存所有未保存輪次 | #3 | 前輪失敗後開始新輪，仍可選擇重試並確認完成；本機合併 SHA `d424470`，五項驗收及雙軸複審通過，見 [本機驗收紀錄](../evidence/ticket-03/local-validation.md) |
| [T4](04-responsive-save-before-close.md) | [#5](https://github.com/Bowei1121/B518_205_207_ATE/issues/5) | 所有本次執行紀錄完整保存後才正常關閉 | #4 | 非阻塞等待、失敗、重試、取消及成功關閉 |
| [T5](05-trusted-round-archival.md) | [#6](https://github.com/Bowei1121/B518_205_207_ATE/issues/6) | 完整保存的已結束輪次產生可信封存時間 | #4 | 人工處理後封存、磁碟可讀、舊資料保留 |
| [T6](06-global-retention-setting.md) | [#7](https://github.com/Bowei1121/B518_205_207_ATE/issues/7) | 工程師可持久設定全域輪次保存天數 | 無 | 設定畫面、驗證、持久讀寫與縮短期限提示 |
| [T7](07-background-round-retention.md) | [#8](https://github.com/Bowei1121/B518_205_207_ATE/issues/8) | 背景清理到期整輪紀錄，保留摘要並可恢復失敗 | #5、#6、#7 | 自動排程到整輪刪除、保護、摘要與下次重試 |

T1 是保存併發生命週期的前置整理，T2 在此基礎上加入故障保留與重啟。T3 提供共同未保存輪次保護清單，T4、T5 皆使用它；T5 不依賴關閉 UI，兩者可分別實作。T6 不依賴保存復原，僅設定及提示，不提前啟用清理。T7 需要可信封存、有效設定及關閉協調；不重複列出傳遞依賴。

所有票沿用已確認的 RoundCoordinator 高層入口、注入時鐘、真實暫存檔、磁碟重建及真正 Tk 測試。每票需相關案例及現有全套驗證通過、更新證據並 commit／push；不變更產品放行、未知同輪 FAIL 或 KVM 契約。除 T1 外的票與到期資料清理尚未實作。

T3 完成審查及合併後，T4、T5 的直接阻擋條件將解除；T6 可獨立進行，T7 仍需等待 T5、T6 及 T4 的相關關閉協調能力。發布票不代表已認領或開始產品實作。

## 規格驗收覆蓋

| 規格必要驗收案例 | 負責本機票 |
| --- | --- |
| 1：writer 退出、重啟與競爭 | T1 |
| 2：停止讀檔後人工操作保存 | T1、T2 |
| 3：保存故障與完整恢復 | T2 |
| 4：前輪失敗、換輪與資源釋放 | T3、T4 |
| 5：UI 可操作、取消、重試 | T2、T4 |
| 6：完整保存才關閉及契約不變 | T4 |
| 7：保存設定、持久性與提示 | T6 |
| 8：待確認後封存時間 | T5 |
| 9：期限邊界與舊輪次生效 | T7 |
| 10：不符合條件資料保留 | T5、T7 |
| 11：同輪多目錄 | T5、T7 |
| 12：外部及非輪次資料保護 | T7 |
| 13：排程互斥與關閉協調 | T7 |
| 14：清理故障、競爭及部分失敗 | T7 |
| 15：持久摘要與摘要寫入失敗 | T7 |
| 16：新舊資料相容與重建 | T2、T5、T7 |
