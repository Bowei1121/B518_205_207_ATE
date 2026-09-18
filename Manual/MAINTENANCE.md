# B518 Log Solution 手冊維護

手冊入口為 `Manual/index.html`，樣式及互動分別在 `manual.css`、`manual.js`。所有資源必須使用相對路徑，讓使用者可直接以 `file://` 離線開啟。

當 B518 Log Solution 修改工站、路徑結構、CSV 格式、狀態、逾時值、Session 輸出或畫面時，請同步更新本文和手冊內容。截圖放在 `Manual/Photo/`，每張圖需保留用途明確的圖說與 alt 文字；實機對照圖還需標示測試機通道、CSV Thread 與 Log Solution Slot 的對應關係。

本手冊以 B482 專案製作，其他專案必須依自身環境選擇正確路徑。B482 目前產線參考路徑為 `/Users/gdlocal/Library/Logs/Atlas/active`、`/Users/gdlocal/Library/Logs/Atlas/unit-archive`，以及 BT 的 `/vault/B482_RFTEST/TestData`。BT 的 TestData 與 CaseInfo 設定欄位都選相同的 TestData 根資料夾；更新部署或實機結構時，先核實這些路徑再改寫手冊。

發版前以瀏覽器直接開啟 `index.html`，確認：圖片可讀取及可放大、行動版導覽可收合、回報範本可複製或手動選取、列印不顯示側欄和操作按鈕。手冊說明必須以 `B518 Log Solution/log_monitoring.py` 與 `b518_log_solution.py` 的實際行為為準。

狀態校對時應一起核對狀態產生條件、STATUS_COLOURS、Slot 與 KVM 色帶的套色流程，以及回到前景的觸發條件。2026-09-18 已確認手冊八種狀態顏色與原始碼一致，COMPLETING 為 #82c7ff；實機安裝包尚未驗證，不能只因未觀察到短暫狀態而更改手冊色彩。TE 內容以「先記錄原有 Log，避免誤讀舊結果」說明啟動準備。
