# 18：決定未知同輪來源的人工採用政策

**類型：**保留決策

**What to build／工作內容與交付結果：**整理無法確認是否同輪的來源案例與證據；取得使用者明確政策後，才實作允許／禁止及適用條件並驗收。

**Blocked by／前置依賴：**

- [10：共同處理已確定同輪的結果衝突](10-same-round-conflict-review.md)

**Status：**complete（2026-10-06；政策、實作、必要受控驗收及固定基準雙軸審查完成；現場未知來源原始資料仍列為限制，不冒充已驗）

## 驗收條件

- [x] 整理不確定來源的輸入、來源識別、時間、SN 與批次證據；未知資訊不捏造。（依 repo 內平台程式、匿名化基準與隔離測試逐平台整理；證據層級及現場資料缺口見 `docs/refactoring/evidence/ticket-18/source-case-review.md`。）
- [x] 使用者明確決定能否人工採用、適用條件與必要限制，決策有紀錄；未決前此項不能完成。（2026-10-06 決定見 ADR 0006。）
- [x] 政策確認後，候選、人工操作、結果、放行及紀錄符合決策，有對應案例。（共用輪次與真實 Tk 案例確認未知候選拒絕、slot FAIL、一般 FAIL 終態可取用、候選／操作時間入 audit 且不記理由；已確定同輪候選仍依 Ticket 10。）
- [x] 不以現有 B482 跨批次接受或 RS-WMT 拒絕不同批次冒充新版通則。（逐平台分開記錄為歷史來源行為。）
- [x] 定案前不標為可直接開發，不宣稱此分支驗收通過；其他已確認工作可繼續。（決策前階段維持 `deferred-decision`、未修改採用行為；後續收到政策決定後轉為實作中。）

## 驗證方式

決策前只準備來源案例與證據，不填允許／禁止預期；決策後補具體行為驗收。

**規格驗收對照：**REFACTOR_SPEC AC-08、ADR 0006、`B518 Log Solution/README.md` 的來源衝突與 B482 操作說明、輪次事件及 audit 記錄。行為驗收以 `RoundCoordinator` 公開快照／事件接口、三平台 Adapter 與真實 Tk 受控流程完成；各層結果分開記錄。

## 保留決策、待確認事項與限制

本票建立時保留的政策已由使用者於 2026-10-06 決定，內容見 ADR 0006；以下早期執行紀錄中的「未決」狀態為當時快照，已由後續決策紀錄取代。

所有行為測試須依 Ticket 01／02 已確認的公開接口落實；先前的接口確認不包含本政策，政策現依 ADR 0006 執行並由 AC 3 驗收。

## 執行與追蹤

依 2026-09-30 使用者確認的任務清單建立。以 REFACTOR_SPEC、CONTEXT 與 ADR 0001～0005 為基準，沿用測試配置、平台資料來源、監控輪次、桌面介面四模組與 Python／Tk／既有 macOS 打包方式。只在前置完成且本票關鍵待決及外部條件已滿足時轉為 ready-for-agent；需要人類決策的任務不得逕自轉為可直接實作。

執行時逐項記錄實際交付、驗證環境與結果、仍未決／待驗範圍及相關提交。未執行的驗收維持未勾選；本文件建立不代表 App 已完成重構。

## 2026-10-06 決策前證據整理

- 固定起始 SHA：`26a097e1dd7fc00c40bbb7d8472d946fdc920939`。從 `B518-Log-Solution` 建立全新的 `codex/ticket-18`；建立前本地與 Gitea／GitHub 都沒有同名分支，主分支三處均指向固定起始 SHA。實作位於隔離工作樹 `/private/tmp/B518-Log-Solution-ticket-18`，沒有合併 Ticket 17 專用分支。
- Ticket 10 實際程式及五項受控驗收存在於基準；以共同輪次快照／事件／逐項選擇操作處理**已確定同輪**衝突。Ticket 02 已完成且 App 透過共同輪次公開快照與事件操作；Ticket 01 的接口確認不包含 Ticket 18 政策。
- 三平台案例、程式現況及證據限制整理於 `docs/refactoring/evidence/ticket-18/source-case-review.md`。案例明確區分匿名化 baseline、repo 隔離測試、來源時間、批次線索與未知值，沒有把測試資料稱為實機案例。
- 現況有重要決策影響：沒有既有結果時，輪次目前接受 final，即使沒有 `round_evidence_id`；有既有結果時，未知同輪矛盾只記錄 `unresolved_source_conflict`、保留原結果、不建立人工覆核項目。該事件本身不是放行阻擋。這些是程式現況，沒有被當成政策批准。
- 決策前階段只新增案例文件與驗收對照；沒有修改程式或使用者資料。當時 AC 1、4、5 已完成，AC 2、3 尚未完成，狀態為 `deferred-decision`；後續政策決定及狀態更新見下節。
- 下一步須先向使用者提出具體選項，確認未知同輪是否允許人工採用、最低證據條件、首次結果與替換既有結果的範圍、未選擇／證據不足的行為及是否阻擋放行。取得明確決策前，不實作或宣稱此政策完成。

## 2026-10-06 使用者決策與實作啟動

- 使用者決定未知同輪來源一律不得人工採用，第一筆 final 與替換既有結果同規則；測試時間為最低來源證據，SN 非最低證據；SN 讀取失敗、證據不足、拒絕或未選擇均將 Slot 判為 FAIL。記錄操作、候選及時間，不記理由。
- 使用者明確選擇 B482 空 SN 且平台回報 FAILED 維持 FAIL，取代 Ticket 01／04 的歷史 NOTEST 映射；已由 ADR 0006 與 REFACTOR_SPEC 記錄，Ticket 04 驗收需更新測試。
- 使用者於 2026-10-06 另確認：未知來源候選判 FAIL 後依一般 FAIL 終態放行；符合其他必要輪次條件後可完成並供上位機讀取 FAIL，不新增額外待確認項目。未知候選仍不得產生 PASS。
- 同一已確定輪次的結果矛盾仍沿用 Ticket 10；未知來源候選不得採用，FAIL Slot 按現有輪次規則成為終態。
- 政策確認後狀態改為 `in-progress`。AC 3（候選、結果、放行與紀錄驗收）仍未完成；尚未宣稱 Ticket 18 通過。

## 2026-10-06 實作與受控驗證

- 首次測試以公開 `RoundCoordinator` seam 重現三個紅案例：沒有輪次連結的第一筆 final、未知同輪替換候選、具輪次連結但缺來源測試時間。另重現 B482 空 SN 且平台 FAILED 被轉成 NOTEST。實作後相關測試轉綠。
- 現行規則：PASS／FAIL 等來源終態只有在有輪次來源連結且有實際來源測試時間時才可被採用；未知同輪候選不顯示採用選項。來源不明或時間不足時記錄 `unknown_round_candidate_rejected`、操作 `fail_unconfirmed_candidate`、原／候選資料與操作時間，slot 設為 FAIL；不保存理由。已確認同輪且有來源測試時間的矛盾仍進入 Ticket 10 逐項覆核。
- 平台來源判讀仍在 Adapter；B482 空 SN 的 PASSED／FAILED TestData 終態都依 SN 讀取失敗判為 FAIL。Atlas 已鎖定 SN 後的未知身份變更令該 slot FAIL；可信 SN 已存在時，單獨的後續不可讀觀察不會改寫可信 SN。
- 相關受控測試：`python3 scripts/run_tests.py test_monitoring_round test_b482_source_adapter test_atlas_source_adapter test_rswmt_monitoring test_audit_records`，79 tests 通過。這是核心／Adapter／audit 單元及共同輪次測試，不代表真實 Tk、上位機、設備或現場驗收。
- 實際 Tk 受控測試 `python3 scripts/run_tests.py test_log_solution_ui` 通過 37 項；新增流程在暫存 Atlas 路徑中觀察到未知身份變更後 UI 顯示 FAIL、維持原 SN、結果可用，audit 含候選與操作時間且不含理由。這是受控 Tk 測試，不代表 Atlas 現場或目標設備驗收。
- `_has_source_test_time()` 回歸案例先證明 `2026-10-06` 會誤被 `datetime.fromisoformat()` 當作測試時間並令 slot 保留 PASS；修正為必須包含時間部分後，日期字串候選轉為 FAIL，35 項輪次測試通過。
- 完整 `python3 scripts/run_tests.py` 最終重跑通過 190 tests；執行環境 Python 3.8.10、Tk 8.6、macOS 15.7.9。範圍含來源／共同輪次／audit 核心測試、真實 Tk UI、bundle verifier 單元檢查；無任何跨層替代。`git diff --check` 通過。
- repo 沒有 mypy、pyright、pyproject／setup.cfg／tox 型別檢查設定；沒有型別檢查結果可報，不以語法檢查替代。
- Spec 初審要求釐清 FAIL 是否仍依一般規則放行或阻擋輪次完成／待確認／上位機取用；使用者已確認一般 FAIL 終態可放行，決策已補入 ADR 與操作文件。最終 Standards／Spec 雙軸平行複審皆以固定起始 SHA `26a097e1dd7fc00c40bbb7d8472d946fdc920939` 為基準、覆蓋整票變更，結論無未解發現；先前發現的時間日期邊界與歷史政策措辭均已修正並複審。
- 沒有 Ticket 18 未知同輪現場原始資料；此限制不能由合成來源回放抵銷。此票定義的程式與受控驗收、測試及固定基準雙軸審查已完成；現場補驗仍需取得實際資料及設備。最終提交、各 push 目的地同步、合併及分支清理結果另於本節追記。
