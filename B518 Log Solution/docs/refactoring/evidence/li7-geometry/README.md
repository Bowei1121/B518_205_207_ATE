# LI7 真 Tk 幾何驗證

這組驗證在 macOS 上以 `/opt/anaconda3/bin/python3`（Python 3.11.7、Tk 8.6）啟動真正的 B518 Log Solution Tk App。測試透過正常 profile 選擇資料改變容量，並檢查實際 widget bounds、父框尺寸、顏色與未配置格的狀態。

## 執行方式與矩陣

```sh
B518_TK_TESTS=1 B518_TK_EVIDENCE_DIR=docs/refactoring/evidence/li7-geometry PYTHONPATH=src /opt/anaconda3/bin/python3 -m unittest tests.test_log_solution_ui.LogSolutionUiTests.test_li7_geometry_at_both_scalings_and_all_capacities
```

共產生8組畫面及JSON：Tk scaling 1.0與1.5各搭配容量1、10、11、20。測試逐格切換容量，最後再以正常 profile 更新路徑將20切回1，確認單排/雙排父框尺寸跟著切換。1.0與1.5下幾何均一致；實際Tk scaling讀值約為1.0000、1.4985。

測試支援以 `B518_LI7_SCALING=1.0` 或 `1.5` 將兩種縮放分成獨立程序重跑。驗收矩陣的有效輸出來自上方不帶此filter的一次成功執行。之後重跑時，macOS LaunchServices/hiservices XPC 回報 `Connection invalid`，Tk 在建立第一個 root 時於 `NSMenuItem initWithTitle:action:keyEquivalent:` 以 `Invalid parameter not satisfying: aString != nil` 原生中止；分 scaling 單程序重跑也遇到相同環境錯誤，沒有改寫既有成功矩陣。

## 凍結的幾何與量測

- 左定位點：父框座標 `(0, 2)`、尺寸 `22×22 Tk units`；第一格色帶左緣為 `x=0`，定位點完全位於父框內，沒有使用負Canvas座標或依賴裁切。
- 右定位點：`(320, 2)`、尺寸 `22×22 Tk units`。左右原點距離精確為 `320 Tk units`，定位點外緣跨度為 `342 Tk units`。
- 左白格：定位點內 `(3, 3)`、尺寸 `8×8`；四邊內部黑邊距左/上/右/下為 `3/3/11/11 Tk units`。右定位點仍維持鏡像白格 `(11, 11)`。
- KVM父框寬 `360 Tk units`。父框位於視窗內容x=8，因此左定位點至內容左緣有8單位空白；父框內上方留白2、右側338、下方容量1/10時37，容量11/20時64 Tk units。各標記彼此不重疊，原有排數格、狀態格及色帶位置/顏色由測試逐一固定比較。
- Tk contentView快取影像與Tk內容尺寸的實體像素比例為 `2.0×2.0 px/Tk unit`。Tk root內容尺寸與包含標題列的Quartz原生視窗bounds分開記錄；此環境原生視窗高度比Tk內容高28點（標題列/視窗框），該差值不納入像素比例。
- 兩個scaling下的容量1與10是單排，11與20是雙排；容量外格保持黑色。每組完整資料在同名JSON及`li7-geometry-matrix.json`。

## 畫面擷取與限制

PNG使用 `NSWindow.contentView()` 的 `bitmapImageRepForCachingDisplayInRect_` / `cacheDisplayInRect_toBitmapImageRep_` 擷取已映射、正在執行的Tk App內容，不是合成重畫，也不是WindowServer螢幕截圖。此環境的Quartz window capture曾回傳全黑圖；`screencapture -x` 回報 `could not create image from display 69734272`。因此以可讀的真實Tk contentView快取搭配Quartz on-screen bounds和widget量測作為本票畫面證據，沒有把黑圖當驗收結果。

左定位點能表示視窗上方基準區域；若另一個不規則視窗只覆蓋色帶而未覆蓋上方定位點，本定位點無法偵測該遮擋。這是此標記位置本身的偵測限制。
