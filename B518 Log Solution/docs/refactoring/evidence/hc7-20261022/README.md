# HC7 本機幾何與橋接交接

Issue：[ #112 — HC7：新版本機幾何量測與 KVM 模板交接](https://github.com/Bowei1121/B518_205_207_ATE/issues/112)；父規格：[ #105](https://github.com/Bowei1121/B518_205_207_ATE/issues/105)。

## 結論

- App source `d03c7b6bf56e25cae4ceea58814d78a467bb112c` 的顯示契約維持 **1.3**。HC3 固定高度調整了 App 內 KVM 色帶與計時器的垂直位置；KVM 父框內的定位點、狀態格、排數格、結果色帶與心跳幾何沒有改版。
- 橋接 `main` HEAD `736bb8b4df5ce87beaf140416f3aea027d3aa1d7` 宣告 contract 1.3。App 的 `STALLED` 與 `TIMEOUT` 都是 `#ff9900`；原 reader 函式把兩者都讀成 `TIMEOUT`，不會回傳 UNKNOWN。結論是幾何與色樣本可讀，但狀態語意會把 STALLED 靜默合併為 TIMEOUT，不能宣稱完整語意相容。
- HC3 原始資料提供 1440×900 與 1152×720 的固定高度量測；HC4 真 Tk review 提供提醒/計時/心跳行為證據。**HC7 新版雙語、雙 scaling、容量 1/10/11/20 的完整布局矩陣仍未完成**：舊 LS7 只量到歷史 KVM child 座標，不能替代 HC7 幾何驗收。HC7 目前 3/6 項可勾選；詳見 [`geometry-matrix.json`](geometry-matrix.json)。
- App 的 1.3 顯示欄位沒有改變，不升 App contract version。橋接需由其維護者決定如何區分同色的 STALLED/TIMEOUT，或明確承認兩者為同一語意；不能只新增同色 mapping。此票不修改橋接程式。
- 本次無真實 JetKVM 接收影像；遠端影像縮放、壓縮、像素大小、遮擋與凍結串流驗收均**未完成**，留給 HC8。所有截圖像素值只屬本機 macOS/Tk 證據。

## 座標與模板

座標分開記錄 KVM child 相對父框的 Tk 單位，以及每張 timer PNG 自身的 raster 像素座標。四張標準 752×1612、無 titlebar 的樣本使用 `00:00 ROI [600,1330,136,40]`；capacity-10 圖的字形 bbox 為 `[654,1339,730,1359]`。長計時 PNG 是 752×1668 並含 56 px titlebar，原圖 ROI 為 `[600,1386,136,40]`；正規化移除 titlebar 後才是 `[600,1330,136,40]`。之前的標準 ROI `[648,1386,88,40]` 落在空白。這些是本機樣本的 pixel crops，不是 JetKVM stream ROI。

本機樣本沿用 HC3 真 App 截圖（容量 1/10/11/20，英／繁中交錯）及 LS6 真 Tk 心跳截圖。它們供橋接專案確認模板欄位與定位流程，**不代表遠端擷取結果**。樣本路徑與 SHA-256 列在矩陣中；既有 1.3 機器可讀模板為 [`../ls7-kvm/contract.json`](../ls7-kvm/contract.json) 與 [`../ls7-kvm/samples.json`](../ls7-kvm/samples.json)。

## 證據版本與限制

- 固定高度量測來源是 HC3 commit `59fc669d43022bcf9088e11085f9a6111c92b1bc`；其 source tree **不同於** HC7 base `d03c7b6bf56e25cae4ceea58814d78a467bb112c`，因 HC4 有提醒邏輯改動。幾何僅作重用證據；PR #119 HEAD `3bee309eea300c2f222b4d6cf5e8c0788dfd83d0`（與 HC7 base 同 tree）的真 Tk 3/3 通過，驗證固定 bounds、長計時、提醒與心跳獨立。
- 本次 review 發現上一版一般 timer ROI 裁到空白；目前已按原始 raster 重算並以 `sips` 裁圖確認標準與長計時 crop。timer widget 寬度採 HC3 量測的 68 Tk units，不再使用錯誤的 44。
- 完整新版雙 scaling 原生截圖仍未取得；此次 Tk/Aqua 矩陣重跑以 exit 134 結束，沒有 unittest 輸出。舊 LS7 矩陣不算 HC7 新布局通過證據。依 review 保留本機驗收未完成：3/6 可勾、1/2/4 未勾。詳細執行記錄見 [`local-run.json`](local-run.json)。
