# B518 Log Solution

獨立的 macOS 本機 Log 監控程式，供 DFU、FCT、BT 顯示測試結果。它不含 Arduino、USB CDC、TCP、OpenCV、螢幕截圖、鍵盤／滑鼠或 KVM 控制；與 Atlas Agent 是不同的 App 與程序。

## 使用方式

```zsh
cd "B518 Log Solution"
python3 b518_log_solution.py
```

每輪必須由人員按下「開始監控」建立系統時間基準與啟動前快照。

若必要路徑尚未設定、已不存在或無法讀取，程式會拒絕開始並顯示原因；空白路徑不會被誤當成 App 的目前目錄。建立啟動前檔案快照期間，主畫面會先顯示「啟動中」，完成後才進入「監控中」。

## KVM 顯示與快捷鍵

主視窗是供 KVM 擷取的固定高對比看板：只顯示目前工站、KVM 狀態模板、Slot、狀態、產品 SN 與開始／停止按鈕。它採瘦長的 360 px 固定寬度，所有主畫面文字固定為 14 pt，啟動時會自動放在螢幕右上方；DFU、FCT、BT 分別顯示 7、6、4 個通道。設定、路徑、即時事件與 Session 紀錄都位於左上角的「設定」視窗。

看板上方固定顯示 `PASS`、`FAIL`、`TESTING`、`NOTEST` 四個色塊，其文字、字級與背景色和 Slot 實際狀態完全相同，讓 KVM 在第一次測試前即可製作全部狀態模板。這些色塊只供取樣，不是操作按鈕。

- `Command + Shift + M` 等同「開始監控」。在 macOS 上會註冊為全域快捷鍵，因此 Atlas／BT HMI 有鍵盤焦點時也可觸發；程式正在監控時不會重啟本輪。
- 快捷鍵只向 macOS 註冊這一組按鍵，並不監聽其他鍵盤輸入，所以不需要 Accessibility、Input Monitoring 或 Screen Recording 權限。
- 如果這組快捷鍵已被其他程式占用，App 會顯示警告；仍可按主畫面按鈕，或在 Log Solution 有焦點時使用相同按鍵。
- 目標最小螢幕解析度為 `1280 x 1024`。App 不會強制置頂，部署時應讓 Atlas／BT HMI 不覆蓋右上角看板。

- DFU：選擇 `active` 及 `unitest`；監看 slot1～7。
- FCT：選擇 `active` 及 `unit-archive`；監看 slot1～6。第一次讀到的可信 SN 會鎖定，active 消失後轉為 `COMPLETING` 並讀取最終 `records.csv`；全程無可信 SN 則顯示 `SN 讀取失敗 / FAIL`。
- BT：選擇 `TestData`，CaseInfo 根路徑可選。每輪固定監控 Thread0～3；檔案穩定五秒後才解析；空 SN 的 FAILED CSV 顯示 `NOTEST`。

每輪紀錄保存在 `~/Library/Application Support/B518LogSolution/sessions/`，包含事件、結果、設定、時間與來源檔案。
