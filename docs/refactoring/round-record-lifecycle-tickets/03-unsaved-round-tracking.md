# T3：換輪後仍追蹤並補存所有未保存輪次

## Parent

Part of [規格 Issue #1](https://github.com/Bowei1121/B518_205_207_ATE/issues/1)。依 ADR 0007／0008 與已確認拆票方案實作。

## What to build

操作員即使前輪保存失敗後已開始新輪，仍能看見本次執行所有未保存輪次並重試補存。共同輪次保留必要恢復資料，保存完成後釋放；不需要掃描全部歷史 Session。

## Acceptance criteria

- [x] 換輪不丟失前輪待保存資料、錯誤原因或重試入口，UI 能辨識受影響輪次。（共同入口與真正 Tk 選取舊輪測試；見 [驗收紀錄](../evidence/ticket-03/local-validation.md)。）
- [x] 本次 App 執行的全部未保存輪次可經共同入口查詢、重試及確認完整保存；新輪與舊輪事件不混淆。（多個舊輪逐輪重建及目前看板隔離測試；見 [驗收紀錄](../evidence/ticket-03/local-validation.md)。）
- [x] 已保存輪次釋放不必要物件與 worker；仍有失敗或未保存工作者保留必要資料。（六輪保存後弱參照回收測試；audit worker 空閒退出沿用 Ticket 01 驗收；見 [驗收紀錄](../evidence/ticket-03/local-validation.md)。）
- [x] 提供保存、封存及後續清理共用的未保存輪次保護狀態，不以目前顯示輪次取代全部追蹤。（`unsaved_rounds()` 與 `has_unsaved_rounds` 追蹤本次 coordinator 的全部未完成輪次；見 [驗收紀錄](../evidence/ticket-03/local-validation.md)。）
- [x] 以前輪故障、開始新輪、修復、磁碟重建及真正 Tk 跨輪重試驗證，且未掃描歷史 Session。（暫存磁碟與真正 Tk 測試，並確認本次追蹤不載入歷史 Session；見 [驗收紀錄](../evidence/ticket-03/local-validation.md)。）

## Blocked by

- [#3：本輪保存失敗可有序重試，且不漏寫或重複](https://github.com/Bowei1121/B518_205_207_ATE/issues/3)
