# macOS 15 arm64 build 測試修正 — 2026-10-16

## 查核與重現

- 開始 HEAD：`7a4cca6`，分支 `B518-Log-Solution`。先讀 AGENTS.md、CONTEXT.md、domain.md、ADR 0002／0005 與最新 HMI／HF1 文件。
- 本機使用指定 `.venv-macos15_0-arm64-log-solution/bin/python`：Python 3.12.10、Tcl/Tk 8.6.16、Aqua、Apple Silicon，macOS 26.5.2；build 最低目標為 macOS 15.0。
- 完整重現使用者截圖：503 tests、112.549 秒、9 failures／1 error／1 skipped，見 [tests-before.log](tests-before.log)。沒有用 10/12 的舊版 374 tests 證據代替本次驗證。
- 原有 VERSION 為未提交的 0.1.3，spec 為未追蹤檔；先備份至 `/tmp/b518-hmi-20261016/`，建置使用隔離副本，不刪除或覆蓋兩檔。

## 原因與修正

1. **Aqua 的固定尺寸視窗拒絕後續 geometry。** 真實 probe 顯示多次 update 後仍是 362×679；重新要求 376×855 也不生效。允許程式調整後又遭預設 WM maximum 819px 裁切。因此 `_position_window` 在程式調整期間暫時解除 resizable，明確設定當前寬高的 min／max、套用 geometry 並處理 idle，最後恢復不可手動縮放。376px、既有 window_height 與 KVM 座標斷言均保留。見 [aqua-probe.log](aqua-probe.log)。
2. **Aqua 假接受 X11 ISO_Left_Tab。** binding 可建立，但合成事件為 keysym `??`／0、state 0；實際 Shift+Tab 為 Tab、state 1，反向遍歷正確。Aqua 不註冊該 X11 alias，測試使用真正 Shift+Tab；非 Aqua 保留 alias。四個頂列控制項、離開頂列及 disabled review 的完整正反向斷言仍在。
3. **build 缺少原生畫面測試依賴。** HF6 像素測試 import Quartz 失敗。新增固定版本 desktop-test requirements（PyObjC core／Cocoa／Quartz 11.1），由 macOS15 arm64 requirements 引入，原本兩個 build 指令即可安裝。這是測試工具依賴，App 功能不因此增加截圖或桌面控制。
4. **標題測試把版本寫死。** 尺寸修好後，測試才走到將實際 0.1.3 與 0.1.0 比對的斷言；改用實際 APP_VERSION，並新增 9.8.7 在語言／機型切換後保留的精確標題回歸。
5. **容量測試的非同步與 Tk 收尾。** 準備官方 50,000 筆 fixture，實際執行原本缺 fixture 而跳過的 H8 案例。第一頁可讀不等於所有頁面準備完成，先等待完成狀態才驗證最終筆數／日期，原有分頁、原文、hash 與 heartbeat 斷言不變。進一步捕捉到下一個 audit worker GC 原生中止；heartbeat 原本只取消初次 ID，且回呼循環沒有在主執行緒回收。改追蹤最新 ID、取消 timer、TestCase cleanup 主執行緒 GC。新增子程序執行真實容量流程，確認 root weakref 已消失後才讓 worker GC。見 [capacity-lifecycle-red.log](capacity-lifecycle-red.log)。
6. **完整套件揭露的測試排版前置條件。** 提示的 disposable 按鈕改用獨立映射的 Toplevel，避免放到已填滿的固定主窗之外；仍驗證按鈕銷毀會同步清掉提示。長原文先用 Tk Text count 的 update／ypixels 完成惰性換行計算，再記錄閱讀位置，保留語言切換前後的精確字元索引比對。

## 回歸與畫面證據

- 新固定尺寸案例遍歷 2→10→20→2，舊程式在 10／20 容量先失敗，見 [geometry-red.log](geometry-red.log)。修正後同時檢查376px、高度函式、resizable=(0,0) 與 marker=(278,0)。
- 新容量生命週期案例先以 retained interpreter 失敗；修正後在 GC disabled 的子程序確認已釋放 root，再由 worker GC，程序正常結束。
- 原生畫面六張（2／10／20 × 中英）與 bounds 保存於 native/。本機實測 size 分別為 376×667、376×855、376×882，兩語相同；marker 在主窗的座標保持 (286,95)，尺寸26×26。已目視檢查2片英文與20片繁中，頂列、KVM與底部操作均有呈現。
- 最終執行使用者同一份 `scripts/build_macos15_arm64_log_solution.sh`，工作目錄為 `/tmp/b518-hmi-20261016/build-validation`，沿用指定 venv 並傳入 `B518_H8_CAPACITY_ROOT=/tmp/b518-hmi-20261016/capacity-50k`。
- **506 tests，153.666 秒，OK，零跳過，build exit 0**。原生像素、全部 HMI／Tk、容量與兩個 Tk worker-GC 子程序案例均實際執行；完整輸出見 [build-after.log](build-after.log)，容量資料一致性見 [capacity-after.json](capacity-after.json)。
- PyInstaller 完成、macOS15.0 arm64 bundle compatibility 通過、ad-hoc codesign verify 通過、ZIP 與 SHA256 完成。隔離副本 VERSION 從0.1.3遞增至0.1.4；原始 VERSION 沒有改動。
- 候選檔：`B518 Log Solution/dist-validation-20261016-macos15_0-arm64/B518-Log-Solution-V0.1.4-macOS15.0-arm64.zip`，SHA256 `ab3c36131388dc3abbbc326ca407aa9f3c285ea573d13ff0df92ddc06c8a4851`。複製後 checksum 與腳本輸出一致。
- 驗證後再次 cmp 確認原有 VERSION／spec 與備份逐位元組相同；遠端 fetch 查核與開始基準相同，只提交本次相關程式、測試與紀錄。

## 保護與範圍

- VERSION SHA256：`2d2454ef0edeb462a6ce8b25d387aaa74df08093d5cea0428a10ce55510c6326`。
- spec SHA256：`1c205a379736c9461fb8cc17a958b850ad17a78c43d1075fc2d0cb69d4472a13`。
- 沒有改動工站判定、輪次／稽核資料格式、KVM display contract 或降低 build gate。Intel 實機與工廠 KVM 路徑未在本次重驗。
- [PyObjC Quartz 11.1 官方套件資料](https://pypi.org/project/pyobjc-framework-Quartz/11.1/)列有 Python3.12／macOS10.13+ universal2 wheel；相依版本已固定，並於本機原生像素測試實際使用。
