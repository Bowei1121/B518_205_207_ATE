# M3：已支援平台事件與來源錯誤完整接入雙語

## Parent

Part of [規格 Issue #13](https://github.com/Bowei1121/B518_205_207_ATE/issues/13)。依 ADR 0009 及已確認拆票方案實作。

## What to build

操作員監控 Atlas、B482、RS-WMT 及 sample-json 時，來源發現、讀取／解析及平台錯誤的 App 說明可依語言閱讀，磁碟紀錄同筆保存兩語，原始來源內容不翻譯。

## Acceptance criteria

- [ ] 已支援平台的 App 事件及錯誤接入共用訊息識別與參數，畫面換語言及 audit／Session 保存一致。
- [ ] SN、檔名、路徑、來源時間、來源原文與平台識別保留；不從翻譯文案判斷狀態或補造時間。
- [ ] 相同來源案例在兩語下結果、候選、未知來源 FAIL、逾時及事件身分相同。
- [ ] 原始解析／系統診斷留在詳細資訊，外層說明翻譯；保存後切換不回寫紀錄。
- [ ] 真實暫存來源覆蓋各平台正常、部分資料與讀取錯誤，經共同輪次到 Tk 顯示及磁碟重建驗證，既有解析回歸通過。

## Blocked by

- [#15：共同輪次事件同筆雙語保存與即時重新顯示](https://github.com/Bowei1121/B518_205_207_ATE/issues/15) — 已由 M2 合併提交 `f128d9f963f60d416d0eaf5917fa5eda87408280` 納入 `B518-Log-Solution`，M3 的程式依賴已解除。公司 Gitea 同步仍待公司網路即時確認。

## Current delivery status

M3 is in progress on `Multilingual/ticket-03`. Program/test commits through `65dcd18` and evidence commits through `c9a348d` are on the branch; a direct GitHub query after `c9a348d1f4bc7a72fe0a7015c17af7e7dfb6ae62` confirmed that ref. The full Tk suite passed 314 tests, and real Tk App tests exercise Atlas, B482, RS-WMT and sample-json source diagnostics through Session/audit reconstruction and bilingual refresh. Fixed-base Standards review found no hard violations; Spec review confirms diagnostic fixes but leaves criteria 1, 3 and 5 partial for incomplete producer coverage and the cross-platform normal/partial/candidate/unknown-source/timeout matrix. Criterion 2 is supported by distributed source and integration tests; criterion 4 passes for exercised diagnostic paths. Company Gitea synchronization is scheduled for Monday per the user. Acceptance remains partial; do not merge or clean the branch. See [local validation](../evidence/multilingual-ticket-03/local-validation.md).
