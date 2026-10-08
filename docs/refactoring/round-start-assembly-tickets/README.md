# 配置與輪次啟動組裝開發票

日期：2026-10-08。使用者已核可三票拆分及依賴。

來源規格：[ROUND_START_ASSEMBLY_SPEC_2026-10-08.md](../ROUND_START_ASSEMBLY_SPEC_2026-10-08.md)；父規格議題：[GitHub #24](https://github.com/Bowei1121/B518_205_207_ATE/issues/24)。本次未修改或關閉父議題。

| 票 | 開發票 | GitHub | Blocked by |
| --- | --- | --- | --- |
| R1 | [集中啟動準備，驗證配置與輪次紀錄一致性](01-concentrated-start-preparation.md) | [#25](https://github.com/Bowei1121/B518_205_207_ATE/issues/25) | 無，可立即開始 |
| R2 | [桌面開始操作接入集中準備流程](02-desktop-start-integration.md) | [#26](https://github.com/Bowei1121/B518_205_207_ATE/issues/26) | #25 |
| R3 | [移除舊組裝流程，完成交付驗證](03-contract-and-release-verification.md) | [#27](https://github.com/Bowei1121/B518_205_207_ATE/issues/27) | #26 |

R1 implementation and local verification are recorded in [R1 local validation](../evidence/round-start-assembly-ticket-01/local-validation.md). R1 was merged before R2 began. R2 implementation, main-branch verification, review, and delivery status are recorded in [R2 local validation](../evidence/round-start-assembly-ticket-02/local-validation.md); R3 old-path removal and overall release verification remain separate.

## 執行與交付

- R1 是第一階段：完成可直接驗證的集中準備流程，正式 Tk 入口維持原樣。
- R2 已將正式桌面開始操作接入集中準備流程，並合併至 `B518-Log-Solution`；主線驗證、遠端同步及票分支清理狀態見本地驗收紀錄。R3 再移除失去呼叫端的舊組裝細節並完成整體交付驗證。
- 原生 GitHub blocking 關係為 #25 → #26 → #27；R1 已納入 R2 工作基準。R3 仍待 R2 完成及後續交付。
- 原生 GitHub blocking 關係為 #25 → #26 → #27；每份本文亦保存 Blocked by 編號，不為建立子議題關係而修改父議題。
- 待確認時所有開始入口無副作用的修正與多語言工作維持另案。
- 程式與桌面驗證完成後交付；現場驗收清單包含實際配置、平台來源、正常開始、位置／結果、停止、失敗提示及保存關閉。實際設備驗收另階段安排。

本次僅拆票及發布，未修改程式、未執行產品測試。
