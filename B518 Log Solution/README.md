# B518 Log Solution

獨立的 macOS 本機 Log 監控程式，供 DFU、FCT、BT 顯示測試結果。它不含 Arduino、USB CDC、TCP、OpenCV、螢幕截圖、鍵盤／滑鼠或 KVM 控制。

## 使用方式

```zsh
cd "B518 Log Solution"
python3 b518_log_solution.py
```

每輪必須由人員按下「開始監控」建立系統時間基準與啟動前快照。

- DFU：選擇 `active` 及 `unitest`；監看 slot1～7。
- FCT：選擇 `active` 及 `unit-archive`；監看 slot1～6。第一次讀到的可信 SN 會鎖定，active 消失後轉為 `COMPLETING` 並讀取最終 `records.csv`；全程無可信 SN 則顯示 `SN 讀取失敗 / FAIL`。
- BT：選擇 `TestData`，CaseInfo 根路徑可選。使用 `BT Log Start All` 或單一 Thread 按鈕。檔案穩定五秒後才解析；空 SN 的 FAILED CSV 顯示 `NOTEST`。

每輪紀錄保存在 `~/Library/Application Support/B518LogSolution/sessions/`，包含事件、結果、設定、時間與來源檔案。
