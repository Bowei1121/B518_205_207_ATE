# M10：完成全 App 翻譯覆蓋與發布資源驗收

## Parent

Part of [規格 Issue #13](https://github.com/Bowei1121/B518_205_207_ATE/issues/13)。依 ADR 0009 及已確認拆票方案實作。

## What to build

交付可發布的英文／繁中 App：全部既有操作路徑沒有漏譯，跨視窗及快速切換保持一致，KVM 與兩語業務結果相同，發布產物包含完整資源。必要修正同票完成，不能只宣告各模組測試通過。

## Acceptance criteria

2026-10-12 使用者改授權：尚未驗項先以source App完成，必要source驗收、全套及審查通過即可合併；正式bundle、目標OS／HMI及實機KVM另待驗，不宣稱完整可發布。以下勾選僅表示本次source範圍，完整發布未完成。

- [x] source資源键／參數／術語完整：English／繁中各322鍵，零catalog錯誤，關鍵裁決／警報／保存文案完整，不擴張固定雙語磁碟契約。
- [x] source全部可達自有視窗／事件／錯誤以共用兩語呈現，已開視窗保留狀態；原生文字與原證據例外明確。完整入口與逐鍵清單見 [source-coverage.md](../evidence/multilingual-ticket-10/source-coverage.md)。
- [x] source跨五窗、連續切換、RUNNING／待確認、其他位置收集、關閉停用／取消／再次關閉通過；真正可見notice、選取／閱讀保留及單次操作磁碟重建。
- [x] source長英文／窄主頁／主要視窗可讀可操作，KVM固定幾何／色帶／標記回歸通過；實際HMI／上位機KVM另待驗。
- [x] 母規格16組適用source部分已於最後整合版本實際重跑並記錄；平台來源／人工決定業務等價、完整保存及清理回歸。案例16正式產物及現場部分未勾選。
- [ ] 正式發布資源收錄、bundle操作及適用目標環境仍待驗；不以source／合成verifier測試代替發布。

最後程式／測試SHA：`079b5191598b39182ef6e7acd3269c3cc3d703a9`；實際全套與審查、source合併及查詢結果見 [local-validation.md](../evidence/multilingual-ticket-10/local-validation.md) 與每日M10摘要。正式發布接續見 [release-validation.md](../evidence/multilingual-ticket-10/release-validation.md)。歷史365tests／317keys不是本次結果。

## Blocked by

- [#18：工程師設定與配置操作換語言不丟失輸入](https://github.com/Bowei1121/B518_205_207_ATE/issues/18)
- [#19：衝突與警報即時翻譯並保留人工決定狀態](https://github.com/Bowei1121/B518_205_207_ATE/issues/19)
- [#20：保存與關閉流程的雙語提示及語言切換協調](https://github.com/Bowei1121/B518_205_207_ATE/issues/20)
- [#21：歷史事件按語言顯示且不改寫舊紀錄](https://github.com/Bowei1121/B518_205_207_ATE/issues/21)
- [#22：App 層雙語事件按自身時間安全清理](https://github.com/Bowei1121/B518_205_207_ATE/issues/22)
