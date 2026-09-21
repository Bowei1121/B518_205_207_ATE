# 專案摘要｜2026-09-11

## 背景

B518 Log Solution 是 macOS 本機 Log 監控程式，為 DFU、FCT、BT 顯示多通道測試狀態、產品 SN 與 KVM 可辨識的色帶。程式不控制測試機，僅讀取本機可存取的 Log。

## 本次決議

- 以繁體中文離線網頁手冊交付；使用者雙擊 `Manual/index.html` 閱讀，不需網路或套件。
- 讀者分為產線 TE 與接收程式的其他部門開發者。開發者內容只說明原理與資料流，不提供改碼或打包教學。
- TE 的問題回報先在 WeChat 與開發者討論；手冊提供可複製回報範本與附件指引，不建立線上回報系統。
- 手冊使用現有 BT 截圖；DFU、FCT 使用目錄示意和表格，避免以不是真實畫面的圖片造成誤解。

## 重要操作事實

- 每輪先開始監控，程式建立時間基準和快照後才操作測試機；舊檔未變更不會列入本輪。
- DFU、FCT：目前產線參考 active + unit-archive，DFU 為 7 Slots、FCT 為 6 Slots；BT：TestData 必填、CaseInfo 選填，Thread0–3 對應 Slot1–4。
- Session 位於 `~/Library/Application Support/B518LogSolution/sessions/`，包含設定、事件、結果與來源路徑，不含原始 Log 副本。

## 使用手冊第二版調整

- 手冊先說明 HMI 區域、KVM 色帶、結果表格與開始／停止監控，再說明操作步驟。
- DFU、FCT 的產線參考路徑為 `/Users/gdlocal/Library/Logs/Atlas/active` 與 `/Users/gdlocal/Library/Logs/Atlas/unit-archive`。DFU App 欄位目前仍標示 unitest，實機設定依 unit-archive 選取。
- BT 的 TestData 與 CaseInfo 欄位均指向相同的 TestData 根資料夾；CaseInfo 保持選填，但建議設定以提早顯示 SN 與測試活動。
- 新增 FCT、BT 實機畫面對照，說明測試機、CSV Thread 與 Log Solution Slot 的結果關係。
- 手冊以 B482 專案製作；BT 參考路徑為 `/vault/B482_RFTEST/TestData`，其他專案需選擇自身正確的 Log 根路徑。
