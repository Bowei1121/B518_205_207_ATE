## Parent

Part of #28 — https://github.com/Bowei1121/B518_205_207_ATE/issues/28

## What to build

衝突、輪次警報與關閉進度視窗依共同語言契約呈現，保持人工操作與保存效果；待確認時可切語，關閉保存期間仍拒絕切語。

## Acceptance criteria

- [x] 衝突及輪次警報接入通知，關閉進度呈現使用同一目前語言依據；不引入關閉期間切語或重試繞過政策。
- [x] 維持候選集合與目前選取、詳細閱讀、兩區對照、差異樣式及視窗實例；不重新解析候選或裁決。
- [x] 更新不自動確認警報、不採用候選、不改結果或 KVM 契約；其他位置收集與待確認流程保持。
- [x] 開啟、隱藏／再顯示、關閉／重開均遵循登記與解除，不累積接收者；保留原焦點及必要操作效果。
- [x] 故意讓已遷移的操作視窗更新失敗，其他接收者保持正常，人工處理可用；透過主畫面提示重試，不重開視窗。
- [x] 語言更新不改未保存追蹤、保存重試、關閉 generation 或完整保存才關閉；關閉進度文字按原政策呈現。
- [x] 真正 Tk 與公開輪次入口驗證監控中／待確認切語、候選與警報保持、失敗恢復、關閉期間禁切語與保存磁碟結果。
- [x] 移除本票已遷移視窗的重複手動刷新，保留既有輪次與保存測試，記錄實際結果與限制。

## Blocked by

- #29 — 語言通知、失敗提示與重試

## Current implementation status — 2026-10-12

L3 implementation and all eight acceptance items pass at code/test SHA `04c2b0d04f1d6e634b57628b58306abdcd43bcdb`, fixed review baseline `93ac9e47903649c4098c1423c2496f86ac685a03`. Final desktop Python 3.11.7/Tk 8.6 suite: **383 tests, 160.014 s, OK**. Wrapped raw reading position, candidate-list top/sash, simultaneous refresh failure/partial recovery, WM lifecycle and close-time retry controls have final-version evidence. Standards and Spec code/test reviews have no unresolved findings; final documentation review passed and merge/mainline verification are recorded in [L3 local validation](../evidence/language-refresh-ticket-03/local-validation.md).

Earlier timeout/abort and intermediate failed-suite results are retained there with their fixes or limitations; no L1 notice product repair is mixed into L3. Parent-wide first-item acceptance remains L4; cleanup-reason C1–C4 and bundle/field acceptance are separate.

Merged into `B518-Log-Solution` at `6ecef64235626ee9fc289462ebdf5323b467ceb3`; mainline desktop suite passed 383 tests / 148.658 s. GitHub and Gitea directly confirmed that merge SHA before the final documentation-only commit. Source/bundle and physical-menu limitations remain as recorded; L4 is not declared complete.
