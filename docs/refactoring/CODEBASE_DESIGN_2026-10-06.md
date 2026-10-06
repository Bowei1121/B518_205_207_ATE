# B518 Log Solution 設計與優化分析

日期：2026-10-06（Asia/Taipei）

分析基準：`28239f5706c593cf29cbc10d1e8d193a0a2f556c`，分支 `B518-Log-Solution`。範圍為 `B518 Log Solution/src/` 的 15 個 Python 檔、相關測試與領域文件；不是整個 repo 其他工具的全面審查。本次沒有修改產品程式。

使用 codebase-design skill 的 Module、Interface、Seam、Adapter、Depth、Leverage、Locality 詞彙。優先度表示改善順序，不表示所有項目都是已發生的產品故障。

## 結論

ADR 0005 的配置／平台資料來源／監控輪次／桌面介面分工值得保留。已有真正的多 Adapter Seam，也有可注入時鐘、決定性 `poll_once()`、共同輪次與磁碟重建測試。主要改善空間是縮小呼叫者必須理解的 Interface，而不是增加檔案或抽象層。

| 優先度 | 改善項目 | 證據性質 | 主要價值 |
| --- | --- | --- | --- |
| P1 | audit writer 的輪次生命週期 | 已受控重現 | 避免長時間運轉時執行緒累積 |
| P2 | RS-WMT 解析快取與重複 I/O | 解析次數已受控量測，其餘為程式檢視 | 減少讀檔、解析與磁碟寫入 |
| P2 | 將監控啟動組裝移出 Tk | 設計分析 | UI 與 CLI 共用同一個深 Module |
| P2 | 結果狀態由共同輪次集中持有 | 設計分析，需較大遷移 | 縮小平台 Interface、降低回呼重入成本 |
| P2 | 來源證據與裁決使用明確資料型別 | 設計分析 | 集中同輪契約與錯誤檢查 |
| P3 | 精簡 snapshot 與 UI 更新 | 結構性成本，未量測現場延遲 | 避免每次刷新複製全部歷史 |

## 1. audit writer 缺少結束生命週期

位置：`B518 Log Solution/src/audit_records.py:78`、`:193`、`:205`；`B518 Log Solution/src/monitoring_round.py:939`。

每個 `RoundAuditStore` 建立一條 daemon writer。`_write_worker()` 永久阻塞於 `queue.get()`，沒有停止訊號或 close Interface；`flush()` 只等待既有寫入完成。`RoundCoordinator.start()` 切換至新輪次後，舊 writer 仍持有舊 store，且其錯誤回呼間接保留輪次物件。這是可由程式結構確認的資源累積，不只是命名或檔案大小問題。

受控重現：在獨立 Python 程序的暫存目錄建立 30 個 store，全部 `flush(3.0)` 成功，audit 執行緒從 0 增為 30；store 沒有 `close`。此測量不操作設備，也不修改現有 Session。

建議：讓寫入 Module 自己管理 worker 的存活期。可採用佇列空閒後退出、下次寫入再啟動的方式，現有 `SessionStore` 已有類似做法；或增加可重複呼叫的 `close(timeout)`，由輪次退役及 App 關閉流程負責排空與回收。二者擇一，不再疊加另一個只轉呼叫的 Module。

不能在 `collection_stopped` 就關閉 writer：依 ADR 0004，停止讀檔後仍可能有人工衝突操作與警報確認需要寫入。也不能以 `flush()` 等同釋放資源。路徑 lock registry `_LOCKS` 同樣只新增不移除，需在同一生命週期設計中評估共享鎖回收，不能任意刪除仍被使用的鎖。

驗證：連續完成與退役多輪後，worker 數不隨已結束輪次線性增長；待確認後的操作仍可重建；排空、寫入失敗及重複 close 有明確結果。保留稽核失敗不新增放行阻擋的既有產品決策。

## 2. 減少平台輪詢與 Session 的重複 I/O

位置：`B518 Log Solution/src/rswmt_source_adapter.py:223`、`:239`；`B518 Log Solution/src/b482_source_adapter.py:216`；`B518 Log Solution/src/log_monitoring.py:196`、`:267`；`B518 Log Solution/src/atlas_source_adapter.py:215`。

RS-WMT 已追蹤檔案 signature 與 final 是否送出，但每次 poll 都在判斷是否需要再次送出之前執行 `parse_rswmt_csv(path)`。受控案例以既有 `result_text()` 產生一份 CSV，在時間 0 與 6～14 秒共 poll 10 次：CSV 完全未變更，parser 被呼叫 10 次，final observation 只有 2 次（穩定前與穩定後）。

建議：在 Adapter Implementation 內以 `(path, signature)` 快取解析結果，將「檔案變更」與「五秒穩定期限到達」分開處理。穩定期限到達仍須送出事件，不能直接因 signature 相同而跳過整個 poll。對不完整或讀取失敗的檔案保留重試策略，不能無條件永久快取失敗。

另外三個可一起檢查的成本：

- B482 CaseInfo 有邏輯 offset，卻先 `read_text()` 讀取整份檔案再切片。可改成以 byte offset 讀取新增內容，搭配增量 decoder；須保留 CR／LF、部分寫入、UTF-8 跨 chunk 與截短／重建檔案的既有行為。
- `SessionStore.source()` 每次都重寫並 fsync metadata，即使來源路徑已在 set。只在首次加入來源時保存 metadata，可直接減少重複寫入；這比改變 audit 的 durability 承諾更低風險。
- Atlas active 搜尋每個位置各做兩次遞迴搜尋。先量測大型資料樹，再決定是否一次列舉或快取發現結果；快取要處理 active 目錄移動、刪除及重建。

這些是本機檔案依賴，優先用真實暫存檔測試跨 Seam 的結果，不需要引入檔案讀寫的外部抽象。尚未量測實際 ATE 的 CPU、磁碟量或端到端延遲，因此不宣稱改善百分比。

## 3. 將監控啟動組裝變成深 Module

位置：`B518 Log Solution/src/b518_log_solution.py:513`～`615`，尤其 `monitor_factory`、`view_holder` 與 profile／audit context 組裝。

UI 呼叫者目前必須知道平台必要路徑、可選路徑、來源位置、顯示位置、回呼轉換、monitor 建構時序、Session 設定與 audit 配置快照。`view_holder` 的兩階段初始化，是這些 Implementation 細節漏到呼叫者的具體例子。

建議：建立一個掌管「接受配置並開始本輪」的 Module，對外以 `start(profile)` 加上既有 snapshot／stop／人工操作 Interface 提供行為。registry、路徑解析、ConfiguredMonitor 組裝及配置快照放在其 Implementation，讓 Tk 只傳入所選配置、呈現可讀的錯誤與結果。時鐘、Session 根目錄、registry 等依賴在建構時接受。

這個 Module 只有在真正收納上述規則時才有 Depth；若只是逐項轉呼叫 `RoundCoordinator`，應避免新增該層。`ConfiguredMonitor` 的雙向來源／顯示映射則有真實用途，刪掉後複雜度會回到多個呼叫者，應保留這份 Leverage。

驗證：不建立 Tk 就能從版本化 profile 跑完整輪次；必要／選填路徑、非連續 mapping、啟動錯誤與配置快照使用同一個測試 Interface。保留真正 Tk 測試驗證排數標記、前景顯示、衝突視窗及配置編輯流程。

## 4. 結果狀態由共同輪次集中持有

位置：`B518 Log Solution/src/monitoring_round.py:18`、`:257`、`:349`、`:778`；`B518 Log Solution/src/log_monitoring.py:296`～`330`。

輪次持有期限、來源證據、衝突與放行狀態；平台 monitor 持有有效 `SlotResult` 與 terminal lock。平台先透過 callback 問輪次是否接受，輪次又可能呼叫 monitor 套用結果、引發另一個 callback。`RoundMonitor` 因此除了 poll 還要提供讀取結果、修改結果、發布輪次事件、更新設定與多種停止方法。

目前不是已證明的錯誤；其成本是新 Adapter 與 FakeMonitor 必須理解共同流程的內部協議，以及同步回呼重入／鎖取得順序。這削弱 Locality，也讓 Interface 比單純提供來源事實更複雜。

建議長期方向：平台 Adapter 回傳來源 observation 批次；共同輪次集中套用有效結果、terminal lock、期限、衝突與放行。保留各平台來源發現、啟動快照、穩定性與身份／批次證據的實際差異，不強迫所有平台使用同一個 parser。

建議的平台 Interface 方向是 `poll() -> observations`，配上確有必要的準備／收集結束生命週期。確切方法數須在遷移時由現有四種格式需求決定。既有 Atlas、B482、RS-WMT、sample-json 與測試 Adapter 已證明這是實際 Seam。

此項比啟動組裝重構風險大，適合在前三項完成後逐平台遷移。驗證保留未知同輪 FAIL、同輪衝突逐項處理、停止讀檔與放行分離、期限優先及 audit 重建。避免一次改掉所有 Adapter、UI 與紀錄格式。

## 5. 將來源證據與裁決契約明確化

位置：`B518 Log Solution/src/log_monitoring.py:28`、`:296`；`B518 Log Solution/src/monitoring_round.py:50`、`:702`、`:778`；各 Adapter 的 `evidence()`。

目前 `MonitorEvent.kind`、`status`、callback 的 accept／ignore／defer 與 `detail` key 大量使用字串。`detail` 宣告 `Dict[str, str]`，實際衝突事件卻包含巢狀 original／candidate 字典；`_receive_monitor_event()` 宣告回傳 None，候選分支實際回傳裁決字串。這是現有型別契約與 Implementation 的落差，現行執行不因此必然失敗。

建議：在既有 Adapter／輪次 Seam 引入明確 observation、來源證據與裁決型別；最低包含來源位置、status、SN、來源識別、可選來源測試時間與輪次連結證據。未知時間使用明確未知值，禁止用檔案時間或 App 觀察時間補造。顯示位置 mapping 集中轉換一次；audit 在序列化時轉成既有版本化欄位。

先集中核心欄位，平台額外證據仍保留可擴充資料，不要求建造龐大通用型別階層。新資料型別不能自行取代 ADR 0006 的同輪判定政策，也不能因為時間格式可解析就視為同輪。

驗證：不同平台證據契約共用行為案例；時間缺失、同輪矛盾、未知候選、未映射來源與 audit 序列化有明確預期。若增加型別檢查，先修正 Seam 的契約落差，再逐步擴大範圍。

## 6. snapshot 只攜帶目前狀態，事件按 cursor 讀取

位置：`B518 Log Solution/src/monitoring_round.py:349`、`:402`、`:1001`；`B518 Log Solution/src/b518_log_solution.py:630`、`:726`、`:812`。

`snapshot()` 每次複製全部 `_events`；UI 每 150ms 取得 snapshot，衝突與警報刷新也各自重新取得。輪次與 coordinator 還分別保存事件列表。成本隨單輪事件數增加，而 UI 主要只需要目前結果、衝突與警報。

建議：同一 UI tick 取得一個 snapshot，傳給各渲染方法；一般 snapshot 不帶完整事件歷史，透過既有事件 queue 或獨立事件 Interface 按 cursor 讀取。若保留 `events_since()`，利用遞增序號取得切片，而不是每次掃描全部列表。只有建立可靠的完整磁碟紀錄後，才考慮對記憶體事件做保留上限，避免丟掉稽核證據。

驗證：高事件量下測量 snapshot 配置與 Tk tick 時間；新輪次事件隔離、cursor 不重複／不漏事件，以及 KVM 狀態仍保持一致。目前僅確認結構性 O(E) 複製成本，沒有證明現場 UI 卡頓。

## 測試與遷移策略

現有 `RoundCoordinator` 加上 fake clock、真實暫存檔及磁碟重建測試，是適合保留的測試 Seam。部分 UI 測試用 `object.__new__(B518LogSolutionApp)`、手工補入大量屬性與 MagicMock，顯示啟動組裝與畫面綁得太緊；不是因此認定這些測試無效。

啟動 Module 建立後，把流程規則的重複驗證轉到新 Interface，取代相對應的 Implementation 耦合測試；保留圖形契約與真實 Tk 操作測試。每次遷移均以目前既有行為、相關新增情境及全套測試驗證，不以新增 Module 數量判定改善。

建議執行順序：先處理 audit worker，接著解析快取與來源去重，再移出啟動組裝；最後評估共同結果持有與型別契約遷移。snapshot 優化可以獨立進行，但應先加入量測。

## 本次驗證

- 工作樹起始乾淨；當日摘要 `PROJECT_SUMMARY_2026-10-06.md` 已存在，未重建或改寫既有跨日紀錄。
- 非 Tk 測試：`python3 scripts/run_tests.py` 指定其他 13 個 test modules，共 **156 tests，7.198 秒，通過**。
- 首次全套在 sandbox 中於 Tk 案例以 exit 134 中止，未把該次算成通過；在可存取 macOS 圖形工作階段的環境重跑相同入口，全套 **193 tests，19.879 秒，通過**。
- 兩個獨立受控探測確認：30 次 audit store 建立／flush 後仍有 30 條 audit worker；單份未變更 CSV 10 次 poll 導致 10 次 parse、2 次 final observation。
- 未執行現場 ATE／KVM、正式 bundle／目標機驗收，也未量測現場效能。本報告不改判 Ticket 17 尚未完成的驗收。

參考：`CONTEXT.md`、`docs/adr/0001`～`0006` 的既有決策，以及上列程式與測試。改善提案維持單工站整輪、配置獨立更新、新格式隨 App 發布、固定 KVM 契約及未知來源 FAIL 政策。
