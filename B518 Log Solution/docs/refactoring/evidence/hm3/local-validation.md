# HM3 本機驗收紀錄

- GitHub issue：#56；票規格：`docs/refactoring/hmi-layout-tickets/03-review-and-alarm-layout.md`。
- 固定審查基準：`0a877eb8dbb97e60fdf7e6309080019f06de69d2`。
- 分支：`codex/hm3-20261015`。
- 執行環境：macOS 15.7.9、Python 3.8.10、Tk/Tcl 8.6（Aqua）。

## 真 Tk 操作與畫面證據

- 衝突視窗使用 28 個同輪候選，選取第 18 筆；原始／候選 SN 與路徑為長英文資料，候選路徑和原路徑使用相同檔名但位於不同目錄。比較表保留 PASS／FAIL 紅色粗體差異及來源時間，來源檔名顯示目錄提示。長候選文字可由列表水平捲軸閱讀，詳細原文與診斷可垂直捲動。
- 以真正輪次逾時建立未確認警報。切換 English／繁中四次，檢查視窗大小、每個可見控件 bounds、候選選取、分隔位置、詳細文字閱讀行、結果資料、警報未確認狀態及 KVM 區塊／標記幾何都不變。
- 每語言擷取衝突視窗及警報視窗本身，使用 Quartz `CGWindowListCreateImage(..., kCGWindowListOptionIncludingWindow, ...)`，沒有保存桌面背景。PNG、原生視窗 frame、像素尺寸、控件 bounds、選取與警報狀態記錄在 [window-bounds.json](screenshots/window-bounds.json)。
- 衝突對照文字採 App 淺色底、黑色實線框；PASS／FAIL 差異色保留。警報文字與背景採 App 淺色；確認鈕狀態仍由輪次準備與人工確認規則控制。

## 命令與結果

- `PATH=/opt/anaconda3/bin:$PATH B518_TK_TESTS=1 B518_TK_EVIDENCE_DIR=docs/refactoring/evidence/hm3/screenshots PYTHONPATH=src python3 scripts/run_tests.py test_log_solution_ui.LogSolutionUiTests.test_hm3_conflict_and_alarm_layout_stays_fixed_across_languages`：1/1 通過；真 Aqua 視窗逐控件 bounds 中英相等。
- `PATH=/opt/anaconda3/bin:$PATH B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py test_log_solution_ui.LogSolutionUiTests.test_scrolled_conflict_candidates_keep_reading_position_on_language_change test_log_solution_ui.LogSolutionUiTests.test_conflict_and_alarm_refresh_fail_independently_and_retry_latest_language test_log_solution_ui.LogSolutionUiTests.test_real_tk_close_keeps_conflict_and_alarm_actions_available`：3/3 通過。
- `PYTHONPATH=src python3 scripts/run_tests.py test_monitoring_round.MonitoringRoundTests.test_conflict_resolution_does_not_release_round_deadline_results test_monitoring_round.MonitoringRoundTests.test_round_deadline_alarm_is_created_once_and_acknowledgement_releases_results test_monitoring_round.MonitoringRoundTests.test_round_alarm_and_conflict_are_independent_release_blockers`：3/3 通過。
- `python3 -m py_compile src/b518_log_solution.py tests/test_log_solution_ui.py`：通過。
- `git diff --check`：通過。
- 未執行完整測試套件或工廠設備驗收；本票改動只調整衝突／警報視窗布局與對應真 Tk 驗收。
