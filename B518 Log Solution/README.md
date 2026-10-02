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

設定頁的路徑、工站與逾時秒數會在按下「儲存」時一起保存到 `~/Library/Application Support/B518LogSolution/preferences.json`。每個工站保有自己的路徑與逾時設定；下次啟動會恢復上次選擇的工站與其對應的 Slot 數。按「取消」不會保存設定頁中的修改。

## 逾時監控

每個工站可分別設定「等待開始測試逾時」、「測試時間上限」與「整輪監控上限」，皆以秒計且必須是正整數。等待開始／測試上限預設為 DFU `30 / 480`、FCT `30 / 480`、BT `30 / 240`；整輪監控上限預設為 7200 秒。

接受開始監控時即固定共同輪次起點，來源準備時間也計入等待開始期限。到期時，尚無可信活動或結果的位置顯示粉紅色 `NOTEST`，並記錄「期限內未觀察到測試」；已有活動或終態的位置保留。平台明確回報的 `NOTEST` 會保留平台來源證據。首個可信活動起算個別測試時間，後續進度及 `COMPLETING` 不重設期限；逾時只將該位置設為橘色 `TIMEOUT`，其他位置繼續監控。

只有最終匯出檔的平台不會由檔案複製時間推定 `TESTING`；Adapter 依結果資料及檔案穩定條件接受終態。所有有效位置都有終態時，程式立即停止收集；沒有待確認事項時結果可取用，不再額外觀察三秒。人工停止會保留既有終態，未完成位置標為 `STOPPED`，不會當作正常完成。停止後新檔不會改寫本輪結果。

## KVM 顯示與快捷鍵

主視窗是供 KVM 擷取的固定高對比看板：只顯示目前專案／機型、KVM 狀態模板、有效位置、狀態、產品 SN 與開始／停止按鈕。它採瘦長的 376 px 固定寬度，所有主畫面文字固定為 14 pt，啟動時會自動放在螢幕右上方；工程師配置決定有效容量及位置映射。設定、路徑、即時事件與 Session 紀錄都位於左上角的「設定」視窗。

看板頂端的 `KVM RESULT` 是固定十格色帶；配置容量 1～10 時顯示一排十格，容量 11～20 時顯示兩排各十格。第一排代表位置 1～10，第二排代表 11～20，而且格內不顯示文字。色帶兩端有方向相反的黑白定位標記，可用來定位色帶、確認方向並依固定中心位置取色。容量內有效位置在每輪開始時為灰色 WAITING，出現測試活動後為黃色 TESTING，完成後依結果顯示綠色 PASS、紅色 FAIL 或粉紅色 NOTEST，逾時為橘色 TIMEOUT；容量內未投入位置仍使用 WAITING 等狀態色，容量外位置固定黑色。明細位於可捲動區，色帶不隨明細捲動。

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
- BT／B482 TestData 格式：選擇配置的平台與機型，CaseInfo 根路徑可選。Adapter 將原始 Thread0～3 正規化為來源位置 1～4，再依 profile mapping 顯示在配置位置；CaseInfo 支援既有 CSV 記錄格式。只有 `狀態,--,SNRead,物料條碼` 中第二個 `SNRead` 後的第 6 欄會被當成物料條碼，例如 `4,InitResource,SNRead,--,SNRead,HK5HVH6ZSB300003YV,...`；會在最終 CSV 到達前顯示 `TESTING` 與條碼。檔案可用 CR、LF 或無換行的時間戳切分，且分次寫入的未完成記錄會等待完整後才讀取；空 SN 的 FAILED CSV 顯示 `NOTEST`。

每輪紀錄保存在 `~/Library/Application Support/B518LogSolution/sessions/`，包含事件、結果、設定、時間與來源檔案。

## 美國 B518 BT／RS-WMT 試用流程

設定頁選擇工站 `BT`、格式 `B518 RS-WMT`，結果路徑指向測試程式的 `output/SmtCal`，例如 `~/Documents/rswmt_conducted_1.0.0-b518+42/output/SmtCal`。請選固定根目錄，程式會遞迴監控新產生的時間戳子目錄。舊設定預設仍使用 `B482 TestData`。

每輪先按「開始監控」，再到 RS-WMT 按 `Run All`。啟動快照排除原本已存在的檔案，不能把歷史資料夾直接指定為路徑就期待立即顯示結果。歷史驗證請用下方回放工具。

- CSV 跳過 Overlay 與上下限／單位列，讀取 `Serial Number`、`Test Pass/Fail Status`、`Test Start Time`／`Test Stop Time`，以 `tc=Slot...` 的值 1～4 作為來源位置，再依 profile mapping 對應顯示位置。`Summary_*.csv` 不作為單機結果。
- 每個結果檔穩定五秒後才定案。不同 Slot 的結束時間可以不同；本輪以解析後的開始時間（秒）鎖定。已確定同輪且同一有效位置的矛盾結果會進入共同待確認佇列，操作員可逐項保留原結果或採用已捕捉的新結果；來源證據不足以確認同輪的資料只保留證據，不提供採用選項。相同結果的重複來源可追查但不重複發結果或衝突。
- 樣本 CSV 為 `YYYY/DD/MM`，檔名及 Log 為 `YYYY-MM-DD`。解析器以檔名結束時間核對日期，不以檔案複製時間代替測試時間。
- 無 SN 的明確 Fail 保留 `FAIL`，與 B482「空 SN FAILED → NOTEST」規則分開。沒有觀察到資料的 Slot 保留 WAITING，不憑空推定 PASS／FAIL／NOTEST；現場若有缺檔請停止本輪並收集資料。
- 即時 Log 支援樣本中的 `initialize`、`instance_active_1～4`、`MLB#..條碼` 與 `shutdown`。單項 `PASS:TestRunner Item complete.` 不代表整機 PASS。若提供另外的 Live logs 路徑，必須是相同格式、每個檔案包含單一 DUT／單輪的 Log；未指定時從結果根目錄讀取 `.log`。
- 目前只有完成後的原始匯出檔能確定，尚未確認測試中是否就能讀到這些 Log。只有最終匯出時會先等待、接著 COMPLETING，再顯示結果，無法從尚未存在的資料判定 Testing 或測試已當機。
- 在設定頁切換到 RS-WMT 時，原本 30 秒的等待時間會改為 240 秒供結果匯出模式試用；取消不保存，其他自訂數值保留。測試時間上限仍為 240 秒，從首次觀察到該 Slot 的有效活動起算。若確認即時 Log 可用，可將等待時間設回 30 秒。
- 最終結果沿用依 profile 容量顯示的一排或兩排 KVM 色帶與回到前景行為；逾時後的 Slot 不接受遲到結果。

### 同輪結果衝突

已確定同輪、同一有效顯示位置出現互相矛盾的來源時，主畫面會顯示待確認數量並開啟非模態衝突視窗。視窗列出原值、候選值、來源與可取得的來源時間；沒有來源時間時顯示未知。選擇「保留原結果」或「採用新結果」只處理所選衝突，其他候選保留在佇列中。關閉視窗不會替操作員作選擇。

待確認期間，其他位置仍繼續收集與計時。所有有效位置已有終態後，App 立即停止讀取新 Log，但會保留已捕捉候選；所有必要確認完成且沒有其他放行阻擋時才提供結果。操作員選擇不會解除期限或人工停止的獨立阻擋。無法確定資料是否屬於本輪時，App 保留來源證據，採用政策依 Ticket 18 決定。

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
