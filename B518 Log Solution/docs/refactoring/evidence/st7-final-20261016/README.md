# #75 最終版本桌面驗收 — 2026-10-16

驗收產品版本為主線 `6fb5b7581e06fd465513c2daba09041cf18d7c37`。使用獨立乾淨工作樹與測試暫存的配置、輪次及 App 事件，不使用原工作樹未提交暫稿。本次沒有修改產品或測試程式。

## 環境及目前結論

- 本機 macOS 15.7.9（24G830）、x86_64；Python.org Framework Python 3.8.10、Tk/Aqua 8.6，入口為 `scripts/run_macos_desktop.sh`。
- 最終來源的真正 Tk 驗收 **11/11 通過**：Dark 下外層淺色 1/1（4.225s）、相關恢復／關閉回歸 8/8（47.664s）、同視窗外觀切換 1/1（107.397s）、Light 下獨立新程序開窗 1/1（2.212s）。本次沒有出現先前 Tk/AppKit 建窗中止；此結果不代表已查明先前中止原因。
- 同一已開恢復視窗實測 Dark→Light→Dark。每階段均有兩分頁 × 英文／繁中，合計 12 張原生視窗畫面；已實際檢視內容與外圍留白。系統模式由 macOS preferences 讀回；使用者原本 Dark 已還原。
- 使用者在本次補充：原面板變色情境發生於打包 `.app`。該 bundle 的路徑／版本尚待提供，不能以本次 Framework 原始碼測試當成原 bundle 重現。既有 `77d15fb` 原始碼基線未重現的結論維持；原症狀根因尚未確認。
- #75 第 1 項及第 6 項中原症狀重現／修復前後證據仍未全滿足；保持未通過，不以調整規格方式自行關票。

## 實際測試

所有真 Tk 命令從 `B518 Log Solution/` 執行，使用：

```sh
PYTHONPATH=src:tests \
B518_TK_EVIDENCE_DIR=/private/tmp/st7-final-evidence \
PYTHON_BIN=/Library/Frameworks/Python.framework/Versions/3.8/bin/python3 \
bash scripts/run_macos_desktop.sh -m unittest -v <test names>
```

- 外層底色：`LogSolutionUiTests.test_recovery_window_outer_surface_uses_the_app_light_palette`；結果轉錄於 `outer-surface-results.txt`，兩分頁雙語真畫面為 `st7-dark-tab{0,1}-{en,zh-TW}.png`。
- 八項回歸的完整測試名稱與輸出：[`regression-results.txt`](regression-results.txt)。涵蓋零警報切語言／重開保留分頁、封存清單選取／閱讀位置、人工確認、保存與封存區分、恢復重試恰好一次、選取前輪重試而不換本輪板、取消關閉及完整保存才關閉。對應 `hf2-*`、`close-progress-*`、`st5-close-retry-enabled-hint-*` 是此次真 App 截圖。
- 系統外觀：`B518_ST7_MANUAL_APPEARANCE=1 B518_ST7_ORIGINAL_APPEARANCE=dark`，執行 `LogSolutionUiTests.test_recovery_window_stays_light_during_real_system_appearance_changes`。完整輸出為 [`appearance-results.txt`](appearance-results.txt)；[`appearance-evidence.json`](appearance-evidence.json) 記錄各語言、分頁、系統模式與 native bounds；[`appearance-change-result.txt`](appearance-change-result.txt) 記錄還原結果。
- 另外語言／KVM `test_language_catalog test_kvm_display_contract` 15/15（0.007s）通過；產品與 UI 測試模組 Python 3.8 編譯、`git diff --check` 通過。
- Light 獨立開窗使用相同 outer-surface 測試，在新的 Python 程序執行。前後均從 macOS 讀回 Light，記錄為 `light-cold-open/system-mode-before.json`、`system-mode-after.json`；結果與四張雙語兩分頁畫面在 `light-cold-open/`。測試沿用原輸出命名 `st7-dark-tab*`，檔名中的 `dark` 不是系統外觀判定；本次該資料夾確實在 Light 下產生，模式以兩份 preference 讀回為準。

## 驗收條件對照

| 項 | 結果 | 證據／限制 |
| --- | --- | --- |
| 1 原症狀重現與記錄 | 尚未通過 | 原始碼修復前基線未能重現；現在得知來源為 `.app`，需要該 bundle 路徑／版本 |
| 2 固定淺色範圍與語意色 | 通過 | 真正兩分頁雙語畫面、帶選取警報／恢復清單、可用及停用控制；原生標題列維持 OS 邊界 |
| 3 深淺外觀及已開窗切換 | 通過 | Dark 開窗、Light 新程序獨立開窗，以及同視窗 Dark→Light→Dark 均有雙語兩分頁真畫面 |
| 4 語言／分頁／重開與資料狀態 | 通過 | 本次 8/8 回歸；人工 ack、保存／封存重試及取消關閉契約保持 |
| 5 OS 邊界與還原偏好 | 通過 | 只由使用者手動切系統外觀；最後實際讀回 Dark；沒有永久修改系統設定 |
| 6 畫面、重現修復及必要回歸 | 部分通過 | 最終版真畫面及必要回歸已有有效新結果；原 bundle 重現／修復前後證據仍缺 |

工廠 KVM、工廠流程、其他 macOS／顯示縮放及打包 runtime 尚未由本次原始碼驗收涵蓋。先前 AppKit abort 與未能重現原症狀的歷史仍保留在 `../st7-20261016/local-validation.md`，不改寫為通過。
