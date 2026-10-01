# 06：以專案＋機型選擇配置並啟動一輪

**類型：**新增

**What to build／工作內容與交付結果：**操作員只選專案與機型，由工程師預設配置決定平台、容量、路徑、映射及期限；先用 Atlas 打通完整一輪並固定開始時配置。

**Blocked by／前置依賴：**

- [03：搬移 Atlas 資料來源並保護完整監控流程](03-atlas-source-adapter.md)

**Status：**complete（六項 Ticket 06 驗收、測試及 Standards／Spec 複審完成；已一般合併、雙遠端同步並安全清理專用分支）

## 驗收條件

- [x] 以專案＋DFU／FCT／BT 機型選擇有效配置；平台不是操作員日常第三個選項。
- [x] 重新啟動可恢復有效選擇，舊偏好有明確遷移及失敗處理。
- [x] 配置有版本；未知平台、缺欄位、非法容量、重複／越界映射、非正整數逾時與不相容版本被拒絕。
- [x] 真正開始前指出空白、缺少或不可讀路徑，不把空白當目前目錄。
- [x] 本輪綁定配置快照；後續配置變更不改進行中的輪次。
- [x] Atlas 完成選擇至結果的完整流程；其他 Adapter 依相同契約接入。（本機 Tk App 受控回放通過；使用者於 2026-10-01 明確接受此方式作為 Ticket 06 AC 6。目標設備／發布 App 狀況分開記錄。）

## 驗證方式

配置錯誤矩陣、啟動前路徑檢查、重新啟動與運行中修改配置；完成一次 Atlas 操作。

**規格驗收對照：**AC-01（快照）、AC-03

## 保留決策、待確認事項與限制

版本格式與舊偏好遷移方式是需記錄及測試的工程選擇；同專案＋機型的設備差異由工程師部署適用配置，不增加操作員欄位。

所有行為測試須依 01 的接口確認結果落實；本次批准任務清單不代表測試接口已獲批准。未知同輪來源能否人工採用仍由 18 決定，任何本票的已完成部分都不能抵銷該未決分支。

## 執行與追蹤

依 2026-09-30 使用者確認的任務清單建立。以 REFACTOR_SPEC、CONTEXT 與 ADR 0001～0005 為基準，沿用測試配置、平台資料來源、監控輪次、桌面介面四模組與 Python／Tk／既有 macOS 打包方式。只在前置完成且本票關鍵待決及外部條件已滿足時轉為 ready-for-agent；需要人類決策的任務不得逕自轉為可直接實作。

執行時逐項記錄實際交付、驗證環境與結果、仍未決／待驗範圍及相關提交。未執行的驗收維持未勾選；本文件建立不代表 App 已完成重構。

## 執行紀錄｜2026-10-01

### 前置與基準

- Git 根目錄為本文件所在的 `B518 Log Solution` repo，起始分支 `B518-Log-Solution`，Ticket 06 固定基準 commit 為 `9de46477629bbea1afffe26bb21238033135bf8a`。Ticket 01 已確認以公開輪詢、可注入時鐘、事件及暫存來源回放測試；實作沿用 `RoundCoordinator`、監控快照／事件及可注入 clock seam。
- Ticket 03 的 Adapter、共同輪次入口及本機 App 受控 Atlas 流程已在起始 commit 中；因此必要程式／接口已可供本票接續。Ticket 03 文件仍為 `in-progress`，真實 active tree 與目標機／發布 App 兩項驗收仍未勾選。2026-10-01 的延期決策只記錄為 Ticket 03 未完成項目延期，不視為通過，也不沿用為 Ticket 06 的驗收豁免；Ticket 06 AC 6 另依使用者當日明確決策以本機受控 Tk App 流程驗收。
- 實作依 `CONTEXT.md`、`REFACTOR_SPEC.md`、ADR 0001～0005 及 Ticket 01 的測試接口進行。版本選擇工程上採整數 `schema_version: 1`；舊偏好遷移成明確的專案＋機型配置，只把舊 BT 路徑／期限放入當時選取的 BT 平台配置；遷移不覆寫舊檔，損壞或未知版本明確報錯且保留原設定。此選擇由配置往返、遷移及失敗案例測試。
- Ticket 18 的未知同輪來源人工採用政策保持未決；本票未改定該政策。

### 交付與驗證

- 新增版本化機型配置、操作員專案＋DFU／FCT／BT 選擇、工程師配置欄位、選擇保存／恢復、舊偏好遷移／錯誤保留、路徑 preflight、來源至畫面位置映射與本輪 profile snapshot。操作員畫面不提供平台第三選項；平台由工程師配置決定。
- 三種平台監控都接收相同的配置容量、映射及期限契約。容量超過現有 Adapter／畫面能力時，配置可被辨識但開始會明確拒絕，不宣稱已支援未完成的容量／版面工作。整輪期限固定於開始時，期限到達前先停止來源讀取；保留已完成結果，將執行中位置標記 TIMEOUT、未開始位置標記 NOTEST，只產生一次待確認警報。開始等待逾期也將未開始位置標記 NOTEST。
- Ticket 06 AC 1～6 均通過。Atlas 本機 Tk App 經開始按鈕與匿名化受控來源完成 DFU／FCT 各一輪；B482 TestData App 全流程、有效 B482 profile 下 CaseInfo 非 identity 映射及 RS-WMT 共同輪次測試通過。使用者於 2026-10-01 明確接受本機受控 Tk App 流程作為 Ticket 06 AC 6；目標設備／發布 App 驗收仍分開列為未執行限制。
- 環境：macOS 15.7.9、Intel x86_64、Python 3.8.10。原始實機輸入維持唯讀；Atlas/B482 App 驗證用隔離目錄與匿名化受控複本，未更動原始資料。

| 驗證命令 | 結果 |
| --- | --- |
| `python3 scripts/run_tests.py` | 114 tests 全數通過；含設定錯誤矩陣、啟動前路徑檢查、選擇保存／恢復及監控器期限傳遞、舊偏好遷移／失敗且保留原檔、輪次快照、輪次／個別期限、B482 CaseInfo 映射及 Atlas App 整輪行為。 |
| `python3 tools/smoke_atlas_app.py` | 通過；本機真實 Tk App 受控回放，DFU PASS（另 6 NOTEST）、FCT PASS（另 5 NOTEST），兩輪完成；測試期間修改配置仍使用開始時映射快照。 |
| `python3 tools/smoke_b482_app.py` | 通過；本機真實 Tk App 受控 TestData 回放，4 個平台 NOTEST 結果可見且共同輪次完成。 |
| `python3 -m compileall -q src tests tools scripts` | 通過語法／位元碼編譯檢查；不是型別檢查。 |
| `git diff --check` | 通過。 |

專案未配置 mypy、pyright 或其他靜態型別檢查工具，未宣稱型別檢查通過。未執行 Apple Silicon 目標機、發布 App、產線 KVM／上位機或真實 Atlas active tree 驗收；這些是分開記錄的環境限制。Ticket 03 本身仍為 `in-progress`，其 active tree 與目標設備驗收仍未勾選，也未被本票變更或視為通過；Ticket 03 所需程式與共同接口已存在於本票基準。

### 審查

- `$code-review` 以固定基準 `9de46477629bbea1afffe26bb21238033135bf8a` 審閱 Ticket 06 完整差異，執行 Standards 與 Spec 雙軸審查。初次 Spec 發現整輪期限只保存未套用；已補上所有 Adapter 的期限執行、開始時間固定、到期停讀與混合結果處理，並加入輪次期限測試。初次 B482 Thread 映射疑慮經檢查後撤回：CaseInfo Thread 1–4 與 TestData Thread 0–3 均正規化為 logical slot 1–4，另補有效配置與 CaseInfo 非 identity 映射測試。Spec 另指出開始等待期限的未開始位置應為 NOTEST，已修正並以測試覆蓋。
- Standards 最終複審未發現可確認的規範違反。平台／機型判斷分散的 Repeated Switches 僅是低信心維護觀察；條件分別服務遷移、UI 與監控器派送，新增註冊表會是推測性重構，故不列為未解審查問題。
- Spec 最終複審確認整輪期限載入、舊偏好遷移失敗處理、B482 映射及受控 App 證據符合紀錄；先前的實質發現均已修正並補測，B482 映射疑慮撤回。最終 Spec 無未解 code finding；AC 6 依使用者 2026-10-01 明確決策勾選。

### 提交與遠端

- 起始基準：`9de46477629bbea1afffe26bb21238033135bf8a`。
- `3453d107fd8a58276652536e849b5ee14b5a5781` — `feat: select versioned project machine profiles`。
- `a1656db7e2ed209d8c7555c0a2f4e70b62b60199` — `fix: enforce configured round timeout`。
- `2d7f0f70b22fa9f242d763a6e523d8d9eb880db0` — `fix: mark untouched slots notest on start expiry`。
- `4cfa54139d1a71c40f3da932af5844a44806e556` — `fix: restore profile deadlines and guard migration`。
- 分支 `codex/ticket-06` 首次 push 已設定追蹤；Gitea 與 GitHub 兩個既有 push 目的地均成功更新至 `4cfa541`。Ticket 執行紀錄與本日專案摘要隨後以文件提交補記。

### 合併與外部限制

Ticket 03 仍保持 `in-progress`，其未勾選驗收沒有改寫為通過。Ticket 03 所需程式與共同接口已在 Ticket 06 固定基準中；使用者另於 2026-10-01 明確確認本機受控 Atlas App 流程足以滿足 Ticket 06 AC 6，因此本票以自己的測試與驗收完成 AC 6，沒有沿用 Ticket 03 的延期豁免。目標設備、發布 App、KVM／上位機及真實 active tree 限制仍留在驗收紀錄中，且不改寫 Ticket 03 狀態。

### 合併完成紀錄｜2026-10-01

- 合併前 `B518-Log-Solution` 工作樹乾淨，並確認已納入 Gitea 與 GitHub 上最新的目標分支提交 `9de46477629bbea1afffe26bb21238033135bf8a`。
- 以一般非快轉合併 `git merge --no-ff --no-edit codex/ticket-06` 完成；合併 commit：`1977bca94d34f6f2955dc1e4ec438964514d036b`。
- 合併後 `python3 scripts/run_tests.py` 通過 114 tests；`python3 tools/smoke_atlas_app.py`、`python3 tools/smoke_b482_app.py`、`python3 -m compileall -q src tests tools scripts` 及 `git diff --check` 均通過。
- 合併 commit 已推送至兩個既有 push 目的地：Gitea `http://10.64.76.34:3000/8362/B518-205_207_ATE.git` 與 GitHub `git@github.com:Bowei1121/B518_205_207_ATE.git`；逐一查詢確認兩端 `B518-Log-Solution` 均為 `1977bca94d34f6f2955dc1e4ec438964514d036b`。
- 確認兩端合併結果同步後，已從 Gitea 與 GitHub 刪除遠端 `codex/ticket-06`，兩端查詢均不再列出該 ref；再以 `git branch -d codex/ticket-06` 安全刪除本地分支。最後工作樹位於 `B518-Log-Solution` 且乾淨。
