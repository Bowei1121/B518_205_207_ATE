# 2026-10-20 macOS arm64 建置診斷

## 基準與重現

主線 `B518-Log-Solution` 基準 `ce690f4`。使用 `.venv-macos15_0-arm64-log-solution/bin/python`（Python 3.12.10）及真實 Aqua 桌面，執行 `B518_TK_TESTS=1 .../python -X faulthandler scripts/run_tests.py`。546 項、147.140 秒：6 failures、13 errors、3 skips，完整輸出見 `before.log`。截圖的原生互動失敗數為 10，故只宣稱重現實際紀錄中的案例與同類清理連鎖故障。

## 原因及有效回歸

1. **新增定位框的循環參考**：`marker.white_cell -> child.master -> marker` 形成純 Python widget cycle，destroy 後仍持有祖先 Tk。`lifecycle-owner-chain.log` 在關閉後找到 Frame 鏈與定位框互相參照。Tk 本來已透過 children 持有子框，將便利屬性 white_cell 改為 weakref.proxy，保持繪製與擷取 API。新增 `test_destroyed_locator_releases_widget_graph_without_collection` 在停用自動 GC 下驗證所有弱參照釋放；未修正前失敗，修正後通過，既有 worker-GC 子程序亦通過。
2. **測試收尾取消 timer 的 owner 錯誤**：test fixture 用 desktop root.after_cancel 刪除由子 widget 註冊的 command，留下子 widget._tclCommands 的舊登記；destroy 再刪除而拋出 TclError，後續 M10/ST1 又命中已污染的 default interpreter，出現 pyimage 不存在。先建立 owner map，再透過實際註冊 widget 取消；raw Tcl timer 僅取消排程。新增 nested-widget timer 清理回歸在舊 fixture 重現雙重刪除，修正後通過。App 的 PhotoImage／nametofont 亦明確使用傳入的 root，避免誤用預設 interpreter。新增兩項紅燈見 `new-red.log`，綠燈見 `lifecycle-green.log`。
3. **舊狀態期待未跟上已接受規格**：LI3 要求接受前故障亦持續 REVIEW，必須人工復位；舊測試仍期待 None／開始按鈕立即可用。依 CONTEXT／ADR0010／LI3 完成紀錄更新測試：要求故障 request、原始診斷、不可交付及開始鎖定，重複開始不得換 request，明確按復位後才解除；接受後失敗必須保留取消輪次。LI5 的逾時警報確認與本輪取消分開；badge 測試先證明直接新輪被拒，再明確取消，仍保留失敗保存、多位數 badge、重試及通知清除斷言。五項集中驗證通過（`contracts-after.log`）。未放寬產品的故障／交付／關閉門檻。
4. **畫面測試隱含環境與原生更新競態**：LI7 強制讀取未設定的 B518_TK_EVIDENCE_DIR；改為此測試自有暫存輸出，若使用者指定仍優先採用。保留真實 NSView 擷取與 2× 像素比例斷言。共用 interpreter 的 scaling 在測試結束還原並驗證。另等到原生 contentView 大小與 Tk 大小真正一致再擷取，避免 2.758 倍等由舊 frame/新幾何混算的假失敗。
5. **背景測試尚未完成工作便收尾**：ControlledConflictMonitor 先更新 PASS，再同步回呼記錄來源證據；主測試僅等 PASS 即送 candidate，可能在證據尚未完成時得到 ignore。改等公開 source_ready 與另一位置 TESTING，再保留所有 defer／衝突裁決斷言。復位測試新建後續輪次後須等待 close 完成，及重啟後 App store.flush 完成，才 stop／刪除暫存目錄；不忽略 Directory not empty、不增加刪除重試。這些情境的紅燈與綠燈見 `settling-red.log`、`settling-after.log`。

## 驗證與保護方式

原 VERSION 與 spec 在 `/tmp/b518-20261020` 備份。打包在獨立 `/tmp/b518-20261020/build-validation` 副本執行原 build script，使用同一 venv，並啟用既有 50K capacity fixture；不刪除或覆寫使用者 spec，也不讓自動版本遞增影響原目錄。未修改 build 門檻、未 skip 失敗測試、未吞掉 Tk/background 例外。既有人工 Light/Dark 互動案例仍屬人工驗收，不能宣稱自動通過。

### 同名原生視窗的批次回歸

完整順序下仍有原生窗口大小與 Tk 不一致的紀錄。進一步列出 AppKit 視窗，證明同時存在兩個同名 HMI，一個 contentView 為 376×855，當次 Tk 視窗對應另一個 376×620；單靠 title 會擷取前者。`native-window-ambiguity-red.log` 保存視窗編號、位置與大小清單，不能把此案例誤歸為尚未等夠的 resize。

擷取 helper 在取得 NSWindow 時短暫使用當次 Tk window ID 的唯一 title，取得物件後立即以 finally 恢復原 title；畫面擷取與 metadata 保留產品原標題，Quartz 以該 NSWindow.windowNumber 比對而非重複的 title。仍要求 native 與 Tk 尺寸一致及原有 2× 像素比例，不接受舊視窗影像。

新增兩個同名、不同大小的真實 Tk/NSView 回歸，僅固定 AppKit 枚舉順序以穩定模擬已觀察到的舊窗在前情境，未模擬畫面。舊 helper 為 220×150 vs 320×210 失敗（`native-title-red.log`），修正後通過（`native-title-green.log`）。原失敗之前的 42 項 UI 測試依原順序重跑，36.974 秒全部通過（`native-prefix-green.log`）。

隔離建置曾漏帶新版測試讀取的儲存庫根 docs，產生兩個 FileNotFoundError；已補齊根 docs 的實際副本。該輪不計為通過，也不將驗證副本缺件誤認為產品錯誤。

## 最終驗證結果

- 執行原 `scripts/build_macos15_arm64_log_solution.sh`，僅提供 `B518_H8_CAPACITY_ROOT=/tmp/b518-hmi-20261016/capacity-50k`，腳本自行啟用真實 Tk 測試。
- **549 項、193.257 秒：548 通過，1 項既有需人工切換系統 Light/Dark 的案例未執行；零 failures、零 errors。** 50K 容量及全部自動 Tk／原生輸入／M10／復位／關閉測試實際執行。`build-green.log` 無背景 thread／Tk callback／invalid command／unraisable 例外。
- PyInstaller bundle、macOS 15.0 arm64 相容性檢查、codesign deep strict 驗證及 ZIP 全部成功，腳本 exit 0。
- 完整建置後最後僅將 LI7 預設 JSON／PNG 證據目錄統一放進 fixture 暫存目錄，避免無環境變數時遺留 root JSON；專項重跑完整雙縮放矩陣 1.848 秒通過（`artifact-output-after.log`），原產品程式無後續變動。先前本次測試產生的 root JSON 移存 `/tmp/b518-20261020/earlier-root-artifacts`，沒有刪除既有使用者檔案。
- 已驗證打包 src 與原目錄修改 src 位元相同；原 VERSION 0.1.4 修改及 untracked spec 皆與開始前備份 cmp 相同。隔離副本自行遞增為 0.1.5，原檔不納入提交。
- 產物保存在 ignored `B518 Log Solution/dist-validation-20261020-macos15_0-arm64/B518-Log-Solution-V0.1.5-macOS15.0-arm64.zip`；SHA-256 `1b58c44c2228ed7358506ace16e9e8a4e55aefcc7a0fdc524da9e0d5d7b25011`。
- `git diff --check` 及四檔 py_compile 通過。未在 Intel／其他 macOS 版本／產線 KVM 重跑，亦未宣稱人工外觀驗收完成。
