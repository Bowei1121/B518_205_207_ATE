# HC3 固定視窗驗收

驗收入口為正式 Tk/Aqua App。啟動時計算一次固定視窗高度：以畫面可用區（macOS `NSScreen.visibleFrame`）、主畫面控制項的實際需求高度、列高 33 Tk px、32 px 視窗裝飾保留量及上下各 8 px 邊界間距決定可視列數。裝飾保留量比本機量到的 28 px 多留 4 px。計算不讀取測試容量。後續容量、語言、長狀態與計時更新都沿用該視窗和表格可視區。

## 實測尺寸與支援條件

| 螢幕可用尺寸 | Tk 視窗 | macOS 原生視窗 | 可視列 | 結果 |
| --- | --- | --- | ---: | --- |
| 1440×900，頂部系統保留 25 px | 376×797，位置 +1052,+33 | 376×825，含 28 px 標題列 | 9 | 正常尺寸；容量 1／10／11／20 與中英文幾何一致 |
| 1152×720，頂部系統保留 25 px | 376×632，位置 +764,+33 | 376×660，含 28 px 標題列 | 4 | 小螢幕實際驗收通過，開始、狀態、計時、停止及診斷操作完整可見 |

本次控制項實際需求高度為 500 Tk px，計入一個 33 px 通道列、32 px 裝飾保留量、上下各 8 px 邊界及本機系統保留區後，最低支援高度為 606 px。此門檻依目前 macOS/Tk/Aqua、14 pt 字體、佈景與控制項需求成立；若字體或控制項需求增高，程式會以新量測值提高門檻。固定寬度為 376 px，含右側 12 px 邊界的適用寬度至少 388 px。低於門檻的螢幕不列為支援條件。

主畫面量測使用 `NSScreen.visibleFrame` 排除系統保留區；本機兩種螢幕高度的頂部保留均為 25 px、底部為 0 px。原生視窗比 Tk client 高 28 px，程式採 32 px 保留。1152×720 是本機可用的實際顯示模式；測試切換後確認恢復為原本的 1440×900。

## 間距前後比較

改版前使用已合併 HC2 commit `dc79be1` 的原始 UI 程式，在同一台 1440×900 螢幕量測；改版後使用真 App 截圖與元件座標。容量 1 的表格到開始鍵間距從 99 px 降到 4 px；容量 10 從 33 px 降到 4 px；容量 11／20 也從 33 px 降到 4 px。減幅約 88% 至 96%，超過減半目標。所有容量的新間距相同，少量通道留下的空間位於表格背景內，不計入表格外間距。

改版前主視窗高度會隨容量在 606／804／831 px 間改變，KVM 色帶也在 61／88 px 間切換。改版後四種容量皆為 376×797，KVM 色帶固定 88 px；開始鍵、狀態與計時座標完全相同。容量 1 仍只建立一個通道列。完整座標列在 [`hc3-before-after-geometry.json`](hc3-before-after-geometry.json)。

## 真 App 證據

- [`hc3-layout-matrix.json`](hc3-layout-matrix.json)：正常螢幕的四種容量、雙語幾何、桌面資訊與原生視窗邊界。
- [`hc3-startup-capacity-matrix.json`](hc3-startup-capacity-matrix.json)：分別用 1／10／11／20 通道啟動 App 的真實視窗幾何。
- [`hc3-small-display.json`](hc3-small-display.json)：1152×720 小螢幕尺寸及原生視窗邊界。
- 容量 1 繁中：[截圖](hc3-capacity-1-zh-TW.png)；容量 10 英文：[截圖](hc3-capacity-10-en.png)；容量 11 繁中：[截圖](hc3-capacity-11-zh-TW.png)；容量 20 英文：[截圖](hc3-capacity-20-en.png)；1152×720：[截圖](hc3-small-display-en.png)。

驗收執行環境：macOS、Python 3.12.10、Tk/Aqua；正常矩陣及 1152×720 實際顯示模式均通過。小螢幕測試結束後已還原顯示模式。真實 JetKVM 接收端與不同型號外接顯示器不在本票本機 UI 驗收範圍。

`B518_TK_TESTS=1 PYTHONPATH=src .venv-python31210/bin/python scripts/run_tests.py` 完整執行 583 項，結果 5 項失敗、4 項略過。當中一項 LI7 幾何測試仍預期低容量色帶為 61 px，已更新為 HC3 固定 88 px 並單獨通過。其餘四項失敗案例單獨重跑時，三項非本票 UI 案例通過；只有 `test_query_snapshot_pages_all_events_and_loads_detail_only_on_request` 的 `audit.flush()` 仍單獨失敗，該案例不使用 HMI。全套測試在長時間桌面 Tk 執行後也有非確定性逾時，因此不宣稱全套通過。
