# LI6 真正桌面驗收 / LI6 Real Desktop Acceptance

日期：2026-10-19（Asia/Taipei）
環境：macOS、Python 3.11.7、Tk 8.6.12、PyObjC/AppKit、Quartz。
視窗：真正的 `B518LogSolutionApp` Tk 主視窗與另一個本機 Tk 測試視窗；Quartz `CGWindowListCopyWindowInfo` 讀取實際視窗堆疊，Tk `focus_get()` 讀取焦點控制項。

執行命令：

```sh
B518_TK_TESTS=1 B518_TK_EVIDENCE_DIR="$PWD/docs/refactoring/evidence/li6-foreground" /opt/anaconda3/bin/python3 scripts/run_tests.py test_li6_foreground
```

結果：`Ran 1 test ... OK`。逐事件觀測及截圖清單見 `run.json`；截圖為同次通過執行所產生。

已驗收：

- 批次開始監控、可信 `TESTING` 狀態令 Log 視窗浮到另一視窗上方，焦點仍在另一視窗的 Entry，`topmost=false`。
- 輪詢相同狀態不會再次提升視窗。
- PASS 結果更新、正常完成、人工停止、TIMEOUT 完成均提升視窗且不改焦點。
- 最小化後的 Log 視窗可恢復至另一視窗上方，同時 Entry 保持焦點且未設永久置頂。
- 舊輪次事件不會提升視窗。
- 注入原生視窗查找錯誤時會記錄雙語 App event 與原始診斷，結果列仍更新為 FAIL。

相鄰回歸命令：

```sh
/opt/anaconda3/bin/python3 scripts/run_tests.py test_language_catalog test_monitoring_round
```

結果：`Ran 71 tests ... OK`。
