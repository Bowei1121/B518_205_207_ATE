# 15：移除已完成遷移的 MVP 舊流程

**類型：**收斂

**What to build／工作內容與交付結果：**在新流程完整接通後移除無呼叫端的舊接口、重複共同規則及固定容量／七格假設，保留單一可維護流程。

**Blocked by／前置依賴：**

- [12：固定定位點與四種黑白程式標記](12-kvm-locators-and-state-marker.md)
- [13：完成可追查的輪次紀錄](13-round-audit-records.md)
- [14：以樣本 Adapter 驗證新格式擴充能力](14-sample-adapter-extensibility.md)

**Status：**implemented; local validation complete; fixed-baseline Standards／Spec review passed; hardware／target bundle acceptance deferred

## 驗收條件

- [x] 確認全部產品與工具呼叫端已遷移後才移除舊接口；保留平台解析測試、歷史偏好遷移及合法預設容量，沒有遺留 App／smoke 對舊共同接口的引用。
- [x] Atlas、B482、RS-WMT 保護與配置、容量、期限、衝突、警報及標記回歸通過；完整套件 185 項通過。
- [x] UI 只經 PlatformRegistry 建立 Adapter，並透過 RoundCoordinator 公開快照、事件、輪詢、Session 查閱／flush、衝突與警報操作；未讀取具體 Adapter 結果、候選或完成旗標。
- [x] 移除 App 的七格 fallback、第二套路徑／期限矩陣、BT 格式切換與重複期限設定入口；沒有新舊兩套共同期限或平台專屬放行規則。
- [x] Source entry、延遲平台註冊、建置入口語法、assets 與 bundle checker 測試通過；在目前主機只完成靜態入口／引用／資源檢查，目標 macOS bundle 未建置並明確列為環境限制。

## 驗證方式

搜尋舊呼叫與固定假設，執行完整行為回歸及打包引用檢查；驗證每項移除有遷移依據。

**規格驗收對照：**AC-01～AC-24、AC-27、AC-28 的整合回歸（上位機部分由 16）

## 實際交付與呼叫端遷移對照

| 舊接口／規則 | 實際呼叫端 | 新接口 | 遷移／測試 | 保留或移除理由 |
|---|---|---|---|---|
| `B518LogSolutionApp.monitor` 與 App 自行判定 adapter 是否存在 | 主畫面 controls、事件處理、profile 容量顯示及舊 smoke | `RoundCoordinator.snapshot()`、`poll_once()`、`stop()`；狀態來自共同輪次快照 | UI 測試與 deadline、Atlas、B482、sample Tk smoke | 移除直接持有的平行 monitor／finished 狀態，避免 UI 建立第二套完成判定 |
| `RoundCoordinator.monitor`／`MonitoringRound.monitor` 對外暴露 Adapter；`ConfiguredMonitor.emit_display_event()` 舊別名 | replay 工具、共同輪次整合測試、Session 查閱；別名全庫搜尋無呼叫端 | coordinator 的 `poll_once()`、`snapshot()`、`session_path`、`flush_session()`；事件使用 `publish_round_event()` | registry、round、audit tests；replay 工具及 Session 讀取測試；`rg emit_display_event` 確認無引用 | 移除跨模組存取 Adapter 及無呼叫端轉發別名；有必要的 Session 邊界功能改由共同公開接口提供 |
| App `paths`／`timeouts` 矩陣、`bt_format`、`STATION_SLOTS`、`slot_count()` 與 `DEFAULT_TIMEOUTS` fallback；重複「監控設定」分頁 | 操作員選擇、開始監控、舊偏好、工程師設定 UI 與舊 UI 測試 | `MachineProfileStore` 版本化 profile、`PlatformRegistry` 的 path/capability contract、工程師草稿編輯／套用 | profile editor、保存失敗、取消、匯入／重新載入、重啟與失效選擇測試 | 移除日常第二設定流程及固定七格 fallback；保留 DFU 7、FCT 6、B482 BT 4 作舊偏好遷移後合法預設，不當作 App fallback |
| Smoke 直接替換 App Atlas 建構器或輪詢 `app.monitor` | deadline、state marker、Atlas、B482、sample 與 audit Tk 工具 | 受控測試在 registry factory seam 注入來源；流程以 `RoundCoordinator` 公開接口觀察 | `smoke_deadline_app.py`、`smoke_state_marker_app.py`、`smoke_audit_records_app.py`、`smoke_atlas_app.py`、`smoke_b482_app.py`、`smoke_sample_adapter_app.py` | 工具仍可在 Adapter 建立 seam 注入資料／寫入故障，但不透過 App 公開舊屬性或以 adapter finished 判放行 |
| Replay 工具直接建立平台 Monitor，並呼叫 adapter 私有輪次入口 | Atlas/B482/RS-WMT 基準回放 | `DEFAULT_PLATFORM_REGISTRY.create_monitor()`、`RoundCoordinator.poll_once()` | `replay_baseline_samples.py`、`replay_rswmt.py`；完整 anonymized baseline replay | 統一驗證註冊、時計注入及共同輪次；解析器單元測試仍直接覆蓋平台格式 |
| 共同輪次 smoke 從 `events.log` 尋找警報／候選順序 | Ticket 09/11 回放工具 | Ticket 13 `audit.jsonl` 與 `read_round_audit()` | deadline App smoke 比對 alarm → collection stop → acknowledgement → release | 共同稽核事件以版本化 audit 為權威；舊 Session 檔案仍保留相容查閱 |
| 平台格式解析、來源穩定性、歷史快照與來源診斷 | Atlas／B482／RS-WMT Adapter 與 parser tests | 現有 platform Adapter／registry contract | 三平台 Adapter、RoundCoordinator 與 baseline replay 回歸 | 保留：平台日期／批次、可信 SN、B482 零起算 Thread、半筆緩衝、檔案穩定性及平台 NOTEST／FAIL 差異不是重複共同期限 |

平台註冊的延遲 Adapter import、profile path schema 與 `assets/` bundle data 引用都保留。未知平台仍由 registry/profile validation 拒絕。沒有刪除 root 下的 JetKVM／Arduino prototypes、原始樣本、歷史 evidence 或平台 Adapter。`tools/smoke_audit_records_app.py` 在 registry factory 測試 seam 擷取 Adapter，只為刻意延遲底層 Session 寫入；App 正常結果、衝突、期限與放行仍由 RoundCoordinator 決定。

## 驗證紀錄

- 固定修改前基準：`241dcdffb2e8b0450ff701977b9f4b862ffb43a4`。分支：`codex/ticket-15`，由乾淨 `B518-Log-Solution` 建立。實作提交：`0d239e7`；公開 Session API 測試遷移：`f16f313`；兩次均推送到 Gitea 與 GitHub push URL。
- TDD 行為測試先驗證 coordinator Session path/flush 公開邊界，及平台 registry replay clocks 保留；缺少接口時測試失敗，新增實作後轉綠。移除舊設定表單測試改由 profile editor、profile migration、operator restart 與 round snapshot 測試保護，不只以方法／檔案不存在作測試。
- `python3 scripts/run_tests.py test_log_solution_ui test_platform_registry test_monitoring_round test_audit_records test_configured_monitor test_atlas_source_adapter test_rswmt_monitoring`：120 tests 通過。最後公開 Session API 遷移後，`python3 scripts/run_tests.py test_monitoring_round test_platform_registry`：42 tests 通過。
- `python3 scripts/run_tests.py`：185 tests 通過（包含 Atlas／B482／RS-WMT／sample-json Adapter、配置映射、期限、候選／警報、KVM marker 與 bundle verifier）。
- Spec 複審修正：完成／人工停止事件後保留已結束輪次的 profile snapshot，避免下一次 UI 重繪採用編輯中的新容量；擴充 Tk 行為測試至終態事件處理後。移除全庫無呼叫端的 `emit_display_event()` 舊別名；相關單檔測試與複審結果追加於下方。
- 回歸先以紅燈重現：profile 容量由 3 編輯成 12、目前輪次 STOPPED 事件處理後，UI 曾回退顯示 12；修正後終態仍保留容量 3。`python3 scripts/run_tests.py test_log_solution_ui.LogSolutionUiTests.test_running_round_keeps_its_capacity_and_mapping_after_profile_update test_configured_monitor`：6 tests 通過。Atlas 衝突 Tk 測試 teardown 增加有界 Session/audit flush；隔離重跑該案例與容量快照案例 2 tests 通過。修正後完整 `python3 scripts/run_tests.py`：185 tests 通過。第一次全套測試遇到該 Tk 測試暫存 Session 目錄清理競態，單獨重跑通過；補 flush 後再跑完整套件全綠。
- 受控資料回放：`python3 tools/replay_baseline_samples.py --caseinfo-date 2026-08-21 testdata/anonymized-baseline` 通過，Atlas DFU／FCT PASS、B482 TestData 4 槽平台結果、RS-WMT 4 槽 PASS；`python3 tools/replay_rswmt.py 'testdata/anonymized-baseline/B518 BT/2026-09-11_05-45-44'` 通過。工具將輸入複製至暫存目錄，原始匿名化 fixtures 保持唯讀。
- Tk 受控回放：`python3 tools/smoke_deadline_app.py` 通過全空／未放滿／個別 timeout／人工停止、round alarm 及兩種 alarm／conflict 選擇順序；Session audit 證明 alarm → collection stop → acknowledgement → release。
- Tk 受控回放：`python3 tools/smoke_atlas_app.py` 通過 DFU／FCT；`python3 tools/smoke_b482_app.py` 通過四個 B482 NOTEST；`python3 tools/smoke_audit_records_app.py` 通過 Atlas PASS 與獨立磁碟重建、背景 Session 延遲及 App close flush；`B518_SMOKE_EVIDENCE_DIR='docs/refactoring/evidence/ticket-15' python3 tools/smoke_state_marker_app.py` 與 `... python3 tools/smoke_sample_adapter_app.py` 產生 Ticket 15 專用截圖及 JSON 驗證報告。
- 受控 UI 環境：macOS 15.7.9、x86_64、Python 3.8.10、Tk scaling 約 1.0、螢幕 1440×900 Tk units。marker smoke 主窗 376×682 logical／752×1420 captured physical pixels；sample round 主窗 376×467 logical／752×990 captured pixels；conflict window 1640×916 pixels，alarm window 920×496 pixels，均未遮住頂部辨識帶。證據位於 `B518 Log Solution/docs/refactoring/evidence/ticket-15/`。這些是本機 Tk／Quartz 截圖，非實際 KVM frame。
- 打包／資源檢查：source entry import 成功；registry 發現 Atlas、B482、RS-WMT、sample-json 四個已註冊 Adapter；`assets/` 及目前存在的 `logo_foxlink_b.png` 可用，正式 `foxlink_logo.png` 是 README 已說明的選配，公司圖標缺少時 App 使用文字 fallback；三個既有 zsh build script `zsh -n` 通過；`scripts/verify_macos_bundle.py` 的完整 bundle 契約測試包含於 185 tests。未實際建立新 bundle。
- `python3 scripts/check_macos_build_python.py` 在本機依設計拒絕：本機為 Python 3.8.10／x86_64；build targets 要求 macOS 10.15 x86_64 + Python 3.12，或 Apple Silicon arm64 + Python 3.12 及 macOS 15／26。建置腳本會遞增 VERSION 並清除其 target build/dist，故不在不相容主機執行。目標系統／架構 bundle、正式發布 App、實機／KVM／治具驗收未執行，保持待確認；不以本機 source/Tk 結果代替。
- Repository 無 mypy、pyright、pyproject type-check、setup.cfg 或 tox 型別檢查設定；沒有宣稱 `py_compile` 是型別檢查。實際 KVM 驗收仍按既有決策留在 Ticket 12 AC 1／Ticket 13 AC 4 未勾選；上位機共同整合留給 Ticket 16、發布留給 Ticket 17、未知同輪來源政策留給 Ticket 18。
- 固定基準 `241dcdffb2e8b0450ff701977b9f4b862ffb43a4` 的 Standards／Spec 審查發現均已修正：保留終態 profile snapshot、移除無呼叫端舊別名、更新測試接口文字；雙軸複審無未解決問題。Standards 無硬性標準違規；Session path／flush 邊界轉接被確認為有理由的共同公開界面。Spec 確認容量快照及舊接口清理符合 Ticket。審查涵蓋此基準至 `493c4ee` 的完整變更。
- Ticket 15 commits：`0d239e7`（遷移與清理）、`f16f313`（公開 Session API 測試）、`8f89d86`（交付／證據）、`07ee42d`（終態容量快照與舊別名清理）、`493c4ee`（Tk teardown flush 與測試接口紀錄更正）；各批均推送至 Gitea 與 GitHub。最終合併與遠端清理尚待完成後補記。

## 保留決策、待確認事項與限制

不得以清理名義刪除未知來源證據、默認採用政策或宣稱 18 完成；清理在移植及驗證後進行。

行為測試沿用 Ticket 01 於 2026-09-30 確認的共同輪次公開接口及代表案例，並透過 Ticket 02～13 已建立的 `RoundCoordinator`／`MonitoringRound` 公開 `start()`、`poll_once()`、`snapshot()`、事件、衝突選擇、警報確認、停止及稽核查閱／flush 操作驗證；本票不重新要求批准既有測試接口。未知同輪來源能否人工採用仍由 Ticket 18 決定，任何本票的已完成部分都不能抵銷該未決分支。

## 執行與追蹤

依 2026-09-30 使用者確認的任務清單建立。以 REFACTOR_SPEC、CONTEXT 與 ADR 0001～0005 為基準，沿用測試配置、平台資料來源、監控輪次、桌面介面四模組與 Python／Tk／既有 macOS 打包方式。只在前置完成且本票關鍵待決及外部條件已滿足時轉為 ready-for-agent；需要人類決策的任務不得逕自轉為可直接實作。

執行時逐項記錄實際交付、驗證環境與結果、仍未決／待驗範圍及相關提交。未執行的驗收維持未勾選；本文件建立不代表 App 已完成重構。
