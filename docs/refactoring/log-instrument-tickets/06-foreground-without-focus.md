## Parent

[父規格 #77：Log Solution 儀器狀態、人工停止與顯示契約 1.2](https://github.com/Bowei1121/B518_205_207_ATE/issues/77)

## What to build

開始監控、可信TESTING、結果更新及整輪完成時，Log視窗提升到前面但不強制鍵盤焦點、不永久置頂；同批事件合併，不隨輪詢持續提升。

以LI2已有的一般／人工停止完整生命週期驗證指定前景時機；不新增Dock自動化、不要求現場ATE或KVM配合，也不把原衝突視窗移到會遮擋狀態格的位置。

主責使用者故事：67, 68, 69, 70, 71。
依父規格實作決策：20；測試決策：14, 15。

本票只驗收本程式的公開輪次行為／磁碟資料與必要真App／Tk輸出；不要求KVM_Log、JetKVM或LabVIEW驗收。

## Acceptance criteria

- [x] 開始監控、可信TESTING、結果更新及一般／人工停止整輪完成均有可觀察的前景效果；依輪次與實際轉換處理，不漏人工停止或TIMEOUT等結果更新。
- [x] 不呼叫強制鍵盤焦點或設永久topmost；使用者仍能操作其他視窗，既有人工裁決／保存及關閉流程保持。
- [x] 同批事件可合併提升，狀態未變不因固定輪詢反覆提升；舊輪事件不提升錯誤輪次畫面。
- [x] 真Log App與另一個本機測試視窗驗證遮擋前後順序、鍵盤焦點、最小化恢復及非永久置頂，不以假root呼叫次數代替實機效果。
- [x] 前景操作失敗保留可查閱診斷，不讓例外中斷輪次處理或暗中跳過其餘結果更新；新增說明保持兩語。
- [x] 保留適當隔離資料與前景／焦點證據，驗收不包含橋接點Dock、JetKVM傳輸或特定ATE測試軟體。

## Blocked by

- https://github.com/Bowei1121/B518_205_207_ATE/issues/79


## LI6 implementation record

來源分支：`codex/li6-foreground-without-focus` (`342345c29204d4334567297286e6a737a3def72c`)
目標整合分支：`codex/log-instrument-1-2`（當前整合 SHA：`5d9b008477fcbbf80f6e1c7ab650f160ead9efe1`）
Merger 候選分支：`codex/li6-merger-integration`
LI6 merge commit：`35f757051a2e2938fc63716b6598cc7af3c4f383`，父 commits：`b2be9c66f0eb54796bf35c1f0016a64850131a28`、`342345c29204d4334567297286e6a737a3def72c`。整合分支已 fast-forward 並同步本機票務紀錄至 `c757920f15ed35ff87f4cbe71fedd21ae796f901`。
GitHub Issue #83：已留言並讀回確認 `CLOSED / COMPLETED`；完成紀錄連結：[LI6 完成紀錄](https://github.com/Bowei1121/B518_205_207_ATE/issues/83#issuecomment-6264624598)。

以輪次 snapshot 的實際狀態與結果轉換排程前景提示；同一 Tk idle 批次合併、輪詢不變時不重複提升，輪次 ID 不符時忽略。macOS 原生視窗使用非 key window 的 order-front 路徑；不設永久 topmost、不呼叫 `focus_force()`。原生提升失敗記錄雙語 App event 與原始診斷，仍繼續更新結果列。README、RS-WMT pilot 與 Ticket 17 驗收說明同步調整為雙語前景規則。

### 實際驗證

- `B518_TK_TESTS=1 B518_TK_EVIDENCE_DIR="$PWD/docs/refactoring/evidence/li6-foreground" /opt/anaconda3/bin/python3 scripts/run_tests.py test_li6_foreground` — macOS Python 3.11.7、Tk 8.6.12、Quartz/AppKit；1 test，通過。真正 B518 Tk 主視窗與本機第二個 Tk 視窗驗證開始監控／可信 TESTING、結果變更、一般完成、TIMEOUT、人工停止完成、最小化恢復、焦點保持、非永久置頂、同狀態輪詢不提升、舊輪事件忽略及原生提升例外後 FAIL 仍呈現。
- `/opt/anaconda3/bin/python3 scripts/run_tests.py test_language_catalog test_monitoring_round` — 71 tests，通過。
- 整合分支 primary worktree 的重跑補充：同一真 Tk 命令在 Tk 建立視窗前兩次遭 macOS `com.apple.hiservices-xpcservice`／LaunchServices 的 `NSMenuItem` `aString != nil` 原生例外中止（exit 134，測試本體未執行）；相鄰 71 tests 首次有一項 Python 暫存目錄 cleanup race，立即重跑 71 tests 全通過。對同一整合候選 SHA `5d9b008477fcbbf80f6e1c7ab650f160ead9efe1` 在 merger worktree 重跑同一真 Tk 命令為 1 test OK（exit 0）；此前 merger 原始驗收亦 1 test OK。故保存 primary 桌面服務的啟動錯誤，LI6 真桌面驗收由同 SHA 的 merger worktree 成功執行，不把未啟動的兩次 primary 重跑算作測試通過。
- 固定基底 UI 分類：`B518_TK_TESTS=1 /opt/anaconda3/bin/python3 scripts/run_tests.py test_log_solution_ui.LogSolutionUiTests.test_empty_paths_are_rejected_before_monitor_creation test_log_solution_ui.LogSolutionUiTests.test_monitor_creation_error_is_visible_and_returns_to_standby test_log_solution_ui.LogSolutionUiTests.test_real_tk_notification_badge_stays_until_alarm_is_acknowledged test_log_solution_ui.LogSolutionUiTests.test_real_tk_preference_replace_failure_does_not_accept_round_or_leave_start_busy test_log_solution_ui.LogSolutionUiTests.test_main_page_actions_explain_bilingual_behavior_without_invoking test_log_solution_ui.LogSolutionUiTests.test_toolbar_keyboard_traverses_visual_order_and_leaves_toolbar` — 基底 `b2be9c66f0eb54796bf35c1f0016a64850131a28` 的 6 個測試方法，實際為 5 failures、2 cleanup errors；通知 badge 測試自身清理與 `tearDownClass` 各產生一個 Tcl cleanup error，詳見 `B518 Log Solution/docs/refactoring/evidence/li6-foreground/ui-regression-classification.md`。
- `python3 -m compileall -q src tests` 與 `git diff --check` — 通過。
- 真桌面逐事件 JSON 與截圖：`B518 Log Solution/docs/refactoring/evidence/li6-foreground/`；執行命令與環境記於其中 README，執行觀測記於 `run.json`。

### 範圍與限制

本機合成輪次與第二個 Tk 視窗驗證；未連接現場 ATE、KVM_Log、JetKVM、Dock automation 或 LabVIEW。既有整套 `test_log_solution_ui` 基底有預存 UI 失敗／cleanup errors，分類和逐項基底比較見證據文件；不將其宣稱為通過。
