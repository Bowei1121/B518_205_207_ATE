# 歷史事件查詢：日期範圍、背景載入與可重建索引規格 — 2026-10-13

狀態：需求與測試入口已確認；ready-for-agent。

追蹤議題：[GitHub #37](https://github.com/Bowei1121/B518_205_207_ATE/issues/37)。

## Problem Statement

操作員通常查閱三個月內的事件，目前開啟歷史視窗會同步讀取全部輪次與 App 事件、排序及全量呈現，資料累積後可能造成視窗長時間無法操作。使用者無法先指定日期，也無法以可控制的頁面大小查閱大量結果。

設備預估 UPH 約 700，規劃採 1,000 件／小時；90 天每天生產 8／16／24 小時時，產量估算分別為 72／144／216 萬件。產量不等於事件筆數，一輪可能涵蓋多件產品並產生多個事件，因此不得將此估算宣稱為已量測的事件量或現場效能。

僅在全量讀取後篩選日期不足以解決讀取成本。查詢也必須維持既有保存、監控、雙語顯示與期限清理契約，不能因加速而漏掉跨午夜、尚在追加或舊格式的事件。

## Solution

歷史頁面先顯示日期條件，預設最近 90 天；提供今天、最近 7／30／90 天、指定單日及自訂區間。操作員按放大鏡圖示按鈕才啟動背景查詢，可以取消或改條件後重新查詢，視窗及監控仍可操作。

結果依工廠當地日期篩選，最新事件優先，每頁最多 100 筆，以純左右箭頭換頁。原結果在重新查詢期間保留，新查詢成功取得結果才替換。新事件不自動插入，按查詢才更新。

建立可重建索引以避免未變更歷史反覆全量解析，按需取得頁面與詳細資料。索引故障可回讀原檔；局部讀取失敗或無有效日期時保留正常結果與原始診斷。查詢不延後正常清理，來源已消失時清楚提示。

## User Stories

1. 身為操作員，我希望開啟歷史頁面時先看到查詢條件，以便避免尚未選好範圍就讀取大量資料。
2. 身為操作員，我希望預設最近 90 天且包含今天，以便符合常用查詢範圍。
3. 身為操作員，我希望可快速選擇今天，以便追查當天事件。
4. 身為操作員，我希望可快速選擇最近 7 天，以便追查近期異常。
5. 身為操作員，我希望可快速選擇最近 30 天，以便查閱近月事件。
6. 身為操作員，我希望可快速選擇最近 90 天，以便查閱常用歷史範圍。
7. 身為操作員，我希望可指定單一日期，以便直接查某一天。
8. 身為操作員，我希望可自訂開始與結束日期，以便查較短或較長的期間。
9. 身為操作員，我希望起訖日期都涵蓋整天，以便不漏掉結束日的事件。
10. 身為操作員，我希望查詢依工廠當地時間計算，以便與現場日曆一致。
11. 身為操作員，我希望無時區的舊紀錄直接視為當地時間，以便不需額外設定原時區。
12. 身為操作員，我希望日期錯誤時在欄位旁提示，以便先修正且保留原查詢結果。
13. 身為操作員，我希望合法範圍不受 90 天上限限制，以便追查更早資料。
14. 身為操作員，我希望以放大鏡圖示啟動查詢，以便減少文字並容易辨識功能。
15. 身為操作員，我希望圖示有目前語言的停留提示並可用鍵盤操作，以便理解及操作按鈕。
16. 身為操作員，我希望修改條件不自動查詢，以便一次調整完再送出。
17. 身為操作員，我希望查詢中顯示狀態且畫面可操作，以便不誤認 App 停止回應。
18. 身為操作員，我希望等待期間可送出新條件，以便改查較小範圍。
19. 身為操作員，我希望只接受最新一次送出的查詢，以便舊查詢不覆蓋新結果。
20. 身為操作員，我希望可取消查詢而不停止監控，以便中止不再需要的工作。
21. 身為操作員，我希望重新查詢期間保留原結果與其日期標示，以便繼續查閱且不混淆條件。
22. 身為操作員，我希望整次查詢失敗時保留原結果並說明原因，以便了解問題並重試。
23. 身為操作員，我希望最新事件排在前面，以便先看到近期狀況。
24. 身為操作員，我希望每頁最多 100 筆，以便大量資料仍能順暢查閱。
25. 身為操作員，我希望以純左右箭頭換頁且首末頁停用不適用方向，以便容易辨識可用操作。
26. 身為操作員，我希望換頁保留日期條件，以便不用重新設定查詢。
27. 身為操作員，我希望選取事件可查看詳細資訊與原始診斷，以便追查原因。
28. 身為操作員，我希望新事件不自動改動查閱中的結果，以便頁面與選取位置保持穩定。
29. 身為操作員，我希望再次按查詢才納入新保存的事件，以便自行決定更新時機。
30. 身為操作員，我希望切換語言保留頁面與選取，以便不丟失查閱位置。
31. 身為操作員，我希望查詢涵蓋輪次與無輪次 App 事件，以便查完整操作經過。
32. 身為操作員，我希望局部檔案讀取失敗時仍看到正常結果，以便不因一份資料有問題就無法查閱。
33. 身為操作員，我希望看到資料不完整提示與詳細來源，以便不把部分結果誤認為完整結果。
34. 身為操作員，我希望無有效日期的資料仍保留原文可查，以便重要異常不被悄悄忽略。
35. 身為操作員，我希望空結果與資料讀取異常可區分，以便知道是沒有事件或尚無法確認。
36. 身為操作員，我希望資料已被清理時得到重新查詢提示，以便不誤認紀錄損毀。
37. 身為工程師，我希望重複查詢使用索引，以便未變更紀錄不反覆完整解析。
38. 身為工程師，我希望新增、變更及刪除來源能使索引更新或失效，以便加速不犧牲正確性。
39. 身為工程師，我希望索引可重建且故障時可回讀原檔，以便查詢不依賴唯一加速檔。
40. 身為工程師，我希望讀取失敗仍可重試，以便暫時性異常不永久排除資料。
41. 身為工程師，我希望分頁按需讀取詳細內容，以便記憶體不隨全部原始事件內容成長。
42. 身為工程師，我希望關閉視窗或多次重查能回收舊工作，以便不累積背景負擔。
43. 身為工程師，我希望查詢不改寫原始紀錄或清理資格，以便保存及稽核契約一致。
44. 身為開發人員，我希望以真實暫存紀錄與真正桌面視窗驗證，以便驗收實際行為。
45. 身為開發人員，我希望開發與桌面驗證完成後可合併，以便工廠驗收由後續部署工作獨立追蹤。

## Implementation Decisions

1. **責任與入口**：歷史查詢模組負責日期驗證、來源發現、索引、穩定結果集合、分頁及背景工作生命週期。沿用既有歷史紀錄讀取與呈現契約；桌面層只管理條件與畫面更新。以對外的提交查詢、取消及取得結果入口驗證整體行為，不讓視窗拼接多套資料規則。
2. **資料範圍**：合併輪次稽核事件、既有舊事件與 App 事件；沿用現有來源優先與識別規則，不因兩種保存格式同時存在就重複計入。查詢僅涵蓋已保存且可取得資料，不要求保存 worker 因查詢而立即落盤。
3. **日期依據**：使用 App 觀察／記錄事件時間；平台來源時間、檔案修改時間、輪次開始時間與封存時間都不能替代。當地時區取執行 App 電腦設定，查詢提交時固定日期條件與時區，避免執行期間條件漂移。
4. **日期邊界**：快捷 N 天為當地今天往前 N−1 天至今天。自訂起訖包含整天，以結束日次日當地午夜作排他上界；處理夏令時間，不能假定每個日曆日固定 24 小時。有時區時間先換算為當地時間；無時區舊時間直接以當地日曆判定，不猜原時區或還原重複時刻的絕對時間。
5. **輸入與啟動**：缺值、無效日期及反向區間不送出工作，保留舊結果。合法區間不限 90 天。開啟及編輯條件不自動掃描；按查詢才提交。原重新整理操作整合為相同查詢流程，避免保留繞過日期條件的全量入口。
6. **圖示操作**：查詢採放大鏡，分頁採純左右箭頭；不要求使用平台顯示效果不一致的彩色 emoji 作唯一實作方式。停留提示、操作名稱及鍵盤操作完整支援；首末頁停用相應方向。保留必要的進度、日期範圍、頁碼與異常文字，依目前語言顯示。
7. **結果與排序**：每頁最多 100 筆，依可判定事件時間由新至舊；相同時間使用穩定事件身分及數字序號作固定次序，避免重複或漏頁。無有效日期不混入指定日期的正常結果，而由異常詳細入口查閱。不同語言共用同一集合，不以翻譯文字作排序或身分。
8. **查詢狀態**：初始未查詢、查詢中、有完整／部分結果、失敗及取消均可辨別。每次送出配置獨立世代，只有最新有效世代可提交狀態與結果；僅編輯未送出條件不使舊結果失效。整次失敗或取消保留舊結果及舊日期標示，新查詢得到部分正常結果時可替換但須標示不完整。
9. **背景管理**：檔案掃描、解析、索引維護及大量結果處理不在 Tk 執行緒進行；只由 Tk 執行緒操作元件。多次重查不無限制啟動 worker，過期工作可協作停止，待處理請求以最新一次為準。取消、關閉及視窗重開不得接受舊回傳；App 關閉保存仍沿用既有契約，不等待無效查詢或因此新增保存工作。
10. **固定結果**：查詢取得事件身分與來源版本邊界，翻頁不重新加入後續新事件。再次查詢才更新。背景載入期間來源變動需驗證、重讀或標示未能確認，不以競態讀取發布可靠索引。這不是跨所有檔案同一瞬間的交易快照，不要求鎖住保存或清理。
11. **分頁與詳細內容**：大集合透過持久索引及按需查詢管理，不先載入全部原始事件物件再切頁；每頁最多 100 筆正常列表資料，詳細內容依選取取得。結果識別等精簡資料可另管理，但需有容量及回收證據。翻頁、切語言不重新全量掃描；索引損壞等異常必要恢復另行提示。
12. **索引內容與耐久性**：索引是可丟棄、可重建的衍生資料，不是新增原始稽核來源。保存來源身分／版本、事件識別、日期查詢所需時間及定位資訊等必要資料；索引格式與儲存技術由實作選擇，不擴大原始紀錄格式。本機重啟可使用有效索引，寫入中止或版本不支援可安全重建。
13. **安全跳過與增量**：只有已驗證且來源仍符合版本的事件範圍可用來排除日期外內容；不得只按資料夾名、開始或封存時間跳過輪次。未變更且成功整理的來源不反覆完整解析；新增、追加、替換、搬移及刪除可使索引更新或失效。需避免把來源內容變動誤認為未變更；App 整份事件紀錄變更時依來源能力更新，不強制改其保存方式。
14. **失敗與降級**：索引遺失、損壞、無法讀寫時在背景回讀原檔並提示這次可能較慢；回讀仍維持分頁與操作回應。不把失敗、損壞或變動未確認來源快取為成功；下次查詢可重試。首次全掃描與降級不承諾跳過所有來源，不能用此情境掩蓋正常增量查詢仍反覆全掃描。
15. **部分結果與診斷**：無有效日期、來源讀取錯誤或不完整保存沿用可查證的原始資料與警告。未知日期不推測所屬區間；提示說明其未納入日期結果。來源不可讀不等同區間無事件，空結果有異常時仍標示不完整。必要的異常清單也按需呈現，不一次塞入大量診斷文字。
16. **清理共存**：不因查詢視窗開啟延後合法清理。已取得內容（依 2026-10-14 使用者釐清，包含可信暫存已捕捉的完整原始 JSON）可繼續查看；原內容尚未取得的來源被刪除時在該事件位置提示不可取得，不填入其他事件或改報損毀。來源版本已替換且無法取得原版本時同樣不得冒充固定結果。索引刪除失效資訊不改清理 ledger、資格或原始保存期限。
17. **相容與多語言**：遵守既有保存前關閉、整輪封存清理及同筆繁中／英文事件契約。原始 SN、路徑、檔名、Log 與診斷不翻譯、不改寫。新介面文案集中管理，支援英文／繁中與既有回退；切語言保留輸入、結果世代、頁面與選取，不重掃磁碟或自動重新查詢。
18. **交付條件**：允許分階段實作及逐票驗收。功能所需程式、必要測試、桌面驗證與相應既有回歸通過即可合併回 B518 Log Solution 工作樹；最後完成全規格整合驗證。工廠實際資料量與設備效能是後續部署驗收，不能列為阻擋開發票合併的條件，也不能把本機通過宣稱為現場通過。

## Testing Decisions

使用者已確認：以既有歷史讀取／呈現入口、真實暫存紀錄，以及查詢提交／取消／結果取得的公開行為入口為主要測試 seam；真正 Tk 視窗是桌面整合驗證入口。優先少量高層入口，避免為每個私有 helper 新增測試介面。

良好測試驗證結果集合、日期與身分、可操作性、來源 bytes、實際 I/O 成本及生命週期；不只斷言某函式被呼叫。可注入時鐘、當地時區與受控慢速來源，使跨午夜及競態可重現；保存與清理使用正式公開入口和真實暫存磁碟。既有混合新舊歷史、數字序號、異時區排序、未知訊息原文，以及真 Tk 選取／語言／捲動／不改檔案案例為先例。

| 驗證組 | 必要案例與外部結果 |
| --- | --- |
| 日期與時間 | 指定單日、快捷 1／7／30／90 天、起訖整天、跨月年午夜、夏令時間 23／25 小時日期、有 offset 換算、無 offset 直接當地解讀、無效日期；不漏結束日事件、不猜檔案日期。 |
| 混合來源 | 正式輪次、舊事件、App 事件、同時存在格式、相同時間與序號；事件身分集合及穩定次序與安全原檔基準一致，頁面無重複漏筆。 |
| 分頁 | 0／1／100／101／多頁筆數，首末方向、詳細讀取、頁面與選取保留；不得全量建構所有詳細呈現內容。 |
| 查詢生命週期 | 受控慢讀尚未完成時 Tk 仍處理互動；多次重查打亂完成次序、取消、關閉重開、失敗、編輯但未送出；只有最新有效工作可更新畫面，舊結果與日期一致。 |
| 固定結果與語言 | 新增事件不自動出現，再查才納入；翻頁／切語言不改集合，不重新全量解析，保留操作狀態。 |
| 索引正確性 | 首次建立、重啟重用、未變更、追加、同路徑替換、搬移、刪除、跨午夜輪次、尚在寫入、版本不支援；與全量原檔基準比較，不能只按輪次開始或封存時間漏查。 |
| 索引失敗 | 損壞、遺失、權限／磁碟寫入錯誤、中斷建立、來源解析失敗後恢復；背景降級有提示，正常資料可查，失敗來源保留重試。 |
| 部分結果 | 壞檔、無有效日期、不完整保存、全部來源不可讀；正常結果與異常分開，不能把不可讀來源當作確認無事件，原文及來源可查。 |
| 清理與保存 | 正式清理與翻頁競態、來源版本變動、查詢期間保存追加及關閉保存；不延後正常清理、不混入其他事件、不改結果／待確認／期限／耐久性契約。 |
| 桌面及來源完整 | 真 Tk 日期輸入、放大鏡、左右箭頭、鍵盤／提示、取消、重查、雙語；操作前後原始來源 bytes 一致，衍生索引變動另計。 |

### 開發效能與容量驗收

- 至少測試 5 萬筆參考集及 **216 萬筆合成事件容量集**，後者是明確指定的工程壓力規模，不宣稱等於 216 萬件產品的實際事件量。容量集同時包含輪次及 App 來源、區間內外資料；記錄來源數、大小、事件比例及 runtime。小案例走自動回歸，大容量量測可另跑並保存開發驗收證據。
- 分別報告首次索引、索引有效的重複查詢、單一來源變更、索引降級及換頁的耗時、讀取 bytes、完整解析來源數、記憶體峰值與存活背景工作數。至少三次相同 fixture，揭露冷／暖條件；不拿單次最佳數據作結論。
- 成本合格條件：正常未變更重查及換頁不完整重讀／解析已成功索引的所有來源；允許目錄發現、必要版本檢查與目前頁面定位讀取。單來源變更不使其他未變更來源全面重解析；恢復案例可重掃但必須標明降級原因。
- 容量合格條件：正常列表每頁不超過 100 筆，完整歷史的原始物件與診斷不得全量駐留；持久索引大小、結果精簡資料與峰值記憶體實測揭露。重複查詢／取消／關閉後背景工作與查詢資源不持續累積。
- 桌面回應合格條件：以慢速來源被測試閘門阻擋的期間實際完成日期編輯、取消或重新送出等 Tk 操作，證明這些動作不需等磁碟讀取結束；整個換頁及結果呈現也不得在 Tk 進行全量格式化。容量測試附 Tk 回應間隔量測，不承諾未量測的工廠秒數。
- 同一容量集以無索引原檔查詢作正確性基準，比對事件識別與日期邊界；完整產品回歸與必要桌面驗證由實作票交付時執行。撰寫本 spec 不代表已跑上述驗收。

## Out of Scope

- 依 SN 查產品 PASS／FAIL、產量統計或完整生產報表。
- 改監控裁決、來源穩定期限、失敗重試、保存格式、保存天數、封存及清理資格。
- 改寫舊紀錄、猜原時區／檔案日期、搬移歷史到另一時區後還原原始絕對時刻。
- 改 App 事件保存為新 journal 技術、提供外部資料庫服務、要求原子跨來源快照或禁止正常清理。
- 查詢結果自動追蹤新事件、現場手動匯入翻譯、新增語言或查詢匯出功能。
- 把工廠資料取得、設備效能驗收或正式部署完成設為開發票合併前提。

## Further Notes

- 來源為已確認的歷史事件查詢討論 A1–A18，另已確認本規格的測試入口；不重新開啟需求訪談。
- 遵守 ADR0007 整輪封存保存期限、ADR0008 保存成功才關閉與 ADR0009 同筆雙語／舊檔不改寫契約。ADR 的歷史狀態標頭不是當前程式是否完成的判斷依據。
- 查詢日期不是清理期限：前者用事件觀察時間，輪次清理仍以可信封存時間，App 事件清理仍以原事件時間。索引不能改變此界線。
- 前次 5 萬筆約 1.95 秒為合成舊紀錄讀取／排序與文字準備兩段中位數合計，未含 Tk 插入及現場磁碟；只作現況背景，不作本規格現場性能承諾。
- 後續可拆垂直開發票，分階段遷移並最終移除舊全量桌面路徑；本 spec 本身不建立子票、不修改產品程式。
- 工廠後續驗收另記每日運轉時間、實際事件／產品比例、三個月存量、現場硬碟與 Tk 回應；可合併與可部署的狀態分別記錄。

## H1 implementation coverage — 2026-10-13

H1 applies the date-range entry and first-page subset of this specification: recent-90-day default, explicit date submission, local-day boundaries, existing mixed-source precedence, bounded newest-first results, original-detail lookup on selection, and background reading with an interactive Tk window. The H1 implementation and its seven acceptance checks have independent evidence in [H1 local validation](evidence/historical-event-query-ticket-01/local-validation.md). This coverage note does not mark the full parent specification delivered: cancellation/latest-query lifecycle is H2, complete pagination is H3, persistent index and incremental-read guarantees are H4, and the remaining stories stay assigned to H2–H8. It does not claim factory-volume or deployment acceptance.

## H2 implementation coverage — 2026-10-13

H2 adds a public app-scoped query service and wires it into the existing history window. Each submitted request snapshots its date range and local timezone; a monotonically increasing generation gates visible results, progress, and errors. A single active read cooperates with cancellation while one pending request is replaced by the latest submission. The history page keeps the previous result and its date range until a successful current query replaces it; editing an unsubmitted draft does not relabel that result. Cancel, window close, app close, and reopen invalidate stale deliveries without joining a slow reader on Tk's thread. The actual Tk lifecycle evidence and seven H2 checks are recorded in [H2 local validation](evidence/historical-event-query-ticket-02/local-validation.md).

This coverage is limited to H2's query lifecycle. It does not claim H3 pagination, H4 persistent indexing, H5 complete error recovery, H6 retention-race integration, H7 complete icon/keyboard localization, H8 capacity acceptance, or delivery of this parent specification. Factory-volume and deployment acceptance remain separate.

## H3 implementation coverage — 2026-10-13

H3 extends the H1 bounded first page into a fixed, disk-backed query snapshot with complete 100-row pagination. The history UI exposes previous/next arrows and page information, keeps the captured result set and source boundary stable, and loads original detail only for the selected event. Pagination reads the requested snapshot range without rescanning the source files; the snapshot is released when replaced or when its owning app window is destroyed. Source readers stream validated saved records in the background, and the Tk thread only publishes bounded page summaries and selected detail. Acceptance evidence, including real Tk navigation, mixed-source identity/order, source-byte preservation, memory observations, and resource cleanup, is recorded in [H3 local validation](evidence/historical-event-query-ticket-03/local-validation.md). This is not H4's persistent/restart-reusable index or cross-query incremental-read guarantee, nor H5–H8 or complete parent delivery; factory-volume and deployment acceptance remain separate.

## H4 implementation coverage — 2026-10-14

H4 adds a versioned, disposable SQLite derivative index to the public query service and actual App path. Successful indexing requires complete source reads and matching source versions before and after parsing; unchanged sources are reused by a newly created service, while changed sources refresh independently. Event time remains interpretable under the submitted timezone, and the existing H3 fixed page snapshot and selection-only detail contract remain in use. The H4-specific source mutation, race, disk/restart, I/O, memory and true-Tk evidence is recorded in [H4 local validation](evidence/historical-event-query-ticket-04/local-validation.md). H4 covers only its ticket allocation: H5 recovery UI, H6 full save/cleanup race integration, H7 complete interaction/localization, and H8 capacity/full closeout remain separate. Following local fast-forward, the historical Aqua initialization abort was isolated to sandbox GUI access using identical zero-project Tk probes; the clean mainline's desktop run passed 439 Tk-enabled tests in 160.299 seconds, exit 0, without skips. Final synchronization is recorded in the acceptance resumption, and the user-requested stop retains the H4 branch/baseline worktree. This does not claim all of parent #37, factory acceptance, or deployment.

H5 handles derivative-index loss, corruption, unsupported versions and read/write failures by rejecting the unreliable acceleration data and running the established source query in the background. A successful rebuild after an existing index fault is still reported as degraded for that search; ordinary first-use index creation is not described as corruption. The actual App status uses the centralized current-language catalog with English fallback. Partial and unknown-date results remain visibly incomplete, and a paged diagnostic list retrieves original source detail only for a selected anomaly. Query failure/cancellation continue to rely on H2's previous-result and range retention; manual Search retries through the same public service. Readable legacy records preceding a later decode failure remain in the fallback result, while that failed source is not committed as a successful persistent-index entry and stays retryable. H5-specific real-disk, true-Tk, source-byte and recovery evidence is recorded in [H5 local validation](evidence/historical-event-query-ticket-05/local-validation.md). This allocation does not include H6's full save/cleanup race integration or source-disappearance position, H7's complete icon/tooltip/keyboard and all-state language integration, or H8's volume and old-flow closeout. It does not claim full parent #37, factory acceptance, or deployment.

## H6 implementation coverage — 2026-10-14

H6 keeps a query's source identity/version with its disk-backed fixed snapshot. The H3 temporary snapshot contains the complete captured raw event JSON; under the user's explicit clarification, that trusted captured content counts as acquired and remains readable after official source removal or same-path replacement, even if the user had not yet selected the detail. Detail reads use the frozen snapshot and never reopen a replacement path. A subsequent public query refreshes the deleted derivative-index source and publishes the then-current set. The official App-event retention entry and RoundCoordinator retention entry were exercised against isolated real files while a result stayed open. The fallback source scan also checks each source before and after parsing and excludes records from a source whose version changed during that scan, reporting the source as unconfirmed; indexed and fallback reads recheck the discovered source set. H6's seven-item evidence, diagnosed historical M10 test-fixture Tk traceback cycle, subprocess red/green regression, final default Python 3.8.10/Tk 8.6.8 full suite (461 tests / 139.240 sec / exit 0 / no skips), fixed-base dual review and mainline closeout are recorded in [H6 local validation](evidence/historical-event-query-ticket-06/local-validation.md). This does not include H7's complete icon/tooltip/keyboard integration, H8's capacity and old-flow closeout, full parent #37, factory acceptance, or deployment.

The unavailable-source position rule in item 16 is conditional on original raw content not yet being acquired. Every valid fixed row in the current H3 contract already has the complete captured `event_json` in its owned disk snapshot; selection only loads/deserializes that captured payload. Thus a valid fixed row with uncaptured original detail does not occur in this implementation, and the conditional Tk unavailable-position check is not applicable. A source lost or unconfirmed during capture is reported via incomplete-source diagnostics without publishing invented normal event rows. H6's evidence explicitly distinguishes that applicability from the tested acquired-content-after-cleanup behavior and does not claim an unavailable-position test that was not performed.

H6 locally fast-forwarded into `B518-Log-Solution` at `592310ee51d813111b2f02297a4a6756e97ce0ac` with no merge commit. The post-integration default Python 3.8.10/Tk 8.6.8 full suite passed 461 tests in 138.609 seconds, exit 0, without skips. Final documentation synchronization and H6-only cleanup are recorded in the evidence closeout.

## H7 implementation coverage — 2026-10-14

H7 completes the allocated icon, keyboard and live-localization behavior for the actual history window. Search pairs a magnifier with its localized action name; page controls remain pure left/right arrows with the existing boundary disabling. Current-language non-focusing hints are tied to control/window lifecycle. The existing App language receiver rerenders shared query/date/page copy while retaining unsent date text, the H2 query generation and old result range, H3 page/selection/detail and visible reading position; changing language does not submit a query or change the fixed set. An Event-gated real-Tk test verifies progress changes language in flight and the completed result renders in the language current at completion. Audit, legacy `events.log`, App journal and selected raw diagnostic bytes/text remain unchanged. Evidence, full-suite history, fixed-base Standards/Spec results, remote closeout and limits are in [H7 local validation](evidence/historical-event-query-ticket-07/local-validation.md). H7 does not claim physical keyboard/mouse device testing, screen-reader certification, H8 all-state/capacity closeout, factory acceptance, deployment, or complete parent #37.

## H8 implementation coverage — 2026-10-15

H8 completes the local development acceptance of the 45 stories with a row-by-row final-version matrix, mixed-source 50,000- and 2,160,000-synthetic-event fixtures, and five measured cost scenarios with three runs per fixture. It records independent original-reader identity digests, parse/read costs, memory, index/snapshot size, worker cleanup, and actual Tk responsiveness on real temporary disk sources. Opening the history window, editing its draft, and language refresh remain condition-only/render-only actions; Search is the public read entry, while first-use and index-degradation scans remain supported background paths. The real-Tk test verifies opening creates no index, gated query work permits draft editing, bounded first- and second-page arrow navigation, selected detail, source-byte preservation, and complete App close. The actual App result first/middle/last pages are identity-compared with the independent original-reader baseline. The retained reports distinguish initial index absence from uncontrolled OS cache and do not treat logical parser bytes as physical I/O. Full suite, capacity data, review and limitations are in [H8 local validation](evidence/historical-event-query-ticket-08/local-validation.md) and linked run reports. H8 records engineering synthetic volume only; it does not claim factory event volume/performance, deployment, or physical-device/accessibility certification. The implementation allocation across H1–H8 has local evidence but this coverage note does not alter remote parent issue #37 or claim plant acceptance.
