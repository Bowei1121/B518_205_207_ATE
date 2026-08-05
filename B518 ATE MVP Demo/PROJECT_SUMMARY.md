# B518 ATE MVP Demo — 專案摘要

最後更新：2026-08-05（Asia/Taipei）

## 專案目的

Atlas Agent 透過 Arduino UNO R4 的 USB CDC 接收工作指令，並以 Arduino USB HID 執行測試 HMI 的鍵盤、滑鼠與截圖操作。支援 DFU、FCT、BT；上位機使用 TCP 與 CRLF 交換 JOB、ACK、RESULT。

## 目前測試／Demo 架構

- 開發用 B482 模擬 HMI：`b482_demo_server.py` + `b482_demo_hmi.html`，開啟 `http://127.0.0.1:8080`。
- Agent 支援手動條碼與 Demo slot 視窗：DFU 7 格、FCT 6 格、BT 4 格；正式上位機協定維持最多 4 slot。
- BT 以 `TestData/YYYY-MM-DD/PASSED|FAILED/*.csv` 監聽結果；Thread0～3 對應 slot1～4。
- 現場可在 FCT／BT Demo 視窗啟動「無 SN Log Demo」：以按鈕時間與啟動前檔案基準排除舊資料，從新 Log 自動取得 SN 與結果，只顯示、不回傳 TCP RESULT。FCT 顯示「檢出 N」，BT 顯示實體 slot。
- 正式 DFU／BT／FCT checkbox 畫面定位會暫時隱藏 Agent 視窗；路徑選擇器會顯示隱藏資料夾（例如 `/vault`）。
- 現場 OS：BT 為 macOS Mojave 10.14.5；DFU／FCT 為 Catalina 10.15。共用候選 App 需在 Intel Catalina VM 以 10.14 deployment target 建置，並經兩種 OS 實機驗收。

## USB CDC／HID 現況

- USB CDC 本地控制命令使用 LF；TCP JOB／ACK／RESULT 保留 CRLF。
- `ERR:TCP_NOT_CONNECTED` 是 TCP bridge 診斷，不能視為本地 HID 指令失敗。
- 每次 HID 命令前會清除 App 端舊事件並 flush serial output；接收執行緒是唯一 serial reader，避免搶走第一筆回覆。
- 最新韌體版本為 **1.0.4**：`M_RESET`、`M_DELTA`、`M_MOVE` 先回 `ACK`、HID 函式返回後回 `OK`。舊版 macOS 仍需實機驗證滑鼠相對位移與 M_RESET 是否能回 `OK`。
- 若見 `ACK:M_RESET` 但沒有 `OK:M_RESET`，代表 CDC 指令已送達、問題在滑鼠 HID 執行／舊 OS 接受 report 的路徑；若完全無 ACK，則先查 CDC 傳輸或命令 framing。

## 最近提交

- `7d1e5aa fix: diagnose legacy mouse HID stalls`：韌體 1.0.4、舊 macOS 的較保守 mouse report 節奏、HID ACK 診斷與移除收訊鎖定造成的 UI 延遲。
- 下一筆提交：無 SN Log Demo、即時 SN／結果表、正式辨識時隱藏 Agent 視窗、原生隱藏路徑選擇器。

## Git 與交付規則

- Remote：`origin` → `http://10.64.76.34:3000/8362/B518-205_207_ATE.git`
- 每次程式修改完成後，必須自動 commit 並 push 至 `origin/main`。
- `release-hid-calibration/` 是本機打包輸出，不納入 Git。
