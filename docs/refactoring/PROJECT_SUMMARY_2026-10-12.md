# 專案摘要 — 2026-10-12

## 前次討論與結果

- 延續 [2026-10-09 摘要](PROJECT_SUMMARY_2026-10-09.md) 與本對話的 M10 實作紀錄。M1～M9 已納入 `B518-Log-Solution`；M10 尚未合併，全部自有入口／跨視窗整合、正式 bundle 及適用目標 HMI／KVM 驗收仍未完成。
- M10 固定審查基準為 `95b791c2cf1a54b10db4f07cbc606ddd06db8280`，程式／測試版本為 `e8a309fd1fac186832c5825c803e4299932f206b`。10/09 完整含 Tk 套件 365 tests（97.910 秒）通過，資源兩語各 317 keys；這些是歷史 source 證據，不代表本次重跑或正式發布驗收。本次只做遠端同步、Git 清理及摘要記錄，沒有修改程式或重跑測試。
- 使用者先前指定 Gitea 內網同步延至週一；本次已回到公司網路，授權查核未推送項目、同步後清理殘餘 worktree。

## 即時查核與 Gitea 同步

- Git 根目錄為本 repo；它與 `Mac mini`、`Mac mini-BT-Codex` 共用 Git repository。查核全部本地分支及 Gitea／GitHub 的 `refs/heads/*`，不是沿用 10/09 的 tracking refs。
- 開始時 Gitea `B518-Log-Solution` 為 `44567457f0c94ae4667ab0c06e82cbacc9a001a6`，本地及 GitHub 為 `95b791c2cf1a54b10db4f07cbc606ddd06db8280`；左右 ancestry 數為 `0 / 95`，可以安全 fast-forward。既有 `main`、`BT-Codex`、`BT_Claude` 及 `codex/ticket-17` 分支三方一致，沒有待推提交。
- 已 fetch Gitea，並以明確 Gitea URL 推送主線與 M10 票分支；未使用 force。直接 `git ls-remote` 確認 Gitea／GitHub 主線皆為 `95b791c2cf1a54b10db4f07cbc606ddd06db8280`，M10 皆為 `d73c18e1c4e27cdcae5f33796432a9e3db95d1d8`。這是本摘要新增前的查詢版本；本摘要提交推送後須再直接確認兩個目的地。
- `origin` fetch URL 是 `http://10.64.76.34:3000/8362/B518-205_207_ATE.git`，push URL 同時包含該 Gitea URL 與 `git@github.com:Bowei1121/B518_205_207_ATE.git`；`github` 另指向同一 GitHub。既有目的地均保留。

## 分支與 worktree 清理

- M2～M9 票分支末端均經 `git branch --merged B518-Log-Solution` 確認納入主線；主線已直接查證同步兩個目的地。因此刪除 GitHub 的 `Multilingual/ticket-02`～`Multilingual/ticket-09`，並使用 `git branch -d` 安全刪除同名本地分支。Gitea 原先沒有這八個票分支，所有內容已經由主線同步。
- `git worktree prune --dry-run --verbose` 確認 `/private/tmp/B518-Log-Solution-ticket-17`、`/private/tmp/B518-Log-Solution-ticket-18` 的目錄已不存在，僅有失效 Git 登記。以 `git worktree prune --expire now --verbose` 清除這兩筆登記；沒有刪除有效 checkout 或使用 force。
- 保留三個有效 worktree：`Mac mini`（`main`）、`Mac mini-BT-Codex`（`BT-Codex`）、`B518 Log Solution`（未完成的 `Multilingual/ticket-10`）。M10 尚未完成必要驗收，因此不合併、不刪除其本地或遠端分支。
- 開始時 `docs/refactoring/PROJECT_SUMMARY_2026-10-09.md` 有既存未提交的架構討論摘要修改；原內容保留，不納入本次提交。本次只提交此 10/12 摘要，並將 M10 的新增文件提交推送至兩個目的地。

## 後續

- Gitea 同步不再是 M10 的阻擋。後續仍需依 [M10 驗收](evidence/multilingual-ticket-10/local-validation.md) 及 [發布驗收](evidence/multilingual-ticket-10/release-validation.md) 補齊產品與正式產物證據，通過全部合併條件後才整合 M10。
- 所有分支不存在／遠端 SHA／worktree 清理結果，在摘要提交與最終推送後再次直接查核，最終文件提交 SHA 與查詢結果回報於本對話，避免文件自引用 SHA。

## 本機 macOS Tk 建置異常修正

- 在桌面 checkout 的 `B518-Log-Solution` 查核 Git，保留既有 VERSION 0.1.3 與未追蹤 spec，兩檔先備份並於驗證後 cmp 確認原樣。
- 使用指定 Python 3.12.10 重現殘留 after script 的 invalid `_drain_events` command，以及 worker GC 的 Variable.__del__ 主執行緒錯誤／Tcl_AsyncDelete 中止；保存 Python 與原生執行緒堆疊。
- 修正 App timer 管理、Destroy 主執行緒 Tk 資源釋放、hotkey callback 生命週期、測試桌面視窗及所有背景工作收尾；新增 subprocess GC、timer 與 native openat mode 回歸測試。
- 完整套件另外找出 Apple arm64 openat 可變參數宣告錯誤（清理後事件檔權限 000），一併修正；保留安全路徑查核。修正衝突視窗小尺寸操作列及非同步 Tk 畫面驗證。
- 完整含 Tk 374 tests（71.342 秒）通過，零跳過；最終 macOS15 arm64 build 腳本在隔離副本再跑 374 tests（72.838 秒）通過並 exit 0，bundle／簽章／ZIP 檢查完成。候選 V0.1.4 留在忽略的 dist-validation 目錄，原 VERSION 0.1.3 不納入提交。
- 原因、回歸前失敗、完整測試及 build 記錄見 [本次驗證證據](evidence/tk-lifecycle-2026-10-12/validation.md)。本機此次依實際既有 origin（GitHub）與目前分支提交推送；沒有依摘要的歷史遠端配置推測內網目的地。
