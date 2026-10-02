# 09：統一通道期限與正常完成規則

**類型：**新增／行為變更

**What to build／工作內容與交付結果：**輪次管理共同開始等待、個別測試上限、正常停止收集與人工停止，操作員可完成未放滿的一輪。

**Blocked by／前置依賴：**

- [06：以專案＋機型選擇配置並啟動一輪](06-project-machine-profile-selection.md)

**Status：**completed（本票七項驗收、受控 Tk 回放、完整測試與固定基準 Standards／Spec 複審均通過；合併、兩目的地同步及分支清理完成）

## 驗收條件

- [x] 所有有效位置從接受開始的同一時刻計算等待，不因來源準備、第一個活動或新進度重設。
- [x] 等待到期僅無活動／結果的位置為 NOTEST，已有活動或結果不被重設，推定原因有紀錄。
- [x] 首個可信活動起算個別上限；TESTING 與 COMPLETING 到期為 TIMEOUT，其他位置繼續。
- [x] 僅 final 匯出資料不捏造 Testing，依配置等待並接受正確結果。
- [x] 無待確認且結果齊全立即停止收集並可取用，不增加完成後三秒觀察，後續檔案不改本輪。
- [x] 人工停止保留終態，其他位置 STOPPED，不補成 NOTEST 或正常完成。
- [x] 資料到達與期限同次推進的先後明確且可重現，不受 thread 或檔案排序偶然決定。

## 驗證方式

模擬時鐘驗證全空、部分活動、收尾逾時、final-only、邊界與停止後新檔，補 App 操作。

**規格驗收對照：**AC-10～AC-12、AC-15、AC-21

## 保留決策、待確認事項與限制

採用 01 確認後的測試接口；推定 NOTEST 與平台明確 NOTEST 必須可區分。不加入停止後觀察期。

沿用 Ticket 01 已確認的公開接口：建立輪次、注入單調時鐘、呼叫 RoundCoordinator.poll_once()，再從公開 RoundSnapshot 與事件檢查狀態、原因、期限及可取用性。未知同輪來源能否人工採用仍由 Ticket 18 決定，本票沒有擴張該政策。

本票明確將一次公開推進定義為：先取推進開始時的單調時間；若此刻已到期限，先套用期限並停止讀取該批來源；否則讀取完整來源批次，再依批次證據更新狀態。恰好到期視為期限到達，期限前開始的批次則整批先於期限判定，因此同批多來源結果不依檔案或執行緒排序決勝。平台檔案穩定等待仍由 Adapter 管理。

Ticket 03 的實機／發布驗收及 Ticket 05 的 RS-WMT 實機即時時機仍未通過；Ticket 06～08 的受控回放沒有被當作本票豁免。Ticket 16 上位機共同整合及 Ticket 17 發布／目標設備驗收不屬本票。這些外部範圍未宣稱完成；本票以隔離受控資料與實際 Tk App 流程驗證本票行為。

整輪期限到達仍維持待確認且不可取用；B482 候選覆核不能代替 Ticket 11 的整輪逾時警報確認與放行。Ticket 09 只保護既有整輪上限接口，不擴張其完整政策。

## 執行與追蹤

依使用者於 2026-10-02 的完整 Ticket 09 指令執行，開始基準固定為 9950cabb1d01d9b022065ba9ef065a6b9527938a，分支為 codex/ticket-09。基準已含本票所需的共同輪次入口、profile 三種期限與開始時容量／映射快照；Ticket 03／05 的實機驗收仍保持未完成，不因本票受控驗收而變更。

### 實際交付與驗收紀錄

- src/monitoring_round.py 現為共同期限與輪次生命週期唯一擁有者。接受開始請求時固定單調時鐘 t0，非同步準備來源；開始等待、個別 TESTING／COMPLETING 上限與整輪上限均由共同輪次推進。結果全為終態後立即停止收集；有既有覆核待決時轉為不可取用的待確認狀態。人工停止保留終態，未完成位置為 STOPPED。
- BaseMonitor 僅保留來源解析與狀態容器，不再負責共同期限或結果齊全後延遲完成。Atlas Adapter 不再以來源消失三秒推定 NOTEST。期限推定 NOTEST 記錄原因、期限、經過時間及本輪接受開始時間；平台明確 NOTEST 維持其 Adapter 證據語意，逾時終態鎖定以防遲到資料覆寫。`RoundMonitor` 明確列出輪次所需的公開 Adapter 契約；輪次不再直接讀取 Adapter 的結果字典、期限欄位、session 或覆核私有狀態。`ConfiguredMonitor` 對映雙向各建一次索引，並透過相同契約轉送輪次操作。
- 明確推進順序：每次 poll_once() 以推進開始時間判斷期限；到期（包含恰好相等）先裁決期限、不讀來源；尚未到期則先完整讀取該批資料，再進入下一次期限判斷。這使批次內多來源結果不受檔名、掃描或執行緒排序左右，並保留 Adapter 的檔案穩定等待。
- 7 項驗收如上均已勾選。測試涵蓋全空／部分活動／部分終態、準備期間跨過期限、開始 t0 不重設、TESTING 與 COMPLETING 個別逾時、終態鎖定、RS-WMT final-only、到期前／恰好到期、人工停止混合狀態、停止後遲到結果及舊輪事件隔離；Atlas／B482／RS-WMT 透過共同入口回歸。
- 實際 Tk App 隔離回放命令：python3 'B518 Log Solution/tools/smoke_deadline_app.py'。App 由同一視窗驗證 Atlas 未放滿 [PASS, NOTEST]、全空 [NOTEST, NOTEST]、個別逾時加人工停止 [TIMEOUT, STOPPED]，以及 RS-WMT final-only [PASS, NOTEST, NOTEST, NOTEST]。Tk 視窗 376x596，scaling 1.0；回放偏好、profile、來源與輸出均在臨時目錄，序號為合成資料。
- 專案完整測試命令：python3 scripts/run_tests.py，134 tests 通過。相關單檔命令：python3 scripts/run_tests.py test_monitoring_round test_configured_monitor test_atlas_source_adapter test_b482_source_adapter test_rswmt_monitoring test_log_monitoring，61 tests 通過；Tk UI 單檔 36 tests 通過。專案沒有 mypy、pyright 或其他型別檢查設定；未以 compileall 代替型別檢查。
- 原始實機資料保持唯讀；本次未做實機即時時機、目標設備、正式發布 App 或上位機共同驗收，依指示沒有宣稱通過。Ticket 16／17 與 Ticket 18 的分工及未決政策維持不變。
- 審查基準固定為 9950cabb1d01d9b022065ba9ef065a6b9527938a。初審發現重複 import／重複 session 設定，已移除並通過輪次單檔測試；Spec 初審發現所有位置終態時仍有 B482 候選覆核會因停止輪詢而無法釋放，已將覆核決策接到共同輪次公開接口，直接消化已捕捉候選而不讀新檔，並新增兩位置真 Adapter 公開流程回歸測試。複審另發現候選覆核不得解除整輪期限的待確認狀態；已以明確完成原因保持結果不可取用並加回歸測試。另將公開輪詢時間留在共同輪次，避免修改 Adapter 私有欄位。Standards 複審指出輪次與 Adapter 欄位耦合及重複反向映射；已新增 `RoundMonitor` 公開契約、單一雙向位置索引，並補公開介面測試。來源準備失敗事件亦修正為不依賴尚未建立的 Adapter。固定基準 Standards／Spec 最後複審（9950cabb1d01d9b022065ba9ef065a6b9527938a…94e299bb12ea74fcd0e8a0d9ad474686e11c1c06）均無未解決發現；完整套件 134 tests 通過。
- Ticket 09 實作提交：`807e0ce`、`46f61b6`、`3031c30`、`48baadc`、`94e299b`；驗收與審查紀錄提交 `5f51aee`。一般非快轉合併 commit 為 `1b4b8d1e8867f00c6c7a584a063182a7967d3270`；合併後完整測試再次通過（134 tests）。合併分支已推送並核對 Gitea、GitHub 兩端相同；兩端 `codex/ticket-09` 均已刪除，本地使用 `git branch -d` 安全刪除，並移除已確認失效的 `origin/codex/ticket-09` 追蹤引用。最後停在乾淨的 `B518-Log-Solution`。最終交付紀錄提交及推送狀態由本次 Git 結果核對。
