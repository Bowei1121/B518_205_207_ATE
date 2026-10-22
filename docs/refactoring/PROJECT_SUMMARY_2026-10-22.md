# 專案摘要 — 2026-10-22

- 指定 Issue #112（HC7），父Spec #105，沿用PR #120分支`codex/hc7-geometry-handoff`。HC1–HC6已完成；App runtime源自已審HC4，contract維持1.3。
- 前兩輪補正：STALLED/TIMEOUT同色，bridge source`736bb8b`實際回傳TIMEOUT而非UNKNOWN；HC3 source tree與HC7 base不同；內容座標須扣除原生titlebar。舊資料仍保留歷史來源，不作新矩陣通過證據。
- R3真正阻擋為Tk啟動exit134。以同一Python最小Tk程式確認：Codex sandbox內exit134、sandbox外exit0，Tk8.6.16且可讀1440×900。先前「無Aqua/Accessibility session」的原因判定撤回，未修改系統權限。
- 已新增`capture_hc7_geometry.py`與`verify_hc7_evidence.py`，在真實macOS桌面取得容量1/10/11/20 × 英/繁中 × scaling1.0/1.5 × 1440×900/1152×720的32組完整矩陣；每組一般計時、長計時與提醒亮/暗/清除共4張，總計128張。
- 新證據在`B518 Log Solution/docs/refactoring/evidence/hc7-20261022/native-matrix/`，manifest記錄來源commit`13fad247a8048bfe0f0a26ec6ac910afc41fd33c`及src tree、擷取腳本hash、PNG hash/尺寸、內容座標、timer ROI與實際字形bbox/count、提醒色與心跳值。原生顯示模式已恢復。
- 32/32組控制項不因一般/長計時與提醒亮暗/清除移位，心跳獨立前進；128/128 timer crop含完整字形且有留白；離線128圖hash/尺寸/ROI核對通過。900高ROI`[600,1330,136,40]`為2×，720高ROI`[300,500,68,20]`為1×。
- 三個既有真Tk回歸3 PASS、0 skipped（17.858s）；未重跑完整套件。648px是計算下限，本輪實測模式720及900px。沒有JetKVM接收影像、部署配對或遠端壓縮/遮擋驗收，仍屬HC8。
- R3所需實作與本機證據已補齊；同步更新geometry/sample/run/handoff文件。最新commit仍須由獨立session複查；未自行宣稱審查通過，尚未merge或關閉Issue。

## HC8 整合驗收（Issue #113）

- 以 HC7 合併提交 `07ab0fbbae8eb50032ca2152f86a881f6d376449` 建立獨立工作分支；App source tree 為 `e32ba1068f361e4540670b0d92739faa50965ffc`，HC1–HC7 已合併。
- 新增真 Tk 整合斷言：實際來源、衝突、警報、多視窗與 audit 流程中保持 2 件提醒，切換所有開啟視窗語言時檢查紅字提示、計時／提示幾何及 KVM 心跳；該案例 1/1 通過。
- 本次整合／語言／顯示契約測試 31/31 通過；HC7 32 case／128 張影像 hash、尺寸與 ROI 離線檢查 32/32、128/128 通過。
- 聚焦 15 項桌面案例 13 通過、1 項 Quartz 原生輸入不可用而失敗、1 項需切換實體 1152×720 顯示器而跳過。完整 suite 開始後到 275 項時卡在 Tk modal 關窗；中止前 264 pass、3 fail、4 error、3 skip、另 1 項執行中。audit 重試案例單獨重跑 1/1 通過，但未抹除全套首次失敗；完整套件未全綠。
- 沒有 JetKVM received frame 或部署配對；T22、遠端縮放／壓縮／遮擋／狀態與心跳仍待設備驗收。橋接 source `736bb8b` 對同色 `STALLED`／`TIMEOUT` 仍有語意別名；不改橋接 repo。
- HC8 驗收表與結果見 `docs/refactoring/evidence/hc8-20261022/acceptance.md`、`results.json`、`full-suite.log`。Issue／PR 不關閉，等獨立審查與硬體待驗補齊。
- PR #121 首輪審查 S1／R1 已在同分支修正：真來源衝突＋逾時 alarm 與注入 audit 保存失敗形成真 badge；Canvas 已繪內容驗心跳／badge，切語言期間驗提醒閃爍；鈴鐺只確認 alarm 後失敗保存仍在，重試後清除；取消逾時輪、啟動新輪並從磁碟重讀兩份 audit。新增真 Tk 案例 1/1 PASS。
- 審查 R2 診斷：完整套件在本輪完成 **587 tests，4 FAIL／6 ERROR／4 skipped**。所有失敗／錯誤皆可定位至 Python 環境缺 Quartz／AppKit（含 NSApplication／NSRunningApplication None）；modal lifecycle 1/1 通過、UI 模組 124 項完成，Atlas 啟動重跑通過。原生輸入／擷取必要回歸仍待含 PyObjC 的環境，故不宣稱全套通過；完整 log 為 `docs/refactoring/evidence/hc8-20261022/review-fix-full-suite.log`。
- #113／PR #121 尚未 merge 或關閉：R2 原生回歸未通過，T22 無 JetKVM 配對／接收影格；需同 PR 獨立複查新 HEAD。審查修正證據追加於 HC8 acceptance。

## HC8 第三輪修正（最新狀態）

- 第二輪獨立審查已解除 S1／R1，新增 R3：audit 集合斷言不能檢出重複操作。`c79fbc823dc978ee982b4758ed054ff874cde820` 改用 Counter，要求衝突決策、警報確認、輪次取消各一次；reader 將三種事件各重複一次時案例會在精確次數斷言正確 FAIL（12.898s），保留雙語與原結果檢查。
- R2 找到原專案既有 `.venv-python31210`，含 PyObjC 11.1 的 Quartz／AppKit；前輪使用全域 Python 漏用此環境。既有原生輸入／截圖權限均 true，未安裝套件或改系統權限。以此 venv 對上述提交跑完 native full suite：587項＝583 PASS／4既有條件skip／0 FAIL／0 ERROR（369.371s）。前輪十個原生失敗／錯誤均通過；聚焦整合／語言／契約31/31通過（17.039s）。
- 新原始log、變異腳本／log、環境、結果JSON、235份擷取檔hash／尺寸清單及9張代表影像／3份幾何資料在 `docs/refactoring/evidence/hc8-20261022/round3-native/`。四個skip仍明列 H8 fixture兩項、1152×720實體顯示一項、使用者切換系統appearance一項；本輪未重新執行HC7實體矩陣。
- R2／R3已補修正與執行證據，仍需獨立審查目前新HEAD；本session不宣稱審查通過。T22無JetKVM影格／部署配對，因此#113／#105不關閉，PR尚未合併。前段未通過結果保留為歷史，以本節及新版acceptance為最新狀態。
