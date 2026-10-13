## Parent

Part of #28 — https://github.com/Bowei1121/B518_205_207_ATE/issues/28

## What to build

App 事件清理改用同一原因契約，清理結果摘要可用繁中／英文查閱並保留原始診斷；到期、安全及未保存保護維持原行為。

## Acceptance criteria

- [x] App 事件清理成功、跳過、失敗及狀態原因接入 C1 契約，涵蓋格式／序號／時間／管理路徑／待保存原因。
- [x] 與既有清理執行同筆保存原因識別、參數、雙語與診斷，既有 deleted／skipped／failed 計數與序號資訊保持一致。
- [x] 從事件自身時間起算、沿用全域期限；pending、保存或耐久性故障、未知／損壞資料保持保護，不虛構輪次。
- [x] 保留退休序號、pin 住管理路徑、符號連結與路徑替換防護、原子替換及目錄 fsync；表述改造不改任何刪除資格。
- [x] 不另建 scheduler／journal，沿用既有背景清理與摘要保存，故障重試保留事件與清理進度。
- [ ] 真實 App journal → 清理 → 原因摘要 → 全新讀取器 → 最終版本真正 Tk 畫面查閱：磁碟與全新讀取器證據已完成；本次最終完整套件在 Tk 建窗時被 macOS AppKit 中止，故最終版本可見畫面驗收待重跑。
- [x] 驗證尚未到期、待補存、損壞、越界、符號連結、rename後fsync失敗與重試；原刪除／保留及序號解釋結果不變。
- [x] 舊摘要不改寫，輪次尚未遷移原因仍相容；相關現有測試保持並記錄實際結果。

## Blocked by

- #33 — 新舊清理摘要相容讀取與原因呈現（已由固定基準中的 C1 完成；本票證據見 [C3 驗收紀錄](../evidence/retention-reason-ticket-03/local-validation.md)）

## Delivery status

正式 producer 與保存／恢復實作、55 項非 Tk 聚焦測試已完成；Spec 複審發現的期限延長後 skipped 恢復錯誤已在 `4cb353f` 修正並有回歸測試。固定基準 Standards／Spec 複審已完成，沒有未解阻擋；Standards 的命名建議屬非阻擋。本票仍為部分完成。必要完整含 Tk 套件已於 2026-10-13 12:00 在 `tkinter.Tk()` 建窗階段遭 macOS AppKit `NSInternalInconsistencyException` 中止（exit 134），同一 runtime 的兩個直接相關 Tk 個測也在建窗前以相同錯誤中止。不得合併或清理票分支；請在可正常建立 Tk 主視窗的 macOS 桌面重新執行完整驗收，證據與最小步驟見 [C3 驗收紀錄](../evidence/retention-reason-ticket-03/local-validation.md)。
