# M7：保存與關閉流程的雙語提示及語言切換協調

## Parent

Part of [規格 Issue #13](https://github.com/Bowei1121/B518_205_207_ATE/issues/13)。依 ADR 0009 及已確認拆票方案實作。

## What to build

操作員以所選語言閱讀保存狀態、失敗、重試與關閉提示。關閉保存期間語言入口停用並說明原因，取消關閉後恢復；App 與輪次所有待保存工作完整保存才正常關閉。

## Acceptance criteria

- [x] 保存狀態、失敗原因、原始診斷、重試及關閉操作完整兩語，使用 App 管理提示保留既有操作效果。
- [x] 正常操作時已開保存／診斷視窗同步更新；關閉保存期間禁止切換，停用原因使用目前語言。
- [x] 取消關閉恢復語言入口及必要操作資源，保留全部待保存資料，不重啟已停止收集。
- [x] 故障修復與重試不重入、不漏寫，歷史錯誤不永久阻止關閉；含無輪次 App 事件，不以翻譯略過保存條件。
- [x] 真正 Tk 驗證兩語下等待、失敗、重試、取消及再次關閉，磁碟雙語事件與結果一致。

## Blocked by

- [#17：無輪次 App 事件雙語保存與可理解錯誤復原](https://github.com/Bowei1121/B518_205_207_ATE/issues/17) — 已由 M4 merge `f7e24cd265fc173d5d113e7fb122083602f5e5fa` 納入 M7 基準，依賴已解除。

## Local validation

See [M7 local validation evidence](../evidence/multilingual-ticket-07/local-validation.md) for the baseline, M4 ancestry check, real Tk tests, complete-suite result, remote state, and current delivery boundary.
