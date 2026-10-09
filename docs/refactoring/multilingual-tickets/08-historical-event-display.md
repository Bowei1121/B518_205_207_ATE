# M8：歷史事件按語言顯示且不改寫舊紀錄

## Parent

Part of [規格 Issue #13](https://github.com/Bowei1121/B518_205_207_ATE/issues/13)。依 ADR 0009 及已確認拆票方案實作。

## What to build

現場與開發人員可用選定語言閱讀新舊事件；新版依訊息識別呈現、必要時使用保存英文，舊版只在可靠辨識時翻譯。不明內容保留原文詳細及翻譯外層提示，不改寫硬碟證據。

## Acceptance criteria

- [x] 新雙語紀錄依識別／參數重新呈現；資源更新不回寫保存文字，資源缺少、版本不適用或參數不完整時安全回退保存英文。
- [x] 舊訊息只按有格式依據的穩定 kind、必要欄位及輪次平台標頭辨識；相似自由文字不翻譯，不在線翻譯、不補造值。
- [x] 無法辨識內容以目前語言顯示外層說明，詳細區保留原文／原始紀錄；讀取、切換及重開不改事件檔。
- [x] 既有事件與歷史列表即時按目前語言重顯示，保留穩定選取、順序及操作結果，不重跑事件或保存。
- [x] 輪次、平台、App 診斷及混合新舊紀錄通過全新磁碟讀取器與真正 Tk 讀取操作；完整含 Tk 套件通過。

## Delivery status (2026-10-09)

M3 (#16) and M4 (#17) were verified in the fixed M8 baseline by Git ancestry and their committed local acceptance records; they are not outstanding blockers. The final M8 code/test commit is `06c65592958970f38aa9330fb218ab2da66a3581`; all five acceptance criteria, the 350-test Tk-enabled suite, and fixed-baseline Standards/Spec reviews have passed. Evidence and separate GitHub/Gitea status are recorded in [M8 local validation](../evidence/multilingual-ticket-08/local-validation.md). GitHub main merge and internal Gitea synchronization are recorded separately.
