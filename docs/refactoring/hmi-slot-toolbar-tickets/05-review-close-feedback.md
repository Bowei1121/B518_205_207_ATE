## Parent

https://github.com/Bowei1121/B518_205_207_ATE/issues/68

## What to build

操作員在裁決、警報、關閉保存及 App 提示視窗能理解每個按鈕效果，且浮動說明不改變原人工確認與保存保障。

## Acceptance criteria

- [ ] 盤點並套用 ST3 能力至待確認裁決、警報、關閉保存及其他 App 自有提示視窗，包含動態按鈕；更新覆蓋清單。
- [ ] 提供準確雙語功能、效果、適用快捷鍵及已知停用原因；保留必要短標籤與原啟用條件，不變更 Tab 可達性政策。
- [ ] 真正滑鼠與鍵盤驗證焦點／懸停並存、按下釋放、啟用轉換，浮動說明不搶焦點、不按鈕、不自動確認或重試。
- [ ] 驗證裁決與警報仍需原人工動作，開提示不清除事項；關閉保存仍等待全部應保存資料，可重試或取消關閉。
- [ ] 提示隨語言及原因變化更新，語言切換遵守關閉保存限制；視窗關閉／控制銷毀／重開後無殘留浮窗或回呼錯誤，原選取與輸入不被清除。
- [ ] 提供真正 App 兩語畫面與操作證據，明記實測環境，不以私有呼叫次數替代外部行為驗證。

## 2026-10-16 本機執行紀錄（進行中）

- 分支 `codex/st5-adjudication-alert-close-hints` 從整合基準 `c8eb613fb179ad41157e724026d240d0f4c0d0ce` 開始；本次未讀寫 GitHub Issue。
- 已在共用提示系統加入裁決、警報、關閉保存與確認訊息的雙語效果說明；未選取衝突、警報未就緒／已確認、關閉保存尚未失敗等狀態提供已知原因。沒有更改人工裁決、警報確認、重試／取消或完整保存才關閉的業務流程。
- TDD 首個真實 Tk 裁決提示測試先以缺少 hover 提示失敗，實作後通過；語言資源測試 8 項通過，`py_compile` 通過。
- `test_open_notice_receives_language_refresh_and_keeps_modal_acknowledgement` 與 `test_close_failure_keeps_window_open_and_real_retry_rebuilds_complete_audit` 真正 Tk/Aqua 測試通過（2 tests passed）；當次截圖被 macOS Automation 視窗覆蓋，已清除，不能作交付證據。
- Quartz HID 注入曾移動系統游標座標，但 Tk/Aqua 沒有收到 `<Motion>`，因此自動注入不能證明實際 hover；這是桌面輸入注入限制，不記為產品缺陷或驗收通過。已準備 `B518_MANUAL_HOVER=1` 路徑，讓操作者實體懸停於未選取 conflict 狀態的停用 `Accept New Candidate`，擷取英文提示，保持游標位置切換繁中後擷取更新提示，並確認停用控制不改變衝突／警報狀態。無需授予 System Events 權限：

  ```sh
  PYTHONPATH=src B518_TK_TESTS=1 B518_MANUAL_HOVER=1 \
    B518_TK_EVIDENCE_DIR=docs/refactoring/evidence/st5-20261016 \
    /usr/local/bin/python3.8 -m unittest -v \
    tests.test_log_solution_ui.LogSolutionUiTests.test_real_tk_close_keeps_conflict_and_alarm_actions_available
  ```

- 淺藍 hover 與藍色 focus 框仍是試行方向；此票未宣稱視覺核可。工廠環境另列 ST8。

## 規格對照與共同契約

使用者故事：28、29、30、31、32、33、34、35、36、37、38、39、40、41、42、43、48、50、51、52。

沿用已確認真正 App／Tk 操作入口與既有公開輪次情境，不新增專供測試的業務接口，不把未提交暫稿當成已完成。保留 KVM 幾何與色彩、人工裁決、警報確認、雙語更新、保存及正常關閉保障。提供對應真正繁中／英文畫面與行為驗證，記錄已測環境；工廠驗收另列，不阻擋已完成程式與桌面驗證的整合。
