# M1 本機驗收紀錄

日期：2026-10-08（Asia/Taipei）
票證：多語言 M1／GitHub #14  ︎
固定 Standards／Spec 基準：`dd81e4dcef781ef4c29a3310a2650827e45d0609`
最後程式／測試提交：`3a613f9`（`test: verify unknown language fallback in Tk`）
前一程式提交：`0a346544fa65a4dd31f6c3194d61a04514e2d6e8`
工作分支：`Multilingual/ticket-01`

## 實作契約

- `src/language_catalog.py` 集中 English／繁體中文資源、穩定訊息 ID、具名參數、缺少繁中項目的英文回退與資源完整性檢查；提供 `translate`、`language_name` 及語言支援檢查。共用術語沿用 `CONTEXT.md` 的 Test Round、Awaiting Review、Station Type、Original Result、New Candidate、Source Time、Source Filename 對應，不改機器狀態碼。
- 全域語言沿用 `MachineProfileStore` 的本機 preferences JSON 欄位 `language`，不綁 profile、不新增 schema。無檔／舊檔缺欄位時為 `en`；受支援值由公開 `language` 與 `save_language` 讀寫。設定保存及匯入沿用同一可靠原子寫入與偏好保留行為，匯出仍只輸出可攜配置。
- 主頁右上選單顯示 English ▾／繁體中文 ▾，原生語言名稱以原生 radio menu 顯示選取勾號。滑鼠、Space／Return／Down 開啟、選取及 Escape 取消皆由實際 Tk 測試操作。
- 切換只更新既有主頁 widget 與目前文案，不重建監控、不重新綁回呼、不重讀來源、不清除產品結果／候選／警報，不碰 Tk 外的 worker。KVM 標記、色帶、PASS／FAIL 等機器狀態碼及輪次磁碟資料維持原契約。
- 未知已保存語言回退 English，`MachineProfileStore.language_error` 提供診斷，App 透過可理解警告呈現且不把它轉成阻擋啟動的 `profile_error`。當次語言寫入失敗時允許當前畫面使用所選語言，顯示保存失敗對話框；store 與磁碟仍保留舊有效值，重啟不會假稱記住失敗的新值。
- M1 僅翻譯主監控頁及其主頁保存／輪次摘要文字。設定、衝突、警報與其他自有視窗，以及 App／平台事件雙語落盤、歷史事件重翻譯、bundle／現場發布仍屬 M2～M10；本次不宣告全 App 多語言完成。

## 六項驗收

| 驗收 | 結果與證據 |
| --- | --- |
| 1. 語言按鈕、原生選項及當前勾選 | **通過。** 真 Tk 測試核對按鈕目前語言與展開箭頭、選項恰為 English／繁體中文、radio 語言變數與當前選擇；確認入口在選取列右側且位於 KVM 標題上方，沒有壓住 KVM 內容。 |
| 2. 滑鼠／鍵盤展開、選取、取消與重選 | **通過。** 真 Tk 測試對實際 Menubutton 送出滑鼠事件及 Space，對實際 Menu 選項操作；Escape 取消不改語言，重選現值不寫偏好。 |
| 3. 預設、持久化與偏好相容 | **通過。** 無偏好檔及舊檔缺欄位單元測試確認預設 English；真 Tk 以 Chinese／English 實際選單切換，再用全新 `MachineProfileStore` 和全新 App 從暫存磁碟讀回。配置保存、匯入、匯出與保存天數保留由 `test_profile_save_and_import_keep_global_language_but_export_only_profiles`、`test_language_replace_failure_preserves_effective_setting_and_preferences_file` 及相關偏好測試驗證。未知語言真 Tk 測試確認 English、可理解警告及正常 profile 使用；寫入故障真 Tk 驗證錯誤訊息與磁碟舊值。 |
| 4. 集中資源、穩定 ID、參數、回退與術語 | **通過。** `test_language_catalog` 驗證具名參數、缺少繁中單項回退英文、支援語言資源鍵／參數完整，以及 CONTEXT 核准的七個中英術語；流程使用 round ID／狀態，不以翻譯字串判斷。 |
| 5. 監控中即時更新與 KVM／結果保護 | **通過。** 真 Tk 使用暫存 `sample-json` 來源從 RUNNING 切換，再進入 AWAITING_REVIEW 後切換；確認 round ID、候選身分、結果列及 audit／Session bytes 在第一次切換前後一致。切換前後以實際 widget 座標檢查語言入口不遮住 KVM。 |
| 6. App／磁碟／未知值／失敗與舊路徑相容 | **通過。** 真 Tk 操作持久讀寫、全新 App 重啟、未知語言警告、原子寫入失敗；磁碟配置與既有 audit／Session 對照未因切換改寫。完整既有套件回歸 297 tests 通過；未遷移視窗仍使用原行為，不據此宣稱全 App 翻譯完成。 |

## 實際命令與結果

從 Python 程式目錄 `B518 Log Solution/` 執行：

```text
python3 scripts/run_tests.py test_language_catalog test_machine_profiles
B518_TK_TESTS=1 python3 scripts/run_tests.py test_log_solution_ui.LogSolutionUiTests.test_real_tk_language_menu_switches_main_page_and_persists_across_app_instances
B518_TK_TESTS=1 python3 scripts/run_tests.py test_log_solution_ui.LogSolutionUiTests.test_real_tk_unknown_saved_language_uses_english_and_shows_diagnostic
B518_TK_TESTS=1 python3 scripts/run_tests.py
python3 -m compileall -q src tests
git diff --check
```

最後完整含 Tk 套件在可存取桌面圖形工作階段執行，**297 tests 通過，64.846 秒**；compileall 及 diff whitespace 檢查通過。第一次未提升的 Tk 嘗試在建立視窗前因執行環境中止（exit 134），其後使用已授權桌面工作階段重跑，兩個新增真正 Tk 案例及完整套件皆通過。這是執行環境限制，不是產品失敗。

測試先以 `test_machine_profiles` 建立「預設英文／磁碟重讀」反例，再實作全域公開讀寫；翻譯 API 與英文回退測試先因資源／API 缺少而失敗，再加入集中資源後通過。真正 Tk 驗收從實際 App 與 menu 入口操作，不以 mock widget 或純記憶體設定代替。

專案未找到 mypy、pyright 或其他既有型別檢查設定；未宣稱型別檢查已通過，也沒有為 M1 新增型別檢查工程。

## 提交與界線

- 程式／翻譯資源提交：`0a346544fa65a4dd31f6c3194d61a04514e2d6e8`。
- 未知設定真正 Tk 回歸測試提交：`3a613f9`。
- 本紀錄最後程式驗收對應 `3a613f9`；固定審查基準為 `dd81e4dcef781ef4c29a3310a2650827e45d0609`。Standards／Spec 審查結果與合併 SHA 將於完成審查及主線驗收後補記。
- M2～M10 的視窗翻譯、雙語事件保存、歷史事件、App 事件期限與清理、完整 bundle 發布不在本票通過範圍。未執行 OS 全域快捷鍵實機、正式 bundle 或美國現場設備驗收。
- 遠端 GitHub Issue #14 與母規格 #13 未修改。
