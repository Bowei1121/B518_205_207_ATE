# C3 人工衝突彈窗本機驗收紀錄

日期：2026-10-08（Asia/Taipei）

專案根目錄：`B518 Log Solution`

Python 程式／測試目錄：`B518 Log Solution/B518 Log Solution`

工作分支：`ConflictDialog/ticket-03`

固定 code-review 基準：`00a73526bc84b1862835672e3d329ddca06a92f4`

最後驗證程式／測試 SHA：`db567ffb097e253dc9e7b8e23ba8e4a4f6b908a2`

## 起始基準及前票確認

- 開始前在 Git 根目錄確認分支為 `B518-Log-Solution`、工作樹乾淨、程式目錄為 `B518 Log Solution/`，並列查本地分支、所有遠端、`origin` fetch URL 及兩個 push URL。當時主線為 `00a73526bc84b1862835672e3d329ddca06a92f4`，Gitea 與 GitHub 的主線 SHA 相同，兩邊都沒有 `ConflictDialog/ticket-03`。
- 固定審查基準 `00a73526...` 是實際開始修改時的主線 commit，不沿用 C1/C2 review base。其 ancestry 含 C1 合併提交 `d7d82e8405ef8839820cc727b15f256c24353389` 及 C2 合併提交 `a56cfa5b0d532cfcb582794d5e76150cd7aeed9d`。C1/C2 的實際程式、真 Tk 測試與驗收紀錄亦已查閱。
- README 舊文曾同時聲稱 C2 等待審查及 C3 尚未實作。Git ancestry、C2 證據檔及開始前即時主線／遠端查詢確認 C2 已合併、票分支已清理；本次已更正該過時描述。
- 起始未提交／未追蹤變更：無。本票提交沒有包含其他工作文件。

## 交付內容

`_clear_conflict_comparison()` 現在會清空精簡／詳細顯示並停用「保留原結果」與「採用新候選」按鈕。選取不存在、共同輪次快照消失，或選取的 conflict ID 已從最新待裁決集合移除時，都走清空路徑；目前選取仍有效時才重新啟用兩個按鈕。沒有改動來源解析、衝突產生／去重、候選排序、裁決政策、保存流程或產品放行規則。

TDD 先新增真 Tk 無選取案例。紅燈測試確認清單空選時原本已會清空內容，但兩個裁決按鈕仍為 `normal`、可操作；最小實作後，內容維持清空、顯示未知位置且兩個入口為 disabled，測試轉綠。

主要 C3 端到端案例使用已註冊 `sample-json` 平台，而非直接呼叫 UI 私有 helper：測試建立真實暫存 JSONL，設定並啟動實際 `B518LogSolutionApp`，由平台 adapter 將同位置兩筆衝突及另一位置衝突送入共同 RoundCoordinator，再用真正 Tk 清單和按鈕互動。測試在第二筆同位置衝突被選取時追加跨位置衝突，確認刷新後仍為同一 conflict ID，位置、摘要與詳細內容一致；檢查真實渲染的紅色前景及粗體，修改來源 JSONL 後仍顯示捕捉快照，隱藏／重開、採用新候選、保留原結果、全部清空後禁用裁決。最後從新讀取的 audit 及 Session `results.csv` 驗證三個位置結果、三筆 `conflict_detected`／`conflict_resolved` 及其 ID 一致。

另有 Event 控制的 monitor 到共同輪次背景候選加入測試：在選取非首項時加入同位置候選並刷新，選取仍保留原衝突識別；隱藏後更新另一位置、重開、逐項裁決後回到原有後續項目，最後清空。該案例並重建真實 audit，確認所有偵測衝突都有對應裁決。

## 七項驗收

1. **同／跨位置候選的雙區一致：通過。** `test_sample_platform_conflicts_stay_consistent_through_real_tk_and_disk_rebuild` 以真實平台來源同輪產生兩個 slot 1 衝突及一個 slot 2 衝突；選取第二個 slot 1 衝突後再加入 slot 2 候選，仍保持相同 ID、位置、SN、精簡及詳細內容。C3 每個顯示內容由共同輪次當前 `RoundConflict` 快照提供。
2. **刷新時保持有效選取：通過。** sample-platform 真 Tk 案例涵蓋跨位置候選加入後仍保留第二個同位置 conflict ID；`test_conflict_review_tracks_same_slot_candidates_through_refresh_resolution_and_reopen` 用 Event 控制同位置背景候選加入時的刷新交錯，亦確認非首項選取不因新增候選改變。
3. **裁決移除、空狀態及隱藏重開：通過。** 真正點擊「採用新候選」後，該 ID 消失且 UI 選取下一筆；「保留原結果」逐項處理其餘候選。全數處理後，清單無選取、比較／詳情清空、顯示位置未知且按鈕停用。關閉入口只隱藏，重開從當下 pending 集合刷新。另有明確取消清單選取的測試驗證裁決入口不可操作。
4. **捕捉後來源變動：通過。** sample-platform 測試在候選捕捉後改寫來源 JSONL，再選取與重開彈窗，仍顯示原 SN／狀態／來源證據。C1/C2 驗收另以來源檔改名驗證同一快照契約。
5. **逐項按鈕、非模態及其他位置收集：通過。** 真 Tk 操作採用新候選及保留原結果，只移除當前選取；關閉不裁決。第三位置仍在彈窗開啟時收到其最終資料，證明其他位置可繼續收集。
6. **未知來源、audit、放行與 KVM 契約：通過。** 未知同輪來源 FAIL／不提供人工採用由現有 `test_unknown_atlas_identity_change_is_visible_as_fail_and_audited_without_reason` 與共同輪次測試回歸；停止收集不等同結果放行，三位置結果於候選處理完成後才由磁碟重建為可放行。`test_kvm_display_contract.py` 及完整套件回歸通過。
7. **真 Tk、磁碟重建與母規格十二案例：通過。** 真 Tk 平台路徑、audit／Session 磁碟讀取已驗證；母規格十二案例逐項結果與 C1/C2 證據適用性列於 [母規格覆蓋表](../../CONFLICT_DIALOG_SPEC_2026-10-07.md#2026-10-08-c3-本機覆蓋紀錄)。這是受控平台驗收，不宣稱現場設備驗收。

## 測試與檢查

下列命令均從 `B518 Log Solution/B518 Log Solution` 執行，使用可存取桌面圖形工作階段的環境：

```sh
PYTHONPATH=src B518_TK_TESTS=1 python3 -m unittest discover -s tests -p 'test_log_solution_ui.py' -k conflict_review -v
PYTHONPATH=src B518_TK_TESTS=1 python3 -m unittest discover -s tests -p 'test_log_solution_ui.py' -k sample_platform_conflicts_stay_consistent_through_real_tk_and_disk_rebuild -v
B518_TK_TESTS=1 python3 scripts/run_tests.py
python3 -m py_compile src/b518_log_solution.py tests/test_log_solution_ui.py
git diff --check
```

- 真 Tk 聚焦 `conflict_review`：2 tests passed。
- 真 Tk `sample_platform_conflicts_stay_consistent_through_real_tk_and_disk_rebuild`：1 test passed。
- 最終程式／測試 SHA `db567ffb097e253dc9e7b8e23ba8e4a4f6b908a2` 完整含 Tk 套件：**279 tests passed，63.887 秒**。
- Python 編譯與 `git diff --check` 通過。
- 已檢查專案未設定 mypy、pyright 或其他既有型別檢查工作流程；因此未宣稱型別檢查通過，亦未為本票新增工具設定。
- 在沙盒無桌面權限時 Tk 建窗曾中止；切換至已授權可存取桌面圖形工作階段的執行後，所有真 Tk 聚焦案例及完整套件通過。此為測試環境限制，非產品失敗。

## Standards／Spec 審查

- 固定審查基準：`00a73526bc84b1862835672e3d329ddca06a92f4`。以此基準審查本票最終程式／測試差異，沒有隨 HEAD 推進。
- Standards：最終複審沒有未解決發現。初次提醒測試曾檢查私有範圍欄位；已改為直接檢查 Text widget 上的可見文字樣式，最終沒有此依賴。
- Spec：初次指出多候選主驗收需使用註冊平台至實際 App/Tk，並需保留非首項選取。新增 `sample-json` 真實暫存來源流程，並在第二候選保持選取時追加另一位置候選；最終複審確認沒有未解決規格缺口。審查者未代替實際測試執行；測試結果以上列本機命令為準。
- 六項受控行為已由實際測試驗證；C3 第七項在完整含 Tk 套件及本文件十二案例矩陣完成後勾選。C1/C2 不重複宣告為 C3 新測試，僅引用已整合版本仍適用的驗收紀錄。

## 提交與遠端狀態

| SHA | 內容 |
| --- | --- |
| `2bd373595cba5db934d0f4eb883c86feb75cb19c` | 修正無有效衝突選取時清空顯示並停用裁決按鈕；含首個紅綠測試 |
| `72194dd9735baa4eab9a3dcef485113a3081932d` | 多候選刷新、逐項處理、隱藏重開與磁碟 audit 測試 |
| `5827cab47be6d7cd890ea15d61127cfeef7c2150` | 真實 sample-json 平台至 App/Tk、差異樣式、來源變動及磁碟重建測試 |
| `db567ffb097e253dc9e7b8e23ba8e4a4f6b908a2` | 真實平台刷新時保留非首項選取的額外驗收 |

首次 push 已設定 upstream。票分支文件最終提交 `c1206b99ab5e2e8b9adda7c5933276cd551eed64` 已推送至 Gitea 與 GitHub。

## 合併後驗證與清理

- 目標分支在合併前工作樹乾淨，且本地與 `origin/B518-Log-Solution` 均為兩個 push 目的地即時確認的最新 SHA `00a73526bc84b1862835672e3d329ddca06a92f4`。以一般 `--no-ff` 合併 `ConflictDialog/ticket-03`，實際合併 commit：`965d4224218fc96526e8e97141e3bb54b1ec70df`。
- 在該合併 SHA 上執行 `B518_TK_TESTS=1 python3 scripts/run_tests.py`：**279 tests passed，53.411 秒**。
- `git push origin B518-Log-Solution` 成功推送至 Gitea 與 GitHub；隨後分別以 `git ls-remote` 即時確認兩邊 `B518-Log-Solution` 都是 `965d4224218fc96526e8e97141e3bb54b1ec70df`，再刪除兩邊的 `ConflictDialog/ticket-03`。本地票分支以 `git branch -d` 安全刪除；沒有使用強制推送或強制刪除。
- 正式工作樹位於 `B518-Log-Solution`。本驗收紀錄、票 README 與專案摘要已包含在提交 `8aa109faa54adb0aecaa55e2fd2124ebeb8302ce`；推送後分別以 `git ls-remote` 確認 Gitea 與 GitHub 的主線均為該 SHA，兩邊及本地均不存在 `ConflictDialog/ticket-03`。

未修改或發布任何遠端議題狀態。
