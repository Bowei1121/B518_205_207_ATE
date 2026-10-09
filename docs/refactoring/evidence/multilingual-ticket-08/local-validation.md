# M8 本機驗收紀錄 — 歷史事件顯示

日期：2026-10-09（Asia/Taipei）
專案：`B518-Log-Solution`（Python 專案位於 Git 根目錄內 `B518 Log Solution/`）
固定 Standards／Spec review baseline：`98a3e5c388cb993154d3302c70c10cbb608398c2`
票分支：`Multilingual/ticket-08`
最終程式／測試提交：`06c65592958970f38aa9330fb218ab2da66a3581`

## 基準與依賴

M8 開始時工作樹乾淨；固定 review baseline 是當時 `B518-Log-Solution` 的本地 SHA `98a3e5c388cb993154d3302c70c10cbb608398c2`，後續審查使用此 SHA，不隨票分支 HEAD 推進。從 `B518-Log-Solution` 建立 `Multilingual/ticket-08`，沒有覆蓋既有同名分支。

以 ancestry 和實際程式／已提交驗收紀錄確認 M3、M4 已包含於基準：M3 GitHub merge `fb4ffb2286d9c113511482b738a101a11616bd14`、M4 GitHub merge `f7e24cd265fc173d5d113e7fb122083602f5e5fa` 均為該基準祖先；M3/M4 驗收文件分別記錄平台事件與無輪次 App 事件的固定雙語、磁碟重建、原始診斷及保存恢復契約。README 原先將 #16/#17 列為 M8 阻擋，與 Git ancestry 及交付證據不符，已在本票文件中修正。M5～M7 不屬 M8 直接依賴。

開始時本地／GitHub 同名票分支皆在 M8 起始基準；M8 修改期間已提交並推送 `d20cc579`、`ebfa2a91`、`b076e6c`、`06c6559`。每批完成相應測試後 commit，再 push 至 `github/Multilingual/ticket-08`。2026-10-09 15:23（台北）直接 `git ls-remote github` 查得票分支 `06c65592958970f38aa9330fb218ab2da66a3581`、主線 `45df1e36895cdb8bbb313de0a4c038cdeef13ac4`。主線尚待此最終驗收及審查結果後合併。`origin` 的既有 fetch URL 為公司 Gitea `http://10.64.76.34:3000/8362/B518-205_207_ATE.git`，push URL 包含 Gitea 與 GitHub；本次直接查詢 Gitea 未於 10 秒內回應，依使用者指示週一於公司內網重試，未移除目的地。Gitea 尚未直接確認前保留本地及 GitHub 票分支。

## 事件讀取與辨識契約

歷史檢視器只讀取既有資料，不修復、補寫、封存或清理。輪次 audit 使用 `read_round_audit`，App 事件使用 `read_app_event_store`；兩者保持原有嚴格版本／欄位檢查。相容的舊 Session `events.log` 逐行讀取既有 JSON；不合法行以讀取錯誤呈現，其他有效行仍可見。audit 標示 `audit_complete=false` 時另顯示保存不完整警示，不把部分資料宣稱完整。

| 格式／事件 | 可辨識依據 | 必要資料及拒絕條件 | 原文／診斷與測試 |
| --- | --- | --- | --- |
| 新版 round audit event | audit schema v1、事件 `kind`、header `round_id`／`station`、序號與 `localized_message` | ID、version 1、parameters dict；不適用資源、未知 ID、參數格式錯誤或版本不符時顯示捕捉的英文，不生成新值 | 保留原 `message`、整筆 raw record 及 detail diagnostic；`test_new_app_event_uses_current_resource_and_keeps_saved_english_and_diagnostic`、`test_resource_updates_change_only_display_and_missing_or_unsupported_resources_fall_back` |
| 共同輪次舊 audit 事件 | audit schema v1 舊 producer 寫入的穩定 kind 白名單；`capture_round_event_message` 中既有 kind／station 契約 | `result` 要正整數 display position 及非空字串 status；有位置的 `timeout` 要正整數位置及非空字串 status，並有 elapsed/deadline 證據；`conflict_resolved` 要受支援 choice；未知 kind 不翻譯 | 詳細區保存舊 message／raw record；含 malformed station/status/timeout、缺欄位及未知 kind 拒絕案例 |
| 舊 Atlas audit platform event | audit v1 header `config.platform=atlas` 與明確 kind：`source_prepared`、`sn_locked`、`final`、`unresolved_source_conflict`；讀取錯誤需精確 `Atlas source read failed: ` producer 前綴 | Slot 事件需正整數 `display_position`；final 另需 status；source error 需原 source 路徑可取 basename；其他 warning 或不完整欄位拒絕翻譯 | 原始路徑、訊息、診斷保留詳細區；`test_legacy_platform_event_requires_platform_and_producer_contract` |
| 舊 B482／RS-WMT audit platform event | audit v1 platform header + producer kind：B482 `batch`／`batch_observed`；RS-WMT `batch`；平台讀取 warning 依 producer source 欄位 | B482 batch 要 batch identity；slot mismatch 要正整數位置；warning 需明確 producer kind及 source；不符合條件不翻譯 | 原 source／診斷保留；必要條件失效時落入未辨識原文，不補 batch／位置 |
| 舊 sample-json 平台事件 | M3 前不存在已交付的穩定 sample-json 舊 producer 契約 | 不從相似文案推 ID；M3 後新版事件走 `localized_message` | 新版由 `test_real_tk_historical_reader_selects_and_localizes_disk_records_without_rewriting` 覆蓋；舊自由文字由通用未辨識測試覆蓋 |
| 舊 `events.log` Session event | 舊 JSON line 僅有 `timestamp`／`message`／`detail`，沒有可靠穩定 kind | 不從 prose 猜 kind；不補 round ID、序號或時間。缺時間保留空值；格式錯誤產生 localized read-error row | 原 message/detail/raw JSON 保留；`test_legacy_session_without_machine_kind_is_kept_as_original` |
| 新版 App event store | App event store schema v1、event ID、sequence、occurred_at、kind、localized message、diagnostic | 嚴格沿用 `read_app_event_store`；不虛構 round ID | 新資源只改顯示，保存 English 與診斷仍可查；上述新 App 事件測試及真 Tk 混合紀錄測試 |

`HistoricalEvent.key` 只用於當次畫面穩定選取，不寫回磁碟；舊紀錄缺少持久身分時不製造持久 ID。排序按原事件時間，時間相同時使用現有 numeric sequence；無序號的舊 Session line 使用來源行序作為顯示 tie-breaker。新增測試先重現字串排序將 10 排在 2 前，再驗證數字順序。

## UI 及唯讀驗收

主頁 `Events & Session` 分頁的 `Browse Event History` 開啟唯讀歷史視窗。列表列出輪次、平台、App、legacy 及讀取錯誤／不完整警示；詳細區顯示舊 message、保存的雙語表示、參數、診斷及原始紀錄。選取由畫面 key 保持；換語言只重畫既有資料，不重新讀取來源或產生事件。使用者按 `Refresh History` 才執行明確磁碟重讀。

真正 Tk 驗收使用實際 Listbox row 的滑鼠 ButtonPress／ButtonRelease 操作，涵蓋混合舊 round event、新 Atlas platform event、新 App startup event 及舊 Session `events.log`。測試經語言選單項目觸發切換並檢查已開歷史窗、選取、列表位置及 detail 文字索引維持，原始診斷可查且 audit／App／Session bytes 不變；長紀錄及 40 列列表也納入。選單項目 `invoke` 驗證 App command/update path，不宣稱它單獨證明原生滑鼠／鍵盤導覽；原生 menu 操作另由 M1 真 Tk 與使用者在 `44826d4` 視窗的實際滑鼠／鍵盤確認支持。

`B518_TK_TESTS=1 PYTHONPATH=src python3 -m unittest tests.test_log_solution_ui.LogSolutionUiTests.test_real_tk_historical_reader_selects_and_localizes_disk_records_without_rewriting -v`

結果：通過。另以真實隔離暫存資料、全新 audit／App event readers 驗證新舊讀取、嚴格錯誤處理、保存英文回退、未知／相似舊文不翻譯及來源 bytes 不變。

## M8 五項驗收

| 驗收 | 結果與證據 |
| --- | --- |
| 新雙語資料依 ID／參數與目前資源顯示；失效時英文回退，不改保存文字 | 通過。`test_new_app_event_uses_current_resource_and_keeps_saved_english_and_diagnostic`、`test_resource_updates_change_only_display_and_missing_or_unsupported_resources_fall_back`；真 Tk mixed-history 測試；bytes 比較一致。 |
| 舊事件只按可靠契約辨識，不模糊猜測、不補值 | 通過。舊 round kind 白名單、Atlas 平台＋kind＋欄位契約及 rejection test；相似 custom note 與無 kind `events.log` 保留原文。未定義舊 sample-json 對照規則，避免推測。 |
| 未辨識內容原文詳細保留、外層翻譯；讀取不寫入 | 通過。舊自由文字、壞行與不完整 audit 有明確展示；測試前後來源檔 bytes 相同。 |
| 既有及歷史事件按語言更新，不重跑、不改事件身分、序號及結果 | 通過。真 Tk 在既有混合紀錄中切換並保留選取；新增 numeric sequence tie-breaker regression；語言刷新只作用於呈現。 |
| 輪次、平台、App、新舊混合資料由磁碟重建及真 Tk 閱讀 | 通過。全新 audit／App store readers 與真正 Tk mixed history 入口；整個專案 Tk 套件重跑。 |

M8 局部呼叫端清單：共同輪次與人工操作事件來自 `audit.jsonl`；平台來源事件經 ConfiguredMonitor／RoundCoordinator 進同一 audit；無輪次 App diagnostics 來自 App event store；相容舊 Session `events.log` 不含穩定 kind 時維持原文。歷史 UI 是純讀取展示，沒有把 M9 清理或既有待補存恢復混進閱讀流程。

## 命令與結果

程式／測試提交 `06c65592958970f38aa9330fb218ab2da66a3581`：

```text
PYTHONPATH=src python3 -m unittest tests.test_historical_event_display -v
Ran 13 tests in 0.180s — OK

B518_TK_TESTS=1 PYTHONPATH=src python3 -m unittest tests.test_log_solution_ui.LogSolutionUiTests.test_real_tk_historical_reader_selects_and_localizes_disk_records_without_rewriting -v
OK (real Tk desktop session)

B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py
Ran 350 tests in 100.778s — OK (true Tk cases in accessible desktop)

python3 -m compileall -q src tests
通過

git diff --check
通過
```

完整含 Tk 套件是在可存取桌面圖形工作階段執行；一般沙盒建窗失敗不當成產品缺陷。初始版本 343 tests 通過；相同時間序號排序 regression 起初 red（觀察 `[10, 2]`），後續審查亦找出捲動定位、重複錯誤列 key、malformed source/station/status 及 timeout 型別案例，逐一新增回歸並修正。最終 350 tests 全通過。專案未找到既有型別檢查設定；未新增設定，也不宣稱型別檢查通過。

## Code review、遠端與後續

Standards／Spec 雙軸審查均使用固定 baseline `98a3e5c388cb993154d3302c70c10cbb608398c2` 對最終 diff 複審，沒有未解決的可行動問題。Standards 提醒大型歷史列表同步讀取／呈現可能延遲 Tk；屬非阻擋建議，本票不擴增 M9 清理或背景載入架構。Spec 確認新舊資料契約、未知回退、唯讀 bytes、Tk 選取與捲動、錯誤型別拒絕符合 M8。原生 menu 導覽不由 M8 的 `.invoke()` 單獨宣稱通過；援引既有 M1 真 Tk 測試及使用者於 `44826d4` 視窗實際確認滑鼠、鍵盤切換與取消。

GitHub 票分支最後直接查詢 SHA 為 `06c65592958970f38aa9330fb218ab2da66a3581`（2026-10-09 15:23 台北）；GitHub main 在查詢時為 `45df1e36895cdb8bbb313de0a4c038cdeef13ac4`，其合併及合併後驗證仍待執行。公司 Gitea 位於內網，直接查詢逾 10 秒未回應，依使用者指示週一同步；未宣稱已同步且未移除目的地。Gitea 同步並直接確認前保留本地及 GitHub `Multilingual/ticket-08` 分支，不清理。

母規格案例 11 僅標記 M8 已實測的歷史相容、未知原文、目前資源顯示、磁碟唯讀及真 Tk 部分；M8 不代表全 App 多語言或 bundle 發布完成。M9 App event retention、M10 全 App／bundle 驗收仍待後續票。
