# M3：已支援平台事件與來源錯誤完整接入雙語

## Parent

Part of [規格 Issue #13](https://github.com/Bowei1121/B518_205_207_ATE/issues/13)。依 ADR 0009 及已確認拆票方案實作。

## What to build

操作員監控 Atlas、B482、RS-WMT 及 sample-json 時，來源發現、讀取／解析及平台錯誤的 App 說明可依語言閱讀，磁碟紀錄同筆保存兩語，原始來源內容不翻譯。

## Acceptance criteria

- [x] 已支援平台的 App 事件及錯誤接入共用訊息識別與參數，畫面換語言及 audit／Session 保存一致。
- [x] SN、檔名、路徑、來源時間、來源原文與平台識別保留；不從翻譯文案判斷狀態或補造時間。
- [x] 相同來源案例在兩語下結果、候選、未知來源 FAIL、逾時及事件身分相同。
- [x] 原始解析／系統診斷留在詳細資訊，外層說明翻譯；保存後切換不回寫紀錄。
- [x] 真實暫存來源覆蓋各平台正常、部分資料與讀取錯誤，經共同輪次到 Tk 顯示及磁碟重建驗證，既有解析回歸通過。

## Blocked by

- [#15：共同輪次事件同筆雙語保存與即時重新顯示](https://github.com/Bowei1121/B518_205_207_ATE/issues/15) — 已由 M2 合併提交 `f128d9f963f60d416d0eaf5917fa5eda87408280` 納入 `B518-Log-Solution`，M3 的程式依賴已解除。公司 Gitea 同步仍待公司網路即時確認。

## Current delivery status

M3's five acceptance criteria are covered in [local validation](../evidence/multilingual-ticket-03/local-validation.md). Final validation at `30f8702cd6511c5a698882874306093cbaf5dd26` passed the full Tk-enabled suite (317 tests, 79.404 seconds). Fixed-base Standards review found no documented-standard violations and one non-blocking possible duplication smell; Spec's producer inventory parameter note was corrected and is awaiting document-only recheck. The fixed review base is `c87c7bcefa334b96c420f255e8c1bf99e7a97370`. GitHub directly confirmed the ticket ref at `30f8702cd6511c5a698882874306093cbaf5dd26`; Gitea synchronization is scheduled for Monday per the user, so retain the branch until direct confirmation. No type-check command is configured. This ticket does not claim full App multilingual completion or field-device acceptance.
