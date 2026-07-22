# B518 ATE 上位機模擬器

這是未來 Windows 產線上位機的 TCP 模擬工具。Arduino 是 TCP server；上位機以 TCP client
連線至 Arduino IP（預設 `192.168.1.100`）與 port `5000`。

## 使用方式

1. 確認 Arduino、Windows 電腦與 Mac mini 在同一網段，且 Mac Agent 已用 USB CDC 連上 Arduino。
2. 在上位機填入 Arduino IP／port，按「連線」。Arduino MVP 同時間只支援一個 TCP client。
3. 選擇 DFU、FCT 或 BT，輸入或產生唯一 JOB ID。
4. 在 Slot 1～4 輸入 1 至 4 個 SN；空白 slot 不會送出，也不會重新編號。按「發送測試條碼」後會送出：

   ```text
   BT:JOB=20260722-001;1=SN001,3=SN003,4=SN004\r\n
   ```

5. Agent 接單後立即回傳：

   ```text
   ACK:BT:JOB=20260722-001\r\n
   ```

6. 保持 TCP 連線。測試完成後收到：

   ```text
   RESULT:BT:JOB=20260722-001;1=SN001,PASS;3=SN003,PASS;4=SN004,FAIL\r\n
   ```

   程式會將各 Slot 結果更新為 PASS、FAIL、TIMEOUT 或 UNKNOWN，並保留原始通訊紀錄。

IP／port／工站會保存在 Windows 的 `%APPDATA%\B518UpperComputerSimulator\preferences.json`。

## Windows 建置

在 Windows 安裝 Python 3 後執行：

```bat
python -m pip install pyinstaller
build_windows_upper_computer.bat
```

產物是 `dist\B518 Upper Computer Simulator\B518 Upper Computer Simulator.exe`。本工具只使用標準
TCP socket，不需要 Windows 的鍵盤／滑鼠自動化權限。
