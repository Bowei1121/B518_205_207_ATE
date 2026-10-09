# M9：App 層雙語事件按自身時間安全清理

## Parent

Part of [規格 Issue #13](https://github.com/Bowei1121/B518_205_207_ATE/issues/13)。依 ADR 0009 及已確認拆票方案實作。

## What to build

工程師設定的全域保存天數同樣管理無輪次 App 事件，依原事件時間清理、保護待補存資料，並可查閱雙語維護摘要。沿用既有背景清理協調入口，不再新增獨立排程。

## Acceptance criteria

- [x] 使用事件原時間與帶時區一致比較，不虛構封存時間；輪次仍按可信封存時間計算。
- [x] 全域期限修改在下次清理生效，期限前、恰到及之後有注入時間證據。
- [x] 只清理可信、完整保存、已到期的 App 事件；待補存、故障、未知及損壞資料保留。
- [x] 同一保存段含未到期或受保護事件時不因其他到期內容誤刪整段，不碰配置、來源、人工匯出等外部資料。
- [x] 與既有清理排程、保存及關閉協調，不重疊；摘要可用兩語查閱，清理失敗可安全重試。
- [x] 真實暫存磁碟、注入時鐘與 App 操作驗證設定變更、邊界、競爭、故障及摘要，不以純 helper 測試代替行為。

## Direct dependency verification

- M4 / #17 is an ancestor of the fixed M9 baseline. Its bilingual App event, ordered persistence, retry, disk-reader and close-protection contracts are present in code and committed validation evidence.
- Existing round-retention Ticket 07 / #8 is also an ancestor. M9 reuses its trusted archive timestamps, cleanup coordination, durable summaries, protection checks and close coordination.
- Exact ancestry checks, implementation details and acceptance evidence are in [M9 local validation](../evidence/multilingual-ticket-09/local-validation.md).

M9 implementation and six acceptance criteria are verified in the linked evidence. Fixed-baseline Standards/Spec review is complete with no unresolved blockers. M9 is merged into the local and GitHub `B518-Log-Solution`; Gitea synchronization and ticket-branch cleanup remain pending until the Monday intranet sync is directly verified. This does not complete M10 bundle or release verification.
