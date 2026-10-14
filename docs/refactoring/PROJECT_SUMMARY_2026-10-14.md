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
- 合併前直接查兩遠端後，乾淨本機 `B518-Log-Solution` 於 `e13f54d539797147d0b66840e1aa26e94c34d9b8` fast-forward（無 merge commit）。兩次 post-merge Python 3.11.7 全套均在首次歷史 UI 類別 Tk 建窗時以 AppKit `NSMenuItem`／`Tk_CreateConsoleWindow` uncaught `NSException` exit 134 中止；完整 runtime／stack log 已保存。固定基準同 runtime 全套則完成 429 tests，但有一項 H3 測試的固定日期資料 `StopIteration`；基準同組 86 tests 含 Tk 通過。H4 版本全套在 merge 前曾通過 439 tests，H4 對應 query+Tk 組合後 Tk setup 仍中止；該 runtime 互動原因未釐清。故本機已整合，但主線未推送、未清理 ticket branch/worktree；不宣稱 post-merge 驗收完成。詳見 H4 local validation。
- 已更新 H4 ticket、票總覽與父規格 H4 coverage；新增本日摘要、成本 benchmark 及測試日誌。文件尚有本次失敗證據待提交推送；全部 push destination 最後 SHA、分支／本票 worktree cleanup 未完成，受 post-merge Tk 阻擋。

## 範圍界線與下一步

H4 不包含 H5 完整錯誤提示／降級／恢復介面、H6 完整固定結果與正式保存／清理競態整合、H7 完整 icon／提示／鍵盤／即時雙語、H8 5 萬及 216 萬筆容量／全規格收尾。未改監控、裁決、警報確認、產品放行、保存格式、期限、封存、清理、KVM、journal 技術、語言偏好或原始診斷；未宣稱父規格、工廠驗收或正式部署完成。

後續先調查可重現的 post-merge Aqua Tk 啟動 abort，必要時在真正桌面 session 修復／重驗；不得以單次成功掩蓋失敗。完整主線 suite 通過後，才提交／推送失敗與最終驗收文件、直接查詢所有遠端、推送主線，再確認 SHA 一致後刪除本票分支與專用 worktree並留在主線。不得觸碰其他票分支、stash、worktree 或前置修改。
