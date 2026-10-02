# Log Solution 專案摘要｜2026-10-02

## 前次討論與結果

依 2026-10-01 專案摘要及本次對話中的使用者決策整理。

- Ticket 06 已合併至 `B518-Log-Solution`，合併 commit 為 `1977bca94d34f6f2955dc1e4ec438964514d036b`；前次紀錄為完整 114 項測試及 Atlas／B482 受控 App 回放通過，Gitea 與 GitHub 同步、專用分支清理完成。
- 使用者接受本機受控 Atlas App 回放作為 Ticket 06 AC 6 的驗收證據；此決策不得自動延伸至其他 Ticket。
- Ticket 03 未完成驗收保持未勾選；Ticket 18 的未知同輪來源人工採用政策仍待決定。實機與發布 App 驗證不得以受控回放冒充。

## 本次執行進度

- 使用者明確要求實際完成 Ticket 07；已核對適用文件與 Ticket 06 前置程式，確認基準 `0fd33075223a88cce2d76585d38d57d9a8e1407d` 已包含所需 profile schema、Adapter、共同輪次入口與開始時快照。
- 從 `B518-Log-Solution` 建立並切換至 `codex/ticket-07`。既有未追蹤摘要由先前同日對話建立，保留並在本次列入專案紀錄，不混入程式提交。
- 已實作 profile JSON 匯出／匯入、工程師配置草稿、載入既有配置、欄位驗證、套用／取消、部署重新載入及保存／匯入失敗保留；更新 Atlas 受控 App 流程。
- Ticket 07 分批提交包括：`bbba326`、`d94100f`、`f7e5c87`、`f9f7463`、`6a8786f`、`fdcee0f`、`034324c`、`0572c38`、`6e53f69`、`c19320b`。
- 單檔已通過 `test_machine_profiles` 13 tests、`test_log_solution_ui` 34 tests；完整 `python3 scripts/run_tests.py` 為 125 tests 通過。Atlas Tk App 受控部署至結果回放重跑通過（DFU PASS、FCT PASS）；B482 受控共同輪次回放通過。
- Ticket 03 仍是 `in-progress`，實機／發布 App 驗收未勾選；使用者對 Ticket 06 受控 Atlas 回放的接受僅適用 Ticket 06。Ticket 18 政策仍未決。
- Ticket 07 的 5 項驗收已由配置錯誤矩陣、隔離部署測試與 Atlas Tk App 受控回放支持並勾選；目標設備、正式發布 App、產線 KVM／上位機尚未執行並明確保留為未驗收範圍。完整測試套件已通過，固定基準 `0fd33075223a88cce2d76585d38d57d9a8e1407d` 的 Standards／Spec 複審均無未解決問題。
- Ticket 07 以一般非快轉合併完成，merge commit `f060ba19721f25a179ab6c203cbca2b041abaf55`；合併後完整套件 125 tests 通過。SHA 已推送並逐一核對 Gitea 與 GitHub 的 `B518-Log-Solution`，兩端一致；兩端遠端 `codex/ticket-07` 及本地專用分支均已安全刪除，最後 checkout 為乾淨的 `B518-Log-Solution`。
- 型別檢查未配置，沒有宣稱型別檢查通過。

## Ticket 08 執行紀錄

- 使用者要求實作 Ticket 08，基準為 `bc880b3aad8542d038f4a50189a992e4f6a5ad01`，工作分支 `codex/ticket-08`。已讀適用領域／架構文件及 Tickets 01、04～08 的最新交付狀態；Ticket 05 現場即時時機、Ticket 03 驗收、Ticket 18 未知來源政策均維持原狀，沒有把前票回放當成本票豁免。
- 使用者確認上位機共同整合排在 Ticket 16。repo 中 `B518 ATE MVP Demo/upper_computer_simulator.py` 是固定 1～4 槽 Arduino TCP 模擬器，不能作 KVM 上位機驗收。
- Ticket 08 實作 Atlas parser 位置能力 1～20、B482／RS-WMT 1～4 的 profile 相容驗證；共同輪次入口套用來源到顯示位置映射。主畫面按容量在 1～10 顯示一排十格、11～20 顯示兩排十格，容量外黑色，二十筆明細獨立捲動；開始輪次固定配置快照。
- 受控 Tk Atlas App 從開始、容量／映射更新隔離至最終 PASS 顯示通過；容量 4／6／10／12／20 實際 Atlas parser 受控檔案經 `ConfiguredMonitor` 與 `RoundCoordinator` 驗證。登入桌面 1440×900、Tk scaling 1.0；容量10視窗376×643、容量11／20視窗376×670；另測 Tk scaling 1.5 無裁切。唯讀匿名化基準回放 Atlas DFU/FCT各PASS、B482 4個NOTEST與CaseInfo 4個TESTING、RS-WMT 4個PASS，工具輸出無序號且原樣本樹未修改。
- 完整 `python3 scripts/run_tests.py`：130 tests 通過；單檔及 UI 目標測試分批通過。專案未配置 mypy、pyright 等型別檢查。
- `$code-review` 固定基準 Standards／Spec 初審發現容量≤10時仍顯示第二排；已按容量隱藏位置11～20、調整色帶與視窗高度，並增加10／11切換測試。README舊七格敘述已更新。兩軸複審無未解決發現。
- Ticket 08 實際驗收、能力證據、命令及限制記在 `docs/refactoring/tickets/08-capacity-mapping-kvm-layout.md`；本票實機KVM／上位機共同驗收、目標設備與發布App未宣稱通過，分別依Ticket16／設備驗收工作追蹤。
- 實作與交付文件首批提交 `cae6337afb50d6102ff6e90d141aa574d9ac5d2e` 已推到 Gitea 及 GitHub 的 `codex/ticket-08`，兩端遠端 ref 均已核對為該 SHA，tracking 設為 `origin/codex/ticket-08`。
- 合併 commit、合併後測試與推送、各遠端專用分支清理及最後 checkout 結果，待本次 Git 流程結束後補記。
