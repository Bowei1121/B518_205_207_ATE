# B518 ATE 方案三：AppleAgent 現場確認清單

- 文件版本：V01
- 建立日期：2026-07-17
- 使用時機：現場確認 AppleAgent、ATA、Atlas 與 B518 ATE 方案三的整合可行性。
- 勾選原則：每一項應由現場人員實際驗證；無法確認時請記錄原因、截圖、Log 或負責窗口。

## 一、現場基本資訊

- [ ] 已確認客戶廠區、產線、工站名稱與 StationId。
- [ ] 已確認測試 Mac mini 的主機名稱、macOS 版本、Intel/Apple Silicon 架構。
- [ ] 已確認 Atlas 測試程式名稱、版本與啟動方式。
- [ ] 已確認測試 Mac mini 的網路 IP、Subnet、Gateway 與 VLAN。
- [ ] 已確認 B518 上位機/LabVIEW 電腦與測試 Mac mini 是否位於同一個 Layer-2 網段。
- [ ] 已確認現場網路允許 TCP 連線及 mDNS multicast（UDP 5353）。
- [ ] 已確認可由客戶授權人員操作測試 Mac mini 的終端機。
- [ ] 已確認可取得必要的 Apple/客戶機密文件、SDK 或 sample code，且使用方式符合保密規範。

## 二、FactoryAutomation、ATA 與 AppleAgent 安裝狀態

- [ ] 已確認測試 Mac 上存在 `/Library/FactoryAutomation`。
- [ ] 已確認目錄內存在 `AppleTestStationAutomation.framework`。
- [ ] 已確認目錄內存在 `AppleTestStationControl.framework`。
- [ ] 已確認目錄內存在 `eTraveler.framework`。
- [ ] 已確認 `StationHerder` 已安裝且處於可運作狀態。
- [ ] 已確認 AppleAgent 已安裝、已啟動，並取得其版本。
- [ ] 已確認 AppleAgent 的設定檔、Log 位置與重啟方式。
- [ ] 已確認 FactoryAutomation／AppleAgent framework 支援現場 macOS 與 CPU 架構。
- [ ] 已取得目前實際使用的 AppleAgent Protocol、ATA SDK、header 與 eTraveler 文件版本。

## 三、Bonjour 與 AppleAgent 服務探索

- [ ] 在測試 Mac 執行 `dns-sd -V` 成功，確認 Bonjour 工具可用。
- [ ] 在測試 Mac 執行 `dns-sd -B _AppleAgent._tcp local.`。
- [ ] 指令可看到 `_AppleAgent._tcp` 的 `Add` 服務事件。
- [ ] 已記錄 AppleAgent 的 Service Name，並確認其對應 StationId。
- [ ] 已使用 `dns-sd -L "<Service Name>" _AppleAgent._tcp local.` 取得 hostname 與 port。
- [ ] 已記錄 AppleAgent 的 hostname、IP、port、TXT record 與 StationId。
- [ ] 在 B518 上位機或 Adapter 主機也可發現同一個 `_AppleAgent._tcp` 服務。
- [ ] 若無法跨網段探索，已確認固定 IP/port 或 mDNS reflector 的替代方案。
- [ ] 若服務找不到，已確認 AppleAgent 是否啟動、Atlas 是否已註冊、VLAN 是否阻擋 multicast。

## 四、Atlas 與 ATA 註冊確認

- [ ] 已確認 Atlas 是否為實際的 Test Station Software。
- [ ] 已確認 Atlas 是否連結 `AppleTestStationAutomation.framework`。
- [ ] 已確認 Atlas 啟動後會向 AppleAgent／StationHerder 註冊 Tester。
- [ ] 已取得 Atlas 的 TesterId。
- [ ] 已取得每個 Tester 的 Slot 數量。
- [ ] 已確認工站為單 Slot、多 Slot（Gang）或多 Gang 架構。
- [ ] 已確認多 Slot DUT 是否必須同時 Start/Finish。
- [ ] 已確認 Fixture Control 是否啟用。
- [ ] 已確認工站是否啟用 Async 模式。
- [ ] 若為 Async，已確認 ReadyForLoad、ReadyForUnload 與 UnloadComplete 的實際行為。
- [ ] 已確認 Atlas 能接收 eTraveler/Start 指令。
- [ ] 已確認 Atlas 能以 `finishedWithResults` 或等效方式回報測試結果。

## 五、AppleAgent REST 協定確認

- [ ] 已取得 AppleAgent 的實際 HTTP/HTTPS URL path。
- [ ] 已確認每個命令使用的 HTTP method。
- [ ] 已確認 request/response Content-Type 與字元編碼。
- [ ] 已確認是否需要帳號、Token、Client Certificate 或其他 authentication。
- [ ] 已確認是否使用 TLS，以及憑證管理方式。
- [ ] 已取得成功與錯誤 HTTP status 的定義。
- [ ] 已確認 `Version` 欄位應使用的值。
- [ ] 已確認 UUID 格式與大小寫要求。
- [ ] 已確認 TEST_UUID 是否由 Vendor Control/B518 產生。
- [ ] 已確認同一 DUT 重測時 TEST_UUID 的處理規則。
- [ ] 已確認 QueryStatus 最小輪詢間隔；預設不快於每 1 秒一次。
- [ ] 已確認 `Abort` 與 `RequestOffline` 已棄用後的替代處理流程。
- [ ] 已確認 Reset 類命令的權限、允許範圍及操作窗口。

## 六、最小端到端測試（Go/No-Go）

- [ ] `QueryConfig` 成功回傳 StationId、TesterId、NumberOfSlots、SoftwareVersion。
- [ ] `QueryStatus` 成功回傳每個 Tester/Slot 的狀態。
- [ ] 測試前 Slot 狀態可確認為 `Idle`。
- [ ] 使用測試用 DUTId 執行 `QueryUOP`，可確認 SFC 資格檢查結果。
- [ ] B518 產生並保存一組 TEST_UUID。
- [ ] 以 DUTId、TesterId、SlotId、TEST_UUID 發送 `Start`。
- [ ] Start response 的 ErrCode/ErrMsg 可正確判讀。
- [ ] `QueryStatus` 可看到 DUT 進入 `Running`。
- [ ] 測試結束後 `QueryStatus` 可看到 `TestCompleted`。
- [ ] `QueryStatus` 可取得 `BinCode = PASS` 或 `FAIL`。
- [ ] `QueryStatus` 的 DUTId、TesterId、SlotId、TEST_UUID 與 Start request 一致。
- [ ] B518 可將結果成功傳回 LabVIEW／MES／PLC／Robot Controller。

## 七、測試結果與 records.csv 對應

- [ ] 已確認 Atlas 結果資料夾根目錄。
- [ ] 已確認資料夾命名格式，例如 `<DUTId>/<timestamp>.<suffix>/system/records.csv`。
- [ ] 已確認 `records.csv` 中的 `PrimaryIdentity` 對應 DUTId。
- [ ] 已確認每個 DUT 的資料夾與測試起始時間可被可靠辨識。
- [ ] 已確認 `records.csv` 的 `startTime`、`stopTime` 時區與 Mac 系統時間一致。
- [ ] 已確認整體 PASS/FAIL 判定規則；例如任一測項 FAIL 即整體 FAIL。
- [ ] 已確認 `records.csv` 是否一定存在，或需同時支援 `record.csv`／其他結果檔。
- [ ] 已確認 `device.log`、原始 Log 與 CSV 的保存位置及保留期限。
- [ ] 已確認 records.csv 是否包含詳細測項、量測值、上下限、失敗訊息。
- [ ] 已確認 TEST_UUID 是否可寫入 eTraveler、Atlas metadata 或其他永久保存欄位。
- [ ] 若無法保存 TEST_UUID，已確認以 DUTId + Start Time + SlotId 關聯的容許誤差與重測規則。

## 八、治具、搬運與 Async 行為

- [ ] 已確認 B518/Robot 的 Load DUT 時機。
- [ ] 已確認 B518/Robot 的 Unload DUT 時機。
- [ ] 已確認標準模式下 `TestCompleted` 後是否可直接卸料。
- [ ] 已確認 Fixture Control Open/Close 的可用性。
- [ ] 已確認 Fixture Control Open/Close 的完成判斷方式。
- [ ] 已確認 Async 模式下不可使用 Fixture Control 的限制。
- [ ] 已確認 Async 模式下不使用 Start `Timeout` 的限制。
- [ ] 已確認 ReadyForLoad=YES 時，Robot 是否可安全放入 DUT。
- [ ] 已確認 ReadyForUnload=YES 時，Robot 是否可安全取出 DUT。
- [ ] 已確認 `UnloadComplete` 發送時機與成功回應。
- [ ] 已確認治具開關、Robot、DUT 存在感測等安全 interlock。

## 九、異常、重啟與資料一致性

- [ ] 已測試 AppleAgent 無法連線時的 B518 顯示與復原流程。
- [ ] 已測試 Atlas 異常結束時的 Slot `Error` 狀態與 Log。
- [ ] 已測試測試逾時時的 `Timeout` 狀態與處理流程。
- [ ] 已測試 DUT 測試 FAIL 時，B518、LabVIEW 與 MES 的處理一致性。
- [ ] 已測試測試中斷線後，B518 可依 TEST_UUID 恢復查詢。
- [ ] 已測試 B518 Adapter 重啟後，可從 SQLite/Event Log 恢復未完成批次。
- [ ] 已確認 ResetAgent、RestartAgent、RestartTestApp、RebootHost 的權限與核准流程。
- [ ] 已確認 Reset/Reboot 不可由一般生產流程自動觸發。
- [ ] 已確認同一 DUT 重測、重工、重複 CSV 資料夾時不會誤取舊結果。
- [ ] 已確認事件 Log 不包含不必要的機密 DUT 資料或憑證。

## 十、Arduino／Legacy Provider 備援確認

- [ ] 已確認 AppleAgent Native Provider 可直接回傳 PASS/FAIL 至上位機，不依賴 Arduino。
- [ ] 已確認現有 Arduino 是否仍負責治具、按鈕、燈號、Robot I/O 或隔離功能。
- [ ] 已確認 Atlas UI 無 API 時，Arduino USB HID 可作為 Legacy Provider。
- [ ] 已確認 Legacy Provider 使用的 USB CDC port、TCP IP、port、CRLF 訊框。
- [ ] 已確認 OpenCV 模板、截圖位置與雙螢幕限制。
- [ ] 已確認 Legacy CSV/Log 監控可正確以 DUTId + 測試時間取回結果。
- [ ] 已確認 AppleAgent Native 與 Legacy Provider 的切換條件及操作人員指示。

## 十一、現場結論

- [ ] Go：完成 `Idle → Start → Running → TestCompleted → PASS/FAIL`，可進入正式方案三開發。
- [ ] Conditional Go：AppleAgent 可發現但 Atlas/結果映射尚待客戶補件；先完成 Adapter PoC。
- [ ] No-Go：無 AppleAgent/ATA 串接能力或客戶無法提供必要規格；維持 Legacy UI/HID/CSV 方案。

### 現場記錄

- StationId：
- AppleAgent Service Name：
- Host/IP/Port：
- TesterId／Slot 數：
- Async：
- Fixture Control：
- Atlas 版本：
- AppleAgent/FactoryAutomation 版本：
- 測試 DUTId：
- 測試 TEST_UUID：
- 結果資料夾：
- 現場窗口：
- 未完成項目與原因：
- 下一步與負責人：

## 十二、版本紀錄

| 版本 | 日期 | 說明 |
|---|---|---|
| V01 | 2026-07-17 | 初版現場確認與 Go/No-Go 清單 |
