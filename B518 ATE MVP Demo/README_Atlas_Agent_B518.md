# Atlas Agent B518 ATE MVP

`atlas_agent.py` 是設計給受隱私權鎖定的 Mac mini 的本機 Agent。程式不使用
Accessibility、AppleScript、CGEvent 或任何 Mac 端鍵盤／滑鼠控制；所有 UI 操作都
是透過 USB CDC 對 Arduino 下達指令，再由 Arduino 的 USB HID 實作。

## 執行

```bash
python3 -m pip install -r requirements.txt
python3 atlas_agent.py
python3 -m unittest -v test_atlas_agent.py
```

## 打包 macOS App

在具備網路與 Python 套件安裝權限的建置電腦上執行：

```bash
chmod +x build_macos_app.sh
./build_macos_app.sh
```

輸出為 `dist/Atlas Agent B518 ATE.app`。目標 Mac mini 僅執行產出的 App；Agent
本身不要求 Automation 或 Accessibility 權限。

這是 ad-hoc／未公證的 MVP；正式交付到另一台 Mac 前，請由有 Apple Developer
憑證的建置流程完成簽署與 notarization。不要為此開啟 Automation 或 Accessibility
權限。

選取 Arduino USB CDC 埠和 CSV 根路徑後，Arduino 會透明轉送上位機 TCP 的
`SN1,SN2,...\r\n`；每一批條碼**建議以 CRLF 結尾**，可直接搭配 LabVIEW 的 CRLF
偵測模式，也能避免 TCP 串流分段時誤讀。Agent 仍相容 LF-only，並相容可選的
`DATA:SN1,SN2,...\r\n`／`SN:SN1,SN2,...\r\n` 訊框；收到完整一行後立刻
顯示 1–4 個 SN 並依工站啟動流程。FCT 直接開始監聽；DFU／BT 則請 Arduino 截圖，
再依影像匹配結果輸入條碼或點擊按鈕。

資料夾結構應為：

```
CSV 根路徑/<SN>/YYYYMMDD_HH-MM-SS.<任意雜湊>/system/device.log
CSV 根路徑/<SN>/YYYYMMDD_HH-MM-SS.<任意雜湊>/system/records.csv
```

Agent 每 0.25 秒檢查每個當前 SN，只使用和 Mac 系統時間最接近的有效時間戳資料
夾，避免誤取舊的重工結果。`records.csv` 的 `status` 欄任一 `FAIL` 即上報 FAIL，
全部 PASS 才上報 PASS；新增的 `device.log` 會即時顯示在畫面中。所有當前 SN 都完成後，
Agent 才經 USB CDC 送出一行批次結果，例如
`RESULT:SN001,PASS;SN002,PASS;SN003,PASS;SN004,FAIL`，由 Arduino 回送給 TCP 上位機。

### TCP／LabVIEW 交握訊框

所有上位機與 Agent 的業務訊息使用 UTF-8、以 CRLF (`\r\n`) 結尾。有效批次被接收後
不會先回覆 ACK；DFU／BT 必須完成影像操作，並在所有 SN 的 CSV 結果都完成後，才回覆一行
`RESULT:<SN1>,<PASS|FAIL>;<SN2>,<PASS|FAIL>...\r\n`。LabVIEW 可用 TCP Read 的 CRLF
模式逐行讀取。若批次無效或 DFU／BT 影像啟動失敗，則回覆相對應的 `NACK` 錯誤訊息。

偏好資料存於 `~/Library/Application Support/AtlasAgentB518/preferences.json`，包含
串口、CSV／Log 路徑與工站。

## DFU／BT OpenCV 定位協定

本 MVP 透過 `SCREENSHOT`、`M_RESET`、`M_MOVE:x,y`、`M_CLICK:L`、`K_WRITE:<文字>`
與 `K_KEY:TAB` CDC 指令由 Arduino HID 執行動作。`template_center()` 以 OpenCV 執行模板匹配；整合時請
把測試程式視窗、條碼框與開始按鈕的 PNG 模板放入介面所選的模板資料夾（預設為
專案 `templates/`）；精確裁切規則見該資料夾的說明。截圖必須由 Arduino 取得並存到
桌面，檔名包含 `ScreenShot`。`opencv-python` 已列入 `requirements.txt`。DFU_2 對每個 SN
都會依序執行「`M_RESET` 回左上角 → 移到 SN 框 → 點擊 → 輸入 SN → `M_RESET` 回左上角 →
移到 OK → 點擊」；Agent 會逐一等待 Arduino 回覆每個 HID 指令成功，確認最後一筆 OK
點擊完成後才開始監聽 CSV。

「螢幕截圖路徑」預設為 `~/Desktop`，也可選擇例如 `~/Desktop/ScreenShot`。DFU／BT
送出 `SCREENSHOT` 後會先等待 5 秒，最長等待共 15 秒，再在該資料夾尋找新產生的
圖片。檔名支援 `ScreenShot`、`Screen Shot`、`Screenshot` 與中文版 macOS 的「截圖」；
此設定也會隨其他偏好一起保存。

程式內「OpenCV 模板路徑」旁的「製作模板」可直接從截圖資料夾選取圖片（或使用最新
截圖），以滑鼠框選範圍並儲存為 PNG。通用流程可命名為 `test_window.png`、
`barcode_field.png`、`start_button.png`；B482 流程可使用 `b482/dfu2_window.png`、
`b482/dfu2_sn_input.png`、`b482/dfu2_ok.png` 或 `b482/bt_start_all.png`。
「製作模板」的檔名下拉選單會依目前工站與畫面設定預先列出正確名稱；DFU_2 請依序
選擇並儲存三個 `b482/dfu2_*.png` 檔案。
模板視窗請使用內建的「縮小預覽／放大預覽」按鈕；預覽尺寸受到上限保護，且不使用
macOS 視窗的綠色放大按鈕。來源截圖上限為 2400 萬像素，以避免 Tk／AppKit 建立過大的
影像表面而造成記憶體問題。

「OpenCV 模板路徑」可指定任意**根資料夾**。若 DFU 畫面設定為 `b482_dfu2`，根資料夾
內必須有 `b482/dfu2_window.png`、`b482/dfu2_sn_input.png` 與 `b482/dfu2_ok.png`；若
選 `generic`，則使用根目錄下的 `test_window.png`、`barcode_field.png`、`start_button.png`。
相容既有作法：根目錄直接有 `dfu2_window.png` 等同名檔案時，Agent 也會自動使用；但
任意名稱（例如 `123.png`）無法判斷模板用途，仍須改成下拉選單列出的名稱。
雙螢幕 Mac 在 `SCREENSHOT` 後可能新增多張檔案，Agent 會逐張尋找視窗模板；請將 HTML
測試人機完整放在單一螢幕，不要跨越兩個顯示器。
自訂 B482 模板會在匹配到測試視窗的那張完整截圖上搜尋控制項，因此可支援 Retina 與 HTML
人機的不同解析度；專案內建 B482 模板才使用原始 1011×600 參考區域。

### 驗證期 HID 延遲與座標校正

主畫面的「驗證 HID」可設定每步延遲，預設 `0.5` 秒；Agent 會收到 Arduino 的成功回覆後
才等待並送下一個動作，方便觀察「歸零、移動、點擊、輸入」各步驟。每次定位完成也會
儲存匹配疊圖，按「查看匹配疊圖」可檢視綠框模板範圍、紅十字截圖座標，以及實際送給
Arduino 的 HID 座標。

若疊圖位置正確、游標卻偏移，通常是 Retina 截圖像素與 HID 螢幕座標的比例不同。先將
X／Y 比例改為 `0.5` 再測試；外接或雙螢幕的測試人機若不是主螢幕，可用 X／Y 偏移補上
該螢幕在 Mac 桌面座標中的起點。預設比例 `1.0`、偏移 `0`。

### B482 客戶 Demo 設定

本次提供的 B482 畫面已配置在 `templates/b482/`。選 DFU 時，請選 `b482_dfu2`：
Agent 會依序填入左下 SN 欄、點擊 `OK`，讓測試程式把 SN 搬入各 Slot。FCT 將在治具
推入後直接監聽；BT 則定位並點擊底部 `Start All`。PASS／FAIL／NOTSET／TESTING
狀態格不作為影像模板，因此顏色差異不會影響定位。

### 無硬體本機 Demo：HTML B482 HMI

在一個終端機啟動模擬器（CSV 根路徑須和 Agent 選擇的相同）：

```bash
python3 b482_demo_server.py --csv-root "$HOME/Desktop/AtlasDemoCSV"
```

再開啟 `http://127.0.0.1:8080`。DFU_2 可逐筆輸入 SN 並按 `OK`，BT 可按 `Start All`，
FCT 可按「Simulate Fixture Insert」。模擬器會先寫入 `device.log` 的 TESTING，再於兩秒
後寫入每個 SN 的 `records.csv`。使用 Agent 時，CSV 根路徑設成同一個 `AtlasDemoCSV`。
這是客戶展示用 HMI，不需要也不會使用 macOS Automation／Accessibility 權限。

也可直接在 Agent 手動輸入 1–4 個 SN 後按「本機模擬」。此模式會先要求確認，接著在目前
選擇的 CSV 根路徑建立 Atlas 格式的 `device.log` 與 `records.csv`，不使用 Arduino、截圖或
OpenCV。請選擇專用的 Demo 資料夾，不要指向正式量產資料夾；可勾選「本機模擬最後一台 FAIL」
驗證批次 `RESULT`。

## Arduino TCP bridge

交付資料夾內的 `B518_Arduino_MVP_Test` 是建議燒錄的整合韌體：它同時提供
Ethernet TCP bridge、USB CDC、Keyboard 與 Mouse HID。上位機→Mac 可直接使用
`SN1,SN2,...\r\n`（也相容 `DATA:` 訊框；**建議 CRLF 結尾**），Mac→上位機使用批次
`RESULT:<SN>,<PASS|FAIL>;...\r\n`；網路按鈕對 Arduino 使用 `GET_IP`／`NET_SET:x.x.x.x`。
