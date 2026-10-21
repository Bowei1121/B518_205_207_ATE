# HC2 真 App 表格驗收

環境：macOS、Python 3.12.10、正式 B518 Log Solution Tk/Aqua 主視窗。以測試入口暫時切換至 1650×1050 顯示模式，測完恢復原本 1440×900；截圖由 Window Server 擷取真 App 視窗。

執行命令（於 `B518 Log Solution` 專案目錄）：

```sh
B518_TK_TESTS=1 B518_ST1_LARGE_DESKTOP=1 \
B518_TK_EVIDENCE_DIR=docs/refactoring/evidence/hc2-20261021 \
PYTHONPATH=src:tests .venv-python31210/bin/python -X faulthandler \
  scripts/run_tests.py test_slot_toolbar_st1
```

結果：`Ran 2 tests — OK`。矩陣涵蓋 1、10、11、20 個通道，中英文，1200 與 650 高度請求；20 通道於 Tk scaling 1.0 與 1.5 另行擷取表格頂端及末端畫面。

| 驗收 | 證據 |
| --- | --- |
| 超過十列、四種結果色、SN 與黑色格線；Tk 1.0 | [表格頂端](hc2-cap20-scale-1.0-top-zh-TW.png)、[最後完整列](hc2-cap20-scale-1.0-bottom-zh-TW.png) |
| 同樣檢查；Tk 1.5 | [表格頂端](hc2-cap20-scale-1.5-top-zh-TW.png)、[最後完整列](hc2-cap20-scale-1.5-bottom-zh-TW.png) |
| 1／10／11／20 個通道，中英文與可捲動視窗 | [截圖矩陣](st1-matrix.json)，同目錄 `st1-cap*-h*-*.png` |

量測見 [hc2-scaling-measurements.json](hc2-scaling-measurements.json)：列內容高 32 Tk px，14pt 字體需求高 22 Tk px；橫線與兩條內直線各 1 Tk px（本機 Retina 截圖為 2 個實體像素）。Tk 1.0／1.5 均一次完整顯示 14 列；捲到底後第 20 列完整可見，scroll view 為 `[0.3, 1.0]`。狀態色 PASS、FAIL、TESTING、NOTEST 與 SN 呈現均由真 App 畫面及斷言核對。
