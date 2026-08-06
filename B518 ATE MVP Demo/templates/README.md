# OpenCV 模板

請以 Arduino 產生的同一螢幕解析度、顯示器縮放比例與測試程式主題，裁切並放入下列 PNG：

- `test_window.png`：測試程式的固定、具辨識度的視窗區塊。
- `barcode_field.png`：DFU 的第一個條碼輸入框。
- `start_button.png`：開始測試按鈕。

DFU 會先全螢幕匹配 `test_window.png`，後續條碼框與開始按鈕的匹配會嚴格限制在該視窗矩形內；BT 則只會在該視窗內匹配開始按鈕。預設相似度門檻為 0.80。

不可使用包含真實 SN、客戶資料或個資的截圖作為模板。

## B482 客戶 Demo

`b482/` 已根據提供的 B482 畫面建立模板。這些模板只使用固定的視窗標題、DFU SN
輸入框／`OK`，以及 BT 的 `Start All`；刻意不包含會變動的 PASS、FAIL、NOTSET
或 TESTING 顏色。FCT 沒有 UI 點擊，直接監聽 CSV。

### DFU 四槽與七槽

- `b482_dfu2`：舊四槽流程；每一筆是「點 SN 欄 → 輸入 → 點 OK」。
- `b482_dfu2_7slot`：現場七槽流程；每筆是「點 SN 欄 → 輸入 → Enter」，所有已選 slot
  都填完後才點一次 `OK` 開始 ATE。

七槽 Profile 需要以下額外模板，均請從 Arduino 的**乾淨截圖**裁切，不能直接使用拍攝螢幕
照片：

- `b482/dfu7_window.png`、`b482/dfu7_sn_input.png`、`b482/dfu7_ok.png`
- `b482/dfu7_slot_label.png`：下方卡片的共用 `slot` 文字，勿包含 slot 數字或 checkbox。
- `b482/dfu7_group0_label.png`：下方 group0 文字，勿包含上方表格中的 group0。
- `b482/slot_checkbox_checked.png`、`b482/slot_checkbox_unchecked.png`：同一解析度下、盡量框選
  相同主體範圍的 checkbox；可保留少量邊界，不要包含 slot 名稱或其他控制項。

Agent 以 group0 文字左側定位全選控制，並在每個 slot 文字右側的小範圍辨識 checkbox，再依第一排四個、第二排
三個映射 slot1～7。因此只需要一組 checked／unchecked 模板，不需要為七個 slot 分別製作模板。
slot checkbox 的搜尋範圍會依同一排相鄰 slot 文字間距延伸到卡片右端，不會只以文字寬度估算。
啟用自動同步時，Agent 會先用 group0 將全部 slot 重設為未勾選，再建立本次所需狀態並截圖驗證。group0
僅作為操作全選／取消全選的控制，其顏色或勾選外觀不是判定依據；重設與最終複驗都以 slot1～7 的實際狀態為準。
七槽 checkbox 會先自動裁出主體，再以灰階邊緣比較方框與勾形，降低視窗焦點造成的灰底黑勾／
藍底或綠底白勾色彩差異；兩種狀態分數不足或過於接近時會停止流程並把完整分數寫入 Log。

`b482_dfu1_manual` 不會自動操作，因其畫面未顯示與 DFU_2 相同的 SN 輸入流程；確認
其實際輸入規則後再加入專用設定。
