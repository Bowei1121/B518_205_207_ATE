# HC8 第三輪：R3 防重複與 R2 原生回歸

測試提交：`c79fbc823dc978ee982b4758ed054ff874cde820`；前次審查 HEAD：`5f575dc018f4bfd9a1c04908538bd364a0da051a`。App runtime source tree 仍為 `e32ba1068f361e4540670b0d92739faa50965ffc`。

使用原專案既有 `.venv-python31210/bin/python`，不是前輪缺依賴的全域 Python。完整路徑、版本、既有權限及 1440×900 顯示條件見 [environment.json](environment.json)；Python 3.12.10、Intel macOS 15.8.1、PyObjC core／Cocoa／Quartz 11.1。未安裝套件、修改系統權限或切換實體顯示模式。Tk 於 sandbox 外原生桌面執行。

| 驗證 | 結果 | 原始證據 |
| --- | --- | --- |
| 完整套件 | 587 項：583 PASS、4 skipped、0 FAIL、0 ERROR，369.371s，exit 0 | [native-full-suite.log](native-full-suite.log) |
| M10／語言目錄／KVM 契約 | 31 PASS、0 skipped，17.039s | [focused.log](focused.log) |
| reader 重複三種操作各至兩次 | 在 Counter 精確次數斷言正確 FAIL，12.898s；腳本 exit 0 表示偵測到預期失敗 | [mutation log](duplicate-operation-mutation.log)、[實際腳本](check_duplicate_operations.py) |

完整套件在上述提交完成後執行；聚焦批次及變異驗證使用與該提交相同的測試內容，執行完才提交。變異僅 patch 測試 reader 的回傳值，不修改磁碟 audit、產品或測試檔。三種處置為 `conflict_resolved`、`round_alarm_acknowledged`、`round_cancelled`，正常情境各恰好一次；雙語及原結果檢查仍保留。

前輪缺依賴造成的十項原生失敗／錯誤，本輪均執行且通過，包含 LI6 foreground、cleanup 可見擷取、LI7 幾何、duplicate-title capture、HF4 原生提示、主頁／設定與恢復操作提示、關閉時衝突與警報提示、歷史／診斷提示及 toolbar 原生鍵盤。完整套件沒有新增 skip，也沒有以單項重跑替代本輪整批結果。

四項既有 skip：H8 容量 fixture 未提供的兩個 optional Tk 案例、需獨立 1152×720 實體顯示驗收的一例、需使用者切換 macOS Light/Dark appearance 的一例。1152×720 幾何仍沿用 HC7 相同 runtime source tree 的既有證據，本輪不宣稱重新執行實體矩陣。

[run-results.json](run-results.json) 記錄確切命令、結果及 log hash。[capture-inventory.json](capture-inventory.json) 列出全部 235 個擷取檔（202 PNG）的 SHA-256、尺寸及是否隨 PR 保存；完整擷取資料仍在該清單的本機暫存路徑。本目錄僅保存 9 張代表影像與 3 份幾何資料。預設擷取來自 WindowServer；LI7 的 `view-cache` 圖由測試明確擷取真 Tk contentView。已人工抽查 cleanup 繁中與歷史取消停用提示影像；未宣稱全部影像都人工檢視，也不以檔案清單替代測試斷言。

R2／R3 修正交回獨立複查新 HEAD；本實作自查不代表審查通過。T22 仍缺真 JetKVM received frame／部署配對，#113 與父規格 #105 保持 OPEN。
