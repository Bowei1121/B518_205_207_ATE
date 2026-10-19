## Parent

[父規格 #77：Log Solution 儀器狀態、人工停止與顯示契約 1.2](https://github.com/Bowei1121/B518_205_207_ATE/issues/77)

## What to build

操作員開始本輪後立即看到 BUSY／準備中，不能重複開始；來源舊檔基準完成才顯示監控中，之後逐格顯示活動與結果，正常完整結束回 READY。

以正常輪次做第一條完整路徑，建立後續票共用的狀態與公開可觀察事實；不全面重構，不實作人工停止交付、啟動故障復位或新開始警報。

主責使用者故事：1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 16, 17, 18, 19, 20, 21, 51, 52, 53, 54。
依父規格實作決策：1, 2, 3, 4, 5, 6, 7, 8, 15；測試決策：2, 3, 4, 10, 12, 14。

本票只驗收本程式的公開輪次行為／磁碟資料與必要真App／Tk輸出；不要求KVM_Log、JetKVM或LabVIEW驗收。

## Acceptance criteria

- [x] 按鈕、視窗內／全域快捷鍵與核心入口共用接受／鎖定規則；接受時凍結容量、映射、來源與期限，重複開始不建新輪、不清結果、不重設計時。
- [x] 接受後立即 PREPARING／BUSY，來源仍在背景準備且視窗可操作；舊檔基準及必要準備完成後才 MONITORING，不能提前宣告可開測。
- [x] 以可阻塞來源展示 PREPARING→MONITORING；監控就緒後才寫入的新資料能被收集，實際來源／顯示位置映射保持。
- [x] 正常 READY、PREPARING、MONITORING、REVIEW 與 COMPLETE 對公開快照、HMI、標記一致；共用圖樣表定義規格六碼，人工停止圖樣在 LI2 才接上真實交付路徑。
- [x] 衝突／警報 REVIEW 優先於完成；準備中、監控中、待確認及關閉保存中所有開始入口均不能換輪；此票不以 App 私有欄位另建一套狀態機。
- [x] 只有可信 TESTING／COMPLETING／本輪有效測試結果作為實際通道活動；MONITORING、HID 成功或 WAITING／NOTEST／TIMEOUT／STOPPED 不單獨作開測證據。
- [x] 快速或 final-only 來源未出現 TESTING 仍可正常完成；一格有活動不推論全通道開始。完整結果須精確涵蓋配置容量，不以空集合、缺格、重複格或錯誤映射放行。
- [x] 同一份輪次事實更新色帶與狀態格；READY 保留前輪結果到下一輪開始，容量外固定黑色、排數意義與現有色碼保持。
- [x] 正常輪次的 Session／audit 可由新讀取者重建並與公開結果一致，既有雙語事件、事件身分及保存政策不退化。
- [x] 以既有輪次公開入口及真正 Tk／App 驗證狀態、開始控制、可信活動與正常完成，不以假 root 代替可見畫面；此票成果為整合候選，不能宣稱整套1.2已可發布。

## LI1 實作驗收紀錄（2026-10-19）

實作候選已在 `codex/li1-ready-busy-preparation` 完成，尚待整合分支合併複驗及外部 Issue 完成紀錄；本段不表示 GitHub #78 已關閉。實作將已接受輪次公開為 `PREPARING`，只有來源工廠與監控基準啟動完成後才轉成 `RUNNING`／MONITORING；PREPARING 維持 BUSY、開始入口共用輪次鎖定、停用再次開始而保持停止操作可用。六種共用圖樣現有唯一碼表，PREPARING 圖樣接上真實狀態，人工停止碼只先定義、不接本票未實作的交付路徑。

驗收命令及結果：

| 驗收 | 命令 | 結果 |
| --- | --- | --- |
| TDD red | `PYTHONPATH=src python3 -m unittest tests.test_monitoring_round.MonitoringRoundTests.test_accepted_round_stays_preparing_until_background_source_baseline_is_ready tests.test_monitoring_round.MonitoringRoundTests.test_start_during_preparation_can_stop_and_late_source_does_not_restart_round -v` | 新增測試先失敗：被阻塞來源尚未返回時，公開快照為 `RUNNING`，預期 `PREPARING`；準備中停止案例原行為通過。 |
| TDD green | `PYTHONPATH=src python3 -m unittest tests.test_monitoring_round.MonitoringRoundTests.test_accepted_round_stays_preparing_until_background_source_baseline_is_ready tests.test_monitoring_round.MonitoringRoundTests.test_start_during_preparation_can_stop_and_late_source_does_not_restart_round tests.test_kvm_display_contract -v` | 9/9 通過。 |
| 輪次、來源、映射、磁碟保存及顯示契約回歸（整合分支同步後） | `python3 scripts/run_tests.py test_round_start_preparation test_platform_registry test_configured_monitor test_audit_records test_monitoring_round test_kvm_display_contract` | 112 tests，17.113 秒，全部通過；包含受控阻塞來源、來源晚回、final-only、活動、映射、容量與新磁碟讀取者重建案例。 |
| 真實 Tk 快捷鍵、待確認鎖定及凍結映射（整合分支同步後） | `B518_TK_TESTS=1 PYTHONPATH=src /opt/anaconda3/bin/python3 scripts/run_tests.py test_log_solution_ui.LogSolutionUiTests.test_real_tk_shortcuts_start_rounds_with_session_and_audit_profile_evidence test_log_solution_ui.LogSolutionUiTests.test_awaiting_review_start_entrypoints_preserve_their_existing_side_effects test_log_solution_ui.LogSolutionUiTests.test_running_round_keeps_its_capacity_and_mapping_after_profile_update` | 3/3 通過，8.024 秒。 |
| 真 App／Tk 四階段輸出 | `PYTHONPATH=src /opt/anaconda3/bin/python3 tools/smoke_li1_preparation_app.py` | 真正 B518 Tk 視窗以 Quartz 擷取 PREPARING、MONITORING、TESTING 活動與 COMPLETE；PREPARING 開始停用、停止可用；按鈕／視窗快捷鍵／全域快捷鍵／核心入口重複觸發維持同一輪；兩格 PASS 後公開結果可用。需在允許原生桌面視窗的工作階段執行。 |

真實 App 環境為 macOS 15.8.1、x86_64、Python 3.11.7、Tk 8.6；證據在 [li1-real-app](../../../B518%20Log%20Solution/docs/refactoring/evidence/li1-real-app/)：`preparing.png`、`monitoring.png`、`activity.png`、`complete.png`、`run.json`。Quartz 擷取以本次 App PID 及 Tk root title `B518 FCT ATE Log Solution-V0.1.0` 篩選，四張圖均直接顯示 B518 App 主視窗。

限制：沒有執行外部 KVM／ATE／LabVIEW 驗收，依規格不屬本專案門檻。人工停止交付、啟動失敗復位、整輪未開始警報及契約幾何仍分別屬後續票；本紀錄不宣稱這些功能完成。整合後 SHA 與跨分支複驗結果待整合代理補入。

## Blocked by

None (can start immediately)
