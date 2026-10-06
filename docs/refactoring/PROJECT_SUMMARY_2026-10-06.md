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

本次僅保存跨日摘要，沒有新增程式或產品規則。

## Ticket 18 執行紀錄（2026-10-06）

- 從乾淨的 `B518-Log-Solution` 固定基準 `26a097e1dd7fc00c40bbb7d8472d946fdc920939` 建立 `codex/ticket-18` 隔離工作樹；本地及 Gitea／GitHub 均無同名既有分支，主分支三處 SHA 一致。Ticket 17 分支未混入。
- 核對 Ticket 10 程式與受控驗收已在基準，Ticket 02 共同輪次接口已完成。已整理 Atlas、B482、RS-WMT 的未知來源與已知同輪對照，見 [Ticket 18 案例與現況](evidence/ticket-18/source-case-review.md)。測試案例是隔離輸入，非現場實機證據。
- 關鍵現況：無既有結果時，無 `round_evidence_id` 的 final 目前可被接受；已存在結果的未知同輪矛盾則留下 `unresolved_source_conflict` 並保留原結果，但該事件不建立人工確認項目，也不單獨阻擋放行。這是待使用者裁定的範圍，未視為已批准政策。
- 本階段只補決策前證據及 Ticket 驗收對照，沒有修改產品程式或新增政策預期。需由使用者明確決定首次結果與替換結果是否適用相同政策、證據門檻、拒絕／未處理狀態、放行及紀錄要求；Ticket 18 維持 deferred-decision。
