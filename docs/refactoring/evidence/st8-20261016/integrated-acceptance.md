# ST8 整合桌面驗收紀錄 — 2026-10-16

## 基準與結論

驗收對象是整合提交 `0d927ae1678795b1394eec8a8a930a106c8b0aba`，不是原工作樹暫稿。該提交包含已整合 ST1–ST7；ST8 此次補上故事逐項追溯、按鈕實例清點、整合驗證結果與現場待驗清單。前票有效的真實 B518 App/Tk 操作和中英 PNG 逐項重用，沒有把 widget/style lookup 或本文件本身當成產品行為通過證據。

本機可重現驗收涵蓋 Slot 高度／容量矩陣、雙徽章生命週期、語言選單、主頁與設定／恢復／裁決／警報／歷史／診斷／關閉按鈕提示、代表性可用及停用互動、恢復視窗真正 Light/Dark 切換，以及監控、人工裁決、人工警報確認、保存／封存重試和取消關閉保護。對應有效證據及結果列於下方故事表及各票原始驗收紀錄。

## 52 項使用者故事追溯

| 故事 | 整合驗收證據 | 結果／界線 |
| --- | --- | --- |
| 1 | [ST1 1/10/11/20 容量矩陣與淺灰空白](../st1-20261016/README.md) | 通過本機真 App；工廠顯示環境另測 |
| 2 | ST1 matrix screenshots、`regression-result.txt` | KVM 狀態色及未用黑格保留；工廠影像辨識另測 |
| 3 | ST1 高度矩陣、1/10/11/20 雙語真 App 圖 | 十列上限通過；足夠高度下十列圖在 `large/` |
| 4 | ST1 20 項末頁圖及實際捲軸箭頭至 `yview=1.0` | 通過，末列可見 |
| 5 | ST1 650px 矩陣及末頁圖 | 可用列數依高度減少；其他顯示比例留待工廠測 |
| 6 | ST1 回歸記錄原 14pt 字體及列高 | 通過，未縮字 |
| 7 | ST1 各矩陣操作區 bounds 與截圖 | 開始／停止／保存／診斷仍可見 |
| 8 | ST1 cap1 靜止捲軸及 viewport matrix | 淺灰停用狀態通過 |
| 9 | ST1 scrollbar bounds、20→1 回歸 | 欄位固定且欄寬不跳動 |
| 10 | ST1 cap10/11/20 × 650px matrix | 以實際可視列及末端操作驗證啟用；不以容量門檻推斷 |
| 11 | ST1 20→1 容量切換及視窗高度 matrix | yview 修正且末列可達 |
| 12 | [ST2 12/1 真 App 雙徽章中英畫面](../../../../B518%20Log%20Solution/docs/refactoring/evidence/st2-20261016/st2-twelve-conflicts-en.png) | 通過，獨立計數及位置完整 |
| 13 | ST2 zero-count 情境；ST7 zero-alarm/recovery 雙語圖 | 零值隱藏通過 |
| 14 | ST2 真輪次測試開窗不清零 | 通過，衝突 12 與警報 1 維持 |
| 15 | ST2 真輪次人工裁決後更新；ST5 disabled candidate no-op | 完成裁決才減少，停用操作不裁決 |
| 16 | ST2 conflict/alarm independent-count regression | 12 與 1 分開維持 |
| 17 | ST2 12-count header crop / full screenshot | 兩位數完整顯示；9+ 封頂未引入 |
| 18 | ST2 toolbar focus bilingual PNG、ST2 acceptance notes | 設定、Logo 與入口排列在同列 |
| 19 | ST2 `window-bounds.json` 與 Logo 尺寸紀錄 | 原比例、固定 137×35 slot；Logo 缺失也保留空間 |
| 20 | ST2 真 App header bounds / screenshots | 徽章留白完整，不碰標題列 |
| 21 | ST2 12/1 full screenshot、header crop | 雙徽章與語言入口不相交 |
| 22 | ST2 count-change geometry regression | 數量改變不推動工具列位置 |
| 23 | ST2 中英畫面與切語言回歸 | 切語言不改入口位置 |
| 24 | ST2 missing/corrupt Logo regression | 槽位固定、不顯示文字替代 |
| 25 | [ST2 toolbar focus 真實畫面](../../../../B518%20Log%20Solution/docs/refactoring/evidence/st2-20261016/toolbar-focus-language-en.png) | 🌐 入口沒有原生箭頭；未以裁切藏箭頭 |
| 26 | ST2 實體滑鼠選取及真鍵盤選單測試 | 按鈕可點範圍、鍵盤入口通過 |
| 27 | ST2 Quartz Tab/Space/Down/Return/Escape + manual pointer | 目前語言、選取和取消通過 |
| 28 | ST3/4/5/6 button inventory 與逐票中英提示證據 | 所有盤點的適用按鈕均有雙語用途提示 |
| 29 | ST3 真主頁 hover 中英圖；ST4/5/6 真視窗 hover 圖 | 懸停提示由實際 App 顯示 |
| 30 | ST3 真 Tab/Shift+Tab focus 測試；ST2 toolbar traversal | 鍵盤焦點提示已驗證 |
| 31 | ST3/4/5/6 真測試之離開、焦點、關窗生命週期 | 提示清除與焦點仍在時保留規則通過 |
| 32 | ST3 tooltip screenshots/catalog；逐票操作效果核對 | 效果與適用快捷鍵有對應文案 |
| 33 | ST4 disabled retry、ST5 disabled candidate、ST6 disabled cancel 真圖 | 停用按鈕可讀原因但不能執行 |
| 34 | ST3 Start hover en/zh-TW 真 App 圖 | 淺藍懸停已呈現；使用者於 2026-10-16 看過真 App 對照後明確選擇保留 |
| 35 | ST3 focus en/zh-TW、toolbar focus 真 App 圖 | 藍色焦點框已呈現；使用者於 2026-10-16 看過真 App 對照後明確選擇保留 |
| 36 | ST3 focus-mouse-out screenshot與互動測試 | 懸停離開後焦點仍保留 |
| 37 | ST3 pressed screenshot及真滑鼠事件測試 | 按壓有回饋；釋放還原通過 |
| 38 | ST3 disabled Stop／ST4-6 disabled control 回歸 | 灰色且 no-op |
| 39 | ST3、ST4、ST6 動態狀態切換測試 | 文案與可用狀態刷新；停用效果不殘留 |
| 40 | ST4/5/6 開窗語言刷新及 ST2 language round-trip | 已開視窗提示更新成目前語言 |
| 41 | ST3/4/5/6 真畫面與現有短標籤清單 | 開始／停止／保存等短標籤保留 |
| 42 | ST3/5 真輸入 no-op / focus tests | 顯示提示不觸發命令、不搶焦點、不確認警報 |
| 43 | ST3/4/5/6 destroy/reopen tests | 關閉後清理浮窗／回呼，未見殘留 |
| 44 | [ST7 同一視窗 Dark／Light 真切換、兩語截圖](../../../../B518%20Log%20Solution/docs/refactoring/evidence/st7-20261016/st7-dark-before-tab0-en.png) | 外觀本機通過；OS 標題列仍由系統管理 |
| 45 | [ST7 Light tab 0/1 繁中／英文完整畫面](../../../../B518%20Log%20Solution/docs/refactoring/evidence/st7-20261016/st7-light-open-tab1-en.png) | 兩分頁與外層留白固定淺色 |
| 46 | [ST7 外觀切換結果](../../../../B518%20Log%20Solution/docs/refactoring/evidence/st7-20261016/appearance-change-result.txt) | 視窗開啟時 Dark→Light→Dark；使用者原 Dark 已還原 |
| 47 | ST7 list-reading、alarm、selection/reopen 真 Tk 回歸 | 選取／閱讀及語意狀態保留 |
| 48 | ST4/6 語言、分頁、關窗重開保留測試；ST7 archive list | 輸入、選取、捲動位置保留 |
| 49 | ST1 KVM bounds、ST2 toolbar bounds、ST3 before/after geometry | 固定 marker、格位、狀態色與主頁幾何保留；工廠 KVM 另驗 |
| 50 | ST2 adjudication；ST4/5 recovery/close-save；ST7 no auto-retry | 人工裁決、人工 ack、save/archive retry、取消關閉與完整保存才關閉回歸通過 |
| 51 | ST1–ST7 中英真正 App/Tk PNG 索引及 ST3 hover／focus 對照 | 使用者已看過繁中／英文樣式畫面，明確核可保留淺藍懸停與藍色焦點框 |
| 52 | 本檔及 [按鈕清單](../../../../B518%20Log%20Solution/docs/refactoring/evidence/st3-20261016/button-coverage.md) | 主頁、動態設定、通知恢復、裁決、警報、查詢、診斷、關閉及訊息按鈕皆列入 |

## 全 App 按鈕實例清點

按整合程式中建立的 `ttk.Button` 對照 ST3 coverage manifest：**41 個實際按鈕實例**，分屬九種視窗／入口；另有兩個可點擊 Canvas 計數徽章代理到既有待確認／警報按鈕，語言選單另有原生選單項目。逐類控制、動態／停用狀態與有效證據見 [button-coverage.md](../../../../B518%20Log%20Solution/docs/refactoring/evidence/st3-20261016/button-coverage.md)。清單是依 `src/b518_log_solution.py` 與 `src/localized_notice.py` 建立點核對，不把文字欄、清單、捲軸、Logo、KVM 格位或 OS 原生對話框算成 App 按鈕。

| 視窗 | 實例 | 動態／狀態覆蓋 | 真正畫面／操作證據 |
| --- | ---: | --- | --- |
| 主頁工具列與底部操作 | 8 | 徽章點擊代理、待確認／停止／保存停用、Start/Stop 狀態 | ST2、ST3 中英主頁、hover/focus/pressed/disabled |
| 設定 | 14 | 每配置 3 個動態路徑 chooser；配置套用、期限清理重試等狀態 | ST4 設定三分頁、原生 NSOpenPanel Cancel |
| App 診斷 | 3 | 事件保存重試、語言更新重試、關閉 | ST6 診斷中英及停用重試提示 |
| 待確認裁決 | 3 | 原結果、新候選依選取／來源狀態停用、關閉只收窗 | ST5 真實 disabled hover 英中、點擊 no-op |
| 通知與恢復 | 3 | 人工警報 ack、選取項目保存重試、封存重試動態啟用 | ST4/7 真實兩分頁中英、狀態回歸 |
| 整輪警報 | 2 | ack 依準備／已確認狀態停用、Close 不 ack | ST5 真實警報／裁決同畫面及 no-op |
| 歷史查詢 | 5 | 上／下頁、取消、搜尋、續頁重試依查詢狀態更新 | ST6 真實 disabled/active Cancel 提示及回歸 |
| 關閉前保存 | 2 | 重試、取消關閉；成功完整保存才關閉 | ST5 close/save retry 與回歸 |
| App 訊息視窗 | 1 | acknowledge-only，語言刷新時保留閱讀位置 | ST5/7 notice lifecycle 與中英顯示 |

共通樣式和提示的真操作採代表性控制驗證，不假設每個不同控制都經過人工滑鼠移入；未逐一人工 hover 的項目已有雙語提示目錄、狀態來源測試及所屬真視窗截圖。具體人工滑鼠已驗證的停用控制是 Settings「Retry Selected」、ST5「Accept New Candidate」、ST6「Cancel search」；其他控制沒有宣稱逐一以實體滑鼠驗收。

## 整合測試與風險

- ST1：真 Tk/Aqua 1/10/11/20 容量及足夠／不足高度矩陣，繁中／英文共 32 個場景；末列以捲軸箭頭實際到達並記錄 `yview`，另有 12 個 KVM／macOS 幾何回歸。詳細數據、命令與畫面在 ST1 README、matrix 與 result 檔。
- ST2：真 Tk toolbar keyboard、12 conflict + 1 alarm lifecycle、Logo 缺失／損壞及 KVM bounds；真滑鼠實際開啟語言選單與選取，真鍵盤測取消／選取。對應 ST2 acceptance notes。
- ST3–ST6：沿用各票記錄的真 Tk/Aqua 行為及各自測試結果；包含滑鼠與鍵盤提示、停用 no-op、人工裁決／警報、歷史 query 狀態轉換、Settings 原生 chooser Cancel、保存／封存重試及取消關閉。沒有以各票程式檔案數或 widget 存在取代驗收。
- ST7：使用者實際操作 macOS 外觀；同一個已開 Recovery 視窗於 Dark／Light、兩分頁、兩語擷取完整畫面，並已恢復起初 Dark。成功互動結果及畫面有效；capture-helper hardening 後 replay 在 AppKit 建立 Tk application menu 時 abort，unittest 沒有進入測試本體，**不列通過**。完整 Light/Dark 原生畫面與此限制見 ST7 `local-validation.md`。
- 最終審查另在修復前整合版 `77d15fb` 的獨立乾淨工作樹，以真正 App 的同一恢復視窗完成 Dark→Light→Dark 基線重現嘗試；三張單獨視窗原生截圖、bounds 及系統模式讀回紀錄位於 ST7 `baseline-reproduction-attempt/`。內容在三個模式畫面都呈淺色，原先回報的深色／重繪症狀本次**未能重現**，因此根因仍未確定；不能把此次結果說成重現或根因證明。系統外觀最後讀回 Dark。
- ST8 在此整合工作樹重跑：`PYTHONPATH=src:tests python3 -m unittest test_language_catalog test_kvm_display_contract` **15 tests OK**；Python 3.8 `py_compile` 通過 `b518_log_solution.py`、`localized_notice.py`、UI 與 Slot 測試模組；`git diff --check` 及故事／證據檔案完整性檢查通過（故事 1–52 各一列，清單計數 41）。不再改系統外觀，也不啟動數小時歷史容量效能測試。各票真桌面有效證據維持為其原提交所產生，ST8 不重拍無缺漏的畫面。

使用者於 2026-10-16 檢視 [游標移開後保留焦點框](../../../../B518%20Log%20Solution/docs/refactoring/evidence/st3-20261016/st3-main-focus-mouse-out-en.png) 與 [淺藍懸停及焦點框](../../../../B518%20Log%20Solution/docs/refactoring/evidence/st3-20261016/st3-main-hover-en.png) 的真正 App 畫面對照，明確選擇保留目前樣式。

未驗證：工廠電腦、產線實機 KVM／壓縮識別容差、工廠資料流程，以及未涵蓋的 macOS／顯示縮放組合。它們屬現場驗收，沒有否定已通過的本機 App 與桌面證據。另有 ST7 AppKit replay 啟動限制如上，保留原始錯誤而不冒稱 pass。
