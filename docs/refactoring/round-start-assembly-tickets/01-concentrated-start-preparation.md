## Parent

Part of #24 — https://github.com/Bowei1121/B518_205_207_ATE/issues/24

## What to build

在不切換正式 Tk 啟動入口的第一階段，讓集中啟動準備 Module 能透過既有輪次管理完成來源建立、位置對應與 Session／audit 配置保存。工程師可不建立畫面就驗證整條準備與紀錄流程，所有既有平台仍使用原解析 Adapter。

## Acceptance criteria

- [x] 先核對最新正式流程並補足有意義的基準行為測試；新 Module 不接收 Tk widget，正式 Tk 仍走原入口，既有測試維持通過。
- [x] 集中選定測試配置驗證與固定、必要／選填來源路徑檢查、平台建立能力、回呼橋接與來源／顯示位置映射；沿用 PlatformRegistry 與 ConfiguredMonitor 的真實責任。
- [x] 必要路徑不存在、不可讀／進入或空白時拒絕；選填路徑空白沿用省略規則，非空無效時拒絕；空白不當目前目錄，保留原平台標籤與錯誤文字。
- [x] 平台、容量、映射、路徑、逾時及版本由同一份固定配置衍生，後續外部設定變更不影響本輪；Session／audit 保留各自既有格式及原配置路徑含義，不新增 schema 版本。
- [x] 以公開準備 Interface 接入既有 RoundCoordinator，使用真實暫存來源與磁碟紀錄，驗證來源建立、位置／結果及兩份配置資訊一致；不以 mock 呼叫鏈代替端到端證據。
- [x] 覆蓋 Atlas DFU／FCT、B482 BT、RS-WMT BT、受控 sample-json FCT；樣本平台不代替實際平台解析測試。
- [x] 來源建立仍由輪次接受後的背景準備執行，不另設輪次狀態機或排程；接受時間與就緒時間分開，準備耗時計入期限。
- [x] 以受控來源與可注入時鐘驗證緩慢準備、停止與逾時；來源晚到不得重新收集，事件順序與輪次歸屬保持一致。
- [x] 來源背景建立失敗保留失敗輪次及事件，仍受跨輪追蹤與正常關閉完整保存保護；驗證磁碟證據且不得重複發送事件。
- [x] 保留雙向位置映射與未映射來源證據處理；不改結果判定、原始來源、未知同輪採用政策或 KVM 契約。
- [x] 記錄本票實際執行的測試與限制；不宣稱桌面已切換或現場已驗收。

Implementation evidence: [R1 local validation](../evidence/round-start-assembly-ticket-01/local-validation.md). Formal Tk startup remains on the original assembly path; R2/R3 and field-device acceptance are not included.

## Blocked by

None (can start immediately).
