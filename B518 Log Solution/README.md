# B518 Log Solution

獨立的 macOS 本機 Log 監控程式，供 DFU、FCT、BT 顯示測試結果。它不含 Arduino、USB CDC、TCP、OpenCV、螢幕截圖、鍵盤／滑鼠或 KVM 控制；與 Atlas Agent 是不同的 App 與程序。

## 使用方式

```zsh
cd "B518 Log Solution"
python3 src/b518_log_solution.py
```

## 建置安裝包

舊測試機使用的 Intel macOS 10.14／10.15 安裝包，請在 Intel Catalina 10.15 執行 `./scripts/build_macos10_14_log_solution.sh`。

M4／macOS 26.5.2 建置給美國 M4／macOS 15.4.1 使用時（最低目標為 15.0，涵蓋 15.x），先在建置機安裝 [Python.org 3.12.10 universal2](https://www.python.org/downloads/release/python-31210/)，再執行 `./scripts/build_macos15_arm64_log_solution.sh`。預設 Python 路徑為 `/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12`；必要時可用 `PYTHON_BIN=/完整路徑/python3.12` 指定。產物為 `dist-macos15_0-arm64/B518-Log-Solution-V版本號-macOS15.0-arm64.zip`。腳本會檢查內含執行檔的 arm64 架構、最低 macOS 版本及外部函式庫依賴；檢查失敗時不會產生 ZIP。產物仍需在目標 M4／15.4.1 實機驗證，並在支援 15.0 的硬體驗證最低版本，目標機不需另外安裝 Python。

`./scripts/build_macos26_arm64_log_solution.sh` 仍供 macOS 26.x 測試機使用，最低系統版本為 26.0，產物不能在 15.0 啟動。所有建置腳本均會執行測試、遞增 `VERSION`、以 ad-hoc 簽章打包並輸出 SHA-256。

### M4／15.0 候選產物驗證

Python.org 3.12.10 universal2 是本流程的初始建置環境，並非最新 Python 3.12。腳本使用獨立的 `.venv-macos15_0-arm64-log-solution`，保留其他舊環境；每次都檢查指定 Python 及虛擬環境中的實際 Python 版本、原生 arm64 與 Tk。若既有目標環境檢查失敗，先將該環境重新命名保留，再重跑建置。PyInstaller 維持 `6.16.0`。

```zsh
cd "B518 Log Solution"
./scripts/build_macos15_arm64_log_solution.sh
open "dist-macos15_0-arm64/B518 Log Solution.app"
```

建置須在登入桌面的 M4 上執行，完整核心、UI 與建置檢查測試任一失敗都會中止。建置後先在 26.5.2 確認 App 視窗正常開啟，再將 ZIP 與 SHA-256 檔交給目標機測試人員。

`scripts/verify_macos_bundle.py` 只讀取二進位資訊，不修改版本標記；檢查 `Info.plist`、每個 Mach-O 的 arm64 slice 及 macOS 載入指令，依 `@loader_path`、`@executable_path`、`LC_RPATH` 核對依賴的實際路徑。外部／損壞連結、找不到的依賴及無法判讀的版本都會阻止 ZIP 輸出。保守靜態檢查不保證所有執行階段動態載入與系統 API 都相容；deployment target 不會降低預編譯函式庫的需求，參見 [PyInstaller macOS 說明](https://www.pyinstaller.org/en/stable/usage.html#making-macos-apps-forward-compatible)。

目標 M4／macOS 15.4.1 不另外安裝 Python 或 Homebrew，解壓縮後逐項驗收並記錄版本號與結果：

- App 可啟動；設定儲存後重開仍保留。
- 背景狀態按 `Command + Shift + M` 可開始監控。
- 若有可持續讀取的即時 BT Log，在最終 CSV 產生前顯示 Testing 與正確條碼；只有完成後匯出的檔案時，依結果檔驗收。
- 最終結果解析後視窗回到前景，PASS／FAIL／NOTEST 正確。
- 各 Slot 的測試逾時與等待開始逾時顯示正確。

2026-09-29 開發端驗證使用 Intel／macOS 15.7.9，尚未在 M4／26.5.2 打包或 M4／15.4.1 與最低系統版本的實機驗收；上述兩階段仍須在對應電腦完成。

每輪必須由人員按下「開始監控」建立系統時間基準與啟動前快照。

若必要路徑尚未設定、已不存在或無法讀取，程式會拒絕開始並顯示原因；空白路徑不會被誤當成 App 的目前目錄。建立啟動前檔案快照期間，主畫面會先顯示「啟動中」，完成後才進入「監控中」。

工程師在「設定 → 工程師配置」編輯版本化配置草稿；驗證後按「套用並保存」才更新有效配置，取消或保存失敗會保留原配置。配置包含平台、容量、來源映射、路徑及期限，保存於 `~/Library/Application Support/B518LogSolution/preferences.json`。操作員在主畫面只選專案與 DFU／FCT／BT 機型；重新啟動會恢復有效選擇，舊偏好透過明確遷移轉成配置。每輪開始時固定配置快照，運行中更新只供後續輪次使用。

## 逾時監控

工程師配置中的「開始等待」、「測試上限」與「整輪上限」均以正整數秒保存。舊偏好遷移保留 DFU `30 / 480`、FCT `30 / 480`、BT `30 / 240` 的預設開始／測試期限及 7200 秒整輪期限；有效輪次一律採用所選 profile 的期限快照。

接受開始監控時即固定共同輪次起點，來源準備時間也計入等待開始與整輪期限。準備期間主畫面仍會推進期限；若整輪上限先到，警報會顯示但在 Adapter 返回並完成位置裁決前不可確認。逾時後才返回的 Adapter 不會開始讀取來源。到期時，尚無可信活動或結果的位置顯示粉紅色 `NOTEST`，並記錄「期限內未觀察到測試」；已有活動或終態的位置保留。平台明確回報的 `NOTEST` 會保留平台來源證據。首個可信活動起算個別測試時間，後續進度及 `COMPLETING` 不重設期限；逾時只將該位置設為橘色 `TIMEOUT`，其他位置繼續監控。

只有最終匯出檔的平台不會由檔案複製時間推定 `TESTING`；Adapter 依結果資料及檔案穩定條件接受終態。所有有效位置都有終態時，程式立即停止收集；沒有待確認事項時結果可取用，不再額外觀察三秒。人工停止會保留既有終態，未完成位置標為 `STOPPED`，不會當作正常完成。停止後新檔不會改寫本輪結果。

若仍有未完成位置而整輪上限到達，程式停止讀取來源、保留既有終態，並依是否曾觀察到可信活動將其他位置定為 `NOTEST` 或 `TIMEOUT`，只建立一筆整輪警報。警報以非阻塞視窗顯示；關閉視窗不代表確認，可從主畫面的「整輪警報（待確認）」重新開啟。確認只解除該警報，不能清除結果衝突；警報與所有衝突等必要確認分別完成後，結果才可取用。確認沒有倒數時間。結果已齊全、只剩衝突待確認時，整輪上限不會轉成確認倒數或額外警報。

## KVM 顯示與快捷鍵

主視窗是供 KVM 擷取的固定高對比看板：只顯示目前專案／機型、KVM 狀態模板、有效位置、狀態、產品 SN 與開始／停止按鈕。它採瘦長的 376 px 固定寬度，所有主畫面文字固定為 14 pt，啟動時會自動放在螢幕右上方；工程師配置決定有效容量及位置映射。「設定」視窗只提供工程師配置編輯及事件／Session 查閱，不提供第二套工站、路徑或期限設定。

看板頂端的 `KVM RESULT` 是固定十格色帶；配置容量 1～10 時顯示一排十格，容量 11～20 時顯示兩排各十格。第一排代表位置 1～10，第二排代表 11～20，而且格內不顯示文字。色帶上方有左右不對稱的黑白定位點，以及獨立的 2×2 黑白狀態標記：待命為黑白對角線、監控中為上黑下白、待確認為左欄黑右欄白、本輪完成為反向對角線。標記只依共同輪次快照繪製；執行緒停止、人工停止或舊輪結果不能表示本輪完成。完成標記只在輪次已完成且結果可取用時顯示。定位點與狀態標記的幾何、取樣門檻及限制見 [KVM 顯示契約 1.1](docs/refactoring/KVM_DISPLAY_CONTRACT.md)。

容量內有效位置在每輪開始時為灰色 WAITING，出現測試活動後為黃色 TESTING，完成後依結果顯示綠色 PASS、紅色 FAIL 或粉紅色 NOTEST，逾時為橘色 TIMEOUT；容量內未投入位置仍使用 WAITING 等狀態色，容量外位置固定黑色。明細位於可捲動區，色帶、定位點及狀態標記不隨明細捲動。Ticket 12 本機 Tk 樣本不代表實際 KVM 擷取、壓縮或上位機辨識已驗收；部署取像與共同辨識驗收由 Ticket 16 完成。

若要顯示正式公司圖標，將提供的原始 PNG 置於 `assets/foxlink_logo.png`。該檔存在時會自動載入；未提供時畫面保留藍色 `FOXlink` 文字識別，避免阻擋監控程式啟動。

App 會固定使用高對比淺色介面，不跟隨 macOS 深色模式改變文字、輸入框、分頁或按鈕色彩，確保開發機、Mojave 與 Catalina 的畫面一致並方便 KVM 建立模板。

看板上方固定顯示 `PASS`、`FAIL`、`TESTING`、`NOTEST` 四個色塊，其文字、字級與背景色和 Slot 實際狀態完全相同，讓 KVM 在第一次測試前即可製作全部狀態模板。這些色塊只供取樣，不是操作按鈕。

- `Command + Shift + M` 等同「開始監控」。在 macOS 上會註冊為全域快捷鍵，因此 Atlas／BT HMI 有鍵盤焦點時也可觸發；程式正在監控時不會重啟本輪。
- Log Solution 不會持續置頂。解析到 PASS、FAIL 或 NOTEST 的最終結果時，主看板會自動回到前景並取得焦點，方便 KVM 立即讀取結果；之後仍可正常切換回測試程式。
- 快捷鍵只向 macOS 註冊這一組按鍵，並不監聽其他鍵盤輸入，所以不需要 Accessibility、Input Monitoring 或 Screen Recording 權限。
- 如果這組快捷鍵已被其他程式占用，App 會顯示警告；仍可按主畫面按鈕，或在 Log Solution 有焦點時使用相同按鍵。
- 目標最小螢幕解析度為 `1280 x 1024`。App 不會強制置頂，部署時應讓 Atlas／BT HMI 不覆蓋右上角看板。

- DFU：選擇 `active` 及 `unitest`；舊偏好遷移的預設容量為 7。Atlas Adapter 可解析來源位置 1～20，配置容量需依實際設備證據設定。
- FCT：選擇 `active` 及 `unit-archive`；舊偏好遷移的預設容量為 6。第一次讀到的可信 SN 會鎖定，active 消失後轉為 `COMPLETING` 並讀取最終 `records.csv`；全程無可信 SN 則顯示 `SN 讀取失敗 / FAIL`。Atlas Adapter 的 parser 上限不表示真實設備具有相同通道容量。
- BT／B482 TestData 格式：選擇配置的平台與機型，CaseInfo 根路徑可選。Adapter 將原始 Thread0～3 正規化為來源位置 1～4，再依 profile mapping 顯示在配置位置；CaseInfo 支援既有 CSV 記錄格式。只有 `狀態,--,SNRead,物料條碼` 中第二個 `SNRead` 後的第 6 欄會被當成物料條碼，例如 `4,InitResource,SNRead,--,SNRead,HK5HVH6ZSB300003YV,...`；會在最終 CSV 到達前顯示 `TESTING` 與條碼。檔案可用 CR、LF 或無換行的時間戳切分，且分次寫入的未完成記錄會等待完整後才讀取；SN 讀取失敗時產品判定為 `FAIL`，包含 TestData 空 SN 且狀態為 PASSED 或 FAILED。

### Ticket 14 controlled sample Adapter

工程師配置中可建立 `SAMPLE` 專案／`FCT` 機型並選擇 `sample-json`。操作員仍只選專案與機型。這是受控 JSON Lines 格式，用來驗證新格式經平台註冊、共同輪次、既有人工確認、Tk 畫面及稽核紀錄完成一輪；來源位置 1～20 是樣本解析能力，不代表任何真實設備容量。格式欄位、匿名化樣本、設定與回放步驟見 [受控樣本 Adapter 指南](docs/refactoring/SAMPLE_ADAPTER_GUIDE.md)。

受控來源使用完整 UTF-8 JSON Lines；每筆需以換行結尾才會被讀取，啟動前已有的內容會被快照排除。`batch_id` 只有在來源明確提供時才形成同輪比較證據；未知來源時間或 SN 保持未知。Adapter 使用既有 `ConfiguredMonitor` 映射與 `RoundCoordinator` 期限、衝突、警報、停止及放行流程，不新增樣本專屬畫面或逾時規則。此功能不宣稱新硬體、實際 KVM、目標設備或發布 App 已驗收，也不實作動態載入外掛。

每輪紀錄保存在 `~/Library/Application Support/B518LogSolution/sessions/`，包含既有的 `session.json`、`events.log`、`results.csv`，以及版本化的 `audit.jsonl`。稽核檔從接受開始時記錄輪次識別、配置快照與有序事件；來源時間、App 觀察時間、操作時間及單調經過時間分欄保存。`round_id` 僅用於追查與隔離，不證明來源屬於同一測試輪次。

在「設定 → 事件與 Session → 開啟 Session 紀錄」可找到目前 Session。維護工程師可用本機工具從磁碟重建輪次，不依賴仍執行中的 App：

```zsh
python3 tools/rebuild_round_audit.py "/完整路徑/audit.jsonl"
```

預設輸出完整配置、來源證據、結果、候選與操作時間；若只需狀態摘要，加入 `--summary`。舊 Session 仍可用原有檔案查看，未含 `audit.jsonl` 的舊紀錄不會被補造本輪快照。若紀錄寫入失敗，App 會在事件與輪次狀態中標示稽核不完整；依已確認產品決策，這不改變輪次既有的結果放行條件。截斷、損壞或不支援版本會被讀取工具明確拒絕，原有完整檔案不會以半份內容覆蓋。

## 美國 B518 BT／RS-WMT 試用流程

在「設定 → 工程師配置」選取或建立 `B518 / BT` 配置，平台設為 `rswmt`，結果路徑指向測試程式的 `output/SmtCal`，例如 `~/Documents/rswmt_conducted_1.0.0-b518+42/output/SmtCal`。按「套用並保存」後，操作員仍只在主畫面選專案與機型。舊偏好會明確遷移為版本化配置；App 不再提供另一組工站／格式／路徑／期限設定。

每輪先按「開始監控」，再到 RS-WMT 按 `Run All`。啟動快照排除原本已存在的檔案，不能把歷史資料夾直接指定為路徑就期待立即顯示結果。歷史驗證請用下方回放工具。

- CSV 跳過 Overlay 與上下限／單位列，讀取 `Serial Number`、`Test Pass/Fail Status`、`Test Start Time`／`Test Stop Time`，以 `tc=Slot...` 的值 1～4 作為來源位置，再依 profile mapping 對應顯示位置。`Summary_*.csv` 不作為單機結果。
- 每個結果檔穩定五秒後才定案。不同 Slot 的結束時間可以不同；本輪以解析後的開始時間（秒）鎖定。已確定同輪且同一有效位置的矛盾結果會進入共同待確認佇列，操作員可逐項保留原結果或採用已捕捉的新結果；來源證據不足以確認同輪的候選不提供採用選項，並將該 slot 判為 FAIL。相同結果的重複來源可追查但不重複發結果或衝突。
- 樣本 CSV 為 `YYYY/DD/MM`，檔名及 Log 為 `YYYY-MM-DD`。解析器以檔名結束時間核對日期，不以檔案複製時間代替測試時間。
- 無 SN 的明確 Fail 保留 `FAIL`。B482 空 SN 終態也判產品 `FAIL`；不要把 SN 讀取失敗解讀成可忽略的 NOTEST。沒有觀察到資料的 Slot 保留 WAITING，不憑空推定 PASS／FAIL／NOTEST；現場若有缺檔請停止本輪並收集資料。
- 即時 Log 支援樣本中的 `initialize`、`instance_active_1～4`、`MLB#..條碼` 與 `shutdown`。單項 `PASS:TestRunner Item complete.` 不代表整機 PASS。若提供另外的 Live logs 路徑，必須是相同格式、每個檔案包含單一 DUT／單輪的 Log；未指定時從結果根目錄讀取 `.log`。
- 目前只有完成後的原始匯出檔能確定，尚未確認測試中是否就能讀到這些 Log。只有最終匯出時會先等待、接著 COMPLETING，再顯示結果，無法從尚未存在的資料判定 Testing 或測試已當機。
- RS-WMT 的開始等待、測試上限及整輪上限均由所選版本化配置提供；若部署仍以 final-only 匯出為主，可在工程師配置中將開始等待設為 240 秒。期限在每輪開始時固定，後續配置編輯供下一輪使用。
- 最終結果沿用依 profile 容量顯示的一排或兩排 KVM 色帶與回到前景行為；逾時後的 Slot 不接受遲到結果。

### 同輪結果衝突

已確定同輪、同一有效顯示位置出現互相矛盾的來源時，主畫面會顯示待確認數量並開啟非模態衝突視窗。視窗列出原值、候選值、來源與可取得的來源時間；沒有來源時間時顯示未知。選擇「保留原結果」或「採用新結果」只處理所選衝突，其他候選保留在佇列中。關閉視窗不會替操作員作選擇。

待確認期間，其他位置仍繼續收集與計時。所有有效位置已有終態後，App 立即停止讀取新 Log，但會保留已捕捉候選；所有必要確認完成且沒有其他放行阻擋時才提供結果。每項選擇套用該衝突在觀察時固定的原值或候選值；同一位置有多項待確認時，最後一項操作員選擇決定該位置的有效值。選擇紀錄會保存操作後有效值。操作員選擇不會解除期限或人工停止的獨立阻擋。

無法確認來源是否屬於本輪時，操作員不能採用該候選；此規則涵蓋第一筆 final 與替換既有結果。共同輪次將 slot 判為紅色 `FAIL`，並停止該 slot 的候選替換。其他位置仍按正常規則監控。若來源缺少測試時間，系統保留未知，不以檔案或觀察時間補值。SN 不是證明同輪的必要欄位，但平台明確回報 SN 讀取失敗時產品仍判 FAIL。事件紀錄包含原結果、候選、來源測試時間、FAIL 處置及操作時間，不記理由。依使用者 2026-10-06 確認，FAIL 是一般輪次終態；符合其他必要條件後可完成輪次並供上位機讀取 FAIL。操作員不可把未知來源候選改成 PASS。

匿名化回歸測試保留實機欄位／Log 標記，不把原始條碼、站點或網路資訊提交到 repo。已用實際四組 CSV／Log 回放核對 Slot 與結果；失敗／缺件／分次寫入等情境另以測試資料驗證，尚待美國現場驗收。

```zsh
# 在程式目錄執行；只讀原始檔，使用暫存目錄與對齊的模擬時鐘
python3 tools/replay_rswmt.py /完整路徑/2026-09-11_05-45-44
```

美國同事可使用 [英文試用說明](docs/RSWMT_US_PILOT.md)。建置候選 App 後需在 15.4.1 確認實際檔案更新時機、四個 DUT、Fail（含無 SN）、快捷鍵、前景顯示與逾時。

## 開發目錄與驗證

以下指令由本 README 所在的應用程式資料夾執行：

```zsh
python3 src/b518_log_solution.py
python3 scripts/run_tests.py
python3 tools/replay_baseline_samples.py --caseinfo-date 2026-08-21 testdata/anonymized-baseline
```

| 目錄 | 內容 |
| --- | --- |
| `src/` | 桌面介面、監控核心、輪次與快捷鍵 |
| `tests/` | 行為、介面與打包驗證測試 |
| `tools/` | 樣本匿名化與回放 CLI |
| `scripts/` | macOS 建置、環境檢查、bundle 檢查與測試入口 |
| `requirements/` | 各目標平台建置依賴 |
| `docs/` | 試用說明與 `images/` 截圖 |
| `assets/` | App 使用的圖像資產 |
| `testdata/` | 匿名化行為基準樣本 |

指定測試可使用 `python3 scripts/run_tests.py test_monitoring_round`。完整測試包含 Tk 桌面測試，需可使用圖形介面的 macOS 工作階段。

Git 根目錄位於上一層；技能設定見 [AGENTS.md](../AGENTS.md)，領域詞彙見 [CONTEXT.md](../CONTEXT.md)，架構決策與重構規格見 [docs](../docs/)。歷史摘要與 ticket 執行紀錄保留當時的檔案位置與命令；目前命令以本節為準。

Ticket 16 將顯示契約更新為 1.1，在頂部加入獨立排數標記（黑白＝一排、白黑＝兩排），四種完成／待確認狀態圖樣不變。App 與上位機須配對更新；新版上位機拒絕缺少排數標記的 1.0 畫面。ATE 僅有 SFC 網路，因此由當地 TE 人工搬入使用者提供的配對版本；上位機內網及自動更新尚未確認。部署步驟見上位機 repo 的 `docs/TICKET16_DEPLOYMENT.md`。
