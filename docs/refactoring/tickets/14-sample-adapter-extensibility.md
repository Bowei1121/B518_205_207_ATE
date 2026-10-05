# 14：以樣本 Adapter 驗證新格式擴充能力

**類型：**架構驗證

**What to build／工作內容與交付結果：**用受控新格式樣本完成配置選擇、共同輪次、人工流程及既有畫面的完整一輪，證明擴充邊界。

**Blocked by／前置依賴：**

- [08：配置容量與位置映射，完成十格／兩排顯示](08-capacity-mapping-kvm-layout.md)
- [11：整輪上限、一次警報與確認後放行](11-round-deadline-alarm-release.md)

**Status：**實作與本機驗收完成；實機類驗收依使用者決策暫緩

## 驗收條件

- [x] 新格式透過平台 Adapter、平台註冊及匿名樣本／測試接入；操作員仍選專案＋機型。為提供可擴充 seam，另將原有三平台能力描述、工廠建立及路徑前置檢查集中至泛用 `PlatformRegistry`，並將 App／配置驗證改接該 seam；樣本格式本身沒有平台專屬 Tk 分支。
- [x] `sample-json` 的活動、final 與來源證據經 `ConfiguredMonitor`、`RoundCoordinator` 及原有 Tk 畫面；主視窗未新增平台特有 UI 或輪次分支。受控 App 已從工程師編輯器建立／保存 SAMPLE/FCT 配置，再以操作員專案／機型選擇啟動。
- [x] 使用共同開始等待、個別期限、整輪期限／警報、衝突候選、人工選擇及放行流程；Adapter 不定義期限或放行。畫面回放中 position 3 因個別上限成為 TIMEOUT，整輪警報與衝突仍由共同流程管理。
- [x] Atlas、B482、RS-WMT 及新 Adapter 的相關回歸通過；三平台均由同一註冊／能力契約建立，不改變既有平台解析器。
- [x] 完成 Tk 受控完整輪次及從新磁碟讀取實例重建稽核紀錄。匿名化截圖、配置／來源樣本、環境與命令見下方交付紀錄。

## 驗證方式

加入受控樣本格式並經共同測試接口及 App 操作完成一輪，比對變更責任邊界。

**規格驗收對照：**AC-28

## 保留決策、待確認事項與限制

受控樣本用於架構證明，不宣稱支援未有實機樣本的新平台；新格式仍隨 App 發布，不實作動態外掛。

所有行為測試沿用 Ticket 01 已確認的公開接口。未知同輪來源能否人工採用仍由 18 決定，任何本票的已完成部分都不能抵銷該未決分支。

## 執行與追蹤

依 2026-09-30 使用者確認的任務清單建立。以 REFACTOR_SPEC、CONTEXT 與 ADR 0001～0005 為基準，沿用測試配置、平台資料來源、監控輪次、桌面介面四模組與 Python／Tk／既有 macOS 打包方式。只在前置完成且本票關鍵待決及外部條件已滿足時轉為 ready-for-agent；需要人類決策的任務不得逕自轉為可直接實作。

## 實際交付與設計決策

- 泛用前置調整：新增 `B518 Log Solution/src/platform_registry.py`，由單一註冊表描述平台支援機型、來源位置、必要／選用路徑、欄位標籤及 Adapter 工廠。`machine_profiles.py`、App 的路徑檢查、工程師平台選單及監控器建立均讀取同一能力資料；新增平台仍需隨 App 編譯，不支援動態載入。
- 樣本格式接入：新增 `sample_json_monitor.py`、`tests/test_platform_registry.py`、`testdata/ticket-14/` 匿名樣本及 `tools/smoke_sample_adapter_app.py`。App 只呼叫註冊表的泛用介面。樣本的格式／批次契約、範例及重現方式見 [樣本 Adapter 開發說明](../SAMPLE_ADAPTER_GUIDE.md) 與 [樣本格式說明](../../../B518%20Log%20Solution/testdata/ticket-14/README.md)。
- `sample-json/v1` 使用以換行界定完整記錄的 JSONL；啟動時快照前置檔案長度，不重播舊資料；未換行的尾端半筆暫不接受。活動記錄只在有明確 `activity` 證據時產生 TESTING。final-only 記錄不推造活動／起始時間。`source_time`、SN、`batch_id` 缺漏一律未知；只有格式明確提供 `batch_id` 且來源位置相符時才形成可比較的批次證據。App `round_id`、檔名、路徑、複製時間均不充作同輪證據。
- 格式有效位置為 1–20，這是 parser fixture 能讀取的來源編號範圍，不宣稱硬體容量。樣本 profile 使用容量 3 的非恆等映射：來源 20→顯示 1、4→2、7→3；有效但未映射的來源只產生 `unmapped_source` 證據。非法 JSON／欄位／狀態發出 warning 事件，不形成結果。資料排序以來源時間（缺值排序在前）、來源位置與記錄內容的穩定鍵決定，不依掃描／執行緒先後。
- 受控完整輪次：工程師畫面建立並保存 SAMPLE/FCT 設定；操作員選 SAMPLE＋FCT 後啟動；注入活動與矛盾 final；既有非阻塞衝突 UI 與整輪警報分開確認；使用共用「採用新結果」操作；共同期限將未完成位置裁為 TIMEOUT，完成後共用狀態為 COMPLETED 且結果可取用。最後從磁碟重新開啟 audit record，與畫面結果一致。稽核保存失敗沿用已確認決策：不新增放行阻擋，但會標示稽核不完整。

## 驗證紀錄

- 基準：`8f6c8497e58eb1865d9c85f42df2d4a532575a15`（開始 Ticket 14 前的 `B518-Log-Solution`）。工作分支：`codex/ticket-14`。
- 環境：macOS 15.7.9、Intel x86_64、Python 3.8.10；桌面 1440×900（macOS 顯示點），Tk scaling 約 1；主視窗 752×990 實際像素／376×467 Tk 邏輯單位。實際 KVM／上位機未連接。
- Tk 驗證命令：`python3 -u tools/smoke_sample_adapter_app.py`。結果：工程師配置建立／保存及操作員選擇成功；配置容量 3 與非恆等映射生效；衝突與警報各自可操作；畫面最終為 `[1: FAIL, 2: FAIL, 3: TIMEOUT]`、共同輪次 COMPLETED、結果可取用；稽核可由磁碟重建且與 App 一致。隔離 HOME、偏好、來源及 sessions 目錄均由腳本建立於暫存目錄；樣本僅含 `SAMPLE000xxx`。
- 實際畫面證據：`B518 Log Solution/docs/refactoring/evidence/ticket-14/` 中的 `monitoring.png`、`conflict.png`、`alarm.png`、`complete.png` 與 `app-round.json`。截圖來自受控 Tk App，不是 KVM／上位機輸出。
- 單檔／回歸命令：`python3 scripts/run_tests.py test_platform_registry test_machine_profiles test_configured_monitor test_log_monitoring test_monitoring_round test_audit_records test_log_solution_ui`；相關測試均包含於下列全套 184 項結果。另以 `python3 scripts/run_tests.py test_platform_registry test_machine_profiles test_configured_monitor` 通過 24 項。
- 全套命令：`python3 scripts/run_tests.py`；184 tests，全數通過（macOS 桌面環境，約 20 秒）。
- 語法檢查：`python3 -m py_compile src/platform_registry.py src/sample_json_monitor.py src/machine_profiles.py src/b518_log_solution.py tests/test_platform_registry.py tools/smoke_sample_adapter_app.py`。專案沒有 mypy／pyright／其他型別檢查設定；此命令只驗證 Python 語法，不作型別檢查通過宣稱。
- 補充：`git diff --check` 通過。Code review 使用固定基準上述 SHA，執行 Standards 與 Spec 雙軸；發現、修正及複審結果於提交後補記。

## 尚未執行／限制

- 本機受控樣本與 Tk 回放已執行；需要實際 KVM、治具、目標設備、發布 App 的驗收依使用者已確認決策暫緩，保持未勾選。實機即時來源時間行為亦未在本票宣稱通過。
- Ticket 12 AC 1 的實際 KVM 驗收仍未確認；Ticket 13 AC 4 的實際 KVM 驗收仍待驗。上位機共同整合留在 Ticket 16、發布留在 Ticket 17、未知同輪來源政策留在 Ticket 18。
- 樣本格式只驗證 adapter 擴充邊界及既有共同流程，不代表新儀器、真實治具容量或部署支援。

## 提交與同步

- 實作提交、審查修正提交、合併 commit SHA、Gitea／GitHub 推送及分支清理結果：完成後填入。
