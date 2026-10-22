# HC7 本機幾何與橋接交接

Issue：[ #112 — HC7：新版本機幾何量測與 KVM 模板交接](https://github.com/Bowei1121/B518_205_207_ATE/issues/112)；父規格：[ #105](https://github.com/Bowei1121/B518_205_207_ATE/issues/105)。

## 結論

- App source `d03c7b6bf56e25cae4ceea58814d78a467bb112c` 的顯示契約維持 **1.3**。HC3 固定高度調整了 App 內 KVM 色帶與計時器的垂直位置；KVM 父框內的定位點、狀態格、排數格、結果色帶與心跳幾何沒有改版。
- 橋接專案 `Bowei1121/B518_KVM_Log` 的 `main` HEAD `736bb8b4df5ce87beaf140416f3aea027d3aa1d7`，`host-app/log_solution_reader.py` 宣告 `CONTRACT_VERSION = "1.3"`。幾何與大多數顏色相符，但 parser **沒有 `STALLED` 顏色樣本**；遇到 STALLED 格會 fail closed，該畫面變成 unreliable。因此目前只是幾何相容，並非全狀態相容，不能宣稱完全可配對。
- 本機 1440×900 幾何矩陣、1152×720 支援高度、HC4 閃爍/計時/獨立心跳證據及雙 Tk scaling 的定位點資料見 [`geometry-matrix.json`](geometry-matrix.json)。本文件把舊 timer ROI 明確標成不可沿用，改列 HC3 後新的裁切座標。
- App 的已發布顯示契約欄位沒有改變，故不升 App contract version；橋接 1.3 實作仍需補辨識 `STALLED` 才能和 App 的全部狀態安全配對。依本票範圍只記錄缺口，不修改橋接程式。
- 本次無真實 JetKVM 接收影像；遠端影像縮放、壓縮、像素大小、遮擋與凍結串流驗收均**未完成**，留給 HC8。所有截圖像素值只屬本機 macOS/Tk 證據。

## 座標與模板

座標區分為兩種：KVM child 相對 `KVM` 父框的契約座標，以及畫面 timer 相對 Tk content view 的本機 ROI。橋接只從定位點偵測 KVM 父框；不可把本機 Retina 的 2 px/Tk unit 當成 JetKVM stream 比例。新版 timer crop 在 1440×900 截圖為 `00:00 → [648, 1386, 88, 40]`，長分鐘 `10000:00 → [600, 1386, 136, 40]`，原點為 content-view 左上角。矩陣 JSON 記錄來源、公式與適用限制。

本機樣本沿用 HC3 真 App 截圖（容量 1/10/11/20，英／繁中交錯）及 LS6 真 Tk 心跳截圖。它們供橋接專案確認模板欄位與定位流程，**不代表遠端擷取結果**。樣本路徑與 SHA-256 列在矩陣中；既有 1.3 機器可讀模板為 [`../ls7-kvm/contract.json`](../ls7-kvm/contract.json) 與 [`../ls7-kvm/samples.json`](../ls7-kvm/samples.json)。

## 證據版本與限制

- 固定高度本機矩陣：HC3 合併 commit `59fc669d43022bcf9088e11085f9a6111c92b1bc` 的實測 JSON/PNG；HC4 在該 UI 上加入通知閃爍，沒有改固定幾何。HC4 最新 PR #119 review HEAD `3bee309eea300c2f222b4d6cf5e8c0788dfd83d0` 的真 Tk 變更案例 3/3 通過，0 skipped，另含 10000:00、長狀態、提醒/心跳互相獨立與提醒清除後不移位的檢查。
- 雙 Tk scaling `1.0/1.5`、容量 `1/10/11/20`、中英矩陣取自 LS7 已通過的真 Tk/NSView 測量；僅用於不變的 KVM 父框內座標。舊矩陣中的 timer 根座標已因 HC3 固定高度而過期，本交接不再引用。
- 本次工具執行環境沒有可用的 macOS Aqua/Accessibility GUI session。以本機 `.venv-python31210` 重跑 `test_li7_geometry_at_both_scalings_and_all_capacities` 時，Tk 初始化以 exit 134 結束，沒有測試輸出。這不是產品測試失敗，也不算本次重新驗收；詳細命令見 [`local-run.json`](local-run.json)。
- 雙 scaling 的完整新版 HMI 原生截圖尚未由本次執行重新產生。沿用的是先前通過的雙 scaling KVM child 幾何與 HC3/HC4 的更新版實測，兩者來源已分開標示，不能合稱同一批次的新截圖。

