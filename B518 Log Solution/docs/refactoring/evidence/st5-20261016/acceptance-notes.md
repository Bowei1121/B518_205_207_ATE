# ST5 本機進度紀錄（2026-10-16，桌面驗收待補）

工作分支 `codex/st5-adjudication-alert-close-hints` 起於整合基準 `c8eb613fb179ad41157e724026d240d0f4c0d0ce`。本次依 ST5 將雙語提示擴至人工裁決、整輪警報、關閉前保存及 App 確認訊息；沒有更新 GitHub Issue，也沒有改變人工裁決、警報確認、保存重試、取消關閉或完整保存才關閉的契約。

局部驗證：

- 首個真正 Tk/Aqua 裁決提示測試先因缺少提示失敗；加入提示後該 red-green slice 曾通過（2.053 秒）。
- `PYTHONPATH=src /usr/local/bin/python3.8 -m unittest -v tests.test_language_catalog`：8 tests passed。
- `PYTHONPATH=src /usr/local/bin/python3.8 -m py_compile src/b518_log_solution.py src/localized_notice.py src/language_catalog.py tests/test_log_solution_ui.py` 通過。
- `test_open_notice_receives_language_refresh_and_keeps_modal_acknowledgement` 與 `test_close_failure_keeps_window_open_and_real_retry_rebuilds_complete_audit` 在真正 Tk/Aqua 視窗通過（2 tests passed，3.855 秒）。最新截圖中 `st5-notice-dismiss-hint-zh-TW.png` 無系統對話框，但提示由 Tk 事件測試觸發，不能代替實體鍵鼠驗收；Notice EN、Close Retry EN/ZH、Conflict disabled EN/ZH 截圖被 macOS Automation 對話框覆蓋。這些僅是診斷用畫面，不列為接受證據。
- `git diff --check` 通過。

桌面驗收尚未完成：Quartz HID 事件能移動系統游標座標，但本機 macOS Tk/Aqua 進程未收到 `<Motion>`，不能用該注入方式證明實際滑鼠懸停；此為輸入注入限制，不作產品缺陷或功能通過的結論。最近一次 `B518_MANUAL_HOVER=1` 等候 60 秒仍未收到新的實體 Motion，因此沒有產生有效 disabled-hover 中英文證據。已改成先隱藏舊提示、重設游標狀態，再要求新的游標移出／移入事件和可視 tooltip 才能通過；需在真正 App 的 `Same-Round Result Conflict` 視窗中，實際懸停沒有選取 pending conflict 時停用的 `Accept New Candidate`。成功擷取英文提示後不移動游標，切換繁中並擷取更新提示，再驗證停用控制沒有清除衝突或確認警報。無須授予 System Events 權限。

手動桌面驗收命令：

```sh
PYTHONPATH=src B518_TK_TESTS=1 B518_MANUAL_HOVER=1 \
  B518_TK_EVIDENCE_DIR=docs/refactoring/evidence/st5-20261016 \
  /usr/local/bin/python3.8 -m unittest -v \
  tests.test_log_solution_ui.LogSolutionUiTests.test_real_tk_close_keeps_conflict_and_alarm_actions_available
```

輸出 `Move the physical mouse outside the disabled 'Accept New Candidate' button, then hover its center at screen point (x,y) for 0.5 seconds.` 後，先將實體游標移出按鈕再移回中央停留。測試重設先前提示狀態並等新的 Tk motion 確認實體 hover，最多 60 秒；可視 tooltip 文字和 geometry 通過後才擷取。中英文停用提示截圖輸出為 `st5-conflict-candidate-disabled-hint-en.png` 與 `st5-conflict-candidate-disabled-hint-zh-TW.png`。目前同名截圖來自舊測試、帶有 Automation 對話框遮擋，必須成功重拍並人工檢查後才能作證據。ST5 ticket 接受條件維持未勾選。

其他待補的原生畫面包括裁決啟用／關閉／按下、警報確認／關閉、Close Retry 停用／啟用／取消及 Notice 確認，證據名稱列於 ticket 驗收步驟。淺藍 hover 與藍色 focus 框仍是試行方向；沒有宣稱視覺核可。工廠環境另列 ST8。
