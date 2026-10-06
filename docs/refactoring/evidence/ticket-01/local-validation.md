# Ticket 01 本機驗收紀錄

日期：2026-10-06（Asia/Taipei）  
程式碼基準：`a6bd86ed6097e7fb1f0c7a53b3b7c8b05d9dfa06`  
驗收分支：`round/ticket-01`  
環境：Python 3.8.10、macOS 15.7.9、x86_64、Git 2.50.1

## 驗收結果

| Ticket 01 驗收項目 | 結果 | 證據 |
| --- | --- | --- |
| 多輪完成後不累積 idle audit worker | 通過 | `test_completed_round_audit_writers_exit_after_idle_period` 透過 RoundCoordinator 完成六輪，排空保存佇列後，程序活動執行緒數在期限內回到測試基線。 |
| 空閒退出後可重新保存，競爭時不漏寫 | 通過 | `test_round_alarm_can_be_acknowledged_after_idle_writer_exits` 先等 worker 退出，再以公開警報確認入口新增事件並從磁碟重建。`test_concurrent_audit_events_near_idle_exit_are_all_reconstructed_in_order` 以 Barrier 同步多個公開入口呼叫，檢查 20 筆新增事件及連續序號。enqueue、pending 更新及 worker 退場由同一 Condition 序列化。 |
| 停止讀檔後仍可處理衝突／警報且可重建 | 通過 | `test_conflict_resolution_after_manual_stop_and_idle_exit_is_reconstructable` 在手動停止並等 worker 退出後解決衝突；警報案例在空閒退出後確認。兩者均以新磁碟讀取結果確認事件及順序。 |
| 同路徑鎖可回收且仍使用中的鎖不替換 | 通過 | 路徑登記使用 `WeakValueDictionary`；Store 仍持有鎖時其物件保持存活。`test_session_attachment_waits_for_the_destination_path_lock` 以受控 fsync 暫停持有目標路徑鎖的 writer，確認 audit 搬移會等待，再驗證磁碟內容完整。搬移同時取得來源與目標鎖，並按固定順序鎖定以避免反向搬移死鎖。 |
| 共同輪次入口、暫存磁碟、反覆輪次及同步競爭 | 通過 | 新增案例透過 `RoundCoordinator`、真實暫存檔與 `read_round_audit` 磁碟重建驗證；路徑鎖案例另外直接測試 Store 的公開操作。沒有以私有 helper 呼叫次數作為驗收。 |

## 執行命令

- 紅燈：`python3 'B518 Log Solution/scripts/run_tests.py' test_audit_records.RoundAuditRecordTests.test_completed_round_audit_writers_exit_after_idle_period`。舊實作失敗，6 個已完成輪次留下 6 個 audit worker。
- 聚焦：`python3 'B518 Log Solution/scripts/run_tests.py' test_audit_records test_monitoring_round`，55 tests 通過。
- 完整套件：`python3 'B518 Log Solution/scripts/run_tests.py'`，198 tests 通過。需要桌面圖形工作階段才能執行 Tk 測試；最後一次在桌面權限下全數通過。先前一次完整執行只有暫存目錄清理錯誤，隔離重跑該 UI 案例及後續完整重跑皆通過。
- 語法：`python3 -m py_compile 'B518 Log Solution/src/audit_records.py' 'B518 Log Solution/tests/test_audit_records.py'`，通過。
- 差異格式：`git diff --check`，通過。

repository 沒有 mypy、pyright 或其他型別檢查器／型別檢查命令；未宣稱型別檢查通過。`py_compile` 僅驗證語法。

## 提交與審查

- `6008c12 fix: retire idle audit workers safely`
- `f1cd840 test: cover audit idle races and shared locks`
- 固定基準 Standards／Spec 雙軸審查均無未解發現。審查涵蓋 `git diff a6bd86ed6097e7fb1f0c7a53b3b7c8b05d9dfa06...HEAD`。
- 兩個程式提交均已推送至 Gitea `origin` 與 GitHub `github`。最終分支 refs 會在整合紀錄中再次查核。

本機受控測試不代表現場設備或實際長時間部署測試。本票沒有實作保存失敗重試、完整保存後關閉、封存或到期清理。
