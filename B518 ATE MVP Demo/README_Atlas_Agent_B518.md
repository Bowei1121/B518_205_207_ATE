# Atlas Agent B518 ATE MVP

`atlas_agent.py` 是設計給受隱私權鎖定的 Mac mini 的本機 Agent。程式不使用
Accessibility、AppleScript、CGEvent 或任何 Mac 端鍵盤／滑鼠控制；所有 UI 操作都
是透過 USB CDC 對 Arduino 下達指令，再由 Arduino 的 USB HID 實作。

## 執行

```bash
/usr/local/opt/python@3.12/bin/python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt pyinstaller
.venv/bin/python atlas_agent.py
.venv/bin/python -m unittest -v test_atlas_agent.py test_upper_computer_simulator.py
```

開發與建置環境固定使用 Python 3.12 的 `.venv`，不要使用系統或 Anaconda 的 `python3`。

## 打包 macOS App

在具備網路與 Python 套件安裝權限的建置電腦上執行：

每次執行建置腳本會自動遞增共用版本號的 patch 段，例如 `V0.1.0` 變為 `V0.1.1`；
Mac App 視窗標題與 `Info.plist`、Windows 上位機模擬器標題均使用此版本號。

```bash
chmod +x build_macos_app.sh
./build_macos_app.sh
```

輸出為 `dist/Atlas Agent B518 ATE.app`。目標 Mac mini 僅執行產出的 App；Agent
本身不要求 Automation 或 Accessibility 權限。

### macOS Catalina 10.15 Intel 專用打包

若交付機是 macOS Catalina 10.15 Intel，**不可**使用較新的 macOS 直接建置，否則
PyInstaller 會將需要較新 macOS 的 Python 原生模組包進 App，造成 Catalina 上雙擊無法開啟。
請在 Catalina 10.15 的 Intel VM 完成以下操作；交付機不需要安裝 Python。

```bash
cd "/你的專案/B518 ATE MVP Demo"
xcode-select -p
chmod +x build_macos_catalina_app.sh verify_catalina_bundle.sh
./build_macos_catalina_app.sh
```

`xcode-select -p` 應顯示 `/Library/Developer/CommandLineTools`。腳本會建立
`.venv-catalina`、使用 Catalina 相容的固定套件版本、遞增版本號，並輸出
`dist-catalina/Atlas Agent B518 ATE.app`。最後會掃描 App 內所有 Mach-O 原生檔案；若任何
檔案要求高於 macOS 10.15，建置會失敗而不應交付。

這是 ad-hoc／未公證的 MVP；正式交付到另一台 Mac 前，請由有 Apple Developer
憑證的建置流程完成簽署與 notarization。不要為此開啟 Automation 或 Accessibility
權限。

選取 Arduino USB CDC 埠和 CSV 根路徑後，Arduino 會透明轉送上位機 TCP 的 JOB 指令：

```
DFU:JOB=20260722-001;1=SN001,3=SN003,4=SN004\r\n
FCT:JOB=20260722-002;1=SN101,2=SN102\r\n
BT:JOB=20260722-003;1=SN201,3=SN203,4=SN204\r\n
```

slot 1～4 可不連續，空料位置直接省略。每一行以 CRLF 結尾，可直接搭配 LabVIEW 的
CRLF 偵測模式，也能避免 TCP 串流分段時誤讀。Agent 收到有效 JOB 後先驗證工站、JOB ID、
slot 與 SN；若本機已有未完成 JOB，回覆 `NACK:<工站>:JOB=<id>;BUSY`，不會中斷舊測試。
FCT 直接開始監聽；DFU 請 Arduino 截圖後依 slot 順序輸入條碼；BT 四個 slot 全滿時按
Start All，未滿時逐一點擊指定的 Start 1～4，並只監控指定 slot。

DFU generic 的多輸入框流程會依 slot 差距送出 Tab，略過空料位置。DFU_2 是「單一 SN
輸入框＋OK 後搬到下一個已勾選 slot」的設備流程；使用不連續 slot JOB 前，測試 HMI 的
checkbox 必須與 JOB 指定的 slot 一致，Agent 會依勾選順序輸入 SN 並在 Log 顯示提示。

資料夾結構應為：

```
CSV 根路徑/<SN>/YYYYMMDD_HH-MM-SS.<任意雜湊>/system/device.log
CSV 根路徑/<SN>/YYYYMMDD_HH-MM-SS.<任意雜湊>/system/records.csv
```

Agent 每 0.25 秒檢查每個當前 SN，只使用和 Mac 系統時間最接近的有效時間戳資料
夾，避免誤取舊的重工結果。`records.csv` 的 `status` 欄任一 `FAIL` 即上報 FAIL，
全部 PASS 才上報 PASS；新增的 `device.log` 會即時顯示在畫面中。所有當前 SN 都完成後，
Agent 才經 USB CDC 送出一行批次結果，例如
`RESULT:DFU:JOB=20260722-001;1=SN001,PASS;3=SN003,PASS;4=SN004,FAIL`，
由 Arduino 回送給 TCP 上位機。

監聽啟動時會記錄按下「開始流程」的時間，只接受該時間之後建立的時間戳資料夾與
`records.csv`，不會讀取上一批或重工留下的檔案。主畫面的「測試結果逾時(s)」預設 300 秒；
設為 `0` 可停用。逾時時尚未完成的 SN 會以 `TIMEOUT` 納入最終 `RESULT`。DFU／BT
成功完成模板分析並保存匹配疊圖後，會自動刪除本次 Arduino 產生的原始螢幕截圖；若匹配
失敗，截圖會保留供製作模板與除錯使用。

### TCP／LabVIEW 交握訊框

所有上位機與 Agent 的業務訊息使用 UTF-8、以 CRLF (`\r\n`) 結尾。有效 JOB 被接收後
立即回覆 `ACK:<工站>:JOB=<id>\r\n`；ACK 代表 Agent 已接單，不代表測試完成。DFU/FCT
等待 CSV 結果；BT 等待所有指定 slot 走過 TESTING 並完成 PASS／FAIL，才回覆：

```
RESULT:<工站>:JOB=<id>;<slot>=<SN>,<PASS|FAIL|TIMEOUT>;...\r\n
```

LabVIEW 可用 TCP Read 的 CRLF 模式逐行讀取。工站不符、設備忙碌、指令無效或影像啟動
失敗會回覆帶 JOB ID 的 `NACK`。舊的純 `SN1,SN2,...` 格式只保留給 HMI 手動驗證；正式
上位機流程應一律使用包含工站、JOB ID 與 slot 的新格式。

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
`b482/dfu2_sn_input.png`、`b482/dfu2_ok.png` 或 BT 的 `b482/bt_*.png`。
「製作模板」的檔名下拉選單會依目前工站與畫面設定預先列出正確名稱；DFU_2 請依序
選擇並儲存三個 `b482/dfu2_*.png` 檔案。
製作模板視窗的「擷取螢幕截圖」會透過已連線的 Arduino 發送 `SCREENSHOT`，等待 macOS
儲存後自動載入本次最新截圖；雙螢幕時會載入最新一張，其他新截圖仍保留可用「選擇截圖」
切換。此功能不會自動刪除模板製作用截圖。
模板視窗請使用內建的「縮小預覽／放大預覽」按鈕；預覽尺寸受到上限保護，且不使用
macOS 視窗的綠色放大按鈕。來源截圖上限為 2400 萬像素，以避免 Tk／AppKit 建立過大的
影像表面而造成記憶體問題。

「OpenCV 模板路徑」可指定任意**根資料夾**。若 DFU 畫面設定為 `b482_dfu2`，根資料夾
內必須有 `b482/dfu2_window.png`、`b482/dfu2_sn_input.png` 與 `b482/dfu2_ok.png`；若
選 `generic`，則使用根目錄下的 `test_window.png`、`barcode_field.png`、`start_button.png`。
相容既有作法：根目錄直接有 `dfu2_window.png` 等同名檔案時，Agent 也會自動使用；但
任意名稱（例如 `123.png`）無法判斷模板用途，仍須改成下拉選單列出的名稱。

### BT 畫面 STATUS 判定

BT 不使用 Atlas CSV。請在 BT 初始畫面選「製作模板」，分別框選**一個完整 STATUS 格**
（包含背景與文字），並依下列名稱儲存：

```
b482/bt_window.png
b482/bt_start_all.png
b482/bt_start_1.png ... b482/bt_start_4.png
b482/bt_status_pass.png
b482/bt_status_fail.png
b482/bt_status_testing.png
b482/bt_status_notset.png
```

輸入 1–4 個 SN（多筆時依 slot 1～4 排列）後，按「開始流程」會點 `Start All`；按「BT Start 1`～
`BT Start 4` 則只啟動、回報對應 slot 的 SN；個別測試也可只輸入一個 SN。啟動後每次由 Arduino 產生新截圖，Agent 讀取
四列 STATUS，截圖分析完即刪除；下一次擷取至少間隔 1 秒。macOS 截圖本身可能延後數秒才
真正落檔，因此無須、也不能用需要 Screen Recording 權限的方式強制固定每秒取得新影像。
BT 在 Start 前會先點擊匹配到的 BT 標題取得測試畫面焦點；結果監聽會先確認指定 slot 至少
出現一次 `TESTING`，並等待**所有指定 slot 的 TESTING 都結束**後，才一起接受 PASS／FAIL，
避免前一批殘留結果或尚未完成的單一 slot 被誤回傳。
在所有指定 slot 都首次出現 `TESTING` 後，Agent 以 macOS Vision OCR 讀取同張截圖的設備 SN，
並逐 slot 與上位機 SN 比對。若不符、缺值或 OCR 無法讀取，測試仍會完成，但 RESULT 前必須由
操作員在覆核視窗確認或修正設備實際 SN；確認後只回傳設備 SN，取消則回傳
`NACK:BT_SN_MISMATCH`。Vision OCR 只分析 Arduino 已存下的截圖，不需要 Screen Recording、
Accessibility 或軟體鍵鼠控制權限。
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

「自動比例」預設開啟：Agent 在找到實際匹配的截圖後，會讀取 macOS 每個顯示器的邏輯
尺寸與 Retina backing scale，以截圖像素尺寸比對對應顯示器並自動填入 X/Y 比例。例如
2880×1800 截圖對應 1440×900 Retina 顯示器時，自動填入 `0.5`。若多個顯示器解析度相同
或截圖無法對應任何顯示器，會保留手動值並在通訊紀錄提示；雙螢幕的 X/Y 偏移仍須依螢幕
排列設定。若 macOS 顯示器 API 無法列出與截圖相符的螢幕，Agent 會再讀取 PNG 截圖內的
72/144 DPI Retina 資訊作為比例 fallback。

當相對 `Mouse.move()` 受到 macOS 游標加速度影響而出現「step=1 五次不等於 step=5
一次」時，將 HID 模式改為 `absolute`。此模式會將「比例與偏移」換算後的邏輯桌面座標，
映射為 Arduino 第二個絕對 HID 指標的 `0–32767` 範圍；設定「虛擬桌面寬 × 高」為 macOS
顯示器排列後的邏輯總尺寸。單一 2880×1800 Retina 截圖通常填 `1440×900`，比例先填
`0.5`。雙螢幕請使用 X/Y 偏移指定目標螢幕在虛擬桌面中的起點。absolute 模式需要重新
燒錄 Arduino 韌體，並以實機確認 macOS 將該絕對 HID 裝置對應到正確桌面。
匹配疊圖在 absolute 模式會分別顯示 `px`（影像像素）、`logical`（螢幕邏輯座標）與
`target`（0–32767 絕對 HID report）；最後一項不是螢幕像素，數值較大屬正常現象。
DFU 在第一個 SN 前會先點擊匹配到的測試視窗標題安全區取得前景焦點；absolute 模式以
絕對 HID 負責定位，但使用標準相對 Mouse report 的按鍵狀態執行點擊，確保 macOS 的
輸入框與按鈕收到 click 事件。

### Arduino HID 距離校正工具

`hid_calibration.py` 是不依賴測試流程的獨立校正 UI。執行 `python3 hid_calibration.py`
（或 `bash build_hid_calibration_app.sh` 後開啟 `dist/Atlas HID Calibration B518.app`），選擇
Arduino USB CDC 串口並連線。先按 **Home** 將游標移到左上角；設定 Step 後按鍵盤方向鍵
或畫面方向按鈕，Arduino 會以 `M_DELTA:X,Y` 相對移動指定距離。
工具會顯示從 Home 累積的「目前 Arduino 控制座標」：Home 為 `(0,0)`，右／下遞增，
左／上遞減，可直接與 OpenCV 疊圖顯示的匹配座標比較。

例：OpenCV 疊圖顯示按鈕中心為 `(1000,1000)`，校正工具從 Home 以累計 `(500,500)`
才到達同一位置，則將 Agent 的 X／Y 比例設定為 `0.5`。使用前必須重新燒錄
`B518_Arduino_MVP_Test.ino`，使 Arduino 支援 `M_DELTA` 指令。

### B482 客戶 Demo 設定

本次提供的 B482 畫面已配置在 `templates/b482/`。選 DFU 時，請選 `b482_dfu2`：
Agent 會依序填入左下 SN 欄、點擊 `OK`，讓測試程式把 SN 搬入各 Slot。FCT 將在治具
推入後直接監聽；BT 可定位並點擊 `Start All` 或 `Start 1`～`Start 4`，後續以 STATUS
格的 PASS／FAIL 模板判讀結果。

### 無硬體本機 Demo：HTML B482 HMI

在一個終端機啟動模擬器（CSV 根路徑須和 Agent 選擇的相同）：

```bash
python3 b482_demo_server.py --csv-root "$HOME/Desktop/AtlasDemoCSV"
```

再開啟 `http://127.0.0.1:8080`。DFU_2 可逐筆輸入 SN 並按 `OK`，BT 可按 `Start All`，
FCT 可按「Simulate Fixture Insert」。模擬器會先寫入 `device.log` 的 TESTING，再於 30 秒
後寫入每個 SN 的 `records.csv`。使用 Agent 時，CSV 根路徑設成同一個 `AtlasDemoCSV`。
這是客戶展示用 HMI，不需要也不會使用 macOS Automation／Accessibility 權限。

也可直接在 Agent 手動輸入 1–4 個 SN 後按「本機模擬」。此模式會先要求確認，接著在目前
選擇的 CSV 根路徑建立 Atlas 格式的 `device.log` 與 `records.csv`，不使用 Arduino、截圖或
OpenCV。請選擇專用的 Demo 資料夾，不要指向正式量產資料夾；可勾選「本機模擬最後一台 FAIL」
驗證批次 `RESULT`。

## Arduino TCP bridge

交付資料夾內的 `B518_Arduino_MVP_Test` 是建議燒錄的整合韌體：它同時提供
Ethernet TCP bridge、USB CDC、Keyboard 與 Mouse HID。上位機→Mac 可直接使用
`STATION:JOB=<id>;<slot>=<SN>,...\r\n`，Mac→上位機依序使用
`ACK:<STATION>:JOB=<id>\r\n` 與 `RESULT:<STATION>:JOB=<id>;<slot>=<SN>,<status>;...\r\n`；
網路設定對 Arduino 使用 `GET_IP`／`NET_SET:x.x.x.x`。
