## Parent

[父規格 #77：Log Solution 儀器狀態、人工停止與顯示契約 1.2](https://github.com/Bowei1121/B518_205_207_ATE/issues/77)

## What to build

配置／路徑等接受前失敗或來源準備中的失敗，都形成持續可見的異常待確認；人員排除、確認並復位後才回 READY，再次明確開始才新輪。

涵蓋 App 層無輪次故障及已接受輪次故障，包含該失敗請求結束／失敗輪次取消與保存；其他已完成／停止／逾時輪次的人工取消由 LI5 擴充。

主責使用者故事：55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65。
依父規格實作決策：2, 4, 7, 16, 18, 19；測試決策：9, 11, 14。

本票只驗收本程式的公開輪次行為／磁碟資料與必要真App／Tk輸出；不要求KVM_Log、JetKVM或LabVIEW驗收。

## Acceptance criteria

- [ ] 配置／路徑或其他同步啟動失敗未接受新輪時，只記失敗請求及 App 異常，不補造新輪、不掛到上一輪；仍投影 REVIEW，不能讓上一輪COMPLETE殘留成可取用狀態。
- [ ] 本輪已接受後的來源建立／準備例外停止並保留失敗輪次、原因及原始診斷，HMI為BUSY／待確認與REVIEW；不造產品FAIL、MONITORING或人工停止完成。
- [ ] 真App顯示具體錯誤與繁中／英文說明，單靠REVIEW不假裝辨識全部根因；輪次與App層失敗的歸屬可從公開狀態及紀錄查證。
- [ ] 尚未人工復位前所有開始入口均被阻擋；關閉提示或設定畫面不解除故障，修正路徑本身不會自動開新輪。
- [ ] 操作員排除問題、確認並復位：無輪次者結束失敗請求，有輪次者取消該失敗輪，保留結果與故障／復位紀錄，之後才READY。
- [ ] 下一次明確觸發才取得新輪次並重新準備；不自動重試、不啟動ATE、不操作治具，也不強制採用未知來源結果。
- [ ] 復位或換輪不丟棄未保存失敗輪，保留跨輪保存恢復及關閉契約；新讀取者可還原失敗、取消及復位歸屬，不等待不存在的Session而永久卡住。
- [ ] 保留已先因人工停止定案的結果，不能讓其晚到factory例外誤走本票故障覆蓋路徑；與LI2同分支整合時補驗該交會，並以LI8確認完整組合。
- [ ] 用前置驗證失敗、接受後factory失敗、舊結果仍在畫面、修復後復位四種真App操作及公開入口案例驗證；不只assert提示函式有被呼叫。

## Blocked by

- https://github.com/Bowei1121/B518_205_207_ATE/issues/78

## Code review follow-up (2026-10-19)

- Fixed restart recovery: reset now finds the persisted accepted failed round, appends bilingual reset/cancellation audit events, preserves its failed-round evidence, and permits a subsequent explicit start. Regression: `test_accepted_start_failure_can_be_reset_after_app_restart_from_disk_records`.
- Fixed false whole-round no-start alarm after accepted activity later times out. The round retains accepted activity evidence; per-slot TIMEOUT/NOTEST decisions remain independent. Regression: `test_start_deadline_uses_accepted_activity_after_that_slot_times_out`.
- Verification on integrated HEAD `efd3efc3f09d3d3bd8b981154e65bd7dd567fce4`: `PYTHONPATH=src:tests python3 -m unittest test_machine_profiles test_monitoring_round test_round_start_preparation test_app_event_store test_audit_records test_round_archival -q` — 171 tests passed; `python3 -m compileall -q 'B518 Log Solution/src' 'B518 Log Solution/tests'` and `git diff --check 8922bb5..HEAD` passed.
- Cleanup race investigation: on clean baseline `8922bb5`, the manual-stop cancellation case passed alone and the baseline six-module suite passed 162 tests. Candidate six-module suite passed 171 tests, including that case; no cleanup error reproduced. The earlier candidate cleanup-only `OSError` remains recorded as a transient failure, not counted as a pass.
- Limit: startup-failure rounds have no Session to archive; the restart regression verifies durable audit/reset and subsequent start without waiting for an inapplicable archive-settle state.
- Real Tk on integrated HEAD: `B518_TK_TESTS=1 PYTHONPATH=src:tests python3 -m unittest test_log_solution_ui.LogSolutionUiTests.test_engineer_can_apply_and_cancel_a_complete_profile_draft -v` — 1 test passed under local macOS window permission. It verified an engineer-entered B518/FCT start timeout of 180 survives editor save and disk reload. Sandbox-only attempts aborted while creating Tk before test execution and are not counted as passes.
- Fix commit: `5e968fdf0da012cf0535970a9bdff057afb01718`; integrated and pushed HEAD at the time of review follow-up: `efd3efc3f09d3d3bd8b981154e65bd7dd567fce4`.
