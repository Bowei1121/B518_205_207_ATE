# 13：完成可追查的輪次紀錄

**類型：**新增／保護

**What to build／工作內容與交付結果：**維護工程師查閱一輪紀錄可重建配置、來源、結果變更、逾時、候選、人工選擇及收集停止／放行時間。

**Blocked by／前置依賴：**

- [11：整輪上限、一次警報與確認後放行](11-round-deadline-alarm-release.md)

**Status：**implemented（本機持久重建、Adapter 回歸及 Tk 受控回放完成；AC 4 的實際 KVM 驗證待驗）

## 驗收條件

- [x] 保留既有設定、事件、結果與來源紀錄，補齊配置版本及本輪快照；Session JSON／CSV 使用原子替換，新增版本化 `audit.jsonl`。
- [x] 可區分平台 NOTEST／等待推定 NOTEST，查到逾時原因與警報；來源未知時間／SN 不補造。
- [x] 原／新候選、來源證據、人工選擇及時間可追查；磁碟紀錄失敗會明確標示不完整，依使用者決定不阻止既有產品放行。
- [ ] 收集停止與結果放行有獨立事件與時刻；Tk 色帶、標記和放行來自同一 `RoundSnapshot`，但實際 KVM 取像／辨識尚未執行。使用者已批准暫緩實機類驗收，此項待實機補驗，不阻止本機交付及合併。
- [x] 正常、結果衝突與整輪逾時均由新讀取實例從磁碟重建，匿名化證據見 [`evidence/ticket-13`](../evidence/ticket-13/)。

## 驗證方式

產生正常及異常輪次後讀取持久紀錄，比對配置、來源、操作及可觀察狀態。

**規格驗收對照：**AC-27

## 保留決策、待確認事項與限制

各功能票本身先保留必要紀錄；本票整合完整可追查性。不新增原始 Log 備份、雲端或帳號系統；未知來源政策仍未決。

所有行為測試須依 01 的接口確認結果落實；本次批准任務清單不代表測試接口已獲批准。未知同輪來源能否人工採用仍由 18 決定，任何本票的已完成部分都不能抵銷該未決分支。

## 執行與追蹤

依 2026-09-30 使用者確認的任務清單建立。以 REFACTOR_SPEC、CONTEXT 與 ADR 0001～0005 為基準，沿用測試配置、平台資料來源、監控輪次、桌面介面四模組與 Python／Tk／既有 macOS 打包方式。只在前置完成且本票關鍵待決及外部條件已滿足時轉為 ready-for-agent；需要人類決策的任務不得逕自轉為可直接實作。

執行時逐項記錄實際交付、驗證環境與結果、仍未決／待驗範圍及相關提交。未執行的驗收維持未勾選；本文件建立不代表 App 已完成重構。

## Ticket 13 執行紀錄｜2026-10-05

### 前置判讀與決策

- 固定審查基準：`371d94b54c5d4061153ab9cac13de6d7c8c5248b`。從乾淨的 `B518-Log-Solution` 建立 `codex/ticket-13`。基準已實際包含 Ticket 06～12 的版本化配置快照、共同輪次／期限、衝突候選、整輪警報及 UI 狀態標記；本票未將 Ticket 12 AC 1、Ticket 03／05 未完成驗收或前票受控回放當成本票豁免。
- SessionStore 原先以覆寫方式更新 `session.json`／`results.csv`，共同輪次事件只在記憶體中，查閱按鈕可開啟單一 Session 資料夾。新增紀錄仍放在同一 Session 查閱入口。
- 使用者決定：稽核寫入因磁碟滿／權限錯誤失敗時，已符合既有條件的結果仍可取用，但 App 必須明確顯示稽核紀錄不完整。故障不另創產品放行阻擋。
- 上位機整合留在 Ticket 16；未知同輪來源採用政策留在 Ticket 18。使用者已批准將需要實際 KVM、治具、目標設備或發布 App 的驗收暫緩，維持未勾選；本機行為測試、Tk 回放、持久重建與 code-review 仍須完成。

### 實際交付

- 新增 `audit.jsonl` schema v1，保存輪次 ID、專案／機型／平台、配置版本及容量／映射／路徑／期限快照；事件包含單調經過時間、App 觀察時間、來源時間、操作時間、顯示／來源位置、來源識別及可取得的 SN／結果／日期／批次證據。round ID 僅供追查，不代表來源確屬同輪。
- 共同輪次事件依序列進入單一背景追加寫入佇列，不在 Tk 輪詢中重寫整份紀錄；`flush_audit()` 提供明確的磁碟讀取／Session handoff 邊界。寫入以單行追加、fsync 及失敗回退避免留下半行；讀取器拒絕截斷、損壞、不支援版本或序號缺口，並從新讀取的磁碟檔重建有效結果、候選、警報、停止及放行。
- 原 `session.json`／`results.csv` 改為鎖定下原子替換，保存失敗保留前一份完整檔案；既有 `events.log` 與 Session 查閱流程保留。正式 Tk App 將傳統 Session 更新與事件寫入背景佇列，避免輪詢阻塞畫面；直接建立的 monitor 維持同步預設。保存失敗向共同快照及 App 事件顯示稽核不完整；依已確認決策不改變結果可取用條件。
- 保存 Adapter handoff 前的期限／停止事實；Adapter 延遲返回後接續原輪次紀錄，不恢復已停止的讀取。衝突候選快照、逐項人工選擇及整輪警報建立／確認時間均可分別追查；final-only RS-WMT 不補造測試活動時間。
- 新增離線讀取工具 `tools/rebuild_round_audit.py`（預設完整重建；`--summary` 遮蔽配置與來源細節）及合成資料證據產生器 `tools/generate_ticket13_evidence.py`。匿名化案例為 normal／conflict／round-timeout，無真實序號或實機來源。
- README 增補 Session 查閱、時間欄位、紀錄版本、重建命令及保存失敗行為。未新增原始 Log 備份、雲端或帳號功能。

### 驗證、環境與限制

| 驗證 | 命令／環境 | 結果 |
| --- | --- | --- |
| 行為測試及 Adapter／共同輪次／Session 回歸 | `python3 scripts/run_tests.py test_audit_records test_monitoring_round test_log_monitoring test_atlas_source_adapter test_rswmt_monitoring test_configured_monitor`；macOS 15.7.9、Intel x86_64、Python 3.8.10 | 89 tests 通過。包含正常／衝突／整輪逾時的磁碟新實例重建、三種 Adapter、非恆等映射、來源準備跨期限、併發順序、損壞／結構不完整紀錄、原子保存及背景寫入故障仍允許既有產品放行。 |
| Tk UI 回歸 | `python3 scripts/run_tests.py test_log_solution_ui`；登入桌面 | 40 tests 通過，包含關閉時 Session → audit 有界 flush 順序及失敗提示。 |
| 完整測試套件 | `python3 scripts/run_tests.py`；macOS 桌面工作階段 | 179 tests 通過。沙箱 Tk 初始化會 abort，故桌面 UI 與全套測試需在桌面工作階段執行。 |
| 實際 Tk 受控輪次 | `python3 tools/smoke_audit_records_app.py`；隔離 HOME、偏好、Session、來源及輸出；合成匿名化 Atlas | 通過。視窗 `376x608+1052+32`；刻意延遲 Session 寫入時 Tk 仍可更新；關閉經正式 `app.close()` 且無保存失敗提示。共同輪次及磁碟重建皆為 PASS，結果已放行、稽核完整，Tk 狀態標記為 `complete`；稽核檔在既有 Session 目錄可查。 |
| 磁碟重建案例 | `python3 tools/generate_ticket13_evidence.py` | 三個匿名化完整紀錄案例均寫出；normal 6、conflict 9、round-timeout 10 個有序事件，皆重建為 `audit_complete=true`。 |
| 語法／差異檢查 | `python3 -m py_compile src/audit_records.py src/monitoring_round.py src/log_monitoring.py src/configured_monitor.py src/b518_log_solution.py tools/rebuild_round_audit.py tools/generate_ticket13_evidence.py tools/smoke_audit_records_app.py`；`git diff --check` | 通過；py_compile 僅語法檢查，不代表型別檢查。 |
| 型別檢查 | repo 設定盤點 | 沒有 pyproject、mypy、pyright、setup.cfg 或 tox 型別檢查配置；未宣稱型別檢查通過。 |

### 驗收界線與後續審查

- AC 1、2、3、5 由本機測試、離線重建及匿名化證據通過；AC 4 保持未勾選：本機已證明停止／放行分開記錄，Tk 標記使用同一共同快照，但實際 KVM 端取像及辨識尚未驗收。此實機待驗項依使用者明確批准暫緩，不阻止合併。
- Ticket 12 AC 1 仍未驗收；Ticket 16 上位機共同整合、Ticket 18 未知同輪政策，以及目標設備／發布 App 驗收均未以本票結果宣稱通過。
- 固定基準 `$code-review` Standards／Spec 初審及複審均完成，無未解決問題。審查修正包含事件值物件、損壞／缺欄位／無效 UTF-8 紀錄拒絕，以及 Tk App 專用的非阻塞 Session 背景寫入；新增對應回歸測試。非同步測試與受控回放於查閱／清理前明確 flush。
- 實作 commit `ff7a5e9`、審查修正 `1b5e4251957289b69f3d531e70b972d16af66955` 及分支交付紀錄 commit `5326cef23025e2e0bcb3dae977da792d231d7c8c` 均已納入本票歷史。一般非快轉合併 commit 為 `a1e712a3f2ffdfd2f4070b715223309255d4edb1`；合併後非阻塞 Session／關閉 flush 修正為 `2b241c8`、`53984d60ff273156e23ace3e824119d484dbc209`。最終同步 SHA `f020e490645902783bedea5a175e91d0b056bb6a` 在 Gitea 與 GitHub 的 `B518-Log-Solution`、`codex/ticket-13` 均已核對一致；之後已從兩端刪除 `codex/ticket-13`、prune 對應追蹤引用，並安全刪除本地分支。最終清理紀錄提交後會再推送並核對目標分支。
