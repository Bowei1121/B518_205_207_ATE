# M5：工程師設定與配置操作換語言不丟失輸入

## Parent

Part of [規格 Issue #13](https://github.com/Bowei1121/B518_205_207_ATE/issues/13)。依 ADR 0009 及已確認拆票方案實作。

## What to build

工程師在設定、配置編輯及匯入匯出中切換語言，既有視窗同步翻譯且保留尚未儲存輸入與選取。錯誤及操作說明同筆雙語保存；原生選檔系統文字依作業系統，App 提供的內容仍翻譯。

## Acceptance criteria

- [x] 設定、配置、保存天數及匯入匯出可見文案完整接入兩語與共用術語。
- [x] 不關閉重開視窗，切換保留未保存輸入、選取及驗證狀態，不自動儲存或清除。
- [x] 配置與語言／全域保存設定彼此不抹除，機型仍用 Station Type 語意，不改資料名稱。
- [x] App 設定操作及錯誤保存同筆雙語，原始診斷可讀；SN、路徑及自訂名稱不翻譯。
- [x] 原生選檔遵照系統文字，App 的標題／類型／說明翻譯；取消、覆寫確認及回傳路徑效果不變。2026-10-09 使用者完成兩語真正原生對話框、取消、返回路徑與拒絕覆寫；磁碟核對通過。
- [x] 真正 Tk 驗證輸入中切換、連續切換、匯入失敗及保存失敗；長英文仍可閱讀操作。

## Blocked by

- [#17：無輪次 App 事件雙語保存與可理解錯誤復原](https://github.com/Bowei1121/B518_205_207_ATE/issues/17) 已由 M4 合併至 GitHub `B518-Log-Solution`，依賴解除；依據見 [M4 驗收紀錄](../evidence/multilingual-ticket-04/local-validation.md)。

## M5 驗收紀錄

本票六項驗收已通過；最後的原生選檔實際桌面操作於 2026-10-09 由使用者完成，兩語匯出及拒絕覆寫的磁碟核對亦通過。程式、測試、測試命令、M4 依賴及環境限制見 [M5 本機驗收紀錄](../evidence/multilingual-ticket-05/local-validation.md)。

最終程式／測試版本 `a90be28c8b1615b408aaf6147572e603dff5338e` 的完整含 Tk 套件通過 334 項，真 Tk UI 模組通過 57 項；固定 Standards／Spec 基準為 `740b26c23f5fb6fcc0988272183159b4405df5da`，複審發現已修正。此 SHA 已直接確認在 GitHub `Multilingual/ticket-05`。第五項驗收已有 [真正原生操作與磁碟證據](../evidence/multilingual-ticket-05/native-dialog-validation.md)。依遠端交付例外可先完成 GitHub 合併與合併後驗證；公司 Gitea 週一同步直接確認前，保留票分支、不清理。
