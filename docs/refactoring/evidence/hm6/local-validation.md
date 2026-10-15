# HM6：全 App 淺色一致性與整體驗收

固定審查基準：`c9b1993`（HM6 worktree 建立時的共同整合分支 HEAD）。
GitHub：#59；父規格：#47；整體 45 故事矩陣及畫面矩陣分別見 [`45-story-matrix.md`](45-story-matrix.md) 與 [`screen-matrix.md`](screen-matrix.md)。

## 本票修正

真 Tk 主頁截圖在 macOS 15.7.9／900pt 螢幕發現主窗高度需求 768pt，舊計算只給 634pt，停止與保存重試鈕各被壓到 16pt（需求 36pt／34pt），封存及診斷操作列亦有裁切。將固定主窗預算由 379pt 改為 513pt；可見輪次列按螢幕高度減少，根視窗現在 `376x768`，完整操作區與需求高度相等或更高。

同一真 Tk 截圖顯示語言標籤寬度使專案／機型 combobox 由英文 x=94pt 移至繁中 x=43pt。為主頁標籤欄設 81pt 最小寬度，兩語言所有記錄的頂列、識別、狀態、KVM與操作控件 bounds 逐項一致。測例也鎖住 stop/retry 控件高度，避免再次裁切。

主頁單排、12容量雙排 KVM 都以真正 Tk 操作驗收。雙排案例確認整區高度、第二排位置、狀態／布局標記、PASS 色及未使用黑格；沒有更動 KVM 的格位、顏色或解碼契約。原型 commit `9637913` 僅是方案來源，沒有合入產品分支。

## 測試與檢查

執行環境：macOS 15.7.9、`AppleInterfaceStyle=Dark`、Python 3.11.7、Tk/Tcl 8.6、Aqua Retina 2x。沒有切換或修改全機外觀。所有截图均由 Quartz 擷取 App 自有視窗；原生 macOS 標題列保留系統深色外觀。

- 真 Tk 覆蓋 18 個案例，含主頁／Logo、376px 語言與 profile 選擇、三頁設定、共用淺色主題、衝突與警報、歷史／診斷、保存失敗重試、一般提示、鍵盤及 tooltip、QP 主頁查詢／取消／關閉回歸及 12 格 KVM 雙排；18/18 通過。
- `test_hm6_two_row_kvm_keeps_geometry_and_unused_slots_black` — 真 Tk 雙排 12 格案例通過，另存 `main-page-capacity12-en.png`。
- 主頁中英畫面所有 bounds 完全相同；`main-page-en.png`、`main-page-zh-TW.png`、`screenshots/window-bounds.json`。
- 中英設定位於 `settings-configuration-en.png`、`settings-configuration-zh-TW.png`。三個設定頁都在真 Tk 測例逐控件比較 bounds、草稿和選取狀態；截圖呈現配置頁。
- HM3 衝突／警報、HM4 歷史／來源異常／App診斷、HM5 一般通知／關閉保存的中英畫面及 bounds 已保存；完整索引見 `screen-matrix.md`。
- 非 Tk 相關回歸：語言、KVM contract、bundle verifier、machine profiles 共57項通過。
- Aqua/Tk 完整 repo 回歸：`scripts/run_tests.py`，493 項通過、1 項跳過（需要未提供的 H8 capacity fixture）；全程使用 Python 3.11.7/Tk 8.6，含主頁與其餘歷史、監控、封存整合案例。先修正三項歷史測試的過期幾何／round-record 數量／非同步完成等待條件，再完整重跑通過。
- `zsh -n`：三個既有 macOS build scripts 通過；`py_compile`、`git diff --check` 通過。
- Foxlink Logo 原始資產 `assets/foxlink_logo.png` 為 137×35，SHA-256 `e4db8e4abbc5156448e8e50913ab4485b8705cb50c0132a54382895c5fa14e21`。三個現有打包腳本均包含 `assets`；正式簽章 bundle／現場 KVM 未在本機產生或部署，未宣稱完成該類驗收。

## 外觀與限制

Dark 系統桌面下，App 自有內容仍使用 `clam` 淺色樣式；測例檢查 Label／Button 深色字、Entry 白底、唯讀文字 `LIGHT_BACKGROUND` 同底細框，以及一般提示、衝突、歷史、設定和主頁的實際畫面。把既有主題測例過期的 `settings_log == #ffffff` 預期修成規格正確的 `LIGHT_BACKGROUND`；設定事件文字是唯讀輸出，不是可編輯欄位。系統目前是 Dark；本票沒有改全機設定切到 Light，Light mode 的相同 palette 行為由程式固定樣式與控件測例覆蓋，不能冒稱做過第二種系統桌面的截圖驗收。

既有配置 Import/Export 仍由 HM2 真 Tk 案例透過 temporary folder 操作；保存、封存、診斷、查詢與 KVM 行為沒有因布局精簡而移除。最終整合分支仍需以固定起始 SHA `3517e75a794d1b9ba45c3bc17633f6b9abbfb405` 完成雙軸審查，才可合併回 `B518-Log-Solution` 並關閉父規格 #47。工廠／實體設備驗收另列，不阻擋開發合併；不重跑無具體風險理由的 216 萬事件數小時容量流程。
