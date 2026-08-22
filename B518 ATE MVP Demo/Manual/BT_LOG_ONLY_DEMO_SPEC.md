# BT 純 Log Demo：現場操作與判讀規格

本文件記錄 BT 電腦尚無法穩定使用 Arduino HID 時的替代 Demo 流程。此功能只讀取 BT TestData CSV；不移動滑鼠、不輸入鍵盤、不點擊 BT HMI，也不需要 USB CDC 已連線。

## 使用方式

1. 在 Atlas Agent 選擇 `BT`，並設定：
   - `BT TestData 根路徑`：BT 的 `TestData` 根目錄，作為最終 PASS／FAIL／NOTEST 來源。
   - `BT CaseInfo 根路徑（選填）`：`thread1CaseInfo_YYYY-MM-DD.txt` 至 `thread4CaseInfo_YYYY-MM-DD.txt` 所在目錄，作為即時進度來源。若留空，會改在 TestData 根路徑及其當日子目錄尋找。
2. 按 `Demo` 開啟視窗。
3. 依展示需求按下：
   - `BT Log Start All`：監聽 Thread0～3（slot1～4）。
   - `BT Log Start 1`～`BT Log Start 4`：只監聽對應一個 Thread。
4. Agent 顯示 `TESTING` 後，由 TE 在 BT 儀器 HMI 手動開始測試。
5. Agent 收到穩定、有效的 CSV 後立即顯示結果；本模式只顯示於 Agent，**不送出 TCP ACK／RESULT／NACK**。

## CaseInfo 即時進度

CaseInfo 只補充「正在測什麼」，不參與最終良率判定。對應關係為：

| CaseInfo | 結果 CSV | Agent |
| --- | --- | --- |
| thread1 | Thread0 | slot1 |
| thread2 | Thread1 | slot2 |
| thread3 | Thread2 | slot3 |
| thread4 | Thread3 | slot4 |

- `OpenFixture` 及中間測項：顯示 `TESTING`，並在 Log 顯示當前測項。
- `SNRead`：鎖定並顯示該 thread 的實際 SN，狀態仍為 `TESTING`。
- `CloseFixture`：顯示 `COMPLETING`，繼續等待最終 CSV。
- 最終 CSV 到達後，覆蓋同一 slot 的進度，定案為 `PASS`、`FAIL` 或 `NOTEST`；後續 CaseInfo 不得覆蓋已定案結果。

CaseInfo 為當日累積檔，而且實機可能把兩筆記錄連在同一行。Agent 會以每筆記錄內的時間戳切分，只接受監聽啟動前 30 秒以後的記錄。CaseInfo 不存在、正在寫入或格式異常時，Agent 只記錄警告，不會停止 TestData CSV 監聽。

## Thread、slot 與結果

| Thread | slot | CSV 檔名 SN | Agent 結果 |
| --- | --- | --- | --- |
| Thread0 | slot1 | 非空白 | PASS 或 FAIL |
| Thread1 | slot2 | 非空白 | PASS 或 FAIL |
| Thread2 | slot3 | 非空白 | PASS 或 FAIL |
| Thread3 | slot4 | 非空白 | PASS 或 FAIL |
| 任一 Thread | 對應 slot | 空白 `[]` 且檔案為 `FAILED` | NOTEST（空治具） |

BT 的實體檔案格式為：

```text
TestData/YYYY-MM-DD/PASSED|FAILED/
[ThreadN][測試設定][SN][PASSED|FAILED][YYYYMMDDHHMMSS].csv
```

程式會同時驗證資料夾、檔名與 CSV 的 `SerialNumber`、`Unit Number`、`Test Pass/Fail Status`、`StartTime`、`EndTime`。只有空 SN 且三處均為 `FAILED` 的特例，才會被視為 `NOTEST`，不會誤判成產品 FAIL。

## 新檔與批次防呆

- 啟動監聽前已存在且未變動的 CSV 視為舊資料，不採用。
- 接受 CSV 時間可比啟動早 30 秒，允許 TE 先開始測試再按 Log Demo。
- 第一份合格 CSV 的檔名時間會鎖定為本輪批次；後續只收相同時間戳的 Thread0～3。
- CSV 檔案大小與修改時間需連續穩定 **5 秒** 才解析，避免讀到半成品。
- `Start All` 等待所選 Thread 全部完成；單一 `Start N` 收到對應 Thread 後立即完成。
- 沒有收齊資料時會持續監聽至人員按「停止監聽」或設定的保護逾時。

## 人工覆核與通知

不同批次時間戳，或同一 Thread 出現第二份不同 CSV 時，Agent 會彈出人工覆核視窗：

- 批次衝突可選擇保留原批次、改用新批次，或停止監聽。
- 同 Thread 重複檔可選擇保留原 CSV、採用候選 CSV，或停止監聽。

CSV 結構、狀態或時間不一致時，也會顯示一次通知並寫入 Log。同一 session 中相同檔案與相同錯誤不會重複彈窗；新檔案或不同錯誤才會再次提醒。

## 與正式 BT JOB 的關係

本規格只變更「無 SN Log Demo」。既有已知 SN 的正式 BT JOB 仍保留 OpenCV 視窗／Start 定位、嚴格 SN 比對與人工覆核流程，避免改動 DFU、FCT 及既有正式協定。
