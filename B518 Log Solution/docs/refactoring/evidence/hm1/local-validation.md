# HM1 本機驗收紀錄

- 固定審查基準：`31d08141add7bf9a936e701d99f193455bf40ede`
- 分支：`codex/hm1-20261015`
- 驗收範圍：GitHub #54，主頁工具列、識別標題與操作區狀態。

## 已完成的非 Tk 檢查

- `python3 -m py_compile src/b518_log_solution.py src/language_catalog.py tests/test_log_solution_ui.py tests/test_language_catalog.py`：通過。
- `zsh -n scripts/build_macos10_14_log_solution.sh scripts/build_macos15_arm64_log_solution.sh scripts/build_macos26_arm64_log_solution.sh`：通過。
- `python3 scripts/run_tests.py test_language_catalog test_kvm_display_contract test_verify_macos_bundle`：33 項通過。
- `git diff --check`：通過。
- 三個 macOS build 命令都會將根目錄 `VERSION` 隨 App 打包；Logo 沿用既有 `assets` 打包路徑，原始 137×35 PNG 未修改。

## 真 Tk 驗收

- 執行環境：macOS 15.7.9、Python 3.8.10、Tk/Tcl 8.6。
- Logo SHA-256：`e4db8e4abbc5156448e8e50913ab4485b8705cb50c0132a54382895c5fa14e21`；測到的原圖尺寸 137×35，程式使用同一資產，不裁切或重繪。
- 命令：`B518_TK_TESTS=1 python3 scripts/run_tests.py test_log_solution_ui.LogSolutionUiTests.test_hm1_toolbar_title_status_and_kvm_geometry_stay_fixed test_log_solution_ui.LogSolutionUiTests.test_real_tk_language_and_profile_controls_fit_fixed_hmi_width test_log_solution_ui.LogSolutionUiTests.test_real_tk_language_menu_switches_main_page_and_persists_across_app_instances`
- 結果：3/3 通過。真 Tk 檢查主視窗 376px、四圖示操作鈕、0 與 20 待確認數、英文／繁中切換、語言選單持久偏好、主標題配置更新與狀態數量文字；切換前後工具列 bounds 一致，KVM 區、定位標記、狀態標記與20格 bounds 完全相同。既有定位標記真 Tk 座標 `(278, 0)` 亦通過。
- 規格補充命令：`B518_TK_TESTS=1 python3 scripts/run_tests.py test_log_solution_ui.LogSolutionUiTests.test_hm1_toolbar_title_status_and_kvm_geometry_stay_fixed test_log_solution_ui.LogSolutionUiTests.test_hm1_logo_normal_missing_and_corrupt_keep_fixed_slot_without_dialog`
- 規格補充結果：2/2 通過。四個圖示 hover tooltip 顯示 Settings、Select language (current: English)、Round Alarm (Awaiting Review)、Awaiting Review (0)；設定提示亦可由 focus 顯示。以真 Tk `<KeyPress-space>`/`<KeyRelease-space>` 從鍵盤開啟 Settings；語言按鈕有 Space、Return、Down 綁定。滑鼠點擊開啟裁決與整輪警報視窗。正常、缺失、損壞 Logo 的 slot 均為固定 137×35，三態的 slot/工具列 bounds 相同；缺失/損壞不顯示替代文字或彈窗。
- 共用提示生命週期回歸命令：`B518_TK_TESTS=1 python3 scripts/run_tests.py test_log_solution_ui.LogSolutionUiTests.test_hm1_toolbar_title_status_and_kvm_geometry_stay_fixed test_log_solution_ui.LogSolutionUiTests.test_hm1_logo_normal_missing_and_corrupt_keep_fixed_slot_without_dialog test_log_solution_ui.LogSolutionUiTests.test_real_tk_history_hover_hint_updates_language_and_closes_with_window`
- 共用提示生命週期結果：3/3 通過。工具列與歷史按鈕共用同一提示元件，驗證 hover/focus、語系即時更新、禁用時自動收起，以及單獨按鈕與 App/Toplevel 銷毀時清除提示與排程；保留歷史提示既有語系更新回歸。
- 標題與長計數最新真 Tk 命令：`B518_TK_TESTS=1 python3 scripts/run_tests.py test_log_solution_ui.LogSolutionUiTests.test_hm1_toolbar_title_status_and_kvm_geometry_stay_fixed test_log_solution_ui.LogSolutionUiTests.test_hm1_logo_normal_missing_and_corrupt_keep_fixed_slot_without_dialog test_log_solution_ui.LogSolutionUiTests.test_real_tk_history_hover_hint_updates_language_and_closes_with_window test_log_solution_ui.LogSolutionUiTests.test_integrated_language_refresh_keeps_open_settings_diagnostics_and_history`
- 標題與長計數結果：4/4 通過。設定視窗依語系顯示 `Setting`／`設定`；review count 固定寬度 8，在 376px 視窗顯示 `1234567` 且文字測量寬度完整，數字切換前後 review group、工具列與 KVM bounds 不變。
- 只跑上述指定桌面案例，未跑完整套件、容量壓力或歷史大資料測試。未做實體 KVM、工廠設備或已簽章正式 bundle 驗收；bundle 的資產路徑檢查限於三個現有 build script 均打包 `assets`，本次新增 `VERSION` 資源亦已列入打包命令。
