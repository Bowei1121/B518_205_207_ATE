# M10 全 App 整合驗收紀錄

日期：2026-10-09（Asia/Taipei）  
Git 根目錄：本 repo 根目錄  
Python 專案目錄：`B518 Log Solution/`  
固定 Standards／Spec 審查基準：`95b791c2cf1a54b10db4f07cbc606ddd06db8280`  
本次程式／測試版本：`e8a309fd1fac186832c5825c803e4299932f206b`

## 基準與直接依賴

從固定基準以 ancestry 與實際交付紀錄確認 M5～M9 均已在 `B518-Log-Solution`：M5 `740b26c`、M6 `31a9bcc`、M7 `45df1e3`、M8 `98a3e5c`、M9 `01ab629` 相關實作及後續合併提交均為基準祖先。逐票驗收證據為 `multilingual-ticket-05` 至 `multilingual-ticket-09/local-validation.md`；另以目前實際程式、M10 最終完整套件及本文件的新整合案例覆核。前票驗收紀錄中的歷史 SHA 與測試數字只用來定位證據，不作本次結果。

本次 M10 整合檢查發現兩個已修正的漏項：來源準備失敗原先固定中文且未將錯誤作為穩定雙語事件保存；已開啟的 App 診斷及歷史視窗標題未隨主語言刷新。來源準備失敗案例使用真實 Tk App 與磁碟重建，但 mock `messagebox.showerror`，因此只確認 App 將本語言標題／說明及原始診斷傳至對話框邊界，沒有宣稱原生 modal 實際可見驗收。多視窗真 Tk 案例檢查所選語言的事件列與詳細文字、同一視窗實例、草稿及事件選取保留，以及語言切換未改寫 App 事件 bytes 或增加事件 revision。

## 覆蓋清單

| 領域／入口 | 人員文案與狀態 | 固定原值／例外 | 刷新與驗收證據 |
| --- | --- | --- | --- |
| 主頁、語言入口、監控狀態、保存控制 | `main.*`、`monitor.*`、`save.*` 集中資源；狀態以 message ID 表示 | KVM 的 PASS／FAIL／TESTING／NOTEST 是機器狀態 | M1/M2/M3/M7 驗收及完整 Tk 套件；本票移除以中文狀態文字反查 ID 的邏輯 |
| 設定、配置、保存天數、匯入匯出 | M5 集中資源；已開設定視窗原地刷新 | 專案代號、Station Type 值、平台 ID、路徑、自訂名稱及配置資料 | M5 真 Tk 草稿／選取／錯誤及持久重讀；M10 多視窗案例再次覆核設定視窗 |
| 原生選檔 | App 提供的標題、類型名稱及說明採所選語言 | 原生檔案視窗按鈕及 OS 覆寫提示屬系統文字 | M5 使用者已完成兩語選取、取消、匯入匯出及拒絕覆寫；App 標題傳遞與原生視窗文字邊界見 M5 證據 |
| 衝突、證據對照、人工裁決 | M6 共用資源；已開視窗刷新 | SN、來源時間／檔名／路徑、原始 Log 與證據快照 | M6 真 Tk 多候選、刷新、裁決及 audit 重建；本次完整套件重跑 |
| 整輪警報 | M6 共用資源；已開視窗刷新 | alarm／round ID、時間與機器欄位保留 | M6 真 Tk 確認操作及保存；本次完整套件重跑 |
| App／輪次保存、重試、關閉及取消 | M4/M7 資源及目前保存狀態；關閉期間語言入口受保護 | 原始診斷保留原文 | M7 真 Tk 等待、失敗、重試、取消、再次關閉及延遲完成交錯；本次完整套件重跑 |
| App 診斷、歷史事件、維護摘要 | M4/M8/M9 資源；事件依目前語言重顯示 | 原始診斷、原始 message、保存的英文、參數及時間 | M10 新多視窗案例重驗 App 診斷／歷史標題刷新、選取保留及事件磁碟不變；前票真 Tk／全新讀取器證據 |
| Atlas、B482、RS-WMT、sample-json 與共同輪次 | M2/M3 穩定 message ID、固定參數及雙語事件 | SN、來源檔名／路徑／時間、Log、平台識別、狀態碼 | 各平台真實暫存來源、共同輪次、真正 Tk、Session／audit 重建於 M3 驗收；最終完整套件重跑 |
| 啟動來源準備失敗 | 本票修正為 `round.start_failed` 穩定雙語訊息；繁中標題／說明送至 messagebox | `PermissionError` 原始診斷保留原文 | M10 真 Tk／磁碟案例確認對話框參數及同筆 audit 雙語重建；`showerror` 被 mock，原生 modal 可見結果未由此案例驗證 |

完整資源 catalog 有 English 317 鍵、繁體中文 317 鍵。`validate_translations()` 回傳空 tuple；它逐語言驗證鍵集合及格式參數集合一致。`test_language_catalog` 同時核對核准術語及衝突／警報關鍵文案。本驗收不新增語言，也不讓新語言進入固定雙語磁碟格式。

## M10 六項驗收

| # | 驗收 | 結果與證據 |
| --- | --- | --- |
| 1 | 資源鍵、參數及術語完整；英文基準與關鍵提示不是靠回退 | **通過資源結構檢查。** 317/317 鍵及參數格式一致、零 catalog errors；集中目錄含裁決、警報、保存失敗提示。來源：`test_language_catalog`、下方 catalog 命令。完整入口覆蓋仍依逐路徑測試與前票證據，不以搜尋零命中作證。 |
| 2 | 全部自有視窗、事件及錯誤兩語完整，已開視窗保留狀態 | **部分通過。** M10 新測試檢查設定、App 診斷、歷史三窗的標題、已選事件列與詳細文字確實換語，並保留草稿、分頁、選取、視窗實例及磁碟 bytes。M5～M9 真 Tk 測試另覆蓋各自視窗；全部可達入口的完整 producer／文案盤點與全部視窗整合流程仍待完成。原生系統文字、機器狀態及原始證據依規格保留。正式 bundle 尚未驗。 |
| 3 | 多視窗、連續切換、監控、待確認及關閉取消 | **部分通過。** 新案例同時開啟設定、App 診斷及歷史視窗，連續中英切換並核對同一視窗、選取、草稿及事件 bytes/revision；衝突／警報與關閉取消各由 M6/M7 真 Tk 案例覆蓋並在完整套件重跑。跨全部自有視窗的一次性長流程尚無單一案例。 |
| 4 | 長英文、主要畫面可讀、KVM 幾何與判定維持 | **source 通過、整項部分待驗。** M1/M5/M6/M7 真 Tk 版面及 KVM 幾何測試納入最終完整套件；尚未在目標 HMI／實機 KVM 與目標解析度驗收。 |
| 5 | 十六組情境、兩語業務一致、回歸通過 | **部分通過。** 十六組對照已建立，最終完整套件涵蓋本機 source 測試入口，M1～M9 真 Tk／磁碟證據按適用案例引用；第 16 組正式 bundle／目標環境尚未驗，不能勾選全部案例完成。來源、操作及 KVM 實機不宣稱已驗。 |
| 6 | 發布產物收錄資源，source 與 bundle／目標環境分開 | **未通過／外部環境阻擋。** 本機不符合任何既有建置矩陣；未執行會清目錄及遞增 `VERSION` 的建置腳本，未產生或驗證正式 bundle。見 [release-validation.md](release-validation.md)。此項是 M10 必要驗收，不可標完成或合併。 |

## 母規格十六組案例對照

| # | 案例 | 本次整合版本的證據與結果 | 限制 |
| --- | --- | --- | --- |
| 1 | 首次英文、語言持久、配置互不抹除、保存故障 | M1/M5 `test_machine_profiles`、語言／設定真 Tk 測試；完整套件重跑 | source App；未在 bundle 重啟 |
| 2 | 語言選單滑鼠／鍵盤／取消 | M1 真 Tk 滑鼠與鍵盤驗收；M10 完整套件重跑 | 本票未另作 OS 級全域輸入驗收 |
| 3 | RUNNING／AWAITING_REVIEW 切換不改流程 | M1/M2/M3/M6 的輪次、平台、衝突測試；完整套件重跑 | 兩語實機生產來源待現場 |
| 4 | 多自有視窗與既有事件刷新、狀態保留 | M10 `test_integrated_language_refresh_keeps_open_settings_diagnostics_and_history` 檢查設定／診斷／歷史三窗的事件列及詳細文案兩語更新；M5～M9 各視窗真 Tk 回歸 | 本次新組合涵蓋設定／診斷／歷史三窗；衝突、警報、關閉路徑由前票各自驗證，非同一長流程。語言選單使用測試 invoke 驅動刷新，M1 的原生滑鼠／鍵盤使用者驗收另行引用 |
| 5 | 關閉時停用語言、取消恢復、重試 | M7 真 Tk 關閉保存案例；完整套件重跑 | OS 原生選單跨關閉競爭按 M7 既有接縫測試 |
| 6 | 原生選檔、取消、覆寫、返回路徑 | M5 使用者操作及暫存檔／hash 證據；完整套件重跑 | OS 原生按鈕文字遵照 OS |
| 7 | 本語言錯誤、原始診斷、關鍵提示及安全回退 | M4/M6/M7 及 M10 來源準備錯誤真 Tk／磁碟重建；完整套件重跑 | 對未遷移路徑仍保留既有相容行為 |
| 8 | 資源鍵、參數、術語、兩語首版完整性 | catalog 317/317、`validate_translations()==()`、`test_language_catalog` | 不等於 OS 對所有像素的文字審核 |
| 9 | 同筆雙語與磁碟不改寫 | M2/M3/M4/M8/M10 真磁碟讀取器與 bytes 測試；本次多窗事件 bytes/revision 不變 | 無外部 journal 操作 |
| 10 | 有序保存、故障補存、無輪次事件 | M2/M4/M7/M9 保存、重試、關閉與 App event store 測試；完整套件重跑 | source 暫存資料 |
| 11 | 新舊歷史相容與原文保留 | M8 混合歷史真 Tk／全新 reader／唯讀 bytes 測試；完整套件重跑 | 不批次改寫歷史資料 |
| 12 | App 原事件時間期限與受保護資料 | M9 注入時鐘、混合保存段及保護測試；完整套件重跑 | 只限 App 管理資料 |
| 13 | 全域期限、保存／清理競爭、故障及摘要 | M9 RoundCoordinator／真 Tk／磁碟重建測試；完整套件重跑 | bundle 上的排程仍待 M10 產物驗收 |
| 14 | 兩語 Tk 版面、長文字、主要彈窗與 KVM | M1/M5/M6/M7/M10 真 Tk + KVM geometry tests | 實際 HMI、KVM 擷取及目標解析度現場待驗 |
| 15 | 相同平台來源與人工決定的兩語業務一致 | M2/M3/M6 真實暫存平台來源、衝突／操作、audit 測試；完整套件重跑 | 現場設備操作待安排 |
| 16 | 正式發布資源、bundle／目標環境與完整回歸 | release preflight 現況見 release 驗收紀錄；source 完整套件通過 | **未驗；不符合發布環境，不產生 bundle。** |

## 命令與結果

以下命令在 `B518 Log Solution/` 執行，程式／測試 SHA 為 `e8a309fd1fac186832c5825c803e4299932f206b`：

```zsh
B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py
python3 -m compileall -q src tests
git diff --check
PYTHONPATH=src python3 -c 'import language_catalog as c; print(len(c.LANGUAGE_RESOURCES[c.ENGLISH]), len(c.LANGUAGE_RESOURCES[c.TRADITIONAL_CHINESE]), c.validate_translations())'
```

最終含 Tk 套件結果：**365 tests，97.910 秒，OK**；包括新增的多視窗與來源準備失敗真 Tk 案例。最終程式／測試 SHA 為 `e8a309fd1fac186832c5825c803e4299932f206b`。該 SHA 的整合 Tk 案例另單獨重跑：1 test，1.112 秒，OK。`python3 -m compileall -q src tests`、`git diff --check` 及資源檢查均通過。catalog 輸出為 `317 317 ()`。專案未找到既有 mypy、pyright 或型別檢查設定；沒有新增型別檢查工程，也不宣稱型別檢查通過。

標準與規格複審指出，先前測試未斷言診斷／歷史事件列及詳細區的可見文字變更，故新增對 `app.startup.started` 既有事件在英文／繁中切換後的 Listbox 與詳細文字斷言。來源準備失敗測試以 mock 擷取 `messagebox.showerror` 參數，僅證明 App 傳入本語言標題／說明及原始診斷，不能作為原生提示實際顯示驗收；既有 M4/M7 真 Tk 提示案例另有各自證據。完整全入口及全視窗整合仍列部分，不以本次三視窗案例擴大宣稱。

## 審查、發布與遠端狀態

固定基準 Standards／Spec 雙軸複審已確認先前問題已修正；程式／測試提交：`68379866d09dc8709cd9249665bcd2c0f837f269`、`f58c0a6252e438da8fa67a74ba1feb916516732d`、`3cebd090d4ec8a6c70c7cc09f69b07b43061f480`、`e8a309fd1fac186832c5825c803e4299932f206b`；文件提交 `3a658399927de1fe5bffbfb614e1c47c6fe30b89`、`522bdaa52f4352553342354a2a7a7bfd9c5534ed`。各驗證批次已推 GitHub 同名票分支。2026-10-09 17:39（Asia/Taipei）在 `3a65839` 文件推送後直接查得 ticket `3a658399927de1fe5bffbfb614e1c47c6fe30b89`、main `95b791c2cf1a54b10db4f07cbc606ddd06db8280`；2026-10-09 17:40（Asia/Taipei）在 `522bdaa` 推送後再次執行 `git ls-remote github refs/heads/Multilingual/ticket-10 refs/heads/B518-Log-Solution`，直接查得 ticket `522bdaa52f4352553342354a2a7a7bfd9c5534ed`、main `95b791c2cf1a54b10db4f07cbc606ddd06db8280`。後續最終文件提交推送後仍須直接查詢。`origin` 另有內網 Gitea fetch/push URL `http://10.64.76.34:3000/8362/B518-205_207_ATE.git`，且 push URL 另列 GitHub；M10 前置查核時 Gitea 不可達，依使用者指定週一內網同步並直接確認前保留本地與遠端票分支。未合併、未清理分支。

M10 source 測試與必要整合修正已交付，但正式 bundle／目標環境仍是必要阻擋；固定基準審查及文件審查完成後仍不進行 merge，直到發布驗收補齊。Gitea 週一直接確認前保留分支。M10 不代表未授權部署或現場設備驗收。
