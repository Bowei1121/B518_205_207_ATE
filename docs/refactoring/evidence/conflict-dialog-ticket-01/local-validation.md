# C1 人工衝突彈窗本機驗收紀錄

日期：2026-10-08（Asia/Taipei）

專案根目錄：`B518 Log Solution`

Python 程式／測試目錄：`B518 Log Solution/B518 Log Solution`

工作分支：`ConflictDialog/ticket-01`

固定 code-review 基準：`d0f4535dc74753cbb6a457828b7b5c1d6ecacac9`

最後已驗證程式提交：`ebe7364`（其父提交 `5240a21`）

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

以下兩個聚焦測試在分支程式提交 `ebe7364` 上曾以可用的 Tk 桌面工作階段通過：

```sh
cd "B518 Log Solution/B518 Log Solution"
B518_TK_TESTS=1 python3 scripts/run_tests.py test_log_solution_ui.LogSolutionUiTests.test_atlas_round_shows_nonblocking_conflict_and_releases_after_other_slot_finishes
B518_TK_TESTS=1 python3 scripts/run_tests.py test_log_solution_ui.LogSolutionUiTests.test_real_tk_conflict_selection_keeps_both_sections_on_same_snapshot
```

本次後續靜態檢查：`python3 -m compileall -q src tests` 與 `git diff --check` 通過。專案未發現 `pyproject.toml`、mypy、pyright 或其他既有型別檢查設定；因此沒有宣稱型別檢查通過。

本回合非 Tk 完整模組套件命令：

```sh
cd "B518 Log Solution/B518 Log Solution"
python3 scripts/run_tests.py test_verify_macos_bundle test_log_monitoring test_audit_records test_anonymize_baseline_samples test_platform_registry test_round_archival test_b482_source_adapter test_kvm_display_contract test_configured_monitor test_atlas_source_adapter test_replay_baseline_samples test_machine_profiles test_rswmt_monitoring test_round_retention test_monitoring_round
```

結果：232 tests passed（26.507 秒）。這組命令刻意排除會建立 Tk 視窗的 `test_log_solution_ui`，不能代替完整含 Tk 的專案套件。

完整 `test_log_solution_ui` 曾有測試 teardown 與背景 Session／archive 寫入競爭，TemporaryDirectory 清理偶發失敗；另一次測試檔整體執行曾通過，但不是最終完成的全專案套件結果。本次嘗試重新啟動 Tk 時，最小命令 `python3 -c 'import tkinter as tk; r=tk.Tk()'` 以 exit 134／SIGABRT 結束，無法重新執行 GUI 驗收。`python3 scripts/run_tests.py test_conflict` 不是有效測試識別，已確認 runner 要求 unittest module 名稱；不列為產品測試結果。


## 固定基準審查

- Standards（基準 `d0f4535dc74753cbb6a457828b7b5c1d6ecacac9`）：沒有文件標準違規或可行性異味發現。
- Spec：C1 實作與聚焦驗收相符；審查指出母規格的全套測試交付門檻尚未確認（P2）。上述完整 UI／專案測試阻擋仍未解決。

因此，聚焦驗收項目有既有真 Tk 證據，非 Tk 測試模組 232 項通過，但**最終完整 UI／全專案測試尚未通過確認**。須在可成功建立 Tk 視窗的桌面工作階段重跑兩個聚焦案例、完整 UI 檔與完整 `B518_TK_TESTS=1 python3 scripts/run_tests.py`，再解除 Spec 審查所列交付門檻，才可進入合併及分支清理。這些門檻未完成，應保留 `ConflictDialog/ticket-01`。
