# B518 Log Solution 手冊維護

## 轉發方式與檔案分工

- `Manual/` 僅保留閱讀所需的 11 個檔案：`index.html`、`index-en.html`、`manual.css`、`patch.css`、`manual.js` 及 `Photo/` 內六張原始截圖。整個資料夾可以直接轉發，不能只傳 HTML，否則圖片、樣式與互動會遺失。
- 收件者先解壓縮，再開啟 `Manual/index.html`；頁面頂端可以切換 English，也可以直接開啟 `index-en.html`。不需安裝套件或連線。
- 維護文件與專案摘要保存在 `docs/manual/`，不放入轉發資料夾。歷史摘要中的舊路徑保留作為當時紀錄。
- 本次提供專案根目錄的 `B518_Log_Solution_Manual_2026-09-21.zip`，ZIP 為本機交付產物，依既有 `.gitignore` 不提交。更新手冊後應重新打包，排除 `.DS_Store`、`__MACOSX`、Markdown 紀錄及其他非閱讀資源；壓縮檔內只需 `Manual/` 的上述 11 個檔案。

手冊入口為 `Manual/index.html`，樣式及互動分別在 `manual.css`、`manual.js`。所有資源必須使用相對路徑，讓使用者可直接以 `file://` 離線開啟。

## 中英文同步維護

- 繁體中文為 `index.html`，完整英文版為 `index-en.html`；共用 `manual.css`、`patch.css`、`manual.js` 及六張原始圖片。兩版全文直接寫在 HTML，停用 JavaScript 仍可閱讀並透過頂端連結切換。
- 修改時同步翻譯章節、表格、警語、圖說、alt／aria-label、data-caption、回報範本、文件日期與版本，保留相同章節 ID、圖號及順序。英文操作說明附上 App 的原始中文標籤，例如 Settings（設定）。
- 路徑、SN、狀態名稱、顏色與程式識別名稱不可因翻譯改變。原圖維持中文實機畫面，不製作英文假畫面。MD 維護文件與專案摘要維持繁體中文。
- `manual.js` 依 HTML 的 lang 選擇複製與圖片放大提示；英文頁為 en、中文頁為 zh-Hant。新增互動提示需同時提供兩種語言。
- 語言連結帶 `?lang=en` 或 `?lang=zh-Hant`，優先於 localStorage 的 `b518-manual-language`。只有未帶語言參數的中文入口會依已存英文偏好跳轉，直接開啟英文頁則保留英文。切換時以目前閱讀章節保留定位；不跨頁保存檢查表或測試資料。瀏覽器可能限制 file:// 儲存，捕捉錯誤後仍使用正常語言連結。
- 列印目前頁面的語言，隱藏語言切換；列印前展開異常處理，列印後恢復原本狀態。

驗收兩版的離線開啟、語言來回切換、章節定位、記憶偏好、禁止儲存與停用 JavaScript 情境，以及圖片放大／Escape、複製成功／失敗、手機與列印版面。記錄哪些是實際瀏覽器驗證，哪些只有靜態檢查。

當 B518 Log Solution 修改工站、路徑結構、CSV 格式、狀態、逾時值、Session 輸出或畫面時，請同步更新本文和手冊內容。截圖放在 `Manual/Photo/`，每張圖需保留用途明確的圖說與 alt 文字；實機對照圖還需標示測試機通道、CSV Thread 與 Log Solution Slot 的對應關係。

本手冊以 B482 專案製作，其他專案必須依自身環境選擇正確路徑。B482 目前產線參考路徑為 `/Users/gdlocal/Library/Logs/Atlas/active`、`/Users/gdlocal/Library/Logs/Atlas/unit-archive`，以及 BT 的 `/vault/B482_RFTEST/TestData`。BT 的 TestData 與 CaseInfo 設定欄位都選相同的 TestData 根資料夾；更新部署或實機結構時，先核實這些路徑再改寫手冊。

發版前以瀏覽器直接開啟 `index.html`，確認：圖片可讀取及可放大、行動版導覽可收合、回報範本可複製或手動選取、列印不顯示側欄和操作按鈕。手冊說明必須以 `B518 Log Solution/log_monitoring.py` 與 `b518_log_solution.py` 的實際行為為準。

狀態校對時應一起核對狀態產生條件、STATUS_COLOURS、Slot 與 KVM 色帶的套色流程，以及回到前景的觸發條件。2026-09-18 已確認手冊八種狀態顏色與原始碼一致，COMPLETING 為 #82c7ff；實機安裝包尚未驗證，不能只因未觀察到短暫狀態而更改手冊色彩。TE 內容以「先記錄原有 Log，避免誤讀舊結果」說明啟動準備。
