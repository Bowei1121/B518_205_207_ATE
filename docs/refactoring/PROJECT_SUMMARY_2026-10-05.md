# 專案摘要（2026-10-05）

承接 [2026-10-03 摘要](PROJECT_SUMMARY_2026-10-03.md) 與本對話可查證的交付結果。

- Ticket 10 已完成共同衝突候選、逐項保留／採用、非模態 Tk 操作與放行隔離；五項受控驗收通過，完整測試及合併後測試均為 144 項通過，固定基準 Standards／Spec 複審無未解決發現。
- Ticket 10 一般非快轉 merge SHA：`4ba5c897a5762226bf43f337d63db396fd49d633`。最後交付紀錄 SHA：`d253b02edaa75d93809ecf246c38574def8b49c8`。前次已逐端確認 Gitea／GitHub 同步，以及專用分支與已失效追蹤引用清理；本次讀取本地 Git，分支仍為 `B518-Log-Solution`、HEAD `d253b02`，新增本摘要前工作樹乾淨。本次未重新核對遠端狀態。
- Ticket 03 既有實機／發布驗收、Ticket 05 即時實機資料時機，以及實際治具／KVM、目標設備、發布 App 等未執行項保持未驗收。前票受控回放不得自動豁免後票驗收。
- 使用者先前明確決定上位機共同整合留在 Ticket 16；Ticket 18 仍決定未知是否同輪來源的人工採用政策。
- 2026-10-05 使用者要求以 `$implement` 完整執行 Ticket 11，含 `codex/ticket-11` 提交、全部 push 目的地同步、符合條件後一般非快轉合併及安全清理流程。依此開始實作並建立專用分支。
- Ticket 11 五項驗收聚焦整輪共同起点不可重設、到期立即停止收集並保留終態／裁決未完成位置、一次警報、警報與衝突獨立確認，以及候選保留至所有必要確認後放行。需保護 Ticket 09 期限及人工停止語意、Ticket 10 多候選選擇與證據契約；不新增人工確認倒數，亦不擴張 Ticket 12／16／17／18。

## Ticket 11 執行紀錄｜2026-10-05

- 以 `d253b02edaa75d93809ecf246c38574def8b49c8` 為固定基準，從遠端同步的 `B518-Log-Solution` 建立 `codex/ticket-11`；啟動時工作樹只有本摘要未追蹤，沒有既有程式修改。Gitea 及 GitHub 均沒有同名專用分支。首個實作 commit `3eacb26299fe02f5cb8151e4e36cb8bf0f1ca6ee` 已推送兩個目的地並設定 tracking。
- 核對基準包含 Ticket 07 配置快照／保存接口、Ticket 09 的共同 t0／期限／停止收集及 Ticket 10 的候選佇列／逐項人工選擇；Ticket 03／05 的待驗不視為豁免。沿用使用者決定，上位機整合留在 Ticket 16；未知是否同輪來源的採用政策留在 Ticket 18。
- 工程選擇：到期裁決沿用 Ticket 09 的推進次序（輪詢開始時先裁決已到期期限，到期則不讀新來源）；只在尚有未完成位置時建立整輪警報。所有位置在期限前已有終態而僅待處理候選時，收集依既有全終態規則停止，不啟動警報或確認倒數。警報及收集停止、確認與放行分別以共同輪次事件記錄。
- 新增警報快照及 RoundCoordinator 公開確認操作；確認識別輪次與警報，重複／過期操作會留下忽略事件。警報及 Ticket 10 衝突維持獨立阻擋，所有位置終態且無任何待確認後才一次放行。Tk 警報採非阻塞視窗，關閉只隱藏，主畫面按鈕可重開；新輪不沿用舊視窗操作識別。
- TDD 紅綠測試從 Ticket 01 已確認的配置啟動輪次、注入單調時鐘、使用公開 `poll_once()`、快照／事件及確認接口；未測私有 timeout 方法。加入來源準備期間跨過期限、一次警報／重複與過期確認、終態保留／未開始 NOTEST／TESTING 和 COMPLETING TIMEOUT、警報與候選雙阻擋、停止收集後無確認倒數等案例。
- 固定基準雙軸審查另找到準備期期限輪詢中斷、Tk 準備期畫面不同步、延遲裁決期間確認競態、handoff 事件漏存及事件回呼鎖順序／stop-poll-coordinator 互鎖。已修正：延遲裁決與確認共用鎖、統一通道裁決、同步 monitor handoff 與 deferred event queue、Tk 依同一快照更新明細／色帶、adapter callback 在狀態鎖外執行、stop 在釋放狀態鎖及 coordinator lock 後呼叫 adapter／round。屏障測試、舊輪 UI 回歸與實際 Tk 回放通過；固定基準 Standards 與 Spec 最終複審均 PASS。
- 真實 Tk App 受控回放使用隔離的臨時偏好、設定、來源與輸出路徑及合成 Atlas／RS-WMT 資料；未讀取或修改原始實機資料。回放實測阻塞 Adapter 設定交接時，警報與 NOTEST 色帶／明細仍同步可見、確認按鈕停用、交接返回後 Adapter 未啟動；並以實際 Tk 按鈕驗證「警報先確認」及「衝突先選擇」兩流程均在所有待確認完成後才放行。主畫面 376x596、scaling 約 1.0、警報視窗 460x220；Session 驗證共同起點及 alarm → collection stop → acknowledgement → result release 順序。實際治具／目標裝置、發布 App 及 Ticket 16 上位機驗收仍未執行。
- 開發環境為 macOS 15.7.9、Intel x86_64、Python 3.8.10。`python3 scripts/run_tests.py test_monitoring_round` 32 tests、`python3 scripts/run_tests.py test_log_solution_ui` 37 tests，完整 `python3 scripts/run_tests.py` 154 tests 全部通過。Ticket 11 真 Tk 受控回放 `python3 -u tools/smoke_deadline_app.py` 通過，含 Adapter 設定 handoff 阻塞時期限畫面、兩種警報／衝突操作順序及人工停止流程。沙盒內 macOS Tk 初始化會 abort，UI 與全套測試在桌面環境執行。Repo 沒有 mypy、pyright 或其他型別檢查設定；`py_compile` 只作語法檢查，未宣稱型別檢查通過。
- Ticket 11 實作 commit `3eacb26299fe02f5cb8151e4e36cb8bf0f1ca6ee`、期限準備修正 `76c8798d48f0e75e8e7b5095ee19f42da7d467d0`、最後程式／測試／執行紀錄 commit `c1f308c6aa5978b8d66a0e53a6707ed9b6aa070d` 已推送到 Gitea 與 GitHub；兩端均核對專用 ref 為 c1f308c。一般非快轉合併 commit `fb3d653771723294224598c5d348ac667effd7d2` 已推至 Gitea 與 GitHub，合併後完整測試再通過 154 項。合併後驗收與清理紀錄 commit `7bd55e2150001d4eef02160e0645e0910cfe4dc7` 也已同步至兩端；兩端 base ref 均為 7bd55e，Ticket 11 遠端分支 ref 已移除，本地分支以安全刪除，兩個已確認失效的遠端追蹤引用也已移除。實機治具時機、目標裝置／發布 App、KVM 與上位機共同驗收未執行；沒有用本機受控回放替代其驗收。上位機整合沿用使用者決策留在 Ticket 16。

## Ticket 12 執行紀錄｜2026-10-05

- 從 `B518-Log-Solution` 以固定基準 `b21a5b65b7e2fc049afba53e39bfaef8ce57cda5` 建立 `codex/ticket-12`。實作 commit `cbd17a08b8d0e57be25bbad63b3bfb86a8693433`、審查修正 `0e1cd4c03bdf44c1c384193ed79f0f934c9653fa`、驗收紀錄 `487e4c9e61ff816d3162ffa547ea76037a6e80a6`、PNG 證據 `d07d8393eaa59b77cae74e65117c3781ca605d31` 及本摘要補充均推送 Gitea／GitHub。兩端 `codex/ticket-12` refs 已核對一致為 d07d839，base 仍為 b21a5b6。Ticket 08 新十格／兩排和 Ticket 11 同一輪次快照／獨立警報阻擋已在基準內。
- Ticket 12 版本化 KVM 顯示契約 1.0 定義四種 2×2 pattern、Tk logical geometry、兩個非對稱定位點、色帶間距與樣本黑白門檻。App 從同一 `RoundSnapshot` 在同一 UI 更新中繪製色帶與 marker；新輪快照不沿用上一輪完成圖樣。五項 Ticket 驗收均在本機 Tk 範圍有測試／回放證據；實際 KVM、目標設備及發布 App 未驗收，不能以本機截圖豁免。
- 使用者補充的 `B518_JetKVM_Log` 僅作唯讀工程參考：該 README 說明 JetKVM 上位機 prototype 與本機 Log 專案獨立；原始 BGR frame 尺寸可供 Ticket 16 設計實際像素量測。沒有複製程式或歷史畫面，歷史圖片不算目前 KVM 證據。
- Ticket 12 隔離 Tk 回放 `python3 -u tools/smoke_state_marker_app.py` 已通過；Quartz 擷取視窗 752×1420 physical pixels，Tk app 376×682 logical units，畫面 1440×900 Tk units，scaling 1.0。驗證 standby、monitoring、衝突與警報同時待確認、完成、20 筆明細捲動、新輪切換、人工停止，且衝突／警報窗口未遮住頂部定位區。資料只含合成匿名化 SN，臨時 HOME／偏好／輸出在回放結束後清理。
- 固定基準 Standards／Spec 審查及複審均無未解發現。兩項 P3 維護性意見（快照參數型別、共享格距）與一項完成狀態優先級規格問題已修正並有測試；複審確認方向拒判及文件狀態順序清楚。
- `python3 scripts/run_tests.py test_kvm_display_contract` 通過 7 項，完整 `python3 scripts/run_tests.py` 通過 161 項；`py_compile` 僅語法檢查通過。repo 無型別檢查工具設定，未宣稱型別檢查通過。實際 KVM 傳輸、縮放、壓縮與目標／發布設備尚未驗收。
- Ticket 12 AC 2～5 本機 Tk 範圍通過。AC 1 保持未勾選：雖已定義與測試本機 Tk 邏輯幾何及合成 locators／marker samples，但目前無可用的實際 KVM frame，仍缺物理方向、畫面座標／scale／壓縮及 KVM 調校容差證據。使用者於 2026-10-05 明確決定所有實機類測試可先略過並接受本票先合併；因此 AC 1 是已記錄的後續待驗項，不代表通過。Ticket 16 上位機共同整合仍按先前分工處理，不以本機畫面替代。
- 固定基準雙軸 code-review 已最終通過；2026-10-05 使用者補充允許略過實機類驗收並合併，AC 1 保持未勾選。一般非快轉 merge commit `7bfe62b1f74abfd536919dfda1f42cb226a0afbf` 已在 `B518-Log-Solution` 建立；合併後完整測試 161 項通過。Gitea 與 GitHub 的 `B518-Log-Solution` 均已同步至 `cfcd3facbc4433a2bb4be44df3e147e01ac14395`；兩端 `codex/ticket-12` refs 均查無，local feature branch 及已確認失效的 `origin/codex/ticket-12` tracking ref 已清除。本地最後留在 `B518-Log-Solution`，工作樹清潔；最終分支／工作樹檢查待此摘要提交後再記錄於回覆。
