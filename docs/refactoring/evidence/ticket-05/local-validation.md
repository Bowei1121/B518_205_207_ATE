# Ticket 05 本機驗收紀錄

## 基準與範圍

- 固定 Standards／Spec code-review 基準：`a4a00d5fd6ca7ea4fdb6c2e1482cf2c78d244de5`。
- 最後驗證的程式提交：`d679b9992a7582169352c8f745a408cd2fe34d82`（`fix: bind archive checks to tracked rounds`）。其後只有文件提交。
- 實作接續 Ticket 01～04；沒有加入 Ticket 06／07 的期限設定、到期判定、排程或刪除。
- 開始時即時查核本地與 Gitea／GitHub push 目的地；分支 `round/ticket-05` 原先不存在，主線兩遠端均為固定基準的後續已知文件提交。工作樹既有未追蹤 `docs/adr/0009-bilingual-app-event-records.md` 及 `docs/refactoring/MULTILINGUAL_DISCUSSION_2026-10-07.md` 未修改、未納入提交。

## 驗收結果

| 驗收 | 結果與證據 |
| --- | --- |
| 1. 已結束、無待確認且 Session／audit 完整才封存 | 通過。`test_manual_stop_and_pending_alarm_only_archive_after_required_operator_work`、`test_round_with_pending_conflict_is_protected_until_operator_resolves_it`、`test_source_preparation_in_progress_cannot_be_archived_early`。停止收集或產品結果完成本身不會授予封存資格。 |
| 2. 封存時間取實際完成時刻 | 通過。`test_completed_round_is_archived_by_coordinator_using_actual_injected_time` 以注入時鐘推進後完成工作，檢查 manifest 的帶時區封存時間。 |
| 3. 版本、輪次身分、時區與完整性可由磁碟驗證 | 通過。`test_archive_round_can_be_verified_from_disk_and_binds_every_session_piece` 以新讀取器重讀 manifest，驗證 audit 與 Session 各組件的 SHA-256／大小及 round ID；`test_archive_writer_requires_the_coordinators_expected_round_identity` 與 `test_detached_retry_rejects_a_consistent_replacement_from_another_round` 驗證身分替換失敗關閉。 |
| 4. 聚合同輪分散組件並拒絕不完整、損壞或未解決狀態 | 通過。磁碟案例由不同 audit／Session 位置組合驗證；測試涵蓋 audit 完整性、Session metadata、衝突／警報、未知版本、缺少封存資訊、損壞及封存寫入失敗。 |
| 5. 新必要紀錄撤銷舊封存資格，共同狀態可供 UI 使用 | 通過。`test_new_persisted_event_invalidates_then_reseals_the_previous_archive`、`test_archive_check_racing_a_new_round_event_seals_the_latest_disk_contents` 驗證新增事件與封存競爭；新讀取器重驗後舊 manifest 不再代表目前內容。 |
| 6. 舊資料可讀且不猜造時間，Tk 能辨識狀態 | 通過。`test_archive_time_must_have_timezone_and_legacy_session_stays_readable`、`test_missing_or_unknown_archive_metadata_keeps_old_round_protected`，以及桌面 Tk 測試 `test_real_tk_distinguishes_unsaved_saved_and_archived_round_states`。 |

另有真正 Tk 與高層關閉回歸：`test_real_tk_retry_button_recovers_disk_record_once_without_blocking_ui`、`test_close_stays_open_when_a_detached_round_fails_disk_verification`、`test_normal_close_waits_for_archive_write_repair_and_retry`。封存寫入錯誤及已封存舊輪磁碟損壞都保持受保護；修復後可重新驗證。沒有以 mock `flush=True` 或記憶體旗標代替磁碟讀取。

## 實際驗證

在 `B518 Log Solution/` 程式目錄執行：

```text
python3 scripts/run_tests.py test_round_archival test_monitoring_round test_audit_records test_log_solution_ui
Ran 130 tests in 27.251s — OK

python3 scripts/run_tests.py
Ran 242 tests in 36.113s — OK

python3 -m compileall -q src tests
git diff --check
```

包含 Tk 的命令在可存取桌面圖形工作階段執行（macOS 15.7.9、Python 3.8.10、x86_64）；沙盒隔離的 Tcl 初始化會中止，因此不把該環境的退出碼當成 Tk 驗收。Repository 沒有 mypy、pyright 或其他既有型別檢查設定；型別檢查未配置，未宣稱通過。

合併 commit `fbd3ac0f09381819e87b40cb17f190145d190f88` 後，在乾淨主線 worktree 再次執行 `python3 scripts/run_tests.py`，242 tests 通過（38.883 秒），包含真正 Tk 案例。

## Standards／Spec 審查

兩軸均以固定基準 `a4a00d5fd6ca7ea4fdb6c2e1482cf2c78d244de5` 審查完整差異，最後檢視提交 `d679b9992a7582169352c8f745a408cd2fe34d82`。初次及複審發現的輪次身分驗證、脫離追蹤物件後磁碟損壞，以及 `ArchiveLocation`／時區正規化問題均已修正；最終 Standards 與 Spec 複審沒有未解問題。最後程式提交後重新執行完整 242 項測試。

## 提交與同步

- 程式提交：`0798043`（封存能力）、`938542c`（磁碟驗證修正）、`d679b99`（審查修正）。
- 分支驗收文件／專案摘要提交：`6feebe2ed08b63fdd277c9d76e0a1fb90e34d612`。
- 主線合併 commit：`fbd3ac0f09381819e87b40cb17f190145d190f88`。合併前即時 fetch 確認 Gitea／GitHub 主線都是 `a4a00d5fd6ca7ea4fdb6c2e1482cf2c78d244de5`、票分支都是 `6feebe2ed08b63fdd277c9d76e0a1fb90e34d612`；乾淨主線 worktree 無未提交檔案。
- Ticket 分支推送目的地：`origin` 的 Gitea 與 GitHub push URL，兩端均同步至 `6feebe2`。主線合併 commit `fbd3ac0f09381819e87b40cb17f190145d190f88` 與摘要驗收提交 `3d405236c7564b725b34c40587ef782670e7f1c9` 已推送至兩個目的地；即時 fetch 確認兩地主線均為 `3d40523` 且包含合併 commit。
- 確認合併已同步後，使用 `git push origin --delete round/ticket-05` 刪除 Gitea 與 GitHub 遠端分支，`git ls-remote --heads` 查無兩端分支；本地 `git branch -d round/ticket-05` 成功，`git fetch --prune` 移除 stale tracking refs。最後工作目錄切回 `B518-Log-Solution`。本次清理證據文件更新也提交並推送至兩個目的地，最後 refs 已再次查核。
- 最終主工作目錄保留未追蹤的 `docs/adr/0009-bilingual-app-event-records.md` 與 `docs/refactoring/MULTILINGUAL_DISCUSSION_2026-10-07.md`；未修改或納入 Ticket 05。
