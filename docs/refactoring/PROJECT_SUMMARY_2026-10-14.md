# 專案摘要 — 2026-10-14

時區：Asia/Taipei。此摘要承接 2026-10-13 的已查證內容，當日完整前情與 H1–H3 歷史分別見 [2026-10-13 project summary](PROJECT_SUMMARY_2026-10-13.md) 及各票驗收證據；不補造未保存的對話內容。

## 今日目標與開始基準

- 使用者指定完成歷史事件查詢 H4「持久索引與增量查詢」（GitHub #41，父規格 #37），明確不是其他系列同號票。範圍、七項驗收、禁止事項及合併／遠端清理程序見 [H4 ticket](historical-event-query-tickets/04-incremental-index.md)。父規格與已確認討論為 `HISTORICAL_EVENT_QUERY_SPEC_2026-10-13.md`、`HISTORICAL_EVENT_QUERY_DISCUSSION_2026-10-13.md`；不修改遠端 Issue。
- Git 根目錄與 Python 專案目錄已分別確認。H4 開始前固定 review base：`bbcfc1b0ddeba66e54b5de1291dbeb476dcb11c3`。當時兩個 push 目的地的 `B518-Log-Solution` 均指向該 SHA，未有 H4 遠端分支。H3 `75adc7623fc0b2313cbfc231766b5e4edb15b017`、H1/H2 已在 ancestry；H3 真實分頁、固定集合、精簡快照／按需詳細、SQLite close/open race 修正、暫存目錄清理調查、完整含 Tk 及雙軸 review 證據均查驗，H3 是 H4 唯一直接依賴。
- 起始工作目錄的七個 tracked 檔案（732 insertions）屬先前未提交內容，已完整保存到 `stash@{0}` 和 `/private/tmp/h4-preexisting-20261014.patch`，patch SHA-256 `d1844691a39886a0dce823fcbc6b701933fc50aee400aceea39d924e2370bf28`。既有 stash、Mac mini、BT-Codex 及語言刷新 worktree 未變更。先前修改不在 H4 commit 中；結束時依原狀保護／還原狀態仍須記錄。
- 拆票 README 初期 H2/H3 狀態文字已與 H3 完成證據及 Git ancestry 不符，H4 交付文件已修正此陳舊狀態；不依舊敘述判定前票阻擋。

## H4 實作與驗證進度

- `HistoricalEventQuery/ticket-04` 已有首個程式／測試 commit `12c4dd6268dd8220c928237ff33764d187cc0a29`，初次 push 使用 upstream tracking，推送到 Gitea 與 GitHub。SQLite v1 衍生索引已接至公開歷史查詢服務與實際 App；新服務可重用磁碟索引，來源版本檢查包括 device/inode/size/mtime_ns/ctime_ns，解析前後版本一致且交易成功才視為可靠。分頁仍經 H3 固定快照，詳細仍在選取後取得。來源失敗／競態不快取為成功，索引不改原始格式、不影響清理資格。
- 新增及修改測試涵蓋重啟重用、未變更查詢、不同日期範圍、同大小保留 mtime 內容變動、追加、同路徑替換、移動、刪除、App journal 整份替換、audit/legacy 優先與去重、掃描中追加、取消 rollback、索引版本拒用／重建、時區重用與固定結果。真正 Tk App 路徑新增磁碟索引重用、查詢、頁面、選取詳細、切語和來源 bytes 核對。
- 可重現三來源／450 事件／五頁 fixture：首次建立三次 source bytes 各 523,329，完整解析 3 源；新服務重啟重用與未變更查詢各三次皆 source bytes 0、解析 0／重用 3；單源改變三次讀取約 175–177 KB，只解析 1／重用 2；翻頁／選取詳細三次 source bytes 0。完整耗時、tracemalloc 峰值、索引／快照大小、雜湊與限制見 [H4 local validation](evidence/historical-event-query-ticket-04/local-validation.md) 及同目錄 `benchmark.py`。小型工程 fixture 不代表 H8 容量或工廠速度。
- 正確 Python 目錄、桌面 runtime `/opt/anaconda3/bin/python3` Python 3.11.7／Aqua Tk 8.6.12 執行 `B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py` 通過 439 tests／168.128 秒／exit 0，無 Tk skip。預設 Python 3.8.10/Tk 8.6 的桌面完整套件出現 `Tcl_AsyncDelete` exit 134，固定 review base 的隔離 worktree 同樣重現；因此不宣稱 Python 3.8 suite 通過，日誌與環境限制均保留。repo 沒有型別檢查設定，不宣稱 typecheck。
- 固定基準雙軸 review 均通過，沒有阻擋：Standards 未找到 documented-standard／ADR 違規；Spec 確認 H4 分配有覆蓋。非阻擋建議為版本 tuple 重複可考慮集中，以及 bytes 觀測是 reader 交付 parser 的 UTF-8 bytes、非 OS 級物理磁碟 I/O；詳細限制與完整審查摘要已寫入 H4 驗收證據。磁碟保存 event JSON 是為固定 H3 詳細資料快照，列表記憶體仍為精簡摘要，選取才讀詳細。
- 已更新 H4 ticket、票總覽與父規格 H4 coverage；新增本日摘要、成本 benchmark 及測試日誌。最後文件提交、合併前遠端直查、主線合併後完整驗證、全部 push 目的地直查、票分支／本票 worktree 清理仍待完成，未越過合併門檻。

## 範圍界線與下一步

H4 不包含 H5 完整錯誤提示／降級／恢復介面、H6 完整固定結果與正式保存／清理競態整合、H7 完整 icon／提示／鍵盤／即時雙語、H8 5 萬及 216 萬筆容量／全規格收尾。未改監控、裁決、警報確認、產品放行、保存格式、期限、封存、清理、KVM、journal 技術、語言偏好或原始診斷；未宣稱父規格、工廠驗收或正式部署完成。

後續依序：完成固定 base `bbcfc1...` 的 Standards／Spec 平行 review；修正阻擋並重跑受影響驗證；提交及推送文件；重新確認主線與全部遠端 SHA；只有全部驗收通過才安全快轉合併至 `B518-Log-Solution`，主線再跑完整含 Tk 套件並推送；逐一直接查詢 GitHub/Gitea；遠端一致後才正常刪除本票分支和乾淨專用 worktree，最後切回主線。不得觸碰其他票分支、stash、worktree 或前置修改。
