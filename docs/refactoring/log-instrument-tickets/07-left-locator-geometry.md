## Parent

[父規格 #77：Log Solution 儀器狀態、人工停止與顯示契約 1.2](https://github.com/Bowei1121/B518_205_207_ATE/issues/77)

## What to build

移除KVM RESULT文字、將左定位點移到第一格色帶正上方，保留其他元素位置，量測出唯一可重現的新座標與本機畫面證據。

這是可獨立完成的顯示幾何切片，不等待輪次業務票，也不在本票宣告整套1.2完成；最終六狀態與幾何共同檢查由LI8完成。

主責使用者故事：72, 73, 74, 75, 76。
依父規格實作決策：21, 22；測試決策：12, 13。

本票只驗收本程式的公開輪次行為／磁碟資料與必要真App／Tk輸出；不要求KVM_Log、JetKVM或LabVIEW驗收。

## Acceptance criteria

- [x] KVM RESULT字樣移除且不移到其他位置；左定位點左緣與第一格色帶左緣同為x=0，左右維持22×22及同高，內嵌白格保持左右不對稱。
- [x] 定位點四周至少2 Tk單位白留白，父框不裁切、各標記不重疊；父框實測起點為x=8、定位點為父框內(x=0,y=2)，其與第一格同左緣，定位點完整落在360 Tk單位寬父框中。真Tk contentView畫面及bounds見[LI7幾何證據](../evidence/li7-geometry/README.md)。
- [x] 右定位點、排數格、狀態格、色帶的既有位置及顏色不移動；維持每排十格、一／兩排與容量外黑格。
- [x] 條件式阻擋項不適用：所有幾何約束均成立。左定位點x=0且完整位於寬360 Tk單位父框內；root提供8單位左留白，真Tk畫面及bounds已證明沒有裁切，無需移動其他契約元素。
- [x] Tk scaling1.0／1.5、容量1／10／11／20及正常容量切換，以真正App／Tk擷取及bounds量測驗證；Tk單位與實體像素分列。可見Profile Editor中逐一編輯容量/mapping、按Apply並重載偏好檔驗證持久化；20→1亦走正常Apply流程。授權桌面矩陣與八張畫面見[LI7幾何證據](../evidence/li7-geometry/README.md#執行方式與矩陣)。舊版直接替換profile catalog的根目錄畫面僅供幾何參考，正式驗收採用`escalated-desktop-20261019/`。
- [x] 凍結座標：左(0,2)、右(320,2)，原點距離320、外緣跨度342；左locator 22×22，白格(3,3) 8×8，內部黑邊距(左/上/右/下)=(3/3/11/11)。每邊至少2 Tk單位的外部淨空已量測，且父框未裁切。比例為每Tk內容單位2.0×2.0實體像素；Tk scaling讀值分別約1.0及1.4985。逐組bounds與畫面見證據README及JSON。
- [x] 上方定位點無法保證偵測所有僅遮色帶的視窗形狀；本票不依賴外部consumer或實際KVM判讀驗收。

### 驗證紀錄

- `PYTHONPATH=src /opt/anaconda3/bin/python3 -m unittest tests.test_kvm_display_contract`：通過。
- 舊版矩陣的8張圖由測試直接替換profile catalog產生，只作幾何參考，不算正常Profile Editor儲存/切換驗收。sandbox中的GUI重跑遇到LaunchServices/hiservices XPC `Connection Invalid`及AppKit root初始化中止，這是sandbox沒有Aqua GUI session的環境限制，不是程式測試失敗。
- 授權桌面完整Profile Editor矩陣命令：`B518_TK_TESTS=1 B518_TK_EVIDENCE_DIR=docs/refactoring/evidence/li7-geometry/escalated-desktop-20261019 PYTHONPATH=src /opt/anaconda3/bin/python3 -X faulthandler -m unittest tests.test_log_solution_ui.LogSolutionUiTests.test_li7_geometry_at_both_scalings_and_all_capacities`：`Ran 1 test in 7.788s / OK`。成功輸出8份JSON與8張view-cache PNG，驗證scaling 1.0/1.5、容量1/10/11/20、profile持久化及20→1切換。
- Merger worktree重跑：`B518_TK_TESTS=1 B518_TK_EVIDENCE_DIR=docs/refactoring/evidence/li7-geometry/merger-retest-20261019 PYTHONPATH=src /opt/anaconda3/bin/python3 -X faulthandler -m unittest tests.test_log_solution_ui.LogSolutionUiTests.test_li7_locator_is_visible_at_first_cell_with_fixed_other_geometry tests.test_log_solution_ui.LogSolutionUiTests.test_li7_geometry_at_both_scalings_and_all_capacities`：`Ran 2 tests in 6.816s / OK`。八組矩陣與畫面見[重跑證據](../evidence/li7-geometry/merger-retest-20261019/)。
- AppKit contentView bitmap cache 可讀並呈現執行中的Tk畫面；它不是WindowServer螢幕截圖。Quartz window capture曾產生黑圖，`screencapture -x` 回報 `could not create image from display 69734272`，因此不將其作為有效畫面證據。環境與證據細節見證據README。
- sandbox重跑 GUI 測試時，LaunchServices/hiservices XPC回報 `Connection invalid`，Tk在建立首個root期間由AppKit原生中止；改在授權桌面 Aqua session 執行後矩陣通過，因此判定為sandbox環境限制。Quartz window capture黑圖及`screencapture -x`限制記錄於證據README；驗收使用已目視確認可讀的真Tk contentView快取圖。

## Blocked by

None (can start immediately)
