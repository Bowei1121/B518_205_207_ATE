## Parent

Part of #28 — https://github.com/Bowei1121/B518_205_207_ATE/issues/28

## What to build

建立可讀取新舊清理原因的集中表述契約，透過真實摘要與真正 Tk 查閱已知原因、未知外層提示及完整原文；正式清理產生端暫不切換。

## Acceptance criteria

- [x] 先核對 ledger、清理結果、雙語與回復契約；採現有 ledger schema 的可選原因欄位，不重置 schema、active plans、摘要或恢復進度。
- [x] 讀取新原因識別、參數、捕捉繁中／英文說明與原始診斷；保留 run／輪次／時間／結果／計數關聯。
- [x] 驗證新原因欄位與原因紀錄版本；舊原因僅對照已查證的 producer 原文及精確前綴，不以含糊文字分類。
- [x] 未知或不適用格式使用所選語言外層提示並顯示完整原始原因／診斷；資源或參數不適用時回退保存英文，不顯示內部訊息識別碼。
- [x] 原因表述只控制顯示，不參與刪除判定；時間、路徑、序號、身分及原始診斷保持原值。
- [x] 真實暫存 ledger 同時放入新原因、舊原因及 active plan，由全新 RoundCoordinator 與真正 Tk 設定頁讀取狀態、列表與詳細內容。
- [x] 英文／繁中閱讀與切語前後 ledger bytes 完全相同，測試關閉啟動清理排程；正式 producer 與正常清理路徑未切換。
- [x] 輪次、App 事件及封存原因均由新格式與既有清理行為覆蓋；完整回歸通過。

## Blocked by

None (can start immediately).

## Verification

Implementation and evidence: [C1 local validation](../evidence/retention-reason-ticket-01/local-validation.md). C2 and C3 producer migrations and C4 all-screen migration remain separate tickets.
