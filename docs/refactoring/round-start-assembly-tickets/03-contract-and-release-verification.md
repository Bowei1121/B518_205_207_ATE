## Parent

Part of #24 — https://github.com/Bowei1121/B518_205_207_ATE/issues/24

## What to build

移除桌面已無呼叫端的舊組裝規則，使正式版本只有一套啟動準備。完成所有平台、桌面與保存安全性驗證，交付可追查的驗證結果與後續現場驗收清單。

## Acceptance criteria

- [x] 確認正式啟動已完全使用集中準備流程，移除無呼叫端的舊配置驗證／來源組裝／配置證據組裝；不得刪除配置編輯、匯入匯出或其他功能仍使用的能力。—[驗收紀錄](../evidence/round-start-assembly-ticket-03/local-validation.md)
- [x] 移除失去意義的私有呼叫鏈／widget 補齊測試細節，保留其有效行為情境；保留真正 Tk、平台解析與 ConfiguredMonitor 的行為測試。—[驗收紀錄](../evidence/round-start-assembly-ticket-03/local-validation.md)
- [x] 正式交付僅有一套啟動準備規則，不留下平行組裝或永久相容選項；配置參數仍可獨立更新，新來源格式仍隨 App 發布。—[驗收紀錄](../evidence/round-start-assembly-ticket-03/local-validation.md)
- [x] 完成規格全部 14 項程式與桌面驗收情境，記錄各情境測試入口、實際結果及未驗證限制；先前測試數字不能充當本次通過證據。—[十四組對照](../evidence/round-start-assembly-ticket-03/local-validation.md)
- [x] Atlas DFU／FCT、B482 BT、RS-WMT BT、sample-json FCT 均完成新流程回歸；驗證容量、路徑、位置、結果、事件與雙份配置證據。—[平台與磁碟證據](../evidence/round-start-assembly-ticket-03/local-validation.md)
- [x] 準備期計時、停止／逾時、建立失敗、偏好保存失敗、RUNNING／AWAITING_REVIEW／關閉中開始與舊輪事件隔離均維持契約。—[輪次情境證據](../evidence/round-start-assembly-ticket-03/local-validation.md)
- [x] 執行相關跨輪未保存追蹤、重試、完整保存才關閉、封存與期限清理安全回歸，確認改造沒有破壞保護或造成漏寫／重複。—[完整套件結果](../evidence/round-start-assembly-ticket-03/local-validation.md)
- [x] 完成專案必要檢查及桌面驗證，記錄目前版本與結果，所有既有平台完成後才交付；不以拆檔數或未量測效能作為驗收。—[命令與結果](../evidence/round-start-assembly-ticket-03/local-validation.md)
- [x] 提供現場驗收清單：工程師認可的實際配置與各平台來源、正常啟動、位置／結果、停止、失敗提示、保存關閉，以及設備／配置版本／結果記錄方式。—[現場驗收清單](../evidence/round-start-assembly-ticket-03/field-acceptance-checklist.md)
- [x] 清楚標記現場驗收另階段安排；本票完成不代表現場設備已驗收，不等待未安排的現場工作才交付程式。—現場清單維持待排程，沒有宣稱設備驗收完成。
- [x] 待確認入口無副作用修正與多語言工作維持另案，不修改父規格議題狀態或內容。—保留三入口基準測試；未操作遠端議題。

## Blocked by

- #26 — 桌面開始操作接入集中準備流程

## R3 delivery status

All 11 acceptance items have evidence in [R3 local validation](../evidence/round-start-assembly-ticket-03/local-validation.md). The full Tk suite passed 286 tests on the final program/test SHA `8f9b293ec7c90595c4bcd443daabf26e72049f0b` and again after merge on `98fa01e20dd883fc6a9d6c3c25fbc764e5c3cd7e`. Fixed-base Standards review found no violations and one non-blocking test-maintenance observation; Spec review found no blocking gaps. Merge SHA is `98fa01e20dd883fc6a9d6c3c25fbc764e5c3cd7e`; the post-merge evidence and final documentation updates were directly verified on Gitea and GitHub, and the local and both remote ticket refs were removed. Physical field acceptance remains a separate pending activity.
