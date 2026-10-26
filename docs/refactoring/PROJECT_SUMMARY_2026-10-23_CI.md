# 專案摘要 — 2026-10-23：GitHub 雲端 CI

- 使用者確認本次目標為 GitHub 提供的 Apple Silicon M1／macOS 15 虛擬機，完成自動化測試與打包；不是自有 Mac 或 SSH runner。
- 可查證既有結果：最新產品整合分支 `github/B518-Log-Solution` 為 `e441be3`（PR #121 合併）；repo 預設分支仍為 `main`。GitHub 查詢當時沒有 self-hosted runner。
- 原 checkout 的未提交 HMI 交接、HC7 證據及 10/22、10/23 摘要均保留；本次從最新產品整合分支建立獨立工作目錄與 `codex/m1-macos15-ci` 分支。
- 新 workflow 使用 GitHub-hosted `macos-15`，固定 Python.org 3.12.10 universal2、PyInstaller 6.16.0 與既有桌面測試依賴；沿用完整 Tk 測試、原生輸入檢查、bundle 驗證與 ad-hoc 簽章。
- CI 保留追蹤中的 VERSION，以 workflow run／attempt 及 commit 區分產物；本機不帶參數建置仍遞增 patch。產物與測試證據保存 14 天。
- PR／產品整合分支 push 自動觸發。workflow_dispatch 需要 workflow 同時存在於預設分支，不能僅因 YAML 中宣告就假稱手動按鈕已可用。
- 完整雲端桌面測試與打包是否通過，須讀取實際 Actions 結果；本機 Intel 驗證不代表 M1 雲端驗收。獨立審查與合併仍依專案流程交接。
- 初次雲端 run `39970766079` 實際環境：Apple M1 (Virtual)、macOS 15.7.9、Python 3.12.10、Tk 8.6.16。原生輸入檢查通過，590 項測試中有 4 項失敗、4 項跳過，因此未打包；證據已保存為 Actions artifact。
- 兩項失敗明確來自測試硬編碼 Retina 2 倍像素，改為與真實原生視窗的 backingScaleFactor 比對；另加入至少 1920×1080 邏輯像素的桌面設定，保留遮擋與提示測試以實際重跑驗證。
- 已建立 PR #122；初始 commit `467239c` 已推送 GitHub。內部 Gitea `10.64.76.34:3000` 連線逾時，未宣稱該 remote 同步完成。

## 最終驗證結果

- [雲端 run 39973646605](https://github.com/Bowei1121/B518_205_207_ATE/actions/runs/39973646605) 成功。實作 HEAD 為 `42bbbae070aff01ba02cfe2c3ab158b6376ebc63`，實際待合併測試 commit 為 `1e31b3ce53aec90ae9aef9edd4da1f856850c93b`。
- 剩餘兩項桌面問題的最小重現通過；完整套件 590 項中 586 項通過、4 項條件式跳過（H8 容量資料環境兩項、指定小解析度一項、人工外觀驗收一項）。未把這四項視為通過。
- 根因：使用程序範圍的顯示模式設定，程序結束後桌面回到 1024×768，衝突視窗無法避開 KVM、部分提示控制項落在畫面外。改用 CoreGraphics 的 `.forSession`，並用新的 Tk 程序證明桌面仍是 1920×1080；不修改 App 的視窗與提示邏輯。
- 完整測試後成功建置 `B518-Log-Solution-V0.1.0-macOS15.0-arm64.zip`；bundle 驗證、ad-hoc 簽章與 SHA-256 驗證均通過。安裝包與證據已上傳 Actions artifacts，保存 14 天。
- 已下載實際 artifact 再核對：SHA-256 `cd60296b93281bbf714aee673c47b57ae68163187545ed5ef4a9544deefa2b36`；Info.plist 版本 0.1.0、最低 macOS 15.0；主執行檔 Mach-O CPU type 為 arm64。
- [PR #122](https://github.com/Bowei1121/B518_205_207_ATE/pull/122) 交接獨立審查；未合併、未更新產線。此結果記錄的提交只修改本摘要，使用 `[skip ci]` 避免重跑未變更的產品／workflow 程式。
