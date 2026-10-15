# HM2 本機驗收紀錄

- GitHub issue：#55；票規格：`docs/refactoring/hmi-layout-tickets/02-settings-layout.md`。
- 固定審查基準：`53ccf8574400d1b04e4da2403a6bbe9f30fa68e6`。
- 分支：`codex/hm2-20261015`。
- 執行環境：macOS 15.7.9、Python 3.8.10、Tk/Tcl 8.6（Aqua）。
- 測試設定視窗為 `680x560`。主案例逐頁收集可見的 ttk Label、Button、Entry、Combobox 的 `(widget class, x, y, width, height)`；每一頁切換 English／繁中並比較所有 tuples，三頁均完全相同，且頁籤選取保持不變。這是逐控件 bounds 相等檢查，不是只比較視窗外框。

## 真 Tk 操作

- readonly machine combobox：讀取原值，對下拉箭頭送出 ButtonPress／ButtonRelease 開啟原生 popdown，再送 Down／Return 選擇下一項；確認值改變且仍在允許的 values 內。無產品端鍵盤 workaround。
- 配置草稿：輸入未保存專案名稱、capacity `17`、長路徑 `/deployment/` + 12 個 `long-directory/` + `final-results.csv`；切語言和頁籤後逐值確認草稿仍在。
- 期限：在 retention entry 輸入 `14`，以按鈕 ButtonPress／ButtonRelease 點擊保存，確認生效值為 14，並確認中英切換後顯示仍為 14。
- 輸入欄位白底：`TEntry` `fieldbackground` 為 `#ffffff`。
- 唯讀事件文字：切換語言後閱讀位置約 `0.45`、selection ranges `24.0`–`26.0` 保留，底色為 `#f3f4f6` 且有實線邊框。
- 匯出與匯入：透過設定頁實際 Import／Export controls 操作，僅將檔案對話框結果導向 `TemporaryDirectory` 內的 `profiles.json`；確認檔案建立且匯入回報成功。偏好檔同樣以 `patch(PREFS_PATH, TemporaryDirectory/preferences.json)` 隔離，沒有寫入正式使用者偏好或來源資料。
- Aqua 測試限制：合成 `<KeyPress-space>`／`<KeyRelease-space>` 未觸發 retention Save，故驗收依規格改用按鈕滑鼠事件，不把 `.invoke()` 或合成鍵事件當作真實操作證據。下拉選擇仍保留 Tk popdown 開啟後的 Down／Return 路徑。

## 命令與結果

- `PATH=/opt/anaconda3/bin:$PATH B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py test_log_solution_ui.LogSolutionUiTests.test_settings_layout_is_stable_across_languages_and_keeps_drafts`：1/1 通過（中英 bounds、combobox 選擇、草稿保留、期限保存、匯入匯出、Entry 顏色）。
- `PATH=/opt/anaconda3/bin:$PATH B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py test_log_solution_ui.LogSolutionUiTests.test_settings_layout_is_stable_across_languages_and_keeps_drafts test_log_solution_ui.LogSolutionUiTests.test_english_profile_editor_controls_fit_the_existing_minimum_window test_log_solution_ui.LogSolutionUiTests.test_open_settings_refreshes_language_in_place_and_keeps_invalid_draft test_log_solution_ui.LogSolutionUiTests.test_integrated_language_refresh_keeps_open_settings_diagnostics_and_history`：三個既有回歸 3/3 通過；主案例在改成滑鼠保存前僅因 Aqua 合成 Space 限制失敗，已改走規格所需的滑鼠保存並以單項命令重跑通過。
- `PYTHONPATH=src python3 scripts/run_tests.py test_machine_profiles test_language_catalog`：30/30 通過。
- `python3 -m py_compile src/b518_log_solution.py tests/test_log_solution_ui.py`：通過。
- `git diff --check`：通過。
- 未執行完整測試套件、容量壓力測試或與本票無關的重度測試；未驗收實體工廠設備。
