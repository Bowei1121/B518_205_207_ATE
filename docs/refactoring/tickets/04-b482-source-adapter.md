# 04：搬移 B482 資料來源並保護完整監控流程

**類型：**搬移

**What to build／工作內容與交付結果：**集中 B482 TestData／CaseInfo、來源位置、增量資料與可取得的批次證據，經共同接口完成 BT 監控。

**Blocked by／前置依賴：**

- [02：讓現有 App 經統一輪次接口操作](02-shared-round-interface.md)

**Status：**in-progress（實作及本機驗收完成；固定基準雙軸 code-review 進行中）

## 驗收條件

- [x] 歷史來源不混入本輪，位置、可信 SN 與進度符合保護基準。（RoundCoordinator 案例覆蓋啟動前 TestData 排除、Thread 至位置映射、可信 SN 與 CaseInfo 活動進度；四位置 App 回放完成。）
- [x] CaseInfo 第二個 SNRead 動作欄位解析正確。（RoundCoordinator 快照確認讀取 `...,--,SNRead,<barcode>`，忽略後續 CBRead 欄位。）
- [x] 半筆記錄不提前產生結果，補齊後可正常處理。（RoundCoordinator 案例確認未完成行維持 WAITING，補完整行後成為 TESTING 並鎖定可信 SN。）
- [x] 空 SN FAILED 保留為平台 NOTEST，而非套用其他平台規則。（RoundCoordinator 測試與四位置 App 回放均確認。）
- [x] 來源識別、來源時間與批次證據可交付輪次，未知欄位不捏造；App 可完成一輪。（RoundEvent detail 提供檔案相對識別、來源時間及現有日期／Thread／Config 證據；不確定的 CaseInfo 批次 ID 保持未知。本機 Tk App 完成四通道。）

## 驗證方式

回放 TestData／CaseInfo、空 SN、增量與半筆樣本，透過共同入口驗證結果。

**規格驗收對照：**AC-06、AC-08

## 保留決策、待確認事項與限制

現有跨批次接受不能當作新版通則。若搬移觸及未知同輪採用分支，保留證據及待決接口，不在本票改選允許／禁止；交由 18。

所有行為測試須依 01 的接口確認結果落實；本次批准任務清單不代表測試接口已獲批准。未知同輪來源能否人工採用仍由 18 決定，任何本票的已完成部分都不能抵銷該未決分支。

## 執行與追蹤

依 2026-09-30 使用者確認的任務清單建立。以 REFACTOR_SPEC、CONTEXT 與 ADR 0001～0005 為基準，沿用測試配置、平台資料來源、監控輪次、桌面介面四模組與 Python／Tk／既有 macOS 打包方式。只在前置完成且本票關鍵待決及外部條件已滿足時轉為 ready-for-agent；需要人類決策的任務不得逕自轉為可直接實作。

執行時逐項記錄實際交付、驗證環境與結果、仍未決／待驗範圍及相關提交。未執行的驗收維持未勾選；本文件建立不代表 App 已完成重構。

## 執行紀錄｜2026-10-01

### 交付與驗收

- 新增 `B518 Log Solution/src/b482_source_adapter.py`，集中 B482 TestData／CaseInfo 檔案探索、啟動快照、穩定等待、增量游標、半筆記錄緩衝、檔名／CSV 判讀、可信 SN 與來源證據。`BtLogMonitor` 經 Adapter 取得型別化觀察並維持既有批次／重複 Thread 覆核操作；共同輪次及 App 使用原本入口。
- 依本票保護既有 B482 Thread 0–3 對應顯示位置 1–4；新增 RoundCoordinator 案例以四個不同 SN／結果直接驗證位置。配置驅動的位置映射屬 AC-05／Ticket 08，不由本票提前實作。
- Adapter 在輪次建立時記錄已存在 CaseInfo 檔案的大小，只讀取後續新增內容；回歸案例確認時間仍在 30 秒寬限內的歷史行也不會混入本輪。檔案截短時跳過當下已存在的內容，從新檔尾繼續讀取。
- 每筆 B482 RoundEvent 的結果 detail 帶有來源識別與來源時間；TestData 另提供檔名批次戳記及已知 Thread／Config，CaseInfo 提供檔名日期與 Thread 作為來源證據，不宣稱其為已確認批次。缺少的批次欄位保持未知。
- 新增 `tests/test_b482_source_adapter.py`，經 RoundCoordinator 公開快照／事件驗證歷史 TestData 與 CaseInfo 隔離、第二個 SNRead 欄位、半筆 CaseInfo 補齊、空 SN FAILED → NOTEST，以及來源識別／時間／批次證據。
- 新增 `tools/smoke_b482_app.py`，以隔離偏好目錄與匿名化四通道樣本，透過 Tk App 開始並完成一輪；四通道平台 NOTEST 均可取用。這是本機受控回放，不代表目標產線或目標機驗收。
- Ticket 18 的未知同輪來源人工採用政策保留未決；本次沒有替 CaseInfo 日期或檔名戳記推斷未知批次，也未改動允許／禁止採用政策。

### 驗證與限制

- 執行環境：macOS 15.7.9、Intel x86_64、Python 3.8.10。
- 相關單檔套件 `python3 scripts/run_tests.py test_b482_source_adapter test_log_monitoring`：25 tests 通過。
- 完整套件 `python3 scripts/run_tests.py`：97 tests 通過（包含 Tk 介面與 bundle 檢查）。
- `python3 -m compileall -q src tests tools scripts` 及 `git diff --check` 通過；專案未配置 mypy／pyright，沒有宣稱型別檢查通過。
- `python3 tools/replay_baseline_samples.py --caseinfo-date 2026-08-21 testdata/anonymized-baseline` 通過：B482 TestData 4 個 NOTEST、CaseInfo 4 通道 TESTING 且含可信 SN，經共同輪次完成；Atlas／RS-WMT 對照樣本亦符合基準。來源是 repo 內匿名化樣本，沒有讀寫原始機台資料。
- `python3 tools/smoke_b482_app.py` 通過：本機 Tk App 完成 B482 四通道輪次，結果為 4 個 NOTEST 且 `result_available` 為真。
- 尚未在 Apple Silicon 目標機、發布打包版或產線 KVM／上位機組合驗收；這些不由本機匿名化回放代表。

### 審查與提交

- 固定審查基準：`30739a0690ed534b5db2801a2eba2fadc08384ce`（`B518-Log-Solution`）。
- Standards 初審：無文件標準違規或可採取的 Fowler smell 發現。Spec 初審指出 CaseInfo 啟動前內容缺少隔離；已新增啟動快照及公開輪次回歸案例修正，雙軸複審待完成。全部審查通過後才更新狀態並合併。
- 本批程式與測試提交：`f9837ae`（`refactor: isolate B482 source adapter`），已推送至內部 Gitea 與 GitHub 的同名專用分支。
