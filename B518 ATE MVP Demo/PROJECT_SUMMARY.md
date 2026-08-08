# B518 ATE MVP Demo — 專案摘要

最後更新：2026-08-08（Asia/Taipei）

## 專案目的

Atlas Agent 透過 Arduino UNO R4 的 USB CDC 接收工作指令，並以 Arduino USB HID 執行測試 HMI 的鍵盤、滑鼠與截圖操作。支援 DFU、FCT、BT；上位機使用 TCP 與 CRLF 交換 JOB、ACK、RESULT。

## 目前測試／Demo 架構

- 開發用 B482 模擬 HMI：`b482_demo_server.py` + `b482_demo_hmi.html`，開啟 `http://127.0.0.1:8080`。
- Agent 支援手動條碼與 Demo slot 視窗：DFU 7 格、FCT 6 格、BT 4 格；正式上位機協定維持最多 4 slot。
- BT 以 `TestData/YYYY-MM-DD/PASSED|FAILED/*.csv` 監聽結果；Thread0～3 對應 slot1～4。
- 現場可在 FCT／BT Demo 視窗啟動「無 SN Log Demo」：以按鈕時間與啟動前檔案基準排除舊資料，從新 Log 自動取得 SN 與結果，只顯示、不回傳 TCP RESULT。FCT 顯示「檢出 N」，BT 顯示實體 slot。
- 正式 DFU／BT 影像定位會暫時隱藏 Agent 視窗；FCT 不執行截圖或 HID，直接監聽 CSV。路徑選擇器會顯示隱藏資料夾（例如 `/vault`）。
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

## 2026-08-06 DFU 現場流程確認

- FAE 現場確認七槽 DFU 的真實操作是：每筆 SN 輸入後按 Enter 搬入下一個已勾選 slot；所有 SN
  完成後，僅按一次 OK 以開始 ATE 測試。
- 新增獨立 `b482_dfu2_7slot` Profile，保留既有四槽 `b482_dfu2`。七槽的 group0 先重設全部
  slot，再套用本次選擇並截圖驗證；不通過時不會輸入 SN 或點 OK。
- 七槽 checkbox 以 group0／slot 文字做位置錨點，在相鄰小範圍辨識 checked／unchecked，減少
  模板數量並避開上方結果表格。
- HTML 模擬 HMI 提供四槽／七槽切換，預設七槽現場流程。

## 2026-08-06 DFU 七槽 checkbox 穩定化

- 七槽 group0／slot checkbox 改用焦點不敏感的灰階邊緣辨識，checked／unchecked 模板會自動裁切主體並允許不同外框尺寸。
- 當時版本的稀疏 slot 曾由 group0 重設後再選取；此作法已於 2026-08-08 取消，現行版本改為逐一比對並切換 slot。
- 複驗成功後以最後一張尚未刪除的截圖重新定位 SN 輸入框與 OK，逐筆送出 SN＋Enter，最後只點一次 OK。
- checkbox 模糊時記錄 group0、slot1～7 的 checked／unchecked 分數；任何啟動錯誤在主 HMI 顯示 START_FAILED，本機 Demo 不送 TCP NACK。
- 修正 label-relative ROI 過窄的回歸：slot 搜尋寬度改由同排相鄰錨點間距計算，涵蓋卡片右端 checkbox；以 2026-08-06 現場截圖重算後 checked 分數由 0.20 提升至 0.92～1.00。

## 2026-08-06 FCT 改為儀器自動偵測 slot

- FCT 正式 JOB、稀疏 slot、已知 SN Demo 與六槽 Demo 都直接依 SN 監聽 CSV；Agent 不再截圖、定位視窗、辨識 checkbox 或發送 HID 點擊。
- `auto_slot_sync` 偏好欄位保留相容性，但設定名稱改為「自動同步 DFU Slot 勾選」，只影響 DFU。
- FCT 不需要 `fct_window`、checked 或 unchecked 模板；HTML 模擬 HMI 仍保留人工 checkbox，Fixture Insert 只測試已勾選且有 SN 的項目。

## 2026-08-06 DFU 首次視窗焦點座標修正

- 修正 absolute HID 模式仍以 `M_RESET + M_MOVE` 將螢幕座標當相對距離的問題；長距離相對移動會受 macOS 滑鼠加速度影響而衝過定位點。
- absolute 模式改為先用 `M_ABS` 精準定位，再由標準相對滑鼠做一單位往返後送出左鍵，避免切換 HID pointer interface 時遺失焦點點擊。
- relative 模式保留原有回左上角再移動的行為；Log 會同時列出截圖、logical 與 HID 焦點座標，方便現場比對。
- 七槽重新截圖會先分流多螢幕候選：其他螢幕缺少 `dfu7_window` 不再掩蓋正確 DFU 螢幕的 checkbox 錯誤；checkbox 暫時不明確時會自動重新截圖一次。

## 2026-08-07 Focused checkbox 模板擷取

- 現場確認測試 HMI 未聚焦時 checked checkbox 為白底黑勾，聚焦後則可能成為藍／綠底白勾；兩種外觀直接混用會降低模板相似度。
- 模板製作改採人工聚焦倒數：擷取前先顯示確認提醒，Atlas Agent 隱藏後保留 5 秒，操作人員須手動點擊測試 HMI 的標題列或空白安全區，之後 Arduino 才送出截圖快捷鍵。
- 模板頁常駐顯示人工聚焦提醒，並警告不可點擊 checkbox；checked／unchecked 必須取自相同聚焦狀態與相同裁切範圍。
- 此變更只影響模板製作用的「擷取螢幕截圖」；正式測試流程、選擇既有截圖及使用最新截圖均不變。
- 模板放大預覽會依螢幕尺寸限制畫布高度，預留底部取消／儲存操作區，避免按鈕超出 1440×900 等較矮螢幕。

## 2026-08-07 現場 active Log 與 DFU Dock 聚焦

- FCT 測試開始時會先在 `Logs/Atlas/active/group0-slotN` 建立暫存資料夾，持續更新測試步驟與 `device.log`，完成後刪除 active 資料，再將最終結果搬到 `Logs/Atlas/unitest/<SN>/<timestamp>/system/records.csv`。
- 無 SN FCT Demo 改為雙階段：active 出現即在結果面板顯示 `slotN`、SN（若 Log 已讀出）與 `TESTING`；active 消失時顯示 `COMPLETING`；只有 unitest 的完整 `records.csv` 才更新最終 PASS／FAIL。60 秒無活動時顯示 `STALLED`，但繼續等候直到既有逾時或人工停止。
- 七槽 DFU 不再把小型 `dfu7_window` 模板的中心當作點擊座標，也不會在取得 HMI 焦點前讀 checkbox。現在可選擇製作 `b482/dfu7_dock_icon.png`，優先點擊 Dock 中已固定的 Atlas 圖示；未提供時改點擊 slot1 文字安全錨點，再重新截圖判讀聚焦後的 checkbox。

## 2026-08-08 本次改動統整

- 本次修改已提交至本機 Git：`32d5c86 feat: improve DFU focus and FCT active log demo`；依目前指示暫不推送 remote，待回公司內網後再處理。
- DFU 七槽聚焦優先使用可選 Dock Atlas 圖示模板，降低小型視窗模板中心偏移造成的誤點；沒有 Dock 模板時維持 slot1 文字錨點的安全 fallback。
- FCT 無 SN Demo 已可使用 active／unitest 兩階段 Log 顯示即時進度、停滯與最終結果，避免只靠固定逾時時間等待。

## 2026-08-08 DFU 七槽取消 group0 快捷同步

- 七槽 DFU 自動同步不再辨識、點擊或驗證 group0 checkbox，避免 group0 外觀、狀態不一致或誤判中斷流程。
- 第一張聚焦後截圖讀取 slot1～7 的實際 checkbox 狀態；只逐一切換與本次 JOB／Demo 所需狀態不符的 slot。
- 第二張截圖是唯一複驗依據；若仍與需求不符則停止流程，不輸入 SN、不點擊 OK。group0 文字模板僅保留作為下方 slot 區的版面定位標記。

## Git 與交付規則

### Remote 設定

本專案同時推送至**公司內網 Gitea** 與 **GitHub**：

| Remote 名稱 | 用途 | URL |
|---|---|---|
| `origin` (fetch) | 公司內網 Gitea | `http://10.64.76.34:3000/8362/B518-205_207_ATE.git` |
| `origin` (push) | 公司內網 Gitea + GitHub（**雙推送**） | 見下方說明 |
| `github` | 僅推送 GitHub（外網備用） | `git@github.com:Bowei1121/B518_205_207_ATE.git` |

`origin` 已設定雙 push URL，執行一次 `git push origin main` 即同時推送兩個平台。
在外網時公司 Gitea 那條會失敗（內網 IP），但 GitHub 仍會成功，兩條互不影響。

### 日常推送指令

```bash
# 一次推送到公司 Gitea + GitHub（建議）
git push origin main

# 只推 GitHub（外網、公司內網斷線時）
git push github main
```

### 外網打包虛擬機（macOS 10.15）：從 GitHub 取得程式碼

公司 Gitea 是內網，外網打包時改由 GitHub 取得程式碼。

**情況 A：虛擬機上尚未 clone（全新環境）**

```bash
# 用 HTTPS，不需要 SSH key，直接可用
git clone https://github.com/Bowei1121/B518_205_207_ATE.git

# 或用 SSH（需先在 VM 設定 SSH key，步驟同下方「初次設定」）
git clone git@github.com:Bowei1121/B518_205_207_ATE.git
```

**情況 B：虛擬機上已從 Gitea clone 過，需切換來源**

```bash
# 把 origin fetch 改成 GitHub（不需要重新 clone）
git remote set-url origin https://github.com/Bowei1121/B518_205_207_ATE.git

# 拉取最新程式
git pull origin main

# 確認 remote 設定
git remote -v
```

> ⚠️ 打包 VM 通常只需要**拉取（pull）**，不需要 push，因此用 HTTPS 即可、不需要設定 SSH key。
> 若之後回到公司內網，再執行 `git remote set-url origin http://10.64.76.34:3000/8362/B518-205_207_ATE.git` 切換回 Gitea。

### 初次在新機器上設定（首次 clone 後執行）

```bash
# 1. 產生 SSH Key（若尚未有）
ssh-keygen -t ed25519 -C "Bowei1121@github" -f ~/.ssh/id_ed25519_github -N ""

# 2. 設定 SSH config（寫入 ~/.ssh/config）
cat >> ~/.ssh/config << 'EOF'

Host github.com
  HostName github.com
  User git
  IdentityFile ~/.ssh/id_ed25519_github
  AddKeysToAgent yes
EOF
chmod 600 ~/.ssh/config

# 3. 複製公鑰，貼到 GitHub → Settings → SSH Keys
cat ~/.ssh/id_ed25519_github.pub

# 4. 驗證 SSH 連線
ssh -T git@github.com
# 預期輸出：Hi Bowei1121! You've successfully authenticated...

# 5. 加入 GitHub 為 origin 的第二個 push URL
git remote set-url --add --push origin http://10.64.76.34:3000/8362/B518-205_207_ATE.git
git remote set-url --add --push origin git@github.com:Bowei1121/B518_205_207_ATE.git

# 6. 加入 github 單獨 remote（外網備用）
git remote add github git@github.com:Bowei1121/B518_205_207_ATE.git

# 7. 確認設定正確
git remote -v
# 預期輸出：
# github  git@github.com:Bowei1121/B518_205_207_ATE.git (fetch)
# github  git@github.com:Bowei1121/B518_205_207_ATE.git (push)
# origin  http://10.64.76.34:3000/8362/B518-205_207_ATE.git (fetch)
# origin  http://10.64.76.34:3000/8362/B518-205_207_ATE.git (push)
# origin  git@github.com:Bowei1121/B518_205_207_ATE.git (push)
```

### 其他規則

- 每次程式修改完成後，必須 commit 並 push 至 `origin/main`。
- `release-hid-calibration/` 是本機打包輸出，不納入 Git（已加入 `.gitignore`）。
- `dist-*/`、`.venv*/` 同樣排除在外。
