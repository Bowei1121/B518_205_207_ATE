## Parent

Part of #28 — https://github.com/Bowei1121/B518_205_207_ATE/issues/28

## What to build

衝突、輪次警報與關閉進度視窗依共同語言契約呈現，保持人工操作與保存效果；待確認時可切語，關閉保存期間仍拒絕切語。

## Acceptance criteria

- [ ] 衝突及輪次警報接入通知，關閉進度呈現使用同一目前語言依據；不引入關閉期間切語或重試繞過政策。
- [ ] 維持候選集合與目前選取、詳細閱讀、兩區對照、差異樣式及視窗實例；不重新解析候選或裁決。
- [ ] 更新不自動確認警報、不採用候選、不改結果或 KVM 契約；其他位置收集與待確認流程保持。
- [ ] 開啟、隱藏／再顯示、關閉／重開均遵循登記與解除，不累積接收者；保留原焦點及必要操作效果。
- [ ] 故意讓已遷移的操作視窗更新失敗，其他接收者保持正常，人工處理可用；透過主畫面提示重試，不重開視窗。
- [ ] 語言更新不改未保存追蹤、保存重試、關閉 generation 或完整保存才關閉；關閉進度文字按原政策呈現。
- [ ] 真正 Tk 與公開輪次入口驗證監控中／待確認切語、候選與警報保持、失敗恢復、關閉期間禁切語與保存磁碟結果。
- [ ] 移除本票已遷移視窗的重複手動刷新，保留既有輪次與保存測試，記錄實際結果與限制。

## Blocked by

- #29 — 語言通知、失敗提示與重試

## Current implementation status — 2026-10-12

The L3 implementation is on `LanguageRefresh/ticket-03` from fixed review baseline `93ac9e47903649c4098c1423c2496f86ac685a03`. Focused real-Tk conflict/alarm tests pass, but this ticket is **not complete**: the required full suite did not finish, the L1 modal-notice lifecycle test also timed out when run from L1's recorded tested SHA `1a2fb138dcf7ede875d8a3dcb033e5c6da8468fb`, and the Standards/Spec evidence and full acceptance matrix are recorded in [L3 local validation](../evidence/language-refresh-ticket-03/local-validation.md). The test's stack is blocked in the pre-existing notice's `wait_window`; no L1 dependency fix is included in L3.

Do not merge or delete this branch until the L1 dependency/full-suite validation blocker is resolved and all remaining L3 evidence is complete. Parent first-item acceptance remains partial; L4 is still required.
