# Ticket 06 本機驗收紀錄

## 範圍與基準

- 專案 Git 根目錄：`B518 Log Solution/`；Python 程式目錄：`B518 Log Solution/`。
- 工作分支：`round/ticket-06`；固定 code-review 基準：`f1d6e4768626b73732653ec7d978e9fa41b87bf7`。
- 最後驗證程式／測試 commit：`70db40709ade55d4605959df4207afaccce3ebed`。本文件及票號索引為驗收文件提交，非程式測試範圍。
- 起始分支查核確認 Ticket 01～05 已包含於基準。當時本地與 Gitea、GitHub 的 `B518-Log-Solution` 均為 `f1d6e476`，`round/ticket-06` 均不存在。
- 起始工作樹已有未提交的 `CONTEXT.md` 修改及兩個未追蹤文件：`docs/adr/0009-bilingual-app-event-records.md`、`docs/refactoring/MULTILINGUAL_DISCUSSION_2026-10-07.md`。它們未加入本票提交並保持原狀。

## 實作與 TDD 證據

- `MachineProfileStore` 提供全域 `retention_days` 讀取及 `save_retention_days()` 寫入；無設定或舊格式缺欄位時預設 365。只接受大於零的整數，使用既有同目錄暫存檔與原子替換方式寫入，只有寫入成功後才更新生效值。
- 全域欄位與 profile 草稿／匯出文件分開。既有偏好檔的 profile 寫入及匯入會保留保存天數；另驗證全新 Store 執行 profile save 時會先保留磁碟上有效的全域值。
- App 設定新增「保存期限」分頁，顯示目前生效值、輸入、保存結果及錯誤。說明保存期由可信封存時間起算、一天為完整 24 小時、縮短後可能在下一次背景清理到期，並清楚表示此版本不會刪除輪次資料。
- TDD 先行失敗證據：新增 Store 行為測試初次因缺少 `retention_days` 屬性失敗；全新 Store 覆寫測試曾重現預期的 `180 != 365`；真正 Tk 測試初次因缺少保存期限輸入變數失敗。實作後相應測試通過。新增保存期限分頁後，舊 UI 測試曾因仍只預期兩個分頁而失敗；更新 UI 結構斷言後通過。
- 不加入 Ticket 07 到期判定、歷史 Session 掃描、排程或刪除。

## 五項驗收

1. **全域設定與 365 預設：通過。** 無偏好檔 Store 測試與舊格式偏好遷移測試均確認 365；舊格式在遷移寫回及新 Store 重讀後仍為 365。保存期限放在 App 全域偏好文件頂層，不屬於單一 profile。
2. **正整數、錯誤及失敗保護：通過。** 真正 Tk 測試保存 730 與 180，再由新 Store 從磁碟讀回；空白、非整數、0、負數遭拒，原有效值及偏好檔 bytes 不變。Store 測試將 `os.replace` 注入 `OSError`，確認原偏好檔 bytes 及 365 生效值不變；Tk 顯示目前仍生效天數及錯誤原因。
3. **重啟及 profile 操作：通過。** Store profile save、import、export 與全新寫入器測試確認全域值保留，profile 匯出不含 `retention_days`。真正 Tk profile 編輯保存、配置匯出與匯入案例也在操作前保存 180／730 天，並從新 Store 確認匯入未覆寫全域值。
4. **期限提示：通過。** 真正 Tk 測試讀取設定分頁文字，確認包含可信封存時間、完整 24 小時、縮短後下次背景清理，以及不會執行刪除的說明；縮短期限後顯示下次背景清理提示。
5. **真正 Tk、持久讀寫及無刪除：通過。** 測試透過實際 Tk Entry 與 Button 操作保存、輸入驗證及故障顯示。操作前後比對暫存 Session 樹的檔案清單及既有 Session bytes，結果完全相同；程式差異不含輪次資料刪除。

## 實際驗收命令與結果

從 `B518 Log Solution/` 程式目錄執行：

```text
python3 scripts/run_tests.py test_machine_profiles
Ran 19 tests ... OK

python3 scripts/run_tests.py test_log_solution_ui.LogSolutionUiTests.test_real_tk_global_retention_setting_validates_persists_and_preserves_round_files
Ran 1 test ... OK

python3 scripts/run_tests.py test_log_solution_ui.LogSolutionUiTests.test_engineer_import_export_and_reload_preserve_a_deployable_catalog
Ran 1 test ... OK

python3 scripts/run_tests.py test_log_solution_ui.LogSolutionUiTests.test_settings_expose_profile_editor_and_session_log_without_legacy_monitor_tab
Ran 1 test ... OK

python3 scripts/run_tests.py test_machine_profiles.MachineProfileTests.test_store_migrates_legacy_preferences_and_restores_saved_selection
Ran 1 test ... OK

python3 scripts/run_tests.py
Ran 248 tests in 38.673s
OK

python3 -m compileall -q src tests
exit 0

git diff --check
exit 0
```

完整 248 項測試於最終程式／測試 commit `70db40709ade55d4605959df4207afaccce3ebed` 執行，Tk 測試在可存取桌面圖形工作階段的 macOS 環境實際建立 Tk 視窗並操作設定控制項。執行環境為 Python 3.8.10、macOS 15.7.9、x86_64。

Repository 沒有 `mypy.ini`、`pyproject.toml`、`setup.cfg`、`tox.ini`、`pyrightconfig.json` 或其他型別檢查設定，因此沒有宣稱型別檢查通過；`compileall` 僅作語法編譯檢查。

## Standards／Spec 審查及同步

- Standards 與 Spec 雙軸均以固定基準 `f1d6e4768626b73732653ec7d978e9fa41b87bf7` 審查；最終程式／測試 HEAD 為 `70db40709ade55d4605959df4207afaccce3ebed`，兩軸複審均無未解問題。Standards 首審的 UI／Store 正整數檢查重複已修正為由 Store 統一驗證，錯誤文字及生效值仍由 UI 呈現；受影響測試及完整套件已重跑。
- 程式／測試提交：`475a4e4`、`5e3a962`、`32ceaf8`、`70db407`。
- 使用 `git push --set-upstream origin round/ticket-06` 建立追蹤並推送；`origin` 設定的兩個 push URL 為 Gitea 與 GitHub。最近一次即時 `git ls-remote` 確認兩端 `round/ticket-06` 均為 `70db40709ade55d4605959df4207afaccce3ebed`，兩端 `B518-Log-Solution` 均仍為固定基準 `f1d6e4768626b73732653ec7d978e9fa41b87bf7`。
- 合併前再次 fetch 並確認主線工作樹乾淨；本地與 Gitea／GitHub 主線均為固定基準 `f1d6e4768626b73732653ec7d978e9fa41b87bf7`，Ticket 分支是五個提交的單純前進。一般 `--no-ff` 合併 commit 為 `2c75f07f44b0b3dee9eff22d387b0385ababc3eb`。
- 合併後於 `B518 Log Solution/` 執行 `python3 scripts/run_tests.py`：248 tests 通過（44.394 秒）；`python3 -m compileall -q src tests` 及 `git diff --check` 通過。合併後主線已推送至 Gitea 與 GitHub，重新 fetch／`git ls-remote` 確認兩端 `B518-Log-Solution` 均為 `2c75f07f44b0b3dee9eff22d387b0385ababc3eb`。
- 確認兩遠端主線同步後，使用一般 `git push origin --delete round/ticket-06` 刪除兩端分支；即時查核兩遠端均無該 ref，再以 `git branch -d round/ticket-06` 安全刪除本地分支並 prune tracking refs。合併 worktree 已移除，原專案目錄最後切回 `B518-Log-Solution`，HEAD 為 merge SHA。未使用強制推送或強制刪除。
- 原工作目錄內使用者既有未提交 `CONTEXT.md` 修改及未追蹤的 ADR／討論文件均保持未提交，未納入 Ticket 06 或合併提交。
