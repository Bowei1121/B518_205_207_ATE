# M10：完成全 App 翻譯覆蓋與發布資源驗收

## Parent

Part of [規格 Issue #13](https://github.com/Bowei1121/B518_205_207_ATE/issues/13)。依 ADR 0009 及已確認拆票方案實作。

## What to build

交付可發布的英文／繁中 App：全部既有操作路徑沒有漏譯，跨視窗及快速切換保持一致，KVM 與兩語業務結果相同，發布產物包含完整資源。必要修正同票完成，不能只宣告各模組測試通過。

## Acceptance criteria

- [x] 全部資源鍵、參數與術語完整，英文基準及裁決／警報／保存失敗等關鍵文案不能靠回退；未來語言不擴張固定雙語紀錄。Catalog 兩語各 317 keys、參數格式一致、`validate_translations()` 零錯誤；見 [M10 驗收證據](../evidence/multilingual-ticket-10/local-validation.md)。
- [ ] **部分：**自有視窗、事件及錯誤說明須全部在兩語下完整，並明確標示原生系統文字與原始證據例外。M10 真 Tk 案例涵蓋設定／App 診斷／歷史三窗的標題、事件列與詳細文字刷新及狀態保留；衝突、警報、保存／關閉另有前票證據。仍缺全部可達入口的完整盤點與跨視窗整合驗收；正式 bundle 尚待驗。
- [ ] **部分：**設定、App 診斷與歷史視窗同時開啟的連續切換已由真 Tk／磁碟案例驗證；衝突、警報、監控與關閉取消各有真 Tk 全套回歸。仍缺跨全部可共存視窗與發布產物的整合驗收，不勾選完成。
- [ ] **部分：**source Tk 長英文及主要畫面測試、KVM 固定幾何／標記契約測試通過；目標 HMI／實機 KVM 操作及目標解析度驗收仍待完成，故不勾選整項完成。
- [ ] **部分：**全部 16 組案例須有本次整合版本證據。矩陣已建立，source 可執行案例及相同來源／人工操作回歸已重跑；第 16 組 bundle／目標環境未驗，部分現場設備情境亦待安排，故不勾選完整。見 [驗收矩陣](../evidence/multilingual-ticket-10/local-validation.md)。
- [ ] 發布資源完整收錄，source App 與正式 bundle／目標環境證據分開；環境不足項明記待驗，不虛報通過或完整可發布。

目前 source 程式／測試 SHA：`e8a309fd1fac186832c5825c803e4299932f206b`；完整含 Tk 套件 365 tests 通過。正式 bundle 尚未建置：本次 Intel macOS 15.7.9／x86_64 主機及 Python/Tk 不符合 README 的任何建置矩陣；細節與後續步驟見 [release-validation.md](../evidence/multilingual-ticket-10/release-validation.md)。固定基準 Standards／Spec 複審已確認文件勾選、事件文字斷言與 SHA 問題修正；bundle 與必要目標環境驗收未完成前，M10 不得合併或宣告完成。

## Blocked by

- [#18：工程師設定與配置操作換語言不丟失輸入](https://github.com/Bowei1121/B518_205_207_ATE/issues/18)
- [#19：衝突與警報即時翻譯並保留人工決定狀態](https://github.com/Bowei1121/B518_205_207_ATE/issues/19)
- [#20：保存與關閉流程的雙語提示及語言切換協調](https://github.com/Bowei1121/B518_205_207_ATE/issues/20)
- [#21：歷史事件按語言顯示且不改寫舊紀錄](https://github.com/Bowei1121/B518_205_207_ATE/issues/21)
- [#22：App 層雙語事件按自身時間安全清理](https://github.com/Bowei1121/B518_205_207_ATE/issues/22)
