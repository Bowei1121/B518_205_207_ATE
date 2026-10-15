# HM6：全 App 淺色一致性與整體驗收

固定審查基準：`c9b1993`（HM6 worktree 建立時的共同整合分支 HEAD）。
GitHub：#59；父規格：#47；整體 45 故事矩陣及畫面矩陣分別見 [`45-story-matrix.md`](45-story-matrix.md) 與 [`screen-matrix.md`](screen-matrix.md)。

## 本票修正

真 Tk 主頁截圖發現舊高度預算壓縮停止與保存重試按鈕；Light 桌面補驗又發現英文底部文字擠掉「重試所選」及「App 診斷」入口。最終固定主窗預算為 600pt，底部以固定 140pt 操作欄及換行狀態文字排列，輪次選擇與診斷操作分列，六個底部按鈕均完整可見。900pt 螢幕上的 FCT 根視窗為 `376x808`，顯示五個完整輪次列，其餘沿用原有捲動；同語言狀態下所有底部按鈕位置與尺寸一致。

同一真 Tk 截圖顯示語言標籤寬度使專案／機型 combobox 由英文 x=94pt 移至繁中 x=43pt。為主頁標籤欄設 81pt 最小寬度，兩語言所有記錄的頂列、識別、狀態、KVM與操作控件 bounds 逐項一致。測例也鎖住 stop/retry 控件高度，避免再次裁切。

主頁單排、12容量雙排 KVM 都以真正 Tk 操作驗收。雙排案例確認整區高度、第二排位置、狀態／布局標記、PASS 色及未使用黑格；沒有更動 KVM 的格位、顏色或解碼契約。原型 commit `9637913` 僅是方案來源，沒有合入產品分支。

## 測試與檢查

執行環境：macOS 15.7.9、Python 3.11.7、Tk/Tcl 8.6、Aqua Retina 2x。2026-10-15 使用者親自在系統設定切為 Light，完成擷取後親自切回 Dark；兩種實際系統外觀皆已驗證。測試程式未修改全機外觀設定。所有截圖均由 Quartz 擷取 App 自有視窗，原生標題列跟隨系統。

- 真 Tk 覆蓋 18 個案例，含主頁／Logo、376px 語言與 profile 選擇、三頁設定、共用淺色主題、衝突與警報、歷史／診斷、保存失敗重試、一般提示、鍵盤及 tooltip、QP 主頁查詢／取消／關閉回歸及 12 格 KVM 雙排；18/18 通過。
- `test_hm6_two_row_kvm_keeps_geometry_and_unused_slots_black` — 真 Tk 雙排 12 格案例通過，另存 `main-page-capacity12-en.png`。
- 主頁中英畫面所有 bounds 完全相同；`main-page-en.png`、`main-page-zh-TW.png`、`screenshots/window-bounds.json`。
- 中英設定位於 `settings-configuration-en.png`、`settings-configuration-zh-TW.png`。三個設定頁都在真 Tk 測例逐控件比較 bounds、草稿和選取狀態；截圖呈現配置頁。
- HM3 衝突／警報、HM4 歷史／來源異常／App診斷、HM5 一般通知／關閉保存的中英畫面及 bounds 已保存；完整索引見 `screen-matrix.md`。
- 非 Tk 相關回歸：語言、KVM contract、bundle verifier、machine profiles 共57項通過。
- Light 系統：11 項真 Tk 案例全通過，保存 19 張畫面及 bounds 到 `screenshots/system-light/`。人工檢視發現底部裁切後修正；修正後再跑主頁及雙排 KVM 兩項，通過且更新 Light 主頁畫面。Dark 系統在使用者還原後再驗證同一組 11 項並更新根目錄截圖。
- 底部回歸檢查六個按鈕中英均 `winfo_viewable`，實際寬高至少等於需求，且完整落在主視窗內。相對 `717d480` 證據，KVM 整區仍為 `[8,95,360,61]`、狀態標記 `[286,95,26,26]`、布局標記 `[138,97,26,14]`，沒有因底部增加高度而平移。
- Aqua/Tk 完整 repo 回歸：先前 `scripts/run_tests.py` 共493項，492通過、1項跳過（需要未提供的 H8 capacity fixture）。底部修正後的最終完整整合回歸結果記錄於 `EXECUTION_2026-10-15.md`。全程使用 Python 3.11.7/Tk 8.6，含歷史、監控、封存整合案例。
- `zsh -n`：三個既有 macOS build scripts 通過；`py_compile`、`git diff --check` 通過。
- Foxlink Logo 原始資產 `assets/foxlink_logo.png` 為 137×35，SHA-256 `e4db8e4abbc5156448e8e50913ab4485b8705cb50c0132a54382895c5fa14e21`。三個現有打包腳本均包含 `assets`；正式簽章 bundle／現場 KVM 未在本機產生或部署，未宣稱完成該類驗收。

## 外觀與限制

Dark 與 Light 系統桌面下，App 自有內容均使用 `clam` 淺色樣式；測例檢查 Label／Button 深色字、Entry 白底、唯讀文字 `LIGHT_BACKGROUND` 同底細框，以及一般提示、衝突、歷史、設定和主頁的實際畫面。原生標題列依系統外觀顯示。先前程序內覆寫 Aqua 的嘗試與 Tk 不相容，沒有用該嘗試代替本次實際 Light 桌面驗收。系統已由使用者還原為 Dark。

既有配置 Import/Export 仍由 HM2 真 Tk 案例透過 temporary folder 操作；保存、封存、診斷、查詢與 KVM 行為沒有因布局精簡而移除。最終整合分支仍需以固定起始 SHA `3517e75a794d1b9ba45c3bc17633f6b9abbfb405` 完成雙軸審查，才可合併回 `B518-Log-Solution` 並關閉父規格 #47。工廠／實體設備驗收另列，不阻擋開發合併；不重跑無具體風險理由的 216 萬事件數小時容量流程。
