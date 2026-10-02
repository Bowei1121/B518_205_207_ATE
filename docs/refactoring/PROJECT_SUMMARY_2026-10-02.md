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
- 驗收紀錄提交 `05d0272943e181337b48dcdcafa3ea0d6d98fc28` 亦已推至兩端專用分支。使用者要求的一般非快轉合併 commit 為 `3b024107f497836b0eeea780b30ae5627439ef53`；合併後完整套件再次 130 tests 通過，SHA 已推至 Gitea 與 GitHub 的 `B518-Log-Solution` 並逐一核對一致。
- 合併與驗收紀錄提交 `62a71285a9db66d5f03ecfdf66ae411bed69e594` 已推至 Gitea 與 GitHub，兩端 `B518-Log-Solution` ref 一致並包含 Ticket 08 merge commit。兩端 `codex/ticket-08` ref 均已確認不存在；本地專用分支使用 `git branch -d` 安全刪除，最後停在乾淨的 `B518-Log-Solution`。分支清理結果已寫入 Ticket 08 與本摘要。

## Ticket 09 執行紀錄

- 2026-10-02 開始 Ticket 09，固定基準 `9950cabb1d01d9b022065ba9ef065a6b9527938a`，工作分支 `codex/ticket-09`。確認共同輪次接口、三種版本化 profile 期限、Adapter 與容量／映射快照已在基準；Ticket 03 實機／發布驗收及 Ticket 05 RS-WMT 實機即時時機仍未完成，沒有把 Ticket 06～08 的回放當成本票豁免。Ticket 16 上位機共同整合及 Ticket 18 未知來源採用政策保持原決策。
- 共同期限與完成規則集中在 `MonitoringRound`。輪次接受開始時固定單調時鐘 t0，來源準備非同步，準備時間計入開始等待；到期僅尚未有可信活動／結果的位置成為帶有期限證據的推定 NOTEST。首次可信活動固定個別測試起點，TESTING／COMPLETING 可單獨 TIMEOUT 且終態不可被遲到資料覆寫。RS-WMT final-only 不捏造 TESTING；結果全終態即停止讀取，不加三秒觀察；人工停止保留終態並將其他位置標為 STOPPED。
- 一次公開推進以開始時單調時間決定順序：到期（包含恰好到期）先定期限且不讀取該批資料；未到期則先處理整個資料批次。相關決策已記入 Ticket 09 並有邊界測試。
- 初次雙軸複審發現重複 session 設定，以及 B482 待覆核候選在停止讀檔後無法消化的 Spec 缺口。已移除重複程式碼；新增共同輪次公開覆核入口，使用先前捕捉的候選且不讀新檔，並增加兩位置真實 B482 Adapter 公開流程測試。
- Spec 複審確認整輪期限上的候選覆核不得代替 Ticket 11 的警報確認與放行；共同輪次保留 round_deadline 待確認狀態，並新增回歸測試。另將 poll 時間保存在 MonitoringRound，移除跨物件私有時間戳突變。
- 相關單檔測試 61 項、Tk UI 單檔 36 項、修正後完整測試套件 134 項均通過。隔離實際 Tk App 回放通過 Atlas 未放滿、全空期限、個別逾時加人工停止與 RS-WMT final-only；視窗 376x596、Tk scaling 1.0。合成資料、偏好、配置及輸出均位於臨時目錄。原始實機資料唯讀，未宣稱實機即時、發布 App、目標設備或上位機驗收通過。
- Standards 複審提出 Adapter 欄位耦合及重複反向映射兩項設計氣味；已加入明確 `RoundMonitor` 公開契約與單一雙向位置索引。來源準備失敗路徑也改為直接記錄輪次事件，並以 Tk 回歸測試覆蓋非同步啟動時序。
- 專案沒有既有 mypy、pyright 或其他型別檢查設定。操作說明已更新，移除「全空整輪 TIMEOUT」及過期的等待描述。
- 固定基準 Standards／Spec 複審對完整實作差異均無未解決問題。專用分支提交 `807e0ce`、`46f61b6`、`3031c30`、`48baadc`、`94e299b` 及驗收文件提交 `5f51aee`。已對乾淨且與遠端同步的 `B518-Log-Solution` 建立非快轉合併 commit `1b4b8d1e8867f00c6c7a584a063182a7967d3270`；合併後完整 134 項測試通過。Gitea 與 GitHub 的 `B518-Log-Solution` ref 已逐一核對一致，兩端專用分支均刪除；本地分支安全刪除、失效追蹤引用清除，工作樹乾淨並停在 `B518-Log-Solution`。
