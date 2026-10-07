# 專案摘要：2026-10-07

## Ticket 07 開發記錄（本對話）

- 實際 Git 根目錄為 `B518 Log Solution/`，程式與測試目錄在該根下同名子目錄 `B518 Log Solution/src`、`B518 Log Solution/tests`。本次主線基準 `56f895af0b5bceab73582ab8fec95417068b468e`。Ticket 分支已有子提交 `495e8aaf84ce1af50bbcfd9bace793f955c67b22`（multilingual 文件草稿）且已同步遠端；保留未改寫，Ticket 07 固定雙軸審查基準為 `495e8aaf84ce1af50bbcfd9bace793f955c67b22`。由於該提交仍是分支祖先，合併前須處理其無關文件內容，不能宣稱它未包含於分支歷史。
- 新增背景輪次清理服務，從可信封存 manifest 驗證完整組件、時間與 App 管理路徑；Coordinator 管理 startup／每日／設定變更觸發、保護、重疊合併及關閉協調。持久 ledger 記錄摘要與逐檔刪除意圖，部分刪除可在新 Coordinator 重讀後續作；復原時發現新檔即停止該輪；設定畫面顯示摘要及原因。
- `python3 scripts/run_tests.py test_round_retention`：15 項隔離真實暫存磁碟測試通過。`B518_TK_TESTS=1 python3 scripts/run_tests.py`：264 項完整套件通過（46.081 秒），包含可存取桌面的真正 Tk 設定、期限變更、背景清理、摘要檢視與磁碟資料保護驗收。`compileall`、`git diff --check` 通過。
- macOS Darwin 24.6.0 x86_64、Python 3.8.10、Tk 8.6。Repository 未配置型別檢查工具；不把 compileall 當型別檢查。Ticket 07 雙軸審查、覆蓋複核、主線整合及分支清理尚待完成；不得沿用前次遠端同步紀錄代替本次即時查核。
- 完整實際命令、母規格覆蓋和限制見 [Ticket 07 本機驗收紀錄](evidence/ticket-07/local-validation.md)。

## 多語言訪談共識

後續依 to-tickets 形成 [10 張多語言拆票草案與驗收覆蓋](multilingual-tickets/README.md)，待確認後發布。M1 建立可用主頁切換，M2 相容事件擴充，其他票按來源、App 診斷及操作流程逐批接入；M9 另由既有清理 Issue #8 阻擋，M10 統一發布驗收。M1～M10 尚非 GitHub 票號，原規格 Issue #13 未修改或關閉；本次未實作產品程式。

依使用者要求將已確認討論及 ADR 0009 轉為 [多語言正式規格](MULTILINGUAL_SPEC_2026-10-07.md)，包含 44 項使用者故事與 16 組必要驗收案例，已發布 [GitHub Issue #13](https://github.com/Bowei1121/B518_205_207_ATE/issues/13)，標記 ready-for-agent。沿用已確認的真正 Tk、共同輪次及磁碟重建驗收方向；本次只做文件結構與發布內容核對，未修改產品程式、未執行多語言產品測試。

使用者確認 [美國工廠多語言方案](MULTILINGUAL_DISCUSSION_2026-10-07.md) 符合改動方向，並要求主頁語言按鈕及選單越直覺越好。首版 English／繁體中文、首次英文、記住上次語言，監控及待確認時可即時切換，已開自有視窗保留操作狀態；關閉保存期間暫停切換。全部 App 事件同筆保存固定繁中／英文與訊息識別、參數、必要原始診斷，政策見 [ADR 0009](../adr/0009-bilingual-app-event-records.md)；非輪次事件另存並沿用全域期限，舊檔不重寫。翻譯隨 App 發布，原生檔案選擇器遵照系統語言，中英詞彙表已補入 CONTEXT.md。本次僅保存文件，尚未依此方案修改產品程式。

承接 [2026-10-06 專案摘要](PROJECT_SUMMARY_2026-10-06.md) 與本對話可查證的 Ticket 01 交付結果。

## 本對話前次決策與衝突彈窗新需求

- 2026-10-06 訪談確認穩定性優先，P1／P2 分階段交付；保存失敗保留工作供重試、本次 App 全部未保存輪次完整保存才正常關閉，等待時 UI 可操作。保存期限預設 365 天、工程師可改正整數，從可信封存時間起算，背景清理已到期且完整保存的整輪紀錄，保留未知及未完成資料。
- 政策已存入 ADR 0007／0008，正式規格見 [輪次紀錄生命週期規格](ROUND_RECORD_LIFECYCLE_SPEC_2026-10-06.md)，發布至 GitHub 規格 Issue #1；使用者確認拆票後 T1～T7 已發布為 #2～#8，ready-for-agent 與原生 blocked-by 關係已核對。完整票號對照及驗收覆蓋見 [票號索引](round-record-lifecycle-tickets/README.md)。原規格議題未修改，當次完成時尚未開始產品實作；其後 Ticket 01／02 的實作結果見本摘要其他節。
- 本對話最後發布紀錄提交為 `a6bd86e`，當時已推送 Gitea／GitHub。2026-10-07 讀取主線為 `afe5bde`、工作樹乾淨；這是本次讀取檢查點，不將前次可開工狀態當作當下 tracker 即時狀態。
- 今日新增討論：使用者希望人工衝突彈窗左側保留衝突選單，右上新增精簡資訊比較衝突前後，右下保留原有詳細資訊；使用 grill-with-docs 釐清內容與呈現。此次尚未修改產品程式，精簡欄位及差異呈現待討論，不擅自更改人工裁決或放行政策。

衝突彈窗兩輪答案已確認：固定結果、SN、來源時間及來源檔名；同名不同路徑加簡短目錄提示，缺少來源顯示未知；差異兩側紅色粗體。右側初始 40%／60% 可拖曳，左側選單與底部按鈕維持原位，上下同步更新。使用者其後確認完整文件符合改動方向；已確認方案及驗收方向見 [彈窗討論文件](CONFLICT_DIALOG_DISCUSSION_2026-10-07.md)，作為後續規格與實作依據。目前僅保存文件，尚未依此方案修改產品程式。

依使用者要求以 to-spec 產生 [衝突彈窗正式規格](CONFLICT_DIALOG_SPEC_2026-10-07.md)，包含 28 項使用者故事及 12 組驗收案例，已發布 [GitHub Issue #9](https://github.com/Bowei1121/B518_205_207_ATE/issues/9)，標記 ready-for-agent。沿用已確認的真正 Tk 驗收方向及共同輪次公開行為，未新增來源或裁決政策；僅文件驗證，不宣告產品實作或新增測試通過。

使用者再要求 to-tickets 拆分彈窗規格；[3 張票草案及驗收覆蓋](conflict-dialog-tickets/README.md) 採 C1 基本精簡／詳細分區 → C2 差異與同名來源辨識 → C3 多候選動態一致性。待使用者確認粒度及直接阻擋關係後發布，C1～C3 尚非 GitHub 票號；Issue #9 未修改或關閉，產品程式未因本次拆票改動。

使用者確認「很適當」後，全部三票已發布，C1～C3 對應 GitHub #10／#11／#12，皆 ready-for-agent；#11 原生 blocked-by #10、#12 原生 blocked-by #11，正文及本機也記錄真實票號。完整內容與標籤已核對，原規格 Issue #9 更新時間及狀態未改變。可先執行 #10，尚未認領或實作；最新票號及覆蓋見上述對照表。

## 前次討論與 Ticket 01 交付

- 使用者授權在 `round/ticket-01` 執行生命週期 Ticket 01，逐批驗證、commit／push，必要驗收與 Standards／Spec 審查均通過後自動合併及安全清理分支。
- 已完成 audit writer 約 0.2 秒空閒退出、enqueue 與退出共用條件鎖的安全重啟、共享路徑鎖弱引用回收，以及 audit 搬入 Session 時的來源／目標路徑互斥。
- 五項驗收已勾選；共同輪次公開入口、暫存磁碟、退出後人工衝突處理／警報確認、同步競爭與磁碟重建均有受控證據。聚焦 55 tests、合併後完整 198 tests 通過，雙軸 code review 無未解問題。repository 未配置型別檢查器；語法檢查不等於型別檢查。
- 實作／測試提交 `6008c12`、`f1cd840`；驗收文件提交 `7241c34`；非快轉合併 commit `1453da1ae93733a89756278acad490b4b77a9261`；最終合併與清理紀錄提交 `e19fc7f7b1beb5a5d9444ff35a3c75f51c21e904`。
- 前次完成時已核對 Gitea／GitHub 主線 refs 均為 e19fc7f，本地及兩個遠端 `round/ticket-01` 與失效 tracking refs 已清理；工作目錄停在乾淨的 `B518-Log-Solution`。2026-10-07 本次讀取時本地仍為 e19fc7f，工作樹乾淨；遠端歷史同步結果不當作本日實作基準的即時查核。
- 完整證據見 [Ticket 01 本機驗收紀錄](evidence/ticket-01/local-validation.md)。上述測試是前次結果，本日沒有重新執行產品測試。

## Ticket 02 實作與驗收

- 使用者授權在 `round/ticket-02` 完整執行 [Ticket 02：本輪保存復原](round-record-lifecycle-tickets/02-current-round-save-recovery.md)，逐批驗證、commit／push；全部驗收與固定基準 Standards／Spec 審查通過後合併至 `B518-Log-Solution`，確認所有目的地同步再安全清理分支。
- 已接續 Ticket 01 的 audit writer 生命週期，完成單輪 Session／audit 故障保留與有序重試、audit 初始化失敗重建、保存狀態及真正 Tk 非阻塞重試操作。沒有擴張至跨輪追蹤、正常關閉協調、封存或到期清理。
- 七項驗收均有證據並已勾選。最終完整套件 213 tests 通過，包含真實 Tk、暫存磁碟及重建；聚焦 Session 21、audit 28 tests 通過，`compileall`／`git diff --check` 通過。repository 未配置型別檢查器，未宣稱型別檢查通過。Standards／Spec 雙軸複審無未解問題。
- 固定 code-review 基準 `68b31d5ada3e67e29f04336a7738654f585d4fa0`；最後實作 commit `1b4c8322065a0e390e62a6651a21e41369883b07`。所有五個程式提交及驗收文件均推送至 Gitea 與 GitHub。非快轉合併 commit `61e1e6c77c960052d3f2f39f31ffa24f0af5cb49`；合併後完整 213 tests 再次通過，兩遠端主線同步至合併 SHA 後，安全刪除本地與兩遠端 `round/ticket-02`，並清理 stale tracking refs。最後停在乾淨的 `B518-Log-Solution`；本摘要與清理結果由合併後主線文件提交同步至兩個 push 目的地。
- 完整逐項驗收、TDD 證據、實際命令、環境及同步狀態見 [Ticket 02 本機驗收紀錄](evidence/ticket-02/local-validation.md)。

## Ticket 03 跨輪未保存追蹤（本日後續）

- 使用者授權在 `round/ticket-03` 接續 Ticket 01／02，完成 App 本次執行中的跨輪未保存追蹤、舊輪選取與非阻塞重試。固定 code-review 基準及本次實作主線基準為 `438dd951b6404c5a3f0a900ce08e4285066dd8ea`；即時 fetch 後 Gitea 與 GitHub 主線一致，開始時沒有同名 ticket 分支。
- `RoundCoordinator` 目前持有本次執行中尚未完整保存的輪次，公開提供 `unsaved_rounds()`、按 round ID 查詢／重試，以及 `has_unsaved_rounds` 共用保護狀態。新輪事件依原 round ID 路由；Tk 可選取舊輪、讀取錯誤原因及重試，舊輪事件不更新目前結果看板。完整保存後移除舊輪物件；沒有掃描歷史 Session。沒有加入 Ticket 04～07 的關閉、封存、期限或清理流程。
- 五項 Ticket 03 驗收均已勾選並有證據。聚焦輪次及 UI 77 tests 通過；最終程式 HEAD `64e903e` 的完整套件 218 tests 通過，包含在桌面工作階段實際執行的 Tk 跨輪重試及磁碟重建。語法編譯和 `git diff --check` 通過；repository 未發現型別檢查設定，未宣稱型別檢查通過。逐項命令與證據見 [Ticket 03 本機驗收紀錄](evidence/ticket-03/local-validation.md)。
- 實作提交 `abc5a8b152d56e7daf4ae60d1fee9049aae66fbe`、狀態標籤審查修正 `64e903e`、驗收文件提交 `3168ec7`／`1b2fb51` 均已推送至 `origin` 的 Gitea、GitHub 兩個 push URL；Standards／Spec 雙軸複審均無未解問題。確認最新主線 `e9a1008232448d34a05f5528ff7af6576d19aa48` 為固定基準的後續文件提交且工作樹乾淨後，建立 Ticket 03 merge commit `d4244701656c4b2daef17ba9daece3db8e0d1856`。合併後完整套件 218 tests 通過（32.157 秒），`git diff --check` 通過。合併 commit 後的驗收文件提交 `946fcbd5a945b526b99309b8da13a1e6866e9682` 已推送至兩個目的地，並即時核對 refs 相同；本地與兩遠端 `round/ticket-03` 已安全刪除，tracking refs 已 prune。最後工作樹乾淨並停在 `B518-Log-Solution`。
- 開始時原專案工作樹的 `docs/refactoring/CONFLICT_DIALOG_DISCUSSION_2026-10-07.md` 有未提交修改；Ticket 03 使用獨立 worktree，未觸碰該修改。合併前即時查核時，該文件更新已由主線提交 `e9a1008` 收錄，主線工作樹乾淨，因此沒有 stash 或把未提交資料納入本票。

## Ticket 04 正常關閉協調（本日後續）

- 使用者授權在 `round/ticket-04` 接續 Ticket 01～03，完成正常關閉時停止新增監控、背景協調本次執行全部輪次保存、顯示狀態及錯誤、支援重試／取消，只有全部必要 Session 與 audit 完整保存後才銷毀視窗。沒有擴張至可信封存、期限或到期清理。
- 固定 code-review 基準 `ddd19f979dc1d241e3bf66c45f15ff4c0e831bb5`，Ticket 01～03 已包含於此工作基準。開始前另在隔離 worktree 即時核對本地及 Gitea／GitHub refs；當時兩遠端主線均為固定基準，專用分支不存在。
- App 現透過 `RoundCoordinator` 公開關閉狀態與請求入口，在背景等待來源準備、停止交接、每輪 Session／audit flush，失敗可重試或取消。關閉中允許人工衝突裁決及警報確認；完整保存快照會原子凍結已完成輪次的人工操作，避免最後檢查與視窗銷毀之間新增未保存紀錄。取消不重啟來源、保存工作繼續，熱鍵只在成功關閉後釋放。歷史 Session 不會被掃描。
- Ticket 04 六項驗收皆已以暫存磁碟及真正 Tk 案例驗證。以 Event 控制來源準備、audit 故障／重試與人工操作交錯；延遲超過原兩秒界線時視窗及 `after` 事件仍可用。跨輪恢復、取消後再次關閉、衝突及警報人工操作後的 audit 由磁碟讀取器重建，確認內容及 round ID 正確。
- 聚焦 `PYTHONPATH=src:tests python3 -m unittest test_monitoring_round test_log_solution_ui`：85 tests 通過（24.022 秒）；完整 `python3 scripts/run_tests.py`：Ticket 分支最新測試 fixture commit `60ddc79` 上 225 tests 通過（39.615 秒），此前完整 suite 也有 225 tests 通過。`python3 -m compileall -q src tests` 與 `git diff --check` 通過。Tk 測試在可存取桌面圖形工作階段實際執行。Repository 沒有型別檢查器設定，未宣稱型別檢查通過。完整套件曾因既有平台啟動測試讀取共用 `/tmp` 偏好檔而逾時；改為每次使用隔離 TemporaryDirectory 後，完整套件通過。
- Standards 首審的準備事件私有存取已改由公開 `wait_until_prepared()`；close status 重複 predicate 改為共用判定，`CloseSnapshot.error` 改名 `message`。Spec 複審指出快照與人工操作可能競爭；以輪次完成凍結及 Event 競爭測試修正。固定基準 Standards／Spec 最終複審均無未解問題，最終也檢視測試 fixture follow-up `60ddc79`。實作提交 `7a241be380b55cd237908554d60fcb584f3ebfc8`、測試 fixture follow-up `60ddc79c27c1517b416b2748729b4e23784d2ab2` 均同步至 Gitea、GitHub；實際命令與逐項證據見 [Ticket 04 驗收紀錄](evidence/ticket-04/local-validation.md)。
- Ticket 04 第一次合併 commit `3e4f0c7` 後完整套件揭露測試 fixture 受共享 `/tmp` 偏好污染，故保留分支；隔離 fixture 後在 branch `60ddc79` 完整套件 225 tests 通過。重新 fetch 確認主線工作樹乾淨、Gitea／GitHub 主線一致於 `9bbedf0` 且只有固定基準後續文件更新，之後最終合併 commit `2172f8f3603532122edbc82fc370c79222318840` 將最新 Ticket branch `faf0c4c` 整合至主線。合併後完整套件 225 tests 再次通過（41.980 秒），compileall 與 diff-check 通過。主線與最終驗收文件已推送至 Gitea、GitHub，兩者 refs 相同；安全移除乾淨 worktree、本地分支及兩遠端 `round/ticket-04` 後完成 prune 查核。最後工作樹乾淨並位於 `B518-Log-Solution`；未使用強制推送或強制刪除。

## Ticket 05 可信輪次封存（本日後續）

- 使用者授權在 `round/ticket-05` 接續 Ticket 01～04，將只有已結束、沒有待確認事項且 Session／audit 完整保存的本次執行輪次，寫成有版本、round ID、帶時區實際封存時間與 SHA-256 完整性資料的持久封存資訊。沒有加入 Ticket 06／07 的期限設定、到期判定、排程或實際刪除。
- `RoundCoordinator` 公開回報本次執行輪次的保存／封存狀態，背景驗證磁碟組件並支援重試。封存證據涵蓋同輪分散 audit 與 Session 檔；未知版本、輪次不一致、未解決衝突／警報、缺失或損壞的必要組件均保持受保護。新增必要事件會撤銷舊封存對目前內容的代表性；人工確認或修復後使用注入時鐘的當下時間。不掃描歷史 Session；未具可信封存時間的舊資料維持可讀並保留。
- Ticket 05 六項驗收均有真實暫存磁碟及新讀取器證據，含人工確認後封存、數日後以實際時刻封存、分散組件完整性驗證、故障與修復、事件競爭、foreign round 身分替換拒絕、Tk 未保存／完整保存／封存狀態及舊格式可讀。聚焦 `python3 scripts/run_tests.py test_round_archival test_monitoring_round test_audit_records test_log_solution_ui` 為 130 tests 通過（27.251 秒）；固定程式提交 `d679b9992a7582169352c8f745a408cd2fe34d82` 完整 `python3 scripts/run_tests.py` 為 242 tests 通過（36.113 秒）；`compileall` 與 `git diff --check` 通過。Tk 在可存取桌面工作階段執行。Repository 沒有 mypy／pyright 或其他型別檢查設定，未宣稱型別檢查通過。
- 固定 Standards／Spec 基準 `a4a00d5fd6ca7ea4fdb6c2e1482cf2c78d244de5`。複審指出封存寫入需比對 coordinator 預期 round ID，及脫離追蹤物件的已封存輪磁碟驗證失敗時須維持 close 阻擋；均已修正並以回歸測試覆蓋。Standards 與 Spec 最終複審均無未解問題。實作提交 `0798043`、驗證修正 `938542c`、分支驗收文件提交 `6feebe2` 已推送至 Gitea 與 GitHub。完整命令、逐項證據與環境限制見 [Ticket 05 本機驗收紀錄](evidence/ticket-05/local-validation.md)。
- 合併前即時 fetch 確認主線 Gitea／GitHub refs 均為固定基準 `a4a00d5`，兩端 Ticket 分支均為 `6feebe2`。使用乾淨主線 worktree 合併，merge commit `fbd3ac0f09381819e87b40cb17f190145d190f88`；合併後完整套件 242 tests 通過（38.883 秒）。主線摘要提交 `3d405236c7564b725b34c40587ef782670e7f1c9` 已推送至 Gitea／GitHub，即時 fetch 確認兩地主線 refs 一致且包含 merge SHA。確認同步後安全刪除兩遠端 `round/ticket-05`、本地分支及 stale tracking refs，未使用強制刪除。最後清理證據的文件提交也推送至兩個目的地；最後工作目錄切回 `B518-Log-Solution`。完整證據見 [Ticket 05 本機驗收紀錄](evidence/ticket-05/local-validation.md)。

## Ticket 06 全域保存期限設定（本日後續）

- 使用者授權在 `round/ticket-06` 完成全域輪次保存天數設定。起始固定 Standards／Spec review 基準為 `f1d6e4768626b73732653ec7d978e9fa41b87bf7`；即時檢查確認 Ticket 01～05 已在基準，本地與 Gitea／GitHub 主線 refs 一致，專用分支原先不存在。
- 已在偏好 Store 加入預設 365 天及正整數持久讀寫，沿用原子替換；profile 保存與匯入保留全域設定，profile 匯出維持原契約。設定頁顯示生效值、錯誤及可信封存時間／完整 24 小時／下次背景清理提示。本票未加入到期掃描、排程或刪除。
- Ticket 06 五項驗收均有真實暫存偏好檔、新 Store 磁碟重讀、真正 Tk Entry／Button 操作及 Session 檔案前後比對證據。舊格式缺少欄位及全新偏好檔均預設 365；測試涵蓋 180、730、無效輸入、原子替換失敗、profile save/import/export、跨重啟與設定失敗。最終程式／測試 commit `70db40709ade55d4605959df4207afaccce3ebed` 完整 `python3 scripts/run_tests.py` 248 tests 通過（38.673 秒），`compileall`、`git diff --check` 通過。Repository 無型別檢查設定，未宣稱型別檢查通過。真正 Tk 測試於 macOS 15.7.9、Python 3.8.10 桌面工作階段執行。
- Standards／Spec 固定基準雙軸複審均無未解問題。首輪 Standards 指出正整數驗證重複，已改由 Store 作唯一規則來源並重跑受影響測試及完整套件。Ticket 06 本機驗收文件見 [Ticket 06 驗收紀錄](evidence/ticket-06/local-validation.md)。
- 程式／測試 commits `475a4e4`、`5e3a962`、`32ceaf8`、`70db407` 及分支驗收文件 commit `b3d1796` 均已推送至 Gitea 與 GitHub。一般合併 commit `2c75f07f44b0b3dee9eff22d387b0385ababc3eb` 合併 Ticket branch `b3d1796` 至固定基準 `f1d6e47`；合併後完整套件 248 tests 通過（44.394 秒），compileall 與 diff-check 通過。主線合併 SHA 已同步至兩遠端並經即時 refs 查核；確認同步後刪除兩遠端及本地 `round/ticket-06` 並 prune，移除合併 worktree，最後停在 `B518-Log-Solution`。原有未提交 `CONTEXT.md` 修改與兩個未追蹤文件均保持未提交。完整證據見 [Ticket 06 驗收紀錄](evidence/ticket-06/local-validation.md)。
