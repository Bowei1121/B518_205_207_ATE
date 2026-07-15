# OpenCV 模板

請以 Arduino 產生的同一螢幕解析度、顯示器縮放比例與測試程式主題，裁切並放入下列 PNG：

- `test_window.png`：測試程式的固定、具辨識度的視窗區塊。
- `barcode_field.png`：DFU 的第一個條碼輸入框。
- `start_button.png`：開始測試按鈕。

DFU 會先全螢幕匹配 `test_window.png`，後續條碼框與開始按鈕的匹配會嚴格限制在該視窗矩形內；BT 則只會在該視窗內匹配開始按鈕。預設相似度門檻為 0.80。

不可使用包含真實 SN、客戶資料或個資的截圖作為模板。

## B482 客戶 Demo

`b482/` 已根據提供的 B482 畫面建立模板。這些模板只使用固定的視窗標題、DFU_2
SN 輸入框／`OK`，以及 BT 的 `Start All`；刻意不包含會變動的 PASS、FAIL、NOTSET
或未來的 TESTING 顏色。請以 Agent 的 `b482_dfu2` 設定操作 DFU_2：每一個 SN 都是
「點 SN 欄 → 輸入 → 點 OK」，最多四次。FCT 沒有 UI 點擊，直接監聽 CSV。

`b482_dfu1_manual` 不會自動操作，因其畫面未顯示與 DFU_2 相同的 SN 輸入流程；確認
其實際輸入規則後再加入專用設定。
