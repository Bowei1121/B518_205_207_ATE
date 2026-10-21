# LS8：M4 本地打包與驗收 — 2026-10-21

對應 Issue [#94](https://github.com/Bowei1121/B518_205_207_ATE/issues/94)。本次主機為 Apple M4、arm64、macOS 26.5.2。**不宣稱 macOS 15 實機、Developer ID／notarization 或 JetKVM 配對通過。**

## 版本追溯與變更

- 起始整合版本：`50a6303d584fc2bcab1f0848b06534cd1de1ee35`。
- 打包修正：`c43d56ad8a3ce9658302e139fdc95976967b1b6c`，只將三個建置腳本的 `VERSION:VERSION` 改為 `VERSION:.`，App src/tests 未變。
- 本次沿用使用者既有未提交 VERSION `0.1.5`；原 VERSION 變更與未追蹤 spec 未提交／覆寫。故產物需以 commit **加上 VERSION=0.1.5** 追溯，不宣稱完全乾淨 checkout。
- 修正前實際 App 啟動標題為 `Vunknown`；檢查發現 Resources/VERSION 是目錄，檔案實際位於 VERSION/VERSION。修正後資源根目錄 VERSION 與 Info.plist 兩個版本欄位一致。
- 顯示契約沿用 1.3，Claude 交接 bridge snapshot 1.1 的外部配對限制不變。

## 已完成驗證

| 驗證 | 結果／證據 |
| --- | --- |
| Python 3.12.10、原生 arm64、指定依賴 | `python-preflight.txt`；PyInstaller 6.16.0、PyObjC 11.1 |
| 完整真實 Tk／原生輸入套件 | `full-suite-desktop.log`：580 tests，182.881 秒，OK (skipped=3) |
| 原 skipped 的兩項 H8 容量測試 | `h8-tests.log`：2 tests，32.528 秒，OK；50,000 合成事件，`h8-result.json` 包含獨立磁碟基準、頁面、原文未改及關閉結果 |
| 真實淺色／深色切換 | `appearance-tests.log`：1 test，233.291秒，OK；使用者手動深→淺→深，同一 recovery 視窗中英文／兩頁籤12張截圖，見 `appearance/` |
| 重新原生 arm64 打包 | `build-fixed.log`；使用 Python.org 3.12.10 venv；deployment target 15.0 |
| bundle 所有 Mach-O／相依／最低版本靜態檢查 | `fixed-bundle-check.log`：通過 |
| 資源與 plist 版本一致 | `version-check.txt`、`fixed-bundle-plist.txt`：0.1.5 |
| ad-hoc 簽章驗證 | `fixed-codesign-verify.log` exit 0，詳細類型見 `fixed-codesign-detail.log` |
| ZIP SHA-256 | `fixed-checksum-verify.log`、`fixed-zip.sha256` |
| 修正後真正打包 App 操作 | 版本0.1.5、雙語、快捷鍵、配置錯誤／復位、正常4 PASS、人工停止、無活動逾時／待確認／警報確認／取消、保存、心跳及退出；見 `bundle-smoke.json`、`bundle-*.png`、`bundle-rounds/` |

完整套件已覆蓋 T01–T09、T13–T18 的本地 App/Tk 案例，包括準備、正常／人工停止、逾時、取消、復位、補存、關閉、時間凍結、半秒16態心跳、歷史查詢晚回覆／取消／語言切換、容量與縮放、原生鍵鼠。逐項測試名稱對照沿用 `../ls8-integration-release/README.md`。這些是受控 App/Tk 證據，不能充當產線／橋接實測。

## 重現命令與產物

工作目錄為 `B518 Log Solution/`。完整套件命令：

```sh
B518_TK_TESTS=1 .venv-macos15_0-arm64-log-solution/bin/python scripts/run_tests.py
```

容量 fixture：

```sh
.venv-macos15_0-arm64-log-solution/bin/python scripts/historical_event_capacity.py prepare --root /private/tmp/b518-ls8-h8-20261021 --events 50000 --as-of 2026-10-21
B518_TK_TESTS=1 B518_H8_CAPACITY_ROOT=/private/tmp/b518-ls8-h8-20261021 B518_H8_TK_EVIDENCE="$PWD/docs/refactoring/evidence/ls8-m4-20261021/h8-result.json" .venv-macos15_0-arm64-log-solution/bin/python scripts/run_tests.py test_historical_event_capacity_tk
```

建置使用 macOS15 腳本相同的 PyInstaller 選項，但保留既有 VERSION，不重複 pip 安裝與完整測試，也不覆寫原 dist；隔離的 `PYINSTALLER_CONFIG_DIR=/private/tmp/b518-ls8-pyinstaller-20261021` 避免寫入使用者全域 cache。設定 `MACOSX_DEPLOYMENT_TARGET=15.0 CMAKE_OSX_DEPLOYMENT_TARGET=15.0 CMAKE_OSX_ARCHITECTURES=arm64`；dist/work/spec 路徑分別為 `dist-ls8-fixed-20261021` 與 `build-ls8-fixed-20261021`；`--add-data "$PWD/VERSION:."`，其餘選項同腳本。隨後設定 plist、執行 verifier、ad-hoc 簽章及 ZIP 校驗。

最終產物：`dist-ls8-fixed-20261021/B518-Log-Solution-V0.1.5-LS8-macOS15-arm64.zip`。SHA-256：`1166ca636aeadf93e47aede885f2bb12d1840bfbe3f162f6971914aa399f3070`。原 `dist-ls8-20261021` 為發現版本錯誤的產物，不供交付。

## 限制與保留的失敗證據

- `full-suite.log` 是沙箱內第一次執行，程序 exit 134，無完整摘要；不能算通過。沙箱外登入桌面重跑結果保存在 `full-suite-desktop.log`。原生輸入 preflight 在沙箱外輸出 post/listen 均 true；未修改系統權限。
- `build.log` 與 `new-bundle-check.log` 等無 fixed 前綴項目為修正前候選；不能拿來替代最終版本驗收。
- 只有 macOS 26.5.2 實機；macOS15 靜態相容檢查通過不代表15.x執行階段通過。
- 簽章為 ad-hoc，沒有 Developer ID／notarization。
- T10–T12 的遠端每格≥12×12像素、壓縮／遮擋、三張新鮮影像、8秒循環與觀察中斷判讀仍需新版橋接及實際 KVM 配對。
- 兩個其他目標建置腳本只修正相同路徑錯誤並做語法檢查；未執行 Intel 或 macOS26專用套件建置。
- 不修改父規格、不修改橋接，也不以本地部分結果關閉 #94。

## 真正 frozen bundle 受控輪次

使用 CUA 原生鍵盤操作**同一個最終打包 App**，沒有注入 Python 測試或替換 App 內部物件。關閉 App 後先備份原 preferences，暫將 B518 BT 來源指向 `/private/tmp/b518-ls8-bundle-round-20261021/output/SmtCal`；完成後已還原原始 bytes，見 `preferences-restored.txt`。三輪只使用明確 `LS8TEST` 合成識別碼，非生產產品。

| Session | 真正 App 操作與結果 |
| --- | --- |
| bt-20261021-092201-679896 | 快捷鍵受理後新增四份合成RS-WMT結果，4 PASS、本輪完成、完整保存；計時00:14停止，心跳繼續。 |
| bt-20261021-092233-141652 | 新輪計時歸零，不沿用舊檔；鍵盤停止後4 STOPPED、完整保存，00:11凍結。 |
| bt-20261021-092307-729536 | 開始期限2秒、整輪期限10秒，無新資料；NOTEST／待確認，00:02凍結；關閉警報不算確認，開始快捷鍵不建立新輪；從通知與恢復確認警報，再明確取消未確認輪次，回待命且紀錄保留。 |

`bundle-rounds/` 保留各輪 session、events、audit、results及archive；`bundle-archive-verification.json` 的所有封存組件檔案大小與SHA256均一致。監控耗時以collection_stopped所記錄值及畫面為準，不把之後取消／確認的audit elapsed誤當監控耗時。App使用者歷史保留這三筆合成測試紀錄，沒有刪除既有資料。

## 驗收界線

完整套件仍原樣記錄 skipped=3；兩項容量與一項外觀已分別補跑通過，不改寫原log為零skipped。實際bundle操作與相同src/tests的source App/Tk套件互補：保存重試故障注入、完整歷史查詢資源競態矩陣及所有容量／縮放組合由source suite覆蓋，未宣稱每一條都在frozen bundle重跑。macOS15實機、Developer ID／notarization與真實橋接配對保持待驗；不關閉#94。
