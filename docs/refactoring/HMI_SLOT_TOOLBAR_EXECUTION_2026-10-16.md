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
| ST1 | #69 | 完成；已整合及遠端同步 | codex/st1-slot-scroll (`d3ed365`) / integration (`299a5c2`) |
| ST2 | #70 | 已認領；執行中 | codex/st2-toolbar-badges |
| ST3 | #71 | 未開始 | 待建立 |
| ST4 | #72 | 等 ST3 | 待建立 |
| ST5 | #73 | 等 ST3 | 待建立 |
| ST6 | #74 | 等 ST3 | 待建立 |
| ST7 | #75 | 未開始 | 待建立 |
| ST8 | #76 | 等 ST1–ST7 | 待建立 |

開始查核時 #68–#76 全部 OPEN、無留言、無 assignee；原生依賴符合本機票總覽。#68 原生子議題為 #69–#76。ST1 已於提交 `299a5c2` 整合驗收後關閉；ST2 #70 已確認無未完成前置並開始認領。

## 驗收邊界

真正 App／Tk 公開操作及可見行為是已確認 seam。每票先紅後綠，附本次真正中英畫面與操作結果；不以舊證據、style lookup 或未提交暫稿代表完成。試行配色不代表使用者已接受最終樣式。工廠及未測平台另列。

## ST1 #69 — Slot 十列與捲軸

- 功能分支：`codex/st1-slot-scroll`；從 `612c6d0` 建立獨立 `/private/tmp/B518-st1`，實作期間 fast-forward 合入整合文件 `e245f6c`，原工作樹不變。
- TDD：真正 App/Tk 的容量 1 場景先重現捲軸欄位消失，再修正為固定保留／依實際可視內容啟用；最多十個完整列、保留字體與主要操作、容量下降修正閱讀位置。
- 真正繁中／英文共 32 個畫面場景：1440×900 與原生支援 1650×1050 各容量 1／10／11／20 × 大高／650 高 × 兩語。足高容量 10／11／20 完整十列；650 高減為 5／4／4 列，真正捲軸箭頭到末端後末列完整。
- 真正顯示模式切換在 `finally` 還原並讀回 1440×900；沒有變更系統深淺外觀。
- 受影響回歸 12 項通過：macOS 固定視窗、容量編輯、原字體／列幾何及 KVM 契約；容量 20→1 與捲軸停用拖動亦通過。
- 證據與完整重現命令：`docs/refactoring/evidence/st1-20261016/README.md`、兩份矩陣 JSON、兩語原生截圖與測試結果。
- 工廠顯示器、不同縮放及上位機 KVM 壓縮辨識留作現場驗收；未宣稱完成。待功能分支提交／雙遠端推送及 merger 整合成功後由主代理更新 #69 驗收與狀態。
- ST1 merger 整合提交：`299a5c25f30984742acf267ade825b90a0dc68cf`。整合後 7 項 KVM 契約與 5 項 Aqua UI 幾何回歸共 12 項全通過；使用 macOS 桌面 wrapper／Python 3.8.10、Tcl/Tk 8.6。sandbox 內先前兩種執行都在測試本體前 exit 134（沒有 Tcl traceback），使用者授權的桌面提升權限執行後通過。Gitea／GitHub integration ref 均讀回 `299a5c25f30984742acf267ade825b90a0dc68cf`。
