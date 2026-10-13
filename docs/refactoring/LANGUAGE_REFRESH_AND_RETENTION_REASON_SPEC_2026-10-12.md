# 多視窗語言更新與清理原因表述規格

## Problem Statement

操作員切換語言時，需要所有 App 自有視窗立即更新文字，同時保留輸入、選取與閱讀位置。目前主畫面逐一理解各視窗的刷新方式，部分自有提示另接收語言通知；新增視窗或某個刷新失敗，容易使共同流程負擔增加。操作員也需要在更新失敗時仍能繼續工作，知道哪些視窗未完成更新，並自行重試。

工程師與操作員查看清理狀態時，需要看懂輪次、App 事件及封存驗證的原因。目前畫面依中文字串或前綴辨識底層原因，使來源文案與顯示翻譯耦合，未知原因缺乏所選語言的外層說明。原因表述的改善不能改變刪除資格或既有資料保護。

## Solution

本規格涵蓋兩條可分別實作與驗收的工作：

1. 沿用既有語言通知方向，各視窗登記後自行就地更新文字。App 目前語言為共同依據，開啟／重開／再次顯示時皆讀取目前語言；關閉時解除登記。個別失敗不阻止其他視窗更新，主畫面提供非阻擋彙整提示、重試及診斷。
2. 集中清理原因表述，新摘要保存固定原因識別、參數、繁中／英文說明與原始診斷。畫面依所選語言呈現；舊摘要不改寫，可靠辨識者相容翻譯，未知原因外層提示查看詳細內容，內層完整保留原文。

第一項只處理語言刷新；第二項只改善原因說明。監控、結果裁決、保存、關閉與刪除安全沿用原責任及政策。

## User Stories

1. As an 操作員, I want 切換語言後所有已開 App 自有視窗更新, so that 不會同時看到不一致的語言。
2. As an 操作員, I want 視窗標題與內容都更新, so that 能理解目前操作。
3. As an 操作員, I want 設定草稿與尚未送出的輸入保留, so that 不需重新輸入。
4. As an 操作員, I want 衝突候選選取保持, so that 語言切換不影響人工決定。
5. As an 操作員, I want 診斷與歷史事件選取保持, so that 能繼續查閱同一事件。
6. As an 操作員, I want 捲動及閱讀位置保持, so that 不必重新尋找正在看的內容。
7. As an 操作員, I want 切語不關閉重開視窗, so that 原操作上下文維持。
8. As an 操作員, I want 切語不自動裁決衝突或確認警報, so that 人工決定仍由我完成。
9. As an 操作員, I want 監控中與待確認時仍能切語, so that 不必重啟監控。
10. As an 操作員, I want 關閉保存期間仍按原政策暫停切語, so that 保存流程保持一致。
11. As an 操作員, I want 新開視窗直接使用目前語言, so that 不需再切一次語言。
12. As an 操作員, I want 隱藏視窗再次顯示時使用目前語言, so that 不會看到舊語言。
13. As an 操作員, I want 關閉重開視窗不收到重複更新, so that 操作不因通知累積而異常。
14. As an 操作員, I want 下次啟動仍使用已保存的語言偏好, so that 現有選擇記憶功能維持。
15. As an 操作員, I want 一個視窗刷新失敗時其他視窗仍更新, so that 不會整個 App 都停止換語言。
16. As an 操作員, I want 更新失敗仍保留輸入與選取, so that 不會丟失正在處理的工作。
17. As an 操作員, I want 主畫面顯示不阻擋操作的失敗提示, so that 能知道問題並繼續工作。
18. As an 操作員, I want 多個視窗失敗合併提示, so that 不會連續被彈窗打斷。
19. As an 操作員, I want 可自行重試文字更新, so that 不必重開 App 或視窗。
20. As an 操作員, I want 重試使用最新語言, so that 不會恢復成上一次失敗時的舊選擇。
21. As an 操作員, I want 全部恢復後清除提示, so that 能分辨目前是否仍有問題。
22. As an 工程師, I want 恢復後仍可查閱更新失敗診斷, so that 能排查現場問題。
23. As an 操作員, I want 重試不持續自動發生, so that 不會反覆收到失敗提示。
24. As an 操作員, I want 原生檔案選擇器遵照系統語言, so that 本次改造維持既有操作效果。
25. As an 操作員, I want 輪次清理原因以所選語言說明, so that 能理解哪些紀錄被保留或清理。
26. As an 操作員, I want App 事件清理原因同樣可理解, so that 能分辨到期與未保存等狀態。
27. As an 工程師, I want 封存驗證原因使用相同表述規則, so that 不必跨多處解讀不同文案。
28. As an 工程師, I want 新摘要保存固定原因識別與參數, so that 文案改動不影響原因辨識。
29. As an 工程師, I want 同一份新摘要保存繁中與英文說明, so that 台灣與美國都可直接查閱。
30. As an 工程師, I want 原始診斷保留, so that 可理解說明不覆蓋故障證據。
31. As an 操作員, I want 能可靠辨識的舊摘要依語言呈現, so that 舊資料仍可使用。
32. As an 操作員, I want 無法辨識原因時得到所選語言的外層提示, so that 知道需要查看詳細內容。
33. As an 工程師, I want 未知原因與舊內容完整保留原文, so that 不會因猜測翻譯失去證據。
34. As an 工程師, I want 舊摘要不因閱讀或切語被改寫, so that 歷史資料保持原樣。
35. As an 工程師, I want 原因識別只控制說明, so that 不會取代刪除安全判斷。
36. As an 工程師, I want 新舊摘要都能由磁碟重建, so that App 重啟後仍能查閱。
37. As an 維護者, I want 視窗關閉後解除通知登記, so that 長時間使用不累積失效接收者。
38. As an 維護者, I want 正式版本只保留一條語言刷新流程, so that 不會重複更新。
39. As an 維護者, I want 真正 Tk 與真實紀錄驗證, so that 測試能反映操作與保存結果。
40. As an 維護者, I want 兩項分別交付與驗收, so that 不必承擔一次大型改造的風險。

## Implementation Decisions

### 第一項：多視窗語言刷新

- 深化視窗呈現的語言刷新責任，沿用既有 App 語言變更通知，集中登記、解除、錯誤隔離及失敗狀態彙整；各視窗保有更新自身文字與保留自身操作狀態的責任。
- Interface 讓語言切換端不必了解個別視窗有哪些 widget 或恢復步驟；視窗接收者透過同一契約參與更新。Implementation 不要求新增通用事件匯流排或為各視窗建立背景執行緒。
- App 的目前語言是執行期間共同依據；通知與重試都讀取最新值，不能依賴已過時的通知所帶語言。磁碟偏好仍由原機制管理，下次啟動按既有政策恢復；視窗不保存獨立語言偏好。
- App 自有視窗與主畫面文字皆涵蓋，包含設定、衝突、輪次警報、App 診斷、歷史事件及自有提示。關閉進度視窗沿用關閉期間禁切語政策，開啟時仍依目前語言呈現。
- 開啟時登記一次並依目前語言呈現，關閉與銷毀時解除該視窗自身登記，不能移除其他視窗的通知。隱藏不等於關閉，重新顯示前須完成目前語言呈現；重開後不得重複接收。
- Tk 更新與視窗生命週期操作仍在 Tk 執行流程進行。通知只代表文字刷新，不啟動監控、不變更結果、不採用候選、不確認警報、不重新讀取平台來源或重寫歷史紀錄。
- 視窗就地更新，保留草稿、無效輸入、候選／事件選取、閱讀與捲動位置，以及既有焦點、模態操作及裁決效果。無需重建視窗或重建輪次狀態。
- 單一接收者失敗不得中斷其他接收者，主畫面的文字刷新亦不得阻止其他視窗接收通知。失敗可能造成部分文字尚未更新，但不能清除操作內容或自動重開視窗。
- 主畫面提供一則不阻擋操作的失敗彙整提示，指出未完成的視窗並附「重試文字更新」與詳細診斷入口。多視窗失敗合併呈現，不連續彈窗；正常監控與人工處理仍可操作。
- 操作員要求重試時，只重新執行文字刷新，使用 App 最新語言與有效視窗，不重啟監控、不重開視窗；不建立持續自動重試循環。全部恢復後清除現行失敗提示，先前診斷仍保留。
- 失敗診斷沿用既有 App 事件雙語保存與未保存重試機制，不虛構輪次。通知、診斷或提示刷新不得互相遞迴產生無限失敗通知；保存失敗仍依原契約保留待補存內容，不把未落盤宣稱已保存。
- 原語言偏好保存與保存失敗處理保持；通知失敗不能被誤當偏好保存失敗。關閉保存期間仍拒絕切語；本規格不新增關閉中刷新或重試繞過政策的入口。
- 先完善現有通知契約、生命週期與失敗隔離／重試，再逐步接入視窗。每個視窗遷移時只保留一條有效刷新路徑；全部驗證後移除主畫面手動串接舊流程。

### 第二項：清理原因表述

- 深化原因表述 Module，集中固定原因識別、參數、雙語說明、原始診斷及舊內容辨識規則。資料產生端交出原因語意，Tk 只要求顯示，不必比對中文文案或解析安全 Implementation 的例外文字。
- 範圍涵蓋輪次／App 事件清理成功、跳過與失敗原因、即時清理狀態，以及判斷可否清理時的封存驗證原因。封存資格與資料安全檢查仍由原 Module 執行。
- 新摘要在同一原因紀錄保存穩定原因識別、捕捉參數、繁中與英文說明及必要原始診斷，與既有清理執行識別、輪次識別、時間、outcome 及計數保持關聯，不將兩種語言寫成兩次清理。
- 沿用集中翻譯資源與既有雙語捕捉／呈現契約；顯示語言變更不修改捕捉內容。參數保持原值，尤其時間、路徑、輪次與事件識別、序號及原始錯誤不能翻譯或補造。
- 新舊摘要讀取器都能呈現；相容擴充採明確版本／欄位驗證，具體格式由實作依既有 ledger 與雙語契約決定，不在此硬指定版本數字。必須保留既有清理計畫、恢復進度與摘要資料，不能把格式遷移當作資料重置。
- 新格式依已驗證原因識別呈現；缺少翻譯按既有英文回退，不顯示內部識別碼。原因資料無法可靠解讀時，不猜測分類，以未知原因外層提示與完整原文／原始資料詳細內容呈現。
- 舊摘要僅對可靠辨識的既有原因進行讀取時翻譯，不以含糊文字匹配建立安全判定；無法辨識時外層用所選語言提示「無法辨識此原因，請查看詳細資訊」，詳細區完整保留原文。
- 不因閱讀、切語或翻譯改寫舊摘要；既有正常追加新清理摘要與保存恢復機制仍保留，不要求將新舊紀錄拆成兩份獨立 ledger。
- 原因識別與翻譯只控制說明，不能控制刪除資格。輪次從可信封存時間起算、App 事件從自身時間起算、全域保存天數、保護狀態、未知／損壞資料保留、最終刪除檢查、符號連結保護與耐久性都不變。
- 新原因雙語資訊在產生時捕捉並隨原摘要保存；摘要保存失敗、重試與關閉協調沿用既有政策，不新增另一套排程、清理或保存機制。
- 遷移順序為讀取新舊摘要 → 產生新原因紀錄 → 畫面使用集中表述；每一步保持既有流程與回歸測試通過，保留必要的舊資料相容能力。

### 分項交付與決策約束

- 兩項共同規劃但分別實作與驗收；第二項不以第一項完成作為無關的阻擋。具體票件在後續拆票時依真實依賴安排。
- 遵循 ADR 0005、0007、0008、0009；不改結果放行、輪次保存及刪除政策，也不更換 Python／Tk。沒有新增需記入領域詞彙表的產品概念或需重議的 ADR。

## Testing Decisions

- 使用者在 A10 同意測試 Seams 並確認 A1–A11 完整結論。第一項最高入口沿用真正 Tk 的語言選單、視窗開關／顯示與重試操作；第二項沿用共同輪次公開清理狀態與真實暫存磁碟摘要重建。必要的原因表述測試透過公開呈現契約，不為每個 helper 另增 Seam。
- 良好測試驗證實際內容、操作狀態、輪次與清理結果、保存 bytes 及重啟重建；不以 callback 呼叫次數、私有 widget 階層或登記資料結構代替驗收。
- 沿用已有真正 Tk 的多視窗切語、無效草稿保持、歷史事件選取／捲動及磁碟不改寫案例，以及自有提示視窗就地刷新與原模態效果案例。
- 用受控失敗接收者讓一個視窗更新失敗，驗證其他視窗與主畫面仍可操作。測試單個與多個失敗、彙整提示、診斷、修復後重試，以及連續切語後重試讀取最新語言。
- 驗證多次開啟、關閉、重開、隱藏／重新顯示、接收更新時已銷毀的視窗等情境，不留下失效接收者或造成其他視窗失去通知。
- 使用真實暫存 ledger、封存紀錄與 App 事件紀錄，驗證新原因識別／參數／兩語／診斷、混合新舊摘要與未知內容；由全新讀取器重建，不能只驗證記憶體物件。
- 沿用現有清理路徑替換、符號連結、損壞紀錄、未保存保護、期限變更與耐久性失敗重試案例；同樣輸入在本次改造前後產生相同刪除／保留結果。
- 切語與閱讀的磁碟不改寫檢查使用既存來源紀錄、舊摘要與既有事件 bytes；故意造成更新失敗後新增的診斷是合理的新事件，需與被保護的舊紀錄分別驗證。

### 第一項驗收矩陣

| 情境 | 通過條件 |
| --- | --- |
| 多個自有視窗已開時切語 | 標題、欄位與內容更新，視窗實例與操作狀態保持 |
| 有效／無效設定草稿 | 文字刷新但輸入與驗證狀態不清空 |
| 衝突與警報待處理 | 候選選取保留，不代替裁決或確認 |
| 診斷／歷史閱讀 | 事件選取、閱讀與捲動位置保持，原紀錄不改寫 |
| 新開、關閉重開、隱藏再顯示 | 使用目前語言，無重複更新或失效接收者干擾 |
| 一個／多個視窗故意失敗 | 其他視窗繼續更新，主畫面一則非阻擋提示與診斷入口 |
| 再次切語後重試 | 使用最新語言，不重開視窗或重啟監控；無持續自動重試 |
| 全部失敗恢復 | 清除現行提示，原失敗診斷仍可查閱 |
| 語言偏好保存／關閉保存 | 原偏好保存與錯誤處理保持，關閉期間切語仍被拒絕 |

### 第二項驗收矩陣

| 情境 | 通過條件 |
| --- | --- |
| 新輪次清理／App 事件／封存驗證原因 | 具有穩定識別、捕捉參數、同筆繁中／英文及原始診斷 |
| 重新讀取已保存摘要 | 保持原因、結果、時間、計數及識別，能依語言顯示 |
| 已知舊原因與混合新舊摘要 | 可靠辨識後翻譯，舊內容不改寫 |
| 未知原因或不適用原因表述格式 | 外層所選語言提示，詳細保留完整原文／原始內容，無猜測分類 |
| 保存失敗與恢復 | 保留既有摘要與清理進度，按原契約重試，不偽報保存成功 |
| 清理安全回歸 | 起算、期限、保護、路徑與耐久性檢查不變，刪除／保留結果相同 |
| 切語／閱讀 | 不重新啟動清理、不重寫原因紀錄或舊摘要 |

### C2 已驗證覆蓋（2026-10-13）

C2 (#34) 在固定 review base `d3068bff31fb1f99422121cf9d48e3c925a1c3c2` 上，將正式輪次清理及封存驗證 producer 接入 C1 同筆原因契約，並以真實暫存輪次、ledger、全新讀取器及 Settings 真 Tk 查閱驗證雙語、參數、原始診斷和關聯保持。可信封存／期限、受保護／未知／損壞資料、刪除計畫、路徑完整性、摘要失敗恢復及既存摘要唯讀回歸均通過；詳細證據見 [C2 local validation](evidence/retention-reason-ticket-02/local-validation.md)。這只記錄第二項中輪次／封存 producer 的適用覆蓋，不代表 App-event producer、所有正式畫面、父規格第二項或整體規格完成；C3 與 C4 仍待交付。

每項完成新增行為驗證、適用既有回歸及專案必要檢查，記錄實際命令、結果及限制。沒有執行的桌面或發布環境驗收不得宣稱通過；「試看看」以可觀察操作驗收，不代表已完成實測。

## Out of Scope

- 通用事件匯流排、監控結果／保存／關閉全部改成廣播，或各視窗新增背景執行緒。
- 改變機器狀態碼、來源證據、衝突裁決、警報確認、輪次結果與 KVM 顯示契約。
- 重啟監控、關閉重開視窗、持續自動更新重試或新增獨立清理排程。
- 放寬刪除資格、改保存期限或起算、刪除未知／損壞／待保存資料、移除路徑與耐久性保護。
- 改寫舊摘要、猜測翻譯、為各畫面語言持續增加每筆保存語言內容。
- 新增語言、變更現場翻譯資源管理、原生檔案選擇器系統文字即時翻譯。
- 啟動準備再次重構、其他事件身分交付改造、App journal 全文保存成本優化。
- 自動宣稱 M10、正式 bundle、工廠或 HMI／KVM 驗收完成；既有發布工作維持自身驗收範圍。

## Further Notes

- 日期：2026-10-12。來源為 LANGUAGE_REFRESH_AND_RETENTION_REASON_DISCUSSION_2026-10-12.md 的 A1–A11；使用者已確認完整結論並要求 to-spec。
- 訪談程式核對曾以 4b6efd7 為基準；規格製作時 checkout 為 B518-Log-Solution、59f28f2b31e72f947f52b31897068841bac1dbd9。已沿用現有自有提示通知、雙語資源與清理摘要結構作為背景；實作前再次核對最新版本，不把過往測試當本次通過證據。
- 一份規格保留兩項分別交付與驗收，不代表必須綁成同一次發布。本次不拆票、不直接改程式。
- 遠端規格議題：[GitHub #28](https://github.com/Bowei1121/B518_205_207_ATE/issues/28)，標記 ready-for-agent。開發票拆分另待核可；不修改父議題。

## L1 implementation coverage recorded on 2026-10-12

L1 provides partial evidence for the first acceptance item and applicable first-item scenarios: current-language refresh for the main page and App-owned notices, receiver failure isolation, a nonblocking main-page aggregate/retry path, and durable bilingual failure diagnostics. This is not evidence that every App window has migrated; settings/diagnostics/history remain L2, conflict/alarm/close remain L3, and removal of legacy refresh wiring remains L4. The L1 case mapping and real-Tk commands/results are recorded in [the L1 validation evidence](evidence/language-refresh-ticket-01/local-validation.md). Parent scenarios not reached by L1 remain unchecked and unclaimed.

## L2 implementation coverage recorded on 2026-10-12

L2 adds real-Tk evidence for the settings, App-diagnostics and historical-event windows receiving the existing language notification directly. It covers in-place rendering from each view's captured state, draft/tab and event selection/detail/scroll preservation, per-view close/destroy/hide/reopen behavior, failure isolation, the nonblocking main-page summary and manual latest-language retry, and unchanged event/audit bytes during language refresh. This is limited to L2's three views; conflict/alarm/close notification migration remains L3, and removing every legacy language fanout plus parent-wide first-item acceptance remains L4. See [L2 local validation](evidence/language-refresh-ticket-02/local-validation.md). Parent-wide coverage is not claimed complete.

## L3 implementation coverage recorded on 2026-10-12

L3's eight acceptance items pass on code/test SHA `04c2b0d04f1d6e634b57628b58306abdcd43bcdb`, with 383 final desktop tests (160.014 s, OK) and no unresolved Standards/Spec code findings. Conflict/alarm views directly receive L1 notifications; ordinary candidate/alarm/save updates remain. Same-window conflict_id, immutable detail, actual difference styles, wrapped raw reading anchor, candidate-list top and sash are preserved. Single/simultaneous failures, partial/full latest-language manual recovery, withdraw/WM/Destroy lifecycle and close-time disabled/queued retry guards have final evidence. Actual Atlas/sample-json source-to-Tk/disk paths and existing save/close/KVM regressions pass. Earlier failed attempts remain documented; no L1 notice product repair was included.

This covers first-item scenarios 3, 5, 6–8 and the L3 portion of 9. It does not mark parent-wide nine-scenario acceptance complete: L4 still owns the full integrated first item and remaining legacy-path cleanup; cleanup-reason second item and bundle/field acceptance remain separate. See [L3 local validation](evidence/language-refresh-ticket-03/local-validation.md) for case/command mapping, native-menu/WM limitations and merge/destination chronology.

## L4 implementation coverage recorded on 2026-10-12

L4 (#32) removes the last redundant language-change fallbacks: `show_notice` now requires the existing central receiver-registration callback, and `_select_language` has no pre-notifier direct-render fallback. The one `_apply_main_language()` call retained in `_build()` is first render; normal round/event/save/status presentation remains data-driven. Settings, App diagnostics, history, conflict, alarm and notice views remain on the already-verified L1 receiver contract; close progress continues to use current App language under the existing close gate.

The final code/test SHA `6d1cf22cb68af94962fcdcfd0ef92a614369a2ac` passes the complete desktop suite on Python 3.11.7 / Tk 8.6 (383 tests, 152.591 s, exit 0). The true-Tk source integration test drives a temporary sample-json source through the actual profile/App/shared-round path and verifies the source file and persisted cleanup ledger remain byte-identical through language changes, a failed conflict-window refresh, manual retry and history-view reopen. The final-version test mapping for all nine first-item scenarios, seven L4 acceptance items, bytes-preservation evidence, the Python 3.8.10 `Tcl_AsyncDelete` failure and its reproduction on the fixed pre-L4 base are in [L4 local validation](evidence/language-refresh-ticket-04/local-validation.md). The native menu entry uses Tk `Menu.invoke` in automated cases; the evidence does not claim physical menu-item or native keyboard navigation.

This closes the parent first item in scope for L4 only. The cleanup-reason second item (C1–C4), bundle/factory/field verification, and all product/KVM policies remain separate. Remote Issue #28 and its ticket are not modified or closed.

## C1 implementation coverage recorded on 2026-10-12

C1 (#33) adds an optional versioned bilingual reason record to cleanup summary rows and a public presentation contract for new and producer-verified legacy reasons. The existing settings cleanup summary reads fresh ledger records in English and Traditional Chinese and presents successful, skipped, and failed round outcomes plus App-event and archive-verification reasons. It retains raw source reason/diagnostic details, uses captured English text when a current resource or required parameter is unavailable, and wraps unknown content in a localized explanation without displaying the internal message identifier. Reading and switching language preserve ledger bytes; the reason presenter does not participate in cleanup eligibility. This is C1 evidence only: round/archive and App-event producers remain on their existing raw-reason paths for C2 and C3, while C4 owns complete status-screen integration and parent second-item acceptance. See [C1 local validation](evidence/retention-reason-ticket-01/local-validation.md); this paragraph does not mark the parent second item complete.
