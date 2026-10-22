# 專案摘要 — 2026-10-22

## 今日接續

- 延續 HMI 子票，實作 GitHub Issue [#112：HC7 新版本機幾何量測與 KVM 模板交接](https://github.com/Bowei1121/B518_205_207_ATE/issues/112)，父規格 [#105](https://github.com/Bowei1121/B518_205_207_ATE/issues/105)。
- HC1–HC6 已關閉；HC3/HC4 整合基底為 `d03c7b6bf56e25cae4ceea58814d78a467bb112c`。HC3 幾何來源 commit `59fc669d43022bcf9088e11085f9a6111c92b1bc` 的 source tree 與此基底不同，因 HC4 更新提醒邏輯；僅重用固定幾何，並由 PR #119 同 tree 的真 Tk bounds 測試補充驗證。
- 橋接 repo `Bowei1121/B518_KVM_Log` 的 `main` HEAD `736bb8b4df5ce87beaf140416f3aea027d3aa1d7` 宣告 contract 1.3。App 的 STALLED 和 TIMEOUT 同為 `#ff9900`；橋接 reader 對該顏色回傳 TIMEOUT，會把 STALLED 靜默分類為 TIMEOUT，不是 UNKNOWN/fail-closed。這是狀態語意合併；本票不改橋接程式。

## PR #120 審查修正

- reviewer 發現一般 timer ROI 原本落在空白，且 normal timer widget 寬度錯列為 44。按 HC3 圖片重算：四張 752×1612、無 titlebar 的標準圖使用 raster ROI `[600,1330,136,40]`，capacity-10 字形 bbox 為 `[654,1339,730,1359]`；長 timer 原圖 752×1668 含 56px titlebar，原圖 ROI `[600,1386,136,40]`，移除 titlebar 後正規化為 `[600,1330,136,40]`。timer widget 實測為 `[300,693,68,20]` Tk units。
- 修正 machine-readable 相容性描述為「幾何/色樣本相容，STALLED 語意被 alias 成 TIMEOUT」；把 HC3 source-tree 與 HC7 base tree 相同宣告修正為 false。
- HC7 新版雙語、雙 scaling、容量 1/10/11/20 的完整原生布局矩陣仍缺。舊 LS7 scaling 量測不算 HC7 新布局驗收。本地 Tk/Aqua 重跑仍 exit 134，沒有 unittest 輸出；依審查結果，HC7 本機驗收保留 3/6，PR #120 維持 draft 且不合併。

## HC7 交付與限制

- HC7 證據目錄：`B518 Log Solution/docs/refactoring/evidence/hc7-20261022/`（README、幾何矩陣、樣本索引、重跑紀錄）。更新 `CLAUDE_KVM_HANDOFF.md` 與本摘要，逐張區分 timer PNG raster 原點與 titlebar。
- 不宣稱 JetKVM 影像縮放、壓縮、遮擋、凍結串流已驗收；目前沒有 received frame、部署中的 App/bridge 配對或遠端取樣資料。

