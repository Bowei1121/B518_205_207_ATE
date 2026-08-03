# 已停用的韌體入口

這個資料夾保留只是為了阻止人員再次誤開舊的同名 Sketch。
`B518_Arduino_MVP_Test.ino` 會刻意編譯失敗，並指示正確路徑。

唯一可編譯、燒錄與交付的正式韌體為：

```text
B518 ATE MVP Demo/B518_Arduino_MVP_Test/B518_Arduino_MVP_Test.ino
```

燒錄後必須透過 USB CDC 發送 `GET_INFO` 驗證 `PRODUCT`、`FW`、`PROTO`
與 `BOARD`；未取得 `INFO:PRODUCT=B518_ARDUINO_MVP;...` 不得開始 HID 測試。
