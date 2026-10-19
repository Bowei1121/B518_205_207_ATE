# LI3 #80 完成紀錄

分支：`codex/li3-startup-failure-reset`
基底：`ba026325f167a67f8f623aebd0849d8dccc5e550`
狀態：已整合驗收並推送到 GitHub 與內部 Gitea；GitHub #80 已留下完成紀錄並以 completed 關閉。

## 修改與驗收對照

- 接受前啟動錯誤記入 App 診斷紀錄，投影為持續 REVIEW；不建立輪次，且遮蔽上一輪 COMPLETE 的可用結果。復位前所有啟動入口均鎖定；人工復位結束失敗請求，不自動重試。
- 真實 Tk 操作先完成上一輪並顯示 `PASS / SN-OLD-COMPLETE`，再移除來源目錄觸發前置路徑驗證失敗。舊結果及 PASS 色帶留在畫面，狀態標記為 REVIEW，公開 `result_available=False`，開始按鈕鎖定；關閉錯誤視窗後故障仍在。
- 復位後舊輪結果仍可見、狀態回待命（READY）；復位本身不開新輪。再次明確按開始後才取得不同 `round_id`。
- 接受後 factory／prepare 例外進入 `AWAITING_REVIEW`，停止收集並保留原始診斷與輪次事件；不合成產品 FAIL。明確復位會記錄失敗輪取消與復位事件，磁碟重建得到已取消狀態；之後須再次明確開始才建立新輪。
- Tk 畫面提供中英文錯誤說明及「確認並復位」按鈕。關閉提示不會解除待確認狀態；復位不自動啟動來源。
- 保留先完成人工停止的輪次語意；晚到的來源錯誤不覆蓋 manual stop。來源尚未回報 ready 的人工停止輪次在 close/archive 後仍受保護，供人工核對。

## 實際驗證

- `PYTHONPATH=src python3 -m unittest tests.test_monitoring_round tests.test_round_start_preparation -q` — 64 tests，通過。
- `PYTHONPATH=src python3 -m unittest tests.test_audit_records tests.test_app_event_store tests.test_kvm_display_contract -q` — 61 tests，通過。
- `B518_TK_TESTS=1 PYTHONPATH=src /opt/anaconda3/bin/python3 -m unittest tests.test_m10_integration -v` — 真正桌面 Tk 整合測試 7 tests，通過；在桌面登入工作階段執行。
- `B518_TK_TESTS=1 B518_TK_EVIDENCE_PATH=/private/tmp/B518-LI3-startup-reset/docs/refactoring/log-instrument-tickets/evidence/LI3-prior-result-review.png PYTHONPATH=src /opt/anaconda3/bin/python3 -m unittest tests.test_m10_integration.M10SourceIntegrationTests.test_visible_prevalidation_failure_preserves_previous_complete_result_until_explicit_restart -v` — 新增 AC 案例通過，擷取真正 Tk 視窗。
- `python3 -m compileall -q src tests` — 通過。
- `git diff --check` — 通過。
- 畫面證據：[`LI3-prior-result-review.png`](evidence/LI3-prior-result-review.png)。從實際桌面擷取後裁出 Configuration Error 與 B518 HMI 視窗，避免保留其他桌面內容；畫面同時呈現原始診斷、舊輪 PASS/SN、鎖定的開始按鈕及啟動故障狀態。

## 範圍與限制

測試涵蓋本程式公開輪次行為、App/Tk 畫面、audit/App 診斷持久化及磁碟重建。KVM_Log、JetKVM、Dock 自動化、LabVIEW、現場 ATE 流程不屬本票驗收。

## 整合結果

已整合至 `codex/log-instrument-1-2`，LI3 整合 commit `cd0ccb0698cc55ee2625f5b35e7e7c878e9e6c47`；票務紀錄修正後 commit `6e7842563e285ac0fb61ab08f0f9fc87e9ca8354`。整合後重跑核心+準備 64/64、audit/AppEvent/契約 61/61、真 Tk 7/7，`git diff --check` 通過。GitHub 與內部 Gitea 遠端 SHA 均核對為 `6e78425eda9d2eccc58614e1a0a1780e70b406fb`。GitHub #80 已新增完成紀錄並以 completed 關閉，回讀確認 CLOSED/COMPLETED。

## Code review follow-up (2026-10-19)

- Fixed the restart case where the accepted failed round was no longer in memory: reset now appends durable reset/cancellation events to its audit, preserves failure evidence, and permits a subsequent explicit start. Regression: `test_accepted_start_failure_can_be_reset_after_app_restart_from_disk_records`.
- Added regression for a trusted activity event whose slot later TIMEOUTs before the round start deadline; that prior accepted activity now suppresses only the false whole-round no-start alarm. Per-slot decisions remain intact.
- Verification: candidate domain suite (`test_machine_profiles`, `test_monitoring_round`, `test_round_start_preparation`, `test_app_event_store`, `test_audit_records`, `test_round_archival`) — 171 tests passed; `test_monitoring_round` — 64 tests passed; `python3 -m compileall -q 'B518 Log Solution/src' 'B518 Log Solution/tests'` and `git diff --check` passed.
- Cleanup race check: clean baseline `8922bb5` manual-stop cancellation case passed alone and its six-module suite passed 162 tests; candidate six-module suite passed 171 tests including that case. The earlier candidate cleanup `OSError` did not reproduce in either rerun and is not counted as a pass.
