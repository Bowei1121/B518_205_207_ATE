# 專案摘要 — 2026-10-21

## 前次可查證結果與本次接續

- LS8 / Issue #94 的 PR #102 已合併，App 整合 commit 為 `b24ab21c3bd498518fbff2a036e8e2d85dc5dd26`。完整 580 項測試實際執行於 `7168e5e`，結果 OK、skipped=3，主機為 Intel macOS 15.8.1；arm64 bundle、M4 與 bridge 配對未驗收。
- PR #103 補正測試版本追溯，已合併為 `50a6303d584fc2bcab1f0848b06534cd1de1ee35`。PR #104 後將整合線更新至 `1af60cfa4991cf5af146df9c1cbbefed8965278c`。
- 使用者要求接續本機打包及驗收。本機實為 Apple M4 / arm64 / macOS 26.5.2，不能把此結果宣稱為 macOS 15 實機通過。
- 開始時已有未提交 `B518 Log Solution/VERSION` 0.1.5 與未追蹤 `B518 Log Solution.spec`，均保留。當次證據見 `B518 Log Solution/docs/refactoring/evidence/ls8-m4-20261021/`。

## LS8 本次結果

- M4／macOS26.5.2 完整桌面套件580 tests OK (skipped=3)；另補跑兩項50k容量與一項真實深淺色測試均OK。
- 修正三個打包腳本 VERSION 目的地，commit `c43d56a`；重新產生0.1.5 arm64候選，靜態bundle、ad-hoc簽章、ZIP SHA-256及實際啟動／雙語／快捷鍵錯誤復位／退出smoke通過。
- 正式bundle已另外完成正常4 PASS、人工停止、逾時待確認與取消三輪，匯出封存完整性核對通過；原偏好設定已還原。macOS15實機與橋接配對仍未完成；Issue #94 保持開啟。

## HC6 實作對話

- 使用者指定 GitHub Issue [#111：HC6 待確認、歷史與診斷的白話雙語提示](https://github.com/Bowei1121/B518_205_207_ATE/issues/111)，父規格為 [#105](https://github.com/Bowei1121/B518_205_207_ATE/issues/105)。#111 無留言、無阻擋依賴、開始時沒有既有 PR。
- 本票程式位於上層 repo 的 `B518 Log Solution` 子專案；依最新 `B518-Log-Solution` 整合線 `1af60cf` 建立 `codex/hc6-review-history-diagnostics` 工作分支。#110 HC5 負責主頁、設定與通知／恢復；HC6 負責待確認、歷史查詢及 App 診斷子視窗。
- 原提示元件 `_LocalizedControlHint` 已支援停留／焦點、停用提示、語系刷新與視窗清理；本次沿用，不新增第二機制。白話化衝突裁決、整輪警報、歷史搜尋／分頁／取消／重試、診斷保存重試與關閉提示，並新增 HC6 中英覆蓋表與行為測試。
- 已通過 Python syntax compilation、語言／歷史顯示／歷史查詢測試 85 項、`git diff --check`。全套測試嘗試一次但未完成：`test_li6_foreground` 缺少 `AppKit`，後續真 Tk UI 測試在建立桌面根視窗時以 134 結束；native-access preflight 亦缺少 `Quartz`。未宣稱 T16/T17/T19 的本次真 App 驗收通過。詳見 `docs/refactoring/evidence/hc6-2026-10-21/local-validation.md`。
- 後續角色：使用者安排另一模型獨立審查本票 PR；此實作 session 不自行審查、合併或關閉 Issue。
