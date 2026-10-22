# 專案摘要 — 2026-10-22

- 指定 Issue #112（HC7），父Spec #105，沿用PR #120分支`codex/hc7-geometry-handoff`。HC1–HC6已完成；App runtime源自已審HC4，contract維持1.3。
- 前兩輪補正：STALLED/TIMEOUT同色，bridge source`736bb8b`實際回傳TIMEOUT而非UNKNOWN；HC3 source tree與HC7 base不同；內容座標須扣除原生titlebar。舊資料仍保留歷史來源，不作新矩陣通過證據。
- R3真正阻擋為Tk啟動exit134。以同一Python最小Tk程式確認：Codex sandbox內exit134、sandbox外exit0，Tk8.6.16且可讀1440×900。先前「無Aqua/Accessibility session」的原因判定撤回，未修改系統權限。
- 已新增`capture_hc7_geometry.py`與`verify_hc7_evidence.py`，在真實macOS桌面取得容量1/10/11/20 × 英/繁中 × scaling1.0/1.5 × 1440×900/1152×720的32組完整矩陣；每組一般計時、長計時與提醒亮/暗/清除共4張，總計128張。
- 新證據在`B518 Log Solution/docs/refactoring/evidence/hc7-20261022/native-matrix/`，manifest記錄來源commit`13fad247a8048bfe0f0a26ec6ac910afc41fd33c`及src tree、擷取腳本hash、PNG hash/尺寸、內容座標、timer ROI與實際字形bbox/count、提醒色與心跳值。原生顯示模式已恢復。
- 32/32組控制項不因一般/長計時與提醒亮暗/清除移位，心跳獨立前進；128/128 timer crop含完整字形且有留白；離線128圖hash/尺寸/ROI核對通過。900高ROI`[600,1330,136,40]`為2×，720高ROI`[300,500,68,20]`為1×。
- 三個既有真Tk回歸3 PASS、0 skipped（17.858s）；未重跑完整套件。648px是計算下限，本輪實測模式720及900px。沒有JetKVM接收影像、部署配對或遠端壓縮/遮擋驗收，仍屬HC8。
- R3所需實作與本機證據已補齊；同步更新geometry/sample/run/handoff文件。最新commit仍須由獨立session複查；未自行宣稱審查通過，尚未merge或關閉Issue。
