# 16：同步更新上位機辨識並共同驗收

**類型：**整合

**What to build／工作內容與交付結果：**更新上位機新十格／兩排與黑白標記辨識，只有可靠完成才取用；待確認暫停該輪後續動作。

**Blocked by／前置依賴：**

- [12：固定定位點與四種黑白程式標記](12-kvm-locators-and-state-marker.md)

**Status：**受控整合已實作；外部責任／部署資料與實際 KVM 驗收待補

## 驗收條件

- [ ] 上位機程式、負責者、部署流程及可用 KVM 環境被定位並有紀錄。
- [ ] 各容量格位與容量外黑格辨識一致，四種標記在實際或受控 KVM 畫面可辨識。
- [x] 受控畫面中的確認／警報狀態不誤判完成，待確認暫停；未知或失真畫面拒判。
- [x] 只在可靠完成標記取用已觀察監控中的輪次；新輪切換、重連與重複 check 不會重取前輪畫面。
- [x] 結果回覆遺失後不自動重做本輪取用；App 與上位機受控畫面、狀態及行為已有回放證據。
- [x] DFU Log 結果流程已全面改用 1–20 格新排列，移除舊 4／7 格 Log 結果模板及執行路徑。外部 DFU 視窗的 4／7 格輸入 profile 保留，兩者用途不同。

## 驗證方式

以不同容量、監控中、確認中、正常完成、整輪逾時與失真畫面驗證共同取用契約。

**規格驗收對照：**AC-17（上位機暫停）、AC-23～AC-25

## 保留決策、待確認事項與限制

外部前置：本次已依使用者明確指示授權 `B518_JetKVM_Log` 作為受控整合目標。repo 與 JetKVM frame 接收程式已定位，但現行文件未指明維護／部署負責者、正式部署步驟、現場 KVM 身分及 App／上位機同步部署窗口；AC 1 因此保持未勾選。使用者已批准暫緩實際 KVM、治具、目標設備及發布 App 驗收；本機 App／上位機 frame seam 的受控組合測試照常完成，且不冒充 JetKVM 串流。

Ticket 01 公開輪次測試接口已於 2026-09-30 確認，不需重新批准；本票更正舊文字對此的暗示。未知同輪來源能否人工採用仍由 18 決定，任何本票已完成部分都不能抵銷該未決分支。

## 2026-10-05 執行紀錄

- App 基準：`f2a7a014a9afb4fac8be1047d11c209aed68a1fe`；專用分支：`codex/ticket-16`。
- 上位機基準：`be41a2e09af9156f87ec2cac575041b8dc6c0ac4`（`main`）；依其自身基準建立 `codex/ticket-16`，沒有沿用 App repo 的分支起點。
- 上位機第一個已驗證交付 commit：`45258c9`（完整 SHA 待後續執行紀錄補錄）；此 commit 尚待兩軸審查與所有既有目的地推送。
- 實際上位機來源為 `B518_JetKVM_Log/host-app/`；JetKVM frame 由 `JetKVMClient` 的 WebRTC track 解碼為 BGR NumPy array。frame 接收新增遞增序號、單調接收時間、stream identity 與安全快照接口。
- 上位機新增 `round_frame_consumer.py`：由兩個不對稱定位點估算 App frame 的平移與均勻比例，依顯示契約 1.0 解碼四種標記及 1–20 格色帶。Tk scaling、Quartz 像素與 JetKVM frame 尺寸分開記錄；目前僅量到 Tk／Quartz 受控畫面，沒有聲稱 JetKVM 實際像素相容。
- 判讀契約：灰階黑白門檻 80／176；狀態 BGR palette 距離容差 20；定位候選比例 0.70–3.25，兩 locator 水平間距誤差容差 3.5%；只在同一序號遞增的新鮮 frame 間確認，畫面新鮮度及完成 frame 最大間距皆為 1 秒，需兩張狀態與結果相同的完整 frame。未知色、非連續容量、裁切、方向／定位不明或中間狀態不放行。
- 固定基準 Spec 審查發現完成 frame 未與本輪容量及來源呈現時間綁定。已修正：Monitoring 鎖定容量，容量切換須重新觀察 Monitoring；JetKVM 解碼 frame 保存來源 PTS，實際 TCP 取用要求 PTS 存在且嚴格遞增，舊／重複 PTS 拒判；新增舊輪完成 frame 延遲抵達及容量切換回歸。離線截圖沒有 JetKVM PTS，回放工具使用明確標記的合成順序時間，不將其當成 JetKVM PTS 驗收。
- Round gate 以設備／KVM 隔離。啟動或重連先看到 Monitoring 才會 armed；Review 一律 pause；完成取用一次後不再重複回覆，需同連線觀察下一輪 Monitoring 才可再次取用。程序重啟後不會因殘留 Complete 畫面自行取用。
- DFU TCP `check` 已從 profile 專屬 4／7 格 Log OCR 移轉到共同顯示 frame 契約，移除舊 Log templates 與 checker。DFU 主視窗輸入所需 4／7 格模板保持不變。新回覆列為 `slot::STATUS`；顯示色帶不含 SN，外部 TCP 呼叫端／SN 配對尚未確認，需列為部署整合限制，不以 App 本機 Session 或 Audit 繞過 KVM。
- 受控組合驗證讀取 Ticket 12 由真實 Tk 視窗經 Quartz 各自擷取的 `standby.png`、`monitoring.png`、`review.png`、`complete.png`、`details-scrolled.png`；Ticket 12 的 `run.json` 確認 review、complete 與捲動畫面屬同一匿名化 round ID。五張獨立擷取都經 prototype 公開 BGR frame seam；結果為 standby／waiting、monitoring／waiting、review／paused、complete／waiting、complete／taken，容量 20 且色帶狀態一致。此為本機 Quartz 受控畫面，不是實際 JetKVM frame。
- 證據工具：`B518_JetKVM_Log/tools/verify_ticket16_app_frames.py`；機器可讀報告：`B518_JetKVM_Log/docs/evidence/ticket-16/app-frame-replay.json`。App 畫面 752×1420 像素，當時 Tk scaling 約 1.0，screen 1440×900 Tk units，Tk window 376×682；Locator 推定每 Tk unit 約 2 physical pixels。此僅描述該 Quartz capture。
- 驗證：上位機 `python3 -m unittest discover -s tests -v`，32 項通過；`python3 -m unittest tests.test_round_frame_consumer -v`，15 項通過；App repo 非 GUI 測試 `python3 "B518 Log Solution/scripts/run_tests.py" test_anonymize_baseline_samples test_atlas_source_adapter test_audit_records test_b482_source_adapter test_configured_monitor test_kvm_display_contract test_log_monitoring test_machine_profiles test_monitoring_round test_platform_registry test_replay_baseline_samples test_rswmt_monitoring test_verify_macos_bundle`，149 項通過；App 畫面／上位機 frame 組合工具以 5 張圖通過。
- App 完整測試入口 `python3 "B518 Log Solution/scripts/run_tests.py"` 已執行，但程序在 `test_log_solution_ui` 建立 Tk 視窗期間以 exit 134 中止，不能列為通過；本執行環境無可用 GUI 顯示會話。此票在 App repo 的程式碼沒有變更，Tk 畫面證據為既有 Ticket 12 實際 Quartz 擷取，且由上位機辨識器重新讀取原始像素驗證。Prototype 無型別檢查配置；App repo 亦未在本次執行型別檢查。
- 上位機既有 Python 3.8.10 runner 沒有 Pillow／Quartz 等 GUI dependencies；因此本次沒有重新啟動 Tk smoke。改用已保存、具 run.json 同輪佐證的真實 Tk／Quartz 獨立畫面，直接餵入 prototype frame seam。上位機程式無型別檢查配置；未以 compileall／py_compile 宣稱型別檢查通過。
- 已知未驗收：實際 JetKVM 串流取像／尺寸／H.264 壓縮／方向／縮放容差、現場設備動作、正式部署／發布 App；實際責任者與部署步驟未找到。Ticket 12 AC 1、Ticket 13 AC 4 維持原未勾選狀態。Ticket 17／18 不在本票結論範圍。
- 尚待確認：外部 TCP consumer 對新的 `action_waiting`／`action_paused` 回覆以及 `slot::STATUS`（無 SN）格式的相容性；目前 repo 沒有該 consumer。不得直接推定現場會接受，也不得直接讓實機動作接到未確認格式。
- 首批 prototype 實作 commit：`45258c9fccbdf39b32f7c069aa6fa4b6ae259a61`；審查修正及完整交付 commit 待補。App 驗收／摘要文件 commit：`278eb11e56a31d2f1c926a5d7c90876e48348bc9`，後續審查修正及最終記錄待補。App 非 GUI 149 項通過；完整套件在 Tk UI 測試建立視窗期間以 exit 134 中止，因此不宣稱完整 App 套件通過。

## 執行與追蹤

依 2026-09-30 使用者確認的任務清單建立。以 REFACTOR_SPEC、CONTEXT 與 ADR 0001～0005 為基準，沿用測試配置、平台資料來源、監控輪次、桌面介面四模組與 Python／Tk／既有 macOS 打包方式。只在前置完成且本票關鍵待決及外部條件已滿足時轉為 ready-for-agent；需要人類決策的任務不得逕自轉為可直接實作。

執行時逐項記錄實際交付、驗證環境與結果、仍未決／待驗範圍及相關提交。未執行的驗收維持未勾選；本文件建立不代表 App 已完成重構。
