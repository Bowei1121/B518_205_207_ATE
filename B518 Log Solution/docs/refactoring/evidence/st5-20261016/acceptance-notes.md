# ST5 驗收紀錄（2026-10-16）

工作分支 `codex/st5-adjudication-alert-close-hints` 起於整合基準 `c8eb613fb179ad41157e724026d240d0f4c0d0ce`。ST5 將雙語提示擴至人工裁決、整輪警報、關閉前保存及 App 確認訊息，保留人工裁決、警報確認、保存／封存重試、取消關閉與完整保存才關閉的既有契約。GitHub Issue 寫入依使用者指示暫不處理。

## 真實 App 驗收

- 真 Tk/Aqua 視窗 `Same-Round Result Conflict` 與 `Round Monitoring Timeout` 已在 macOS 桌面開啟；使用者將實體滑鼠移出停用的 `Accept New Candidate` 後，移回按鈕中心停留 0.5 秒。測試觀察到新的 Tk `<Motion>`，不是合成滑鼠事件。
- 英文及繁體中文提示均在真正 App 視窗中可見並截圖；畫面沒有系統權限對話框遮擋提示：
  - `st5-conflict-candidate-disabled-hint-en.png`：`Select a pending conflict before choosing a result.`
  - `st5-conflict-candidate-disabled-hint-zh-TW.png`：`請先選取一筆待確認衝突，再選擇結果。`
- 滑鼠懸停後點擊停用按鈕，pending conflict 仍存在、round alarm 仍未確認；測試通過。畫面保留真實警報視窗與衝突視窗，也顯示完整提示及停用狀態按鈕。
- 螢幕顏色方向仍屬試行；淺藍 hover／藍色 focus 框尚未取得使用者視覺核可。

## 自動化與回歸驗證

使用真正 Tk/Aqua 手動懸停測試：

```sh
PYTHONPATH=src B518_TK_TESTS=1 B518_MANUAL_HOVER=1 \
  B518_TK_EVIDENCE_DIR=docs/refactoring/evidence/st5-20261016 \
  /usr/local/bin/python3.8 -m unittest -v \
  tests.test_log_solution_ui.LogSolutionUiTests.test_real_tk_close_keeps_conflict_and_alarm_actions_available
```

結果：`Ran 1 test in 50.375s — OK`。此測試實際展示輪次警報及衝突；確認停用提示可見、停用按鈕點擊不會接受候選結果或清除衝突，也不會確認警報。

- `tests.test_language_catalog`：8/8 通過。
- Notice 語言更新及 close/save retry 真 Tk/Aqua 測試：2/2 通過。
- 輪次、封存及啟動準備回歸：74/74 通過。
- `py_compile` 與 `git diff --check` 通過。

## 範圍與未驗證環境

- 本機真實懸停畫面已補齊雙語停用裁決提示。既有診斷截圖中被 macOS Automation 權限提示遮擋的 Notice、Close Retry 畫面不列為本次接受證據；不需要授予 System Events 權限。
- 工廠桌面、產線 KVM 與實際工廠資料流程尚未驗收，留待 ST8／工廠驗收。
