# B518 ATE 方案三：AppleAgent／ATA／Atlas 整合分析

- 文件版本：V01
- 建立日期：2026-07-17
- 適用範圍：B518 ATE 方案三之技術可行性評估與開發規劃
- 參考文件：
  - `20230919_AppleAgent Protocol Document Ver DRAFT_0.2.3.pdf`
  - `AppleTestAutomationAPI-v2.0.3.pdf`

## 一、執行摘要

AppleAgent 與 Apple Test Automation API（ATA）可形成一條完整的 Apple 工廠自動化控制鏈，具備作為 B518 ATE「方案三」的潛力。

建議方案三定位為：

> 以 AppleAgent 官方協定控制 Atlas／測試站並取得測試狀態及 PASS/FAIL；現有 Atlas UI/HID 自動化保留為相容性備援。

整體結論如下。

| 項目 | 評估 |
|---|---|
| 自動啟動測試 | 高度可行 |
| 多 Slot／多 Tester | 支援 |
| PASS／FAIL 結果 | 明確支援 |
| 詳細測項及量測值 | 需補齊 eTraveler／Atlas 規格後確認 |
| Atlas 串接 | 條件式可行；兩份文件未直接提及 Atlas |
| LabVIEW 作為上位控制器 | 可行 |
| LabVIEW 直接整合 ATA Framework | 不建議 |
| Arduino 作為測試結果通道 | AppleAgent 方案中非必要 |
| 建議開發時程 | 約 10～12 週；若需修改 Atlas，另加 2～4 週 |

最關鍵的 Go/No-Go 項目不是 REST 或 LabVIEW 是否能實作，而是客戶現場的 Atlas 是否已透過 ATA 註冊至 AppleAgent，以及是否能取得現行 API endpoint、SDK、header 與 eTraveler 格式。

## 二、文件重點與架構

### 2.1 AppleAgent Protocol Document DRAFT 0.2.3

此文件定義 Vendor Control 與 AppleAgent 間的通訊協定。

- 通訊格式：REST + JSON。
- 服務探索：Bonjour。
  - Service Type：`_AppleAgent._tcp`
  - Service Name：`StationId`
- 支援 Station、Tester、Slot 的階層。
- `UUID` 識別一個 request/response；`TEST_UUID` 識別一個 DUT 的測試生命週期。
- 支援標準模式、Fixture Control 模式、Async Pipe 模式。

主要命令如下。

| 命令 | 用途 |
|---|---|
| `QueryConfig` | 取得 Tester、Slot 數、軟體版本、Fixture Control 及 Async 設定 |
| `QueryStatus` | 取得每個 Slot 的測試狀態與結果 |
| `Start` | 傳入 DUTId、CarrierId、TestType、TEST_UUID 後啟動測試 |
| `QueryUOP` | 向 SFC 查詢 DUT 是否符合本站測試資格 |
| `RequestFixtureControl` | 開啟或關閉治具；Async 不可用 |
| `UnloadComplete` | Async 測站回報卸料完成 |
| `Reset` | 重置 Agent、測試應用程式或 Host；應受權限控管 |
| `Abort`、`RequestOffline` | 文件標記為 Deprecated |

`QueryStatus` 的重要回傳欄位：

- `DUTId`
- `CarrierId`
- `TEST_UUID`
- `TestStage`
- `TestType`
- `DevState`
- `BinCode`
- `SlotMessage`
- `StationsToSkip`
- Async 模式下的 `ReadyForLoad`、`ReadyForUnload`

主要 DUT 狀態為 `Idle`、`Running`、`TestCompleted`、`Timeout`、`Error`、`Offline`。文件建議 `QueryStatus` 的查詢週期大於 1 秒，不應高頻輪詢。

### 2.2 Apple Test Automation API v2.0.3

此文件描述測試程式端如何接入 Apple FactoryAutomation，而非 Vendor Control 的 REST 協定。

關鍵元件：

- `AppleTestStationAutomation.framework`（ATA）：測試程式使用的介面。
- `AppleTestStationControl.framework`（ATC）：控制端或本機 Agent 使用的介面。
- `eTraveler.framework`：控制端與測試程式間的資料定義。
- `StationHerder`：串接控制端與測試程式的系統 daemon。
- `Notifaketion`：模擬控制端、啟動測試與偵錯用工具。

ATA 測試程式的基本流程：

1. 建立 `AppleControlledStation`，設定名稱、Class 與 Slot 數。
2. 呼叫 ATA 的 `registerStation` 註冊測站。
3. 實作 delegate，接收控制端的 Start 通知與 eTraveler。
4. 解析每個 Slot 的 eTraveler，開始實際測試。
5. 測試結束後呼叫 `finishedWithResults` 回報。

ATA 支援單一 DUT、多 Slot（Gang）與多 Gang 獨立測試。測試結果定義包含 Passed、Failed、Incomplete、Disqualify Fail、Abort 及 Custom Test Result。

### 2.3 兩份文件的關係

```text
B518 / Vendor Control
        │ REST + JSON
        ▼
AppleAgent / ATC
        │ StationHerder / FactoryAutomation
        ▼
ATA Framework
        │
        ▼
Atlas 或 Test Station Software
        │
        ▼
治具、儀器與 DUT
```

AppleAgent 是上位控制端到測站的協定層；ATA 是測試程式內部整合層。兩者是同一自動化鏈的不同位置，不是替代方案。

## 三、自動化能力與測試結果

### 3.1 可確定取得的結果

AppleAgent 的 `QueryStatus` 可取得：

- 測試是否開始、執行中、完成、逾時或錯誤。
- DUT 的 `PASS`／`FAIL`，由 `BinCode` 判斷。
- Slot 特定的錯誤或狀態訊息，來自 `SlotMessage`。
- DUT、Tester、Slot、`TEST_UUID` 的關聯。

範例：

```json
{
  "DevState": "TestCompleted",
  "BinCode": "PASS",
  "SlotMessage": ""
}
```

注意事項：

- `ErrCode = 0` 只代表 AppleAgent 已接受或完成該命令，不代表 DUT 測試通過。
- `BinCode` 才是 DUT 測試結果。
- `QueryUOP` 回覆 `SFCResponse = OK` 只表示 DUT 具備本站測試資格，不是測試 PASS。

### 3.2 尚無法保證取得的資料

目前兩份文件不足以保證可取得下列細節：

- 每一測項名稱、量測值、上下限與單位。
- 第一個失敗測項或完整失敗原因。
- 完整原始測試 Log。
- Atlas 的實際 CSV/資料夾格式。

ATA 文件指出 eTraveler 可傳遞測試結果及 Custom Result，但未提供 `ETraveler Structure`、`eTraveler_TestResults.h`、`TestStationKeys.h` 等完整定義。方案三第一階段應承諾「控制 + 整體 PASS/FAIL」，詳細測項列為第二階段驗證項目。

## 四、records.csv 與 AppleAgent 欄位對應

已檢視 B482 範例檔案：

`HK5GX100KRW00003YV/20250809_14-52-53.927-81ED0A/system/records.csv`

對應關係如下。

| AppleAgent 欄位 | records.csv／資料夾內容 | 結論 |
|---|---|---|
| `DUTId` | `PrimaryIdentity = HK5GX100KRW00003YV` | 可直接對應 |
| `TEST_UUID` | CSV 無 UUID 欄位 | 不可直接對應 |
| 測試開始時間 | 資料夾 `20250809_14-52-53.927`；CSV `startTime = Aug 9 2025 2:52:53.9290 PM` | 可作為輔助關聯 |
| 測試結束時間 | CSV `stopTime = Aug 9 2025 3:01:28.4010 PM` | 可保存為完成時間 |
| 測試結果 | 501 筆測項 `PASS`，未見 FAIL | 此案例可判定整體 PASS |

資料夾尾碼 `81ED0A` 僅六碼，並非標準 UUID；不可假設它等於 AppleAgent `TEST_UUID`。

正式實作建議：B518 在送出 `Start` 前產生 `TEST_UUID`，並保存下列關聯資料：

```text
TEST_UUID
  ├─ DUTId / PrimaryIdentity
  ├─ StationId
  ├─ TesterId
  ├─ SlotId
  ├─ Start command timestamp
  ├─ Atlas result-folder path
  ├─ records.csv startTime / stopTime
  └─ BinCode / overall PASS-FAIL
```

當 Atlas 產生資料夾時，可先以 `DUTId + 測試開始時間` 回填關聯；若現場支援 eTraveler，應優先將 `TEST_UUID` 寫入 Atlas 可保存的 metadata，避免同一 SN 重測時誤配結果。

## 五、Atlas 串接可行性

### 5.1 可行的條件

若客戶所稱 Atlas 是 Test Station Software，且已完成下列事項，則 B518 串接 AppleAgent 的可行性高：

- Atlas 已連結 `AppleTestStationAutomation.framework`。
- Atlas 已向 StationHerder／AppleAgent 註冊 Station。
- Atlas 能接收 eTraveler Start。
- Atlas 能以 `finishedWithResults` 回報結果。

此時 B518 只需實作 Vendor Control：發現 AppleAgent、查詢設定、送出 Start、查詢狀態、回收結果。

### 5.2 三種現況與風險

| Atlas 現況 | 可行性 | 處置 |
|---|---|---|
| 已註冊 ATA／AppleAgent | 高 | 實作 B518 Vendor Control |
| 有 Atlas 原始碼，可加入 ATA | 中高 | 需客戶提供 SDK、原始碼及整合資源 |
| 無 ATA 且無原始碼 | 低 | 使用 UI/HID/CSV 監控作為 Legacy Provider |

兩份 Apple 文件皆未出現 Atlas 名稱，故不可僅憑文件宣稱 Atlas 已相容。必須由客戶實機或現行整合文件驗證。

### 5.3 現場 Go/No-Go 驗證清單

1. Mac 上是否有 `/Library/FactoryAutomation` 及 ATA/ATC/eTraveler frameworks。
2. AppleAgent、StationHerder 是否執行。
3. Bonjour 是否能發現 `_AppleAgent._tcp`。
4. `QueryConfig` 是否取得 TesterId、Slot 數與軟體版本。
5. 啟動 Atlas 後，Tester 是否完成註冊。
6. 是否能完成一次 `Idle → Start → Running → TestCompleted → PASS/FAIL`。
7. AppleAgent 的 HTTP endpoint、method、port、驗證與 TLS 規格是否可取得。
8. 現有 framework 是否支援現場 macOS、Intel 或 Apple Silicon 架構。

特別注意：AppleAgent PDF 僅說明 REST/JSON 與訊息內容，未定義 URL path、HTTP method、authentication、TLS 或 HTTP error status；必須以現行 SDK、sample code 或受控的實機測試補齊。

## 六、Bonjour 驗證與 Python 使用方式

### 6.1 確認 Bonjour 與 AppleAgent 服務

Bonjour 是 macOS 內建的 mDNS/DNS-SD 機制，並非需手動啟動的一般應用程式。請於測試 Mac 的終端機執行：

```zsh
dns-sd -V
```

若顯示版本資訊，代表 Bonjour 工具與系統服務可用。

瀏覽 AppleAgent 服務：

```zsh
dns-sd -B _AppleAgent._tcp local.
```

若看到：

```text
Timestamp  A/R  Domain  Service Type       Instance Name
14:20:01   Add  local.  _AppleAgent._tcp.  B518_FCT_01
```

代表 AppleAgent 已發布服務，`B518_FCT_01` 為 StationId/Service Name。按 `Ctrl+C` 結束後，以該名稱取得 Host 與 Port：

```zsh
dns-sd -L "B518_FCT_01" _AppleAgent._tcp local.
```

若 `dns-sd` 正常但找不到服務，常見原因為 AppleAgent 未啟動、Atlas 未註冊、設備跨 VLAN、網路阻擋 mDNS UDP 5353，或現場 service type 與文件不同。

### 6.2 Python 以 Zeroconf 發現 AppleAgent

安裝套件：

```zsh
python3 -m pip install zeroconf requests
```

範例：

```python
from zeroconf import ServiceBrowser, ServiceListener, Zeroconf

SERVICE_TYPE = "_AppleAgent._tcp.local."

class AppleAgentListener(ServiceListener):
    def add_service(self, zc, service_type, name):
        info = zc.get_service_info(service_type, name, timeout=3000)
        if info is None:
            print(f"無法解析：{name}")
            return
        print(f"Service: {name}")
        print(f"Host: {info.server}")
        print(f"IP: {info.parsed_addresses()}")
        print(f"Port: {info.port}")
        print(f"TXT: {info.properties}")

    def update_service(self, zc, service_type, name):
        pass

    def remove_service(self, zc, service_type, name):
        print(f"服務離線：{name}")

zeroconf = Zeroconf()
browser = ServiceBrowser(zeroconf, SERVICE_TYPE, AppleAgentListener())

try:
    input("正在搜尋 AppleAgent；按 Enter 結束。\n")
finally:
    browser.cancel()
    zeroconf.close()
```

Bonjour 只負責取得 AppleAgent 的 hostname/IP/port。後續要呼叫 AppleAgent REST API 時，必須依現場取得的 endpoint、HTTP method 及驗證規則送出 JSON；不可先假設 URL 為根路徑或一定使用 POST。

## 七、Arduino 是否仍需要？

### 7.1 結論

若 AppleAgent 與 Atlas ATA 串接成功，Arduino 不再是「測試結果回傳上位機」的必要元件。

```text
LabVIEW / B518 上位機
       │ Ethernet：REST/JSON
       ▼
AppleAgent（測試 Mac）
       │
       ▼
Atlas / ATA Test Software
       │
       ▼
QueryStatus 回傳 Running / TestCompleted / PASS / FAIL
       │
       └──────── Ethernet 回傳 B518 上位機
```

B518 送出 `Start` 後，以 `QueryStatus` 取得 `DevState` 與 `BinCode`，並直接回報 LabVIEW、MES、PLC 或 Robot Controller。

### 7.2 Arduino 的保留情境

既有 MVP 中 Arduino 具有 TCP ↔ USB CDC bridge 與 USB HID 鍵盤/滑鼠角色。因此以下情境仍應保留 Arduino：

- Atlas 尚未支援 AppleAgent／ATA。
- 客戶無法提供 AppleAgent REST endpoint。
- 必須操作既有 Atlas UI。
- 受 macOS 隱私權限制，需要外接 USB HID 進行鍵鼠控制。
- Arduino 另負責治具、按鈕、燈號、Robot I/O 或隔離需求。

建議正式架構採雙 Provider：

- `AppleAgentProvider`：優先使用，走官方協定。
- `LegacyAtlasProvider`：使用現有 OpenCV/HID/CSV 監控，作為備援。

上層 B518 流程不應依賴底層 Provider；如此 AppleAgent 尚未開放或故障時，能切換至 Legacy 路徑。

## 八、程式架構建議

### 8.1 模組劃分

| 模組 | 職責 |
|---|---|
| Discovery Service | Bonjour 發現、StationId/host/port 管理、重連 |
| AppleAgent REST Client | QueryConfig、QueryStatus、Start、QueryUOP、Fixture Control、UnloadComplete |
| Station State Machine | 每個 Tester/Slot 的狀態、超時、錯誤、復原 |
| Result Correlation | 將 TEST_UUID、DUTId、Slot、Atlas CSV/Log 關聯 |
| B518 Gateway | 提供 LabVIEW 所需 TCP/REST 訊框 |
| Persistence | SQLite event log、斷電／程式重啟復原 |
| Atlas Provider | AppleAgent Native 或 Legacy UI/HID 實作 |

### 8.2 狀態機

```text
Offline/Error
     │
     ▼
Idle → Loading → StartRequested → Running
                                  │
                     ┌────────────┼────────────┐
                     ▼            ▼            ▼
               TestCompleted    Timeout       Error
                     │
                     ▼
                 Unloading → Idle
```

Fixture Control 狀態應獨立管理，不能混入 DUT 的 `DevState`。Async 模式需額外處理 `ReadyForLoad`、`ReadyForUnload` 與 `UnloadComplete`。

### 8.3 建議訊框

```text
START:<station>,<slot>,<sn>,<test_uuid>\r\n
ACCEPTED:<test_uuid>\r\n
STATUS:<test_uuid>,RUNNING\r\n
RESULT:<test_uuid>,<sn>,PASS\r\n
ERROR:<test_uuid>,<code>,<message>\r\n
```

不可只以 SN 關聯結果，因為同一 SN 可能重測；應優先使用 `TEST_UUID`。

## 九、LabVIEW 限制與建議平台

### 9.1 LabVIEW 作為 Vendor Control

LabVIEW 可用於 TCP、HTTP/REST、JSON、儀器控制、PLC/Robot Sequence，因此可作為 B518 上位控制器。

限制如下：

- Bonjour/mDNS discovery 通常需 wrapper、外部 helper 或改用固定 endpoint。
- 多 Tester/Slot 的非同步狀態機在 Block Diagram 中維護成本較高。
- JSON 巢狀資料結構與 SQLite event log 使用較不便利。
- macOS 的背景 service、簽署與長時間復原機制較適合由原生或 Python daemon 處理。
- 商業量產前須確認所使用 LabVIEW 版本、macOS 相容性及授權支援。

### 9.2 LabVIEW 直接整合 ATA

不建議。ATA API 為 Objective-C object、protocol、delegate 架構；LabVIEW 的 shared-library 呼叫較適合 C ABI function。若必須由 LabVIEW 使用 ATA，應先由 Swift/Objective-C 建立 C ABI wrapper，成本與風險均較高。

### 9.3 建議 Hybrid 架構

```text
LabVIEW
  └─ 儀器、PLC、Robot、ATE Sequence
          │ localhost TCP/REST
          ▼
Python 或 Swift AppleAgent Adapter
  └─ Bonjour、REST/JSON、狀態機、結果保存
          │
          ▼
AppleAgent → ATA → Atlas
```

平台選擇建議：

| 功能 | 建議平台 |
|---|---|
| AppleAgent REST Client | Python；可延續既有 B518 MVP |
| 直接連結 ATA Framework | Swift／Objective-C |
| 長時間背景 Service | Swift、Python、Go 或 Rust |
| 儀器與既有 ATE Sequence | LabVIEW |

## 十、開發時程與驗收 Gate

以下以兩位軟體工程師與一位客戶／現場窗口估算。

| 週次 | 工作內容 | 驗收 Gate |
|---|---|---|
| 第 1 週 | SDK、文件、現場設備盤點 | 確認 AppleAgent、ATA、Atlas 註冊關係 |
| 第 2 週 | Connectivity Spike | Bonjour、QueryConfig、QueryStatus 成功 |
| 第 3～4 週 | AppleAgent Client | REST、JSON、UUID、timeout、schema 驗證 |
| 第 5～6 週 | 測試狀態機 | Start、Running、Completed、PASS/FAIL、Error、多 Slot |
| 第 7～8 週 | B518/LabVIEW 整合 | SN、Slot、TEST_UUID、Load/Unload、結果回報 |
| 第 9～10 週 | Atlas 實機整合 | DFU/FCT/BT、斷線、重啟、重工、異常流程 |
| 第 11～12 週 | Pilot/量產強化 | 長時間運轉、Log、復原、部署、操作文件 |

若 Atlas 尚未支援 ATA，需客戶修改 Atlas 或開發 station-side shim，建議增加 2～4 週。

第一週 Go/No-Go 最低通過條件：

```text
Bonjour 發現 AppleAgent
→ QueryConfig 取得 TesterId
→ Atlas Tester 註冊
→ Start 使 DUT 進入 Running
→ QueryStatus 取得 TestCompleted 與 PASS/FAIL
```

未通過時，不應承諾 AppleAgent 正式整合時程；應維持既有 UI/HID/CSV 路徑，並將其定位為 Legacy Provider。

## 十一、版本紀錄

| 版本 | 日期 | 說明 |
|---|---|---|
| V01 | 2026-07-17 | 初版：整合 AppleAgent/ATA 文件、Atlas 評估、records.csv、Bonjour、Arduino、程式架構與時程 |
