# B518 ATE MVP Demo — 專案摘要

最後更新：2026-08-14（Asia/Taipei）

## 專案目的

Atlas Agent 透過 Arduino UNO R4 的 USB CDC 接收工作指令，並以 Arduino USB HID 執行測試 HMI 的鍵盤、滑鼠與截圖操作。支援 DFU、FCT、BT；上位機使用 TCP 與 CRLF 交換 JOB、ACK、RESULT。

## 目前測試／Demo 架構

- 開發用 B482 模擬 HMI：`b482_demo_server.py` + `b482_demo_hmi.html`，開啟 `http://127.0.0.1:8080`。
- Agent 支援手動條碼與 Demo slot 視窗：DFU 7 格、FCT 6 格、BT 4 格；正式上位機協定維持最多 4 slot。
- DFU 7-slot Demo 支援掃碼槍輸入：每次掃碼尾端的 CR／Enter 只會將焦點循環移至下一個 Slot（slot7 回 slot1），不會啟動測試；跳到已有條碼的欄位時會全選原內容，方便重掃覆寫。流程只能由操作人員按下「開始流程」按鈕啟動。FCT／BT Demo 維持原本的 Enter 行為。
- BT 以 `TestData/YYYY-MM-DD/PASSED|FAILED/*.csv` 監聽結果；Thread0～3 對應 slot1～4。
- 現場可在 FCT／BT Demo 視窗啟動「無 SN Log Demo」：以按鈕時間與啟動前檔案基準排除舊資料，從新 Log 自動取得 SN 與結果，只顯示、不回傳 TCP RESULT。FCT 以 `active/group0-slotN` 固定顯示實體 slot；只信任 active records.csv 的 `MLB_SN`／`PrimaryIdentity`／`SerialNumber`，並以設定的 `unit-archive` 最終 records.csv 定案 PASS／FAIL。`NUMBER_SOF0` 代表 SN 讀取失敗，不是產品條碼。
- 正式 DFU／BT 影像定位會暫時隱藏 Agent 視窗；FCT 不執行截圖或 HID，直接監聽 CSV。路徑選擇器會顯示隱藏資料夾（例如 `/vault`）。
- 現場 OS：BT 為 macOS Mojave 10.14.5；DFU／FCT 為 Catalina 10.15。共用候選 App 需在 Intel Catalina VM 以 10.14 deployment target 建置，並經兩種 OS 實機驗收。

## USB CDC／HID 現況

- USB CDC 本地控制命令使用 LF；TCP JOB／ACK／RESULT 保留 CRLF。
- `ERR:TCP_NOT_CONNECTED` 是 TCP bridge 診斷，不能視為本地 HID 指令失敗。
- 每次 HID 命令前會清除 App 端舊事件並 flush serial output；接收執行緒是唯一 serial reader，避免搶走第一筆回覆。
- 最新韌體版本為 **1.1.0**（BT_Claude 分支）：所有 HID 指令（含 `M_ABS`、`M_ABS_CLICK`、`M_CLICK`、`K_WRITE`、`K_TYPE`）先回 `ACK`、HID 函式返回後回 `OK`。
- 若見 `ACK:M_RESET` 但沒有 `OK:M_RESET`，代表 CDC 指令已送達、問題在滑鼠 HID 執行／舊 OS 接受 report 的路徑；若完全無 ACK，則先查 CDC 傳輸或命令 framing。1.1.0 起多一種明確錯誤：`ACK:` 後緊接 `ERR:HID_NOT_READY` 代表 macOS 未綁定／未啟用 Arduino 的 HID 介面（BT／10.14 症狀），韌體不再卡死在 HID 忙等中。
- BT（Mojave 10.14.5）現場症狀：CDC 正常（GET_INFO 通過、TX/RX 有紀錄）但滑鼠鍵盤皆不動——推斷為整個複合 HID 介面未被 Mojave 綁定，頭號嫌疑是附加的 report ID 3 絕對指標 collection。二分驗證流程與決策樹見 `B518_Arduino_MVP_Test/README.md` 的「macOS 10.14（BT 站）相容性」章節：`Arduino_mouse_move_via_usb.ino`（最簡版）→ 1.1.0 `B518_ENABLE_ABSOLUTE_POINTER 0`（無絕對指標）→ 1.1.0 完整版。
- `GET_INFO` 於 1.1.0 新增 `ABS`／`HID`／`HIDSEEN` 診斷欄位；PROTO 維持 1，新舊 App 與韌體互相相容。
- HID 校正工具 **0.2.0**：逾時訊息會標明卡在「未收到 ACK」（CDC／framing）或「ACK 後逾時」（HID 層）；新增「絕對指標測試 (M_ABS)」區塊（韌體回 `ERR:ABS_UNSUPPORTED` 時自動停用並顯示 BT 相容模式）與「一鍵診斷報告」（GET_INFO → M_RESET → M_DELTA → K_WRITE → M_ABS → 結尾 GET_INFO 複測；結尾複測逾時代表韌體已卡死、需拔插 USB 並燒錄 1.1.0）。

## 最近提交

- `7d1e5aa fix: diagnose legacy mouse HID stalls`：韌體 1.0.4、舊 macOS 的較保守 mouse report 節奏、HID ACK 診斷與移除收訊鎖定造成的 UI 延遲。
- 下一筆提交：FCT active→unit-archive 明確路徑、可信 SN 鎖定與最終結果監控修正。

## 2026-08-10 FCT active → unit-archive 修正

- FCT 無 SN Demo 現在要求以兩個既有欄位明確指定路徑：`CSV／BT TestData 根路徑` 選擇 `unit-archive`，`Log 根路徑` 選擇 `active`；不再自動猜測 `unitest`／`unit-archive`。
- 每個 `group0-slotN` 一旦從 active `records.csv` 取得可信 SN，會鎖定至本輪結束。active 在測試完成時清空或搬移檔案，不會把已顯示的條碼覆寫回「SN 讀取中」。
- active 消失後，已鎖定 SN 顯示 `COMPLETING` 並只在設定的 `unit-archive/<SN>/<timestamp>/system/records.csv` 尋找最終 PASS／FAIL；始終沒有可信 SN 才定案為「SN 讀取失敗／FAIL」。
- 2026-08-10 現場 `COMPLETING` 不結束的根因已確認：真實 FCT `records.csv` 含有 status 空白的軟體／設定 metadata 列，舊判定要求所有列都為 PASS，因而把有效全 PASS 檔誤判為 UNKNOWN。現行判定忽略空白 status，只以非空白測試列判斷；並只接受本輪 active 已鎖定 SN 的最終檔，避免其他 cycle 汙染畫面。
- 最終檔搜尋改為直接鎖定 `unit-archive/<已鎖定SN>`；每個 SN 都會記錄「找不到資料夾／尚未有時間戳 records.csv／舊資料／CSV 未完成」等原因。判斷新一輪資料以時間戳資料夾與啟動前檔案基準為主，不再因 Atlas 搬移時保留 `records.csv` 舊修改時間而拒絕有效結果。
- `unit-archive` 的時間戳資料夾若採測試開始時間命名，允許比無 SN Demo 啟動時間早 30 秒；仍以啟動前檔案基準排除既有未變更資料，避免讀取前一輪結果。
- 無 SN FCT Demo 的結果保護逾時只用於「尚未出現任何 active」與「active 已全數結束後等待 unit-archive」兩階段；active 仍存在時不會自動停止，以容納現場差異很大的測試時間。

## 2026-08-11 FCT 無 SN Demo 時間容差

- `unit-archive/<SN>/<timestamp>` 若以測試開始時間命名，允許其時間戳最多早於無 SN Demo 啟動時間 30 秒，以支援操作人員在測試開始後短暫延遲才啟動 Demo 的情況。
- 超過 30 秒的時間戳仍視為前一輪資料而拒絕；Demo 啟動前已存在且未變更的 `records.csv` 也持續拒絕，避免時間容差造成舊結果誤配。

## 2026-08-11 FCT unit-archive 資料夾時間戳修正

- FCT 最終結果只依 `unit-archive/<已鎖定SN>/<時間戳-ID>/system/records.csv`（亦相容 `record.csv`）的**資料夾名稱時間**選擇本輪檔案；不再以 Finder Date Modified、CSV mtime 或 CSV 內部時間拒絕結果。這符合 Atlas 搬移完成資料時可能保留舊檔案修改時間的行為。
- 時間戳同時支援 `_HH-MM-SS` 與現場舊版系統使用的 `_H-MM-SS`，並保留毫秒，例如 `20220618_2-28-01.374-04426F`。系統年份即使停留在 2022 也不影響，因為儀器與 Agent 共用同一台 Mac 的系統時間。
- 同一 SN 有多筆合格 archive 時一律優先解析資料夾名稱時間最新的一筆；最新檔仍在寫入或 UNKNOWN 時持續等候，不回退採用較舊重工結果。啟動前快照僅隔離未變更的舊檔，啟動後新增或內容完成的檔案可正常使用。

## 2026-08-08 截圖與七槽 DFU 診斷更新

- Agent 執行期間暫時關閉 macOS 截圖浮動預覽；正常退出與下次啟動皆會復原原始設定。
- 截圖等待改為「新檔案大小／修改時間穩定」即繼續，取消固定五秒等待。
- 七槽 DFU 仍以 4+3 為唯一有效版型。只辨識到六槽時會重新透過 Dock Atlas 圖示聚焦並重試；仍失敗則回報 `DFU_HMI_NOT_READY`，不執行 checkbox、SN 或 OK 操作。
- 每次視覺流程保存完整原圖、成功／失敗疊圖與 JSON 診斷到 `match_sessions`；主畫面可檢視最近十次 session。
- 公司外網無法連線 Gitea 時，可依本摘要的 GitHub remote／SSH 設定提交；本次依現場限制僅提交本機 Git，不推送 Gitea。

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

## 2026-08-08 FCT 即時 SN 與彈性逾時

- 現場截圖顯示 active Log 的暫存值可能是年份／步驟（例如 `2022`、`COMPLETING`），不可當成條碼或最終結果。
- FCT 無 SN Demo 現在優先監看 `active/group0-slotN/**/records.csv` 的 `MLB_SN`／`PrimaryIdentity`，取得完整英數 SN 後立即顯示在 HMI；device.log 僅作為備援，並拒絕純數字或過短 token。
- PASS／FAIL 仍只由 active 結束後搬入 `unitest/<SN>/<timestamp>/system/records.csv` 的完整 status 判定；active 階段只會顯示 TESTING、STALLED 或 COMPLETING。
- 無 SN FCT 監控改為三層：60 秒未見 active／新結果提示尚未開始、active Log 120 秒未更新標示 STALLED、設定中的「結果總保護逾時」才停止；新預設與建議為 900 秒，設為 0 可取消總保護上限。

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

### 2026-08-11 FCT 最終結果畫面鎖定

- 現場影片顯示 unit-archive 的 PASS／FAIL 曾短暫顯示後又被 active 的 `COMPLETING` 覆寫；原因是 active 目錄清理與 Tk 事件佇列可能在最終結果後仍送出舊進度事件。
- FCT 監聽器現在會把已解析 archive 結果的實體 slot 標記為終態；該 slot 後續不再發出 `TESTING`／`COMPLETING`。
- 主 HMI 也保留終態 slot 清單，忽略任何較晚到達的 FCT active 進度事件。沒有可信 SN 的 slot 仍獨立在 active 消失後顯示「SN 讀取失敗／FAIL」，不會影響其他 slot 已取得的 PASS／FAIL。
