## Parent

Part of #28 — https://github.com/Bowei1121/B518_205_207_ATE/issues/28

## What to build

正式清理狀態與摘要畫面統一透過集中原因表述顯示，移除 Tk 分散的中文辨識；完整驗收新舊混合摘要與清理安全。

## Acceptance criteria

- [x] 即時狀態、輪次與 App 事件結果、封存驗證原因均透過公開表述契約，移除 Tk 中文全文／前綴判斷；舊資料辨識留在相容 Implementation。
- [x] 未知原因外層為所選語言，詳細保留原文，已知新原因依識別顯示；不得用顯示文案驅動清理。
- [x] 完成規格第二項全部七項驗收情境，涵蓋新原因、磁碟重建、新舊混合、未知／版本回退、保存故障、安全回歸與切語。
- [x] 雙語說明與原始診斷可直接查閱，run／round／時間／計數／序號不變，讀取或切語不重寫舊摘要、不重複清理。
- [x] 受控真 Tk 與真實磁碟資料完成從清理到保存重建再顯示的驗收，並保持未知內容的完整細節。
- [x] 原有期限、路徑替換、符號連結、未保存保護、封存與fsync故障恢復回歸通過；相同輸入刪除／保留結果相同。
- [x] 移除無意義重複與內部呼叫細節測試，保留有效行為情境，完成必要檢查並記錄版本、命令、結果與限制。
- [x] 第二項可獨立交付，不以L4完成為額外阻擋；不改父規格議題、不宣稱bundle／現場驗收完成。

## Blocked by

- #34 — 輪次清理與封存驗證產生雙語原因
- #35 — App 事件清理產生雙語原因

## Local validation

Final candidate and fast-forward-mainline validation, including all eight C4 acceptance items and the seven parent second-item scenarios: [C4 local validation](../evidence/retention-reason-ticket-04/local-validation.md). The integrated mainline SHA passed the required full Tk-enabled suite. Bundle, factory, target-device and field acceptance are outside this ticket.
