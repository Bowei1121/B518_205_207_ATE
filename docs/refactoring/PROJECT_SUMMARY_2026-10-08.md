# 專案摘要：2026-10-08

承接 [2026-10-07 摘要](PROJECT_SUMMARY_2026-10-07.md) 與本對話可查證的決策；時間基準 Asia/Taipei。

## 前次討論與結果

- 人工衝突彈窗已確認左側選單、右上四項精簡對照、右下詳細內容、差異兩側紅色粗體與可拖曳 40%／60% 分區。規格 GitHub #9，三張工作票 #10→#11→#12；發布內容、標籤與原生依賴已於前次核對，未在本對話實作彈窗。
- 美國工廠多語言方案已確認：首版 English／繁體中文、主頁右上直覺語言選單、首次英文、記住上次選擇。監控與待確認可即時切換，自有視窗保留輸入／選取；關閉保存暫停切換，原生選檔系統文字例外。
- ADR 0009 決定所有 App 事件同筆固定保存繁中／英文、訊息識別、參數及必要原始診斷；舊檔不重寫。無輪次事件另存、沿用全域期限並從自身事件時間起算，待補存受保護；輪次仍使用封存時間。翻譯集中且隨 App 發布，共用中英術語。
- [多語言規格](MULTILINGUAL_SPEC_2026-10-07.md) 已發布 GitHub #13，包含 44 項故事及 16 組驗收，ready-for-agent；正式規格提交 `56f895a` 已同步 Gitea／GitHub。
- 昨日形成 10 張 M1～M10 草案並保存於 `495e8aa`，當時因共享工作區切換，提交位於 `round/ticket-07`。其他工作其後合併 Ticket 07 時明確排除多語言草案，主線未含這 11 個草案檔案；原提交仍可取回。

## 今日查核與拆票交付

- 使用者確認十張拆票「適當」，授權依 to-tickets 發布核准票及依賴。
- 本次起始主線為 `B518-Log-Solution`、`f4ae65d`，工作樹乾淨。已從 `495e8aa` 精確恢復十張核准草案及索引，不帶入其他分支程式變更。
- 前次摘要記載 Ticket 07 背景整輪清理已合併，受控完整 274 tests 通過；這是既有證據，本日未重新執行。發布時既有 GitHub #8 仍為 OPEN；依核准圖保留 M9→#8 外部依賴，不擅自關閉既有議題。
- 本次僅保存文件及發布工作票，不修改產品程式、不宣告多語言實作或新產品測試通過。正式 bundle／目標環境驗收仍依個別票證據判斷。

- 十張核准票已發布為 GitHub #14～#23（M1～M10），全部 ready-for-agent；完整正文、本機對照及原生 blocked-by 已核對，母規格 #13 更新時間與狀態未改。#14 無阻擋可先開工；#22 同時由 #17 及既有 #8 阻擋。最新 [票號與依賴索引](multilingual-tickets/README.md) 與逐票本機正文均已更新。

## C1 人工衝突彈窗（本日後續工作）

- 依 C1／GitHub #10 完成右側精簡四項對照、完整詳細內容、約 40%／60% 可拖曳分區及一般選取同步；保留左側選單、原裁決按鈕、非模態流程及其他位置收集。當日後續 C2 已在專用分支完成差異樣式與來源消歧；C3 多候選動態一致性仍未納入。
- 工作分支 `ConflictDialog/ticket-01`；程式提交 `5240a21`、`ebe7364` 已推送至 Gitea 與 GitHub。固定 code-review 基準為 `d0f4535dc74753cbb6a457828b7b5c1d6ecacac9`。
- 聚焦真 Tk 衝突流程、選取同步、分隔拖曳、最小尺寸、長檔名、捕捉後來源改名、既有裁決/audit 重建曾通過；證據及限制記於[本票驗收紀錄](evidence/conflict-dialog-ticket-01/local-validation.md)。
- 第一次合併後套件發現 UI 測試 teardown 與 App 啟動清理背景工作競爭。測試改用公開 RoundCoordinator 清理狀態等待兩個 App 實例的啟動清理完成；隔離案例連續 3 次通過，修正後完整含 Tk 套件 275 tests 通過（54.894 秒），最終合併後再通過 275 tests（52.689 秒）。固定基準 Standards／Spec 審查沒有未解決問題。產品提交 `5240a21`、`ebe7364`，測試修正提交 `c0ed2dc`，合併提交 `d7d82e8405ef8839820cc727b15f256c24353389`；驗收細節見上述證據文件。

## C2 人工衝突差異與來源消歧（本日後續工作）

- C2 以固定 C1 基準 `332a4518601a8413004b5a1d88baf4b2a89b85d5` 建立 `ConflictDialog/ticket-02`，未重用 C1 的 code-review 基準。程式提交 `fad583e`；最後測試提交 `3275bb0`。
- 精簡對照改為可水平捲動的文字表格，按欄位和值範圍呈現紅色粗體；相同來源路徑維持一般樣式。同名來源路徑會逐層擴大目錄提示，尾端目錄相同時仍能顯示分歧片段。完整路徑與識別保留於詳細區。
- 真 Tk 聚焦衝突 UI 5 tests 通過；受控 Atlas 同名不同封存路徑由真 App／共同輪次進入真正 Tk 彈窗，驗證兩側不同提示及實際紅色粗體。最後完整含 Tk 套件 `B518_TK_TESTS=1 python3 scripts/run_tests.py` 276 tests 通過（46.727 秒）。編譯與 `git diff --check` 通過；專案未找到既有型別檢查設定，沒有宣稱型別檢查通過。
- 六項驗收證據及範圍界線見 [C2 本機驗收紀錄](evidence/conflict-dialog-ticket-02/local-validation.md)。Gitea／GitHub 主線同步於 `341a5ab19880f69d4dd9ce3be110480c604ccd8f`；該提交只新增兩份輪次開始規格文件，討論文件與原未跟蹤檔 SHA-256 相同，已非破壞性合併入票分支 `782ea3f`。固定基準 `332a4518601a8413004b5a1d88baf4b2a89b85d5` 的 Standards／Spec 複審均無未解問題；Standards 記錄一項局部資料群／方法職責氣味，判定不阻擋。票分支 `4b2828e` 推送至 Gitea／GitHub 後，以合併 commit `a56cfa5b0d532cfcb582794d5e76150cd7aeed9d` 整合；主線合併後完整含 Tk 套件 `B518_TK_TESTS=1 python3 scripts/run_tests.py` 於該 SHA 通過 276 tests（51.441 秒）。合併 commit 與交付文件已同步至 Gitea／GitHub；兩邊即時查核均確認主線 `ab9126f`、票分支不存在。本地票分支及隔離 worktree 已清理，正式工作樹最後停在 `B518-Log-Solution`。未修改遠端議題狀態。

## C3 人工衝突彈窗多候選一致性（本日後續工作）

- 本次從主線 `00a73526bc84b1862835672e3d329ddca06a92f4` 建立 `ConflictDialog/ticket-03`；該 SHA 為固定 Standards／Spec 審查基準，Git ancestry 證明主線已包含 C1 `d7d82e8` 與 C2 `a56cfa5`。本機 C2 README 有過時狀態文字，依主線合併紀錄、前票驗收及遠端狀態更正，不沿用歷史待審查描述。
- 修正無有效選取、快照消失或候選已移除時仍可按裁決的 UI 缺口：比較及詳細內容清空，同時停用保留原／採用新按鈕；選到仍有效衝突時恢復操作。
- 真 Tk 測試透過已註冊的 `sample-json` 控制平台，從暫存 JSONL 經實際 App、RoundCoordinator 捕捉多筆同位置及跨位置衝突；驗證非首項選取在候選刷新時保持同一 conflict ID、兩區同步、差異紅色粗體、來源改動不改捕捉快照、隱藏重開、逐項裁決、空狀態，以及 audit 與 Session `results.csv` 從磁碟重建。另以 Event 控制背景候選加入時的刷新交錯。
- 最終程式／測試 SHA `db567ff` 的真 Tk 聚焦案例 3 項通過；完整含 Tk 套件 `B518_TK_TESTS=1 python3 scripts/run_tests.py` 通過 279 tests（63.887 秒）。`py_compile` 與 `git diff --check` 通過。專案沒有既有 mypy／pyright 或其他型別檢查設定，未宣稱型別檢查通過。母規格十二案例依 C1／C2 已合併證據及本票測試逐案列於正式規格覆蓋表。
- 固定基準雙軸審查：Standards 無未解問題；Spec 在新增平台註冊至實際 App/Tk 多候選測試與完整十二案例證據矩陣後確認 C3 七項均有證據。合併提交 `965d4224218fc96526e8e97141e3bb54b1ec70df` 的完整含 Tk 套件通過 279 tests（53.411 秒）；主線已推送並即時確認 Gitea／GitHub SHA 相同，本地與遠端票分支已清理，正式工作樹停在 `B518-Log-Solution`。交付證據見 [C3 本機驗收紀錄](evidence/conflict-dialog-ticket-03/local-validation.md)。未修改遠端 Issue 狀態。

## R1 配置與輪次啟動集中準備（GitHub #25，母規格 #24）

- 從 `B518-Log-Solution` 的 `c71fb5583364f0a7c4e71d9806cfdec04160cb11` 建立 `RoundStartAssembly/ticket-01`；該 SHA 固定為本票 Standards／Spec 審查基準。開始時工作樹乾淨、主線與兩個既有 push 目的地即時 SHA 相同，票分支原先不存在。
- 新增無 Tk 相依的公開 `RoundStartPreparation`／`PreparedRoundStart`，以同一 registry 驗證及固定設定，集中檢查路徑、建立 adapter、橋接回呼、配置來源位置映射，並將同一配置資訊交給既有 RoundCoordinator、Session 與 audit。R1 當時正式 Tk 尚未切換；此後 R2 已完成桌面接入，R3 已完成舊流程檢查與交付驗證，現場設備驗收仍另階段安排。
- 使用真實暫存來源／Session／audit、PlatformRegistry 實際 adapters、Event 控制來源延遲及可注入時鐘驗證。Spec 審查曾指出注入 registry 與全域 validator 不一致，新增反例後已修正為用選定 registry 驗證；來源準備失敗且 Session 未建立時，也修正為 audit 完整落盤後不再永久停在等待狀態。
- 最新程式提交 `f5e3ff5`；聚焦 PlatformRegistry／mapping／profile／RoundCoordinator 與準備測試共 88 tests 通過。最終完整含 Tk 套件於桌面環境通過 287 tests（50.528 秒）。型別檢查設定查無；compileall 不視為型別檢查。固定基準複審與文件提交完成後才合併。
- 本票逐項驗收與母規格 14 組情境對照見 [R1 本機驗收紀錄](evidence/round-start-assembly-ticket-01/local-validation.md)。固定基準 Standards／Spec 複審無未解問題；非阻擋建議為當時新舊入口間重複的路徑 helper。合併 SHA `90e7c276f3ae28167f75d50a11b78cb973a061aa` 的主線完整含 Tk 套件通過 287 tests（49.445 秒）。Gitea 與 GitHub 主線均已同步，且確認後本地及兩個遠端的 `RoundStartAssembly/ticket-01` 均已安全刪除；最終文件提交後再即時確認一次同步。未修改遠端議題狀態。

## R2 桌面開始操作接入（GitHub #26）

- R2 以固定審查基準 `b2816400415364bd033bd4f784bfebf3cda58b2b` 從 `B518-Log-Solution` 建立 `RoundStartAssembly/ticket-02`。起始工作樹乾淨；本次即時查核的 Gitea 與 GitHub 主線均在同一基準，票分支起初不存在。R1 實作與驗收證據均已在基準中。
- 正式 Tk 開始入口改用公開 `RoundStartPreparation`，介面保留既有驗證／提示、忙碌狀態、同步偏好保存與輪次協調順序。UI 不再組裝 callback holder、adapter、來源位置映射或 Session/audit 配置證據。各平台按鈕開始、兩種快捷鍵交接、AWAITING_REVIEW 基準差異、RUNNING 保護和偏好替換失敗均補上真 Tk 行為證據。
- R2 11 項驗收及母規格 14 組情境對照記於 [R2 本機驗收紀錄](evidence/round-start-assembly-ticket-02/local-validation.md)。最後程式／測試 SHA `88b448438564e55f0ef57457b05b855bb30ea67c` 的完整含 Tk 套件於桌面工作階段通過 289 tests（69.410 秒）；四項封存收尾聚焦案例及成功封存斷言亦通過。固定基準 `b2816400415364bd033bd4f784bfebf3cda58b2b` 的 Standards／Spec 複審至 `88b4484` 無未解問題；Standards 留有非阻擋的測試失敗訊息保留建議。最終合併 SHA `a4e051a18aa263456f437af724d8f05ea40f2863` 的主線完整含 Tk 套件通過 289 tests（68.912 秒），型別檢查器未設定。主線推送後直接查得 Gitea 與 GitHub 均為 `002c12a16a6fa744f3224b8d305a4382414f2be2`；兩目的地的 `RoundStartAssembly/ticket-02` refs 均為 `853ae10a8749d8bf83da8cbd8ff4636b057b5a5c` 後，安全刪除本地與兩個遠端票分支。工作樹最後位於乾淨的 `B518-Log-Solution`。未修改遠端議題；R3 當時尚未開始，現已另行完成程式驗收，實際設備驗收仍分開處理。

## R3 移除舊組裝流程與交付驗證（GitHub #27，母規格 #24）

- 從乾淨主線 `0fbbd01ddb627bdd9bdee413ca6d3dfc2ae23fc8` 建立 `RoundStartAssembly/ticket-03`；當時 Gitea／GitHub 主線同 SHA，R1 合併 `90e7c276` 及 R2 合併 `a4e051a` 均為祖先，票分支原先不存在。固定 Standards／Spec 基準為 `0fbbd01ddb627bdd9bdee413ca6d3dfc2ae23fc8`。
- 呼叫端查核確認正式 Tk 已只呼叫 `RoundStartPreparation`。移除 `start_monitor` 對不完整 App 的 fallback 準備器與推測 Session 路徑；配置編輯／匯入匯出仍用的驗證、PlatformRegistry 建立責任及 ConfiguredMonitor 映射均保留。刪除三個由 `object.__new__` 與 mock factory 組裝的舊測試，改以真 Tk 全平台開始、兩輪舊事件隔離，以及實際 B482 重啟配置後的 Session／audit 磁碟讀取保留行為證據。
- 程式／測試提交 `26960a1f18c3e28d06484d30e6c28e19598ac10d`、`8f9b293ec7c90595c4bcd443daabf26e72049f0b` 已推送到 Gitea 與 GitHub。桌面真 Tk 聚焦套件 46 tests 通過（14.590 秒）；實際 B482 配置重啟測試 1 test 通過（1.202 秒）。最終完整含 Tk 套件 `B518_TK_TESTS=1 python3 scripts/run_tests.py` 通過 286 tests（63.304 秒）。`compileall` 與 `git diff --check` 通過；型別檢查設定不存在，沒有宣稱通過。
- 十一項驗收與母規格十四組情境見 [R3 本機驗收紀錄](evidence/round-start-assembly-ticket-03/local-validation.md)，可填寫的實際設備驗收表見[現場清單](evidence/round-start-assembly-ticket-03/field-acceptance-checklist.md)。固定基準 Standards／Spec 審查、最終文件 SHA、主線合併、主線套件、兩 push 目的地直接同步查核及安全分支清理仍待完成；現場設備驗收另階段安排，未宣稱完成。遠端議題未操作。
