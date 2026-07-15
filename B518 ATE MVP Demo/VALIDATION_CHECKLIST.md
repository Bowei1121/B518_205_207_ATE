# B518 ATE MVP 現場驗證清單

此清單將「無硬體可驗證」與「需連接真實設備」分開。不要因為 HTML 模擬器通過，便宣稱
Arduino HID 或 B482 實機已通過。

## 1. 本機無硬體驗證

- [ ] 在 `B518 ATE MVP Demo` 執行 `python3 -m unittest -v test_atlas_agent.py`；預期全部通過。
- [ ] 執行 `python3 b482_demo_server.py --csv-root "$HOME/Desktop/AtlasDemoCSV"`。
- [ ] 開啟 `http://127.0.0.1:8080`，確認 DFU、FCT、BT 均可操作，且 Slot checkbox 未勾選時為 `NOTEST`。
- [ ] 開啟 Atlas Agent，CSV 根路徑設為 `~/Desktop/AtlasDemoCSV`，工站選 FCT；在 Agent 手動輸入
  `LOCAL001,LOCAL002` 並開始，確認 `device.log` 出現、兩個 `RESULT` 分別顯示。
- [ ] 確認一個 CSV 的 `status` 含 `FAIL` 時，Agent 顯示且回報 `FAIL`。

## 2. Arduino 與 TCP／LabVIEW 驗證

- [ ] 將 `B518_Arduino_MVP_Test/B518_Arduino_MVP_Test.ino` 燒錄到 UNO R4 WiFi，接上 W5100 與 Mac mini。
- [ ] 在 Agent 選擇對應 `/dev/cu.usbmodem*`，連線後按「查詢 IP」；預期顯示 `IP:x.x.x.x`。
- [ ] 在 LabVIEW TCP Write 發送 `DATA:SN001,SN002\r\n` 至 Arduino 的 TCP port。
- [ ] 在 LabVIEW TCP Read 啟用 **CRLF terminated**；預期立刻收到
  `ACK:ACCEPTED,<工站>,SN001,SN002\r\n`。
- [ ] 測試結束後，預期每一 SN 收到一行
  `RESULT:<SN>,PASS|FAIL,<說明>\r\n`。
- [ ] 故意給無效 CSV 根路徑或不合法批次；預期收到 `NACK:REJECTED\r\n`。

## 3. B482 DFU／BT 實機驗證

- [ ] Mac 的截圖儲存位置設為 Agent 的「螢幕截圖路徑」，例如 `~/Desktop/ScreenShot`。
- [ ] 確認 Arduino `SCREENSHOT` 能觸發 Command+Shift+3；確認檔案最晚在 15 秒內出現。
- [ ] 用 Agent 的「製作模板」自真實截圖裁切穩定區塊；不要裁切 PASS／FAIL／TESTING 狀態格。
- [ ] DFU_2：送入 1–4 個 SN，確認每個 SN 皆輸入左下欄位並按 `OK`，再確認測試資料夾開始建立。
- [ ] BT：確認 Agent 只點擊 `Start All`，再確認測試資料夾開始建立。
- [ ] FCT：推入治具後確認 Agent 不點擊任何 UI，直接監聽輸出資料夾。
- [ ] 每個 SN 的目錄存在 `YYYYMMDD_HH-MM-SS.* / system / device.log` 與 `records.csv` 或 `record.csv`。

## 4. Demo 完成條件

- [ ] Agent 無要求或使用 macOS Accessibility、Automation、AppleScript 權限。
- [ ] LabVIEW 收到每批 `ACK`（或適當 `NACK`）與每個 SN 的最終 `RESULT`。
- [ ] 結果只取與 Mac 當下時間最接近的時間戳資料夾，不取舊重工資料。
- [ ] 偏好設定重啟後仍保留：CDC port、CSV 路徑、Log 路徑、模板路徑、截圖路徑與工站。
