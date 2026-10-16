# HF6 桌面驗收證據

## 修復前重現

- `baseline/hf6-baseline-before-first-cleanup-completes-en.png`（執行機器暫存目錄）：清理摘要文字模型有 789 字元、元件已映射，但原生 Aqua 畫面為空白。
- `baseline/hf6-baseline-after-three-poll-cycles-en.png`（執行機器暫存目錄）：同一內容經三次既有輪詢後 scrollbar 位置從約 0.923 移至 1.0。
- 根因已在原生視窗確認：Text 建立在內容 Frame 下，卻用 `grid(in_=cleanup_output)` 放到後建立的 sibling Frame；Aqua 將後建立的 Frame 繪製在 Text 上方。暫時將 Text `raise` 到覆蓋層上方後文字立即顯示。修復已將 Text 直接建立為 `cleanup_output` 子元件。

修復前證據位於執行機器 `/private/tmp/B518-hf6-acceptance/baseline/` 與 `baseline-diagnostic/` 暫存目錄，未複製進版控；其 JSON 與截圖來自真正 Tk/Aqua 視窗。

## 修復後畫面

- [hf6-cleanup-render-en.png](hf6-cleanup-render-en.png)：真正 App 的英文 Retention 設定頁，包含完成摘要、清理結果、原始診斷及 scrollbar。
- [hf6-cleanup-render-zh-TW.png](hf6-cleanup-render-zh-TW.png)：同一 App 切換繁體中文後的畫面與本地化摘要。
- [hf6-cleanup-empty-en.png](hf6-cleanup-empty-en.png) 與 [hf6-cleanup-empty-zh-TW.png](hf6-cleanup-empty-zh-TW.png)：真正 App 介面中的雙語明確空狀態。
- [hf6-window-bounds.json](hf6-window-bounds.json)：擷取時原生視窗尺寸及摘要控件位置。

測試在同一個真正 App 視窗中等待清理完成後，觀察多個 150ms 更新週期；摘要內容、頂端閱讀索引及選取均保持不變。接著切換語言、擷取兩種語言的有內容與空狀態畫面，驗證 80 行長診斷可捲動；內容縮短重繪後位置仍是合法範圍，關閉並重開設定頁後摘要與 scrollbar 仍可用。

## 指令與結果

使用 macOS Framework Python 3.8.10、Tcl/Tk 8.6 的原生 Aqua 桌面：

```sh
B518_TK_TESTS=1 B518_TK_EVIDENCE_DIR="$PWD/docs/refactoring/evidence/hmi-followup-2026-10-16/hf6" \
  ./scripts/run_macos_desktop.sh scripts/run_tests.py \
  test_log_solution_ui.LogSolutionUiTests.test_cleanup_summary_is_visibly_drawn_in_the_real_settings_window
```

結果：1 項通過。

```sh
B518_TK_TESTS=1 ./scripts/run_macos_desktop.sh scripts/run_tests.py \
  test_log_solution_ui.LogSolutionUiTests.test_real_tk_reads_mixed_cleanup_reason_ledger_and_keeps_raw_evidence_read_only \
  test_log_solution_ui.LogSolutionUiTests.test_real_tk_global_retention_setting_validates_persists_and_preserves_round_files \
  test_log_solution_ui.LogSolutionUiTests.test_real_tk_shows_startup_cleanup_summary_after_disk_deletion \
  test_log_solution_ui.LogSolutionUiTests.test_cleanup_summary_is_visibly_drawn_in_the_real_settings_window \
  test_log_solution_ui.LogSolutionUiTests.test_real_tk_app_event_cleanup_failure_is_visible_and_retryable \
  test_log_solution_ui.LogSolutionUiTests.test_real_tk_localizes_timezone_missing_app_event_cleanup_reason \
  test_log_solution_ui.LogSolutionUiTests.test_real_tk_cleanup_status_shows_captured_reason_details_during_close
```

結果：7 項通過，涵蓋實際清理結果、原因本地化、原始證據、保存資料保護、失敗狀態及重試。另執行 `python3 scripts/run_tests.py test_round_retention`，36 項通過。工廠現場驗收未在此環境執行。
