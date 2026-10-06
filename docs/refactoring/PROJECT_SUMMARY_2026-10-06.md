# 專案摘要：2026-10-06

## P1／P2 優化訪談查閱入口

使用者已確認穩定性優先、全部 P1／P2 分階段，以及完整保存才關閉與工程師可調保存天數的政策。完整已確認答案及待開始實作確認的交付方案見 [設計文件的優化訪談與分階段方案](CODEBASE_DESIGN_2026-10-06.md)，政策見 [ADR 0007](../adr/0007-round-record-retention.md)、[ADR 0008](../adr/0008-recoverable-save-before-close.md)。此次只更新討論文件，尚未修改產品程式或執行資料清理。

使用者其後要求依 ADR 0007／0008 使用 to-spec 撰寫並發布規格，已確認主要測試入口為 RoundCoordinator 公開接口、注入時鐘、真實暫存檔與磁碟重建，另保留真正 Tk 行為測試。[本機規格](ROUND_RECORD_LIFECYCLE_SPEC_2026-10-06.md) 已發布至 [GitHub Issue #1](https://github.com/Bowei1121/B518_205_207_ATE/issues/1)，標記 ready-for-agent；包含 38 項使用者故事及 16 組驗收案例，產品程式未修改。其他 P2 解析與架構重構列為另案；規格文件結構及 diff 檢查通過，未執行產品測試，也未宣告實作完成。

使用者再要求以 to-tickets 拆票；已形成 [7 張拆票草案與驗收覆蓋表](round-record-lifecycle-tickets/README.md)，待確認粒度與直接阻擋關係後發布。T1／T6 無阻擋，T2→T3 後分支至 T4／T5，T7 由 T4／T5／T6 阻擋；代號尚非 GitHub 票號。原規格 Issue #1 未修改或關閉，沒有發布子票或執行產品修改。

使用者確認「拆的沒問題」後，依 to-tickets 發布全部 7 張票，T1～T7 分別對應 GitHub #2～#8，全部 ready-for-agent；直接阻擋關係以原生 blocked-by 及正文真實票號保存。#2／#7 可先開工，未認領或開始實作；原規格 Issue #1 保持不變。最新票號、依賴及驗收覆蓋見上述本機對照表。

## 前次討論決策與 Ticket 16 結果

- 使用者確認上位機執行 `B518_JetKVM_Log`，由使用者維護並提供更新，當地 TE 工程師協助人工部署。ATE 僅連 SFC 網路；上位機能否連工廠內網仍未知，自動更新僅為未來可能，沒有實作或部署。
- Ticket 16 已完成 App／上位機受控整合，修復真實單排畫面辨識缺陷，兩端配對顯示契約 1.1。來源與結果仍經共同輪次及 frame 接口；七個容量的實際 Tk／Quartz 畫面、磁碟 audit 重建、待確認暫停及每輪一次假動作回放通過，沒有實際設備動作。
- App 非快轉合併 `c4cbffa1d9b9223fc753138df8d3be96837e7044`；上位機非快轉合併 `316f72e80afcb8a0e941e565e0d8209d9783b3ed`。合併後 App 185 tests／上位機 35 tests 通過；Standards／Spec 無未解問題。
- 最終結果文件提交：App `e3f4eb5541f70e326a7ede99b2bc342bd6d850b1`、上位機 `baea12730e2032eb4ddd599dbdaba3cdc2609ca3`。兩 repo 的 Gitea／GitHub 共四個目的地均以遠端 ref 查核同步，四個 `codex/ticket-16` 遠端分支不存在，本地分支安全刪除，僅移除本票失效追蹤引用。
- 查核時 App 在 `B518-Log-Solution`、上位機在 `main`，工作樹乾淨。上述 SHA 是本摘要寫入前的已查核檢查點；本摘要另依既有提交／推送流程保存。
- Ticket 16 AC 1／2 的實際 KVM／現場部署部分仍未勾選，依使用者批准暫緩而允許合併；AC 3～6 的本機受控範圍通過。Ticket 12 AC 1、Ticket 13 AC 4 不改判通過；TCP `slot::STATUS` 外部相容性待現場查核，Ticket 17／18 未完成。
- 稽核故障不新增產品放行阻擋：其他完成條件成立時仍可取用，必須明確標示稽核不完整，沿用既有使用者決策。

## 查閱依據

- [前次完整摘要](PROJECT_SUMMARY_2026-10-05.md)
- [Ticket 16 交付、驗收與合併紀錄](tickets/16-upstream-kvm-integration.md)
- 上位機 repo：`docs/TICKET16_DEPLOYMENT.md`、`docs/PROJECT_SUMMARY.md`、`docs/evidence/ticket-16/contract-1.1/`。

## Ticket 17 執行紀錄

- 使用者授權依 `$implement` 完整處理 `docs/refactoring/tickets/17-macos-release-and-field-acceptance.md`，包括文件、測試、打包／驗收證據、逐批 commit／push，以及只有在必要驗收與雙軸 code review 全部完成且無阻擋時才合併、清理分支。
- 本機 `B518-Log-Solution` 起始 HEAD 為 `c4cbffa1d9b9223fc753138df8d3be96837e7044`，工作目錄當時在摘要與 Ticket 16 文件顯示有既存狀態標記；未改動這些檔案，Ticket 17 改在隔離 worktree 進行。
- Gitea `origin` 與 GitHub `github` 的 `B518-Log-Solution` 起始皆為 `e3f4eb5541f70e326a7ede99b2bc342bd6d850b1`，本地當時落後此共同遠端提交。兩處均無 `codex/ticket-17`。以該共同遠端提交建立 Ticket 分支並記錄為 code-review 基準。
- 使用者其後更新 Git；核對 Git 為 `2.50.1 (Apple Git-155)`。發現主分支另新增 `26a097e1dd7fc00c40bbb7d8472d946fdc920939`，只新增本日專案摘要。將此提交合併到 Ticket 分支；兩份摘要記錄已合併保留。合併前 Ticket 工作樹乾淨，兩個遠端主分支 ref 均指向 26a097e。
- Ticket 15、16 已合併；前票完成的本機測試及受控回放不代表目標機／現場／發布 App 驗收。Ticket 18 仍保留來源是否同輪不明時可否人工採用的決策，Ticket 17 不得替其設定政策。
- 本機建置環境為 Intel x86_64、macOS 15.7.9、Python 3.8.10；不符合既有任何正式建置 target 的原生架構／Python 前置。目標 bundle 與目標機、現場實測須各自保留待驗，不能以本機測試代替。
- 打包檢查器已以 TDD 擴充 Intel／arm64 架構參數；10.14 Intel 與 26 arm64 build 腳本現在也呼叫 Python/Tk preflight 及架構／最低 macOS 版本／依賴靜態檢查。紅燈案例先重現缺少參數與行為，再實作修正。
- 第一批程式驗證：`python3 scripts/run_tests.py test_verify_macos_bundle` 共 20 tests 通過；三個 build 腳本 `zsh -n` 通過；Intel 本機 preflight 因 Python 3.8 而依預期拒絕。未建置任何 bundle，未執行簽章、產物校驗或目標機驗收。
- 專案無 mypy／pyright 或其他既有型別檢查設定；需在完整驗收紀錄說明。後續逐批補記實際命令、證據、commit／push 及外部待驗項目。

## Ticket 17 本機交付更新

- Ticket 分支 `codex/ticket-17` 的第一批 build-check 程式提交為 `f8595872017ac0c5010c1cefa07cac9b86d47d48`；當日摘要合併提交為 `0853dd5`。已推送 Gitea `origin` 及 GitHub `github`；該次推送後兩處 Ticket refs 都為 0853dd5。
- 完成離線部署及 macOS 現場驗收指引：`B518 Log Solution/docs/TICKET17_MACOS_RELEASE_AND_FIELD_ACCEPTANCE.md`；更新 `B518 Log Solution/README.md`、本 ticket 和本摘要。架構、最低系統版本、Python/Tk、依賴、ad-hoc 簽章及 SHA-256 流程均有區分，沒有把 ad-hoc 說成 Developer ID／notarization。
- 真實 Tk source App 受控回放 `smoke_deadline_app.py` 與 `smoke_state_marker_app.py` 通過。證據 `B518 Log Solution/docs/refactoring/evidence/ticket-17/source-tk-replay/run.json` 及 PNG 為隔離的合成畫面；明記 physical KVM unavailable，不能當成發行 App 或現場驗收。
- 桌面執行完整 `python3 scripts/run_tests.py`：最後一次重跑為 188 tests 通過、22.621 秒。三個 zsh build 腳本語法檢查通過；本機 Python 3.8 preflight 正確拒絕正式 Python 3.12 build target。沒有符合條件的 Catalina Intel／原生 Apple Silicon builder，因此無實際 bundle、codesign、checksum 或目標機驗收結果。
- 固定基準雙軸審查：Standards 無硬性違規，指出 build scripts 重複做 `lipo` 架構檢查；已移除 Intel／26 shell 重複迴圈，由 bundle verifier 單一負責。Spec 無未要求功能或錯誤實作，指出各目標實機未執行時 AC 4 不應勾選；已取消。修正後再跑聚焦 20 tests、完整 188 tests 及 zsh 語法檢查均通過。
- Ticket 18 未決政策，以及 Intel／Apple Silicon/macOS 各目標機、KVM／ATE、RS-WMT 現場資料、實際發布 bundle 與簽章條件分別列為待驗。Ticket 17 AC 2、3、4 未勾選，分支保留；不合併、不刪除分支。詳細測試、環境與限制見 `B518 Log Solution/docs/refactoring/evidence/ticket-17/local-validation.md`。這是 Ticket 17 執行當時的狀態快照；Ticket 18 政策其後由使用者定案並完成，見下節。

本次僅保存跨日摘要，沒有新增程式或產品規則。

## Ticket 18 執行紀錄（2026-10-06）

- 從乾淨的 `B518-Log-Solution` 固定基準 `26a097e1dd7fc00c40bbb7d8472d946fdc920939` 建立 `codex/ticket-18` 隔離工作樹；本地及 Gitea／GitHub 均無同名既有分支，主分支三處 SHA 一致。Ticket 17 分支未混入。
- 核對 Ticket 10 程式與受控驗收已在基準，Ticket 02 共同輪次接口已完成。已整理 Atlas、B482、RS-WMT 的未知來源與已知同輪對照，見 [Ticket 18 案例與現況](evidence/ticket-18/source-case-review.md)。測試案例是隔離輸入，非現場實機證據。
- 決策前關鍵現況：無既有結果時，無 `round_evidence_id` 的 final 可被接受；已存在結果的未知同輪矛盾則留下 `unresolved_source_conflict` 並保留原結果，但該事件不建立人工確認項目，也不單獨阻擋放行。此為決策前程式現況，未視為已批准政策；政策後續已定案並實作。
- 決策前階段只補證據及驗收對照，沒有修改產品程式或新增政策預期；該階段結束時尚待使用者決策，後續政策答覆及狀態變更記錄如下。

## Ticket 18 政策決定（2026-10-06）

- 使用者決定未知同輪來源一律不得人工採用，規則同時適用第一筆 final 與替換既有結果。測試時間是最低來源證據；SN 非必要證據，但 SN 讀取失敗、證據不足、拒絕或未選擇時 Slot 判 FAIL。紀錄操作、候選及時間，不記理由。
- 使用者選擇 B482 空 SN 且平台回報 FAILED 維持產品 FAIL，取代 Ticket 01／04 的歷史 NOTEST 映射。新增 [ADR 0006](../adr/0006-unknown-round-result-adoption.md) 並更新 REFACTOR_SPEC、Ticket 04 及相關測試。
- 依 Ticket 01／02 已確認的公開輪次接口先寫失敗測試，再實作共用輪次未知來源拒絕與 FAIL、操作 audit，以及 B482 空 SN 產品 FAIL。104 項核心／Adapter／audit 相關測試通過；真實 Tk `test_log_solution_ui` 37 項通過，新增未知 Atlas 身份變更呈現 FAIL 並驗證 audit。
- 同步更新 Ticket 04／18、REFACTOR_SPEC、案例證據、測試資料指南及操作 README。完整 `python3 scripts/run_tests.py` 在 Python 3.8.10、Tk 8.6、macOS 15.7.9 通過 190 tests；`git diff --check` 通過。Repo 沒有 mypy／pyright 或其他型別檢查設定。
- Ticket 18 的候選拒絕、FAIL、UI、audit 欄位受控案例已驗證。使用者確認未知來源判 FAIL 後按一般 FAIL 終態處理，其他必要條件完成後可結束輪次並供上位機讀取 FAIL；此項已補 ADR／README。未知同輪現場原始資料仍缺，不以 Tk 合成回放冒充。最終完整測試 190 項通過，固定基準 Standards／Spec 雙軸複審均無未解發現；此票必要受控範圍完成。

## Ticket 17 整合至 Ticket 18 主線｜2026-10-06

- 使用者同意先合併 Ticket 17 的建置／bundle 驗證工具、測試、文件與受控驗收證據；分支沒有 App 核心流程改動，但確有打包相關程式碼變更。此決定不代表發行 bundle、目標 App 或現場驗收已通過。Ticket 17 AC 2、3、4 保持未勾選，整體仍 blocked。
- Ticket 17 工作分支先合併最新主線 `3d15abf77575b9b1b5db2b1f878846c930c9d5e3`，保留雙方 Ticket 17／18 摘要。Ticket 18 已定案政策取代 Ticket 17 原本的未決說明；Ticket 17 發行指南與限制同步更新。
- 整合後完整 `python3 scripts/run_tests.py` 通過 193 tests；三個 build 腳本 `zsh -n` 與 `git diff --check` 通過。Standards／Spec 以主線整合點 `3d15abf77575b9b1b5db2b1f878846c930c9d5e3` 為基準審至 Ticket 分支 `1b444ecb587a826f46b04fc686eb598fc9936058`，均無未解發現。
- Ticket 17 合併 commit 為 `883d9f4448ab36b388f4fb01ece66ff406871f31`；合併後完整測試再通過 193 tests，合併 commit 已推送且 Gitea／GitHub refs 同步。工作樹乾淨並停在 `B518-Log-Solution`。因 AC 2、3、4 尚未驗收，`codex/ticket-17` 本地及兩個遠端分支保留在 `1b444ec` 供後續接續；合併不代表發行／目標環境驗收完成。
