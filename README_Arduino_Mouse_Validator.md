# Arduino 滑鼠功能 MVP 驗證器

這個 Python 工具會以 `115200 baud` 直接連接 Arduino，依序完成：

1. 傳送大寫 `S`，確認收到 `ACK: Mouse movement started.`。
2. 觀察 2 秒，確認系統滑鼠座標持續發生微幅變化，且變化週期中位數接近 200 ms（允收 80–320 ms）。
3. 傳送大寫 `P`，確認收到 `ACK: Mouse movement stopped.`。
4. 再觀察 1 秒，確認滑鼠座標不再變化。

> Arduino IDE 的 Serial Monitor 必須先關閉。同一個序列埠無法同時由 Serial Monitor 與 Python 開啟。

## 執行

```bash
python3 -m pip install -r requirements.txt
python3 arduino_mouse_validator.py --list-ports
python3 arduino_mouse_validator.py --port /dev/cu.usbmodem1101
```

## 圖形介面（GUI）

若要以視窗操作，執行：

```bash
python3 arduino_mouse_validator.py --gui
```

視窗會列出可用的 USB CDC 序列埠，固定以 `115200` baud 開啟。選取 Arduino 後可使用：

- **開始完整驗證**：依序送出 `S`、確認 ACK 與滑鼠移動、送出 `P`、確認 ACK 與停止。
- **手動送出 S**：只傳送開始命令，適合確認 Arduino 韌體反應。
- **送出 P／中止驗證**：手動傳送停止命令；在完整驗證途中也可作為緊急停止。

所有 USB CDC 收發與驗證結果會顯示在「執行紀錄」。完整驗證取樣期間請勿碰觸滑鼠，並讓游標保留在螢幕中央附近。

## 打包為 macOS `.app`

圖形介面版必須以 `arduino_mouse_validator_gui.py` 作為打包入口；若直接打包主程式，預設會執行命令列模式，而 `--windowed` 會把命令列輸出隱藏。

```bash
python3 -m pip install --user pyinstaller
pyinstaller --noconfirm --clean \
  --name ArduinoMouseValidator \
  --windowed \
  --collect-all serial \
  arduino_mouse_validator_gui.py
```

完成後開啟 `dist/ArduinoMouseValidator.app`。每次修改 Python 程式後都要重新執行上述打包指令。

如果電腦只接一個序列裝置，通常可直接讓程式自動選擇：

```bash
python3 arduino_mouse_validator.py
```

測試期間請勿碰觸滑鼠，並確保游標不在螢幕邊角，以免 Arduino 的微幅位移被邊界擋住。成功時程式結束碼為 `0` 並顯示 `PASS`；任一 ACK 不符、啟動後未移動或停止後仍移動，會以結束碼 `1` 顯示 `FAIL`。

## 空白鍵互動模式

如果要改成用鍵盤控制 Arduino，不做自動座標驗證：

```bash
python3 arduino_mouse_validator.py --port /dev/cu.usbmodem1101 --interactive
```

操作方式：

1. 第一次按空白鍵：送出 `S`，等待 `ACK: Mouse movement started.`。
2. 下一次按空白鍵：送出 `P`，等待 `ACK: Mouse movement stopped.`。
3. 後續每按一次空白鍵，就在 `S` / `P` 間切換。
4. 按 `q` 或 `Esc` 離開；如果離開時狀態仍是 started，程式會嘗試補送 `P`。

互動模式需要在終端機執行，按空白鍵不需要再按 Enter。

如果按空白鍵後有看到 `偵測到空白鍵，TX: S` 或 `偵測到空白鍵，TX: P`，代表 Python 已經送出序列命令；若接著等不到 ACK，問題通常在序列埠、板子程式狀態或韌體回覆邏輯。

你目前的 Arduino 程式只有在狀態真的改變時才回 ACK：

- 已經在 moving 時再送 `S`：不會回 `ACK: Mouse movement started.`
- 已經 stopped 時再送 `P`：不會回 `ACK: Mouse movement stopped.`

MVP 驗證建議把 `S` / `P` 做成冪等命令，也就是收到命令就設定狀態並一律回 ACK。可把 `checkSerialCommand()` 裡的 `S/P` 分支改成：

```cpp
if (incomingChar == CMD_START) {
  isMoving = true;
  lastMoveTime = millis();
  Serial.println("ACK: Mouse movement started.");
}
else if (incomingChar == CMD_STOP) {
  isMoving = false;
  Serial.println("ACK: Mouse movement stopped.");
}
```

這樣 Python 和 Arduino 即使狀態不同步，下一次空白鍵也能拿到明確 ACK。

若韌體期待「無行尾」而不是 Arduino Serial Monitor 的 Newline 設定，可加上：

```bash
python3 arduino_mouse_validator.py --line-ending none
```

## 無硬體自我測試

```bash
python3 -m unittest -v test_arduino_mouse_validator.py
```
