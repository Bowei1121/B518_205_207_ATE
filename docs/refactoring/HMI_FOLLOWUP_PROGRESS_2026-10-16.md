# HMI 後續實作接續紀錄

目前整合分支：`codex/hmi-followup-20261016`；HF1–HF4 已完成、整合、推送至 Gitea／GitHub，#61–#64 已結案。HF2 由 `e4cd033` 快轉整合至 `ed31f67cefd0ae7745ca4aeb56beaf3bf3f97dc4`，HF3 由 `cfc4738` 快轉至 `f0a1d6ad830a555130f5b60c8a3ff031b326525d`，HF4 由 `f502a83` 快轉至 `a5eb259f1a48edd52c2c7f31ccfb98b0fdddb987`。保留 issue 對帳提交 `63d9ee5`。HF5 #65 已完成實作、真正 App 雙語前景驗收及快轉整合，目前正同步雙遠端；接續 HF6、HF7。

歷史診斷階段：五項真正 Aqua Tk 測試曾有 4 通過，toolbar geometry 失敗且 teardown 錯誤；完整輸出見 `evidence/hmi-followup-20261016/hf1-hf2-desktop.log`。後續修復與受影響重驗結果見下文；不抹除原始失敗。

## 工作目錄

- 整合：專案根目錄 `B518 Log Solution`（桌面 FQ III／2026／B518／0. PC 下）。
- 診斷：`/private/tmp/B518-hf1-input-repair`，分支 `codex/hf1-input-repair`，tip `f9dfa16`，已整合。
- HF1：`/private/tmp/B518-hf1-toolbar`，分支 `codex/hf1-toolbar-icons`，tip `55a5ecf`，已整合。
- HF2：`/private/tmp/B518-hf2-bell`，分支 `codex/hf2-bell-recovery`，tip `520aaba`，已整合。
- HF1 修正：`codex/hf1-focus-fix`，tip `c24c6b3`，已快轉整合；工作樹清理待整批完成。
- HF2 補修驗收：`/private/tmp/B518-hf2-acceptance`，分支 `codex/hf2-acceptance-fix`，tip `ed31f67`，已快轉整合；工作樹清理待整批完成。
- HF3 通知徽章：`/private/tmp/B518-hf3-notification`，分支 `codex/hf3-notification-badge`，tip `f0a1d6a`，已快轉整合；工作樹清理待整批完成。
- 使用者原有未追蹤 evidence 的 3 個檔案在合併前確認無路徑碰撞並完整保留；修正分支新增的鍵盤與滑鼠 evidence 已納入版本。

## HF1 修正與驗證

- Tab 依畫面左至右：⚙️ → ⚠️ → 🔔 → 🌐，Shift+Tab 反向；可離開頂列到專案欄位，設定視窗無全域鍵盤綁定副作用。
- 三個 ttk 圖示提供藍底／焦點框，語言選單提供藍底；修正待確認計數遭擠至 1px，保留原 emoji 與 KVM 契約。
- Framework 3.8/Tk8.6.8 與使用者 Conda Python3.11.7/Tk8.6.12 真 Aqua 必要測試各 3/3；Conda 鍵盤／選單補充 2/2；KVM 7/7。
- 真 App 雙語主頁與四個焦點狀態截圖、bounds 已保存並檢視；證據與命令見 `HF1_KEYBOARD_FIX_2026-10-16.md`。
- 原生滑鼠已定位 runtime 差異：Conda 在最小 widget 與真 App 都收不到原生 pointer 事件，四操作 0/4；不能宣稱 Conda 已修好。Framework 真 App 四個獨立程序的設定／鈴鐺／專案／機型皆 4/4。
- 已提供 `B518 Log Solution/scripts/run_macos_desktop.sh`，選用已驗證的 Python.org Framework，避免 Terminal 的 Conda PATH；README 已更新。打包 App／其他 runtime 與工廠硬體仍待驗。
- 整合採 fast-forward，無程式合併修改；整合後只補 diff whitespace 與 Python compile，重用有效桌面證據。

## HF2 完整驗收補修

- 分支 `codex/hf2-acceptance-fix`，基準 `e4cd033`。完整紀錄見 [HF2_RECOVERY_ACCEPTANCE_2026-10-16.md](HF2_RECOVERY_ACCEPTANCE_2026-10-16.md)。
- 零警報確認按鈕英文化、可捲動長診斷、清單與閱讀位置保留、英文字串欄寬及可信封存成功顯示已修復。
- 補實際新恢復按鈕人工確認、Session／audit 連續故障再恢復、跨輪保存不換當前結果板、兩輪全部封存等真正 App 操作；80 行 raw 診斷仍完整可讀且背景重試不阻塞介面。
- 真 Session 故障發現兩種 audit reader 把歷史錯誤永久判不完整，已依後續耐久 `save_recovered` 恢復，仍要求完整連續事件，驗證缺失／無恢復／新失敗全部受保護；恢復事件本身寫入失敗仍阻擋可信封存與正常關閉。
- Framework 3.8／Tk 8.6.8 真 App 8/8（56.656 秒），保存封存領域 101/101、歷史查詢呈現 74/74，diff whitespace／Python compile 通過。9 類恢復情境雙語原生 PNG、逐項測試輸出與 bounds／hash manifest 已保存。
- 主頁舊恢復入口全部保留，工廠／正式打包環境仍待驗；本票本機驗收完成。merger 已快轉整合 `ed31f67`，無程式合併修改，重用以上有效測試及桌面證據；整合後 diff whitespace 與三個變更 Python 檔 compile 均通過。
- HF1 #61、HF2 #62 已在完整驗收、整合與雙遠端推送後結案；本 merger 不操作 Issue 狀態。

## HF3 通知計數徽章與整合

- HF3 #63 從整合基準 `cfc473827da8b46b028c3fd92beba94b18fc1413` 開始，提交 `93c604d1f29431b2a473697c43c15b23d6b3b4c9` 實作徽章與回歸、`f0a1d6ad830a555130f5b60c8a3ff031b326525d` 保存 12 張桌面圖；已快轉整合至後者。
- 尚未確認的整輪警報及有保存／封存異常的不同輪次各計一筆，同輪多個保存錯誤不重複；開啟中心不清除，確認／完整恢復後遞減。雙位數紅底白字徽章未遮住🌐、待確認計數或 KVM；徽章右側外的點擊不誤開鈴鐺，原鈴鐺區仍能操作。
- 真 Aqua Framework 3.8／Tk 8.6.8 三項測試 3/3（15.315 秒），含徽章生命週期與 HF1 頂列／KVM／Tab 回歸；`git diff --check` 與兩個受影響 Python 檔 `py_compile` 通過。繁中／英文零計數、同輪兩項、12 輪、單輪保存失敗及封存失敗／恢復畫面和 bounds 已保存檢視，完整記錄見 `B518 Log Solution/docs/refactoring/evidence/hf3/local-validation.md`。
- 工廠產線／正式打包環境仍待現場驗收。HF3 已完成雙遠端推送並結案 #63；未合主線或清理工作樹。

## HF4 主頁精簡與診斷入口

- HF4 #64 從整合 tip `f502a83d6bbb37a564d899290e1e83f3bc8f0e4c` 開始，功能提交 `58b0208`，人工驗收紀錄 `f31b9ab`，使用者原始中英畫面 `6df8a82`。
- 主頁改為短 App 狀態及底部 `App diagnostics`／`App 診斷` 入口，移除舊未保存輪次重試、封存摘要／重試與主頁 Retry Text；完整診斷及恢復仍由既有診斷／通知中心提供。KVM、狀態標記、位置與結果看板保留。
- 使用者在真正前景 App 的英文及繁體中文畫面各以滑鼠單擊診斷入口一次，均成功開啟診斷視窗。雙語主頁／診斷視窗截圖已保存檢視；細節見 [HF4 桌面驗收紀錄](evidence/hf4/local-validation.md)。
- HF4 真 Tk、toolbar/KVM 幾何、關閉保存失敗重試、HF2 封存重試、語言刷新失敗／重試、M10 整合測試均通過；`py_compile` 和 `git diff --check` 通過。自動擷取因非 Aqua 前景而產生的黑圖已排除，使用者有效前景證據已取代。工廠／正式打包環境另待驗收。
- HF4 本地功能與桌面驗收完成；整合／推送與 #64 結案由主協調者同步。下一張 HF5 #65，之後 HF6、HF7；尚未合回主線或清理工作樹。

## HF5 設定按鈕與三等分排列

- HF5 #65 分支 `codex/hf5-settings-layout` 從整合基準 `a5eb259f1a48edd52c2c7f31ccfb98b0fdddb987` 開始，提交 `ae3ad15150c27519c822135c1a13bff5746dda45` 已快轉整合至同一提交。
- 資料夾選取按鈕改為本地化「📂 瀏覽／📂 Browse」；六個配置操作分成兩排、每排三等分，取消草稿獨立置於下方右側。既有挑選／取消草稿、套用保存、載入、匯入匯出、部署重載及切換語言保留草稿行為。
- 真正 macOS Aqua App／Python.org Framework 3.8、Tk 8.6 原生視窗完成繁中與英文截圖。原生像素測量確認每排按鈕寬差不超過 1 px、等高等間距、取消草稿按鈕及兩排均在視窗內，英文標籤完整顯示。測試先以舊版像素寬差 104 px 重現 RED，再由真 Tk 測試通過；設定頁相關 UI 8 項、翻譯目錄 8 項、MachineProfile 24 項通過；Python compile 與 diff check 通過。
- 原生雙語 PNG、視窗 bounds 及行為測量見 [HF5 驗收證據](../B518%20Log%20Solution/docs/refactoring/evidence/hmi-followup-2026-10-16/hf5/README.md)。工廠設備／現場配置仍待現場驗收；尚未合回主線或清理工作樹。

## 下一步

1. 確認 HF5 整合分支已推送至既有 Gitea／GitHub 且兩端 SHA 相同，主協調者同步 #65 狀態。
2. 接續 HF6 → HF7，不平行修改 Tk。
3. 七票完成前不合回 `B518-Log-Solution`；工廠驗收另列，不代替桌面驗證。
