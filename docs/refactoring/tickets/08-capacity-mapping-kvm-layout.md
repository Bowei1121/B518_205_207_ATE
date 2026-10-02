# 08：配置容量與位置映射，完成十格／兩排顯示

**類型：**新增

**What to build／工作內容與交付結果：**已支援平台依配置把來源位置映射至有效通道，支援一至二十位置並顯示固定十格色帶及可捲動明細。

**Blocked by／前置依賴：**

- [04：搬移 B482 資料來源並保護完整監控流程](04-b482-source-adapter.md)
- [05：搬移 RS-WMT 資料來源並保護完整監控流程](05-rswmt-source-adapter.md)
- [07：工程師畫面編輯、匯出及部署配置](07-profile-editor-import-export.md)

**Status：**complete（程式與受控 Tk 驗收完成；實機與上位機共同驗收依 Ticket 05／16 分開追蹤）

## 驗收條件

- [x] 容量 4、6、10、12、20 的隔離 Atlas 受控樣本經實際 parser、映射 seam 與共同輪次快照確認位置及 SN；容量 1／20 合法邊界、0／21 與平台不相容容量受驗證。
- [x] 容量 10 一排十格，容量 11～20 兩排各十格；第二排位置 11～20，Tk 實際視窗幾何受驗證。
- [x] 容量外固定黑色；容量內 WAITING、TESTING、COMPLETING、PASS、FAIL、NOTEST、TIMEOUT 等沿用明確色碼。
- [x] 來源編號與顯示位置不同、來源到達順序改變時仍依配置映射；B482 的 Thread0～3 正規化為來源位置 1～4 後，再套工程師映射。
- [x] 二十筆明細可捲動且色帶固定在頂部；字級、高對比、縮放／可用螢幕高度下的視窗尺寸均有 Tk 測試。
- [x] 配置驗證依 Adapter 解析器能力限制容量與來源位置；Atlas 受控格式可驗證至 20，B482／RS-WMT 受限於 4，不以 UI 行數推定硬體容量。

## 驗證方式

受控資料與 Tk 可見布局驗證；平台可支援能力與樣本容量分開記錄。

**規格驗收對照：**AC-04、AC-05、AC-22（色帶／捲動部分）

## 保留決策、待確認事項與限制

容量不等於本輪投入數量；真實四通道儀器不能由配置變成二十通道。定位點及黑白標記接續 12。

所有行為測試須依 01 的接口確認結果落實；本次批准任務清單不代表測試接口已獲批准。未知同輪來源能否人工採用仍由 18 決定，任何本票的已完成部分都不能抵銷該未決分支。

## 執行與追蹤

依 2026-09-30 使用者確認的任務清單建立。以 REFACTOR_SPEC、CONTEXT 與 ADR 0001～0005 為基準，沿用測試配置、平台資料來源、監控輪次、桌面介面四模組與 Python／Tk／既有 macOS 打包方式。只在前置完成且本票關鍵待決及外部條件已滿足時轉為 ready-for-agent；需要人類決策的任務不得逕自轉為可直接實作。

執行時逐項記錄實際交付、驗證環境與結果、仍未決／待驗範圍及相關提交。未執行的驗收維持未勾選；本文件建立不代表 App 已完成重構。

### Ticket 08 實際交付與驗收紀錄（2026-10-02）

- 基準 commit：`bc880b3aad8542d038f4a50189a992e4f6a5ad01`（`B518-Log-Solution`）；工作分支：`codex/ticket-08`。
- 交付：Adapter 宣告來源解析能力；profile 驗證容量與來源位置相容性，顯示位置完整涵蓋 1 至容量；Atlas 可配置來源位置 1～20，B482／RS-WMT 為 1～4。平台實際來源位置可高於配置容量，只要符合該 Adapter 能力並映射至有效顯示位置。
- 交付：主畫面配置容量動態顯示一至二十筆明細；KVM 色帶固定二十格，位置 1～10／11～20 固定排列兩排。容量外黑色，容量內未投入位置為 WAITING，兩者使用不同色碼。明細改為可捲動 Canvas；色帶位於捲動區外。
- 交付：開始輪次時保存有效 MachineProfile 快照並傳入 Adapter 設定；監控期間工程師套用另一容量／映射不重建目前列表、不改變本輪映射與色帶容量，下一輪才採用更新配置。
- 平台能力／證據對照：

  | 平台／Adapter | 解析器位置能力 | 本票受控樣本 | 真實設備容量證據 |
  | --- | --- | --- | --- |
  | Atlas | 可解析來源位置 1～20（`group0-slotN`） | 實際 Adapter／輪次流程覆蓋容量 4、6、10、12、20；每個位置使用隔離 `records.csv`，驗證 SN、事件及映射後快照 | 未以受控目錄推定設備能力；20 通道真實設備未驗收 |
  | B482 TestData／CaseInfo | Thread0～3 先正規化為 canonical 來源位置 1～4，再套 profile 映射 | 既有匿名化四 Thread 樣本及共同輪次測試；Thread0／1-based 正規化和來源到顯示位置映射分層 | 現有證據為四位置樣本；更高設備容量未驗收 |
  | RS-WMT | CSV／Log `tc=Slot` 與 `instance_active_1～4`，來源位置 1～4 | 既有隔離 CSV／Log parser 回歸；profile 容量大於 4 或來源大於 4 被拒絕 | Ticket 05 的現場即時資料時機仍待驗；本票不以 parser／回放代替 |

- 命令與環境：於應用資料夾 `B518 Log Solution/` 使用 Python 3.8；`python3 scripts/run_tests.py test_machine_profiles test_configured_monitor test_atlas_source_adapter test_b482_source_adapter test_rswmt_monitoring`；Tk 驗證使用登入桌面的 macOS Python／Tk。Atlas UI 回放使用 `TemporaryDirectory` 的 active、final、sessions 與暫存偏好；沒有讀寫原始實機資料。完整命令 `python3 scripts/run_tests.py`：130 tests，全部通過。
- 可見 Tk 版面：登入桌面解析度 1440 × 900，Tk scaling 1.0；實際 mapped 視窗在容量 10 為 376 × 643 px（單排十格），容量 11／20 為 376 × 670 px（兩排各十格，明細可視 7 筆、其餘 13 筆可捲動）。另在 Tk scaling 1.5 驗證狀態模板、狀態列與捲動視窗均未裁切；捲動到底時色帶 root 座標不變。不同實體 DPI／發布 App 仍待目標設備驗收。
- 唯讀匿名化基準回放：`python3 tools/replay_baseline_samples.py --caseinfo-date 2026-08-21 --rswmt-run 2026-09-11_05-45-44 testdata/anonymized-baseline` 成功；Atlas DFU/FCT 各 1 個 PASS，B482 TestData 4 個 NOTEST 且 CaseInfo 4 個 TESTING，RS-WMT 4 個 PASS。工具複製樣本至暫存目錄，未修改樣本樹；輸出僅含彙總狀態，不含序號或來源路徑。
- 型別檢查：專案未配置 mypy、pyright 或其他型別檢查命令；不把 `compileall` 當型別檢查。
- 外部安排：使用者確認上位機共同整合安排於 Ticket 16；repo 的 `B518 ATE MVP Demo/upper_computer_simulator.py` 是固定 Slot 1～4 的 Arduino TCP 模擬器，沒有 KVM 擷取。故不宣稱 KVM 實機、上位機共同驗收、目標設備或發布 App 驗收通過。Ticket 05 的 RS-WMT 實機時機仍獨立待驗；Ticket 18 未知同輪來源人工採用政策不由本票決定。
- Review／提交：固定基準 `bc880b3aad8542d038f4a50189a992e4f6a5ad01`；TDD 先以容量 1 的 Atlas 來源位置 20 映射、二十格 Tk 布局及容量 10／11 單排轉雙排行為測試確認失敗，再實作至通過。`$code-review` Standards／Spec 複審均無未解決問題；Spec 初審發現的第二排顯示條件及 README 舊七格敘述已修正。完整套件與合併後完整套件皆為 130 tests 通過。實作提交 `cae6337afb50d6102ff6e90d141aa574d9ac5d2e`、驗收紀錄提交 `05d0272943e181337b48dcdcafa3ea0d6d98fc28`；專用分支曾推至 Gitea 與 GitHub，兩端 ref 均核對為 `05d0272`，追蹤分支設為 `origin/codex/ticket-08`。一般非快轉合併 commit 為 `3b024107f497836b0eeea780b30ae5627439ef53`；合併後完整測試通過，合併及驗收紀錄已推至 Gitea 與 GitHub 的 `B518-Log-Solution`，目前兩端為 `62a71285a9db66d5f03ecfdf66ae411bed69e594` 並包含該合併 commit。確認同步後，Gitea、GitHub 的 `codex/ticket-08` ref 均已刪除，本地分支以 `git branch -d` 安全刪除；目前 checkout 為乾淨的 `B518-Log-Solution`。
