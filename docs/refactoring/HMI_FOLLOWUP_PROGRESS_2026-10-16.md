# HMI 後續實作接續紀錄

目前整合分支：`codex/hmi-followup-20261016`；已由 `63d9ee5` 快轉整合 HF1 修正 `7e23f1b` 與說明 `c24c6b3`，保留 issue 對帳提交 `63d9ee5`。本文件的保存提交見 Git 歷史。

歷史診斷階段：五項真正 Aqua Tk 測試曾有 4 通過，toolbar geometry 失敗且 teardown 錯誤；完整輸出見 `evidence/hmi-followup-20261016/hf1-hf2-desktop.log`。後續修復與受影響重驗結果見下文；不抹除原始失敗。

## 工作目錄

- 整合：專案根目錄 `B518 Log Solution`（桌面 FQ III／2026／B518／0. PC 下）。
- 診斷：`/private/tmp/B518-hf1-input-repair`，分支 `codex/hf1-input-repair`，tip `f9dfa16`，已整合。
- HF1：`/private/tmp/B518-hf1-toolbar`，分支 `codex/hf1-toolbar-icons`，tip `55a5ecf`，已整合。
- HF2：`/private/tmp/B518-hf2-bell`，分支 `codex/hf2-bell-recovery`，tip `520aaba`，已整合。
- HF1 修正：`codex/hf1-focus-fix`，tip `c24c6b3`，已快轉整合；工作樹清理待整批完成。
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
- 主頁舊恢復入口全部保留，工廠／正式打包環境仍待驗；本票本機驗收完成，整合推送／GitHub 結案待 merger。

## 下一步

1. merger 核對 HF2 成果與證據，正常合併到整合分支並推送既有兩個遠端後同步 #62。
2. HF1／HF2 完整驗收且推送後依使用者指定順序 HF3 → HF4 → HF5 → HF6 → HF7，不平行修改 Tk。
3. 七票完成前不合回 `B518-Log-Solution`；工廠驗收另列，不代替桌面驗證。
