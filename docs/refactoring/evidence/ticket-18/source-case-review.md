# Ticket 18：未知同輪來源案例與現況

日期：2026-10-06。固定起始 commit：`26a097e1dd7fc00c40bbb7d8472d946fdc920939`。本文件整理 repo 內可查證的程式、匿名化基準資料及隔離測試案例；測試建立於暫存目錄的案例標為受控合成，不當作現場資料或實機驗收。沒有新增產品規則，也沒有決定未知同輪來源能否人工採用。

## 分類界線

- **已確定同輪**：Adapter 提供可比對的 `round_evidence_id`，共同輪次可將候選與目前結果連結。Ticket 10 的人工覆核只適用於這種已連結的結果矛盾。
- **已確定不同輪**：有可靠的輪次／批次證據證明來源屬不同輪。此時不應把結果當成本輪衝突候選。既有平台各自的篩選行為只描述原平台，不構成 Ticket 18 的跨平台政策。
- **無法確認同輪**：沒有足夠的共同輪次連結，或來源內的身分／輪次線索彼此不足。保留可取得的來源證據，缺失欄位記為 `unknown`；不因 SN 缺失、SN 相同、檔案路徑相同或檔案修改時間相近而推定同輪。

來源測試時間只記錄 Adapter 實際解析到的時間。檔案時間、輪次觀察時間及事件寫入時間不是來源測試時間。

## 平台案例

| 平台與案例 | 輸入／來源識別 | 時間、SN、批次及輪次證據 | 目前可查證行為 |
| --- | --- | --- | --- |
| Atlas：活動來源身份改變 | `tests/test_atlas_source_adapter.py::test_atlas_active_identity_change_is_retained_as_unconfirmed_evidence` 在暫存 `group0-slot1/system/records.csv` 先後寫入兩個不同 SN；不是現場來源。 | 來源名稱與來源位置可見；原／候選 SN 可見；來源時間為 `unknown`；候選沒有可信輪次連結。程式原因為 `active_record_identity_changed_without_round_link`。 | Adapter 輸出未決觀察；共同輪次記錄 `unresolved_source_conflict`、保留目前 SN，不建立 `pending_conflicts` 人工覆核項目。 |
| Atlas：活動 SN 與歸檔結果連結 | `tests/test_atlas_source_adapter.py::test_atlas_same_active_slot_and_trusted_sn_capture_changed_final_as_common_conflict` 使用暫存 active／archive 檔。 | 活動位置與可信 SN 建立 `atlas:<slot>:<SN>`；歸檔資料夾名稱解析出的時間為來源時間。 | 同一證據 ID 下的改變結果進入 Ticket 10 共用衝突覆核；這是已確定同輪對照案例。 |
| B482：CaseInfo 對已完成 TestData 提供不同身分 | `tests/test_monitoring_round.py::test_terminal_bt_slot_retains_caseinfo_identity_as_unconfirmed_evidence` 在暫存目錄使用匿名格式檔名 `[Thread0]...[20261002100001].csv` 與 `thread1CaseInfo_2026-10-02.txt`。 | TestData 有來源位置、SN、狀態及檔名批次時間；CaseInfo 提供 thread、檔名日期與解析出的來源時間。兩者沒有可證明相同輪次的共同 ID；案例中的 `StartTime` 是 `x`／`y`，不能作時間依據。 | 保留原 PASS／SN，輸出未決事件，附候選 SN、CaseInfo 檔名與實際解析時間，不建立人工覆核項目。 |
| B482：具 Thread／Config／時間戳的 TestData | `tests/test_monitoring_round.py::test_each_same_slot_candidate_is_resolved_independently_in_user_selected_order` 為共同輪次隔離案例。匿名化 baseline 另含 B482 TestData 與 CaseInfo 樣本。 | 測試候選具有 `b482:<slot>:<timestamp>:thread=<n>;config=<id>` 證據。CaseInfo 自身不因此自動取得相同批次連結。 | 同一明確證據下的多個候選由 Ticket 10 分項處理。這不等於批准接受或拒絕所有 B482 未知批次來源。 |
| RS-WMT：來源 log 跨多個 Slot／SN 或缺少識別欄位 | `tests/test_monitoring_round.py::test_ambiguous_rswmt_log_retains_candidate_evidence_without_selecting_a_round` 以暫存 `ambiguous.log`、`unbound.log`、`partial-evidence.log` 驗證；內容是受控合成 log。 | `ambiguous.log` 有來源時間、Slot 1／2、兩個 SN 與批次候選時間，但不能選定唯一輪次；`unbound.log` 有 Slot 3、SN、來源時間而無批次候選；`partial-evidence.log` 有初始化及批次候選時間，缺 Slot／SN。 | 以 warning 保留各自可解析的來源、Slot、SN 與時間；沒有證據的欄位省略，不建立結果或待確認選擇，通道維持 WAITING。 |
| RS-WMT：有可識別測試開始時間的 final CSV／相同 run log | `tests/test_monitoring_round.py::test_rswmt_adapter_sends_confirmed_same_run_conflicting_final_to_shared_review` 及相鄰 final-only 測試使用暫存檔；匿名化 baseline 有四個 RS-WMT final CSV。 | 來源位置及解析的測試開始時間形成 `rswmt:<slot>:<test-start>` 證據；來源時間與 batch evidence 分別記錄。 | 證據相同的矛盾進入共用衝突流程；若來源開始時間不同，既有 Adapter 依其來源規則處理，不能推廣為 Ticket 18 的通用拒絕政策。 |

## 跨平台共同輪次目前行為

程式依據：`B518 Log Solution/src/monitoring_round.py` 的 `_consider_result_candidate`、`_finish_if_terminal` 與 `snapshot`。

- 當位置尚無結果或仍為 WAITING 時，候選目前直接 `accept`，不要求 `round_evidence_id`。例如 `tests/test_platform_registry.py::test_final_only_sample_reaches_shared_round_without_invented_activity` 明確確認沒有來源時間及輪次 ID 的 final 仍成為 PASS 並可取用。這是**現況描述**，不是 Ticket 18 對首次結果的政策決定。
- 目前結果與新來源矛盾時，只有兩邊都有相同、非空 `round_evidence_id` 才建立 Ticket 10 的人工覆核項目；否則輸出 `unresolved_source_conflict` 並忽略候選更新。
- `unresolved_source_conflict` 本身不新增 `pending_conflicts`，也不轉換輪次狀態。完成／放行檢查目前依終態結果、警報與 `pending_conflicts` 判定。因此未知來源矛盾目前可能留下稽核事件、保留原結果，卻不成為放行阻擋。這是需由政策決定涵蓋的行為影響，尚未以任何選項宣告正確。
- 已知不同輪的來源被 Adapter 篩選與否，依平台既有識別證據而異；B482 與 RS-WMT 的歷史批次規則不代表產品通則。

## 決策前完成狀態與證據限制

- 已逐項整理三平台 repo 內的未知／模糊來源輸入型態、來源識別、實際解析時間、SN／Slot／批次／輪次證據與目前結果；未知欄位未補造。
- 本次未知案例主要是程式測試中的隔離合成輸入。repo 內匿名化 baseline 用於平台對照，但不等於有涵蓋未知同輪人工採用的現場原始案例。沒有新增原始資料或聲稱實機驗收。
- 決策待確認：能否人工採用、最低證據條件、首次結果與替換既有結果是否共用政策、證據不足／拒絕／未選擇時的狀態、是否阻擋放行，以及稽核欄位與操作限制。
- 決策前沒有新增程式行為測試、改變採用政策或把 Ticket 18 標為 ready／complete。Ticket 01／02 公開接口只用來定位後續可觀察邊界；Ticket 10 行為只作已確定同輪對照。
