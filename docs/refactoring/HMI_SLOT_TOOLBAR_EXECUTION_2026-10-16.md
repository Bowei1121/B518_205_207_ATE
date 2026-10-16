# ST1–ST8 執行紀錄 — 2026-10-16

## 基準與工作樹

- 使用者授權整批依序實作 ST1→ST8、逐票雙語桌面驗收、最後主線合併及 Gitea／GitHub 同步；後續明確要求先不處理 GitHub issue 更新，因此本次 continuation 不寫入、不關閉 #68–#76。
- 已讀 implement-spec、TDD、AGENTS.md、領域詞彙、ADR 0001–0009、完整 Spec、本機八票及 GitHub 正文、留言、狀態、原生依賴。
- 查核時兩遠端 `B518-Log-Solution` 均為 `612c6d08e74c2e6fd2973114ccc9c5d32195a5ad`，包含 `1bdb163` macOS 幾何與建置回歸修正。
- 整合分支 `codex/hmi-slot-toolbar-implementation-20261016`；工作樹 `/private/tmp/B518-st-integration`。最終審查固定基準為上述 SHA。
- 原工作樹仍在 `65cd07a`，兩個未提交程式／測試檔及三個未追蹤證據檔保留原樣。開始前 SHA-256 清單存於 `/private/tmp/B518-st-original-preservation.json`，最終需讀回比對。
- 沙盒內網路／憑證查核失敗；提升權限後確認兩遠端及 gh 授權正常，非永久 API 故障。

## 票況

| 票 | Issue | 執行狀態 | 實作分支 |
| --- | --- | --- | --- |
| ST1 | #69 | 完成；已整合及遠端同步 | codex/st1-slot-scroll (`d3ed365`) / integration (`299a5c2`) |
| ST2 | #70 | 完成；已整合及遠端同步 | codex/st2-toolbar-badges / integration (`cf7fead`) |
| ST3 | #71 | 完成；已整合及遠端同步 | codex/st3-main-button-hints / integration (`fa3d786`) |
| ST4 | #72 | 完成；已整合及遠端同步 | codex/st4-settings-recovery-hints / integration (`c8eb613`) |
| ST5 | #73 | 完成；已整合及遠端同步 | codex/st5-adjudication-alert-close-hints / integration (`f07b0b8`) |
| ST6 | #74 | 完成；已整合及遠端同步 | codex/st6-history-diagnostics-feedback / integration (`77d15fb`) |
| ST7 | #75 | 程式與真實外觀驗收完成；最終回放曾有 AppKit 啟動失敗，修復前症狀另有重現嘗試未能重現 | feature/st7 / integration (`bb35d45`, evidence `0d927ae`) |
| ST8 | #76 | 整合驗收與全故事／按鈕覆蓋完成；Issue 未更新 | codex/st8-integrated-acceptance / integration (`9ba8357`, `215149d`) |

開始查核時 #68–#76 全部 OPEN、無留言、無 assignee；原生依賴符合本機票總覽。#68 原生子議題為 #69–#76。ST1 已於提交 `299a5c2` 整合驗收後關閉；ST2 #70 已確認無未完成前置並開始認領。

> 以上是開始查核時的遠端 Issue 狀態歷史，不代表本次續作後仍相同。本次依使用者最新指示，GitHub Issues 維持未觸碰；最終狀態需由 GitHub 讀回確認，不能從此處推論。

## 驗收邊界

真正 App／Tk 公開操作及可見行為是已確認 seam。每票先紅後綠，附本次真正中英畫面與操作結果；不以舊證據、style lookup 或未提交暫稿代表完成。試行配色不代表使用者已接受最終樣式。工廠及未測平台另列。

## 最終整合審查與同步

- 最終審查固定基準：`e245f6cff9bb4c45954c06208c5adc34d93b5e7e`；標準軸沒有規範違反或額外 code smell。規格軸已核對八票與整合證據，並要求補足 ST7 修復前真實畫面的直接檢查。
- ST7 修復前版 `77d15fb` 真 App 外觀切換已另行實測，結果未能重現回報症狀；三張原生視窗截圖與記錄已保存於 ST7 證據目錄，根因仍未定。ST7 的既有最後 Tk/AppKit replay 仍記為未通過，不以手動外觀畫面冒充該重跑成功。
- 淺藍 hover 與藍色 focus：使用者看過真 App 英／中文對照後明確指示保留。
- ST8 整合驗收完成；工廠電腦、產線 KVM／壓縮識別容差、工廠資料流程及未涵蓋 macOS／縮放留作現場驗收。未執行無關的數小時歷史效能測試。
- 原工作樹 `/Users/tsengbowei/Desktop/公司資料/專案/FQ III/2026/B518/專案名稱/3. 程式/0. PC/B518 Log Solution` 仍有未提交主程式／UI 測試與未追蹤 input-probe／window-bounds 暫稿；本次不覆寫、不清理。五個開始前保存的 SHA-256 全數相符。
- 最終整合分支以正常 fast-forward 從遠端主線 `612c6d0` 前進至 `e9cfa501b2e072b604c85a7318a24ab774572605`；主線受影響驗收 `PYTHONPATH=src:tests python3 -m unittest test_language_catalog test_kvm_display_contract` 為 15 tests OK，四個 Python 檔 `py_compile`、`git diff --check` 通過。
- 已推送主線至 Gitea 與 GitHub，兩端 `B518-Log-Solution` 讀回同一 SHA `e9cfa501b2e072b604c85a7318a24ab774572605`。此紀錄尚有本次最終對帳提交，完成後會再 fast-forward 並讀回兩端一致性。

## ST1 #69 — Slot 十列與捲軸

- 功能分支：`codex/st1-slot-scroll`；從 `612c6d0` 建立獨立 `/private/tmp/B518-st1`，實作期間 fast-forward 合入整合文件 `e245f6c`，原工作樹不變。
- TDD：真正 App/Tk 的容量 1 場景先重現捲軸欄位消失，再修正為固定保留／依實際可視內容啟用；最多十個完整列、保留字體與主要操作、容量下降修正閱讀位置。
- 真正繁中／英文共 32 個畫面場景：1440×900 與原生支援 1650×1050 各容量 1／10／11／20 × 大高／650 高 × 兩語。足高容量 10／11／20 完整十列；650 高減為 5／4／4 列，真正捲軸箭頭到末端後末列完整。
- 真正顯示模式切換在 `finally` 還原並讀回 1440×900；沒有變更系統深淺外觀。
- 受影響回歸 12 項通過：macOS 固定視窗、容量編輯、原字體／列幾何及 KVM 契約；容量 20→1 與捲軸停用拖動亦通過。
- 證據與完整重現命令：`docs/refactoring/evidence/st1-20261016/README.md`、兩份矩陣 JSON、兩語原生截圖與測試結果。
- 工廠顯示器、不同縮放及上位機 KVM 壓縮辨識留作現場驗收；未宣稱完成。待功能分支提交／雙遠端推送及 merger 整合成功後由主代理更新 #69 驗收與狀態。
- ST1 merger 整合提交：`299a5c25f30984742acf267ade825b90a0dc68cf`。整合後 7 項 KVM 契約與 5 項 Aqua UI 幾何回歸共 12 項全通過；使用 macOS 桌面 wrapper／Python 3.8.10、Tcl/Tk 8.6。sandbox 內先前兩種執行都在測試本體前 exit 134（沒有 Tcl traceback），使用者授權的桌面提升權限執行後通過。Gitea／GitHub integration ref 均讀回 `299a5c25f30984742acf267ade825b90a0dc68cf`。

## #75 最終來源補驗

- 使用者要求驗收 #75。兩端主線讀回 `6fb5b75`，從該提交建立獨立 `codex/st7-final-acceptance-20261016`；原工作樹暫稿不變。
- 本次 Framework Python 3.8.10／Tk/Aqua、macOS 15.7.9 x86_64 真正測試 11/11 通過：Dark 外層淺色 1/1、恢復與關閉回歸 8/8、同視窗 Dark→Light→Dark 1/1、Light 下新程序獨立開窗 1/1。先前建窗前 AppKit abort 本次未發生，不宣稱其原因已修復。
- 新的 12 張外觀切換真畫面涵蓋兩分頁與中英文；系統原 Dark 已由使用者還原並讀回。語言／KVM 15/15、Python 3.8 編譯與 diff check 通過。
- 使用者補充原變色發生在打包 `.app`。目前等待該 bundle 路徑／版本以重現。Light 獨立開窗已補驗通過。未調整第 1／6 項原驗收範圍，#75 不能列全部通過。完整新證據與條件對照見 `B518 Log Solution/docs/refactoring/evidence/st7-final-20261016/README.md`。
