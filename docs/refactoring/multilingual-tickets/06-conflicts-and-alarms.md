# M6：衝突與警報即時翻譯並保留人工決定狀態

## Parent

Part of [規格 Issue #13](https://github.com/Bowei1121/B518_205_207_ATE/issues/13)。依 ADR 0009 及已確認拆票方案實作。

## What to build

操作員可在待確認時直接換語言，所有已開衝突及警報視窗同步顯示所選語言；保留候選、選取、原證據與尚未確認的警報，人工決定的雙語紀錄仍是同一次操作。

## Acceptance criteria

- [x] 衝突選單、原／新對照、詳細證據標籤、裁決按鈕及整輪警報使用共用兩語資源，不翻譯原證據值。
- [x] 已開視窗即時更新，不關閉重開、不改選取／候選快照、不自動確認警報或裁決。
- [x] 多候選、刷新、移除與空狀態在連續切換下資訊一致；若新精簡／詳細分區已合併，全部標籤與提示均涵蓋。
- [x] 保留原／採用新及警報確認各寫出同一筆雙語操作，不改未知來源 FAIL 或禁止採用政策。
- [x] 真正 Tk 從受控衝突與警報到切換、裁決及磁碟重建驗證；不遮住固定 KVM 標記、不阻塞其他位置收集。

Local acceptance and GitHub merge completed 2026-10-09. See [M6 local validation](../evidence/multilingual-ticket-06/local-validation.md) for commands, test results, fixed review baseline, merge SHA, and scope boundaries. Company Gitea synchronization remains deferred to Monday; retain the ticket branches until direct synchronization is confirmed.

## Blocked by

- [#15：共同輪次事件同筆雙語保存與即時重新顯示](https://github.com/Bowei1121/B518_205_207_ATE/issues/15)
