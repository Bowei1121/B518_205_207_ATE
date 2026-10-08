# 配置與輪次啟動組裝開發票

日期：2026-10-08。使用者已核可三票拆分及依賴。

來源規格：[ROUND_START_ASSEMBLY_SPEC_2026-10-08.md](../ROUND_START_ASSEMBLY_SPEC_2026-10-08.md)；父規格議題：[GitHub #24](https://github.com/Bowei1121/B518_205_207_ATE/issues/24)。本次未修改或關閉父議題。

| 票 | 開發票 | GitHub | Blocked by |
| --- | --- | --- | --- |
| R1 | [集中啟動準備，驗證配置與輪次紀錄一致性](01-concentrated-start-preparation.md) | [#25](https://github.com/Bowei1121/B518_205_207_ATE/issues/25) | 無，可立即開始 |
| R2 | [桌面開始操作接入集中準備流程](02-desktop-start-integration.md) | [#26](https://github.com/Bowei1121/B518_205_207_ATE/issues/26) | #25 |
| R3 | [移除舊組裝流程，完成交付驗證](03-contract-and-release-verification.md) | [#27](https://github.com/Bowei1121/B518_205_207_ATE/issues/27) | #26 |

R1 implementation and local verification are recorded in [R1 local validation](../evidence/round-start-assembly-ticket-01/local-validation.md). R1 was merged before R2 began. R2 implementation, main-branch verification, review, and delivery status are recorded in [R2 local validation](../evidence/round-start-assembly-ticket-02/local-validation.md). R3 implementation, 14-scenario coverage, review, and release evidence are recorded in [R3 local validation](../evidence/round-start-assembly-ticket-03/local-validation.md); its separate physical field acceptance is listed in the [field checklist](../evidence/round-start-assembly-ticket-03/field-acceptance-checklist.md).

## 執行與交付

- R1 是第一階段：完成可直接驗證的集中準備流程，正式 Tk 入口維持原樣。
- R1／R2 已完成程式交付與主線驗證；R3 程式修改、受控真 Tk／平台／磁碟回歸、固定基準 Standards／Spec 審查及主線合併均已完成，合併後完整 Tk 套件通過 286 tests。Standards 無規範違反，留有一項非阻擋測試維護觀察；Spec 無阻擋缺口。最終文件 SHA `daad502d093994f1be2f369d3092dcb69d24ab54` 已直接確認同步至 Gitea／GitHub；本地與兩個遠端票分支均已安全移除。R3 移除只供不完整測試 App 使用的準備 fallback。各票既有主線合併、推送及分支清理 SHA 以其驗收文件為準。
- 原生 GitHub blocking 關係為 #25 → #26 → #27；每份本文保存 Blocked by 編號。本次未修改父規格 #24 或子議題狀態。
- 待確認時所有開始入口無副作用的修正與多語言工作維持另案。
- 程式與受控桌面驗證已完成；[現場驗收清單](../evidence/round-start-assembly-ticket-03/field-acceptance-checklist.md)列出實際配置、平台來源、正常開始、位置／結果、停止、失敗提示及保存關閉。實際設備驗收另階段安排，未宣稱已完成。

拆票時的歷史記錄為「僅拆票及發布，未修改程式」；其後 R1～R3 的程式與測試交付分別記於各票驗收文件。本 README 現況已依本機 Git ancestry、最終測試與逐票證據更新。
