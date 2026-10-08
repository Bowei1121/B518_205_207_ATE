# M1 本機驗收紀錄

日期：2026-10-08（Asia/Taipei）
票證：多語言 M1／GitHub #14  ︎
固定 Standards／Spec 基準：`dd81e4dcef781ef4c29a3310a2650827e45d0609`
最後程式／測試提交：`44826d44576bf579df1eba4c461468802e8a1ef3`（`fix: attach language menu to its Tk button`）
最初程式提交：`0a346544fa65a4dd31f6c3194d61a04514e2d6e8`
實作分支：`Multilingual/ticket-01`（已合併及安全刪除）
目前交付主線：`B518-Log-Solution`
實際合併 SHA：`83d8a68018ef4d6f78f0f68ff7f6f93caf2df8ce`

## 實作契約

- `src/language_catalog.py` 集中 English／繁體中文資源、穩定訊息 ID、具名參數、缺少繁中項目的英文回退與資源完整性檢查；提供 `translate`、`language_name` 及語言支援檢查。共用術語沿用 `CONTEXT.md` 的 Test Round、Awaiting Review、Station Type、Original Result、New Candidate、Source Time、Source Filename 對應，不改機器狀態碼。
- 全域語言沿用 `MachineProfileStore` 的本機 preferences JSON 欄位 `language`，不綁 profile、不新增 schema。無檔／舊檔缺欄位時為 `en`；受支援值由公開 `language` 與 `save_language` 讀寫。設定保存及匯入沿用同一可靠原子寫入與偏好保留行為，匯出仍只輸出可攜配置。
- 主頁右上選單顯示 English ▾／繁體中文 ▾，原生語言名稱以原生 radio menu 顯示選取勾號。程式提供滑鼠及 Space／Return／Down 開啟、選取和 Escape 取消入口；已由使用者在 `44826d4` 實際視窗確認滑鼠切換，以及 Tab／Space／方向鍵／Enter 選取和 Escape 取消、焦點返回。
- 切換只更新既有主頁 widget 與目前文案，不重建監控、不重新綁回呼、不重讀來源、不清除產品結果／候選／警報，不碰 Tk 外的 worker。KVM 標記、色帶、PASS／FAIL 等機器狀態碼及輪次磁碟資料維持原契約。
- 未知已保存語言回退 English，`MachineProfileStore.language_error` 提供診斷，App 透過可理解警告呈現且不把它轉成阻擋啟動的 `profile_error`。當次語言寫入失敗時允許當前畫面使用所選語言，顯示保存失敗對話框；store 與磁碟仍保留舊有效值，重啟不會假稱記住失敗的新值。
- M1 僅翻譯主監控頁及其主頁保存／輪次摘要文字。設定、衝突、警報與其他自有視窗，以及 App／平台事件雙語落盤、歷史事件重翻譯、bundle／現場發布仍屬 M2～M10；本次不宣告全 App 多語言完成。

## 六項驗收

| 驗收 | 結果與證據 |
| --- | --- |
| 1. 語言按鈕、原生選項及當前勾選 | **通過。** 真 Tk 測試核對按鈕目前語言與展開箭頭、選項恰為 English／繁體中文、radio 語言變數與當前選擇；確認入口在選取列右側且位於 KVM 標題上方，沒有壓住 KVM 內容。 |
| 2. 滑鼠／鍵盤展開、選取、取消與重選 | **通過。** 已修正窄版面及 menu 歸屬產品缺陷。使用者在 `44826d4` 新視窗確認滑鼠可以展開並立即切換；隔離操作紀錄亦記錄 mouse_open、英文／繁中雙向切換及新偏好讀取器的磁碟值一致。使用者另確認 Tab／Space／方向鍵／Enter 選取，以及 Escape 取消後語言不變、焦點返回皆正常；重選不變業務狀態由原真 Tk 回歸覆蓋。`Menu.invoke()` 不代替人員輸入證據。 |
| 3. 預設、持久化與偏好相容 | **通過。** 無偏好檔及舊檔缺欄位單元測試確認預設 English；真 Tk 以 Chinese／English 實際選單切換，再用全新 `MachineProfileStore` 和全新 App 從暫存磁碟讀回。配置保存、匯入、匯出與保存天數保留由 `test_profile_save_and_import_keep_global_language_but_export_only_profiles`、`test_language_replace_failure_preserves_effective_setting_and_preferences_file` 及相關偏好測試驗證。未知語言真 Tk 測試確認 English、可理解警告及正常 profile 使用；寫入故障真 Tk 驗證錯誤訊息與磁碟舊值。 |
| 4. 集中資源、穩定 ID、參數、回退與術語 | **通過。** `test_language_catalog` 驗證具名參數、缺少繁中單項回退英文、支援語言資源鍵／參數完整，以及 CONTEXT 核准的七個中英術語；流程使用 round ID／狀態，不以翻譯字串判斷。 |
| 5. 監控中即時更新與 KVM／結果保護 | **通過。** 真 Tk 使用暫存 `sample-json` 來源從 RUNNING 切換，再進入 AWAITING_REVIEW 後切換；確認 round ID、候選身分、結果列及 audit／Session bytes 在第一次切換前後一致。切換前後以實際 widget 座標檢查語言入口不遮住 KVM。 |
| 6. App／磁碟／未知值／失敗與舊路徑相容 | **通過。** 真 Tk 驗證持久讀寫、全新 App 重啟、未知語言警告、原子寫入失敗；磁碟配置與既有 audit／Session 對照未因切換改寫。最後程式版本完整套件 299 tests 通過；第 2 項的人員滑鼠與鍵盤操作證據已補足。未遷移視窗仍使用原行為，不據此宣稱全 App 翻譯完成。 |

## 實際命令與結果

從 Python 程式目錄 `B518 Log Solution/` 執行：

```text
python3 scripts/run_tests.py test_language_catalog test_machine_profiles
B518_TK_TESTS=1 python3 scripts/run_tests.py test_log_solution_ui.LogSolutionUiTests.test_real_tk_language_menu_switches_main_page_and_persists_across_app_instances
B518_TK_TESTS=1 python3 scripts/run_tests.py test_log_solution_ui.LogSolutionUiTests.test_real_tk_unknown_saved_language_uses_english_and_shows_diagnostic
B518_TK_TESTS=1 python3 scripts/run_tests.py
python3 -m compileall -q src tests
git diff --check
```

原提交版本最後完整含 Tk 套件在可存取桌面圖形工作階段執行，**297 tests 通過，64.846 秒**；compileall 及 diff whitespace 檢查通過。第一次未提升的 Tk 嘗試在建立視窗前因執行環境中止（exit 134），其後使用已授權桌面工作階段重跑。後續雙軸審查發現操作證據缺口；嘗試以 Tk 合成事件與 Quartz HID／指定程序事件補測，聚焦測試未能證明選單項目實際啟用，Quartz 點擊亦未送達 Tk 控制項。這些補測未納入提交；原 297 tests 結果仍對應下列提交，但第 2 項保持待驗，不能據原套件結果推論已通過該操作驗收。

審查後聚焦輸入補測命令：

```text
PYTHONPATH=src B518_TK_TESTS=1 python3 -m unittest tests.test_log_solution_ui.LogSolutionUiTests.test_real_tk_language_menu_switches_main_page_and_persists_across_app_instances
```

Tk 合成 Button／Motion／Return 事件未能在 macOS Cocoa 原生選單上完成選取；測試進程在選取斷言失敗。Quartz `CGEventPost` 與 `CGEventPostToPid` 的實際點擊探測亦未使 Tk 控制項收到事件。已授權桌面工作階段能建立及運行 Tk 測試，但本次工作階段未提供可用的 OS 級輸入注入，因此不將滑鼠／鍵盤選取驗收判定通過。這些失敗補測不改寫原提交 297 tests 的結果，也不構成產品缺陷結論。

測試先以 `test_machine_profiles` 建立「預設英文／磁碟重讀」反例，再實作全域公開讀寫；翻譯 API 與英文回退測試先因資源／API 缺少而失敗，再加入集中資源後通過。真 Tk 測試使用實際 App 與 widget，偏好亦從暫存磁碟重讀；目前原生選單項目選取透過 Tk `Menu.invoke()` 驗證，尚未以 OS 級滑鼠／鍵盤事件完成驗收。

專案未找到 mypy、pyright 或其他既有型別檢查設定；未宣稱型別檢查已通過，也沒有為 M1 新增型別檢查工程。

## 使用者實際操作發現的窄 HMI 缺陷與修正

2026-10-08 使用者在實際開啟的主頁確認語言按鈕無法點擊／看見。新增真 Tk 測試 `test_real_tk_language_and_profile_controls_fit_fixed_hmi_width` 重現：376 像素固定 HMI 下，英文按鈕實際寬度 5 像素、完整需求 72；繁中實際 73、需求 79。原先只檢查按鈕位置的測試沒有辨識裁切，不能把這項實際產品缺陷視為桌面權限問題。

將專案及機型選擇排為兩列，語言按鈕在右上保留完整空間。視窗寬度仍為 376，高度增加 26 像素容納第二列；KVM 區內黑白標記及色帶的相對座標維持，沒有宣稱其螢幕絕對 Y 座標不變。新測試在英文／繁中分別確認控制項已映射、完整需求寬度、位於主視窗內，按鈕中央可命中正確 widget，且位於 KVM 區上方。

實際 red-green 命令：

```text
B518_TK_TESTS=1 python3 scripts/run_tests.py test_log_solution_ui.LogSolutionUiTests.test_real_tk_language_and_profile_controls_fit_fixed_hmi_width
```

修正前失敗 2 個語言 subtest；修正後連同語言切換及 20 通道 KVM 幾何聚焦測試，3 tests 通過（3.302 秒）。首次完整套件另外指出舊固定高度斷言及一個鍵盤焦點依賴失敗；高度預期依新增 26 像素更新，快捷鍵測試獨立重跑通過（1.316 秒）並明確取得實際接收視窗焦點，之後完整 298 tests 通過（64.631 秒）。版面修正提交為 `006eebc`。

固定基準複審再找到既有通道列文字沒有即時切換的缺漏：英文改繁中仍顯示 `Slot 1`。真 Tk 新文字斷言先失敗（1.956 秒），再於主頁語言刷新中逐列更新現有 label，維持結果與輪次，不重建監控。測試同時覆蓋英文 → 繁中及繁中 → 英文的可見文字。聚焦 2 tests 通過（2.959 秒）；完整套件曾遇到既有 `test_close_stays_open_when_a_detached_round_fails_disk_verification` 的暫存目錄清理競爭（298 tests，65.241 秒，1 error）。該案例獨立連跑 3 次通過（1.008 秒），未修改保存／封存生命週期，隨後完整 298 tests 通過（66.178 秒）。通道列修正提交為 `2381556`。

修正版桌面已使用隔離暫存偏好與輪次目錄重新開啟，並保存人員選單操作與磁碟語言核對紀錄。原生選單的實際滑鼠及鍵盤操作仍待使用者確認；新增可見區域／命中測試及 `Menu.invoke()` 不取代第 2 項完整操作驗收，未合併或刪除專用分支。

## 按鈕可見但無法展開的 Tk 選單歸屬缺陷

使用者對修正版的最新回報為「可以完整顯示，但不能點開」，覆蓋先前表單回答的「可以顯示並展開」；目前僅確認按鈕可見，不宣稱人員已成功展開、選取或取消。

檢查本機 Tk 8.6 實際 `::tk::MbPost` 實作，滑鼠路徑要求 menu 為 menubutton 的後代，否則回報 `TK MENUBUTTON POST_NONCHILD`。App 原將語言 menu 建於 root，造成此確定的產品缺陷。新真 Tk 測試透過可見按鈕的 Enter／ButtonPress／ButtonRelease 事件操作，修正前捕捉到 `can't post .!menu: it isn't a descendant of .!frame.!frame2.!menubutton`（1.070 秒），未呼叫 `Menu.invoke()` 或私有 App 開啟 helper。

改為先建立語言按鈕，再將 menu 建於該按鈕底下並關聯。修正後滑鼠開啟測試、固定 HMI 寬度與語言／轮次切換 3 tests 通過（5.035 秒）。滑鼠測試觀察 Tk 真正執行 menu postcommand 並檢查沒有背景錯誤、沒有新輪次或語言變更；此補充證據不能代替人員實際的選取／鍵盤導覽驗收。

```text
B518_TK_TESTS=1 python3 scripts/run_tests.py test_log_solution_ui.LogSolutionUiTests.test_real_tk_language_button_mouse_click_posts_menu_without_tk_error
```

最後程式版本 `44826d44576bf579df1eba4c461468802e8a1ef3` 的完整含 Tk 套件通過 **299 tests（75.866 秒）**，`compileall` 與 `git diff --check` 通過。已重新開啟明確標示 `44826d4` 的最新驗收視窗，隔離目錄為 `/var/folders/gk/zpblb4q57bl24pt55p1m933h0000gn/T/B518-M1-menu-fixed-r0z2zgfg`；`manual-validation.jsonl` 記錄實際輸入、可見文字及全新偏好讀取器的磁碟語言。啟動時英文按鈕 actual／required 均為 72 像素，通道列顯示 Slot 1～6，尚無輪次。紀錄存在不等於人員操作已通過，仍以實際回報與記錄內容確認。

人員隨後確認「可以展開並立即切換」。16:59:32～16:59:54 的紀錄顯示實際 mouse_open、英文／繁中雙向選取、可見 Slot／通道文字更新，以及新 `MachineProfileStore` 重读的磁碟語言一致。`language_selection` trace 在 Tk grid 下一次排版前可能保留前一語言的瞬時 width；下一次真實 mouse_open 時繁中 actual／required 均為 79、英文均為 72。重複 trace 是觀察器收到 StringVar 寫入通知，不代表重複輪次或操作事件；全程 round_id 為 null。鍵盤部分另請使用者實際驗證，尚未當作通過。

## 審查結果、提交與界線

- 程式／翻譯資源提交：`0a346544fa65a4dd31f6c3194d61a04514e2d6e8`。
- 未知設定真正 Tk 回歸測試提交：`3a613f9`。
- 窄 HMI 修正：`006eebc`；通道列切換修正：`2381556`；滑鼠 menu 歸屬修正：`44826d4`。
- 本紀錄最後程式／測試證據對應 `44826d44576bf579df1eba4c461468802e8a1ef3`；固定審查基準維持 `dd81e4dcef781ef4c29a3310a2650827e45d0609`，未隨 HEAD 推進。複審程式缺陷及人員输入證據缺口已解除；合併與同步結果另記於交付節。
- M2～M10 的視窗翻譯、雙語事件保存、歷史事件、App 事件期限與清理、完整 bundle 發布不在本票通過範圍。未執行 OS 全域快捷鍵實機、正式 bundle 或美國現場設備驗收。
- 遠端 GitHub Issue #14 與母規格 #13 未修改。

## Standards

對固定基準至 `44826d4` 的平行複審無文件規範或 ADR 違反。保留兩項非阻擋的 Duplicated Code 維護觀察：主頁 review／alarm／monitor-state 推導重複，以及 `save_language`／`save_retention_days` 的偏好讀取、驗證與原子寫入重複。這些是判斷性建議，不是硬規則。

## Spec

既有通道列未換語言的 P2 問題已修正，Tk menu 歸屬修正亦處理確認的滑鼠開啟錯誤。未發現額外程式缺陷或範圍擴張。第 2／6 項的人員實際滑鼠與鍵盤證據現已補足，最後 Spec 唯讀複核確認已解除必要阻擋。

審查統計：Standards 0 項硬違反、2 項非阻擋維護觀察；Spec 先前程式缺陷已修正，人員輸入驗收缺口現已補足，最後 Spec 複核確認沒有剩餘必要阻擋。

## 最後人員輸入確認

使用者在標題含 `44826d4` 的同一真 Tk 視窗先確認「可以展開並立即切換」，其後對「Tab 將焦點移到語言按鈕 → Space 開啟 → 方向鍵選取 → Enter 切換；再開啟 → Escape 取消，語言不變且焦點回到按鈕」回答「全部正常」。這是人員實際操作結果，解除先前唯一必要輸入驗收缺口。

[操作紀錄快照](manual-validation.jsonl) 保存該視窗的 mouse_open、雙向語言切換、可見 Slot／通道文字、新偏好讀取器磁碟值及部分 Tab／Down 按鍵。Cocoa 原生 menu 不會將全部鍵送回觀察器；Space／Enter／Escape、焦點返回的完整操作以使用者明確確認為證，不宣稱 journal 捕捉全部鍵。快照只記錄隔離暫存資料及無輪次操作。前述「待驗」段落記錄較早查核結果，本節及六項表格為最新狀態。

最後 Spec 複核使用同一固定基準 `dd81e4d...44826d4`，核對操作紀錄及人員明確確認後回報：先前唯一驗收缺口已解除，沒有剩餘必要阻擋；本輪唯讀審查沒有程式變更。

## 主線交付與分支清理

- 驗收文件提交 `f2504e7` 已先推送票分支的 Gitea／GitHub。合併前 fetch 及兩端 `ls-remote` 確認主線皆為固定基準 `dd81e4d`，沒有新增提交；工作樹乾淨。
- 使用 `git merge --no-ff Multilingual/ticket-01`，實際合併 SHA 為 `83d8a68018ef4d6f78f0f68ff7f6f93caf2df8ce`；程式／測試最後 SHA 仍為 `44826d44576bf579df1eba4c461468802e8a1ef3`，文件提交不改產品。
- 在主線 Python 程式目錄，以已授權桌面工作階段執行 `B518_TK_TESTS=1 python3 scripts/run_tests.py`：**299 tests，108.078 秒，OK**。`python3 -m compileall -q src tests` 及 `git diff --check` 通過；無既有型別檢查設定，未宣稱型別檢查通過。
- `git push origin B518-Log-Solution` 推送兩個既有 push URL。逐一直接 `git ls-remote <URL> refs/heads/B518-Log-Solution` 確認 Gitea `http://10.64.76.34:3000/8362/B518-205_207_ATE.git`、GitHub `git@github.com:Bowei1121/B518_205_207_ATE.git` 均為上述合併 SHA 後，才安全清理票分支。
- 本地 `git branch -d Multilingual/ticket-01` 成功，兩端 `git push origin --delete Multilingual/ticket-01` 成功。再次直接查詢兩端票分支皆無 ref，本地 `git branch --list Multilingual/ticket-01` 亦無結果；未強制推送或強制刪除。
- 本節是合併後純文件更新，最終文件提交可由 `git log -1 --format=%H -- docs/refactoring/evidence/multilingual-ticket-01/local-validation.md` 查證；避免將文件自身 SHA 寫入自身造成循環。文件推送後再次直接查核兩端主線 SHA。
- M1 六項驗收通過，必要 Spec 問題已解除，Standards 無硬違反；沒有 M1 剩餘阻擋。M2～M10 尚未由本票交付，未修改任何遠端議題；正式 bundle／OS 全域快捷鍵／現場設備驗收仍屬後續範圍。
