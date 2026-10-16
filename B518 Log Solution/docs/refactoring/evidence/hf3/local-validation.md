# HF3 桌面驗收紀錄

日期：2026-10-16（Asia/Taipei）

## 環境與方法

- 真實 macOS Tk 桌面，`/Library/Frameworks/Python.framework/Versions/3.8/bin/python3`，Tk 8.6.8。
- 測試透過真正的 `B518LogSolutionApp`、`RoundCoordinator`、`BaseMonitor` 與暫存 Session 目錄執行；不直接設定徽章計數或 Canvas 文字。
- 每輪以 Session `events.log` append 注入 OSError，經 App 的保存重試及 coordinator archive retry 恢復；另以一次性 `write_round_archive` OSError 實測已保存輪次的封存失敗與恢復。
- `window-bounds.json` 保存實際視窗與 widget bounds；雙語 PNG 是 Quartz 擷取的已映射 Tk 視窗。

## 驗收結果

- 起始一般進行中輪次顯示 0；待確認整輪警報 + 同輪保存故障顯示 2；確認警報後剩 1。相同輪次多次保存失敗仍只算一輪。
- 另外建立 10 個獨立失敗輪次，主畫面真實顯示 12。紅底白字徽章位於鈴鐺右上方；雙位數未遮住 🌐、review 計數或 KVM 區域。
- 封存寫入故障時該輪 `save_state=complete`、`archive status=failed`，仍只貢獻 1；通知中心顯示封存失敗診斷和可用的封存重試按鈕。封存成功後計數遞減；其餘輪次完成保存及封存後徽章隱藏，歷史保存證據仍存在。
- 對徽章右側原鈴鐺範圍外點擊不開視窗；原鈴鐺範圍內的重疊區仍開啟通知中心。HF1 頂列鍵盤順序與 KVM/header 幾何不變。

## 執行命令與結果

```sh
B518_TK_TESTS=1 B518_TK_EVIDENCE_DIR=/private/tmp/B518-hf3-notification/evidence \
  /Library/Frameworks/Python.framework/Versions/3.8/bin/python3 \
  'B518 Log Solution/scripts/run_tests.py' \
  test_log_solution_ui.LogSolutionUiTests.test_real_tk_notification_badge_stays_until_alarm_is_acknowledged \
  test_log_solution_ui.LogSolutionUiTests.test_hm1_toolbar_title_status_and_kvm_geometry_stay_fixed \
  test_log_solution_ui.LogSolutionUiTests.test_toolbar_keyboard_traverses_visual_order_and_leaves_toolbar
```

結果：`Ran 3 tests in 15.315s — OK`。`git diff --check` 通過。

## 畫面證據

- 同輪警報 + 保存錯誤：`hf3-count-two-en.png`、`hf3-count-two-zh-TW.png`
- 12 輪多位數徽章：`hf3-twelve-save-rounds-en.png`、`hf3-twelve-save-rounds-zh-TW.png`
- 封存失敗徽章：`hf3-archive-failure-en.png`、`hf3-archive-failure-zh-TW.png`
- 封存失敗診斷與重試入口：`hf3-archive-recovery-en.png`、`hf3-archive-recovery-zh-TW.png`；狀態資料見 `hf3-archive-failure-status.json`
- 復原後徽章隱藏：`hf3-zero-en.png`、`hf3-zero-zh-TW.png`
- 點擊前後計數畫面：`hf3-one-save-failure-en.png`、`hf3-one-save-failure-zh-TW.png`

## 未涵蓋

未在工廠產線或客戶部署環境執行驗收；需要現場操作條件的工廠驗收仍由現場另行確認。
