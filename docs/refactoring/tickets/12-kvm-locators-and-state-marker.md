# 12：固定定位點與四種黑白程式標記

**類型：**新增

**What to build／工作內容與交付結果：**頂部固定定位點與獨立黑白標記表達待命、監控中、待確認、本輪完成，產品色帶與標記來自同一輪快照。

**Blocked by／前置依賴：**

- [08：配置容量與位置映射，完成十格／兩排顯示](08-capacity-mapping-kvm-layout.md)
- [11：整輪上限、一次警報與確認後放行](11-round-deadline-alarm-release.md)

**Status：**blocked（本機實作與四項驗收完成；AC 1 的實際 KVM 畫面方向／像素容差驗證缺少設備環境）

## 驗收條件

- [ ] 四種標記固定、不閃爍，有可驗證像素幾何、方向及辨識容差契約。Tk 幾何與合成樣本容差已驗證；實際 KVM 畫面的物理方向、縮放及容差尚未驗證。
- [x] 二十筆明細捲動時色帶、定位點與標記固定；衝突／警報為非模態，實際視窗矩形檢查沒有覆蓋辨識區。
- [x] 受控完整 Tk 輪次確認開始新輪時不會出現上一輪完成標記搭配新輪 WAITING 色帶。
- [x] 快照狀態映射、警報／衝突待確認、完成放行、人工停止及啟動失敗均有行為測試或 App 回放證據；不以執行緒結束判完成。
- [x] 高對比、快捷鍵、結果前景及不持續置頂回歸測試通過；視窗與縮放未裁切頂部。

## 驗證方式

Tk 操作、受控畫面與狀態切換驗證；輸出供上位機共同使用的顯示契約及樣本。

**規格驗收對照：**AC-17（可見標記）、AC-22～AC-24（App 顯示部分）

## 保留決策、待確認事項與限制

二乘二黑白格是已選方向。Tk 邏輯座標、定位點、圖樣、門檻及限制已落地於 [KVM 顯示契約 1.0](../KVM_DISPLAY_CONTRACT.md)。上位機實際取用與暫停由 16 完成，不以 App 畫面通過代替。真實 KVM 擷取設備／串流在本次環境不可用，因此硬體座標縮放、壓縮與實際辨識驗收是 AC 1 未通過的具體阻擋；不能以 JetKVM prototype 歷史畫面或合成圖片代替。本機可獨立交付的實作及四項驗收已完成，專用分支須保留，待有可連線的實際 KVM 取像後重驗 AC 1，再判斷是否符合合併條件。

所有行為測試須依 01 的接口確認結果落實；本次批准任務清單不代表測試接口已獲批准。未知同輪來源能否人工採用仍由 18 決定，任何本票的已完成部分都不能抵銷該未決分支。

## 執行與追蹤

依 2026-09-30 使用者確認的任務清單建立。以 REFACTOR_SPEC、CONTEXT 與 ADR 0001～0005 為基準，沿用測試配置、平台資料來源、監控輪次、桌面介面四模組與 Python／Tk／既有 macOS 打包方式。只在前置完成且本票關鍵待決及外部條件已滿足時轉為 ready-for-agent；需要人類決策的任務不得逕自轉為可直接實作。

執行時逐項記錄實際交付、驗證環境與結果、仍未決／待驗範圍及相關提交。未執行的驗收維持未勾選；本文件建立不代表 App 已完成重構。

## Ticket 12 執行紀錄｜2026-10-05

- 固定審查基準 `b21a5b65b7e2fc049afba53e39bfaef8ce57cda5`。從 `B518-Log-Solution` 建立 `codex/ticket-12`；實作 commit `cbd17a08b8d0e57be25bbad63b3bfb86a8693433` 已推送 Gitea 與 GitHub。後續驗收與審查紀錄仍在本票分支完成。
- 基準已包含 Ticket 08 的新十格／兩排色帶及 Ticket 11 的共同輪次快照／一次警報／獨立確認。以公開 `RoundSnapshot` 產生標記狀態，同一 Tk callback 更新結果帶與黑白標記；新輪起始畫面以新快照同步初始化，防止舊完成標記搭配新 WAITING 結果。
- 顯示契約版本 `1.0`：標記 2×2 pattern、四種唯一圖樣、22×22 不對稱定位點、Tk 座標、quiet zone、格距、黑白取樣門檻及拒絕未知／低對比輸入均記錄於 `KVM_DISPLAY_CONTRACT.md`。幾何為 Tk logical units；不宣稱等於實體或 KVM frame pixels。
- `$implement`／`$tdd` 測試先增後實作；公開快照狀態映射、四種 pattern 解碼、方向未知／錯誤、衝突優先於完成及未知／遮擋／低對比拒絕皆有測試。以固定基準 `b21a5b65b7e2fc049afba53e39bfaef8ce57cda5` 執行 code-review 雙軸複審：Standards 無未解發現；初審兩項 P3（快照參數未型別化、cell pitch 重複）已修正。Spec 初審發現確認阻擋必須優先於 Complete，已修正並新增 contradictory-snapshot 測試；方向不符需拒判已新增 asymmetric-locator samples 驗證。最終複審兩軸均無未解發現。AC 1 真實 KVM 驗收阻擋仍在，這是外部驗收缺口，不是未解 code-review finding。
- 受控 Tk 操作：`python3 -u tools/smoke_state_marker_app.py`。隔離 HOME、偏好、session、來源目錄，使用合成匿名化輪次資料。主視窗 376×682 Tk units、畫面 1440×900 Tk units、Tk scaling 約 1.0；Quartz 擷取視窗 PNG 為 752×1420 physical pixels（2× window capture）。衝突視窗及警報視窗矩形自動檢查未遮住頂部辨識區。檢查待命、監控、同時有衝突與警報的待確認、確認後完成、20 筆明細捲動、新輪初始化及人工停止。結果見 `evidence/ticket-12/run.json` 及同目錄 PNG。
- `B518_JetKVM_Log` 僅作唯讀參考：其 README 明確指出上位機 JetKVM 專案與本機 Log 專案獨立；JetKVM 解碼 BGR frame 可供 Ticket 16 測量實際畫面尺寸的做法參考。其歷史圖片與模板工具未作本票 KVM 證據，也未複製程式或資產。
- 環境：macOS 15.7.9、Intel x86_64、Python 3.8.10。`python3 scripts/run_tests.py test_kvm_display_contract`：7 項通過；完整 `python3 scripts/run_tests.py`：161 項通過。`python3 -m py_compile src/kvm_display_contract.py src/b518_log_solution.py tools/smoke_state_marker_app.py` 語法檢查通過。Repo 未設定 mypy／pyright 或其他型別檢查器；`py_compile` 不作型別檢查通過聲明。實際 KVM、目標設備、發布 App 與 Ticket 16 上位機共同取像／辨識未執行，不能以本機 Tk 截圖取代。
- 驗收記錄：AC 2～5 的本機 Tk 契約／受控 App 驗證通過。AC 1 保持未勾選，因實際 KVM 畫面方向、物理像素、縮放及容差尚未驗證；發布部署也未執行。Ticket 16 上位機共同整合沿用使用者既定分工，但不代替本票 AC 1 的待驗。
- commits: 基礎交付 `cbd17a08b8d0e57be25bbad63b3bfb86a8693433`；code-review 修正與新增方向辨識行為 `0e1cd4c`。執行紀錄、契約補充及匿名化 Tk 畫面證據另在同一專用分支後續文件 commit 提交。
