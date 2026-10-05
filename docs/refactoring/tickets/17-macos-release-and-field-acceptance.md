# 17：完成部署文件、macOS 打包與目標機驗收

**類型：**發布

**What to build／工作內容與交付結果：**完成操作與配置文件、適用 Intel／Apple Silicon 建置及目標 macOS 部署驗證，交付可追溯驗收結果。

**Blocked by／前置依賴：**

- [15：移除已完成遷移的 MVP 舊流程](15-contract-legacy-monitoring.md)
- [16：同步更新上位機辨識並共同驗收](16-upstream-kvm-integration.md)

**Status：**blocked（前置任務完成後；另依本票外部前置檢查）

## 驗收條件

- [x] 操作、配置及部署說明符合專案＋機型、新布局、NOTEST、整輪警報與人工放行規則。
- [ ] 適用 Python／Tk 前置、測試門檻、bundle 架構／最低版本／依賴、簽章與校驗檢查有結果證據。
- [ ] 部署 App 可使用配置與資源，快捷鍵、結果前景顯示、非持續置頂及完整一輪正常。
- [ ] 既有各目標 macOS 的實機驗收與本機核心／Tk／靜態打包檢查分開列出，不混稱相容通過。
- [x] 缺少設備、RS-WMT 實際資料時機或其他現場限制各自列待驗，不以其他測試抵銷。
- [x] 若 18 仍未決，交付範圍與未完成分支明列，不能宣稱整體無保留驗收完成。

## 驗證方式

完成各層檢查與目標機現場一輪，建立版本、環境、結果、待驗及限制清單。

**規格驗收對照：**AC-26；AC-01～AC-28 的發布證據與未完成範圍

## 保留決策、待確認事項與限制

外部前置：對應 Intel／Apple Silicon 及目標 macOS 設備與現場環境。未知同輪政策若影響實際發布使用範圍，需先取得明確處理決定，不能自行默認。

所有行為測試須依 01 的接口確認結果落實；本次批准任務清單不代表測試接口已獲批准。未知同輪來源能否人工採用仍由 18 決定，任何本票的已完成部分都不能抵銷該未決分支。

## 執行與追蹤

依 2026-09-30 使用者確認的任務清單建立。以 REFACTOR_SPEC、CONTEXT 與 ADR 0001～0005 為基準，沿用測試配置、平台資料來源、監控輪次、桌面介面四模組與 Python／Tk／既有 macOS 打包方式。只在前置完成且本票關鍵待決及外部條件已滿足時轉為 ready-for-agent；需要人類決策的任務不得逕自轉為可直接實作。

執行時逐項記錄實際交付、驗證環境與結果、仍未決／待驗範圍及相關提交。未執行的驗收維持未勾選；本文件建立不代表 App 已完成重構。

## 執行紀錄｜2026-10-06

- 固定 Ticket 分支起點及 code-review 基準：`e3f4eb5541f70e326a7ede99b2bc342bd6d850b1`；之後將主分支新增的 2026-10-06 專案摘要提交 `26a097e1dd7fc00c40bbb7d8472d946fdc920939` 合併進 Ticket 分支並保留兩邊摘要內容。分支：`codex/ticket-17`。
- 完成 [macOS 發布與現場驗收指南](../../../B518%20Log%20Solution/docs/TICKET17_MACOS_RELEASE_AND_FIELD_ACCEPTANCE.md)；操作／配置／離線部署、三種 build target、手動驗收項目、Ticket 18 範圍限制及驗收證據層級已明列。目標設備、實際 bundle 與現場步驟沒有標成通過。
- 本機執行環境：macOS 15.7.9、Intel x86_64、Python 3.8.10。正式建置 target 需求分別為 Intel Catalina 10.15 + Python 3.12、Apple Silicon arm64 + Python/Tk 3.12 + macOS 15+，及 Apple Silicon arm64 + Python/Tk 3.12 + macOS 26.x；本機不符合任何 target，故沒有遞增版本、建立 bundle 或清理 build/dist 目錄。
- 以 TDD 擴充 `check_macos_build_python.py` 與 `verify_macos_bundle.py`，靜態查核支援 Intel x86_64 與 Apple Silicon arm64。10.14 Intel 及 26 arm64 build scripts 新增 Python/Tk preflight，並在產物階段執行最低 macOS 版本、架構及 bundle 內部依賴檢查。`scripts/run_tests.py test_verify_macos_bundle`：20 tests 通過；TDD 新案例曾先以 3 個 TypeError 和 1 個 fixture mismatch 失敗，介面及 fixture 修正後全綠。
- 完整 `python3 scripts/run_tests.py`：桌面 Tk 權限下最後一次重跑 188 tests 通過（22.621 秒）。sandbox 內執行遇 Tk 初始化 exit 134，不記為通過；桌面執行同一命令後成功。
- `zsh -n scripts/build_macos10_14_log_solution.sh scripts/build_macos15_arm64_log_solution.sh scripts/build_macos26_arm64_log_solution.sh` 通過。`python3 scripts/check_macos_build_python.py --architecture x86_64` 在本機因 Python 3.8 而依預期拒絕；不是 target preflight 通過紀錄。靜態 verifier 的架構、OS load command、依賴及拒絕案例由 20 項測試驗證，但沒有真實 `.app` bundle 可供查驗。
- 真實 Tk source App 受控回放：`python3 -u tools/smoke_deadline_app.py` 通過，驗證 underfilled PASS／NOTEST、空輪 NOTEST、individual TIMEOUT／STOPPED、整輪警報與候選衝突兩種確認順序、final-only RS-WMT NOTEST、警報到放行事件順序。`B518_SMOKE_TICKET=17 B518_SMOKE_EVIDENCE_DIR=/private/tmp/ticket17-tk-evidence python3 -u tools/smoke_state_marker_app.py` 通過，驗證契約 1.1 standby／monitoring／review／complete／新輪／人工停止狀態、兩種確認視窗不遮住固定頂部辨識區及 20 格明細捲動。隔離截圖及 `run.json` 位於 `B518 Log Solution/docs/refactoring/evidence/ticket-17/source-tk-replay/`，素材為合成樣本；`physical_kvm_available` 明確為 false。這些是來源 Tk App 的受控回放，不是發行 bundle、KVM 或現場驗收。
- UI suite 的快捷鍵 `Command+Shift+M`、衝突 fallback、結果前景顯示與永久置頂屬性回歸包含在完整 188 tests；沒有在發行 bundle 上人工驗收。設定與 Session 資源路徑有來源 App 的現有測試及 README 步驟，bundle 資源仍待真實建置驗證。
- 未執行：Intel macOS 10.14／10.15 目標機、Apple Silicon macOS 15.x（含最低 15.0）及 26.x 實機驗收；實際 PyInstaller bundle 啟動；真實 `codesign` 簽章／驗證與 ZIP SHA-256 校驗；部署後快捷鍵、前景、資源及完整一輪；KVM／ATE 治具與 RS-WMT 實際資料時機。Build host／目標設備均不可用是分別列出的阻擋，ad-hoc 簽章不是 Developer ID 或 notarization。
- 固定基準雙軸審查的 Standards 發現 build scripts 重複檢查 Mach-O 架構，已移除 10.14／26 的重複 `lipo` loops，留下共用 verifier；Spec 發現各目標實機未執行但 AC 4 已勾選，已取消該勾選。修正後聚焦 20 tests、完整 188 tests 及三個 zsh 語法檢查均通過。
- Ticket 18 人工採用政策仍未決。本票不為同輪來源不明的候選定義可採用行為；依賴該政策的發布／操作範圍未完成。雖文件、目標矩陣、限制與受控測試已記錄，AC 2、3、4 仍未勾選，Ticket 整體保持 blocked。沒有因本機測試與受控 Tk 回放通過而合併或刪除分支。
