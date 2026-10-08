# C1 人工衝突彈窗本機驗收紀錄

日期：2026-10-08（Asia/Taipei）

專案根目錄：`B518 Log Solution`

Python 程式／測試目錄：`B518 Log Solution/B518 Log Solution`

工作分支：`ConflictDialog/ticket-01`

固定 code-review 基準：`d0f4535dc74753cbb6a457828b7b5c1d6ecacac9`

最後已驗證程式提交：`ebe7364`（其父提交 `5240a21`；後續僅有驗收文件提交）

## 交付內容

右側彈窗新增固定「結果、SN、來源時間、來源檔名」四列摘要表格與顯示位置，左側衝突清單選取時摘要與原完整詳細資訊同步更新。上下使用可拖曳垂直分隔，首次配置約 40%／60%。摘要與詳細文字均取自同一 `RoundConflict` 快照；檔名只取快照來源路徑 basename，未知值顯示「未知」，完整路徑與來源識別仍由舊 formatter 呈現。長檔名採可水平捲動欄位。裁決按鈕、非模態視窗及既有輪次/audit 行為沿用。

本票未實作 C2 的差異紅色粗體、同名路徑消歧，也未實作 C3 的多候選持續刷新、裁決移除一致性或重開一致性功能。未修改遠端 Issue 狀態。

## 七項驗收證據

1. **四列、欄標題、順序及所選位置：通過。** 受控 Atlas 衝突 Tk 測試檢查「項目／原結果／新候選」、四列順序、兩側值與顯示位置。
2. **同一捕捉快照：通過。** 真實來源檔案在捕捉後改名，重開彈窗仍顯示捕捉時的檔名及原完整路徑；顯示程式不重新讀取來源。
3. **未知值與來源識別：通過。** 合成捕捉快照涵蓋缺少 SN／時間／路徑，驗證「未知」且不從 opaque source ID 或觀察時間推算；詳細區保留原識別與路徑。
4. **完整詳細內容：通過。** 真 Tk 驗證輪次 ID、衝突 ID、完整來源路徑與原候選證據仍在詳細區。
5. **分隔、尺寸與長檔名：通過。** 真 Tk 檢查初始分隔約 40%，實際拖曳後位置改變；720×360 最小尺寸仍有可操作清單、表格及按鈕；長檔名欄位可水平捲動。
6. **選取、按鈕及非模態：通過。** 真 Tk 切換兩筆衝突驗證摘要／詳細內容不串用；實際關閉按鈕只隱藏視窗而保留待裁決；實際保留原結果按鈕寫出 audit；其他 slot 在彈窗開啟時仍可收集及完成。
7. **真 Tk 端到端與磁碟 audit 重建：聚焦驗收通過。** 受控來源衝突經真實 RoundCoordinator／App／Tk 流程操作，`read_round_audit` 從磁碟重讀得到唯一 `conflict_resolved`，choice 與 conflict ID 正確，且 `audit_complete=True`。

## 實際命令與結果

以下兩個聚焦測試在分支程式提交 `ebe7364` 上以可用的 Tk 桌面工作階段通過：

```sh
cd "B518 Log Solution/B518 Log Solution"
B518_TK_TESTS=1 python3 scripts/run_tests.py test_log_solution_ui.LogSolutionUiTests.test_atlas_round_shows_nonblocking_conflict_and_releases_after_other_slot_finishes
B518_TK_TESTS=1 python3 scripts/run_tests.py test_log_solution_ui.LogSolutionUiTests.test_real_tk_conflict_selection_keeps_both_sections_on_same_snapshot
```

重新取得桌面存取後，再次執行上列兩個聚焦測試，均通過（2 tests，7.561 秒）。`python3 -m compileall -q src tests` 與 `git diff --check d0f4535dc74753cbb6a457828b7b5c1d6ecacac9..HEAD` 通過。專案未發現 `pyproject.toml`、mypy、pyright 或其他既有型別檢查設定；因此沒有宣稱型別檢查通過。

本回合非 Tk 完整模組套件命令：

```sh
cd "B518 Log Solution/B518 Log Solution"
python3 scripts/run_tests.py test_verify_macos_bundle test_log_monitoring test_audit_records test_anonymize_baseline_samples test_platform_registry test_round_archival test_b482_source_adapter test_kvm_display_contract test_configured_monitor test_atlas_source_adapter test_replay_baseline_samples test_machine_profiles test_rswmt_monitoring test_round_retention test_monitoring_round
```

結果：232 tests passed（26.507 秒）。這組命令刻意排除會建立 Tk 視窗的 `test_log_solution_ui`，只作為完整套件的非 Tk 對照。

最終完整套件以桌面存取權限執行 `B518_TK_TESTS=1 python3 scripts/run_tests.py`，結果 **275 tests passed（49.283 秒）**，含完整 `test_log_solution_ui`。一般沙盒中的 Tk 建窗會以 SIGABRT 結束；使用已核准的桌面執行權限後，真 Tk 測試及完整套件均通過。早期 `python3 scripts/run_tests.py test_conflict` 不是有效測試識別，已確認 runner 要求 unittest module 名稱；不列為產品測試結果。


## 固定基準審查

- Standards（基準 `d0f4535dc74753cbb6a457828b7b5c1d6ecacac9`）：沒有文件標準違規或可行性異味發現。
- Spec（相同固定基準）：C1 實作與聚焦驗收相符。首次審查的 P2 指出全套測試證據尚缺；其後 275 項含 Tk 完整套件通過，該交付缺口已解除，沒有未解決的程式審查問題。

聚焦 GUI、完整 UI 檔、完整套件與 Standards／Spec 審查均已有通過證據。完整套件對應程式 SHA `ebe7364`；之後僅新增驗收文件，沒有改動程式或測試。
