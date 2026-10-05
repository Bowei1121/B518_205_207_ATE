# Ticket 17：macOS 發布與現場驗收

本指南記錄 B518 Log Solution 的可重現建置方式、離線部署程序、驗收項目與證據界線。每次發布都要填寫本指南的驗收紀錄；未實際執行的項目標為「待驗」，不得用其他測試結果代替。

## 發布目標

| 產物 | 建置主機 | 原生架構與 Python/Tk | 最低 macOS | 建置命令 |
| --- | --- | --- | --- | --- |
| Intel 舊測試機 | Intel Catalina 10.15.x | x86_64；Python 3.12，須能載入 `tkinter`、`_tkinter` | 10.14 | `./scripts/build_macos10_14_log_solution.sh` |
| Apple Silicon 15.x | Apple Silicon、macOS 15.0 或更新版本 | 原生 arm64；Python.org 3.12.10 universal2，建置時執行環境必須是 arm64，且 Tk 可用 | 15.0 | `./scripts/build_macos15_arm64_log_solution.sh` |
| Apple Silicon 26.x 測試機 | Apple Silicon、macOS 26.x | 原生 arm64；Homebrew Python 3.12，且 Tk 可用 | 26.0 | `./scripts/build_macos26_arm64_log_solution.sh` |

Apple Silicon 15.0 bundle 是為涵蓋 macOS 15.x 而建置，不能只因在較新 macOS 開啟成功就宣稱最低版本已驗收。macOS 26 bundle 的最低版本為 26.0，不能部署到 macOS 15。Intel 舊版腳本在 Catalina 建置並將 deployment target 設為 10.14；Catalina 建置成功不等於 10.14／10.15 實機相容通過。

三個腳本會建立各自的虛擬環境、安裝鎖定的 PyInstaller 依賴、先執行完整測試，成功後才遞增 `VERSION` 並建立 bundle。設定的 Python 架構或 Tk 前置不符時，preflight 會中止。腳本會檢查 bundle 主程式及內含 Mach-O 架構、最低系統版本及可解析的函式庫相依，再建立 ZIP 與 SHA-256 sidecar。執行前請確認自己位於 `B518 Log Solution/`；腳本會清理對應 target 的 `build-*` 與 `dist-*` 目錄，不要把其他需要保留的產物放在這些目錄。

`codesign --sign -` 產生的是 ad-hoc 簽章。它不是 Developer ID 簽章，也不代表 notarization 已完成。若部署政策要求 Developer ID 或 notarization，須取得發布憑證與核准流程後另行完成；不得把 ad-hoc 驗證描述為 Gatekeeper／notarization 驗收。

## 建置與產物查驗

在符合表格條件的乾淨建置主機登入桌面，執行對應命令。Apple Silicon 建置機若使用 Rosetta 終端或 Intel Python，preflight 應拒絕。建置前先記錄 Git commit、工作樹狀態、`sw_vers -productVersion`、`uname -m`、Python 路徑及 `python3 --version`；不要把 Python universal2 標籤當作實際執行架構的證據。

成功後記錄腳本輸出的 ZIP 路徑及版本，並在建置機執行：

```zsh
shasum -a 256 -c "dist-目標目錄/產物.zip.sha256"
```

確認 bundle 內 `Contents/Info.plist` 的 `CFBundleShortVersionString`、`CFBundleVersion`、`LSMinimumSystemVersion`，並在發佈前保留 verifier 與 `codesign --verify --deep --strict` 的實際輸出。驗證輸出需與 commit、產物檔名及 SHA-256 一起保存。Verifier 是靜態載入指令檢查，不涵蓋執行階段動態載入、所有 macOS API 相容性或實機啟動。

已知 scripts 行為：10.14 Intel 目標在 Catalina 執行完整測試，檢查 x86_64 及部署版本；15.0 arm64 目標執行 Python/Tk preflight 及 arm64 bundle 相依檢查；26.0 arm64 目標也執行 Python/Tk preflight 及 arm64 bundle 相依檢查。三種產物均採 ad-hoc 簽章並輸出 SHA-256，簽章類型與結果應原樣記錄。

## 離線部署

更新由 App 維護者提供；當地 TE 工程師協助人工搬入及安裝。ATE 設備只連 SFC 網路，不要求設備連外、Git pull 或在線安裝 Python／套件。每次搬運需一併提供對應目標 macOS／架構的 ZIP、SHA-256 sidecar、版本與本指南列出的限制；不要在不同目標間共用不相容的 bundle。

TE 在目標機以 `shasum -a 256 -c` 驗證收到的 ZIP 後解壓，記錄原 App 版本與新 App 版本，再依站點程序替換 App。首次啟動時若 macOS 提示安全或隔離屬性問題，記錄提示原文並依核准的 IT／簽章政策處理；不得為了繞過提示而把 ad-hoc 簽章說成已 notarize。啟動後確認 App 版本及設定位置，再執行下方操作驗收。現場紀錄包含日期、設備識別（不記錄產品 SN）、macOS 版本、CPU 架構、App 版本、ZIP SHA-256、部署人員角色、結果及限制。

設定檔由 App 保存於 `~/Library/Application Support/B518LogSolution/preferences.json`；每輪開始時會鎖定所選版本化配置快照。Session 與 audit 預設在 `~/Library/Application Support/B518LogSolution/sessions/`。部署時確認有效的工程師配置已包含正確的專案、機型、平台、容量、來源位置映射、Log 路徑與期限；配置參數更新可透過配置部署，不代表新 Log 格式可免 App 更新。

## 操作與現場整輪驗收

先確認螢幕至少 `1280 x 1024`，Atlas／BT HMI 不會覆蓋右上方看板。操作員只選擇專案與 DFU／FCT／BT 機型；工程師配置與一般操作分開。開始前確認 Log 路徑可讀，使用本輪新資料，不用歷史檔案冒充現場一輪。

逐項記錄下列實際結果：

1. 驗證工程師配置能載入正確專案／機型設定；操作員重新啟動 App 後仍能選取有效設定。配置容量、路徑及映射更新不改變已啟動輪次的快照。
2. 以「開始監控」建立本輪。確認開始前既有檔案不會被當作本輪結果，所選路徑缺失或不可讀時會在開始前顯示原因。
3. 確認 KVM 固定十格排列：容量 1–10 使用第一排，11–20 使用第二排，容量外格為黑色；容量內未投入位置按平台證據呈現，不以黑格取代 `NOTEST`。
4. 確認固定定位點及黑白狀態標記可見且沒有被明細捲動或確認視窗遮住。標記依同一輪快照表達待命、監控中、待確認與本輪完成。
5. 在 Log Solution 無焦點時按 `Command + Shift + M` 開始監控，並記錄是否被其他程式佔用；按鈕及 App 有焦點時的操作也要確認。重複開始不應重設目前輪次。
6. 觀察至少一個真實來源位置到終態；記錄位置映射、平台證據、狀態及可用 SN 的去識別化代碼。確認 `PASS`、`FAIL`、`NOTEST`、`TIMEOUT` 符合實際平台證據及配置。
7. 若產生同輪結果衝突或整輪警報，確認明細顯示原結果、候選、來源與可用時間。關閉視窗不算確認；警報確認與每項衝突選擇各自完成後才可放行。未決期間上位機須暫停後續動作。
8. 完成後確認 App 不持續置頂，最終 `PASS`／`FAIL`／`NOTEST` 會使看板回到前景並可被 KVM 讀取；結果已齊全後停止收集，不把後續資料套入本輪。
9. 取得 Session／audit 記錄，核對本輪版本、配置快照、來源、結果、逾時／警報、人工選擇、停止收集與放行事件。確認原始 SN 與不需保存的個資沒有進入交付證據。

若現場沒有 RS-WMT 即時資料時機或其他必要測試資料，分別列待驗並記錄取得條件；不得以匿名化回放、合成資料、Tk 來源測試或 KVM 截圖替代實機資料時序及現場整輪。

## Ticket 18 未決範圍

Ticket 18 尚未取得「來源不能確定是否同輪時，是否允許人員採用結果」的使用者政策。Ticket 17 的文件、建置或已知平台驗收不替這項政策定案，也不把未知來源候選標成可採用。依現有平台配置及證據契約處理資料；任何需仰賴該政策的操作／發布範圍都列為未完成，待 Ticket 18 定案後再補行為及現場驗收。這項待決與硬體、bundle、部署或 RS-WMT 資料缺口分開記錄。

## Ticket 17 驗收紀錄

每次候選建置複製此表格填寫；多個目標使用多份記錄。摘要應保留產物校驗值，但避免收錄產品 SN 或原始測試資料。

| 驗收層 | 版本／主機／架構 | 命令或實際操作 | 結果與證據 | 狀態／限制 |
| --- | --- | --- | --- | --- |
| 本機核心測試 |  |  |  | 待執行 |
| 真實 Tk 受控測試 |  |  |  | 待執行 |
| 靜態打包檢查 |  |  |  | 待執行 |
| 實際 bundle、啟動、簽章及 SHA-256 |  |  |  | 待執行 |
| Intel macOS 10.14／10.15 實機 |  |  |  | 待設備 |
| Apple Silicon macOS 15.x 實機 |  |  |  | 待設備 |
| Apple Silicon macOS 26.x 測試機 |  |  |  | 待設備／確認是否發布目標 |
| 現場資料與完整一輪 |  |  |  | 待現場 |

發布前確認所有必要列有真實結果。若目前無法取得目標設備、Python/Tk 建置環境、簽章政策或 RS-WMT 現場資料，記錄負責角色與下一個具體步驟；Ticket 維持未完成，Ticket 分支保留。
