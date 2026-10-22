# HC8 整合回歸驗收

Issue [#113](https://github.com/Bowei1121/B518_205_207_ATE/issues/113)；父規格 [#105](https://github.com/Bowei1121/B518_205_207_ATE/issues/105)。本紀錄只代表表內標示的整合基準與證據；不代表父規格整體完成。

## 版本與執行環境

| 項目 | 值 |
| --- | --- |
| 整合基準 | `07ab0fbbae8eb50032ca2152f86a881f6d376449`（HC7 PR #120 合併提交） |
| HC8 回歸／證據提交 | `5e2b85b`；此提交新增跨功能真 Tk 斷言，App runtime source tree 未變 |
| App source tree | `e32ba1068f361e4540670b0d92739faa50965ffc` |
| App 版本／顯示契約 | `0.1.0`／`1.3` |
| 執行日期 | 2026-10-22（Asia/Taipei） |
| 本次測試環境 | macOS 15.8.1、Intel x86_64、Python 3.12.10、Tk 8.6 |
| 本次顯示條件 | 桌面 1440×900；本次程序未安裝 Quartz／AppKit，不能合成原生滑鼠／鍵盤輸入，也未切換實體螢幕模式 |
| 另有的原生矩陣 | HC7 在同 App source tree 實測 1440×900 與 1152×720；Tk 1.0/1.5、容量 1/10/11/20、中英，共 32 case／128 張 NSView 圖 |
| JetKVM | 本次沒有設備、配對部署或 received frame |

`07ab0fb` 的 App source tree 與 HC7 原生矩陣記錄的 source tree 相同。HC4／HC5／HC6／HC7 的合併證據沿用時明確標為既有證據；本次重新執行的測試另列於「本次實際執行」。

## T01–T22 對照

| T | 整合結果 | 觀察／證據 |
| --- | --- | --- |
| T01 | 通過 | 本次 `test_initial_capacity_does_not_change_fixed_window_geometry`；HC7 矩陣保留固定控制區座標。 |
| T02 | 通過（沿用原生矩陣） | [HC7 PR #120](https://github.com/Bowei1121/B518_205_207_ATE/pull/120) 的真實 1440×900、1152×720 顯示條件及完整 HMI 矩陣；本次沒有切換顯示器。 |
| T03 | 通過 | 本次固定幾何與容量測試、31 項整合批次；HC7 32 case 涵蓋容量 1/10/11/20、中英及提醒／長計時狀態。 |
| T04 | 通過 | 本次 HC2 真 App 兩種 Tk scaling 通道列測試；HC7 原生矩陣含容量 11、20。 |
| T05 | 通過 | 本次 `test_st1_compact_rows_and_small_window_keep_all_slots_reachable`；確認完整列可捲動到且字體保持。 |
| T06 | 通過 | 本次通道列及小視窗測試；少量通道保留表格背景、沒有新增假 Slot。 |
| T07 | 通過 | 本次 HC2 真 App 雙縮放測試檢查黑色格線與字體；狀態色另由 1.3 契約測試覆蓋。 |
| T08 | 通過（沿用量測） | HC3 `hc3-before-after-geometry.json` 記錄改版前後視窗、列高及表格外間距；本次未重做改版前量測。 |
| T09 | 通過 | 本次 M10 真 App 的啟動驗證／來源準備失敗通知測試；[HC1 PR #114](https://github.com/Bowei1121/B518_205_207_ATE/pull/114) 真 Tk 已驗證解除後不自動重試。 |
| T10 | 通過（沿用＋整合） | 本次 M10 多視窗、取消與單次決策及停止準備後關窗流程通過；HC1／[HC4 PR #119](https://github.com/Bowei1121/B518_205_207_ATE/pull/119) 證據確認保留舊輪、拒絕取消不變更輪次及明確新輪。 |
| T11 | 通過（沿用＋整合） | HC4 PR #119 真 Tk 驗證警報／保存失敗共用件數、解決後減量及排除結果衝突；本次提醒生命週期測試通過。 |
| T12 | 通過 | 本次提醒真 Tk 測試見證亮／暗切換、長計時及固定幾何；HC7 PR #120 原生影像矩陣驗證提醒亮／暗下的 timer ROI。 |
| T13 | 通過 | 本次 HC4 提醒與 M10 全視窗語言／取消整合測試；打開通知中心及切語言不會執行處理操作。 |
| T14 | 通過（沿用＋整合） | HC4 PR #119 實際保存／封存失敗流程為 2→1→12→0、新事項重啟；本次提醒真 Tk 測試通過。 |
| T15 | 通過 | 本次 1.3 狀態／結果契約測試及 M10 警報／衝突測試；衝突入口與鈴鐺件數分開。 |
| T16 | 通過（沿用 HC5／HC6） | [HC5 PR #117](https://github.com/Bowei1121/B518_205_207_ATE/pull/117)／[HC6 PR #115](https://github.com/Bowei1121/B518_205_207_ATE/pull/115) 已完成各視窗可用／停用、中英文提示與動作語意獨立驗收；本次 10 項語言目錄測試通過。原生 Quartz 指標輸入本次未重跑。 |
| T17 | 通過（沿用 HC5／HC6） | HC5／HC6 已驗證原地切語言、焦點提示及關窗清理；本次歷史提示關窗與多視窗語言刷新測試通過。 |
| T18 | 通過 | 本次 timer、reminder、heartbeat 契約測試；HC4 真 Tk 長計時 10000:00 與 HC7 心跳獨立矩陣支持。 |
| T19 | 通過 | 本次關窗重試及提示關窗測試；HC4 實際提醒存在時中心關閉／重開與 App 正常結束已通過。 |
| T20 | 通過（沿用＋整合） | HC1 PR #114 真 Tk 取消後重讀 audit 確認原因、原結果及單一取消事件；本次 M10 啟動錯誤與保存流程回歸通過。 |
| T21 | 通過（沿用 HC7 原生證據） | HC7 PR #120 32/32 case、128/128 PNG hash／尺寸／ROI 驗證通過；本次以 `verify_hc7_evidence.py` 離線重驗。 |
| T22 | **待真機驗收** | 無 JetKVM received frame／部署配對；遠端縮放、壓縮、遮擋、可讀性、計時／狀態／結果與獨立心跳皆未測，保持未勾。 |

### 父規格 45 個使用情境索引

| 使用情境 | 對應 T | 結果 |
| --- | --- | --- |
| 1 | T01 | 通過 |
| 2 | T02 | 通過（沿用 HC7 原生矩陣） |
| 3 | T01、T03 | 通過 |
| 4 | T01 | 通過 |
| 5 | T03 | 通過 |
| 6–7 | T04 | 通過 |
| 8–10 | T05 | 通過 |
| 11–12 | T07 | 通過 |
| 13 | T08 | 通過（沿用 HC3 前後量測） |
| 14–15 | T06 | 通過 |
| 16 | T01、T03、T18 | 通過 |
| 17 | T08、T21 | 通過（含沿用 HC7 幾何） |
| 18 | T03、T18 | 通過 |
| 19–21 | T09 | 通過 |
| 22–23 | T10、T20 | 通過（沿用 HC1 取消／重讀證據） |
| 24 | T09 | 通過 |
| 25–27 | T11 | 通過（沿用 HC4 同一事項計數證據） |
| 28 | T12 | 通過 |
| 29 | T13 | 通過 |
| 30–31 | T14 | 通過（沿用 HC4 生命週期證據） |
| 32 | T12 | 通過 |
| 33 | T11、T15 | 通過 |
| 34–38 | T16 | 通過（沿用 HC5／HC6 原生驗收） |
| 39–40 | T17 | 通過（沿用 HC5／HC6 原生驗收） |
| 41 | T21、T22 | **遠端驗收待 JetKVM** |
| 42 | T18、T21、T22 | 本機心跳獨立通過；遠端影格待 JetKVM |
| 43 | T10、T15、T20 | 通過 |
| 44 | T17、T19 | 通過（HC5／HC6／HC4 生命週期證據） |
| 45 | T20、T21、T22 | 本機／橋接文件分流完成；真實遠端證據待 JetKVM |

## 本次實際執行

1. `B518_TK_TESTS=1 python3 'B518 Log Solution/scripts/run_tests.py'`：在基準 commit `07ab0fb` 啟動完整套件，當時已包含相同 App source tree，尚未加入 HC8 的額外整合斷言。套件未完成：到第 275 項時卡在 `test_notice_escape_hidden_reopen_and_current_language_lifecycle` 的 modal 關窗；中止前已記錄 **264 passed、3 failed、4 errors、3 skipped，另 1 項執行中**。原始輸出見 `full-suite.log`。因此完整套件結果是**未完成／未通過**，不是全套綠燈。
2. 31 項整合批次在 HC8 回歸提交 `5e2b85b` 上執行：`test_m10_integration.M10SourceIntegrationTests`、`test_language_catalog.LanguageCatalogTests`、`test_kvm_display_contract.KvmDisplayContractTests`，**31 passed、0 failed、0 skipped（15.172s）**。
3. 15 項真 Tk／布局聚焦批次：**13 passed、1 failed、1 skipped**。失敗 `test_settings_and_recovery_actions_explain_bilingual_behavior_without_invoking` 因 `Quartz is None`（原生 macOS 指標輸入不可用）；跳過 `test_fixed_hmi_fits_smaller_supported_display`，測試要求另行啟動 1152×720 實體顯示驗收。其餘 13 項通過。沒有將環境缺少原生輸入或顯示切換能力描述為產品通過。
4. `python3 'B518 Log Solution/scripts/verify_hc7_evidence.py' 'B518 Log Solution/docs/refactoring/evidence/hc7-20261022/native-matrix'`：`PASS: 32/32 Cartesian cases, 128/128 PNG hashes/dimensions and ROI records`。

全套中出現的 `test_close_failure_keeps_window_open_and_real_retry_rebuilds_complete_audit` 曾報 FAIL；立即單獨重跑同一測試後 **1/1 通過（3.769s）**，顯示整批執行結果不穩定，仍保留首次 FAIL，不以單項重跑抹除。原生互動／影像項目報錯與 Quartz 不可用相符，但中止前 unittest 尚未輸出 traceback；未推定其他 FAIL／ERROR 的根因。T22 無自動測試可替代實機配對。

## T22 待驗條件與橋接缺口

完成 T22 至少需要：可用 JetKVM 與目標顯示器、App 與已部署橋接的確切版本／commit、已配對連線、真實接收影格與其尺寸／縮放／壓縮條件，以及遮擋／靜止影格刺激。逐項記錄 timer、狀態、結果格、定位點、心跳 crop 與來源時間戳；不能用 App 原生截圖代替收到的影格。

HC7 已記錄橋接 source `Bowei1121/B518_KVM_Log@736bb8b4df5ce87beaf140416f3aea027d3aa1d7` 的 1.3 parser 把橘色 `STALLED` 與 `TIMEOUT` 同樣解讀成 TIMEOUT。此語意缺口由橋接所屬專案處理；配對前須確認橋接版本及相應狀態定義。此記錄不代表橋接已修正或部署。

**本驗收不關閉 #113、不勾 T22、不改寫父規格 #105。** 完成 T22、在可操作的原生 macOS 桌面重跑必要完整回歸，並處理完整套件的 FAIL／ERROR 後，需在同 PR 更新證據並交獨立審查者複查最新 HEAD。
