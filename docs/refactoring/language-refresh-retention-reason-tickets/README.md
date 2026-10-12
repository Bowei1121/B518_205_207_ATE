# 多視窗語言更新與清理原因表述開發票

日期：2026-10-12。使用者已核可八張票的粒度與依賴，並明確同意 GitHub 發布。

來源規格：[多視窗語言更新與清理原因表述](../LANGUAGE_REFRESH_AND_RETENTION_REASON_SPEC_2026-10-12.md)；父規格：[GitHub #28](https://github.com/Bowei1121/B518_205_207_ATE/issues/28)。只引用父議題，不修改、關閉或新增其原生子議題關係。

| 票 | 開發票 | GitHub | Blocked by |
| --- | --- | --- | --- |
| L1 | [語言通知、失敗提示與重試](01-language-notification-recovery.md) | [#29](https://github.com/Bowei1121/B518_205_207_ATE/issues/29) | 無，可開始 |
| L2 | [設定與查閱視窗接入語言通知](02-settings-and-readers.md) | [#30](https://github.com/Bowei1121/B518_205_207_ATE/issues/30) | #29 |
| L3 | [衝突、警報與關閉視窗接入](03-review-alarm-close.md) | [#31](https://github.com/Bowei1121/B518_205_207_ATE/issues/31) | #29 |
| L4 | [移除舊刷新流程，完成第一項驗收](04-language-contract-verification.md) | [#32](https://github.com/Bowei1121/B518_205_207_ATE/issues/32) | #30、#31 |
| C1 | [新舊清理摘要相容讀取與原因呈現](05-reason-compatible-reading.md) | [#33](https://github.com/Bowei1121/B518_205_207_ATE/issues/33) | 無，可開始 |
| C2 | [輪次清理與封存驗證產生雙語原因](06-round-archive-reasons.md) | [#34](https://github.com/Bowei1121/B518_205_207_ATE/issues/34) | #33 |
| C3 | [App 事件清理產生雙語原因](07-app-event-reasons.md) | [#35](https://github.com/Bowei1121/B518_205_207_ATE/issues/35) | #33 |
| C4 | [畫面統一使用原因表述，完成第二項驗收](08-reason-contract-verification.md) | [#36](https://github.com/Bowei1121/B518_205_207_ATE/issues/36) | #34、#35 |

## 執行與交付

- 語言組：L1 → L2／L3 → L4。清理原因組：C1 → C2／C3 → C4；兩組不互相阻擋。
- 每張票包含端到端或直接可驗證的行為，遷移時保持原檢查通過；最後收縮票移除舊流程並完成各項獨立交付驗收。
- 全部標記 ready-for-agent，但只從未受未完成票阻擋的工作開始。發布時 L1（#29）、C1（#33）可立即開始。
- 原生 GitHub blocking 關係與每票 Blocked by 本文均保留；不因設置父子關係修改父規格。
- 真正 Tk 驗證視窗內容、輸入／選取／閱讀、生命週期與故障重試；真實磁碟驗證原因摘要、舊資料相容與安全清理，避免只檢查私有方法呼叫。
- 不混入通用事件機制、來源事件身分重構、監控／裁決政策、新語言、journal 效能改造或正式工廠驗收。

本次只拆票與發布，不實作程式、不重跑產品測試。各票完成時另記錄當時實際命令、版本、結果與驗收限制。

## Implementation status

- L1 (#29) is implemented on `LanguageRefresh/ticket-01`; its evidence and remaining runtime limitations are in [local-validation.md](../evidence/language-refresh-ticket-01/local-validation.md). This does not claim all-window migration or complete the parent specification's first acceptance item; L2–L4 remain separate.
- L2 and L3 remain dependent on L1 delivery and are not included here. C1–C4 are unaffected.
