# 2026-08-22 專案摘要

## BT Log-only Demo 現況

- BT 專用開發位於 `BT-Codex` branch 與獨立 worktree `Mac mini-BT-Codex`，避免影響既有 DFU／FCT Demo。
- 已完成純 Log 的 BT 無 SN Demo：不操作 BT HMI、不依賴 Arduino USB CDC，僅監聽 `TestData/YYYY-MM-DD/PASSED|FAILED` 的 CSV。
- Start All／Start 1～4 在此模式只決定監聽的 Thread；人員仍需操作實體 BT 設備開始測試。
- 第一個符合「啟動快照＋30 秒容差」的新 CSV 會鎖定本輪 14 位數批次時間戳，後續只收相同時間戳的 Thread0～3。
- CSV 完整後可立即更新對應 slot；5 秒僅用於確認已收齊檔案後的批次穩定。
- 空白 SN、FAILED 的特殊輸出目前依既定決策顯示 `NOTEST`；批次衝突或同 Thread 重複由人工覆核。
- 規格文件位於 `Manual/BT_LOG_ONLY_DEMO_SPEC.md`；主要實作 commit 為 `c38bb48`，已推送 Gitea 與 GitHub 的 `BT-Codex` branch。

## 本日新增現場資料

- 收到 Thread0～3 的 PASSED、空白 SN FAILED 個別 CSV。
- 收到 thread1～4 CaseInfo 即時文字 Log。
- 收到當日生產綜合 CSV，待確認其適合作為稽核／備援資料，而非主要即時結果來源。

