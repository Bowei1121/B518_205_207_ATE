# 多語言票號與依賴

來源：[正式規格](../MULTILINGUAL_SPEC_2026-10-07.md)，對應 [GitHub Issue #13](https://github.com/Bowei1121/B518_205_207_ATE/issues/13)。已核對遠端完整正文與本機一致，無留言。

狀態：使用者已確認十張拆票，M1～M10 已發布為 GitHub #14～#23。M1 六項驗收與審查已通過並合併至主線 `83d8a68`。M2 六項驗收、完整含 Tk 套件及固定基準 Standards／Spec 審查均已完成，程式／測試 SHA `1d036f0339c2d37ac7907e46c31f92708909ea38` 已推送；合併提交 `f128d9f963f60d416d0eaf5917fa5eda87408280` 已推送至 GitHub 的 `B518-Log-Solution` 並直接確認。完整證據見[本機驗收紀錄](../evidence/multilingual-ticket-02/local-validation.md)。內部 Gitea 將於週一同步；在直接確認同步前保留 `Multilingual/ticket-02` 分支。M3～M10 依下列範圍與依賴另行交付。Issue #13 僅作 Parent 參考；本次不修改遠端議題狀態。M1／M2 的本機證據不代表全 App 多語言完成。

M3 五項驗收已由完整 producer 清單（含共同加入的 `station` 參數）、B482／RS-WMT／Sample JSON producer 斷言、四平台真 Tk 正常／部分／讀取錯誤矩陣、雙語刷新與磁碟重建證據覆蓋；完整含 Tk 套件在測試 SHA `9d35db3` 通過 317 tests（88.328 秒），合併後於主線再次通過 317 tests（89.830 秒）。Sample JSON 五種警告均有 ID／參數／診斷斷言。固定基準 `c87c7bcefa334b96c420f255e8c1bf99e7a97370` 的最終 Standards／Spec 複審至 `99556a784a50e91262cb340ba89fcb8cfccd5555` 無未解規格缺口或硬性標準違反；Standards 留一項非阻擋重複錯誤追蹤氣味。GitHub 合併 SHA `fb4ffb2286d9c113511482b738a101a11616bd14` 與 M3 票分支 `c4f89723fe9bf0389b8df947c940eeeef2b2e537` 均已直接查證。公司 Gitea 依使用者指示週一同步；M2／M3 票分支在 Gitea 直接確認前保留。細節見 [M3 本機驗收紀錄](../evidence/multilingual-ticket-03/local-validation.md)。

M4 六項本機驗收及完整含 Tk 套件已通過：最終程式／測試提交 `be4f091` 的 `B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py` 通過 330 tests（92.409 秒），並通過 compileall 與 `git diff --check`。已建立無輪次 App 事件雙語持久格式、公開重試／狀態及正常關閉協調；真 Tk 覆蓋初始化、語言／配置／匯入匯出／熱鍵失敗、原始診斷、歷史錯誤復原、耐久性重試及完整關閉。固定基準 `648b0c2126aaa6ab29016f2f95deb24ca7c8145f` 的 Standards／Spec 複審至 `be4f091` 無未解問題。GitHub 合併提交 `f7e24cd265fc173d5d113e7fb122083602f5e5fa` 的合併後完整含 Tk 套件亦通過 330 tests（93.584 秒）；GitHub 主線直接查詢曾確認 `a14548e4afa93f1ca00cba3eb165cb1bf4eab7ff`，票分支 `e663e430d9fed1541bc0e4c20447d2f630c698de` 保留。最終文件更新推送及直接查證見 M4 [本機驗收紀錄](../evidence/multilingual-ticket-04/local-validation.md)。公司 Gitea 依使用者指示週一同步；Gitea 直接查證前保留 M4 本地與遠端票分支，不清理分支。

M5 六項驗收於 2026-10-09 補齊：使用者完成英文／繁中原生選資料夾、匯入、匯出、取消及拒絕覆寫；兩份匯出與原始配置相符，原檔雜湊不變，新的 App journal 讀取器驗證七筆同筆雙語及連續序號。完整含 Tk 套件與固定基準複審已通過；GitHub 合併 SHA `cfb35480d890abeb8a03bc74360260dcd8d739e1`，合併後完整含 Tk 套件通過 334 項（95.026 秒），固定基準至 `240d801` 的 Standards／Spec 複審沒有未解阻擋。主線推送後直接確認合併 SHA，最後文件提交另行查證；Gitea 週一直接確認前保留票分支。見 [M5 本機驗收](../evidence/multilingual-ticket-05/local-validation.md)。

M6 五項驗收於 2026-10-09 完成。衝突及整輪警報視窗沿用共用中英資源；語言刷新保留 conflict_id 選取、候選快照、閱讀位置及未確認警報。真正 Tk 驗證受控 Atlas 衝突、其他位置持續收集、KVM 標記、逐項裁決／警報確認及全新 audit 讀取器重建；空選取在正常排程刷新時清除舊比較與詳細內容並停用裁決。最終程式／測試提交 `da94db305547307b8a0370c9da9569f07f671986` 的完整含 Tk 套件通過 335 tests（83.317 秒），固定基準 `31a9bccd5cb1534f2d17b99ad6ed3b4f461ffdd4` 的 Standards／Spec 最終複審為零項可執行發現。GitHub 合併提交 `daba4822566f944e603d065b5319674f83c99311` 合併後完整含 Tk 套件通過 335 tests（85.007 秒）。完整證據見 [M6 本機驗收](../evidence/multilingual-ticket-06/local-validation.md)。公司 Gitea 週一同步直接確認前保留 M6 本地與 GitHub 票分支。

M7 五項程式驗收已由真正 Tk 等待／失敗／重試／取消／再次關閉操作驗證；關閉期間主語言按鈕與選單停用，直接及已排入 Tk 事件迴圈的切換請求均不改語言／增加事件，停用原因、儲存狀態及重試／取消按鈕依目前語言顯示，取消後語言入口恢復而保存與已停止來源狀態保留。完整含 Tk 套件最後重跑通過 335 tests（86.356 秒），真 Tk 包含已排程切換拒絕；先前一次執行出現既有封存案例暫存目錄清理競爭，該案例連續五次隔離重跑及後續完整套件均通過。compileall 與 diff check 通過。固定 M7 review baseline `45df1e36895cdb8bbb313de0a4c038cdeef13ac4` 的 Standards／Spec 複審無未解問題。測試／證據批次 `db1535259f64d68206b0a0badedf6d862dcedabf` 推送後直接查詢 GitHub 票分支即為該 SHA，主線為 `45df1e36895cdb8bbb313de0a4c038cdeef13ac4`；最終文件提交的 SHA 另於交付回報直接確認。Gitea 目前不可達；因此尚未合併或清理票分支。細節見 [M7 本機驗收紀錄](../evidence/multilingual-ticket-07/local-validation.md)。

| 本機票 | GitHub | 可驗證交付 | 直接阻擋 |
| --- | --- | --- | --- |
| [M1](01-main-language-menu.md) | [#14](https://github.com/Bowei1121/B518_205_207_ATE/issues/14) | 主頁直覺語言選單、英文／繁中即時切換、上次語言持久保存；[本機驗收](../evidence/multilingual-ticket-01/local-validation.md) | 無 |
| [M2](02-round-bilingual-events.md) | [#15](https://github.com/Bowei1121/B518_205_207_ATE/issues/15) | 共同輪次事件同筆雙語、切換畫面事件及磁碟重建 | #14（已由 M1 主線交付解除） |
| [M3](03-platform-event-migration.md) | [#16](https://github.com/Bowei1121/B518_205_207_ATE/issues/16) | 各已支援平台的來源／解析／錯誤事件都可雙語閱讀與保存 | #15（已由 M2 主線交付解除） |
| [M4](04-app-diagnostic-events.md) | [#17](https://github.com/Bowei1121/B518_205_207_ATE/issues/17) | 無輪次 App 事件雙語保存、可理解錯誤、原始診斷與故障補存；[M4 本機驗收](../evidence/multilingual-ticket-04/local-validation.md) | #15（M2 已納入 GitHub 主線，依賴解除） |
| [M5](05-settings-and-file-dialogs.md) | [#18](https://github.com/Bowei1121/B518_205_207_ATE/issues/18) | 工程師設定、配置與選檔流程換語言且不丟輸入 | #17（M4 已合併解除；M5 六項驗收已通過） |
| [M6](06-conflicts-and-alarms.md) | [#19](https://github.com/Bowei1121/B518_205_207_ATE/issues/19) | 衝突與警報同步翻譯，保留選取、快照與人工決定；[M6 本機驗收](../evidence/multilingual-ticket-06/local-validation.md) | #15（M2 已納入 GitHub 主線，依賴解除） |
| [M7](07-save-and-close-language.md) | [#20](https://github.com/Bowei1121/B518_205_207_ATE/issues/20) | 保存／重試／關閉提示一致，關閉保存停用切換、取消後恢復；五項程式驗收、完整含 Tk 測試與固定基準複審已通過，Gitea 同步待完成 | #17（M4 已合併至工作基準，已解除） |
| [M8](08-historical-event-display.md) | [#21](https://github.com/Bowei1121/B518_205_207_ATE/issues/21) | 新舊紀錄依語言閱讀，舊檔不改寫、無法辨識原文詳細保留 | #16、#17 |
| [M9](09-app-event-retention.md) | [#22](https://github.com/Bowei1121/B518_205_207_ATE/issues/22) | App 事件按原事件時間清理，待補存保護與清理摘要 | #17、既有 [#8](https://github.com/Bowei1121/B518_205_207_ATE/issues/8) |
| [M10](10-integrated-release-verification.md) | [#23](https://github.com/Bowei1121/B518_205_207_ATE/issues/23) | 全 App 翻譯覆蓋、跨視窗操作、KVM 與發布資源驗收完成 | #18、#19、#20、#21、#22 |

## 分割及相容策略

- M1 以主頁完整操作路徑建立集中翻譯、資源與語言設定入口，必要局部整理在此先做，不獨立發布僅一層的重構票。
- M2 相容擴充事件形式、先驗證共同輪次的完整路徑；M3／M4 按來源與 App 操作批次接入，不同時改掉全部呼叫者。舊 message 及機器欄位仍可讀，批次間保持既有回歸可驗證。
- M5／M6／M7 分別交付工程師設定、人工覆核與保存流程，皆包含資源、操作行為、雙語事件及真正 Tk 測試，不是純翻譯清單或 UI 元件票。
- M8 不依賴所有視窗都先翻譯，使用已具備的訊息及保存契約驗證歷史閱讀；M10 再驗證整體覆蓋。
- M9 明確擴充既有清理入口，需 #8 完成，不另起一套 background scheduler；已具備的全域保存天數與封存接口不重做。
- M10 包含發布資源收錄與跨路徑驗收交付，沒有必要的產品修正不能轉為僅測試通過宣告。正式 bundle／目標環境缺少證據時對應項保持待驗，不以 source App 代替。
- 不將衝突版面 #10～#12 一律列為硬阻擋：M6 對實作時已存在的自有衝突視窗翻譯。若其間新分區已合併，M6／M10 必須納入其全部文字與操作，不重做版面或放行政策。

M1（#14）六項必要驗收通過，程式版本 `44826d4`，合併提交 `83d8a68`；M1 已解除 M2 直接依賴。M2 六項驗收、固定基準 Standards／Spec 審查均已通過；最終程式／測試 SHA `1d036f0339c2d37ac7907e46c31f92708909ea38` 完整含 Tk 套件通過 303 tests（80.331 秒、0 跳過），合併至 `B518-Log-Solution` 的 SHA 為 `f128d9f963f60d416d0eaf5917fa5eda87408280`，合併後完整套件再通過 303 tests（80.964 秒、0 跳過）。GitHub 主線直接查詢與合併 SHA 一致。內部 Gitea 預定週一推送；同步確認前保留 `Multilingual/ticket-02` 分支。其他票依真正直接阻擋推進。所有票維持固定狀態碼、來源證據、人工裁決、結果放行、KVM 幾何、雙語同事件及舊檔不重寫；本機交付不變更遠端議題狀態。

2026-10-08 後續人員操作發現並修正窄 HMI 按鈕裁切、Tk menu 歸屬造成的滑鼠開啟失敗，以及通道列文字未即時切換。已補真正 Tk 回歸；使用者隨後確認滑鼠與鍵盤完整操作正常；主線合併驗證已完成，M1 的本機交付依賴已解除。M2 後續實作與驗收狀態記於本摘要的 M2 專節及其本機驗收紀錄，該前段描述保留為 M1 交付當時的歷史狀態。

## 規格驗收覆蓋

| 必要案例 | 負責票 |
| --- | --- |
| 1：首次語言、持久設定、配置互不抹除 | M1（主頁語言與偏好磁碟重讀已驗）、M5（設定視窗切換、配置操作與保存天數磁碟重讀已驗） |
| 2：直覺選單、鍵盤與取消 | M1（原生選單人員滑鼠切換、鍵盤導覽／選取／取消已驗） |
| 3：監控／待確認即時切換不改流程 | M1（主頁 RUNNING／AWAITING_REVIEW 狀態已驗）、M2、M6（雙語事件與其他自有視窗待驗） |
| 4：全視窗／既有事件刷新及保留狀態 | M2、M5（設定視窗即時刷新與草稿／選取／驗證狀態保留已驗）、M6、M7、M10 |
| 5：關閉保存停用及取消恢復 | M7（真 Tk 已驗：等待與失敗期間停用按鈕／選單及拒絕切換，理由本地化；取消後恢復且不重啟來源） |
| 6：原生選檔例外 | M5（App 標題／類型參數已驗；兩語原生選擇／取消／返回路徑及拒絕覆寫已由使用者操作並核對磁碟） |
| 7：錯誤雙語、診斷及回退 | M4、M6、M7（保存失敗外層訊息與原始診斷於真 Tk 驗證） |
| 8：翻譯完整性與關鍵提示 | M1（主頁資源鍵／參數與核准術語已驗）、M10（全 App 覆蓋待驗） |
| 9：同筆雙語與磁碟不重寫 | M2、M3、M4 |
| 10：有序保存、補存及無輪次事件 | M2、M4 |
| 11：歷史相容與原文保留 | M8 |
| 12：App 事件期限及保護 | M9 |
| 13：清理協調與摘要 | M9 |
| 14：真實版面及 KVM 契約 | M1（主頁選單／KVM 標記與色帶已驗）、M5（680×560 設定視窗英文版面已驗）、M6、M7（關閉進度視窗真 Tk 驗；完整多視窗／bundle 覆蓋仍待 M10）、M10 |
| 15：兩語業務結果一致 | M1（切換未改當輪結果與 audit／Session）、M2、M3、M6、M10（雙語事件及全 App 一致性待驗） |
| 16：發布資源、bundle 證據與全套回歸 | M10 |

44 項故事按操作路徑分配：主頁／設定 M1、M5；切換安全 M2、M5～M7；來源資料 M3；App 錯誤及雙語保存 M2、M4；歷史 M8；保存期限 M9；術語、未來語言及完整發布 M1、M10。

## 發布查核

2026-10-08 已逐票核對完整正文與本機一致、OPEN、ready-for-agent 及全部原生阻擋關係。M9（#22）另由既有 #8 阻擋；母規格 #13 的狀態及 updated_at 保持不變。
