# 專案摘要 — 2026-10-16

## 本次接續範圍

換日後首次對話，整理 2026-10-15 的 HMI 實際使用回饋及 2026-10-16 的 A7 最終確認。依據本次對話、現有討論文件及唯讀程式查核記錄，不重新宣稱其他工作階段的驗收結果。

## 已確認方向

1. 頂列圖示以可辨識的 ⚙️、⚠️、🌐、🔔 emoji 為基準，實際 Tk 若不可靠則採使用者確認的圖像素材；參考先前已認可模擬圖的視覺品質。
2. 鈴鐺集中整輪警報與保存／封存恢復操作。優先右上角紅底白字圓形數量徽章，必要時可用 🔔(1)。
3. 鈴鐺計尚未處理異常：每項未確認整輪警報一筆，每輪保存／封存異常一筆，同輪多錯誤不重複計數。正常保存與 ⚠️ 待確認不重複納入；開窗不清零，處理完成才減少；零筆仍可開窗。
4. 主頁底部只顯示簡短 App 狀態，右下「診斷」連結開 App 事件視窗。詳細說明及重試收納到適當視窗，保留故障可見性與恢復能力。
5. 資料夾選取按鈕為「📂 瀏覽／📂 Browse」，操作語意不變。
6. 設定兩排配置操作各三等分、等高、等間距；取消草稿另置下方右側。
7. 清理摘要避免未變更重建，保留閱讀位置，無紀錄顯示明確提示，並查明空白原因。真正 App 繁中與英文畫面是視覺驗收必要證據。

## 查核限制與後續

- 討論開始程式基準 e861e10；本輪沒有修改程式或執行 Tk 驗收。
- 已查到清理摘要每約 150ms 無條件清空／重填及恢復捲動位置，是跳動風險；空白完整原因仍待實際重現。
- 完整決策見 [HMI 後續討論](HMI_FOLLOWUP_DISCUSSION_2026-10-15.md)。討論已確認；新的 Spec、開發票及程式實作尚未進行。
- 保留既有保存完成才關閉、人工確認、重試與資料保護契約；本輪未授權刪除這些功能。

## 後續完成的規格與拆票發布

- 使用者確認真正 App／Tk 測試入口後，已完成 HMI_FOLLOWUP_SPEC_2026-10-16.md，並於再次取得具體發布確認後發布 GitHub #60，標記 ready-for-agent。
- 使用者核可七張票：HF1 #61 圖示、HF2 #62 鈴鐺與恢復、HF3 #63 計數徽章、HF4 #64 主頁精簡與診斷、HF5 #65 設定排列、HF6 #66 清理摘要、HF7 #67 整體驗收。
- 已設定並讀回驗證 #60 原生子議題及阻擋關係：HF3 ← HF1／HF2；HF4 ← HF2；HF7 ← HF1–HF6。其餘無前置。七票全為 OPEN 及 ready-for-agent；未改父規格正文或關閉父議題。
- 本機票與 44 項故事覆蓋表位於 [HMI 後續開發票](hmi-followup-tickets/README.md)。這次只有文件及議題操作，尚未修改產品程式或執行產品測試。


## HF1／HF2 使用者桌面回報與診斷接續（2026-10-16，歷史階段）

- 整合分支為 `codex/hmi-followup-20261016`；本輪由 `520aababa236aa9acdc5f61f9b0d8de2227a5c1f` 快轉合併診斷工具提交 `f9dfa16440087fb95e4957e5400eba6e5c5a3b12`。
- 使用者提供真正 App 繁中／英文主頁及零警報恢復視窗截圖，另提供繁中「通知與恢復」tooltip 畫面。圖示可辨識，但回報主頁 Tab 無法聚焦、設定頁可用，從 Terminal 啟動後按鈕需多次點擊才開窗。使用者表示已執行故障注入測試；未提供完整結果，不視作全部通過。
- HF1 真鍵鼠輸入問題根因尚未確認，未修復；不能以合成事件或通過部分測試替代。先前沙盒內 Tk abort 是環境限制，沙盒外 Aqua Tk 已能真正建窗與執行測試。
- 英文零警報截圖中的停用確認按鈕仍顯示「確認整輪警報」：HF2 尚有本地化缺項，待修復驗證。
- 新診斷入口：在 repo 根目錄執行 `python3 "B518 Log Solution/scripts/diagnose_hmi_input.py" --seconds 45`。先關閉舊 App；按文件順序以真鍵鼠測試標題列／Tab／齒輪／鈴鐺，提供 `input-trace.jsonl`、`input-summary.json` 及哪次操作未反應。偏好與輪次寫入隔離暫存資料；不啟動監控。詳細見 `HF1_INPUT_DIAGNOSTIC_2026-10-16.md`。
- 診斷 helper `py_compile` 成功。沙盒外五項 Aqua Tk 回歸實跑 13.738 秒，4 項通過、toolbar geometry 1 項失敗並有同測試 teardown 錯誤。原始失敗為 stop_button 高度 1 < 36；失敗清理過程 language tooltip 等待逾時，destroy 出現 `can't delete Tcl command`。不得把這次結果報為全綠，也未據此直接修改產品。
- 通過：未保存／完整保存／封存狀態區分、磁碟紀錄重試、衝突與警報刷新失敗隔離及語言重試、關閉失敗留窗及重試完整稽核。
- 完整輸出：`evidence/hmi-followup-20261016/hf1-hf2-desktop.log`；關閉保存真正 Aqua 雙語 PNG 與 bounds：`evidence/hmi-followup-20261016/hf1-hf2-aqua-20261016-0905/`。兩張圖已實際檢視，標題、失敗說明、重試與取消關閉均可讀；這些是注入測試畫面，不是 HF1 真鍵鼠通過證據。
- HF1 #61／HF2 #62 保持 OPEN；HF3 #63 仍被依賴阻擋。不得關閉父規格、合回主線或清理尚在使用的 worktree。


## GitHub open issues 驗收對帳 — 2026-10-16

- 使用者明確授權比對 `docs/refactoring/` 與 GitHub open issues，將驗收內容更新並關閉已完成案件。
- 起始 53 張 open；已逐票同步正文驗收摘要、測試／版本／限制與固定版本證據，完成票勾選 checklist。43 張以 `completed` 關閉：#1–#45 排除 #13／#23。
- 保留 10 張 OPEN：#13／#23 的 source 驗收完成，但正式 bundle／目標環境發布驗收待補；#60–#67 的 HF 系列尚未完整驗收。HF1 輸入／geometry、HF2 英文殘留及完整恢復操作證據仍待完成。
- #43 已依使用者先前確認的完整原文快照契約，明記「有效列已發布、原文尚未捕捉」條件不適用；未虛構不可取得提示測試。#37 同步此釐清。
- 重新讀回全部 issues，核對 53 張正文、狀態與 completed 原因；標題及標籤不變。105 份文件／版本內容比對一致，39 個實作／整合 SHA 皆在 GitHub 主線祖先。
- 本次只做議題與文件對帳，未修改產品程式或重跑產品測試，未改原生依賴、分支、worktree、stash 或既有未追蹤證據。
- 完整對照與既有測試證據見 [GitHub issue 驗收對帳](ISSUE_RECONCILIATION_2026-10-16.md)。


## HF1 鍵盤、焦點與原生滑鼠後續修復（歷史階段；HF1 已結案）

- 保留上方歷史失敗與對帳結果；整合分支由 `63d9ee5` 快轉至 `c24c6b3`，包含修正 `7e23f1b`，未覆寫使用者 3 個未追蹤證據檔。
- 頂列 Tab 改為 ⚙️ → ⚠️ → 🔔 → 🌐，Shift+Tab 反向且可離開頂列；增加可辨識藍色焦點，修正待確認計數寬度，KVM 契約不變。
- 真 Aqua Framework 與 Conda 受影響測試各 3/3，Conda 鍵盤／選單補充 2/2，KVM 7/7。雙語主頁與四焦點截圖、bounds 均已保存並實際檢視。
- 滑鼠問題定位於本機 Conda runtime：原生 pointer 在最小 Tk 與真 App 不送達（真 App 四操作 0/4），此限制尚存在。Python.org Framework 真 App 四個獨立程序皆單擊設定／鈴鐺／專案／機型 4/4；已提供 `scripts/run_macos_desktop.sh` 選用已驗證 Framework，README 更新入口。未宣稱打包 App／Python3.12 已驗收。
- 詳細測試、證據、原始失敗及限制見 `HF1_KEYBOARD_FIX_2026-10-16.md`。整合沒有修改程式，僅補 diff check／compile，不重跑有效桌面測試。
- HF1 待主協調者完成完整結案審查；HF2 英文零警報按鈕及完整保存／封存雙語操作仍待補。其後依序 HF3～HF7；本次 merger 未關 Issue、未合主線、未清理工作樹。

## HF2 補修、完整桌面驗收與整合（歷史階段；HF2 已結案）

- HF1 #61 已於完整驗收、整合與推送後結案。上方「待補／OPEN」為當時紀錄，以本節及後續進度為準。
- HF2 分支 `codex/hf2-acceptance-fix` 的 `ed31f67cefd0ae7745ca4aeb56beaf3bf3f97dc4` 已從 `e4cd033` 快轉整合至 `codex/hmi-followup-20261016`；保留使用者原未追蹤 input-probe、bounds 與 ignored 畫面，未覆寫其他工作。
- 修復零警報英文確認按鈕、長診斷與窄視窗重試入口溢出、150ms 更新清單閱讀位置，以及可信封存顯示。80 行原始錯誤完整保留於可捲動詳細區，舊主頁恢復控制仍存在。
- 真正 Session／audit 連續故障從鈴鐺新入口重試，人工確認僅一筆、跨輪保存不換當前板、選單一輪仍恢復全部符合資格封存。兩種 audit reader 依耐久 `save_recovered` 解除對應故障，仍拒絕序號缺失、沒有恢復及恢復後新失敗；恢復事件本身未保存仍阻擋封存與關閉。
- Framework Python3.8／Tk8.6.8 真 App 8/8、保存封存領域 101/101、受影響歷史查詢呈現 74/74 通過；20 張繁中／英文原生 PNG 與測試輸出、bounds／hash 已保存並檢視。整合無程式衝突，僅補 diff whitespace 與三檔 compile，重用有效桌面證據。詳見 [HF2 驗收紀錄](HF2_RECOVERY_ACCEPTANCE_2026-10-16.md)。
- HF2 已推送至 Gitea／GitHub，兩端整合分支 SHA 相同；#62 已於完整驗收後結案。HF2 merger 未合主線、未刪工作樹。
- 正式打包 App、工站磁碟／權限／網路位置、實際人工處理及 KVM 傳輸仍需現場確認；Conda Tk 原生滑鼠限制維持 HF1 所記，不假稱修好。

## HF3 通知計數徽章整合（2026-10-16；HF3 已結案）

- HF3 #63 分支 `codex/hf3-notification-badge`，提交 `93c604d1f29431b2a473697c43c15b23d6b3b4c9`（功能／測試／紀錄）及 `f0a1d6ad830a555130f5b60c8a3ff031b326525d`（12 張原生畫面）；由整合分支 `cfc473827da8b46b028c3fd92beba94b18fc1413` 快轉至 `f0a1d6ad830a555130f5b60c8a3ff031b326525d`。
- 徽章只計尚未確認的整輪警報及有保存／封存異常的不同輪次；同輪多錯只一筆，開啟通知中心不清零，完整確認／恢復後才消失。雙位數徽章清晰且未碰到🌐、待確認數或 KVM；徽章右側外點擊不觸發鈴鐺，原鈴鐺點擊區保留。
- 真 Aqua Python.org Framework 3.8／Tk 8.6.8，徽章生命週期、HF1 toolbar 幾何／KVM 與 Tab 順序 3/3（15.315 秒）；`git diff --check`、受影響兩檔 `py_compile` 通過。雙語零計數、同輪兩項、12 輪、單輪保存錯誤、封存失敗及恢復畫面和 bounds 已保存並檢視。完整命令與限制見 [HF3 桌面驗收紀錄](../../B518%20Log%20Solution/docs/refactoring/evidence/hf3/local-validation.md)。
- 工廠產線／正式打包環境仍待現場驗收。HF3 已推送至 Gitea／GitHub 並結案 #63；HF3 已整合，未合回主線。

## HF4 主頁精簡與診斷入口（2026-10-16；目前進度）

- HF1–HF3 已完成、整合並推送至 Gitea／GitHub；#61–#63 已結案。前面各節保留當時進度脈絡，現況以本段和 `HMI_FOLLOWUP_PROGRESS_2026-10-16.md` 為準。
- HF4 #64 已完成主頁短狀態與底部診斷入口，移除主頁舊恢復控制區並保留 KVM、狀態標記、位置、關閉保護及恢復中心。功能提交 `58b0208`、人工驗收紀錄 `f31b9ab`、使用者原始雙語畫面 `6df8a82`，整合起點 `f502a83d6bbb37a564d899290e1e83f3bc8f0e4c`。
- 使用者在真正前景 App 的英文與繁體中文畫面各以滑鼠單擊診斷入口，兩次均成功開啟 App diagnostics／App 診斷。主頁及診斷視窗雙語截圖已保存於 `docs/refactoring/evidence/hf4/` 並檢視；細節及限制見 `evidence/hf4/local-validation.md`。
- HF4 真 Tk、KVM／toolbar 幾何、HF2 恢復、關閉失敗重試、語言刷新及 M10 整合驗證通過。HF4 整合、雙遠端推送及 #64 同步由主協調者處理；HF5 為下一張。HF5–HF7 尚未完成，七票完成後仍須全分支 code review、合回 `B518-Log-Solution` 並推送兩端。工廠／正式打包環境另列。

## HF5 設定按鈕與三等分排列（2026-10-16）

- HF5 #65 從整合基準 `a5eb259f1a48edd52c2c7f31ccfb98b0fdddb987` 開始，分支 `codex/hf5-settings-layout` 的提交 `ae3ad15150c27519c822135c1a13bff5746dda45` 已快轉整合至 `codex/hmi-followup-20261016`。
- 「📂 瀏覽／📂 Browse」本地化完成；設定頁六個配置操作分兩排、每排三等分，取消草稿放在下方右側。原生像素測量確認每排按鈕最大寬差 1 px，等高等間距、控制項未超出視窗，英文標籤完整。既有目錄選擇／取消、草稿、保存載入、匯入匯出、部署重載與語言切換保留草稿操作通過回歸。
- 真正 macOS Aqua App／Framework Python 3.8、Tk 8.6 的中英設定頁截圖與像素 bounds 已提交，見 [HF5 驗收證據](../B518%20Log%20Solution/docs/refactoring/evidence/hmi-followup-2026-10-16/hf5/README.md)。舊布局真 Tk 像素 RED（按鈕寬差 104 px），修正後真 Tk GREEN；受影響 UI 8 項、翻譯 8 項、MachineProfile 24 項通過，compile 與 diff check 通過。
- HF5 整合分支推送與 #65 議題同步尚由主協調者處理；HF6、HF7 尚待依序實作。正式工廠／打包環境另列；最終七票審查、合併主線與雙遠端推送尚待完成。

## HF6 清理摘要顯示修正（2026-10-16）

- HF6 #66 分支 `codex/hf6-cleanup-summary` 由整合基準 `9cad82fc2b8aa9cfe7c848e218c5d2edb3ec18cd` 開始，提交 `98282394e33740913f11076ecf10520f8b45249f` 已 fast-forward 整合至 `codex/hmi-followup-20261016`。
- 根因是清理摘要 `Text` 元件建立於另一個 Frame，卻用 `grid(in_=...)` 顯示到後建立的 sibling Frame；Aqua 將 sibling 繪在文字上方造成畫面空白。已將 Text 改為承載 Frame 的直接子元件。相同摘要不再清空重填，修復輪詢期間的 scrollbar／閱讀位置跳動。
- 原生 macOS Framework Python 3.8.10／Tk 8.6 真 App 驗收：英文及繁中清理摘要和空狀態可見；80 行診斷可捲動；內容更新及語言切換期間閱讀位置與選取穩定；關閉重開設定頁後摘要仍可用。四張真正 Aqua 截圖及 bounds 已納入版控；證據、根因、命令與限制見 [HF6 驗收紀錄](../../B518%20Log%20Solution/docs/refactoring/evidence/hmi-followup-2026-10-16/hf6/README.md)。
- 驗證結果：專屬原生 UI 測試 1/1、清理回歸 7/7、輪次保留清理測試 36/36、`git diff --check` 通過。工廠及正式打包環境另待現場驗收；HF7 尚待執行。此時仍未合回 `B518-Log-Solution`。

## HMI 後續改善七票整合驗收現況（2026-10-16）

- HF1–HF7 的程式工作、對應回歸與真正 App 桌面驗收均已完成。HF7 從 `ed9432cd141b0bd1fe65adbada4ab56e4a2a7751` fast-forward 至整合分支 `codex/hmi-followup-20261016` 的 `3d098c41fd2119b19d64691035905bc2a7b5f5f6`；HF7 44 項故事矩陣、46 張中英原生 Aqua 畫面及 bounds／manifest 已提交，詳見 [HF7 驗收報告](evidence/hmi-followup-2026-10-16/hf7/README.md)。
- HF7 整合測試的焦點測試在 11 項批次中 10 項通過，唯一項於該批次讀到 `focus_get() is None`，隔離重跑 1/1 通過；獨立 KVM 幾何 1/1、KVM 顯示契約 7/7。批次焦點現象已保留於報告，不宣稱批次全綠。HF1–HF6 有效原生驗收及測試證據重用，未無條件重跑長時間歷史效能測試。
- 尚待最終 code review、修正 review 發現、將整合分支正常合回 `B518-Log-Solution`，確認 Gitea 與 GitHub 推送 SHA 相同，並由主協調者同步子議題／父議題狀態。正式打包版、工廠 KVM 傳輸與現場操作另列待確認，並非本地程式及桌面驗收的替代條件。

## 七票最終審查與主線整合（2026-10-16）

- HF1–HF7 的程式、各票回歸及真正 App 桌面驗收均完成；保留使用者現場提供的 HF1/HF2、HF4 證據，以及 HF5–HF7 原生 Aqua 雙語畫面。最終審查固定基準為 `26a4a353928d061bdf64ce32165333cc03b74389`。Spec 軸 finding 已修正：補入 HF6 修復前 Aqua 空白／捲軸跳動對照 PNG、觀察資料及 hash manifest，並校正 HF7 story 44 狀態。Standards 軸無硬性違規；留下兩項維護性提醒（通知計數責任邊界、主 UI 類的多種變更原因），不構成阻擋。
- 整合分支 `codex/hmi-followup-20261016` 最終 tip：`60d5f31ad9ec620cf05f825915377ac0bb94932c`。以一般 `--no-ff` 合併回 `B518-Log-Solution`，主線合併提交：`2a7f7d4`（完整 SHA 待遠端推送後核對）。合併涵蓋七票全部程式、測試與驗收證據，未覆寫或清理使用者原有未追蹤證據。
- `B518-Log-Solution` 合併提交 `fa486ba569b0b874854d2af022199e47798e12cb` 已推送並讀回確認 Gitea、GitHub 相同；整合分支 `60d5f31ad9ec620cf05f825915377ac0bb94932c` 也在兩端。GitHub 可讀 Issue，但使用者表示將重新連結權限後，留言 API 實測仍回覆 `403 Resource not accessible by integration`（#65）。不使用其他通道繞過此拒絕。#65–#67 的完成留言／關閉及父票 #60 總結／關閉尚未完成，維持 OPEN；待 GitHub Issues 寫入權限恢復後按依賴順序同步並讀回。
- 正式打包 App、工廠 KVM 傳輸、工站磁碟／權限／網路位置及現場操作仍需另行現場驗收；這些項目不改變本次七票程式與桌面驗收已完成的結果。


## #60／#65–#67 最終結案同步 — 2026-10-16

- 使用者要求重新確認本機資料並更新四張未結案議題。查核最新主線 `be3e600`：HF1–HF7 驗收、44 故事矩陣、46 張 HF7 雙語原生畫面、最終審查與正常主線合併均已完成；Gitea／GitHub 主線直接讀回相同 SHA。
- 先前 403 是歷史失敗，本次既定 gh CLI 寫入成功。#65／#66／#67 更新完整驗收摘要、測試與固定版本證據、勾選完成條件並關閉；確認 #61–#67 全部 CLOSED 後，父議題 #60 同步總結並關閉。四張皆為 `completed`，另一次獨立 GET 驗證正文與狀態一致。
- 明記 HF7 批次 10/11、焦點項隔離重跑 1/1 的測試限制；未宣稱重新跑完整產品套件，未將正式打包與工廠環境當成已通過。
- 本次僅改文件與 GitHub issues；保留未追蹤 input-probe／bounds、所有 worktree 與分支。

## 本機 Python3.12／macOS15 arm64 build 回歸修正

- 使用者在此 Mac 執行 pull --ff-only 與 macOS15 arm64 build，提供503 tests、9 failures／1 error／1 skipped截圖。本機從7a4cca6以指定Python3.12.10／Aqua Tk8.6.16完整重現相同結果（112.549秒），保留VERSION0.1.3與未追蹤spec並先備份。
- 先前10/12已完成的Tk生命週期／openat修正與374 tests紀錄仍是歷史證據，本次沒有用舊結果代表HMI改版後的完整測試。先前Intel相容性僅做共用程式與build腳本分析，未宣稱Intel實機通過。
- 確認Aqua固定縮放時拒絕程式geometry及WM預設max高度裁切；修正程式調整期間的resize／minmax／idle後恢復不可手動縮放。Aqua鍵盤改驗真正Shift+Tab，保留非Aqua X11 alias；補齊原生像素測試所需固定PyObjC／Quartz依賴，標題測試改驗實際版本。
- 新回歸：2→10→20→2精確尺寸與marker、版本在語言／機型切換後保留；啟用5萬筆容量fixture後，另修正非同步完成狀態、heartbeat最新timer與主執行緒GC，新增容量Tk子程序生命週期回歸。保留精確幾何、焦點、原始資料hash與閱讀位置斷言，修正測試臨時控制項映射及長文字排版前置條件。
- 同一build腳本於隔離副本完整跑 **506 tests，153.666秒，OK，零跳過，exit0**；macOS15.0 arm64 bundle、簽章及ZIP通過。候選V0.1.4留在忽略的dist-validation-20261016目錄，原有VERSION／spec均cmp相同，既有dist產物保留。
- 根因、回歸前失敗、6張原生雙語畫面與bounds、容量資料一致性及完整build輸出見[本次驗證紀錄](evidence/macos15-build-2026-10-16/validation.md)。本次沒有重新驗收Intel、其他Python／Tk組合或工廠KVM路徑。

## Slot 與頂列第二輪 HMI 需求確認

- 使用者要求先討論再實作，並已確認 [Slot 表格與頂列徽章改善討論](HMI_SLOT_TOOLBAR_DISCUSSION_2026-10-16.md) 的六項完整方向：淺灰空白區與最多十列、⚠️ 徽章、含 Logo 的頂列對齊及完整徽章空間、精簡地球入口、全 App 按鈕提示與試行狀態配色、通知恢復窗固定淺色修復。
- 已確認小螢幕可少於十列並啟用捲動；零待確認隱藏徽章；按鈕短標籤保留、浮動說明同步語言，停用按鈕可由滑鼠讀取說明但無可點擊效果。
- 唯讀查核顯示通知恢復窗最外層未明設底色，現有淺色測試未涵蓋該窗及實際系統外觀切換；根因仍待桌面重現，不宣稱已修復。
- 本次只定稿文件，尚未轉成新的 Spec／開發票。先前助理過早修改的主程式與 UI 測試留在未提交狀態，不納入這次文件提交；使用者原有未追蹤證據保留。

## Slot／頂列規格發布

- 使用者確認真正 App／Tk 測試入口後，完成 [Slot／頂列 HMI Spec](HMI_SLOT_TOOLBAR_SPEC_2026-10-16.md)，包含 52 項使用者故事、16 項實作決策與 13 項測試決策。
- 已發布 [GitHub #68](https://github.com/Bowei1121/B518_205_207_ATE/issues/68)，標記 ready-for-agent；待後續拆票，本次未實作產品或執行產品驗收。
- 本地有先前未驗收 UI 暫稿，GitHub 有另一次已提交的 macOS 幾何修正；文件同步在獨立工作樹處理，不提交或覆寫本地暫稿。

## Slot／頂列八票發布

- 使用者核可 ST1–ST8 的粒度及依賴，已發布為 GitHub #69–#76，父規格 #68；全部為 ready-for-agent。本機票、依賴與 52 項故事對照見 [開發票總覽](hmi-slot-toolbar-tickets/README.md)。
- ST1 #69 Slot／捲軸；ST2 #70 頂列／雙徽章／語言；ST3 #71 主頁提示能力；ST4 #72 設定與恢復提示；ST5 #73 裁決／警報／關閉提示；ST6 #74 查詢／診斷提示；ST7 #75 恢復窗淺色；ST8 #76 全覆蓋及整合驗收。
- 依賴：ST4–ST6 各依 ST3，ST8 依 ST1–ST7，其餘無前置。僅按真實前置認領，不將無依賴當成共享 Tk 模組可任意並行。
- 本次只有文件與議題發布，不修改產品、執行產品測試或採納先前未驗收暫稿；保留未追蹤證據。不修改父規格正文或關閉父議題。

## ST1–ST8 整批實作啟動

- 使用者明確授權依序完整實作八票與驗收、必要議題更新、最後正常合併回 B518-Log-Solution 及雙遠端推送，不逐票等待確認。
- 開始前已讀回確認 Gitea／GitHub 主線都為 `612c6d08e74c2e6fd2973114ccc9c5d32195a5ad`；在獨立 `/private/tmp/B518-st-integration` 建立 `codex/hmi-slot-toolbar-implementation-20261016`，保留 macOS 回歸修正。
- 原工作樹未提交主程式／UI 測試及 input-probe／window-bounds 均保持原樣，另記 SHA-256 供結束比對。
- 詳細進度、逐票提交與驗收見 [執行紀錄](HMI_SLOT_TOOLBAR_EXECUTION_2026-10-16.md)；此段只記啟動，不宣稱八票已完成。


### ST1 首票完成

- #69 ST1 已以 TDD 完成並關閉，功能提交 `d3ed365ba86c05674387080ac09e1f15ccfafe75`；整合提交 `299a5c25f30984742acf267ade825b90a0dc68cf` 已推送 Gitea／GitHub 且兩端 SHA 一致。
- 真正 Aqua Tk 矩陣 32 場景涵蓋容量 1／10／11／20、兩種視窗高度及繁中／英文；足高十列，小高度 4／5 列、末列可達，操作區及 KVM 契約維持。整合後 12 項受影響測試全通過。顯示模式已還原。
- 證據含 32 張原生截圖、矩陣及重跑紀錄，見 `B518 Log Solution/docs/refactoring/evidence/st1-20261016/README.md`。工廠 KVM/縮放驗收待現場。
- 當下整合 tip：`299a5c25f30984742acf267ade825b90a0dc68cf`。依序接續 ST2 #70。

## ST1–ST8 整批續作與最終整合（2026-10-16）

- ST1–ST8 已按序實作及整合到 `codex/hmi-slot-toolbar-implementation-20261016`；最終整合證據、逐票畫面與測試索引見 [執行紀錄](HMI_SLOT_TOOLBAR_EXECUTION_2026-10-16.md) 和 [ST8 整合驗收](evidence/st8-20261016/integrated-acceptance.md)。整合階段逐票分支、提交及遠端同步亦記於該執行紀錄。
- 最終 code review 固定基準為 `e245f6cff9bb4c45954c06208c5adc34d93b5e7e`；Standards 軸無發現。Spec 軸要求直接檢查 ST7 修復前症狀；已用真正 App 在修復前整合版 `77d15fb` 執行 Dark→Light→Dark，症狀未能重現，三張窗口畫面與系統模式讀回保存在 `B518 Log Solution/docs/refactoring/evidence/st7-20261016/baseline-reproduction-attempt/`。根因仍未知；最後 Tk/AppKit replay 中止仍列未通過，不冒稱完成。
- 使用者檢視真正 App 中英文 hover／focus 畫面後明確選擇保留淺藍 hover 與藍色 focus 框。工廠電腦、產線 KVM／壓縮識別、工廠流程及未覆蓋的 macOS／縮放組合仍需現場驗收；沒有執行無關的長時歷史效能測試。
- 續作期間使用者要求先不處理 GitHub Issue 問題，因此 #68–#76 未由本次續作更新或關閉。原始 B518 Log Solution 工作樹的未提交主程式／UI 測試及 input-probe／window-bounds 暫稿保留，不納入整合。
