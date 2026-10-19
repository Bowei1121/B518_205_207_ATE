# 2026-10-19 建置異常處理

## 前次可查證結果

2026-10-16 的 macOS 建置修正以 `1bdb163ecd02ae15d103e8884d842541d59a3c7e` 推送至 GitHub，當時含 50K fixture 的 506 項測試全部通過；證據見 `evidence/macos15-build-2026-10-16/validation.md`。本次開始時主線已進至 ST1–ST8 整合後的 `6fb5b75`，不能沿用前版測試結果作為本版保證。

## 本次處理

使用者再次回報 arm64 建置測試失敗。保留原有 VERSION 修改及未追蹤 spec，先備份再重現。M10 子程序出現相同 Tcl command 重複刪除與 interpreter 留存；原生堆疊另確認部分自動測試卡在 Aqua modal menu loop。修正與最終驗證見 [報告](evidence/macos-build-2026-10-19/validation.md)。

最終原始 build script 執行成功：513 項測試、184.950 秒，512 通過，僅既有人工切換系統外觀案例未執行；零失敗／錯誤。包括 50K fixture、真實 Tk、原生 hover/keyboard 與關閉／背景 GC 回歸。macOS 15.0 arm64 相容性、簽章驗證、V0.1.5 ZIP 全部成功。保留原 VERSION 0.1.4 修改及 untracked spec；隔離建置副本自行遞增版本。修正同時涵蓋全域提示回呼 owner、字典 widget key 釋放、Aqua 游標提示與原生測試事件／遮蔽／游標隔離；沒有略過失敗測試或降低 build 門檻。
