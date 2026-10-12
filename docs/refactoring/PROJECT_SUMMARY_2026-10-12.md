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

### 推送認證阻擋（本次實際狀態）

- 本次修正已提交為 b1b4c36；查核遠端新文件提交後，以 f4bade6 安全合併 origin/B518-Log-Solution 的 088caae、82c4a13，程式沒有額外變更。
- 推送尚未完成：HTTPS Git 未設定認證、SSH agent 無金鑰；已連線 GitHub 寫入 API 回傳 403 Resource not accessible by integration。已請使用者在這台 Mac 設定 Git 推送認證，完成後續推並確認遠端 SHA。

### SSH 認證完成後續推

- 使用者新增 SSH key，認證成功為 Bowei1121；GitHub 主機指紋經官方比對後，透過 SSH 完成 B518-Log-Solution 的 fast-forward 推送。
- 直接查核遠端為 edee8253008e22c0d36cd702af5741d7c6d98928（本段紀錄提交前），包含本機 Tk／openat 修正 b1b4c36；推送阻擋已解除。VERSION／spec 原有內容仍保留，程式與已驗證產物沒有追加變更。

## Language refresh L2 implementation (2026-10-12)

- L2 is implemented on `LanguageRefresh/ticket-02` from fixed review baseline `7071ea1065c21fa93612a30ccca64d85840e185b`. Settings, App diagnostics and historical-event windows now register independently with L1's existing notification contract; language rendering uses the displayed event snapshot, retains view state, and does not reread sources. The three windows no longer receive the duplicate main-page language fanout; L3 windows and L4 cleanup remain outside this ticket.
- Real-Tk coverage includes simultaneous windows, settings draft/tab retention, diagnostic/history event selection/detail/scroll retention, close/destroy/hide/reopen, failure injection for each of the three views and two simultaneous failures, aggregate diagnostics and latest-language retry. Bilingual failure diagnostics were rebuilt from disk with no `round_id`; ordinary language switches preserved event/audit bytes. Native file-dialog cancellation and settings/history regression evidence is recorded in the L2 validation file.
- Two earlier full-suite attempts had intermittent `TemporaryDirectory.cleanup(): Directory not empty` failures in existing teardown tests. The same `test_destroyed_ui_is_safe_when_next_worker_collects_cycles` failure signature reproduced on the fixed pre-L2 baseline (1 failure in 3 isolated attempts), confirming a pre-existing intermittent test issue. After the final L2 test additions, the required complete Tk suite passed 381 tests in 108.360 seconds on Python 3.8.10 / Tk 8.6 with desktop access. Final Standards/Spec review against the fixed base found no blocker; a physical title-bar click is an explicitly unclaimed evidence detail, while the shared WM cleanup protocol and button handler are covered by source inspection.
- Focused implementation commit `fbd59244329dd22fd99944600969ca8353651769`, test-evidence commit `3b80c0c`, and acceptance-doc commit `8690529` were pushed to both configured destinations. Direct pre-merge queries on 2026-10-12 09:28 UTC confirmed GitHub and Gitea `LanguageRefresh/ticket-02` refs match `8690529118fa3e121097cda0d240562ce066b4af`, while both main refs remain at `7071ea1065c21fa93612a30ccca64d85840e185b`. Final Standards/Spec reviews found no blockers; the Standards observation is non-blocking. L2 remains isolated from the two pre-existing dirty summary files in the formal worktree.
- Evidence: [L2 local validation](evidence/language-refresh-ticket-02/local-validation.md). L1 is the direct dependency; L3/L4 and cleanup-reason C1–C4 remain separate.

## Language refresh L1 implementation

- Implemented L1 on `LanguageRefresh/ticket-01` from fixed review baseline `0eebc3200e854a27c979ab003e3e6eda0a36461f`. Main page and App-owned notices now use the existing language notification contract with independent receiver failure isolation, a nonblocking aggregate banner, manual retry, and bilingual App-event diagnostics.
- Real-Tk evidence now includes menu-driven failure isolation, actual diagnostics entry/event selection/raw diagnostic, disk reconstruction and retry, modal Escape cancellation, and notice reopening in the current language. L2–L4 and C1–C4 remain outside L1.
- Full suite: 378 tests passed on installed Python 3.11.7 with Tk enabled (`B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py`, PATH selecting `/opt/anaconda3/bin/python3`, 133.706 s; tested code/test SHA `1a2fb138dcf7ede875d8a3dcb033e5c6da8468fb`). The default Python 3.8.10 run aborts in `test_close_recovers_a_failed_previous_round_and_current_round_without_crossing_events` with Tcl_AsyncDelete; the same abort reproduces from the fixed pre-L1 baseline checkout, so record it as an environment/runtime baseline limitation, not as a passing run. Type-check configuration is absent.
- Standards and Spec review against the fixed baseline found no blocking issues. See [L1 validation evidence](evidence/language-refresh-ticket-01/local-validation.md) for commit and remote SHAs, all ten acceptance mappings, and exact limitations.

## Language refresh L3 implementation status (2026-10-12)

- L3 (#31) implementation is isolated on `LanguageRefresh/ticket-03`, fixed review baseline `93ac9e47903649c4098c1423c2496f86ac685a03`. Three code/test commits are present through `48f14dca68894147cd1ba0afa43a8e9edc331145`; focused true-Tk conflict/alarm failure-isolation, retry, lifecycle, close-protection and audit checks passed on Python 3.11.7 / Tk 8.6. Final Standards review found no blocking issue; final Spec review found no code-level gap after the required evidence was added. It confirmed the full-suite/L1 modal timeout and long wrapped-detail reading-anchor validation remain acceptance blockers.
- The required full `B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py` run did not complete: it stalled at `test_notice_escape_hidden_reopen_and_current_language_lifecycle` in existing `localized_notice.show_notice()` / Tk `wait_window`. An isolated reproduction on the accepted L1 code/test SHA `1a2fb138dcf7ede875d8a3dcb033e5c6da8468fb`, Python 3.11.7 / Tk 8.6, timed out at the same call. This is a direct dependency/full-suite acceptance blocker; it is not repaired or hidden in L3. A sandboxed true-Tk run also aborted in macOS AppKit before test execution; the same focused tests passed when run with desktop access.
- L3 is not complete or merged. Do not infer that L1 is product-broken solely from the reproduced environment-sensitive timeout; classify the cause and obtain a clean required suite result before merge. Current direct GitHub and Gitea `ls-remote` queries failed (GitHub DNS unavailable; Gitea `10.64.76.34:3000` unreachable). The prior push command reported both L3 branch destinations updated to `48f14dca…`; current destination SHA remains unverified. Preserve the L3 branch and worktree until tests, documentation review, and direct remote checks are complete. Full evidence: [L3 local validation](evidence/language-refresh-ticket-03/local-validation.md).

## Language refresh L3 resumed validation (2026-10-12)

- Earlier L3 Partial statements above describe that checkpoint. All eight items now pass at final code/test `04c2b0d04f1d6e634b57628b58306abdcd43bcdb`; fixed review base remains `93ac9e47903649c4098c1423c2496f86ac685a03`. Python 3.11.7/Tk 8.6 desktop full suite: 383 tests, 160.014 s, OK, exit 0.
- Added failing-then-passing evidence for wrapped raw reading anchor, candidate-list top identity and sash. Added simultaneous/partial/full receiver recovery, WM withdraw and actual disabled/queued retry during close; cancel restores retry only for current failures. Normal data updates, single decisions, fixed bilingual disk diagnostics and KVM remain covered.
- User suspects earlier timeout followed abnormal Python shutdown; cause remains unproved. Isolated lifecycle and six repeats plus final full suite pass without L1 notice product modification. Intermediate suite's pending-record comparison and public-completion cleanup omissions were corrected without weakening original assertions; prior failed log retained.
- Standards/Spec code/test reviews have no unresolved findings. Final document review, merge and direct destination verification remain separate steps. Formal worktree's pre-existing two summary modifications are protected, not included. [Final L3 evidence](evidence/language-refresh-ticket-03/local-validation.md) preserves commands, runtime, failures, all eight mappings and scope limitations. L4 and cleanup-reason C1–C4 are not declared complete; remote issues unchanged.

## Language refresh L3 mainline delivery (2026-10-12)

- Final Standards/Spec document reviews at df57bdb both pass with zero unresolved findings. L3 merged using an actual merge commit `6ecef64235626ee9fc289462ebdf5323b467ceb3`. Formal mainline complete desktop suite: 383 tests / 148.658 s / OK, exit 0; final source/test SHA remains `04c2b0d04f1d6e634b57628b58306abdcd43bcdb`.
- Both main destinations directly confirmed merge SHA at 2026-10-12T12:55:11Z. Final delivery-only documentation/log commit is separately pushed and directly queried; response records its SHA. Only L3 ticket branch and clean ticket worktree may be removed after synchronization. Original user summary edits are protected and restored uncommitted; unrelated worktrees/branches remain.
- Earlier Partial results above remain historical checkpoint records, superseded by final acceptance/evidence. L4/parent-wide first-item integration and cleanup-reason group remain separate.

## Language refresh L4 implementation and validation (2026-10-12)

- L4 (`LanguageRefresh/ticket-04`) is implemented from fixed review base `3ca01fab7ec7e9669111c60a4b11212876b0ce70`. L2 and L3 are verified ancestors of this baseline and their final evidence confirms their dependencies. The final code/test commit `11738a11464643be4f6962c23534ead9ecd3e8a0` removes `show_notice`'s local language-event bind fallback and `_select_language`'s direct-render fallback. Initial main-page render and normal data-driven view updates remain.
- On desktop Python 3.11.7 / Tk 8.6, `B518_TK_TESTS=1 PYTHONFAULTHANDLER=1 PYTHONPATH=src /opt/anaconda3/bin/python3 scripts/run_tests.py` passed all 383 tests in 152.591 seconds. Python 3.8.10 / Tk 8.6 aborted the full suite with `Tcl_AsyncDelete: async handler deleted by the wrong thread` at an existing round/audit close test; the same abort was reproduced from the fixed pre-L4 baseline. Sandboxed Python 3.8 and 3.11 Tk startup also aborted before test execution; the focused source-integrated test passed with desktop access. These failed attempts are recorded, not counted as passes.
- Final-version evidence maps the full parent first-item nine-scenario matrix, L4 seven acceptance items, source/window responsibility inventory, event/source/cleanup-ledger bytes-preservation checks, code review, and runtime limitations in [L4 local validation](evidence/language-refresh-ticket-04/local-validation.md). Automated Tk menu cases activate the app's real language control/command; they do not claim physical native-menu pointer/keyboard traversal. No type-check configuration exists.
- Final code/test commit `6d1cf22cb68af94962fcdcfd0ef92a614369a2ac` is pushed and direct queries confirmed identical GitHub/Gitea ticket refs. The final source-integrated Tk test drives a real temporary sample-json source through the app and shared round, then confirms source and persisted cleanup-summary bytes remain unchanged across refresh failure, manual retry and reader reopen. Final fixed-base Standards/Spec reviews passed. The ticket was fast-forward merged at `0977e6f314345ffad1a0a628b5e1ea96d9f97df3`; the post-merge desktop suite passed 383 tests / 147.585 s / OK. Final docs commit `c9412dfcecec26f71bc647a33237415ca656f41c` was directly confirmed on GitHub and Gitea at 2026-10-12 13:54:50 UTC; the ticket branch and its worktree were then safely removed. Pre-existing dirty summary edits in the formal worktree remain protected and uncommitted. C1–C4, parent second item and bundle/factory/field acceptance remain separate.

## Cleanup-reason C1 implementation and validation (2026-10-12)

- C1 (#33) was implemented on `LanguageRefresh/ticket-05` from fixed review base `14d7c23195d66962b86b8b301cdcc587b3a15c3d`. Commits `90fc58c`, `dfb7506`, `e1a7020`, and `7ceb746` add the optional bilingual reason record, fresh-reader linkage, visible completed-round reasons, and the true-Tk mixed-ledger assertion.
- The ledger remains schema 2; optional reason data survives actual ledger serialization and fresh `RoundCoordinator` reconstruction without resetting active plans or recovery state. Exact legacy producer text and four format-backed diagnostic prefixes are recognized; ambiguous/UI-only strings are rejected. Unknown or malformed values have localized outer wording and complete raw detail. The reason presenter does not participate in cleanup qualification, and formal cleanup producers remain unchanged for C2/C3.
- Focused public-model tests: 36 passed across cleanup-reason and round-retention suites. The true-Tk mixed-ledger case verifies completed, failed and skipped reasons in both languages and unchanged ledger bytes. Final full suite on Python 3.11.7 / Tk 8.6 desktop: 393 tests / 156.872 s / OK, code/test SHA `7ceb746f39a9c5288459b8622a32ff40538043c7`. Fixed-base Standards/Spec reviews have no blocking findings; Standards noted only duplicated presentation formatting. Final docs commit, direct destination verification and merge remain. The pre-existing edits to the two project-summary files remain protected; only this appended C1 note will be staged separately.
- Evidence: [C1 local validation](evidence/retention-reason-ticket-01/local-validation.md). C2 round/archive producers, C3 App-event producers, C4 complete screen integration, and the parent second acceptance item are not complete through this ticket.
- C1 final update supersedes the earlier checkpoint above: test cleanup and unknown-message-id fallback were fixed at `38aeb0e221adfbd13f05d3c1d5b8823c528dbabb`; the final desktop Python 3.11.7/Tk 8.6 suite passed 394 tests in 163.841 s (exit 0). Final Standards/Spec reviews report no blockers, with non-blocking test-cleanup/presentation notes. See the evidence file for failed/interrupted attempts, current direct GitHub/Gitea SHA checks, merge, and cleanup as those steps complete. Existing unrelated summary edits remain unstaged.
- C1 latest verification supersedes both earlier checkpoints: fixed-base review found the missing-resource fallback defect; commit `5cf609d7a4a168d3701490b2ce51b27bafe25d3e` now returns captured English when the selected-language resource is absent even if the live English catalog changed. Its red-green regression passed and the final desktop-authorized full suite passed 394 tests in 145.474 s / exit 0. One sandboxed run aborted in Tk/AppKit initialization (exit 134); this is recorded separately from the passing desktop rerun. Fixed-base Standards/Spec re-reviews have no blockers. Latest direct remote SHA, merge and cleanup will be appended after their checks; unrelated summary edits remain unstaged.
