# 專案摘要：2026-10-06

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
- Ticket 18 未決政策，以及 Intel／Apple Silicon/macOS 各目標機、KVM／ATE、RS-WMT 現場資料、實際發布 bundle 與簽章條件分別列為待驗。Ticket 17 AC 2、3、4 未勾選，分支保留；不合併、不刪除分支。詳細測試、環境與限制見 `B518 Log Solution/docs/refactoring/evidence/ticket-17/local-validation.md`。
