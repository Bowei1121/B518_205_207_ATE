# B518 Arduino MVP Test

UNO R4 Minima／WiFi 韌體 MVP：USB CDC 指令控制鍵盤／滑鼠，並以 W5100 TCP server 作為 Mac 與上位機間的雙向橋接。

## 硬體與前置條件

- Arduino UNO R4 Minima 或 UNO R4 WiFi。請在 Arduino IDE 選擇與板子絲印完全相同的 Board；Agent 的 `BOARD` 欄位會回報實際編譯目標。
- W5100 Ethernet 模組或 Shield，以 SPI 連接；預設 CS 為 D10。若模組不是 D10，修改 `W5100_CS_PIN`。
- Arduino IDE 已安裝 **Arduino UNO R4 Boards**（舊介面可能顯示 **Arduino Renesas UNO**）board package，以及內建 `Ethernet`、`Keyboard`、`Mouse` libraries。
- USB 接到 Mac mini。此 USB 同時提供 CDC serial 與 HID keyboard/mouse。

首次燒錄時的預設 IP、gateway、subnet 與 TCP port 位於 `.ino` 最上方。預設 TCP server 為 `192.168.1.100:5000`。部署時由 Mac mini 用 USB 指令配置各板 IP；韌體會同步由 IP 推導一組本地管理 MAC，因此每個唯一 IP 都會有唯一 MAC。

> HID 指令會實際控制目前登入的 Mac。測試時請先儲存工作、將游標移到安全位置，並保留可中斷 USB 連線的方法。

## 韌體版本與交付前檢核

唯一版本來源是 `firmware_version.h`；目前版本為 **1.0.4**，協定版本為 **1**。每次修改可執行的韌體原始碼後，必須在提交前升版：

```bash
cd "B518 ATE MVP Demo/B518_Arduino_MVP_Test"
python3 bump_firmware_version.py hotfix   # 修正問題：patch +1
python3 bump_firmware_version.py feature  # 相容新功能：minor +1、patch 歸零
python3 bump_firmware_version.py major    # 不相容變更：major +1、其餘歸零
python3 verify_firmware_version.py --base HEAD
```

驗證工具會在 `.ino` 或韌體標頭變動而版本未變時失敗，也會拒絕跳號、倒退或不符合規則的版本。純文件修改不需要升版。重複編譯或燒錄相同來源不升版。

交付前依序執行：升版、版本驗證、以目標板型 Verify／Upload、使用 Serial Monitor 發送 `GET_INFO`、最後才提交 Git。協定格式不相容時才調整 `B518_PROTOCOL_VERSION`；一般新功能不調整協定版本。

## USB 指令協議

Mac Agent → Arduino 的 **USB CDC 控制指令固定使用 LF** (`\n`) 結尾。這是為了相容 macOS 10.14／10.15 與 VM USB CDC；不要在 Arduino Serial Monitor 對控制指令選擇 `NL & CR`。韌體仍可接受標準 CRLF（CR 在 LF 前），並會忽略空閒時殘留的 CR／LF／NUL。成功會回 `OK:...\r\n`，格式錯誤回 `ERR:...\r\n`。

| Mac → Arduino | 動作 |
| --- | --- |
| `M_RESET\n` | 依序回覆 `ACK:M_RESET`、向左上盲移 3000 × 3000、`OK:M_RESET`。 |
| `M_MOVE:X,Y\n` | 先歸零，再右移 X、下移 Y。X/Y 只能是 0 到 10000 的整數。 |
| `M_DELTA:X,Y\n` | 依序回覆 `ACK:M_DELTA`、不歸零直接相對移動 X、Y steps、`OK:M_DELTA`；可使用負值。 |
| `M_ABS:X,Y\n` | 使用第二個絕對 HID 指標移到 0–32767 的 X/Y；不受一般相對滑鼠加速度影響。 |
| `M_ABS_CLICK:L\n` | 在目前絕對 HID 位置按左鍵。 |
| `M_CLICK:L\n` / `M_CLICK:R\n` | 左／右鍵點擊。 |
| `M_SCROLL:V\n` | 滾輪移動 V；正數向上、負數向下。 |
| `K_TYPE:string\n` | 輸入可列印 ASCII 字串，然後送 Enter。 |
| `K_WRITE:string\n` | 輸入可列印 ASCII 字串，不附加 Enter。 |
| `K_KEY:TAB\n` | 輸入一個 Tab，用於切換下一個 DFU 條碼欄位。 |
| `K_SHORTCUT:SCREENSHOT\n` | 送出 macOS Command + Shift + 3，且前後均釋放按鍵。 |
| `SCREENSHOT\n` | `K_SHORTCUT:SCREENSHOT` 的建議別名，供 Atlas Agent 使用；依序回覆 `ACK:SCREENSHOT` 與 `OK:SCREENSHOT`。 |
| `GET_IP\n` | 回覆既有 `IP:192.168.1.100\n`（實際 IP），新版韌體隨後再回覆 `INFO:...`。 |
| `GET_INFO\n` | 回覆韌體識別資訊，例如 `INFO:PRODUCT=B518_ARDUINO_MVP;FW=1.0.0;PROTO=1;BOARD=UNO_R4_MINIMA\n`。 |
| `DIAG_CLEAR\n` | 清除鎖存異常狀態並熄滅板載 LED，回覆 `OK:DIAG_CLEAR`。 |
| `NET_SET:A.B.C.D\n` | **僅 USB CDC 可發送**。保存新的 IPv4 位址、立即重新初始化 W5100，回覆 `OK:NET_SET:A.B.C.D\n`。 |
| `NET_RESET\n` | **僅 USB CDC 可發送**。還原編譯時預設 IP，回覆 `OK:NET_RESET:A.B.C.D\n`。 |

`K_TYPE:` 後的內容不可含換行，MVP 僅接受 ASCII `0x20` 到 `0x7E`。條碼例如：`K_TYPE:SN01234567890ABCD\n`。
DFU Agent 使用 `K_WRITE:<SN>` 加上 `K_KEY:TAB` 逐欄填入最多四個 SN，最後再由開始按鈕觸發測試。
`M_SCROLL` 的絕對值也限制為 10000，避免過大的指令長時間佔用 HID 傳送。

`NET_SET` 接受單播 IPv4 host 位址，並排除 `x.x.x.0` 與 `x.x.x.255`。設定儲存在 UNO R4 的 EEPROM，斷電或重開機後仍會保留。網路設定指令只會在 Arduino 從 Mac 的 USB CDC 收到時被執行；TCP 收到的資料只會透明轉送到 USB，無法修改設定。

`INFO:` 的欄位含義：`PRODUCT` 為產品識別、`FW` 為韌體 SemVer、`PROTO` 為控制協定版本、`BOARD` 為燒錄時選擇的編譯目標、`FAULT` 為異常鎖存狀態，`LAST` 為最後一個異常代碼。`GET_INFO` 適合 Serial Monitor 人工查驗；Atlas Agent 為了相容舊板，僅送 `GET_IP`，再接收新版附帶的 `INFO:`。所有 `ACK:` 表示韌體已解析命令、即將呼叫對應 HID；`OK:` 表示 HID 函式已返回。兩者都不保證 macOS 一定接受 HID report。

### 板載異常 LED

UNO R4 的 `LED_BUILTIN` 在韌體啟動時熄滅。出現訊框過長、控制指令無法識別、參數格式錯誤或非 ASCII 鍵盤資料時，LED 會常亮並保留異常，即使後續指令成功也不會自動熄滅。發送 `GET_INFO` 可查看 `FAULT=1;LAST=...`；處理完原因後發送 `DIAG_CLEAR` 或重新上電才會熄滅。單純尚未建立 TCP client 不視為韌體故障，不會因 `ERR:TCP_NOT_CONNECTED` 單獨點亮 LED。

## 多 Arduino 的 USB 配置流程

1. 先只接上 **一台**新 Arduino 的 USB（尚未接入 switch），由 Mac 送出 `NET_SET:192.168.1.101\n`，並以 `GET_IP\n` 確認。
2. 拔除或保留該 USB，接上下一台，依序配置 `192.168.1.102`、`.103` 等不同位址。
3. 全部配置完成後才將各 W5100 接至 switch；上位機以各自的 `IP:5000` 連線。

新板都帶有相同預設 IP，所以不可在尚未完成 USB 配置前同時接到同一個 switch。Mac mini 必須維護已分配 IP 的清單；韌體無法偵測局域網中由其他設備使用的 IP。

## TCP 透明橋接規則

- 上位機連線到設定的 TCP port 後，**所有 TCP bytes** 原封不動寫到 Mac 的 USB CDC serial。
  Atlas Agent 的 JOB 必須是完整的一行，例如 `BT:JOB=JOB-1;1=SN1,3=SN3\r\n`；TCP 沒有訊息
  邊界，CRLF 用來避免資料分段時誤判，且可直接使用 LabVIEW 的 CRLF 偵測模式。
- Mac 傳入 USB CDC 的一個換行框架若不是上表控制指令，就會**包含原始 CR/LF 在內**原封不動傳至 TCP client。
- USB CDC 的 HID／網路控制端需以 LF 封包；這是為了能先辨識並攔截 `GET_IP` 與 HID 控制指令。Agent 要回傳給 TCP 上位機的 `ACK`／`NACK`／`RESULT` 則仍透過 USB 使用 CRLF，讓 Arduino 保留原始 CRLF 透明轉送。單一框架上限 768 bytes，可容納四個長 SN 的 RESULT。超過上限會丟棄到下一個 LF，並回覆 `ERR:FRAME_TOO_LONG`。
- MVP 同時間只服務一個 TCP client；目前連線結束後才會接受下一個 client。
- 當 Mac 傳的是非控制資料且沒有 TCP client，Arduino 回覆 `ERR:TCP_NOT_CONNECTED`，該資料不會被緩存或重送。

韌體本身不會新增開機診斷、DATA 或 ACK 前綴，避免污染透明資料流；業務 ACK／RESULT 由
Mac Agent 產生。請讓 Mac 程式區分 Arduino 控制回覆 (`IP:`、`OK:`、`ERR:`) 與 TCP payload。

## 燒錄與快速測試

1. 用 Arduino IDE 開啟 `B518_Arduino_MVP_Test.ino`，選取板子絲印對應的 **Arduino UNO R4 Minima** 或 **Arduino UNO R4 WiFi** 並燒錄。
2. 關閉 IDE 的 Serial Monitor，避免它佔用 Mac 的 CDC port。
3. 在 Mac 找出 port，例如 `ls /dev/cu.usbmodem*`，再用序列工具以 115200 baud 開啟。
4. 發送 `GET_INFO`，確認 `FW`、`PROTO`、`BOARD`；再發送 `GET_IP`，應得到 `IP:...` 與同一份 `INFO:...`。接著測試 `M_MOVE:100,100`、`M_DELTA:5,0`、`M_ABS:16384,16384`、`M_ABS_CLICK:L`，最後才測試 `K_TYPE:...`。
5. 從上位機對設定 IP 的 TCP port 連線，測試 TCP → USB 與 USB 非控制資料 → TCP 是否位元組一致。

## 已知 MVP 限制

- 「絕對座標」依賴 macOS 游標可撞到左上邊界；多螢幕、顯示縮放、遠端桌面或 macOS 顯示設定變更，都可能造成實際落點與 X/Y 不一致。
- `K_TYPE` 固定附加 Enter；若未來需要 Tab，建議明確新增 `K_KEY:TAB`，不要以字串內容隱含控制字元。
- W5100 採 Mac 透過 USB 設定並保存的固定 IP；DHCP、重連佇列、驗證／加密與多 client 不包含在 MVP。
