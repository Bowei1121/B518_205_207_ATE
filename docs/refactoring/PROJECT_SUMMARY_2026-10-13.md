# 專案摘要 — 2026-10-13

## 歷史事件查詢規劃與規格

- 歷史事件查詢 A1–A18 及整體方向已確認：單日／日期範圍／最近90天預設、工廠當地時間、純放大鏡查詢與左右箭頭分頁、每頁100筆、背景重查／取消、固定結果與可重建索引。無時區舊資料直接視為當地時間，完全無有效日期者保留異常提示與原文；不改來源或清理資格。
- 討論文件與詞彙提交 b4dba1c、圖示補充 a247c9e 已同步既有 Gitea／GitHub。使用者明確要求工廠驗收不得阻擋開發票合併，必要程式／測試／桌面驗證與後續現場驗收分開記錄。
- 使用者確認沿用歷史讀取／呈現、真實暫存紀錄、查詢提交／取消／結果取得，以及真正 Tk 操作的測試入口。to-spec 已建立 HISTORICAL_EVENT_QUERY_SPEC_2026-10-13.md，45項故事及七個規格章節，發布 GitHub #37 並標記 ready-for-agent。
- 216萬筆合成事件為規格指定工程容量驗收，非實際產品件數換算；首次索引、增量、降級、分頁及來源不變分開驗證。本次僅驗證文件結構，不宣稱產品測試、容量或現場驗收已完成，尚未拆子票或改程式。

## 本對話：優化後的架構優先順序

- 延續 10/12 已確認的 A1–A11，完成多視窗語言刷新與清理原因規格 #28，以及八張開發票 #29–36；使用者核可粒度與兩組獨立依賴。文件提交 088caae、82c4a13 已經明確授權發布與推送，兩遠端曾直接確認同為 82c4a13。以下區分拆票歷史與其後實作，不將票件發布視為程式完成。
- 本次來源分析固定基準為主線 5f5ff17cfabaf09fd6e26e4561e4c6a5fbd953cc。R1–R3、語言 L1–L4、原因 C1–C4 均已實作與有逐票驗證；M10 source 已合併，正式 bundle／目標設備仍沿既有發布範圍另待驗收。過時 ADR 狀態標頭不作現況依據。
- 本次沒有修改程式、重跑完整產品套件或接觸現場資料。前次 C4 的 405 tests 是既有 source 證據，不能當成本次通過結果。
- 首推 P1：歷史查閱 Module 的載入與呈現工作管理。Tk 開啟／重新整理歷史同步讀取全部輪次與 App 紀錄、排序並全量呈現；合成資料成本支持優先改善畫面可操作性，未宣稱監控結果遺失。
- 本機 Python 3.11.7、真實暫存合成舊 events.log，三次暖快取量測中位數：100輪／1,000筆，讀取排序 0.0244秒、文字計算 0.0162秒；500輪／10,000筆為 0.2841秒、0.1775秒；1,000輪／50,000筆為 1.1009秒、0.8504秒。來源 bytes 均保持。兩段中位數合計約 0.0406／0.4616／1.9513秒，未包含 Tk 插入、正式 audit 或現場磁碟，不作工廠效能預測。
- P2：先量測 AppEventStore 每筆整份 journal 讀寫與診斷取閱深複製的成長成本，再決定保存策略；診斷已有 revision 閘門，不是每150ms無條件取全份資料。此處本次沒有量測，不宣稱現場瓶頸。
- P2 後順位：集中即時事件身分與相容交付，減少 Tk 快照搜尋及文字補配。正常輪次身分已可靠，尚未重現誤配；真正相容 Adapter 不可直接刪除。
- 暫不為檔案長而重拆清理安全；跨 Module 的期限、關閉、提交意圖與 fsync 協調承載真實安全責任。候選遵循既有 ADR，目前不提出具體新 Interface、不新增開發票。
- 繁體中文 HTML 前後對照報告與原始量測 JSON 依技能保存在 OS 暫存目錄；本摘要保存持久結論。使用者另要求一併提交未提交 Git 檔案，開始時僅兩份 10/09、10/12 討論摘要，無未提交程式；本次核對並補上歷史狀態說明，連同本節提交。

## 前次討論與結果

- 當日開始時狀態：延續 2026-10-12 的多視窗語言更新與清理原因表述工作。C1（#33）及 C2（#34）已完成並有最終驗收證據；C3（#35）正式 App-event producer 已實作且非 Tk 契約測試通過，但最終 Tk 全套被 macOS AppKit 建窗異常阻擋；C4（#36）全畫面整合仍待執行。後續章節記錄 C3、C4 當日完成驗收與交付後的狀態。
- C1 固定審查基準為 `14d7c23195d66962b86b8b301cdcc587b3a15c3d`。最終程式／測試 SHA 為 `5cf609d7a4a168d3701490b2ce51b27bafe25d3e`，票分支最終文件提交為 `fc43073eafcfb47053b6948086d9754ef1588b58`。缺少目前語言資源時使用捕捉時保存英文的回歸測試先失敗、實作後通過；固定基準 Standards／Spec 複審無阻擋。
- 真正 Tk 桌面完整套件在程式／測試 SHA `5cf609d` 通過 394 項／145.474 秒；本機主線快轉合併後，最初一次套件執行停在既有提示視窗重開案例。受控 Tk 檢查確認提示視窗可見、確認按鈕持有焦點與模態 grab，Escape 能關閉視窗；隔離測試通過 1 項／2.444 秒。之後主線完整套件於 Python 3.11.7／Tk 8.6 通過 394 項／127.882 秒／結束碼 0，第一次停住未再重現，也未因該次停住修改產品或測試。

## C1 本機整合與遠端狀態

- 乾淨整合 worktree `/private/tmp/B518-C1-merge` 將 `B518-Log-Solution` 從 `14d7c23` fast-forward 至 `fc43073eafcfb47053b6948086d9754ef1588b58`，沒有建立 merge commit。主線完整含 Tk 套件通過後，透過既有 `origin` push destinations 推送主線；推送命令回報 Gitea 與 GitHub 均由 `14d7c23` 前進至 `fc43073`。
- 2026-10-13 08:33 Asia/Taipei 的 push 前直接 `ls-remote` 查詢兩個目的地都顯示主線 `14d7c23`、`LanguageRefresh/ticket-05` 為 `fc43073`。最終文件提交後再次直接查詢目的地的結果應記錄在交付回報，避免在本摘要內自引用文件提交 SHA。
- 正式 worktree `/Users/tsengbowei/Desktop/公司資料/專案/FQ III/2026/B518/專案名稱/3. 程式/0. PC/B518 Log Solution` 原有 `PROJECT_SUMMARY_2026-10-09.md` 與 `PROJECT_SUMMARY_2026-10-12.md` 未提交修改受到保護，沒有併入 C1。只使用乾淨整合 worktree 更新 C1 文件及本摘要。
- 尚未直接完成 final-document push 查詢前，不刪除 C1 票分支或其 worktree；不移除任何其他分支、worktree 或 push destination。

## C2（清理原因組 #34）

- C2 固定 review base 為 `d3068bff31fb1f99422121cf9d48e3c925a1c3c2`；查證 C1 最終程式 `5cf609d7a4a168d3701490b2ce51b27bafe25d3e` 是其祖先，且基準已含 C1 ledger 相容讀取、原因捕捉／呈現、原始診斷、英文回退、真 Tk 與審查完成證據。C1 先前提示視窗重開測試的暫停問題已在固定基準前以可見視窗／焦點／modal grab／Escape 操作及後續完整桌面套件驗證處理；本次 C2 另重新完成全套。
- 輪次清理成功／跳過／失敗、即時狀態及封存驗證 producer 現於正式產生點捕捉 C1 原因識別、參數、同筆英文／繁中與診斷；schema 2、active plans、刪除進度、可信封存時間、資格與路徑／完整性門檻維持。補強後符號連結、路徑不一致及未知檔案有專屬原因識別，仍維持原 skipped 與保留結果。App-event producer 留在 C3，完整畫面遷移留在 C4。
- 固定基準及 C2 版的 `tests.test_round_archival tests.test_round_retention` 均各 45 tests / OK。C2 code/test SHA `316fc7005b3e1ca4992da5601a9882b543228177` 的 Python 3.11.7 / Tk 8.6 桌面完整套件通過 394 tests / 143.542 s / exit 0；在本機快轉主線 SHA `657ce8a2f53aba543fac663217d2057f0abb489a` 再通過 394 tests / 168.394 s / exit 0。首次受限 runner 在 `tkinter.Tk()` 的 AppKit/LaunchServices `NSException`（exit 134）中止並記錄為失敗；相同全套之後在已授權桌面環境完整通過，未將中止當成功或跳過 Tk 案例。無專案既有型別檢查設定。
- 基準／C2 使用相同暫存 fixture 的正式清理入口，對照期限前／後、期限變更、受保護輪次、損壞封存、外部 symlink、目錄替換、初始計畫保存失敗，以及刪除完成後摘要保存失敗和全新讀取器恢復；所有正規化結果一致，外部檔案雜湊不變。最後 Spec 複審者獨立重跑五個延伸情境並確認一致。詳細 fixture／harness 證據見 [C2 local validation](evidence/retention-reason-ticket-02/local-validation.md)。
- C2 真 Tk 使用正式輪次封存及公開清理入口、隔離暫存資料、保存 ledger、全新 coordinator 讀取與既有 Settings 摘要視窗；雙語原因、原始診斷、磁碟 bytes 不變及 archive write failure/retry 有驗收證據。固定基準 Standards／Spec 雙軸複審無阻擋；非阻擋整理建議為移除 `_archive_failure` 未使用參數並考慮合併兩個小型捕捉包裝函式。
- C2 本機快轉後的主線已推送至 Gitea 與 GitHub。文件收尾提交 `ff90c2d06d9fbd8857c0eecb17a348df4763a2b2` 後，2026-10-13 09:52 Asia/Taipei 逐一直接查詢兩目的地皆回報主線此 SHA，且 `LanguageRefresh/ticket-06` refs 均不存在；其後的摘要更正將再次推送及查詢。已用一般刪除移除已合併的本地／遠端票分支及乾淨 C2 專用 worktree；其他 C1、L1 及專案 worktree 保留。原先兩份主線 summary 修改已自保護 stash 原樣還原，diff hash `a2d2e90729f70f9e6c932aba7331a9f77eba50c1b0c8dc61bc7e2068dfd2bdc6` 與保存前 patch 一致，仍未提交；stash 保留作備份。

## 驗收界線

- C1 的原因表述只控制顯示，不參與清理資格；可信封存時間、App 原事件時間、期限、保存保護、路徑／符號連結、原子替換及 fsync 行為沿用既有契約。正式輪次／封存與 App 事件 producer 尚未分別由 C2／C3 遷移；C4 才負責全部畫面及父規格第二項完整驗收。
- 清理原因父規格第二項尚未完成。C2、C3、C4 未交付前，不宣稱全部清理原因雙語化或全 App 畫面整合完成。遠端 Issue #28 與各拆票均未修改或關閉。

## C3（清理原因組 #35）

- C3 固定審查基準是 `f80e86a51907988613185155ed69552c9f392426`；確認該基準包含 C1 的相容原因讀取／呈現和 C2 輪次／封存 producer。C1 的提示視窗重開／Escape／wait_window 收尾問題已有實際 Tk 操作及 post-merge 全套證據；C2 已有正式 producer、全套及 review 證據。C3 只負責 App-event producer，C2 非本票直接依賴，C4 才負責全畫面統一與父規格第二項完整驗收。
- App-event 清理現在於正式決策點捕捉 C1 結構化原因；保留原事件時間、全域期限、退休序號、pending／耐久性保護、管理根目錄、符號連結／路徑替換、原子替換與目錄 fsync。補上期限掃描後變更時的即時重新資格檢查，保存為 `skipped` 原因，不誤報刪除或失敗；清理政策及恢復協調未重寫。真 journal → 清理 → ledger → 全新 coordinator 有磁碟驗收；兩個 Tk 查閱案例曾於較早版本通過，最新版本的畫面驗收仍待重跑。
- 最新版本 `4cb353f` 的 `tests.test_app_event_store tests.test_round_retention` 聚焦套件通過 55 項；Spec 複審揭露的「期限延長後合法 skipped 在全新讀取器中被改成 failed」已用真實暫存 journal、ledger 與 fresh coordinator 回歸測試修正。固定基準與候選刪除／保留、計數及序號對照一致。最終完整含 Tk 套件於 2026-10-13 12:00 首次、12:08 再次在 `tkinter.Tk()` 建窗階段因 macOS AppKit 原生異常中止，兩次 exit 134；非 Tk 測試先行，Tk 測試本體未開始。完整命令、堆疊及重驗紀錄見 [C3 驗收紀錄](evidence/retention-reason-ticket-03/local-validation.md)。歷史 397 項全套通過發生於最終耐久性修復前，不可代表目前交付版。C3 保持部分驗證，必要桌面全套／畫面驗收仍阻擋合併；無專案型別檢查設定。
- C3 程式 SHA 為 `4cb353f`，固定基準雙軸複審及最終驗收紀錄已提交於 `0abbb63`。程式、驗收與 review 已分批推送至 `LanguageRefresh/ticket-07`；`0abbb63` 推送後直接查詢 GitHub 與 Gitea refs，結果記於最終交付回報。主線未合併，C3 專用 branch/worktree 保留；既存主線 summary 修改及 C1／其他 worktree 均不動。C4 與父規格第二項不宣稱完成。

- C3 後續查明先前 Tk 建窗中止是沙盒 GUI 服務限制：同一最小 Tk 程式沙盒內 exit 134、沙盒外 exit 0。沙盒外完整套件在 `e4d2ba7` 跑完 403 項／126.985 秒，有一項實際失敗：成功清理仍保存 commit intent，全新讀取器把摘要原因呈現為 interrupted。目前阻擋已改為具體 C3 完成摘要／恢復標記契約缺口，須修正並保留 fsync 不確定保護後重驗；尚未合併或清理。

- C3 最終修正 `7639be8b8af1fb77461706d763ae95402ae3a3cc`：完整摘要含恢復標記先耐久保存，再解除標記並同步；新讀取器正常完成狀態／雙語原因／身分／時間與 ledger bytes 保持。解除標記 fsync 失敗的公開恢復測試通過；56 項聚焦測試、基準對照及最終桌面完整套件 404 項／140.160 秒／exit 0 均通過。固定基準双軸複審無未解阻擋。正在完成最後文件複核、保護原主線摘要修改及合併／主線重驗／同步清理；C4 與父規格第二項不宣稱完成。

- C3 最後文件複核雙軸通過。主線兩份既存摘要修改已備份雜湊並暫存，確認乾淨後 fast-forward 整合至 `509800011496e90fbd6aabf23a68f90bbdaa10e7`，沒有另建 merge commit。主線再驗完整桌面套件 404 項／133.908 秒／exit 0；程式／測試仍對應 `7639be8`。接續直接查詢全部目的地後安全清理本票並還原原修改。

- C3 交付完成：主線／票分支於 2026-10-13 13:01:53 直接確認 GitHub、Gitea 均為 `e13060fff25d89b5ed630f09ce0421e20f771734`，才安全刪除已合併票分支（兩遠端及本地）與乾淨 C3／C3-baseline 工作樹。13:03:33 再查確認兩主線一致、兩遠端票分支不存在。原主線兩份摘要修改逐檔雜湊一致還原，未納入本票；只移除本次保護 stash。目前正式工作樹為 `B518-Log-Solution`，C3 沒有剩餘阻擋；C4、父規格第二項整體及 bundle／工廠驗收維持各自範圍。最後清理文件提交後仍將再次正常推送並直接查詢全部目的地。

## C4（清理原因組 #36）— 最終候選驗收

- C4 固定審查基準及主線起點為 `9d53ced227591f92cd20bad789ebdccdb05f8950`。Git ancestry、實際程式及驗收文件確認 C1、C2、C3 都已整合；C1 先前提示視窗重開停滯已有真正 Tk 操作與後續主線完整套件證據，不是目前直接依賴阻擋。本票未混入前票修復。
- 正式設定清理摘要與主畫面封存／保存狀態的新舊原因都經 C1 集中表述契約。修正即時 close-skip 狀態未顯示結構雙語詳細資料，以及主畫面封存舊訊息繞過相容呈現器的漏接。外層依目前語言，原始 JSON／診斷可查；時間、身分、outcome、計數、序號及保存狀態不由顯示文案推導。Tk 原因中文全文／前綴辨識只留在 `cleanup_reasons` 相容 Implementation。
- 桌面 runtime 為 Python 3.11.7 / Tk-Tcl 8.6 aqua，實際 root 建立、更新及銷毀成功。原因聚焦套件 82 項通過；五個真 Tk 顯示／重建案例通過；最後 UI 舊原因回退調整後 67 個聚焦測試通過。程式／測試 SHA `af6c21996da36eea1365e0634dacd4db978bdbca` 的完整含 Tk 套件通過 405 項／142.185 秒／exit 0。較早整套有兩項失敗：一項舊斷言把可檢視英文原始雙語資料誤判成中文顯示錯誤，已改為分別檢查中文外層和原文可查並重驗；另一個 2 秒同步等待單獨重跑及最後整套均通過。命令、case 對照及日誌見 [C4 驗收證據](evidence/retention-reason-ticket-04/local-validation.md)。
- 固定基準／候選相同隔離 App-event fixtures 對照涵蓋腐損、混合到期、未到期及路徑替換；刪除／保留、計數、退休及下一序號、外部／管理檔案結果一致。C4 未修改清理 producer、期限、journal、ledger、封存、耐久性或恢復政策；C2/C3 的輪次／App-event正式 producer 安全對照仍維持其票證據。
- 固定基準 Standards／Spec 審查均已通過且無阻擋。C4 候選 `af6c219` 與乾淨主線快轉整合 SHA `2c3514715b2c23799dfc79d4396ef2cba11c73fb` 均通過完整 405 項含 Tk 套件（主線 145.982 秒／exit 0）；八項 C4 驗收與母規格第二項七情境有逐項最終版證據，故第二項已完成。主線與票分支最終文件歷史 tip `b7cfa054e4aff38111488ee9ed7b7d92f279bfde` 曾於 13:48:43 CST 直接確認兩遠端一致，之後已安全清除只屬 C4 的已合併分支與乾淨 worktree。清理記錄文件提交 `20197c956d921b2d2f4f1ccd9f9f9ab7bb80638c` 於 13:49:54 CST 直接確認 Gitea/GitHub 主線一致且票分支不存在；最後驗收文件更新與推送查核見 [C4 驗收證據](evidence/retention-reason-ticket-04/local-validation.md)。原主線兩份摘要修改以 path-limited stash 保護且未混入本票，完成推送後還原。不宣稱 bundle、工廠或現場驗收。

## 歷史事件查詢拆票發布

- 使用者核可H1–H8拆分。已建立GitHub #38–45，全部ready-for-agent，並設定原生阻擋關係：H2/H3→H1；H4→H3；H5→H2/H4；H6→H3/H4；H7→H2/H3；H8→H5/H6/H7（箭頭指向阻擋票）。
- 每票有本機獨立文件及總覽，父規格#37未修改或關閉；先從H1開始。逐票必要開發／測試／桌面驗證可合併，工廠驗收不阻擋。票件發布不等於程式實作或容量驗收完成。

## H1 後續實作與驗收 — 2026-10-13

- H1 在 `HistoricalEventQuery/ticket-01` 實作日期條件與背景首批查詢，接入既有歷史頁面和來源讀取／呈現流程。開啟及編輯日期不讀來源；放大鏡／Return 提交有效條件，最新事件優先顯示最多100筆，明確說明後續分頁尚未交付。來源優先與事件身分沿用既有 reader。
- 審查發現的四項缺口均已修正：不為無時區 fall-back 時間猜測 fold 絕對時刻；重查／失敗時舊結果仍標示舊日期；讀取錯誤或無日期資料使狀態明確標示不完整；列出首批摘要不提前格式化完整詳細原文。真正 Tk 驗收檢查慢讀中可編輯、查詢失敗保留、損壞來源不冒稱無事件、選取後原文／雙語詳細及捲動保持。
- 固定 Standards／Spec review base `5aa83e2438dca802706aaba9aa10daa09bbee150`；最後程式／測試 commit `714d7239ba60bf55fd337b7f270eca7f51d24892`。Python 3.8.10、Tk/Tcl 8.6/8.6 的解鎖 Aqua 桌面完整含 Tk 套件 `B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py` 通過 417 項、130.078 秒、exit 0；聚焦 query/display 25 項及 H1 真 Tk 案例也通過。複審發現查詢送出後排序仍可能讀取變動中的 process timezone，已於 `714d723` 快照凍結 timezone，並以跨 DST fold、送出後切換 TZ 的測試驗證；其後固定基準 Standards／Spec 複審均無阻擋。非阻擋可攜性限制詳見 [H1 local validation](evidence/historical-event-query-ticket-01/local-validation.md)。無專案型別檢查設定，不宣稱型別檢查通過。
- 來源 audit、舊 `events.log` 及 App event journal 在真正暫存 Tk 驗收查詢前後逐檔 bytes 相同。測試不是持久索引／容量保證；H2 負責完整取消與生命週期，H3 完整分頁，H4 持久索引及增量成本，H5–H8 依各自範圍接續。`B518-Log-Solution` 於 `9460594200d191e7a172b67dda771027974c8572` 快轉合併（無 merge commit），合併後完整含 Tk 套件 417 項／128.783 秒／exit 0。2026-10-13 18:58:08 CST 直接查詢 GitHub 與 Gitea 均確認主線和票分支當時為該 SHA；之後已一般刪除兩遠端及本地票分支。最終文件提交 SHA 與推送後直接查詢結果列於本次交付回報。父規格 #37、Issue #38及現場資料未修改。

## H2 重新查詢與視窗生命週期 — 2026-10-13

- H2 以 `HistoricalEventQuery/ticket-02` 接續已納入主線的 H1：固定審查基準為 `0699ab74b96e43a60e53f0cd7f7e2fabdbebde05`，H1 程式／驗收祖先已在該基準。新提交 `dd6b08796cf6ce0025979531fb7ea4c855299764` 建立 app-scoped query service，接入實際歷史頁、取消按鈕、視窗 close/destroy、App close/reopen 與 Tk polling；背景讀取以協作取消及最新 generation 過濾過期結果、進度與錯誤，一次只保留一個執行工作及最新待處理查詢。舊結果與其日期範圍在新查詢成功前保持不變。H2 不改監控／保存／清理政策，不宣稱 H3–H8 或父規格完整交付。
- 真正 Tk 使用隔離暫存來源與 Event 控制慢讀，實際操作日期欄位、重查、取消（含無舊結果）、WM close/reopen 及 App close；驗證提交條件固定、未送出草稿可修改、晚到錯誤不覆蓋新查詢、取消保留舊結果或清楚呈現空狀態、舊視窗不能更新新視窗，App close 不等待被阻塞的歷史讀取。WM 協定由 Tk protocol callback 驗證，未宣稱實體標題列滑鼠操作。聚焦 14 tests 通過。測試於查詢前後逐 bytes 確認隔離 audit 與 App event 檔不變。完整測試命令 `PATH=/opt/anaconda3/bin:$PATH B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py` 於正確 Python 專案目錄，以 Python 3.11.7／Tk-Tcl 8.6.12 Aqua 桌面執行：最終重跑 419 tests、129.330 秒、exit 0。`git diff --check` 及 `python3 -m py_compile` 通過；repo 無既有 type-check 設定。
- Python 3.8.10／Tk 8.6 預設 interpreter 的完整套件曾以 exit 134／139 發生 `Tcl_AsyncDelete`／Tk 跨執行緒 abort。固定基準的隔離 worktree 也重現：一次完整 suite 通過 417 tests，另一次加 faulthandler 執行發生 exit 139，stack 指向既有 audit/event writer 與 conflict notice 的跨執行緒 Tk `event_generate`；這是固定基準既存 runtime 問題，不將其宣稱為通過。此票選用已解鎖桌面、可成功建窗的 Python 3.11.7／Tk 8.6 執行完整 suite，並保留 Python 3.8 差異作限制證據。
- 固定基準 Standards／Spec 雙軸審查均無阻擋。完成 commit `496346fb93f0c5bc7164130188020ae3f0f836af` 將 H2 快轉合併至 `B518-Log-Solution`（無 merge commit）；合併後在主線以 Python 3.11.7／Tk 8.6.12 Aqua 桌面重跑完整含 Tk 套件，419 tests、130.840 秒、exit 0。2026-10-13 20:13:20 CST 推送後直接查詢 GitHub 與 Gitea，兩者主線及 H2 票分支皆為 `496346fb93f0c5bc7164130188020ae3f0f836af`，`main` 仍為 `5acfb2e206c917de7b9232d41f47e54a1c866917`；票分支清理及最後文件 SHA／同步結果以本次交付回報為準。H3 完整分頁、H4 持久索引、H5 異常恢復、H6 保存／清理競態、H7 完整圖示／鍵盤／雙語整合、H8 容量與舊流程收尾仍在各自範圍；沒有宣稱工廠驗收。
- 固定基準雙軸審查均無阻擋：Spec 確認 H2 範圍與最後版測試證據吻合，並指出單一來源檔讀取中的 I/O 無法被強制中斷，取消會立即使請求失效，返回後丟棄結果；Standards 的唯一非阻擋建議是可考慮把 generation-keyed completion map 簡化成單一 completion slot。詳細審查與最終遠端狀態見 H2 驗收證據。

## H3 完整分頁與按需詳細 — 2026-10-13

- H3 固定審查基準 `d0a244b6b53a31e1fc9e57ceefcf9d9f1e959f79` 已包含 H1／H2 實際程式與可查證交付證據。H3 以 SQLite 暫存固定單次查詢集合；列表記憶體只保留精簡摘要，原始 event JSON／長診斷只在選取時從暫存取得。公開頁面入口以 100 筆範圍讀取，翻頁不重新掃描來源；查詢替換或 App 所有者銷毀時關閉並刪除暫存。
- 真 Tk 頁面整合涵蓋 audit 與 App-event 混合資料，實際箭頭操作第一／中間／末頁與返回，驗證跨頁身分集合、原詳細按需載入、慢詳細讀取期間仍可操作，且來源 bytes 不變。受控 205 筆資料含每筆 45,500 字元詳細：來源 9,419,450 bytes、SQLite 暫存 28,590,080 bytes、查詢 tracemalloc 峰值 714,189 bytes，頁面為 100／100／5；此小型可重現觀測不是 H8 容量驗收。
- Python 3.11.7／Aqua Tk-Tcl 8.6.12 桌面最終完整 `B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py` 通過 429 tests／143.026 秒／exit 0；56 項聚焦來源／query 測試、四個 H1/H2/H3 整合 Tk 案例、`py_compile` 與 `git diff --check` 均通過。初次最終全套曾在輪次封存測試 `TemporaryDirectory` 收尾發生一項目錄非空錯誤；單項與 `test_round_archival` 17 項重跑通過，之後整套通過，已於驗收紀錄保留首次失敗。Standards 審查的 SQLite close/open 暫存重建競態已用 read-only 連線和 barrier 測試修復。程式／測試 commit `f17f62b` 已推送至 Gitea 與 GitHub；固定基準 Standards／Spec 無阻擋。非阻擋建議：頁面讀取失敗的完整恢復提示屬 H5、detail service 名稱略窄。合併後主線重驗、最後文件 SHA／目的地直查及分支清理待後續交付流程記錄。無專案既有型別檢查設定，不宣稱型別檢查通過。
- H3 不交付 H4 持久索引／跨重啟重用／跨查詢增量成本保證，也不宣稱 H5–H8 或父規格完整交付。非實體滑鼠硬體操作證據採真正 Tk widget event 操作；未宣稱工廠或正式部署驗收。
