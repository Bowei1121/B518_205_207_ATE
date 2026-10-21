# 固定高度 HMI 開發票 — 2026-10-21

使用者已核准八票拆分；已發布至 GitHub，均為父規格 [#105](https://github.com/Bowei1121/B518_205_207_ATE/issues/105) 的原生子議題並標記 `ready-for-agent`。依賴使用 GitHub 原生 Blocked by 關係，逐票本機正文與遠端一致（本機額外保留標題行）。

| 票 | GitHub | 交付 | 必須先完成 |
| --- | --- | --- | --- |
| [HC1](01-bell-actions-and-count.md) | [#106](https://github.com/Bowei1121/B518_205_207_ATE/issues/106) | 鈴鐺收納異常操作與一致件數 | 無 |
| [HC2](02-compact-rows-black-grid.md) | [#107](https://github.com/Bowei1121/B518_205_207_ATE/issues/107) | 縮小通道列高、黑色格線與完整捲動 | 無 |
| [HC3](03-fixed-startup-layout.md) | [#108](https://github.com/Bowei1121/B518_205_207_ATE/issues/108) | 依螢幕決定固定高度與操作位置 | [HC1 #106](https://github.com/Bowei1121/B518_205_207_ATE/issues/106), [HC2 #107](https://github.com/Bowei1121/B518_205_207_ATE/issues/107) |
| [HC4](04-flashing-action-reminder.md) | [#109](https://github.com/Bowei1121/B518_205_207_ATE/issues/109) | 待處理事項紅字閃爍與生命週期 | [HC3 #108](https://github.com/Bowei1121/B518_205_207_ATE/issues/108) |
| [HC5](05-main-settings-recovery-hints.md) | [#110](https://github.com/Bowei1121/B518_205_207_ATE/issues/110) | 主頁、設定與鈴鐺的白話雙語提示 | [HC1 #106](https://github.com/Bowei1121/B518_205_207_ATE/issues/106) |
| [HC6](06-review-history-diagnostics-hints.md) | [#111](https://github.com/Bowei1121/B518_205_207_ATE/issues/111) | 待確認、歷史與診斷的白話雙語提示 | 無 |
| [HC7](07-kvm-geometry-handoff.md) | [#112](https://github.com/Bowei1121/B518_205_207_ATE/issues/112) | 新版本機幾何量測與 KVM 模板交接 | [HC4 #109](https://github.com/Bowei1121/B518_205_207_ATE/issues/109) |
| [HC8](08-integrated-and-remote-acceptance.md) | [#113](https://github.com/Bowei1121/B518_205_207_ATE/issues/113) | 整合回歸與真實 JetKVM 配對驗收 | [HC5 #110](https://github.com/Bowei1121/B518_205_207_ATE/issues/110), [HC6 #111](https://github.com/Bowei1121/B518_205_207_ATE/issues/111), [HC7 #112](https://github.com/Bowei1121/B518_205_207_ATE/issues/112) |

## 起始可認領

- HC1 #106：鈴鐺收納異常操作與一致件數。
- HC2 #107：縮小通道列高、黑色格線與完整捲動。
- HC6 #111：待確認、歷史與診斷的白話雙語提示。

依賴只列真正的直接前置，不重複列出可由路徑推導的前置。HC3 等 HC1／HC2 後凍結布局；HC4 依 HC3 的固定提示區實作閃爍；HC5 等搬移後的新入口；HC7 量測閃爍版幾何；HC8 等全部分支後整合與設備配對驗收。

## 覆蓋與發布核對

- 八票各自包含可操作成果、細部驗收與父規格使用情境／驗收編號。
- 全部 45 個使用情境與 T01～T22 收錄於機器可讀的 [票務對照](ticket-plan.json)，HC8 另核對完整整合覆蓋。
- 共 8 條原生阻擋關係：HC3←HC1／HC2、HC4←HC3、HC5←HC1、HC7←HC4、HC8←HC5／HC6／HC7。
- [發布核對結果](publication-verification.json)記錄各票正文、父子關係、阻擋關係、標籤與狀態的遠端讀回結果；不是產品驗收證據。
- 父 #105 的正文、標題、標籤、留言與開關狀態保持原樣，僅新增已授權的原生子議題關係。
- 真實 JetKVM 驗收缺設備時須保留待驗，不能以本機截圖或文件代替。
- 本輪僅發布開發票，不啟動產品實作、不認領、不建立 PR 或自動合併。
