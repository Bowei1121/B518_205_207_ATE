# macOS Tk 建置異常修正 — 2026-10-12

## 環境與保護

- Checkout：`B518-Log-Solution`，修正前 HEAD `59f28f2`；本機 macOS 26.5.2、Apple Silicon arm64。
- 使用指定 `.venv-macos15_0-arm64-log-solution/bin/python`，Python 3.12.10、Tcl/Tk 8.6.16。
- 先閱讀 AGENTS.md、CONTEXT.md、docs/agents/domain.md 與 ADR 0005／0008。
- 原有 VERSION 已由 0.1.0 改為 0.1.3；未追蹤的 `B518 Log Solution.spec` 均先備份至 `/tmp/b518-tk-diagnosis/`，不納入提交。
- VERSION SHA256：`2d2454ef0edeb462a6ce8b25d387aaa74df08093d5cea0428a10ce55510c6326`。
- spec SHA256：`1c205a379736c9461fb8cc17a958b850ad17a78c43d1075fc2d0cb69d4472a13`。

## 重現與原因

1. 優先執行兩項 Atlas 衝突測試及 `test_close_failure_keeps_window_open_and_real_retry_rebuilds_complete_audit`。各別執行可通過；連續 UI 執行在 `root.update()` 卡住，取得 faulthandler 的 Python 執行緒堆疊與 `/usr/bin/sample` 原生堆疊。主執行緒位於 Tk／Cocoa event update；另有未完成的 close worker 留在 `_coordinate_close`。
2. 可控案例停用自動 GC，建立 App／設定視窗、銷毀 root，再由下一個 worker 明確執行 `gc.collect()`。銷毀後還有 `after#0`，背景 GC 進入 `tkinter.Variable.__del__`，產生 `main thread is not in main loop`，最後 `Tcl_AsyncDelete: async handler deleted by the wrong thread` 與程序中止。見 [worker-gc-before.log](worker-gc-before.log)。
3. 使用 Git 修正前程式的隔離副本，分派 root 銷毀後殘留的 after script，重現 `invalid command name "..._drain_events"`；這項是明確分派殘留腳本的可控重現，不是宣稱單跑 Atlas 每次都會輸出同一錯誤。見 [timer-before.log](timer-before.log)。
4. root.destroy 只銷毀 widget／已註冊 Tcl command；App 沒有管理 timer ID，Tk 變數、字型、圖片、Style、widget 與回呼的 Python 引用也可能留在物件循環中。下一個背景配置／儲存工作觸發 GC 時，舊 interpreter 的物件在 worker 上被回收。
5. 完整套件額外暴露 Apple arm64 `openat` ABI 錯誤：mode 被宣告成第四個固定參數，但它是可變參數；新檔權限實際為 000，導致 App 事件清理後七項讀取失敗。新增原生建立檔案測試先得到 `0 != 384`（預期 0600）。見 [openat-before.log](openat-before.log)。

## 修正

- App 統一擁有 recurring drain、startup notices、close polls 與兩個 after_idle 回呼；執行後移除 ID，root Destroy 時取消全部自有 timer；close cancel／重新 poll 時取消舊 poll。
- Destroy 在建立 Tk 的執行緒上釋放 App 擁有的 Tk 資源圖；晚到的 drain 不再存取失效 UI。所有 StringVar 明確使用 App root 作 master。
- 全域 hotkey 回呼只持有事件佇列；本地 shortcut 綁定 App toplevel，不留下跨 App 的 bind_all 回呼。
- UI fixture 保持一個 Tcl/Tk interpreter，每項測試使用獨立真實 Toplevel；desktop 測試映射視窗，銷毀前完成必要事件處理。仍保留所有原有衝突、重試、稽核、幾何、語言與快捷鍵斷言。
- 追蹤所有測試 coordinator，取消只為測試留下的關閉等待，停止監控並等待 close／archive／retention／monitor workers 收尾；取消測試自身的 timer，最後於主執行緒 GC。未啟動 retention 的 coordinator 可保持 idle，已啟動工作必須完成。
- unraisable、Python Tk callback 與 Tcl bgerror 都使測試失敗，並未吞掉例外。
- `openat.argtypes` 僅宣告前三個固定參數，mode 以 ctypes.c_uint 傳入；保留 descriptor-relative、O_NOFOLLOW 與提交前路徑查核。
- 衝突視窗先為底部操作列保留空間，修正 720×360 時關閉按鈕被 body 擠掉的問題；封存畫面測試明確等待非同步 PASS 顯示。
- macOS15 build gate 明確啟用 `B518_TK_TESTS=1`；生成 spec 放在 build 目錄，來源與 assets 使用絕對路徑。

## 驗證

- 兩項 Tk 生命周期回歸：銷毀後自有 timer 為空、保留 embedding timer；子程序內刻意讓 worker GC 收集 App 循環，確認 root 已釋放、無 unraisable／中止／殘留物件。
- 原生 openat 檔案建立／讀取權限回歸先失敗、修正後通過。
- 本機完整含 Tk 套件：**374 tests，71.342 秒，OK，零跳過**。含照片中的 Atlas、關閉重試、完整 audit rebuild，以及 M10 真實 source integration。完整輸出見 [tests-after.log](tests-after.log)。
- 最終 build：在 `/tmp/b518-tk-diagnosis/build-validation` 隔離副本執行同一份 `scripts/build_macos15_arm64_log_solution.sh`，使用原 venv，原始 VERSION／spec 不改動。**exit 0**，再跑 **374 tests，72.838 秒，OK，零跳過**，PyInstaller、macOS 15.0 arm64 bundle compatibility、ad-hoc codesign verify、ditto ZIP 均完成。見 [build-after.log](build-after.log)。
- 建置版本只在隔離副本由 0.1.3 遞增為 0.1.4；候選 ZIP 複製到專案忽略的 `B518 Log Solution/dist-validation-macos15_0-arm64/`，保留原有 dist 產物。
- ZIP SHA256：`d1db3e7d43bdddd20afe608c03523f94147ab1277ac52ee2d6f7ea13663d3862`。複製後再計算，比對與 build 生成的 checksum 相同。
- 結束前以 cmp 再次確認 VERSION 與 spec 均與最初備份逐位元組相同；只提交程式、測試、build 腳本與本次證據。

## 參考

- [Python 3.12 Tkinter threading model](https://docs.python.org/3.12/library/tkinter.html#threading-model)：Tk interpreter／事件佇列與執行緒生命週期。
- [Python 3.12 ctypes variadic functions](https://docs.python.org/3.12/library/ctypes.html#calling-variadic-functions)：Apple ARM64 的可變參數呼叫慣例與固定 argtypes 宣告。

## 提交與推送狀態

- 程式／測試／build／證據提交：`b1b4c3630051943a94a9279f4f7abd5c19a8b7d7`。提交沒有包含原有 VERSION 修改或 spec。
- 推送前直接查詢發現遠端已前進至 `82c4a133181bc66f8f43bea4a4b098647a558fb0`，新增兩個純文件提交（088caae、82c4a13），與本次程式無重疊。已 fetch 並以 merge `f4bade6cd8371064667e639d8c74ea3abfa14e79` 安全保留它們；程式／tests／build 已驗證內容未變。
- **推送尚未完成**：本機 HTTPS Git 回傳 `could not read Username for https://github.com`；SSH agent 沒有 identity。GitHub 連線可讀取 repository，但建立 blob 的寫入 API 回傳 `403 Resource not accessible by integration`。沒有成功寫入遠端 blob／commit／ref，沒有 force push 或改動遠端設定。
- 等待使用者設定這台 Mac 的 GitHub Git 推送認證，之後執行 `git push origin B518-Log-Solution` 並再次直接確認遠端 SHA。
