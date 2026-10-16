# 專案摘要 — 2026-10-17

## #75 驗收接續

- 前日 ST1–ST8 程式與整合證據已推送至 Gitea／GitHub，主線與整合分支均為 `6fb5b7581e06fd465513c2daba09041cf18d7c37`。原始工作樹的兩個未提交程式／測試及 input-probe、window-bounds 暫稿保持原樣。
- 使用者要求驗收 #75，從兩端一致主線建立 `codex/st7-final-acceptance-20261016`，獨立工作樹 `/private/tmp/B518-st7-final-acceptance`。本次沒有修改產品或測試程式。
- 最終來源真正 Tk 驗收 **11/11 通過**：Dark 外層淺色 1/1、恢復／關閉契約回歸 8/8、同視窗 Dark→Light→Dark 1/1、Light 新程序獨立開窗 1/1。模式切換由使用者操作，原 Dark 已還原並讀回；12 張同視窗切換畫面及獨立開窗雙語兩分頁畫面已檢視。語言／KVM 15/15、Python 3.8 編譯及 diff check 通過。
- 前次 AppKit 建窗中止本次未發生，最終來源回放缺口已補；沒有根因證據可宣稱該環境中止問題已修復。
- 使用者明確補充原變色發生在「打包的 `.app`」。目前等待原 bundle 路徑／版本，尚不能用 Framework 原始碼測試替代該 bundle 的原症狀重現。原驗收第 1 項與第 6 項中的重現／修復前後證據仍待補；#75 不應關閉。
- 詳細命令、原生圖片、系統模式、11 項測試結果與 source/artifact SHA-256 見 `B518 Log Solution/docs/refactoring/evidence/st7-final-20261016/README.md`。若取得 bundle，先讀其版本、架構與 runtime，使用隔離資料驗證原面板變色，再比對最終修復；不改寫未重現結果、不自行降低驗收條件。
