# 05：搬移 RS-WMT 資料來源並保護完整監控流程

**類型：**搬移

**What to build／工作內容與交付結果：**集中 RS-WMT 日期、位置、單產品 CSV／Log、檔案穩定性與最終結果證據，接回完整 BT 操作。

**Blocked by／前置依賴：**

- [02：讓現有 App 經統一輪次接口操作](02-shared-round-interface.md)

**Status：**blocked（RS-WMT 來源 Adapter 與本機驗收已完成；實機即時資料時機證據仍待取得）

## 驗收條件

- [x] 日期、來源位置、SN、最終結果與舊資料排除符合保護基準。（既有 RS-WMT 單輪回放及日期／Slot／SN／舊資料案例通過）
- [x] 摘要檔及上下限資料排除；單測項 PASS 不當作整機 PASS。（摘要與限制列解析案例通過；Log item PASS 只形成 TESTING，結束標記最多形成 COMPLETING）
- [x] 沒有 SN 的明確 Fail 仍為 FAIL，不套用 B482 空 SN NOTEST。（解析案例通過）
- [x] 半寫入、增量 Log 與穩定性重置可回放驗證。（暫存來源案例通過；Log 使用追加補齊，CSV 內容變動會重啟穩定計時）
- [x] 僅最終結果的平台不捏造 Testing；App 能接收有效 final 證據完成一輪。（四個 Slot 經 App 啟動及 RoundCoordinator 快照完成，沒有 TESTING 事件）

## 驗證方式

使用只讀原始樣本與暫存來源回放，驗證各類資料及 App 結果。

**規格驗收對照：**AC-06、AC-09、AC-10（解析證據部分）

## 保留決策、待確認事項與限制

實機即時資料時機仍須有證據；等待值的完整配置驗收由 07／09 接續。未知同輪採用分支保留至 18。

所有行為測試須依 01 的接口確認結果落實；本次批准任務清單不代表測試接口已獲批准。未知同輪來源能否人工採用仍由 18 決定，任何本票的已完成部分都不能抵銷該未決分支。

## 執行與追蹤

依 2026-09-30 使用者確認的任務清單建立。以 REFACTOR_SPEC、CONTEXT 與 ADR 0001～0005 為基準，沿用測試配置、平台資料來源、監控輪次、桌面介面四模組與 Python／Tk／既有 macOS 打包方式。只在前置完成且本票關鍵待決及外部條件已滿足時轉為 ready-for-agent；需要人類決策的任務不得逕自轉為可直接實作。

執行時逐項記錄實際交付、驗證環境與結果、仍未決／待驗範圍及相關提交。未執行的驗收維持未勾選；本文件建立不代表 App 已完成重構。

## 執行紀錄｜2026-10-01

### 交付與保護行為

- 新增 `B518 Log Solution/src/rswmt_source_adapter.py`，集中 RS-WMT 啟動快照、CSV／Log 檔案探索、日期／Slot／SN／整機結果解析、半寫入判斷、來源增量與穩定性追蹤、歷史及跨批次篩選。
- `rswmt_monitoring.py` 保留輪次監控責任，將來源 Adapter 的 progress、final、batch 證據轉成既有輪次事件與狀態；CSV final 證據穩定前只報 COMPLETING，穩定後才提供 PASS／FAIL。來源時間、來源類型與檔案路徑可由輪次事件觀察；Test Start Time 作為來源批次證據，不宣稱為新的全域批次識別。無證據欄位不補造。
- 無法解析為唯一 Slot／SN／起始時間的 Log，以及與已鎖定時間不同的候選，透過 warning 輪次事件保留檔案來源及可取得的時間、Slot、SN 證據；不更新任何產品結果、不決定人工採用政策，政策仍交由 Ticket 18。
- 保持 RS-WMT 無 SN 明確 Fail 為 FAIL；摘要／上下限資料與單項 PASS 不產生整機 PASS；來源啟動快照中的舊 CSV／Log 隔離；新 CSV 內容變動重新計算穩定等待。未知同輪來源人工採用政策未改動，仍交由 Ticket 18。

### 驗證環境與結果

- 環境：macOS 15.7.9、Intel x86_64、Python 3.8.10。最後一次 `python3 scripts/run_tests.py` 通過 101 tests。相關 RS-WMT、共同輪次、回放與 App 測試通過；完整 Tk 套件需桌面執行，沙盒執行時 Python 在 Tk 幾何測試中以 exit 134 中止，桌面重跑全套通過。
- `python3 tools/replay_baseline_samples.py --caseinfo-date 2026-08-21 testdata/anonymized-baseline` 通過：Atlas DFU／FCT 各 1 PASS，B482 TestData 4 NOTEST、CaseInfo 4 TESTING，RS-WMT 4 PASS。輸入是 repo 匿名化樣本；既有回放工具複製至暫存位置，沒有修改原始機台資料。
- 新增 App 整合測試，在暫存目錄提供四個 final-only CSV，經 `B518LogSolutionApp.start_monitor()` 與共同輪次接口觀察四個 PASS、輪次完成且可取用，沒有產生 TESTING。
- `python3 -m compileall -q src tests tools scripts` 與 `git diff --check` 通過。專案沒有 mypy、pyright 或其他型別檢查設定；未宣稱型別檢查通過。打包腳本以 `--paths src` 由 PyInstaller 靜態追蹤模組，來源 Adapter 被 RS-WMT monitor 匯入；打包檢查器測試納入完整套件。未執行建置，避免遞增 VERSION、清理建置目錄及產生發布產物。
- 本次未取得 RS-WMT 實機即時 Log／CSV 到達時機與目標站回饋；匿名化回放及可控暫存資料僅證明受控程式行為。Apple Silicon 打包啟動、目標站、KVM 與上位機驗收均未執行。因此保持本票 `blocked`，不得把本機測試記成現場驗收。
- 固定 code-review 基準 SHA：`81ea260334fd790821a543986800412bc5234f5e`。Spec 審查提出三項程式證據缺口，分別由 `1b53858`（Live Log 時間精度）、`06a7b80`／`b3af1b5`（歧義及無批次標記來源）、`abfdd0d`（僅有起始／來源時間但無 Slot／SN 的不完整 Log）修正並以公開輪次事件案例驗證。warning 僅保留可取得證據，不更新產品結果，也不決定 Ticket 18 人工採用政策。最後雙軸複查待完成。
- 本票提交：`e70e7312a081183446367c29ae1d5c33cef208ac`、`792f9162c5bbb837cf402de38431de4d614b08f3`、`c93266309e502eefe8f0ea726f6d6afa31c9dc8d`、`e92bab85eefedeeccf3d7b7d5a35aa31156afa0f`、`1b53858a52bdcd9a147f4570219c99615ee55a8c`、`06a7b8024be766eb1423e8d33f27e583c2a50b92`、`b3af1b5ab8367c2ec804ffde7d68228beca3f106`、`c8eabb6fa7b4857c2f66f0b18a31f03bb93d51a6`、`abfdd0d0c99be987cf1d8e67b096f5d63b85aaad`；均推送至 `origin` 設定的內部 Gitea 與 GitHub push 目的地。
