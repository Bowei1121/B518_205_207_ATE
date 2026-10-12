# M10 source App 整合驗收（2026-10-12）

使用者於10/12明確授權：M10尚未驗收項先以source App完成，全部source驗收及審查通過後可合併至 B518-Log-Solution。**正式bundle、目標OS／HMI及實機KVM仍待驗，不再阻擋本次source合併；不宣稱M10正式發布驗收全部完成或可部署。** 原10/09紀錄的bundle合併門檻已由本次授權變更，歷史結果保存於 [10/09紀錄](local-validation-2026-10-09.md)。

## 固定基準與依賴

M10固定review baseline：`95b791c2cf1a54b10db4f07cbc606ddd06db8280`。本次最後程式／測試SHA：`079b5191598b39182ef6e7acd3269c3cc3d703a9`；前一修正批次：`4b6efd7442da7bc3039832a77ca0707dfe5d2efe`。合併SHA及最後遠端查詢另記於交付摘要，與程式測試SHA分開。

实际Git根目錄為本專案工作樹，Python目錄為內層 `B518 Log Solution/`。M5 `cfb3548`、M6 `daba482`、M7 `35fb3ab`、M8 `dd4306f`、M9 `d891dd1` 及M4 `f7e24cd`均經 `git merge-base --is-ancestor <sha> B518-Log-Solution` 實際查得exit0；對應程式與驗收／固定基準審查紀錄在工作基準，並在本次全套重新執行。沒有前票必要產品驗收阻擋。M1～M9同期遠端收尾不混入產品修正。

既存10/09及10/12專案摘要修改、未追蹤架構讨论均屬其他工作，保護且不納入本票提交。本票每日結果另存 PROJECT_SUMMARY_2026-10-12_M10.md，避免覆蓋並行討論。

## 六項验收（source門檻與發布界線分開）

|#|結果|實際證據|
|---|---|---|
|1|source通過|322/322資源鍵、參數、術語及關鍵文案完整；`validate_translations()==()`、`test_language_catalog`。逐鍵清單見resource-coverage.md，沒有新增語言或改固定雙語紀錄。|
|2|source通過|全可達handler／狀態／producer盤點見source-coverage.md。新真Tk notice覆蓋配置驗證、來源建立、語言保存及Session目錄錯誤；其他初始化／熱鍵提示共用同一notice與翻譯資源，既有相應producer測試重新執行。原診斷與OS文字例外明示。|
|3|source通過|新真實sample-json經公開準備、實際Coordinator及App，同開設定／衝突／警報／App診斷／歷史五窗；逐窗中英title與可見內容、RUNNING及待確認連續切換、草稿／候選保留、其他位置繼續收集、關閉停用、取消恢復、單次裁決及確認、實際destroy。|
|4|source通過；設備待驗|最小／窄HMI source Tk、長英文及路徑、拖曳／捲動、實際差異字型／顏色、KVM geometry／色帶／黑白標記回歸。沒有宣稱現場HMI或實機上位機已驗。|
|5|source通過；案例16發布部分待驗|下表16組逐項source證據在最後整合版本重跑；Atlas DFU/FCT、B482 BT、RS-WMT BT、sample-json真實來源及人工決定行為沿用M3／M6案例。雙語不改產品放行、未知來源FAIL或事件身分。|
|6|正式發布待驗|source可載入全部資源且322鍵驗證通過；正式bundle收錄／啟動／目標OS／設備仍未驗，不用source或合成verifier測試代替。依本次source門檻不阻擋合併。接續見release-validation.md。|

## 本次新增／修正與 red-green

- `test_visible_start_validation_notice_refreshes_without_accepting_a_round`：舊原生messagebox被呼叫而red；自有可見Tk notice、grab及英文／繁中實際內容green；未接受輪次。後續red重現中文原診斷混入英文外層，改為本語言說明＋獨立原始診斷。
- `test_visible_source_failure_notice_and_fixed_bilingual_audit`：舊原生提示red；實際App來源建立注入PermissionError，可見提示換語且原round_id不變；新audit讀取器同筆固定兩語與原診斷green。
- `test_visible_language_write_error_refresh_keeps_original_preferences`：原子replace故障，畫面新語言但未持久保存提示可見；同視窗刷新；原偏好bytes不變；修復後完整關閉，新App reader只有一筆失敗紀錄。
- `test_language_refresh_preserves_event_log_reading_position`：red實際重現事件頁跳底、文字選取消失及診斷list/detail跳頂；green保留位置／選取。公開App新增事件後診斷刷新暴露localized紀錄丟失，已保留原雙語表示，未改磁碟事件。
- `test_real_source_all_windows_switch_cancel_and_single_decisions`：red暴露正式開始多一筆固定中文UI行；移除與canonical round_started重複的display-only行。實際來源與五窗長流程、audits/App磁碟bytes及單次操作重建green。
- `test_session_directory_failure_is_visible_and_persisted`：實際Open Session按鈕mkdir失敗原先只Tk callback error而red；mkdir納入既有OSError處理，可見本語言notice與原診斷、新讀取器完整事件green。

另將原snapshot稽核／保存失敗與看板focus失敗的display-only文案改用明確雙語ID，保持原保存責任與診斷。沒有新增排程／schema／裁決／關閉生命週期；未改未知來源、來源時間與機器狀態。

語言整合測試使用Menu.invoke驅動換語，不單獨宣稱原生滑鼠／鍵盤導覽。M1真正按鈕／鍵盤案例與已確認操作證據另行引用；M5原生選檔使用者已確認的兩語選取／取消／拒絕覆寫證據不冒充本次自動OS輸入。

## 母規格16組 source 对照

所有下列suite案例在本次整合版本實際重跑；前票舊數字不作本次結果。

|#|情境|本次测试入口與證據|界線|
|---|---|---|---|
|1|首次英文／偏好／配置互不抹除／故障|test_machine_profiles、language_menu跨App、new language_write_error|新store磁碟重讀，source|
|2|選單／滑鼠／鍵盤／取消／重選|M1真Tk language_menu、fixed_hmi_width；既有使用者操作確認|Menu.invoke不冒充原生輸入|
|3|RUNNING／AWAITING_REVIEW|new real_source_all_windows及M2/M3/M6來源與人工操作|不改結果／候選／警報|
|4|全部自有視窗刷新與狀態保留|new五窗長流程、reading_position、visible notices；既有三窗detail、M5/M6/M7完整視窗案例|關閉視窗依M7停用語言|
|5|關閉語言gate／取消／重試|new五窗closecancel；close_waits_responsively、close_failure_retry等|實際destroy＋磁碟完整|
|6|選檔例外／取消／覆寫／路徑|M5file_dialog_buttons、import_export、已確認使用者實際原生操作|系統文字依OS|
|7|本語言錯誤／原診斷／回退|new四項可見notice、M4diagnostics、catalog/historical fallback|原文不猜譯|
|8|全部資源／參數／術語|test_language_catalog、322/322逐鍵清單|缺項安全性不代替交付完整|
|9|同筆固定雙語／磁碟不回寫|new五窗bytes對照、M2/M3/M4/M8新讀取器|偏好正常保存不算事件回寫|
|10|故障／部分寫入／有序補存／無輪次|test_app_event_store、test_log_monitoring、test_monitoring_round、真Tk retry／close|不以flush/pending代替完整|
|11|新舊歷史／可靠匹配／原文|test_historical_event_display、real_tk_historical_reader及新五窗|唯讀來源bytes保持|
|12|App原時間／保護／輪次封存時間|test_app_event_retention、test_round_retention|無mtime猜測|
|13|期限修改／清理競爭／故障摘要|test_round_retention、真Tkapp_event_cleanup_failure與retry|既有排程、隔離刪除|
|14|兩語Tk／長文／主要彈窗／KVM|new notice及reading；M1/M5/M6/M7版面、test_kvm_display_contract|實機HMI／KVM另待驗|
|15|各平台相同來源／人工決定|M3四平台真Tk矩陣、test_log_monitoring及M6真实衝突／新五窗|不同輪自然ID／時間可不同|
|16|資源／完整回歸／發布|source catalog載入及完整套件；test_verify_macos_bundle僅工具邊界|正式bundle／目標環境待驗|

## 命令、結果與審查

Python子目錄，登入desktop圖形工作階段執行（沙盒外已授權）。Python版本由本次suite runtime使用既有python3，不改build政策。

```zsh
B518_TK_TESTS=1 PYTHONPATH=src python3 -m unittest discover -s tests -p test_m10_integration.py
B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py
python3 -m compileall -q src tests
git diff --check
PYTHONPATH=src python3 -c 'import language_catalog as c; print(len(c.LANGUAGE_RESOURCES[c.ENGLISH]), len(c.LANGUAGE_RESOURCES[c.TRADITIONAL_CHINESE]), c.validate_translations())'
```

最後聚焦6 tests／8.024秒OK，兩項受影響舊測試另重跑0.719秒及1.102秒OK；compileall、diff-check通過；catalog `322 322 ()`。本次完整套件結果：**371 tests／114.119秒，OK**（最後079b519整合版本）。無既有mypy／pyright／型別檢查設定，未新增工程，不宣稱型別檢查通過。

固定基準95b791c2至079b519的Standards／Spec雙軸平行複審：兩軸皆無未解source問題。先前三項Spec問題及追加的選取／診斷閱讀問題已red-green修正，正式bundle待驗不誤標通過。文件更新後再次核對證據。最後成功全套log存 /private/tmp/m10-source-final-tests.log（暫存機器log，主要結論隨此提交）。

GitHub及公司Gitea本次可達；每批已push同名票分支。合併前／後最新直接SHA查詢、main完整重跑及安全清理另記交付摘要；不可把歷史query當最後HEAD。


第一次完整套件於a1ece06為371tests／120.172秒，3項失敗（兩項舊inline診斷文字預期、一項提示等待map時提早關閉）；079b519修正後全套重新執行才通過。未忽略失敗或以縮小套件取得成功。最終log /private/tmp/m10-source-final-tests.log。

合併前直接查詢兩目的地均得到main `95b791c2cf1a54b10db4f07cbc606ddd06db8280`、ticket `079b5191598b39182ef6e7acd3269c3cc3d703a9`；這是文件commit前的查詢，後續文檔與合併最後query另記，不宣稱為最後HEAD。


## 本機source合併與主線複驗（2026-10-12）

合併前兩目的地直接查得main95b791c2、票分支74019aec3b1e3df9ab83b92fb4c8cdd4e26bc438。確認目標工作樹沒有未提交變更後，以no-ff合併；實際merge SHA為`6c55fd24c8a8c4afc5da8b32edfb8a96a095e376`。合併未改最後079b519程式／測試內容，`git diff 079b519 HEAD -- 'B518 Log Solution/src' 'B518 Log Solution/tests'`為空。

主線由同一Python目錄執行完整命令，**371tests／111.476秒，OK**；compileall、diff-check及catalog322/322／零errors通過。完整source及main命令輸出分別提交於 [source-suite.txt](source-suite.txt)、[main-suite.txt](main-suite.txt)。兩軸code-review與證據複審無未解必要source問題。

既存兩份摘要修改及未追蹤架構討論先限定路徑stash／備份，再原樣還原並逐檔SHA256確認一致；沒有加入本票提交。這些既存修改使最終工作樹不是完全乾淨，但本票沒有未提交程式／測試或交付文件。實際遠端最後query及票分支清理結果由下一交付紀錄追加。
