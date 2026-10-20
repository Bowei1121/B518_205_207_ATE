# 2026-10-20 macOS 建置異常

## 前次結果與本次基準

2026-10-19 的修正提交 `2f7b75769dc2d07a8c43d639d789da4874c635d2` 已推送 GitHub，當時 513 項測試中 512 通過、1 項既有人工系統外觀案例未執行，arm64 建置成功。當時未宣稱已完成 Intel／產線驗收，也沒有證據認定故障為 M4 特有。

本次使用者拉取後的基準已為 `ce690f4`，新增 Log 儀器狀態、啟動故障復位、逾時輪取消、前景提升及左右定位等功能。不能沿用前版驗證結果代表本版已通過。

## 本次可查證處理

保留使用者既有 VERSION 0.1.4 修改及 untracked spec，備份至 `/tmp/b518-20261020`。使用指定 Python 3.12/Aqua 完整重現 546 項，實際結果為 6 failures、13 errors、3 skips（使用者截圖為 10 failures、13 errors；原生互動存在執行狀態差異）。新增定位框循環及 test timer owner 回歸，先紅再綠；依已接受規格同步故障復位及逾時取消斷言，不改回舊產品狀態。

完整原因、證據及最終驗證見 [診斷報告](evidence/macos-build-2026-10-20/validation.md)。

最終原始 build script exit 0：549 項、193.257 秒，548 通過、1 項既有人工外觀測試未執行，零失敗／錯誤。包括 50K 資料、所有自動 Tk、原生互動、雙縮放、復位與關閉回歸。macOS 15.0 arm64 相容性、簽章及 ZIP 打包成功；產品 src 與打包副本相同。最後僅調整 LI7 測試證據預設輸出位置，專項矩陣再通過，原 VERSION/spec 保持原樣。準備依 AGENTS 規則提交推送修正及證據。


## Terminal 原生輸入權限與測試收尾補充

使用者確認 Terminal 原生輸入權限由 post=False/listen=False 變為 True/True。新增建置前唯讀事件投遞權限檢查及兩項回歸測試；修正取消後新輪測試未等待背景保存便刪除暫存目錄的競態。隔離原建置腳本 exit 0，Python 3.12.10 完整 551 項測試、550 通過、1 項既有人工外觀驗收未執行（193.962 秒）；相容性、簽章與 ZIP 均完成。原 VERSION/spec 保留。使用者 Terminal 重跑仍待回報。詳見 [驗證紀錄](evidence/macos-native-input-2026-10-20/validation.md)。

---

## 本機開發環境與驗證紀錄（同步時保留）

以下完整保留本機先前未提交摘要；其中HEAD、測試及環境描述是各次紀錄當時的狀況，不代表本次同步後仍停在舊版本。GitHub建置主機的驗證與本機Intel／背景工作階段的Tk初始化失敗分開記錄，兩者不能互相取代。

# 專案摘要 — 2026-10-20

## 前次可查證結果

- 依 2026-10-19 摘要及 evidence/macos-build-2026-10-19/validation.md，曾在 Python 3.12.10 與真實 Aqua 桌面修正 Tcl command 重複刪除、interpreter 保留與原生選單／輸入測試同步問題。當次原打包腳本執行 513 項測試，512 通過、1 項人工外觀切換測試跳過，完成 macOS 15.0 arm64 bundle 檢查及打包。這是歷史驗證，不代表本日版本已重新驗收。
- 昨日另有儀器狀態契約 1.2 規格及 LI1～LI8 票務、手冊更新；詳細結論以 PROJECT_SUMMARY_2026-10-19.md 及所連結規格為準，本次未重新驗收這些功能。

## 本日環境討論

- 使用者提供：目標 M4／macOS 15.0；打包 M4／macOS 26.5／Python 3.12.10，pull 後常在打包測試失敗。本次尚無該次錯誤輸出，不能認定根因。
- 本機預設 python3 實測為 3.8.10。Log Solution 的 macOS 15 打包腳本則指定 Python 3.12、檢查原生 arm64 與 Tk，使用 .venv-macos15_0-arm64-log-solution，並設定 B518_TK_TESTS=1 執行測試。
- 多個桌面測試在未設定 B518_TK_TESTS=1 時會跳過，因此預設 Python 測試成功不能取代打包環境驗收。
- macOS 26 專用腳本設定最低版本 26.0，不適用於交付 macOS 15.0；macOS 15 腳本設定 15.0 並檢查 bundle。新系統建置及靜態檢查成功仍需 macOS 15 實機驗收。
- 建議以相同 Python 3.12.10、相同相依套件及 Tk 桌面測試作為開發／打包共同門檻；git pull 不會同步虛擬環境或已安裝套件。
- 本次程式版本檢視僅唯讀查核，沒有修改產品原始碼；先前新增每日摘要後，使用者要求在這台開發機安裝並切換 Python 3.12.10，以下記錄實際完成情形。

## Python 3.12.10 開發環境

- 當前 Codex 開發機實測為 Intel `x86_64`、macOS 15.8.1，不是使用者描述的 M4／macOS 26.5 打包機。
- 由 Python.org 安裝 Python 3.12.10 universal2（官方 MD5 一致，Sigstore signer `thomas@python.org` 驗證通過）。macOS Installer 由使用者完成管理員授權。
- 安裝後 `/usr/local/bin/python3` 與 Python.org Framework `Current` 指向 Python 3.12.10；Python 3.8 仍可由明確路徑呼叫。
- 專案內建立被 `.gitignore` 忽略的 `.venv-python31210`，並安裝 `requirements-macos15-arm64.txt` 所列的 PyInstaller 6.16.0、PyObjC 11.1 及 Quartz 11.1。版本、Tk 8.6、PyObjC／Quartz／PyInstaller 匯入及 `pip check` 均通過。
- `scripts/check_macos_build_python.py --architecture x86_64` 通過。這台 Intel 主機無法通過 M4 arm64 建置檢查，也不代表 arm64 產物已驗證。
- `B518_TK_TESTS=1 .venv-python31210/bin/python -X faulthandler scripts/run_tests.py` 在 `test_li6_foreground` 發生 Python/Tk 程序中止；未取得完整測試總結。未設 `B518_TK_TESTS` 的完整測試亦以 exit 134 中止（當時輸出至 log monitoring 測試，無 unittest 完整總結）。不宣稱完整測試通過。第二次測試紀錄暫存於 `/private/tmp/b518-py31210-default-tests-rerun.log`。
- 本機 Git HEAD 仍為 `ce690f4`，不含 GitHub 的 `2f0998`；故以上測試是在目前本機 checkout 執行，不能代表 `2f0998` 的驗證。

## GitHub `2f0998` 修正版的 Python 3.12.10 驗證

- 以 Python 3.12.10 專案 venv 在 `/private/tmp` 的隔離副本測試完整 commit `2f0998887aa188ed71fadcea25dcb86314988894`，未更動目前 checkout 或產品原始碼。
- `B518_TK_TESTS=1` 的完整測試在 `test_li6_foreground` 建立 `tkinter.Tk()` 時以 exit 134 發生 Python fatal abort；無 unittest 完整摘要。紀錄：`/private/tmp/b518-py31210-2f0998.log`。
- 未設定 `B518_TK_TESTS` 的完整測試也在 `test_log_solution_ui.py` 的 `setUpClass` 建立 Tk root 時 exit 134；排除該模組後，`test_slot_toolbar_st1.py` 仍會初始化同一 UI 測試類別並觸發 abort。紀錄：`/private/tmp/b518-py31210-2f0998-nogui.log`、`/private/tmp/b518-py31210-2f0998-nonui.log`。
- 因此此主機未能完成 `2f0998` 的完整測試。失敗位置是 macOS Tk root 初始化；目前無證據能判定是 Python 3.12 相容性、GUI session，或測試本身的問題。需要在可建立 Aqua/Tk 視窗的桌面工作階段重跑。

## Python Crash Reporter（10:09）

- 使用者提供的畫面與 `/Users/tsengbowei/Library/Logs/DiagnosticReports/Python-2026-10-20-100936.ips` 相符：Python 3.12.10 PID 90370，父程序 `codex` PID 32560，report 時間 10:09:36；是本次 Codex 啟動測試所觸發，不是已打包的 B518 app。截圖時間 10:09:48。
- 崩潰堆疊為 `TkMacOSXDisplayChanged → TkpOpenDisplay → AppKit 螢幕設定 → HIServices _RegisterApplication → abort()`；對應 `test_li6_foreground.py` 在主執行緒呼叫 `tk.Tk()`。10:14、10:16 的重跑報告也是同一原生堆疊，分別出自 `zsh` 子程序。非 GUI Tk 原始碼測試未能建立 root。
- Tcl/Tk 載入本身正常：Python 3.12.10／3.8.10 均回報 Tcl/Tk 8.6；目前測試環境未設 `PYTHON*`、`TCL*`、`TK*`、`DYLD*` 或 `DISPLAY` 覆寫。已證實的是 Tk/Aqua 建立視窗時 AppKit 主執行緒 abort；Python 3.12 是否為根因仍未證實。需在可用的互動式 Aqua 桌面執行 Tk root 驗證，與 Codex 背景 shell 結果對照。


## 架構訪談與雙遠端同步

- 使用者A1～A16已確認歷史查詢／開始流程優化、監控經過時間、半秒16態獨立心跳、固定計時顯示區及Python3.12.10共同基準；App與Claude橋接規格、ADR0012已提交於7cc434a，尚未實作新功能。
- 使用者要求先核對版本再同步GitHub與Gitea。讀取遠端時，本機7cc434a、GitHub工作分支2f09988、Gitea工作分支5b14451；兩端main均為5acfb2e，本輪不修改main。
- 正常合併GitHub2f09988的Tk修正與本機規格；本機原未追蹤摘要先逐位元備份，再與GitHub摘要一併保存。產品程式應與GitHub2f09988一致，不重寫遠端歷史。
- 相關驗證與雙遠端最終提交，以同步完成紀錄及Git遠端分支查核為準。

### 合併後本機驗證

- Python3.12.10執行test_historical_event_query、test_monitoring_round、test_round_retention、test_round_start_preparation：173項、39.822秒，全部通過。紀錄：`/private/tmp/b518-sync-tests-20261020.log`。本次沒有重跑Tk桌面測試或arm64打包；遠端的549項建置證據屬其原建置環境。
- 合併後全部src的AST語法檢查通過；`git diff --exit-code github/B518-Log-Solution -- "B518 Log Solution"`無差異，證明產品目錄與抓取的GitHub2f09988完全一致。
- 文件相對連結與空白檢查通過；原遠端摘要及本機備份摘要在整合檔中均逐字保留。GitHub與Gitea工作分支會以正常快轉推送至同一個合併提交，不改main、不force push。


## to-spec 正式規格發布

- 依使用者指定to-spec技能，將當日架構／顯示討論整理為七章正式規格，直接更新既有App改善規格，不另外建立競爭版本。
- 規格包含52個使用情境、19組驗收情境；使用者已確認三個高層測試入口。保留原始訪談與Claude交接稿；未量測的幾何不冒充定案值，橋接實作與恢復策略仍由Claude工作接續。
- 發布至[GitHub Issue #86](https://github.com/Bowei1121/B518_205_207_ATE/issues/86)，套用ready-for-agent；本機文件與議題對照記錄於原始討論。
- 本次僅修改文件；檢查模板章節、需求覆蓋、檔案連結、文字格式及遠端議題正文／標籤，不重跑無關的產品測試，也不宣稱新增功能已驗收。

### to-spec發布後同步補充

- 同步前查得GitHub工作分支新增0595522（含493328c原生輸入權限檢查與測試收尾修正），先正常合併，保留遠端新增摘要及本機規格。產品目錄與0595522相同，本次自行撰寫的變更仍只有文件。
- 為驗證新整合的遠端修正，另跑原生輸入權限檢查與監控輪次兩個測試模組：70項、6.430秒全部通過；不建立Tk視窗、不宣稱新計時／心跳功能或跨專案配對驗收已通過。
- 已讀回Issue86核對OPEN、ready-for-agent，正文與本機正式規格一致。


## to-tickets 開發票發布

- 使用者已核准八票拆法；依序建立LS1～LS8（GitHub #87～#94），套用ready-for-agent，並設為父規格#86的原生子議題。
- 7條原生Blocked by：#90←#88、#91←#90、#93←#91／#92、#94←#87／#89／#93。起始可認領#87、#88、#89、#92。
- 原始52個使用情境與19組驗收情境已對照至各票，逐票完整內容及機器可讀編號對照保存在[開發票總覽](log-solution-improvement-tickets-2026-10-20/README.md)。橋接程式仍由Claude另案實作。
- 發布後讀回各票確認正文、標籤及父子／阻擋關係，父規格正文、標題、狀態、標籤及留言保持不變；本次只處理票務與文件，不重跑產品測試、不宣稱功能已實作。
