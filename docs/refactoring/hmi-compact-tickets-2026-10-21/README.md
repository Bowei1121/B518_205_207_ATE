# 固定高度 HMI 開發票拆分草案 — 2026-10-21

狀態：待使用者確認粒度與依賴；尚未建立 GitHub 子議題。核准後逐票發布並建立原生子議題及阻擋關係，套用 ready-for-agent。父 #105 正文、標題、標籤與開關狀態不修改。

來源：[父規格 #105](https://github.com/Bowei1121/B518_205_207_ATE/issues/105)；已讀回全文與留言（無留言、目前無子議題），與本機規格一致。每票含可操作成果及真實驗收，不另外新增橫向預重構票；現有 App 入口、通知中心、提示及影像驗收可直接沿用。

| 票 | 交付 | 必須先完成 |
| --- | --- | --- |
| [HC1](01-bell-actions-and-count.md) | 鈴鐺收納異常操作與一致件數 | 無 |
| [HC2](02-compact-rows-black-grid.md) | 縮小通道列高、黑色格線與完整捲動 | 無 |
| [HC3](03-fixed-startup-layout.md) | 依螢幕決定固定高度與操作位置 | HC1, HC2 |
| [HC4](04-flashing-action-reminder.md) | 待處理事項紅字閃爍與生命週期 | HC3 |
| [HC5](05-main-settings-recovery-hints.md) | 主頁、設定與鈴鐺的白話雙語提示 | HC1 |
| [HC6](06-review-history-diagnostics-hints.md) | 待確認、歷史與診斷的白話雙語提示 | 無 |
| [HC7](07-kvm-geometry-handoff.md) | 新版本機幾何量測與 KVM 模板交接 | HC4 |
| [HC8](08-integrated-and-remote-acceptance.md) | 整合回歸與真實 JetKVM 配對驗收 | HC5, HC6, HC7 |

初始可開始：HC1、HC2、HC6。依賴只列直接前置，不重複列出可由路徑推導的前置；例如 HC4 經 HC3 已包含 HC1／HC2，HC7 經 HC4 已包含布局與表格。

HC1先完成按鈕搬移與件數，HC2完成列高及表格規則，HC3才以最終控制項與列高凍結視窗；HC4在固定提示區交付閃爍。HC5依賴搬移後的新入口，HC6可獨立完成；HC7量測實際閃爍版布局，HC8整合所有分支並驗真實JetKVM。

全部 45 個使用情境及 T01～T22 已對照至逐票驗收；HC8另做全覆蓋整合核對。真實遠端驗收缺設備時保留未完成，不以文件或本機截圖代替。

核准後發布每票時，將草案標題行用於 Issue 標題、其餘內容用於正文；Blocked by 轉成原生關係，正文不留下草案代號作為正式依賴識別。
