# 專案摘要｜2026-09-18

## 前次討論與既有交付

- 繁體中文離線手冊位於 Manual/index.html，服務產線 TE 與了解程式原理的其他部門開發者，回報管道為 WeChat。
- 已加入主畫面編號導覽、等比例截圖、圖 3 的 BT 路徑設定與儲存步驟，以及 FCT／BT 實機結果對照。
- 手冊以 B482 專案為範例，其他專案須自行選擇正確路徑。DFU／FCT 範例為 /Users/gdlocal/Library/Logs/Atlas/active 與 unit-archive；DFU 畫面欄位仍標示 unitest。
- BT 的 TestData 與 CaseInfo 欄位均選 /vault/B482_RFTEST/TestData；CaseInfo 選填但建議設定，以提早顯示測試活動與 SN。
- Session 保存事件、設定、結果與來源路徑，不含原始 Log 副本。

## 本次修正與核對結果

- TE 章節以「先記錄資料夾裡原本有哪些 Log，避免把舊結果當成這一輪的結果」解釋啟動準備。開發者章節說明記錄檔案大小與修改時間，區分 CSV 比對及 CaseInfo 時間篩選。
- 八種正常狀態顏色與目前原始碼一致：WAITING #d9d9d9、TESTING #ffff00、COMPLETING #82c7ff、PASS #00ef00、FAIL #ff0000、NOTEST #f04bf1、TIMEOUT #ff9900、STOPPED #bfbfbf。
- COMPLETING 是等待最終測試結果，可能在同次輪詢中被最終結果取代，UI 不一定呈現這個過渡狀態；實機安裝包是否與原始碼相同尚未驗證。
- NOTEST 分工站說明條件，不代表整輪完成；STOPPED 只標記尚未結束的通道；TIMEOUT 區分整輪等待開始與個別通道測試上限。
- 只有 PASS／FAIL／NOTEST 結果事件觸發看板回到前景。STALLED 僅有顏色定義，目前監控流程未產生，不列入正常操作狀態。
- 本次只修改手冊，保留既有截圖、CSS 顏色與 App 行為。
