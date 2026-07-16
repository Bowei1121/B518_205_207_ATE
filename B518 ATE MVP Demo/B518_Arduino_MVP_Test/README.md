# B518 Arduino MVP Test

UNO R4 WiFi 韌體 MVP：USB CDC 指令控制鍵盤／滑鼠，並以 W5100 TCP server 作為 Mac 與上位機間的雙向橋接。

## 硬體與前置條件

- Arduino UNO R4 WiFi。
- W5100 Ethernet 模組或 Shield，以 SPI 連接；預設 CS 為 D10。若模組不是 D10，修改 `W5100_CS_PIN`。
- Arduino IDE 已安裝 UNO R4 WiFi 對應的 **Arduino Renesas UNO** board package，以及內建 `Ethernet`、`Keyboard`、`Mouse` libraries。
- USB 接到 Mac mini。此 USB 同時提供 CDC serial 與 HID keyboard/mouse。

首次燒錄時的預設 IP、gateway、subnet 與 TCP port 位於 `.ino` 最上方。預設 TCP server 為 `192.168.1.100:5000`。部署時由 Mac mini 用 USB 指令配置各板 IP；韌體會同步由 IP 推導一組本地管理 MAC，因此每個唯一 IP 都會有唯一 MAC。

> HID 指令會實際控制目前登入的 Mac。測試時請先儲存工作、將游標移到安全位置，並保留可中斷 USB 連線的方法。

## USB 指令協議

所有控制指令均建議以 CRLF (`\r\n`) 結束；LF-only 也可使用。成功會回 `OK:...\r\n`，格式錯誤回 `ERR:...\r\n`。

| Mac → Arduino | 動作 |
| --- | --- |
| `M_RESET\n` | 向左上盲移 3000 × 3000，相對定位歸零。 |
| `M_MOVE:X,Y\n` | 先歸零，再右移 X、下移 Y。X/Y 只能是 0 到 10000 的整數。 |
| `M_DELTA:X,Y\n` | 不歸零，直接相對移動 X、Y steps；可使用負值，供座標校正工具的方向鍵測試。 |
| `M_CLICK:L\n` / `M_CLICK:R\n` | 左／右鍵點擊。 |
| `M_SCROLL:V\n` | 滾輪移動 V；正數向上、負數向下。 |
| `K_TYPE:string\n` | 輸入可列印 ASCII 字串，然後送 Enter。 |
| `K_WRITE:string\n` | 輸入可列印 ASCII 字串，不附加 Enter。 |
| `K_KEY:TAB\n` | 輸入一個 Tab，用於切換下一個 DFU 條碼欄位。 |
| `K_SHORTCUT:SCREENSHOT\n` | 送出 macOS Command + Shift + 3，且前後均釋放按鍵。 |
| `SCREENSHOT\n` | `K_SHORTCUT:SCREENSHOT` 的建議別名，供 Atlas Agent 使用。 |
| `GET_IP\n` | 回覆 `IP:192.168.1.100\n`（實際為目前 W5100 IP）。 |
| `NET_SET:A.B.C.D\n` | **僅 USB CDC 可發送**。保存新的 IPv4 位址、立即重新初始化 W5100，回覆 `OK:NET_SET:A.B.C.D\n`。 |
| `NET_RESET\n` | **僅 USB CDC 可發送**。還原編譯時預設 IP，回覆 `OK:NET_RESET:A.B.C.D\n`。 |

`K_TYPE:` 後的內容不可含換行，MVP 僅接受 ASCII `0x20` 到 `0x7E`。條碼例如：`K_TYPE:SN01234567890ABCD\n`。
DFU Agent 使用 `K_WRITE:<SN>` 加上 `K_KEY:TAB` 逐欄填入最多四個 SN，最後再由開始按鈕觸發測試。
`M_SCROLL` 的絕對值也限制為 10000，避免過大的指令長時間佔用 HID 傳送。

`NET_SET` 接受單播 IPv4 host 位址，並排除 `x.x.x.0` 與 `x.x.x.255`。設定儲存在 UNO R4 WiFi 的 EEPROM，斷電或重開機後仍會保留。網路設定指令只會在 Arduino 從 Mac 的 USB CDC 收到時被執行；TCP 收到的資料只會透明轉送到 USB，無法修改設定。

## 多 Arduino 的 USB 配置流程

1. 先只接上 **一台**新 Arduino 的 USB（尚未接入 switch），由 Mac 送出 `NET_SET:192.168.1.101\n`，並以 `GET_IP\n` 確認。
2. 拔除或保留該 USB，接上下一台，依序配置 `192.168.1.102`、`.103` 等不同位址。
3. 全部配置完成後才將各 W5100 接至 switch；上位機以各自的 `IP:5000` 連線。

新板都帶有相同預設 IP，所以不可在尚未完成 USB 配置前同時接到同一個 switch。Mac mini 必須維護已分配 IP 的清單；韌體無法偵測局域網中由其他設備使用的 IP。

## TCP 透明橋接規則

- 上位機連線到設定的 TCP port 後，**所有 TCP bytes** 原封不動寫到 Mac 的 USB CDC serial。
  Atlas Agent 的條碼批次必須是完整的一行，例如 `SN1,SN2\r\n`；TCP 沒有訊息邊界，CRLF 用來避免
  資料分段時誤判成單一 SN，且可直接使用 LabVIEW 的 CRLF 偵測模式。
- Mac 傳入 USB CDC 的一個換行框架若不是上表控制指令，就會**包含原始 CR/LF 在內**原封不動傳至 TCP client。
- USB 端需以 LF 封包；這是為了能先辨識並攔截 `GET_IP` 與 HID 控制指令。單一框架上限 256 bytes。超過上限會丟棄到下一個 LF，並回覆 `ERR:FRAME_TOO_LONG`。
- MVP 同時間只服務一個 TCP client；目前連線結束後才會接受下一個 client。
- 當 Mac 傳的是非控制資料且沒有 TCP client，Arduino 回覆 `ERR:TCP_NOT_CONNECTED`，該資料不會被緩存或重送。

韌體不會輸出開機診斷或 `DATA:`／ACK 前綴，避免污染透明資料流。請讓 Mac 上位程式區分自己的控制回覆 (`IP:`、`OK:`、`ERR:`) 與 TCP payload；若 TCP payload 可能使用這些前綴，建議在上位協議增加訊框或改用獨立 CDC channel（MVP 範圍外）。

## 燒錄與快速測試

1. 用 Arduino IDE 開啟 `B518_Arduino_MVP_Test.ino`，選取 **Arduino UNO R4 WiFi** 並燒錄。
2. 關閉 IDE 的 Serial Monitor，避免它佔用 Mac 的 CDC port。
3. 在 Mac 找出 port，例如 `ls /dev/cu.usbmodem*`，再用序列工具以 115200 baud 開啟。
4. 發送 `GET_IP`，應得到 `IP:...`。接著測試 `M_MOVE:100,100`、`M_DELTA:5,0`、`M_CLICK:L`，最後才測試 `K_TYPE:...`。
5. 從上位機對設定 IP 的 TCP port 連線，測試 TCP → USB 與 USB 非控制資料 → TCP 是否位元組一致。

## 已知 MVP 限制

- 「絕對座標」依賴 macOS 游標可撞到左上邊界；多螢幕、顯示縮放、遠端桌面或 macOS 顯示設定變更，都可能造成實際落點與 X/Y 不一致。
- `K_TYPE` 固定附加 Enter；若未來需要 Tab，建議明確新增 `K_KEY:TAB`，不要以字串內容隱含控制字元。
- W5100 採 Mac 透過 USB 設定並保存的固定 IP；DHCP、重連佇列、驗證／加密與多 client 不包含在 MVP。
