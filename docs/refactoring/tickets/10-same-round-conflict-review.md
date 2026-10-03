# 10：共同處理已確定同輪的結果衝突

**類型：**新增

**What to build／工作內容與交付結果：**已確定同輪、同通道的矛盾由共同人工確認流程處理，提供保留原結果／採用新結果，其他位置繼續監控。

**Blocked by／前置依賴：**

- [04：搬移 B482 資料來源並保護完整監控流程](04-b482-source-adapter.md)
- [05：搬移 RS-WMT 資料來源並保護完整監控流程](05-rswmt-source-adapter.md)
- [09：統一通道期限與正常完成規則](09-channel-deadlines-and-completion.md)

**Status：**implemented; five controlled acceptance checks and Standards/Spec review passed; hardware/release acceptance pending

## 驗收條件

- [x] 顯示位置、原／新 SN、原／新結果、來源識別與來源時間，缺資訊顯示未知而非複製時間。
- [x] 兩種選擇僅處理所選衝突，結果與選擇時間有紀錄。
- [x] 確認期間其他位置持續收集與計時；多項衝突不覆蓋或因一項選擇一起清除。
- [x] 結果齊全即停止讀新 Log，原結果與候選保存；必要確認全部處理後才可取用，不增加人工倒數。
- [x] 不同路徑但內容一致的重複來源可追查，不重複發結果或直接報衝突。

## 驗證方式

用已確定同輪的矛盾／一致重複樣本，多項確認及停止收集後選擇驗證完整流程。

**規格驗收對照：**AC-16、AC-18、AC-19、AC-17（其他位置持續監控部分）

## 保留決策、待確認事項與限制

未知是否同輪時能否人工採用仍未決，本票不得默認任何政策或宣稱此分支完成；交由 18。黑白標記可見及上位機暫停接續 12／16。

所有行為測試須依 01 的接口確認結果落實；本次批准任務清單不代表測試接口已獲批准。未知同輪來源能否人工採用仍由 18 決定，任何本票的已完成部分都不能抵銷該未決分支。

## 執行與追蹤

## Ticket 10 執行紀錄（2026-10-02）

- 基準 commit：`f11473ba9bab60092ff61e695e7df1d592bb88a7`；分支：`codex/ticket-10`。依 Git 現況核對 Ticket 04、05、09 的 Adapter／共同輪次依賴已在基準；Ticket 03 驗收及 Ticket 05 實機即時時機仍未完成。Ticket 16 上位機整合及 Ticket 18 未知同輪來源採用政策維持未決，沒有把前票受控回放當作豁免。
- 共同 `MonitoringRound` 保存不可變衝突快照及有序多候選佇列。每筆衝突記錄有效顯示位置、來源位置、來源識別、原／候選 SN 與結果、同輪證據、來源時間（無值為未知）；候選擷取後不重新讀檔。Tk 提供非模態「保留原結果／採用新結果」，關閉視窗不代表選擇。提交需帶輪次及衝突識別；重複或過期提交不會套用至新輪。
- 判定界線：Atlas 只把活動中的相同來源位置與可信 SN 對應的穩定變更作為本輪候選；活動來源身分變更但無足夠同輪證據時保留未決證據。B482 的相同批次需來源位置、檔名批次戳及 Thread／配置證據相符；沒有批次連結的 CaseInfo 矛盾資料不自行視作同輪。RS-WMT 以來源位置及解析後測試開始時間識別同輪，候選結果仍須通過各自檔案穩定等待。來源時間只使用 Adapter 解析出的來源時間；不以現在時間或複製時間填補。來源證據不充分的資料不進入人工採用選項，留待 Ticket 18 決策。
- 重複相同來源／相同值只新增追查事件，不重複結果或衝突；不同路徑但值相同的資料不作衝突。相同衝突的輪詢候選去重；內容或值改變則建立新候選。每個 `conflict_id` 保存觀察當下不可變的原／候選快照；選擇「保留原結果」或「採用新結果」都將該衝突選中的快照寫為目前有效結果，且只關閉該項。若同位置還有其他候選，後續選擇仍可更新該位置；最後一個操作員選擇決定有效結果。事件同時記錄該項原／候選、選擇時間及 `result_after_*` 實際有效值。此規則依明確人工操作順序執行，不受輪詢執行緒時序影響；候選不重新讀檔，也不因別項選擇而失效或清除。
- 輪次即使有待確認仍繼續輪詢其他位置及推進 Ticket 09 期限。所有有效位置終態後立即停止讀新來源；已捕捉候選仍可離線選擇，全部必要確認處理且無其他放行阻擋後才可取用結果。期限定案及人工停止的阻擋不因衝突選擇而解除；沒有新增完成倒數。
- 五項驗收均由共同公開快照／事件／選擇接口、Atlas／B482／RS-WMT Adapter 測試及隔離實際 Tk App 回放支持。代表性流程使用容量 2 與非恆等映射，顯示衝突後先完成另一位置，確認收集停止、候選保留，關閉視窗仍未選擇，重新開啟並保留原結果後才放行。畫面環境：macOS 10.16（`platform.mac_ver` 回報）、Python 3.8.10、Tk 8.6、1440×900、Tk scaling 約 1.0；衝突視窗 820×430，置於主看板左側以保留頂部色帶與輪次狀態可見。輸入、設定及輸出使用隔離目錄，原始實機資料保持唯讀。
- Spec 複審另要求明確定義同位置多候選的反向選擇順序。已固定操作員最後一次選擇寫入該衝突選中的不可變原／候選快照；保留原結果也會還原該項觀察時的原快照。事件同時記錄選中的值及操作後有效值。`test_each_same_slot_candidate_is_resolved_independently_in_user_selected_order` 覆蓋先採用後保留及反向兩種順序；先確認紅燈，再修正後通過。
- 測試：最新完整 `python3 scripts/run_tests.py`（144 項全通過，含 B482 未決證據與雙向選擇順序修正）；`python3 scripts/run_tests.py test_monitoring_round test_log_monitoring`（38 項通過，含新 B482 案例）；`python3 scripts/run_tests.py test_monitoring_round`（選擇順序修正後 22 項通過）；`python3 scripts/run_tests.py test_log_solution_ui.LogSolutionUiTests.test_atlas_round_shows_nonblocking_conflict_and_releases_after_other_slot_finishes`（1 項通過，含視窗不遮擋看板斷言）。Tk 測試須在有桌面權限的環境執行。專案沒有 mypy／pyright 或其他既有型別檢查設定，未以 `compileall` 代替型別檢查。
- 未驗收範圍：真實治具／KVM、Ticket 05 所需即時實機資料時機、目標設備、發布 App、上位機共同整合均未執行；Ticket 03 既有驗收仍未完成。未知是否同輪來源可否人工採用仍交 Ticket 18；Ticket 11 警報與放行、Ticket 12 黑白標記及 Ticket 16 上位機整合未擴張或宣稱通過。
- 程式與交付提交：`afe56a2`、`194f2c4`、`41627c6`、`67099e4`、`5c6bd8d`、`42e8c05`、`f81198f`、`f50e3fe`、`f3db688`、`e094879`、`41984fc`；各批修改已推送到 Gitea 與 GitHub 的 `codex/ticket-10`。固定基準 `f11473ba9bab60092ff61e695e7df1d592bb88a7` 的 Standards 與 Spec 最終複審均無未解決發現。
- 一般非快轉合併 commit：`4ba5c897a5762226bf43f337d63db396fd49d633`。合併後 `python3 scripts/run_tests.py` 為 144 項全通過。Gitea 與 GitHub 的 `B518-Log-Solution` ref 均已逐一核對為上述合併 SHA；兩端 `codex/ticket-10` 仍在 `41984fcc1b843a2730bc5a4a8a5220c43b19e7da`，清理尚待完成。
- 清理完成：後續驗收紀錄 commit `7e9890184ac033690ee412080a7874fb008364ba` 已推至兩端。`origin` 有 Gitea、GitHub 兩個 push URL；`git push origin --delete codex/ticket-10` 後，對 `github` 的重複刪除回報 ref 已不存在，並以 `git ls-remote` 確認兩端皆無 `codex/ticket-10`。本地分支以 `git branch -d` 安全刪除，已確認失效的 `github/codex/ticket-10` 追蹤引用亦已清除。最後停在乾淨的 `B518-Log-Solution`，目前 HEAD 為 `7e9890184ac033690ee412080a7874fb008364ba`。
