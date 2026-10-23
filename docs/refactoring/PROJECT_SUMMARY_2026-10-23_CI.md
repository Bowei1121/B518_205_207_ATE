# 專案摘要 — 2026-10-23：GitHub 雲端 CI

- 使用者確認本次目標為 GitHub 提供的 Apple Silicon M1／macOS 15 虛擬機，完成自動化測試與打包；不是自有 Mac 或 SSH runner。
- 可查證既有結果：最新產品整合分支 `github/B518-Log-Solution` 為 `e441be3`（PR #121 合併）；repo 預設分支仍為 `main`。GitHub 查詢當時沒有 self-hosted runner。
- 原 checkout 的未提交 HMI 交接、HC7 證據及 10/22、10/23 摘要均保留；本次從最新產品整合分支建立獨立工作目錄與 `codex/m1-macos15-ci` 分支。
- 新 workflow 使用 GitHub-hosted `macos-15`，固定 Python.org 3.12.10 universal2、PyInstaller 6.16.0 與既有桌面測試依賴；沿用完整 Tk 測試、原生輸入檢查、bundle 驗證與 ad-hoc 簽章。
- CI 保留追蹤中的 VERSION，以 workflow run／attempt 及 commit 區分產物；本機不帶參數建置仍遞增 patch。產物與測試證據保存 14 天。
- PR／產品整合分支 push 自動觸發。workflow_dispatch 需要 workflow 同時存在於預設分支，不能僅因 YAML 中宣告就假稱手動按鈕已可用。
- 完整雲端桌面測試與打包是否通過，須讀取實際 Actions 結果；本機 Intel 驗證不代表 M1 雲端驗收。獨立審查與合併仍依專案流程交接。
