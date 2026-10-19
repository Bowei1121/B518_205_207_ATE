# B518 Log Solution 手冊維護

閱讀與離線轉發入口為 `Manual/index.html`（繁中）及 `Manual/index-en.html`（英文）；`docs/manual/` 保存維護流程、摘要與證據。兩版共用 CSS、JavaScript 與圖片，章節 ID／順序相同，停用 JavaScript 仍可閱讀。

## 自動產生圖片

從 repo 根目錄，在已登入的 macOS Aqua 桌面執行：

```zsh
PYTHON_BIN=/opt/anaconda3/bin/python3
"$PYTHON_BIN" "B518 Log Solution/scripts/capture_manual.py"
```

`PYTHON_BIN` 可換成安裝 Tk 與 PyObjC Cocoa／Quartz 的 Python 3.9 以上環境；已驗證的本次環境為 Python 3.11.7／Tcl 8.6.12／Tk 8.6。依賴清單見 `B518 Log Solution/requirements/requirements-macos-desktop-tests.txt`。不要使用本機過舊的預設 Python 3.8 執行此產圖流程。沙箱若無法初始化 Aqua，需在允許存取桌面的執行環境重跑；不得把初始化中止當測試通過。

- 腳本分開啟動每個既有測試程序，使用暫存偏好、Session、受控來源與故障，不更改產線配置。
- 環境變數 `B518_TK_TESTS=1`、`B518_TK_EVIDENCE_DIR` 啟用既有情境截圖，`B518_TK_CAPTURE_METHOD=view-cache` 選用實際 Tk 視窗的 NSWindow.contentView 快取。預設桌面驗收仍使用原 WindowServer 路徑。
- 頁籤切換後要求實際控制項重繪並等候 Aqua，再讀取視窗內容；不是另外合成一張 UI 圖。
- 五個既有 UI 測試各產中英文，兩個輪次 smoke 保留原英文 UI，共 33 張。語言與來源逐張寫入 `Manual/Photo/generated/manifest.json`；中文手冊引用英文輪次樣本時明確標註。
- 全部測試、PNG 解碼／尺寸／色彩檢查成功才複製到 `Manual/Photo/generated/`。失敗時既有手冊圖片保持不變。每次原始證據在新的時間戳子目錄，避免舊圖片誤判成新產物。
- 原始證據預設寫在 `docs/manual/evidence/latest/<UTC時間戳>/`。可用 `--evidence /路徑` 與 `--output /路徑` 指定其他位置。
- manifest 記錄來源 commit、工作目錄是否有修改、原始檔 SHA-256、測試、語言、像素與圖片 SHA-256。`working_tree_dirty=true` 表示使用含未提交變更的工作目錄，不表示 HEAD 已包含全部修改。

### 素材與情境對照

| 素材 | 來源測試／腳本 | 說明範圍 |
| --- | --- | --- |
| home | `test_hm1_toolbar_title_status_and_kvm_geometry_stay_fixed` | 主畫面、工具列、KVM 與操作區 |
| configuration / events / retention | `test_profile_editor_uses_three_equal_action_columns_and_browse_label` | 工程師配置草稿、事件與 Session、保存期限 |
| alarm-pending / alarm-acknowledged / save-recovered | `test_recovery_acknowledges_only_manually_and_session_retry_keeps_evidence_once` | 明確確認警報、保存重試恢復 |
| conflict / round-alarm | `test_hm3_conflict_and_alarm_layout_stays_fixed_across_languages` | 多候選、長來源、整輪警報 |
| history / diagnostics / history-diagnostics | `test_real_tk_history_language_refresh_preserves_draft_snapshot_page_and_detail` | 固定查詢、分頁、診斷、損壞資料與語言切換 |
| preparing / monitoring / activity / complete | `tools/smoke_li1_preparation_app.py` | 來源準備、監控就緒、活動及完成 |
| preparing-stop / preparing-stop-cancelled / mixed-terminal-stop / all-terminal-review / manual-stop-released | `tools/smoke_li2_manual_stop_app.py` | 準備中停止／取消、終態保留、人工停止可交付 |

圖說必須交代情境、預期行為與操作員下一步。受控 SN、路徑、故障及刻意放大的診斷文字須標成範例。不可由單元測試的模擬物件直接合成圖片後冒充 App。視窗快取只證明 App 內容，不證明原生選單、遮擋、鍵盤焦點或實體 KVM 的擷取辨識；這些仍依專用現場驗收。

## 更新內容

以 `B518 Log Solution/src/` 的實際行為與通過測試為準，不把尚未實作的訪談或 ADR 當成既有功能。核對 `CONTEXT.md`、KVM 契約、配置與翻譯目錄，尤其注意每排十格／最多二十位置、容量映射、監控就緒與開測的差別、結果可交付與保存完整性的差別。

中英文同步更新章節、表格、圖說、alt／data-caption、回報範本與日期。英文可使用真正英文 UI 素材，兩版保留相同程式狀態名稱、SN、配置路徑與章節 ID。新增的所有資源均用相對路徑。兩張 2026-09-11 產線照片僅供歷史通道對照，舊七格 UI 不可用來解釋目前版本。

B482 的 Atlas 路徑範例為 `/Users/gdlocal/Library/Logs/Atlas/active`、`/Users/gdlocal/Library/Logs/Atlas/unit-archive`；BT TestData 與選填 CaseInfo 都以 `/vault/B482_RFTEST/TestData` 為範例。其他專案須使用自己的部署路徑；自動測試路徑不是現場部署建議。

## 瀏覽器驗證與轉發

使用 Node.js、Playwright 與已安裝的 Chrome 執行：

```zsh
node "B518 Log Solution/scripts/verify_manual.cjs"
```

Playwright 需在 Node 的模組搜尋路徑；使用 bundled runtime 時設定 `NODE_PATH` 指向其 `node_modules`。可傳第一個參數指定 Manual 位置，`B518_MANUAL_BROWSER_EVIDENCE_DIR` 指定證據資料夾。驗證以 `file://` 開啟，包含兩語圖片解碼、桌面／390 px 手機寬度、圖片放大／Escape、剪貼簿拒絕時的回退提示與選取、手機導覽、列印 CSS、語言切換保留章節及停用 JavaScript。複製驗證不宣稱系統剪貼簿已實際讀回；列印 CSS 驗證不等於逐頁印刷驗收。

打包前執行 `python3 "B518 Log Solution/scripts/package_manual.py"`，核對兩語章節、離線資源、圖片 SHA-256 與 ZIP 逐檔內容。

轉發須提供整個 `Manual/`。不包含維護紀錄、測試原始證據或 `.DS_Store`。本機交付包為 `B518_Log_Solution_Manual_2026-10-19.zip`，依 `.gitignore` 不提交。新素材位於全域忽略圖片規則內；須用 `git add -f Manual/Photo/generated/*.png` 明確提交。只提交已檢查過的交付圖，不批次加入所有原始驗收截圖。

## 2026-10-19 更新

- 重寫中英文手冊，涵蓋配置、輪次生命週期、衝突／警報、復原、歷史事件、保存期限及新 KVM 排列。
- 移除四張過時 UI 截圖，保留兩張歷史產線照片並明確限定用途。
- 新增可重跑的 33 張測試素材、manifest 與離線瀏覽器驗證腳本。完整驗證結果見 `VALIDATION_2026-10-19.md`。
