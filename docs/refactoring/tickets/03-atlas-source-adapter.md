# 03：搬移 Atlas 資料來源並保護完整監控流程

**類型：**搬移

**What to build／工作內容與交付結果：**將 Atlas 來源探索、可信 SN、active／archive 流程及結果證據集中於平台 Adapter，接回既有 DFU／FCT 完整操作。

**Blocked by／前置依賴：**

- [02：讓現有 App 經統一輪次接口操作](02-shared-round-interface.md)

**Status：**in-progress（Ticket 02 已核實完成；可先進行 Adapter 搬移與受控回放。現有 Atlas 樣本只有 archive，沒有真實 active tree；實機來源及 App 驗證仍須分別記錄）

## 驗收條件

- [x] 啟動前舊資料不被當成本輪，來源準備及監控進度可觀察。（RoundCoordinator 公開快照／事件測試驗證啟動前 active 資料忽略，並觀察 source_prepared 與新來源進度。）
- [x] 首次可信 SN 鎖定正確，無效識別值不當產品 SN，SN 讀取失敗語意保留。（首次可信識別鎖定、NUMBER_SOF0 過濾及 SN 讀取失敗由公開輪次結果驗證。）
- [x] active 消失、收尾與 archive 最終結果符合保護基準，最終結果不被後續進度降級。（active→archive、穩定 final 與後續進度保留由輪次快照及事件驗證。）
- [x] 檔案穩定性及來源有效變更按 Atlas 證據處理。（final CSV 簽章須跨兩次輪詢一致；新簽章會重新開始穩定判斷；啟動快照排除啟動前檔案。）
- [x] 由既有 App 完成一輪；畫面及共同輪次不解析 Atlas 特有格式。（本機實際 Tk App 的 DFU／FCT 按鈕流程各完成一輪；受控資料及畫面結果見執行紀錄。）

## 驗證方式

用可信／無效 SN、歷史資料、active 至 archive 的樣本回放，補一次 App 操作驗證。

**規格驗收對照：**AC-06、AC-07

## 保留決策、待確認事項與限制

保留 Atlas 真實證據與差異，不將平台語意強制統一；未知同輪人工採用不在本票定案。

所有行為測試須依 01 的接口確認結果落實；本次批准任務清單不代表測試接口已獲批准。未知同輪來源能否人工採用仍由 18 決定，任何本票的已完成部分都不能抵銷該未決分支。

## 執行與追蹤

依 2026-09-30 使用者確認的任務清單建立。以 REFACTOR_SPEC、CONTEXT 與 ADR 0001～0005 為基準，沿用測試配置、平台資料來源、監控輪次、桌面介面四模組與 Python／Tk／既有 macOS 打包方式。只在前置完成且本票關鍵待決及外部條件已滿足時轉為 ready-for-agent；需要人類決策的任務不得逕自轉為可直接實作。

執行時逐項記錄實際交付、驗證環境與結果、仍未決／待驗範圍及相關提交。未執行的驗收維持未勾選；本文件建立不代表 App 已完成重構。

## 執行紀錄｜2026-10-01

### 交付與行為證據

- 新增 B518 Log Solution/src/atlas_source_adapter.py。Adapter 負責 Atlas active/archive 路徑探索、啟動前檔案快照、可信 SN 解析與首次鎖定、active 消失後搜尋時間有效且來源有變更的 archive、CSV 結果判讀，以及 final 簽章穩定性。AtlasActiveArchiveMonitor 將型別化來源觀察套入共同監控結果／事件；monitoring_round.py 管理輪次生命週期，App 只用共同快照與事件呈現資料。
- 共用檔案簽章、目錄快照、CSV 讀取及 SN 正規化移至 src/monitoring_files.py；Atlas 專屬 archive 時戳、SN 欄位及結果解析留在 Atlas Adapter。舊 log_monitoring import 名稱仍匯出相容，B482／RS-WMT 呼叫與保護測試通過。
- 新增 tests/test_atlas_source_adapter.py，經 RoundCoordinator 快照／事件驗證啟動前舊檔排除、來源準備事件、首次可信 SN 鎖定、無效識別過濾、SN 讀取失敗、active 消失、final CSV 穩定及 final 不被後續 active 進度降級。
- 新增 tools/smoke_atlas_app.py，建立真實 Tk App 視窗並呼叫 App 的開始按鈕，使用隔離的暫存偏好與 session 目錄，分別操作 DFU 及 FCT。它將匿名 archive 記錄複製到受控 active 路徑，再投遞到受控 final 路徑；這是 App 操作驗證及受控回放，不代表有真實 active tree 或現場時序。

### 驗證命令、環境與限制

- 環境：macOS 15.7.9（Build 24G830）、Intel x86_64、Python 3.8.10。
- 單檔／相關測試：python3 scripts/run_tests.py test_atlas_source_adapter（4 tests）、python3 scripts/run_tests.py test_log_monitoring（19 tests）、python3 scripts/run_tests.py test_rswmt_monitoring（14 tests）、python3 scripts/run_tests.py test_replay_baseline_samples test_anonymize_baseline_samples（6 tests）通過；python3 -m compileall -q src tests tools scripts 通過。
- 匿名化包重播：python3 tools/replay_baseline_samples.py --caseinfo-date 2026-08-21 testdata/anonymized-baseline 通過；Atlas DFU/FCT 各 1 PASS，B482 四筆 NOTEST、CaseInfo 四通道 TESTING，RS-WMT 四個 PASS。
- 使用者提供的外部資料唯讀回放：python3 tools/replay_baseline_samples.py --caseinfo-date 2026-08-21 "/Users/tsengbowei/Desktop/公司資料/專案/FQ III/2026/B518/專案名稱/3. 程式/0. PC/ATE Test doc" 通過；Atlas DFU 20/20 PASS、FCT 7/7 PASS，B482 7 組／28 結果（12 PASS、16 NOTEST）及指定日期四通道 CaseInfo，RS-WMT 四個 PASS。回放工具複製輸入到臨時目錄並核對原始檔案雜湊、大小與修改時間；未修改或提交原始資料。
- 實際本機 App 操作：python3 tools/smoke_atlas_app.py 通過；DFU 完成 1 個 PASS 與 6 個 NOTEST，FCT 完成 1 個 PASS 與 5 個 NOTEST，兩輪均呈現完成且結果可取用。輸入 active 來自匿名 archive 範例的受控副本；提供資料中沒有真實 Atlas active tree，因此此結果不宣稱真實 active tree 或現場資料時序驗收。
- 專案未設定 mypy／pyright 型別檢查。Adapter 由 log_monitoring.py 靜態 import，打包入口引用檢查及 bundle 檢查器單元測試將列入最終驗證；未執行發布建置，也未在 Apple Silicon 目標機啟動打包 App。
- Ticket 18 的未知同輪來源人工採用政策保持未決。其餘測試、code-review 與完整套件結果完成後再更新本票最終狀態。

### 提交紀錄

本票分支 codex/ticket-03-atlas-source-adapter 目前包含並已推送至 Gitea 與 GitHub 的提交：448a363、1d22f73、229a599、ac8f4a8、f5b20b5、ce6a3b7。B518-Log-Solution 尚未合併；待雙軸審查及最終完整套件通過後處理。
