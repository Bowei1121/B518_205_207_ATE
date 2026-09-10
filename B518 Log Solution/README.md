# B518 Log Solution

獨立的 macOS 本機 Log 監控程式，供 DFU、FCT、BT 顯示測試結果。它不含 Arduino、USB CDC、TCP、OpenCV、螢幕截圖、鍵盤／滑鼠或 KVM 控制；與 Atlas Agent 是不同的 App 與程序。

## 使用方式

```zsh
cd "B518 Log Solution"
python3 b518_log_solution.py
```

每輪必須由人員按下「開始監控」建立系統時間基準與啟動前快照。

若必要路徑尚未設定、已不存在或無法讀取，程式會拒絕開始並顯示原因；空白路徑不會被誤當成 App 的目前目錄。建立啟動前檔案快照期間，主畫面會先顯示「啟動中」，完成後才進入「監控中」。

設定頁的路徑、工站與逾時秒數會在按下「儲存」時一起保存到 `~/Library/Application Support/B518LogSolution/preferences.json`。每個工站保有自己的路徑與逾時設定；下次啟動會恢復上次選擇的工站與其對應的 Slot 數。按「取消」不會保存設定頁中的修改。

## 逾時監控

每個工站可分別設定「等待開始測試逾時」與「測試時間上限」，兩者皆以秒計且必須是正整數。預設值為 DFU `30 / 480`、FCT `30 / 480`、BT `30 / 240`（等待開始／測試上限）。

開始監控後，若整輪在等待開始期限內沒有任何 Slot 顯示測試活動或最終結果，所有有效 Slot 會顯示橘色 `TIMEOUT`，監控停止。個別 Slot 開始測試後，會從首次活動起算測試時間，包含 `COMPLETING` 等待最終結果；超時的 Slot 顯示 `TIMEOUT`，其他尚未完成的 Slot 顯示 `STOPPED`，已完成的 PASS／FAIL／NOTEST 保留。逾時後重新開始監控才能建立新的一輪。

## KVM 顯示與快捷鍵

主視窗是供 KVM 擷取的固定高對比看板：只顯示目前工站、KVM 狀態模板、Slot、狀態、產品 SN 與開始／停止按鈕。它採瘦長的 360 px 固定寬度，所有主畫面文字固定為 14 pt，啟動時會自動放在螢幕右上方；DFU、FCT、BT 分別顯示 7、6、4 個通道。設定、路徑、即時事件與 Session 紀錄都位於左上角的「設定」視窗。

看板頂端的 `KVM RESULT` 是供上位機影像辨識的固定七格色帶。色塊由左至右永遠代表 slot1～7，而且格內不顯示文字。色塊兩端有方向相反的黑白定位標記，可用來定位色帶、確認方向並依固定中心位置取色；因此上位機不需要 OCR。有效通道在每輪開始時為灰色，出現測試活動後為黃色，最終結果為綠色 PASS 或紅色 FAIL；本輪確定完成後仍未參與的有效通道才改為粉紅色 NOTEST，逾時則為橘色 TIMEOUT。設備不存在的通道固定為黑色：FCT 的 slot7，BT 的 slot5～7。

若要顯示正式公司圖標，將提供的原始 PNG 置於 `assets/foxlink_logo.png`。該檔存在時會自動載入；未提供時畫面保留藍色 `FOXlink` 文字識別，避免阻擋監控程式啟動。

App 會固定使用高對比淺色介面，不跟隨 macOS 深色模式改變文字、輸入框、分頁或按鈕色彩，確保開發機、Mojave 與 Catalina 的畫面一致並方便 KVM 建立模板。

看板上方固定顯示 `PASS`、`FAIL`、`TESTING`、`NOTEST` 四個色塊，其文字、字級與背景色和 Slot 實際狀態完全相同，讓 KVM 在第一次測試前即可製作全部狀態模板。這些色塊只供取樣，不是操作按鈕。

- `Command + Shift + M` 等同「開始監控」。在 macOS 上會註冊為全域快捷鍵，因此 Atlas／BT HMI 有鍵盤焦點時也可觸發；程式正在監控時不會重啟本輪。
- Log Solution 不會持續置頂。解析到 PASS、FAIL 或 NOTEST 的最終結果時，主看板會自動回到前景並取得焦點，方便 KVM 立即讀取結果；之後仍可正常切換回測試程式。
- 快捷鍵只向 macOS 註冊這一組按鍵，並不監聽其他鍵盤輸入，所以不需要 Accessibility、Input Monitoring 或 Screen Recording 權限。
- 如果這組快捷鍵已被其他程式占用，App 會顯示警告；仍可按主畫面按鈕，或在 Log Solution 有焦點時使用相同按鍵。
- 目標最小螢幕解析度為 `1280 x 1024`。App 不會強制置頂，部署時應讓 Atlas／BT HMI 不覆蓋右上角看板。

- DFU：選擇 `active` 及 `unitest`；監看 slot1～7。
- FCT：選擇 `active` 及 `unit-archive`；監看 slot1～6。第一次讀到的可信 SN 會鎖定，active 消失後轉為 `COMPLETING` 並讀取最終 `records.csv`；全程無可信 SN 則顯示 `SN 讀取失敗 / FAIL`。
- BT：選擇 `TestData`，CaseInfo 根路徑可選。每輪固定監控 Thread0～3；CaseInfo 支援實機的 CSV 記錄格式（例如 `2026-08-21 15:19:24:160, ...,SNRead,...,條碼,...`），會在最終 CSV 到達前顯示 `TESTING` 與條碼。檔案可用 CR、LF 或無換行的時間戳切分，且分次寫入的未完成記錄會等待完整後才讀取；空 SN 的 FAILED CSV 顯示 `NOTEST`。

每輪紀錄保存在 `~/Library/Application Support/B518LogSolution/sessions/`，包含事件、結果、設定、時間與來源檔案。
