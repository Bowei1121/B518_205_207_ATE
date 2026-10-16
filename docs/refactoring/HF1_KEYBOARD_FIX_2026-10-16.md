# HF1 鍵盤與桌面輸入修正

基準：`63d9ee5d575cb07b58976be57da4ecc760745cec`；票分支：`codex/hf1-focus-fix`。

## 已重現與修正

使用者實際 trace 位於 App 目錄 `docs/refactoring/evidence/hmi-followup-2026-10-16/keyboard-fix-before/`，保留原始副本。原 Tab 順序是設定、語言、鈴鐺、待確認，與視覺順序不同；使用者 Shift+Tab 有事件但沒有移動焦點。新真正 Aqua 輸入 seam 測試先紅：從設定 Tab 落在 Menubutton，而非預期待確認。

假說依證據排序：1. 控制項建立次序驅動 Tk traversal；2. Aqua 的 Shift+Tab 未匹配 Tk 原生反向 binding；3. 主題缺少 focus 狀態視覺。以控制項建立順序、真實 state=Shift 按鍵及 App 截圖分別驗證。

修正為設定→待確認→鈴鐺→語言，繼續 Tab 可離開頂列到專案選單；反向也能離開頂列，不形成焦點圈。Shift+Tab 只在四個頂列控制項與相鄰專案欄位綁定，設定與其他視窗不受全域 binding 影響。X11 ISO_Left_Tab 僅在 runtime 支援時加入；Aqua 8.6.8 不定義該 keysym。

待確認為 disabled 時仍可聚焦辨識位置，但 Space 不開確認窗。三個 ttk 圖示提供藍色底與藍色焦點框，語言 Menubutton 提供藍色底。圖片保持原 emoji。

## 頂列像素預算

真 App 376px 主窗、左右各8px、header 35px、Logo137×35維持。舊3個 ttk 控制項各50px使待確認計數被擠成1px；單 emoji width=1 後各30px，Logo137、計數54、語言68及間距11，合計360px。計數0與7位測試字串可見。KVM元素、色帶、位置標記與顏色未更動；中英與所有焦點狀態均比對幾何。

舊 HF1/Logo 測試只跑 update_idletasks 就讀尚未映射視窗的1×1尺寸；改等待實際映射後再量測。鈴鐺測試與提示已更新為 HF2 的恢復中心，保留真實點擊測試。

## 真桌面驗證

macOS 15.7.9，使用者明確確認 Terminal 為 `/opt/anaconda3/bin/python3`，Python3.11.7／Tk8.6.12。

- 使用者目標 runtime 與 Framework3.8.10／Tk8.6.8：三個必要測試各3/3通過（頂列幾何與工具提示/操作、雙語鍵盤順逆遍歷、Logo正常/缺失/損壞）。
- Anaconda補充鍵盤離開頂列、原語言選單切換與跨App偏好保存：2/2通過。
- KVM display contract：7/7通過。
- App 子目錄 `docs/refactoring/evidence/hmi-followup-2026-10-16/keyboard-fix-conda/` 保存主頁雙語、四個焦點各雙語共10張真正 App 截圖及 bounds。已逐張檢視8張焦點截圖：glyph無截斷、焦點藍底清楚、0計數可見、KVM不變。Framework對照在 `keyboard-fix/`。
- Anaconda診斷工具5秒smoke與Framework launcher5秒smoke均正常完成保存關閉，並保存runtime/trace/summary。

執行命令：

```zsh
B518_TK_TESTS=1 /opt/anaconda3/bin/python3 "B518 Log Solution/scripts/run_tests.py" \
  test_log_solution_ui.LogSolutionUiTests.test_hm1_toolbar_title_status_and_kvm_geometry_stay_fixed \
  test_log_solution_ui.LogSolutionUiTests.test_toolbar_keyboard_traverses_visual_order_and_leaves_toolbar \
  test_log_solution_ui.LogSolutionUiTests.test_hm1_logo_normal_missing_and_corrupt_keep_fixed_slot_without_dialog
```

Framework 對照將 interpreter 換成 Python.org Framework3.8 的 python3。截圖使用 `B518_TK_EVIDENCE_DIR` 指定上列目錄。

## 滑鼠環境差異與限制

使用者已更正：只有鍵盤能開啟，滑鼠不能；專案/機型也需多次點擊。未將先前誤述的單擊成功當驗收。

相同最小 ttk.Button 的 Quartz 原生 move/down/up、控制項最前 bindtag：Anaconda python3與pythonw皆零按下/放開、callback0；Framework收到兩事件且callback1。結果與可重現probe保存在 `keyboard-fix-conda/pointer-runtime-*`；不能推論所有Conda版本都有此問題，也不改動回調業務或全域Python。

同一真正App原生單擊腳本於Anaconda的設定、鈴鐺、專案與機型皆未開啟，raw pointer事件為空，原始JSON在 `keyboard-fix-conda/native-app-pointer-result.json`。

新增 `scripts/run_macos_desktop.sh` 避免(base)的PATH默默選到故障runtime，優先已安裝Python.org Framework，支援PYTHON_BIN明確指定並列印interpreter。README改以此啟動。正式3.12 build流程維持；本機未安裝3.12，不宣稱驗證過它。

Framework真App原生單擊設定→關設定→鈴鐺→專案→機型，加入native active/keyWindow觀測後，四個獨立process皆4/4成功。前三份原始JSON在 `keyboard-fix/native-app-attempt-{3,4,5}.json`。最初未量keyWindow的一輪鈴鐺未收事件；保留此觀察，沒有據此盲改視窗焦點。實驗不是使用者用launcher親手複驗，HF1保持開啟，等待此複驗。

未驗環境：打包App、其他MacOS/Python組合、工廠硬體/KVM影像辨識。此票分支不包含後續HF3～HF7，也沒有關閉任何Issue。
