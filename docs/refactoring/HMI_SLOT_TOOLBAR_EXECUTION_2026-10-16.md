# ST1–ST8 執行紀錄 — 2026-10-16

## 基準與工作樹

- 使用者授權整批依序實作 ST1→ST8、逐票雙語桌面驗收、GitHub 更新與結案、最後主線合併及 Gitea／GitHub 同步。
- 已讀 implement-spec、TDD、AGENTS.md、領域詞彙、ADR 0001–0009、完整 Spec、本機八票及 GitHub 正文、留言、狀態、原生依賴。
- 查核時兩遠端 `B518-Log-Solution` 均為 `612c6d08e74c2e6fd2973114ccc9c5d32195a5ad`，包含 `1bdb163` macOS 幾何與建置回歸修正。
- 整合分支 `codex/hmi-slot-toolbar-implementation-20261016`；工作樹 `/private/tmp/B518-st-integration`。最終審查固定基準為上述 SHA。
- 原工作樹仍在 `65cd07a`，兩個未提交程式／測試檔及三個未追蹤證據檔保留原樣。開始前 SHA-256 清單存於 `/private/tmp/B518-st-original-preservation.json`，最終需讀回比對。
- 沙盒內網路／憑證查核失敗；提升權限後確認兩遠端及 gh 授權正常，非永久 API 故障。

## 票況

| 票 | Issue | 執行狀態 | 實作分支 |
| --- | --- | --- | --- |
| ST1 | #69 | 已認領；TDD 實作中 | codex/st1-slot-scroll |
| ST2 | #70 | 未開始 | 待建立 |
| ST3 | #71 | 未開始 | 待建立 |
| ST4 | #72 | 等 ST3 | 待建立 |
| ST5 | #73 | 等 ST3 | 待建立 |
| ST6 | #74 | 等 ST3 | 待建立 |
| ST7 | #75 | 未開始 | 待建立 |
| ST8 | #76 | 等 ST1–ST7 | 待建立 |

開始查核時 #68–#76 全部 OPEN、無留言、無 assignee；原生依賴符合本機票總覽。#68 原生子議題為 #69–#76。ST1 已指派 Bowei1121 並發布開始留言。

## 驗收邊界

真正 App／Tk 公開操作及可見行為是已確認 seam。每票先紅後綠，附本次真正中英畫面與操作結果；不以舊證據、style lookup 或未提交暫稿代表完成。試行配色不代表使用者已接受最終樣式。工廠及未測平台另列。
