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
- DFU：active + unitest，7 Slots；FCT：active + unit-archive，6 Slots；BT：TestData 必填、CaseInfo 選填，Thread0–3 對應 Slot1–4。
- Session 位於 `~/Library/Application Support/B518LogSolution/sessions/`，包含設定、事件、結果與來源路徑，不含原始 Log 副本。
