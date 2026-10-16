# HF4 桌面驗收紀錄

日期：2026-10-16（Asia/Taipei）

## 前景 App 與人工滑鼠操作

使用者在目標 Mac 前景啟動整合 worktree 的真正 Tk App，分別切換 English 與繁體中文，並以滑鼠各單擊主頁右下方的 `App diagnostics`／`App 診斷` 連結。兩種語言都開啟既有 App 診斷視窗，畫面中同時可見診斷視窗與主頁。原始畫面由使用者提供並複製保存；操作和畫面檢查細節見 [manifest.json](manifest.json)。

啟動命令：

```sh
cd "/private/tmp/B518-hf4-dashboard/B518 Log Solution"
PYTHONPATH=src /Library/Frameworks/Python.framework/Versions/3.8/bin/python3 src/b518_log_solution.py
```

## 畫面核對

- English 主頁顯示 `App events saved`；繁中主頁顯示 `App 事件已保存`。
- 兩語主頁皆可見底部診斷連結；未保存輪次選取／重試、封存摘要／重試及舊主頁 `Retry Text` 控制不再顯示。
- App 診斷視窗能從兩語主頁的滑鼠連結開啟，視窗標題與事件內容跟隨語言切換；App 事件保存狀態完整顯示。
- 固定寬度、KVM 狀態模板、定位標記及結果看板在兩種語言畫面中仍可見。

## 自動驗證

實際 Tk App 測試使用 Framework Python 3.8／Tk 8.6.8。HF4 主測試、工具列與 KVM 幾何、關閉保存失敗重試、通知與恢復中心封存重試、語言刷新失敗／重試及整份 M10 整合測試均通過；`py_compile` 與 `git diff --check` 通過。測試不替代上方記錄的前景滑鼠操作。

## 擷取限制

自動測試程序當時沒有取得 Aqua 前景啟用，Quartz 原生輸入 probe 對設定、鈴鐺、專案、機型皆沒有收到事件（App `active=false`、key window 為 null）。`CGWindowListCreateImage` 雖找到已映射 Tk 視窗，但輸出影像全黑；`screencapture -x /private/tmp/hf4-screen.png` 回報 `could not create image from display 69734272`。這些自動擷取檔不納入證據；本紀錄只採用使用者在前景桌面提供的兩張有效畫面及其明確滑鼠操作回報。

## 證據檔

- [English 主頁與診斷視窗](hf4-english-diagnostics-and-main.png)
- [繁中主頁與診斷視窗](hf4-traditional-chinese-diagnostics-and-main.png)
