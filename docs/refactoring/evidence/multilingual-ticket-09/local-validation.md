# M9 App 事件保存期限清理驗收紀錄

日期：2026-10-09（Asia/Taipei）  
Ticket：多語言 M9／GitHub #22。固定 Standards／Spec review baseline：`01ab62993cdbc79b3a38a56a7218e63e4ac4ca7f`。  
Git 根目錄：`B518-Log-Solution`；Python 專案目錄：`B518-Log-Solution/B518 Log Solution/`。

## 基準與依賴

本機 `B518-Log-Solution` 在開始時位於固定 SHA `01ab62993cdbc79b3a38a56a7218e63e4ac4ca7f`；M9 分支以此為基準接續，未重設主線或丟棄提交。Git ancestry 查核確認 M4 交付 `8f8b3a1286bc561e239395f9e52bd19efb6244df` 及輪次保存期限／可信封存清理 Ticket 07 修正 `d8e105e2ac83463c95176d3138bff26c598208cb` 均為固定基準祖先。程式及前票驗收文件確認 App 雙語持久保存／有序補存、完整保存才正常關閉、可信封存時間及既有非重疊清理協調已存在。M5～M8不是 M9 直接依賴。

遠端設定：`github` 為 GitHub fetch/push；`origin` 為 Gitea fetch，push destinations 包含公司 Gitea 與 GitHub。本輪程式修正 push 至 GitHub 成功。之後一次 `git ls-remote github` 遇到 DNS 解析錯誤，該次未能直接查證遠端 SHA；不能以舊追蹤 ref 取代。Gitea 位於公司內網，依使用者明示安排延至週一同步；在直接確認前保留票分支，不移除目的地。

## 持久格式與清理契約

- App 事件以自身 `event_id`、原始 ISO `occurred_at`（必須帶時區）、sequence、固定雙語訊息、參數與診斷保存，不建立 `round_id`。事件 record schema 保持 v1。
- 未清理的容器維持 store schema v1／連續序號。清理留下退休序號範圍時容器明確升為 v2，附 `retired_sequences` 與 `next_sequence`。新讀取器兼讀 v1/v2，驗證活躍及退休序號完整解釋、不補號、不重排；混合保存段只移除到期事件，其餘原資料不變。
- App 期限取事件自身 `occurred_at`，換算 UTC 後含等號比較；輪次沿用可信封存時間。一天為完整 24 小時。測試涵蓋不同 offset 同一瞬間、期限前一微秒、恰到、期限後及期限延長競爭。
- pending、寫入／耐久性故障、worker 工作中、未知／損壞格式、缺少或無效時區時間均保留。清理不接觸偏好／配置、來源 Log、人工匯出等外部資料。
- 沿用既有 `RoundCoordinator` retention scheduler、摘要 ledger、close gate；無新增 scheduler。保存天數變動於下次既有背景清理生效；Tk 不直接刪除資料。
- 清理逐層固定 managed directory descriptor，拒絕符號連結；以目錄相對 `openat`／`renameat` 取代一般路徑字串替換，並在提交閘門重新確認目錄及 journal 身分。本機 Python 3.8 macOS 未提供 `dir_fd` 介面，因此使用相對系統呼叫；安全呼叫不可用時失敗封閉。
- App 事件清理摘要沿用持久 ledger，記錄時間、期限、刪除／保留／失敗數及原因。設定頁真 Tk 可用 English／繁中查閱摘要、失敗、原始診斷及重試；已知 App 原因走集中資源，未知 OS／檔案系統診斷保留原文。

## 複審修正與提交

程式／測試批次 `924eb153ec12119677ca4d9f617278db71e9b84d`、固定基準複審修正 `b71fa3bdcbf11a9d01df04fe6b480e8186ad08bc`、管理根祖先 symlink 修正 `1197e017085ce45ef55c43f15e9711e0b5dac0e8`，以及替換成功但目錄 fsync 失敗後的耐久性重試修正 `523660779d20b375c1c3f925ed9fce78e381532f` 均已 push 至 GitHub 同名票分支。2026-10-09 16:42（台北）直接查詢 GitHub：`Multilingual/ticket-09`=`523660779d20b375c1c3f925ed9fce78e381532f`，`B518-Log-Solution`=`01ab62993cdbc79b3a38a56a7218e63e4ac4ca7f`。此查詢只確認當時程式／測試分支；最後文件提交與可能的合併後會再次直接查詢。

固定基準第一輪 Standards／Spec 審查指出三項問題，均已修正：

1. 清理路徑字串替換有父目錄競爭／外部 symlink 風險：改用從檔案系統根目錄逐層以 `O_NOFOLLOW` 固定的目錄 descriptor，再以相對原子替換；Event 控制 managed-root 祖先及父目錄置換測試確認外部 sentinel 及原 journal bytes 不變、清理安全失敗。
2. 稀疏活躍序號與退休範圍被標示為 v1：容器擴充明確升為 schema v2、事件本身維持 v1；測試驗證 v1 初始格式、v2 清理格式及 reader 相容性。
3. 部分 App 清理原因在英文摘要顯示中文：已新增集中原因資源與映射，真 Tk 驗證期限未到、pending 保護及原事件時間缺少時區的中英摘要；原始系統診斷保留。無時區測試先讓 App 以有效 journal 初始化，再注入損壞時間，並攔截會阻塞測試的原生錯誤對話框；實際狀態 label 仍由 Tk 更新及檢查，journal bytes 維持不變。

複審修正後程式／測試驗證 SHA：`523660779d20b375c1c3f925ed9fce78e381532f`。第二輪固定基準複審指出管理根祖先若在清理前已是 symlink，先 resolve 會把外部目錄當作管理根。新增紅燈測試重現錯誤完成並刪除外部事件；修正為保留 lexical root，只正規化已驗證的 macOS `/var -> private/var`、`/tmp -> private/tmp` 標準 alias，再從 `/` 逐段以 `O_NOFOLLOW` pin 管理根及其祖先，並安全 probe relative parent 與 journal entry。使用者路徑 symlink 現會安全跳過；Event 控制事前 symlink 與競爭置換案例均確認清理不 complete、刪除數為 0、外部 bytes 未變。

第三輪 Spec 複審發現原子 rename 已成功、父目錄 fsync 回報失敗後，重試可能看到「無到期事件」並在未再次同步目錄時回報 complete。新增紅燈測試確認重試原本沒有第二次 directory fsync；修正為即使重試時磁碟內容已無待刪事件，也先對 pin 住的父目錄 descriptor 執行 fsync，並從磁碟重新同步記憶體事件、退休序號範圍及 next sequence，再回報完成。回歸確認第一次仍回報失敗、重試重新確認耐久性後 complete，新讀取器可重建退休序號且不會復活已清理事件。固定基準 `01ab62993cdbc79b3a38a56a7218e63e4ac4ca7f` 的 Standards／Spec 最終雙軸複審均完成，無未解阻擋；Standards 的非阻擋建議是 `cleanup_expired` orchestration 較密集，但路徑安全、持久化及保護檢查共同構成清理原子性，不為行數拆分。

## 測試與六項驗收

聚焦命令（從 `B518 Log Solution/` 執行）：`PYTHONPATH=src python3 -m unittest tests.test_app_event_store tests.test_round_retention -v`。44 tests 通過（12.102 秒），涵蓋原時間／時區／含等號邊界、期限延長、混合保存段、v1→v2序號保留、全新讀取器、pending／故障保護、損壞 bytes 保留、symlink／事前 managed-root 祖先／競爭置換／父目錄置換、既有輪次清理、競爭及替換後目錄 fsync 失敗的安全重試。

真 Tk 命令一：`B518_TK_TESTS=1 PYTHONPATH=src python3 -m unittest tests.test_log_solution_ui.LogSolutionUiTests.test_real_tk_app_event_cleanup_failure_is_visible_and_retryable -v`。1 test 通過（0.849 秒），在可存取桌面工作階段執行：隔離暫存 journal 注入替換失敗、確認事件保留及錯誤可見，以實際 Tk Retry 按鈕重試；核對到期事件移除、未到期事件保留、摘要兩語與正常 close。真 Tk 命令二：`B518_TK_TESTS=1 PYTHONPATH=src python3 -m unittest tests.test_log_solution_ui.LogSolutionUiTests.test_real_tk_localizes_timezone_missing_app_event_cleanup_reason -v`。1 test 通過（0.731 秒）；實際設定頁狀態 label 在英文／繁中間刷新，原無時區 journal bytes 不變，完成協調關閉。

完整命令：`B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py`。完整含 Tk 套件 363 tests 通過（104.336 秒），於可存取桌面工作階段完成，包含上述 2 個真 Tk M9 案例；聚焦套件 44 tests 通過。`python3 -m compileall -q src tests` 及 `git diff --check` 於最後 fsync 重試修正後通過。未找到既有 mypy／pyright／型別檢查設定，不宣稱型別檢查通過，亦未新增設定。

| 驗收 | 結果與證據 |
|---|---|
| 1. App 原事件時間／時區與可信輪次封存分離 | 通過：`test_retention_uses_absolute_instant_for_deadline_comparison`、`test_retention_deadline_is_inclusive_and_preserves_event_just_before_cutoff`、`test_deadline_is_inclusive_and_a_round_before_deadline_is_preserved`。 |
| 2. 全域期限於後續清理生效 | 通過：`test_app_event_cleanup_rechecks_extended_deadline_before_replacing_journal`、`test_successful_retention_setting_change_rechecks_all_trusted_rounds` 及真 Tk 保存天數回歸。 |
| 3. 只清理可信完整且到期事件 | 通過：pending／failed、未知與損壞資料保留；fresh reader 重建清理後事件及序號。 |
| 4. 混合段及外部資料保護 | 通過：混合事件、路徑置換與 symlink 測試；隔離根目錄下真 Tk 案例未觸及外部資料。 |
| 5. 既有協調、雙語摘要與安全重試 | 通過：沿用 scheduler／close gate、重複要求合併、持久摘要、真 Tk 錯誤顯示與重試。 |
| 6. 真實磁碟、時間、競爭與 App 操作 | 通過：44 項聚焦、2 項真 Tk M9 驗收及 363-test 完整含 Tk 套件。 |

## 母規格覆蓋及界線

只標記母規格案例 12（App 原事件時間、保存保護、期限比較、磁碟重建）及案例 13（既有清理協調、摘要、競爭與重試）中本票實際測試部分；其他案例不因 M9 完成而勾選。M9 完成 App 事件期限清理與維護摘要；M10 全 App／bundle 發布驗收仍待交付。未新增語言、格式、解析器、排程或產品放行政策，未修改遠端 Issue。

## Git 交付狀態

- M9 固定 review baseline：`01ab62993cdbc79b3a38a56a7218e63e4ac4ca7f`。
- 最後程式／測試提交及完整套件驗證 SHA：`523660779d20b375c1c3f925ed9fce78e381532f`；聚焦 44 tests（12.102 秒）、完整含 Tk 套件 363 tests（104.336 秒）通過，`compileall`／`git diff --check` 通過。
- 固定基準 Standards／Spec 最終複審均無未解阻擋；Standards 留一項非阻擋的 orchestration 密度建議，因其操作共同構成安全清理交易而保留目前 cohesive 流程。2026-10-09 16:42（台北）直接查詢 GitHub：票分支 `523660779d20b375c1c3f925ed9fce78e381532f`，主線 `01ab62993cdbc79b3a38a56a7218e63e4ac4ca7f`。
- 2026-10-09 16:43（台北）一次直接執行 `git ls-remote github refs/heads/Multilingual/ticket-09 refs/heads/B518-Log-Solution` 因 `github.com` DNS 未解析而失敗；之後恢復連線並完成以下合併與直接查詢。
- 本機 merge commit：`d891dd10925e1074d2674b2ed68b36847250fd87`（2026-10-09 16:44 台北，`--no-ff`）。合併後在 `B518-Log-Solution` 執行完整命令 `B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py`，363 tests 通過（97.541 秒）；最初 sandbox 內 Tk 建窗程序 abort（exit 134），以已授權桌面執行權限確認 Tk 8.6.8 可建窗後，在可存取桌面的執行環境重跑並通過，未將 sandbox 中止算作測試通過。
- 推送 GitHub `B518-Log-Solution` 後，2026-10-09 16:45（台北）直接 `git ls-remote` 確認 main=`d891dd10925e1074d2674b2ed68b36847250fd87`、票分支=`ebbdbc34532d6bb58a16c3321c687a540356dbfe`。Gitea 仍待週一內網同步及直接確認；因此保留本地與 GitHub 的 `Multilingual/ticket-09`，未刪除任何分支或 push 目的地。最後文件提交後仍須直接查詢所有目的地。
- Gitea 週一內網同步直接確認前，保留本地與 GitHub `Multilingual/ticket-09` 分支；不移除目的地、不強推、不強制刪除。
