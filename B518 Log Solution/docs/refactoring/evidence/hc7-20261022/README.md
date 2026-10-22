# HC7 本機幾何與橋接交接

Issue [#112](https://github.com/Bowei1121/B518_205_207_ATE/issues/112)，父規格 [#105](https://github.com/Bowei1121/B518_205_207_ATE/issues/105)。

R3 所缺的新版矩陣已實測產出：**32 組、128 張原生 Tk contentView 圖片**。本輪量測 App source `13fad247a8048bfe0f0a26ec6ac910afc41fd33c`；完整程式樹與擷取腳本 SHA 記在 [native-matrix/matrix.json](native-matrix/matrix.json)。這是修正者產出的證據，仍待獨立 session 複查。

## 量測範圍

完整交叉：容量 1/10/11/20 × 英文/繁中 × Tk scaling 1.0/1.5 × 真實顯示模式 1440×900/1152×720。每組保存一般 `00:00`、長計時 `10000:00`＋12件提醒亮色、暗色、清除後，共四張原生影像。

| 真實顯示模式 | Tk scaling | Tk content size | PNG raster | timer content bounds | timer raster ROI |
| --- | --- | --- | --- | --- | --- |
| 1440×900 | 1.0 / 1.5 | 376×806 | 752×1612 | [300,665,68,20] | [600,1330,136,40] |
| 1152×720 | 1.0 / 1.5 | 376×641 | 376×641 | [300,500,68,20] | [300,500,68,20] |

每張圖的控制項座標由 widget-parent 階層量到 Tk content origin；PNG 從真實、已顯示的 NSView contentView 擷取，不含 titlebar。比例依每張圖尺寸實測，不固定套 2×。`controls`、raster 尺寸、timer ROI、實際字形 bbox/count、SHA-256、提醒顏色/文字與心跳值均存於完整矩陣。[geometry-matrix.json](geometry-matrix.json) 提供分組摘要；[samples.json](samples.json) 指向目前樣本目錄。

擷取腳本逐組檢查：所有控制項在視窗內；狀態文字與 timer 不重疊；一般/長分鐘及提醒亮暗/清除不推動控制項；128個 timer crop 均含完整字形且四邊有留白；提醒作用時心跳持續變化。容量由真正的 MachineProfileStore 保存後啟動 App，計時與待處理件數以受控輸入驅動畫面；這是布局量測，並非 ATE 實際輪次。

## 重現與檢查

使用有 macOS Tk/Aqua 與 PyObjC 的 Python，在一般使用者桌面執行：

```sh
python scripts/capture_hc7_geometry.py --output docs/refactoring/evidence/hc7-20261022/native-matrix
python scripts/verify_hc7_evidence.py docs/refactoring/evidence/hc7-20261022/native-matrix
```

命令的 cwd 是 `B518 Log Solution`。擷取時會切換兩個真實顯示模式；正常結束或例外都在 finally 恢復原模式。`--smoke` 只跑一組。離線檢查不需 Tk 桌面，驗證32組完整交叉、128張圖的 hash/尺寸、來源程式樹、腳本hash與ROI座標一致性；字形 bbox/count 是擷取當下的 AppKit 像素量測。

本輪在 Intel macOS15.8.1、Python3.12.10 執行。原 exit134 已用同一 Python 的最小 Tk 程式確認：sandbox內失敗、sandbox外成功；之前「缺 Aqua/Accessibility session」的歸因撤回。本輪沒有變更系統權限。三個既有真Tk回歸亦 3 PASS / 0 skipped（17.858s），詳見 [local-run.json](local-run.json)。

## 契約與限制

App 維持 contract1.3。橋接 `B518_KVM_Log` source `736bb8b4df5ce87beaf140416f3aea027d3aa1d7` 宣告1.3，幾何與色樣本可讀；STALLED與TIMEOUT同為`#ff9900`，原reader都回傳TIMEOUT，屬於語意合併，不能宣稱完整語意相容。本票不修改橋接、遠端命令或ATE控制。

HC3與LS7舊樣本保留歷史追溯；HC7布局驗收改用本次完整native-matrix。648px為程式計算的最低支援高度，不是本輪可用的實際顯示模式；本輪實測720與900px。沒有重跑完整套件，也沒有JetKVM received frame、部署配對、遠端縮放/壓縮/遮擋驗收；後者仍屬HC8。PR需對最新commit獨立複查後，才能合併與關票。
