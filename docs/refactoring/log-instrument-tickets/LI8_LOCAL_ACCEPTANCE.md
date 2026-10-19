# LI8 本機整合驗收紀錄

候選整合：`codex/li8-local-integration-acceptance`
驗收基底：`b933600e0c5f835209502de0e3e210395acb5fb3`
完整證據索引：[li8-integration/README.md](../evidence/li8-integration/README.md)

## 驗收條件狀態

| AC | 狀態 | 證據摘要 |
|---|---|---|
| 1. LI1–LI7 獨立交付與 88 故事追溯 | 通過 | `LI8_STORY_EVIDENCE_MATRIX.md` 覆蓋 1–88，每項指定唯一 LI 主責及文件／證據位置；前七票狀態於開始前已核對完成。 |
| 2. 真 App 完整輪次生命週期 | 通過 | LI1、LI2、LI4、LI5 smoke：PREPARING→MONITORING→活動→PASS；逾時與人工停止、REVIEW、確認／取消、復位新輪。有效 contentView 圖在證據索引列出。 |
| 3. 交叉情境及晚回事件 | 通過 | 127 core tests、4 項真正 Tk disk/UI regression、LI2/LI5 smoke 驗證人工停止與衝突、期限／factory 例外、取消／新輪及舊輪事件隔離。 |
| 4. 新 reader、保存／關閉及歷史資料保護 | 通過 | 新 reader 重建一般結果、人工停止、啟動期限／警報及確認、prep stop 取消和復位；保存失敗可重試，保存未完成不關窗，歷史讀取不改寫。4 項真正 Tk UI regression 全過。 |
| 5. 六圖樣、helper、容量／語言／scaling／幾何 | 通過 | 11 項契約測試；真 Tk 16 格矩陣（scaling 1.0/1.5 × capacity 1/10/11/20 × English/繁中），透過設定 profile editor 與 Apply 切換，16 張可讀 view-cache PNG 與 JSON。 |
| 6. LI6 前景／焦點及控制回歸 | **部分通過** | 候選與基線各自單進程重跑都通過事件、結果、正常完成、逾時、人工停止、外部 Entry 焦點保持及非置頂檢查；兩版都在 minimize→restore 後讀到 `focus_get='.'`, `keyWindow=None`，故整項未通過。完整命令與輸出見證據索引。 |
| 7. 顯示契約 1.2 文件同步 | 通過 | 正式契約與交接文件已更新為 1.2；列出正式色樣、幾何與不相容性。 |
| 8. 交接責任及無橋接功能 | 通過 | 交接文件分清 Log 本機監控與 ATE 活動；`monitor_start`、`check_start`、`check_finish` 屬 KVM_Log，不新增 TCP／ACK／KVM 辨識。 |
| 9. 本機驗收範圍 | 通過 | 僅驗 Log Solution 公開輪次、磁碟重建及真 App/Tk；外部 KVM、JetKVM、Dock、LabVIEW、現場 ATE 不列前置。 |
| 10. 環境、命令、結果與限制 | 通過 | 各次命令、實際結果、擷取方式和無效黑圖均記於證據索引；舊 1.1 測試數不作本版證明。 |
| 11. 整合候選與草稿保護 | 通過 | 所有驗收在同一候選分支；未把尚未驗收的既有 UI 暫稿當成本票需求。父規格 #77 不修改。 |

> LI8 仍有 AC6 未完成，不代表 LI6 已有票務驗收失效；LI6 既有已完成證據另列於索引。本次在 LI8 指定的候選／基線桌面差分重驗未能重現 minimize/restore 後焦點恢復，不能宣稱全數 AC 通過或要求 Issue #85 關閉。
