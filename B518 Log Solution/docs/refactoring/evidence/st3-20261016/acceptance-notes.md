# ST3 真 App 驗收紀錄

環境：macOS、Python 3.8、系統 Tk/Aqua；在正式 B518 Log Solution 主視窗執行滑鼠與鍵盤操作，畫面由該 App 視窗擷取，不是原型或 widget/style lookup。

驗收命令（於 `B518 Log Solution` 專案目錄）：

```sh
PYTHONPATH=src:tests B518_TK_TESTS=1 \
B518_TK_EVIDENCE_DIR=docs/refactoring/evidence/st3-20261016 \
python3 -m unittest -v \
  test_log_solution_ui.LogSolutionUiTests.test_main_page_actions_explain_bilingual_behavior_without_invoking \
  test_log_solution_ui.LogSolutionUiTests.test_toolbar_keyboard_traverses_visual_order_and_leaves_toolbar
```

結果：`Ran 2 tests in 12.242s — OK`。兩項均使用真正 Tk 主視窗；第一項以 Quartz 移動滑鼠、按下／拖離／放開、Tab/Shift+Tab，核對懸停、焦點、按下與停用狀態、提示文字及無焦點搶奪／無意外啟動；第二項回歸驗證頂列鍵盤遍歷。

可檢視的真正主視窗畫面：

- `st3-main-hover-en.png`、`st3-main-hover-zh-TW.png`：Start 中英文滑鼠懸停。
- `st3-main-focus-diagnostics-en.png`、`st3-main-focus-en.png`、`st3-main-focus-zh-TW.png`：焦點狀態的英文及繁中主頁。
- `st3-main-pressed-zh-TW.png`：滑鼠按下狀態。
- `st3-main-disabled-hover-zh-TW.png`：停用 Stop 仍可讀提示；保持灰色且不可按下。
- `st3-window-bounds.json`：主頁控制與 KVM 結果區幾何、Slot 顏色的前後比較資料。

覆蓋四個底部主頁控制 Start、Stop、Retry Save、App Diagnostics 兩種語言；測試同時確認提示不啟動輪次、不搶焦點，Stop 停用時提示用途和不可用原因，滑鼠按下後拖離並放開不執行 Start。語言變更會即時更新已顯示提示；離開仍聚焦的按鈕時焦點提示保留。主頁八個操作入口及後續動態／停用控制盤點見 `button-coverage.md`。

淺藍 hover 與藍色焦點框是供檢視的試行方向，沒有記錄為使用者接受或核可。工廠桌面環境尚未驗證，留待工廠驗收。
