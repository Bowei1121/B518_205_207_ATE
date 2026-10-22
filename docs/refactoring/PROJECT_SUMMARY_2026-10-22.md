# 專案摘要 — 2026-10-22

## 今日接續

- 延續 HMI 子票，處理 GitHub Issue [#112：HC7 新版本機幾何量測與 KVM 模板交接](https://github.com/Bowei1121/B518_205_207_ATE/issues/112)，父規格 [#105](https://github.com/Bowei1121/B518_205_207_ATE/issues/105)。
- HC1–HC6 已關閉；HC3/HC4 整合基底為 `d03c7b6bf56e25cae4ceea58814d78a467bb112c`。HC3 幾何來源 commit `59fc669d43022bcf9088e11085f9a6111c92b1bc` 的 source tree 與此基底不同，因 HC4 更新提醒邏輯；只重用固定幾何，PR #119 同 tree 真 Tk bounds 測試補充驗證。
- 橋接 repo `Bowei1121/B518_KVM_Log` 的 `main` HEAD `736bb8b4df5ce87beaf140416f3aea027d3aa1d7` 宣告 contract 1.3。App 的 STALLED 和 TIMEOUT 同為 `#ff9900`；橋接 reader 對該顏色回傳 TIMEOUT，會把 STALLED 靜默分類為 TIMEOUT，不是 UNKNOWN/fail-closed。

## PR #120 第二輪審查修正

- 修正 timer raster ROI：四張標準 752×1612、無 titlebar 的樣本用 `[600,1330,136,40]`，capacity-10 字形 bbox 為 `[654,1339,730,1359]`；長 timer 原圖 752×1668 含 56px titlebar，原圖 ROI 是 `[600,1386,136,40]`。timer widget 寬68 Tk units。
- 修正座標原點：HC3 native frame screen y=33，titlebar 28 Tk units，Tk content origin 為 screen y=61。content y = screen y - 61；內容座標換算為 KVM y95、table y275、start y545、monitor/timer y665、reminder y687。標準 raster 2px/Tk，timer crop y1330 對應 content y665。
- 相容性、HC3/HC7 source tree 不同的記錄已更正。R2 的原點偏移修正已同步至矩陣、capacity rows、widget bounds、handoff、README、樣本與本摘要。
- R3 仍未解：新版容量1/10/11/20 × 中英 × 雙 scaling × 支援高度的完整原生布局矩陣尚未取得。Tk/Aqua 重跑 exit 134，無 unittest 輸出。PR #120 維持 draft、不合併；Issue #112 維持 open。

## HC7 交付與限制

- 證據目錄：`B518 Log Solution/docs/refactoring/evidence/hc7-20261022/`（README、幾何矩陣、樣本索引、重跑紀錄）。未修改 App runtime、橋接程式或 ATE 控制。
- 沒有真實 JetKVM received frame；遠端像素、縮放、壓縮、遮擋與凍結串流未驗收。
