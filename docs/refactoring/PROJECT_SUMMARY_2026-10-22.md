# 專案摘要 — 2026-10-22

## 今日接續

- 延續 2026-10-21 的 HMI 子票工作；指定 GitHub Issue [#112：HC7 新版本機幾何量測與 KVM 模板交接](https://github.com/Bowei1121/B518_205_207_ATE/issues/112)，父規格 [#105](https://github.com/Bowei1121/B518_205_207_ATE/issues/105)。
- HC1–HC6 Issues 已關閉；HC3/HC4 的 App 整合 source tree 在 `d03c7b6bf56e25cae4ceea58814d78a467bb112c`。這個 source tree 等於 PR #119 審查 HEAD 的檔案樹。
- 讀取橋接 repo `Bowei1121/B518_KVM_Log` 的 `main` HEAD `736bb8b4df5ce87beaf140416f3aea027d3aa1d7`；`log_solution_reader.py` 宣告 contract 1.3。幾何相符，但 parser 漏辨 App `STALLED` (`#ff9900`) 狀態；該格會使影像 fail closed。因此只是幾何相容，不能宣稱完整 source 相容。App 1.3 欄位沒有改變，不升 App contract version；橋接修正留給橋接專案。

## HC7 交付與限制

- 建立 `B518 Log Solution/docs/refactoring/evidence/hc7-20261022/`：`README.md`、`geometry-matrix.json`、`samples.json`、`local-run.json`。舊 LI7 timer ROI 已明確標成 HC3 前資料；新版本機 timer crop 為 `00:00 [648,1386,88,40]`、`10000:00 [600,1386,136,40]`，座標以本機 content-view 為原點。
- 更新 `CLAUDE_KVM_HANDOFF.md`：將原 LS7 1.1 bridge 快照與舊 timer crop 定位為歷史資料，新增 HC7 的 1.3 來源相容判斷及新版本機座標。沒有修改橋接程式。
- 可引用的本機實測：HC3 1440×900 固定高度矩陣與 1152×720 支援顯示；舊雙 Tk scaling 的 KVM child 幾何只用來確認不變的父框相對座標；HC4 PR #119 獨立審查的三個真 Tk 測試 3/3、0 skipped，覆蓋提醒、10000:00、狀態及心跳獨立。
- 本 session 重新跑真 Tk/Quartz 矩陣時，Codex 啟動 shell 無 macOS Aqua/Accessibility GUI session，Tk 初始化以 exit 134 結束；不列為產品測試失敗或通過。雙 scaling 的完整新版 HMI 原生截圖未由本次重新產生，已在 HC7 README/JSON 明確記錄。
- 沒有真實 JetKVM received frame；遠端像素、縮放、壓縮、遮擋及凍結源測試留待 HC8，不以本機 Retina 截圖替代。

