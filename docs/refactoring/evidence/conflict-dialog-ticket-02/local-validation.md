# C2 本機驗收紀錄

日期：2026-10-08（Asia/Taipei）

範圍：人工衝突彈窗 C2／GitHub Issue #11

固定 code-review 基準：`332a4518601a8413004b5a1d88baf4b2a89b85d5`

程式提交：`fad583e`（`feat: highlight conflict field differences`）

最後測試提交：`3275bb0`（`test: cover missing conflict source time`）

程式目錄：`B518 Log Solution`

## 起始狀態與 C1 前置確認

- Git 根目錄為此專案根目錄；Python 程式及測試位於 `B518 Log Solution/`。
- C1 已由 `B518-Log-Solution` ancestry 確認包含於固定基準，且 [C1 本機驗收紀錄](../conflict-dialog-ticket-01/local-validation.md) 證明其精簡／詳細分區、拖曳、切換、長檔名及測試收尾修正。
- 原工作樹有未跟蹤文件 `docs/refactoring/ROUND_START_ASSEMBLY_DISCUSSION_2026-10-08.md`。C2 使用獨立 worktree `/private/tmp/B518-ConflictDialog-ticket-02`；該文件未更動、未加入提交。
- 建立本票時本機分支 `ConflictDialog/ticket-02` 不存在。初次即時遠端查詢因網路不可達失敗；之後重新查核確認 Gitea 與 GitHub 的 `B518-Log-Solution` 均為 `341a5ab19880f69d4dd9ce3be110480c604ccd8f`，遠端 C2 分支均不存在。`341a5ab` 僅新增兩份輪次開始規格文件，且其討論文件 SHA-256 與原工作樹未跟蹤檔相同；沒有覆蓋或改寫該內容。已將 `341a5ab` 非破壞性合併入票分支，合併提交 `782ea3f57abf86968d83baa5ee18e67657c3ad15`。

## 實際驗收命令與結果

從 `B518 Log Solution` 執行：

```sh
python3 -m py_compile src/b518_log_solution.py tests/test_log_solution_ui.py
PYTHONPATH=src B518_TK_TESTS=1 python3 -m unittest discover -s tests -p 'test_log_solution_ui.py' -k conflict -v
B518_TK_TESTS=1 python3 scripts/run_tests.py
```

- Python 語法編譯：通過。
- 聚焦衝突 UI：4 tests 通過，使用可存取桌面圖形工作階段的真 Tk；包括受控 Atlas 來源的實際 App 流程、非模態收集、分隔拖曳、裁決／audit 磁碟重建，以及捕捉後來源檔改名仍使用快照。
- 全套含 Tk 測試：275 tests 通過，59.518 秒。
- 專案沒有 `pyproject.toml`、`mypy.ini`、`setup.cfg`、`tox.ini`、`Makefile`、`.flake8` 或 `pyrightconfig.json` 型別檢查設定；未執行或宣稱型別檢查通過。
- `git diff --check`：通過。

## 六項驗收證據

1. **四欄獨立差異樣式：通過。** 真 Tk 測試檢查實際文字範圍標籤的前景色為 `#b00020`，且實際字型 weight 為 `bold`。覆蓋只有結果不同、只有 SN 不同、只有來源時間不同、四欄都不同、同值及兩側皆未知；相同欄位未套差異樣式。
2. **切換與未知值：通過。** 真 Tk 一般選取切換會重建內容及樣式；一側缺少 SN／來源時顯示未知並標示差異，兩側缺少來源時間均為未知且一般文字。原來源識別沒有被當成路徑或檔名。
3. **檔名與目錄消歧：通過。** 不同檔名直接呈現差異；`/line-A/group0-slot1/system/records.csv` 與 `/line-B/group0-slot1/system/records.csv` 的短提示分別顯示 `line-A/group0-slot1/system` 及 `line-B/group0-slot1/system`，兩側都實際紅色粗體，沒有只比較 basename。
4. **相同來源路徑：通過。** 同一路徑結果變更時，來源欄保持一般文字，只有結果欄標示差異。
5. **完整證據與可操作性：通過。** 下方詳細區仍包含完整路徑及原來源識別；真 Tk 視窗維持 720×360 最小尺寸，長檔名可水平捲動，既有底部按鈕仍可見。C1 分隔拖曳流程在受控 Atlas Tk 測試回歸通過。
6. **受控來源與真正 Tk：通過。** 既有 Atlas 來源測試實際經 App／共同輪次擷取衝突，驗證目前欄位值及可見樣式；其他真 Tk 測試涵蓋來源移動後仍顯示已捕捉內容、缺少值、同名多目錄、切換重置與既有操作。

## 實作契約與範圍

- 精簡區及詳細區都取自同一 `RoundConflict` 捕捉內容，不重新讀取來源檔案；時間沿用來源捕捉值，不補造。
- 僅不同欄位的原／新值範圍套用紅色粗體，不整列染色；選取切換時清空並重建內容。
- C2 將單一 `Treeview` 換為支援逐文字範圍樣式的 Tk `Text` 表格，以實際可見文字標籤實現每格獨立樣式；水平捲動、四欄順序、完整詳細區、左側選單及裁決按鈕維持。
- 不包含 C3 的完整持續刷新、裁決移除同步、空狀態與隱藏重開一致性交付。未變更來源解析、裁決規則、保存／關閉／封存／期限／清理或遠端議題。

## 審查與交付狀態

固定 Standards／Spec 雙軸審查執行中；若審查後有程式修改，需重跑受影響測試及全套驗收。最後驗證程式／測試 SHA 為 `3275bb0`；最新主線文件合併及本文件更新都不包含程式或測試修改。

尚未 push、合併至主線或清理分支。審查通過後須先重新查核兩個遠端與所有 push 目的地，推送同名票分支並確認同步；主線合併、驗證及 push 完成後才可刪除票分支。若任何一步受阻，保留專用分支。
