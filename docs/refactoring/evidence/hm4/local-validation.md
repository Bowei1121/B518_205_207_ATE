# HM4 歷史與診斷視窗驗收紀錄

## 固定基準

- Ticket #57 固定 review base：`b513c78981159ac1fbfbd67c797ddfcf93ab5080`。
- 實作範圍：歷史查詢與 App 診斷視窗；未修改查詢演算法或資料契約。

## 實作與驗收覆蓋

- 歷史與 App 診斷視窗加大並固定最小尺寸；日期標籤、分頁列、等寬結果／詳細欄，以及查詢／取消按鈕預留固定空間。
- 長事件列可用水平與垂直捲動；詳細與診斷文字維持垂直捲動、淺灰底、細黑框；可輸入日期欄仍使用白底。
- App 診斷重試與關閉按鈕隨語言更新。歷史與診斷列在切語言時保留選取及水平／垂直閱讀位置；歷史結果、日期草稿、分頁、查詢世代與選取詳細沿用原狀態刷新路徑。
- 真 Tk 驗收案例使用臨時 round audit、legacy event 與 App event，加入 malformed legacy line 以操作來源異常頁；切換中英並檢查幾何、bounds、日期草稿、查詢快照、選取、讀取位置、原始 bytes 與診斷按鈕標籤。
- 設定 `B518_TK_EVIDENCE_DIR` 時，驗收案例保存歷史事件、來源異常及 App 診斷視窗的中英 Aqua 截圖與 bounds／source SHA-256 JSON。

## 執行狀態

- `python3 -m py_compile "B518 Log Solution/src/b518_log_solution.py" "B518 Log Solution/tests/test_log_solution_ui.py"` — 通過。
- `git diff --check` — 通過。
- `B518_TK_TESTS=1 B518_TK_EVIDENCE_DIR=docs/refactoring/evidence/hm4/screenshots python3 "B518 Log Solution/scripts/run_tests.py" test_log_solution_ui.LogSolutionUiTests.test_real_tk_history_language_refresh_preserves_draft_snapshot_page_and_detail` — 真 Tk 桌面驗收通過（1 測例，9.650 秒）。
- `B518_TK_TESTS=1 python3 "B518 Log Solution/scripts/run_tests.py" test_log_solution_ui.LogSolutionUiTests.test_app_diagnostics_scroll_position_survives_language_refresh` — 真 Tk 診斷列表切語言捲動回歸通過（1 測例，1.105 秒）。
- 歷史查詢／顯示／容量／輪次保留相關非 Tk 回歸通過（99 測例，30.750 秒）。
- 驗收產生中英雙語歷史事件、來源異常、App 診斷共 6 張 Aqua 視窗截圖，以及 `screenshots/window-bounds.json` 的視窗／控制項 bounds 和三份來源 SHA-256。測例比較來源 bytes，確認切語言及查詢後原始檔未變。
