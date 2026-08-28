# 2026-08-28 專案對話摘要

## 摘要範圍

- 這是 2026-08-28 換日後第一次對話建立的延續摘要。
- 由於當前對話上下文未包含全部過往對話原文，以工作區現有的 2026-08-22 摘要與 Git 記錄為依據，不推測未留存的討論。

## 前次可追溯決議與進度

- BT Log-only Demo 位於 `BT-Codex` branch 與獨立 worktree，以避免影響既有 DFU／FCT Demo。
- BT 無 SN Demo 僅監聽 `TestData/YYYY-MM-DD/PASSED|FAILED` CSV，不操作 BT HMI，也不依賴 Arduino USB CDC。
- Start All／Start 1～4 只決定監聽 Thread；實體 BT 設備仍由人員啟動測試。
- 當輪批次會以第一份符合「啟動快照＋30 秒容差」的新 CSV 鎖定 14 位數時間戳，後續只接收同時間戳的 Thread0～3。
- CSV 完整後可立即更新 slot；5 秒穩定期僅用於確認檔案收齊。
- 空白 SN 與 FAILED 的既定特殊輸出為 `NOTEST`；批次衝突或同 Thread 重複需人工覆核。
- 記錄顯示主要實作 commit 為 `c38bb48`，當時已推送 Gitea 與 GitHub 的 `BT-Codex` branch。

## 待續追蹤

- 已收到 Thread0～3 的 PASSED／空白 SN FAILED 個別 CSV、thread1～4 CaseInfo 即時文字 Log，以及當日生產綜合 CSV。
- 當日生產綜合 CSV 是否只作為稽核／備援資料，而非即時結果主來源，仍待確認。

## 2026-08-28 新議題

- 新增研究任務：評估 JetKVM 是否可作為「測試電腦 USB CDC ↔ 上位機 TCP/IP」網關。
- 後續將以官方 JetKVM 原始碼、官方文件與底層 USB gadget 實作完成可行性、改造範圍、風險與 PoC 方案。
