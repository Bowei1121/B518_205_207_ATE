# 2026-10-19 macOS arm64 build 診斷

## 環境與重現

基準 `6fb5b75`；本機 `.venv-macos15_0-arm64-log-solution/bin/python`（3.12.10）、真實 Aqua 桌面。執行 `B518_TK_TESTS=1 .../python -X faulthandler scripts/run_tests.py test_m10_tk_lifecycle test_m10_integration`，7 項中 2 項失敗，包含截圖相同的關閉回呼錯誤與 interpreter 未釋放（`m10-before.log`）。沒有以截圖中的最後一項錯誤代表全部根因。

## 原因與修正

1. `_LocalizedControlHint` 透過 button.bind_all 註冊的回呼，實際由 Tk root 擁有。原清理由 button.deletecommand 刪除 Tcl command，但未移除 root._tclCommands 中的登記，root.destroy 再刪一次即失敗。改由同一 root owner 刪除，保留其他 hint 的全域回呼。新測試覆蓋 hint.close 與 button.destroy 兩條路徑及其他 hint 不受影響。原版紅燈見 `hint-red.log`；M10 修正後 8 項全過見 `m10-after.log`。
2. ST4 新增的提示字典以 widget 當鍵。原 `_on_root_destroy` 只清理字典值，鍵持有 interpreter，之後 worker GC 有錯執行緒刪除風險。將鍵也納入同一 Tk resource release；既有 subprocess 回歸從「Destroyed interpreter is still retained」轉為通過，見 `remaining-failures.log`、`remaining-after.log`。不靠 gc monkeypatch 或吞掉 destructor 例外。
3. 數個語言切換測試先合成 ButtonPress 開原生 Menu，再在下一行 invoke 項目；Aqua popup 是同步 modal loop，下一行不能執行。`hang-sample.txt` 保留主執行緒 AppKit NSMenuTrackingSession/TkpPostMenu 堆疊；此輪被中斷後不算通過。語言/保存/閱讀位置測試改呼叫真實 Menu.invoke，保持所有語言、稽核及捲動斷言；原本專項 Quartz 原生滑鼠/鍵盤頂列測試不變。
4. HM1 測試銷毀 scratch 視窗後先恢復主窗與按鈕焦點，再產生 Enter，以驗證實際可見提示及 destroy 清理，未移除提示斷言。

## 保護與驗證方式

VERSION 與未追蹤 spec 在 `/tmp/b518-20261019` 保存原件；建置在獨立 `/tmp/b518-20261019/build-validation` 執行原腳本，使用相同 venv 及相同程式碼，避免自動版本遞增或產物清理影響原目錄。包含 `/tmp/b518-hmi-20261016/capacity-50k` 的 50K 資料測試。既有要求使用者手動切換系統 Light/Dark 的測試需人工執行，不能冒稱自動驗證。

## 原生輸入回歸的後續診斷

- 原生游標讀回證實事件已送達、Python 在前景、輸入事件權限可用，但 Aqua 在停用 ttk 控制項及原生 view 顯隱後可能不傳 Enter/Motion 至 Tk。新增 100ms Tk 主執行緒游標追蹤，僅在實際命中可見控制項時排程提示；保持合成 Enter 與真實游標狀態分開，並在 close/destroy 取消 timer。新回歸測試也檢查該 timer 已取消；沒有增加背景 Tk 操作。
- 原生 Menu 測試改依目標索引導航（Home、必要次數 Down、Return），將按鍵送至系統 HID queue 並等待語言變更完成，避免只做一次 update 就在非同步事件完成前斷言。原生 keyboard/mouse 測試保留，未以 Menu.invoke 代替此專項驗收。
- ST5 原生 hover helper 原先等待任一 tooltip 存在，就可能讀取上一個控制項的提示。改等待 `_visible_hint` 實際屬於目前 widget、已顯示；原生 click 留出事件投遞時間，Tab 前先確認來源焦點。
- Quartz 視窗堆疊及 Tk 命中讀回證實：兩個最小高度視窗超過 900px 桌面的可用範圍，Aqua 將警報窗夾回後遮住衝突按鈕。測試將視窗依目標操作區排列，保持原有中英文提示、資料不變、焦點、按壓取消、關閉及人工裁決斷言；未改產品視窗尺寸。
- ST5 真實互動案例修正後完整通過（8.714 秒），見 `conflict-native-green.log`；完整自動回歸仍由原 build script 判定，不能以此單項成功代替。

- 自動 Tk 測試使用共用 interpreter，各 App 是真實 Toplevel；原生測試遺留的實際游標會命中下一個新 App，干擾合成 Enter/Focus。每個案例開始先將實際游標置於中立區（手動 hover 模式除外），整個測試類別結束恢復原位置。完整保留原生輸入與提示存在性斷言。五個相關原生／提示測試合併執行 26.379 秒全通過（`native-combined-green.log`）。

- 全套重跑另暴露選單送鍵的固定延遲競態：worker 可能在原生 popup 開始前已送鍵。以事件觀察真正 `tk_popup` 進入及返回，worker 等待 popup 進入再送鍵；主執行緒等待真實返回／語言變更，不以等待時間視為成功。`full-menu-race-red.log` 保留 513 項中僅此項失敗的紀錄，`menu-synchronized.log` 為同步修正後原生案例通過。

## 最終結果

在獨立副本執行未修改的 `scripts/build_macos15_arm64_log_solution.sh`，設定 `B518_H8_CAPACITY_ROOT=/tmp/b518-hmi-20261016/capacity-50k`；腳本自身啟用 `B518_TK_TESTS=1`。513 項測試、184.950 秒，**512 通過，1 項既有人工系統外觀切換測試未執行，零失敗／零錯誤**。所有自動 Tk、M10、50K 容量、原生滑鼠/鍵盤及關閉重試測試通過。`build-green.log` 無 Tk callback、invalid command 或 unraisable 例外。

PyInstaller 打包、macOS 15.0 arm64 bundle 相容性檢查、codesign deep strict 驗證及 ZIP 產生全部成功，腳本 exit 0。獨立副本 VERSION 由 0.1.4 遞增至 0.1.5；原目錄 VERSION 和未追蹤 spec 均與原備份 cmp 相同，未提交或覆蓋。

產物：`B518 Log Solution/dist-validation-20261019-macos15_0-arm64/B518-Log-Solution-V0.1.5-macOS15.0-arm64.zip`（ignored）。SHA-256：`5dc7903f53abbeb79add6f6876ff095defed05590011a7c9e3df80369c0e8f6c`。

驗證用 src 與兩個修改測試檔皆與原目錄逐位元比對一致；`git diff --check` 通過。此次未在 Intel 硬體或產線 KVM 上重跑，亦不宣稱已完成需人工切換系統外觀的驗收。
