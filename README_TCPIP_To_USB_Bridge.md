# Arduino TCP/IP to USB Serial MVP

這組範例用來驗證：

1. 上位機透過 TCP/IP 將文字資料送到 Arduino。
2. Arduino 收到 TCP 資料後，透過 USB Serial 轉送到電腦。
3. Python 接收端從 USB Serial 讀取資料。

目前 Arduino 範例使用 `Ethernet.h`，適用於 Arduino + W5500 / Ethernet Shield 類型硬體。

## 資料格式

TCP client 每送出一行文字，例如：

```text
hello mvp
```

Arduino 會從 USB Serial 輸出：

```text
DATA:hello mvp
```

Arduino 狀態訊息會用：

```text
EVT: ...
```

錯誤訊息會用：

```text
ERR: ...
```

Python 接收端只會把 `DATA:` 當成正式資料。

## Arduino 設定

打開：

```text
Arduino_tcp_to_usb_bridge/Arduino_tcp_to_usb_bridge.ino
```

依照你的網段修改：

```cpp
IPAddress ip(192, 168, 1, 80);
IPAddress gateway(192, 168, 1, 1);
IPAddress subnet(255, 255, 255, 0);
const uint16_t TCP_PORT = 5000;
const uint8_t ETHERNET_CS_PIN = 10;
```

燒錄後，關閉 Arduino IDE Serial Monitor，避免佔用 USB Serial。

## Python 接收端

安裝相依套件：

```bash
python3 -m pip install -r requirements.txt
```

列出 Arduino USB Serial port：

```bash
python3 tcpip_to_usb_receiver.py --list-ports
```

開始接收：

```bash
python3 tcpip_to_usb_receiver.py --port /dev/cu.usbmodem1101 --raw
```

只收 1 筆 DATA 後結束：

```bash
python3 tcpip_to_usb_receiver.py --port /dev/cu.usbmodem1101 --count 1 --timeout 10 --raw
```

把收到的 DATA payload 存檔：

```bash
python3 tcpip_to_usb_receiver.py --port /dev/cu.usbmodem1101 --output-file received_data.txt
```

## TCP 發送端測試

在另一個終端機或另一台上位機執行：

```bash
python3 tcpip_to_usb_sender.py 192.168.1.80 hello mvp
```

預期 sender 端看到：

```text
READY Arduino TCP-to-USB bridge
ACK hello mvp
```

預期 receiver 端看到：

```text
EVENT: TCP client connected
DATA: hello mvp
```

## Timeout 排查流程

如果 sender 顯示 TCP 連線逾時，先不要測 payload，改測 TCP port 是否能連上：

```bash
python3 tcpip_to_usb_sender.py 192.168.1.80 --connect-only --timeout 5
```

結果判讀：

- 看到 `CONNECTED`：網路層已通，再回去測 `hello mvp`。
- 看到 `TCP 連線逾時`：上位機無法連到 Arduino IP/port，通常是 IP、網段、網路線、W5500 初始化或 CS pin 問題。
- 看到 `TCP 連線被拒絕`：IP 可到，但 Arduino 沒有在 `5000` listen，檢查 Arduino 程式是否已燒錄並執行到 `server.begin()`。

建議先在接收 USB Serial 的電腦執行：

```bash
python3 tcpip_to_usb_receiver.py --port /dev/cu.usbmodem1101 --raw
```

Arduino 開機後應該看到類似：

```text
EVENT: Ethernet local IP=192.168.1.80
EVENT: Ethernet hardware=W5500
EVENT: Ethernet link=ON
EVENT: TCP server ready at 192.168.1.80:5000
```

如果看到：

```text
ERROR: Ethernet shield was not found
```

代表 W5500 沒被 SPI 偵測到，優先檢查板子型號、接線、`ETHERNET_CS_PIN`。

如果看到：

```text
ERROR: Ethernet link=OFF
```

代表網路線或交換器/電腦網卡沒有 link，優先檢查線材、交換器、網卡燈號。

## 常見卡點

- Python receiver 沒資料：確認 Arduino IDE Serial Monitor 已關閉。
- TCP sender 連不上：確認 Arduino IP、電腦網段、網路線、W5500 CS pin。
- sender 有 `ACK` 但 receiver 沒 `DATA`：通常是 receiver 開錯 USB Serial port。
- receiver 只看到 `EVT:`：代表 USB Serial 通了，但還沒有 TCP payload 進來。
- 文字太長：目前單行上限 `128` bytes，可調整 Arduino 的 `MAX_LINE_LENGTH`。
