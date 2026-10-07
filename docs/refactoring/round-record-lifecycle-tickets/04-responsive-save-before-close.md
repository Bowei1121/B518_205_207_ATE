# T4：所有本次執行紀錄完整保存後才正常關閉

## Parent

Part of [規格 Issue #1](https://github.com/Bowei1121/B518_205_207_ATE/issues/1)。依 ADR 0007／0008 與已確認拆票方案實作。

## What to build

正常關閉時停止新增監控並於背景等待本次執行全部未保存輪次，視窗保持可操作。失敗可重試或取消關閉，所有必要 Session 與 audit 完整保存後才正常銷毀視窗。

## Acceptance criteria

- [x] 不再於各等待兩秒後警告並關閉，完整判定涵蓋前輪及目前輪次；flush=True 但 audit 不完整時不能正常關閉。
- [x] 等待、失敗及重試時 Tk 事件迴圈可操作，關閉與重試按鈕不重入。
- [x] 取消關閉保留待保存資料及必要操作資源，不隱式重啟已停止來源收集；熱鍵等資源不會永久提前關閉。
- [x] 故障修復且全部保存成功後可正常關閉，歷史錯誤不永久阻擋；不提供略過未保存資料的正常關閉選項。
- [x] 明確提供關閉保存狀態供後續清理協調，關閉不掃描歷史 Session，不變更產品結果放行條件。
- [x] 真正 Tk 驗證成功、暫時／持續失敗、跨輪失敗、取消與再次關閉全部流程。

驗收證據：見 [Ticket 04 本機驗收紀錄](../evidence/ticket-04/local-validation.md)。固定 review 基準 `ddd19f979dc1d241e3bf66c45f15ff4c0e831bb5`；225 項完整套件與 Standards／Spec 雙軸複審通過。最終合併 commit `2172f8f3603532122edbc82fc370c79222318840`，合併後 225 項完整套件通過；Gitea、GitHub 已同步，`round/ticket-04` 本地及遠端分支已安全刪除。

## Blocked by

- [#4：換輪後仍追蹤並補存所有未保存輪次](https://github.com/Bowei1121/B518_205_207_ATE/issues/4)
