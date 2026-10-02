# 07：工程師畫面編輯、匯出及部署配置

**類型：**新增

**What to build／工作內容與交付結果：**工程師使用進階畫面編輯草稿、驗證、套用、取消、匯入及匯出，部署後操作員選用配置。

**Blocked by／前置依賴：**

- [06：以專案＋機型選擇配置並啟動一輪](06-project-machine-profile-selection.md)

**Status：**in-progress（前置程式已核對；驗收、雙軸審查與合併紀錄進行中）

## 驗收條件

- [ ] 編輯欄位涵蓋專案、機型、平台、容量、路徑、映射及三種期限，驗證結果可讀。
- [ ] 匯出再匯入恢復等價配置，取消或匯入失敗保留完整原配置，不留下半套設定。
- [ ] 編輯／匯入結構檢查與部署電腦的實際路徑可讀性檢查分開。
- [ ] 已支援平台的配置可更新並重新載入，不更換 App 二進位；當前輪次仍使用原快照。
- [ ] 配置製作、匯出、部署、選擇到監控的完整流程有驗證證據。

## 驗證方式

配置接口驗證等價及原值保留；Tk 操作草稿與部署後啟動。

**規格驗收對照：**AC-01～AC-03（配置操作部分）

## 保留決策、待確認事項與限制

不擴張為帳號、密碼或身分權限功能。容量／映射與期限的完整行為分別由 08、09、11 驗收；本票不以欄位存在宣稱其全部完成。

所有行為測試須依 01 的接口確認結果落實；本次批准任務清單不代表測試接口已獲批准。未知同輪來源能否人工採用仍由 18 決定，任何本票的已完成部分都不能抵銷該未決分支。

## 執行與追蹤

依 2026-09-30 使用者確認的任務清單建立。以 REFACTOR_SPEC、CONTEXT 與 ADR 0001～0005 為基準，沿用測試配置、平台資料來源、監控輪次、桌面介面四模組與 Python／Tk／既有 macOS 打包方式。只在前置完成且本票關鍵待決及外部條件已滿足時轉為 ready-for-agent；需要人類決策的任務不得逕自轉為可直接實作。

執行時逐項記錄實際交付、驗證環境與結果、仍未決／待驗範圍及相關提交。未執行的驗收維持未勾選；本文件建立不代表 App 已完成重構。

## 執行紀錄｜2026-10-02

### 前置與基準

- Git 根目錄為本 repo；從 `B518-Log-Solution` 的 `0fd33075223a88cce2d76585d38d57d9a8e1407d` 建立 `codex/ticket-07`。建立前確認本地及 Gitea／GitHub 最新目標 ref 均為該 commit，兩端均沒有既有 `codex/ticket-07`。工作樹唯一既有未追蹤檔是本日專案摘要，已保留並於本票文件批次一併保存。
- Ticket 06 的版本化 `MachineProfile`／`ProfileCatalog`、原子偏好保存、操作員 project＋machine 選擇、部署路徑 preflight、開始時 session profile snapshot，以及 Atlas/B482/RW-SMT 共用輪次入口均存在於基準中。Ticket 06 六項驗收與使用者對 AC 6 的本機受控 App 決策依其自身紀錄確認；此決策未作為 Ticket 07 驗收豁免。
- Ticket 03 的 Adapter 與共同輪次必要程式已納入基準；Ticket 03 仍為 `in-progress`，其真實 active tree 與目標設備／發布 App 驗收仍未勾選。本票不把其延期當成通過，也不修改 Ticket 03 狀態。Ticket 18 未知同輪來源政策未觸及。
- 依 Ticket 01 已確認接口，以配置 JSON 公開契約與實際 Tk 操作測試：配置錯誤由 `ProfileCatalog.from_dict`／`validate_profile` 觀察；共同輪次仍沿用 `RoundCoordinator` 的公開 snapshot/event 邊界與既有可控來源 App 回放。
- 延用 Ticket 06 的 `schema_version: 1`。工程師匯出／匯入整份版本化配置目錄；匯入先完整解析驗證，原子保存成功後才替換 App 目錄。路徑存在性不屬匯入時的結構條件，由部署端開始監控前檢查。來源／顯示映射均限制於配置容量內，避免工程師建立不可部署映射。

### 實際交付

- 增加工程師配置頁，可載入既有配置草稿，編輯／建立專案＋DFU、FCT、BT 機型配置的支援平台、容量、三類路徑、來源到顯示映射，以及開始／測試／整輪秒數期限；欄位錯誤在頁面狀態區顯示。草稿取消不更動有效目錄。
- 配置目錄可輸出 UTF-8 JSON 並匯入等價版本；格式、版本、必要欄位、平台／機型相容性、容量、重複／越界映射及期限驗證失敗均保留原配置。保存使用同目錄臨時檔與原子替換；磁碟寫入失敗不更動 App 有效目錄或既有偏好檔。
- 結構檢查接受其他電腦上的路徑文字；開始前仍由既有 preflight 拒絕空白、缺少或不可讀路徑。設定重新載入保留仍有效的操作員選擇；選擇失效時回報明確錯誤，不靜默啟動其他配置。
- 編輯器可在輪次進行中套用未來配置；不切換鎖定中的操作員選擇，也不重繪或重置目前結果。監控建立時使用的 profile、路徑、映射及期限仍由本輪快照決定。
- 更新 Atlas App 受控流程工具，實際走過工程師建立配置、匯出、在獨立偏好目錄匯入部署、操作員選擇、開始、受控 Log 回放、顯示結果；監控期間經 App 編輯器套用映射更新，檢查 session 仍留存開始時映射。

### 驗證紀錄

- 環境：macOS 15.7.9、Intel `x86_64`、Python 3.8.10。原始實機資料保持唯讀；App 受控回放只讀匿名化樣本並複製至臨時目錄。
- `python3 scripts/run_tests.py test_machine_profiles`：13 tests 通過，涵蓋 schema／JSON 等價往返、錯誤矩陣、路徑結構與部署檢查分離、重複 profile／映射、失敗匯入及寫入失敗保留原檔、既有偏好遷移與錯誤處理。
- `python3 scripts/run_tests.py test_log_solution_ui`：32 tests 通過，含工程師載入／取消／套用、保存失敗保留、隔離部署匯入／匯出／重新載入，以及既有 operator、preflight、輪次與 UI 回歸。
- `python3 tools/smoke_atlas_app.py`：通過；DFU PASS（另 6 NOTEST）、FCT PASS（另 5 NOTEST），兩輪完成且結果可取用；工程師設定匯出部署與進行中快照檢查均通過。
- `python3 tools/smoke_b482_app.py`：通過；4 個平台 NOTEST 結果顯示並完成共同輪次。
- 專案沒有 mypy、pyright 或其他型別檢查設定；不以 Python 編譯檢查替代型別檢查。完整測試套件、最後 Standards／Spec 審查及其後結果待執行後記錄。
- 未執行目標設備、正式發布 App、產線 KVM／上位機驗收；本機受控部署流程的證據不代表上述實機驗收。上述未執行範圍依 Ticket 及 REFACTOR_SPEC 的待驗原則分開保留。

### 提交

- 基準：`0fd33075223a88cce2d76585d38d57d9a8e1407d`。
- `bbba326` — `feat: add portable profile document import export`。
- `d94100f` — `fix: replace imported profile catalogs atomically`。
- `f7e5c87` — `feat: add engineer profile editor and deployment flow`。
- `f9f7463` — `feat: validate and apply deployed profile drafts`。
- `6a8786f` — `test: cover duplicate and out of range profiles`。
- 以上程式批次均在相關單檔或受控 App 驗證後提交，並 push 到 Gitea 與 GitHub 上的同名專用分支。最終遠端核對、合併、合併後驗證與分支清理待完成後追加。
