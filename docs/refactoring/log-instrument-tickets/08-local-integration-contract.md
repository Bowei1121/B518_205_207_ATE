## Parent

[父規格 #77：Log Solution 儀器狀態、人工停止與顯示契約 1.2](https://github.com/Bowei1121/B518_205_207_ATE/issues/77)

## What to build

把已完成切片整合成可交付的Log Solution候選，核對88項故事、本機行為／保存／真App證據，凍結完整顯示契約1.2及交接資料；不等待KVM驗收。

這張負責跨切片的完整生命週期與版本一致性，不承接前票未完成的功能／基本驗收，也不代做KVM、JetKVM或LabVIEW開發與測試。

主責使用者故事：14, 15, 77, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88。
依父規格實作決策：1, 18, 19, 23, 24, 25；測試決策：1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17。

本票只驗收本程式的公開輪次行為／磁碟資料與必要真App／Tk輸出；不要求KVM_Log、JetKVM或LabVIEW驗收。

## Acceptance criteria

本機逐條驗收狀態及證據：[`LI8_LOCAL_ACCEPTANCE.md`](LI8_LOCAL_ACCEPTANCE.md)。AC 1–11 本機檢核目前通過；最後 LI6 focus/restore 候選重跑證據位於 evidence 索引。

- [x] 前票各自交付可重現本機證據；整合比對父規格88故事，逐項指向主責切片與實際證據，無未認領或以不適用隱藏的需求。
- [x] 同一真App候選完整驗READY→PREPARING→MONITORING→活動／結果→一般或人工停止完成，以及REVIEW／確認／取消／復位→新輪；標記、通道、色帶與公開資料一致。
- [x] 交叉驗準備阻塞後人工停止／開始期限到／factory例外交會，及人工停止後尚有衝突／警報；晚回事件不改定案、不覆蓋新輪。
- [x] 新讀取者重建一般／人工停止／啟動失敗／警報／取消／復位，與公開結果一致；保存故障恢復、完整保存才關閉、歷史1.1不改寫與資料保護政策不退化。
- [x] 六圖樣、本機契約helper拒判、排數、容量外黑格及LI7精確幾何，在scaling1.0／1.5、容量1／10／11／20與語言切換下共同成立。
- [x] LI6前景／焦點與新人工控制在整合候選重點回歸，設定、歷史查詢、保存恢復及關閉維持；無條件重跑無關長測不列要求。
- [x] 程式顯示契約版本、正式圖樣表、精確幾何表及本機可重現輸出同步為1.2；明確標示新舊幾何／圖樣不相容及舊資料語意。
- [x] 交接清楚區分Log監控就緒與ATE活動、說明monitor_start／check_start／check_finish由KVM_Log實作；Log不新增TCP、ACK或KVM辨識。
- [x] 本專案僅依輪次公開行為／磁碟重建與真正App／Tk輸出驗收；不要求獨立KVM回放、JetKVM、Dock、LabVIEW或現場ATE流程通過，不把外部回覆當完成前置。
- [x] 記錄本機環境、命令、通過／失敗與限制；先前1.1的69tests不作新行為證據。可說明先橋接後App的部署順序，但本票不要求外部部署或正式打包環境作新驗收門檻。
- [x] 所有票屬同一候選整合；單張功能完成不等於可對外部署半套1.2。未驗收既有UI暫稿不默採，父規格正文／狀態不因本票被自動修改或關閉。

## Blocked by

- https://github.com/Bowei1121/B518_205_207_ATE/issues/82
- https://github.com/Bowei1121/B518_205_207_ATE/issues/83
- https://github.com/Bowei1121/B518_205_207_ATE/issues/84

## LI8 implementation and acceptance result

- LI8 candidate: `codex/li8-local-integration-acceptance`.
- Integrated into `codex/log-instrument-1-2` at `577139ffb1b28c776c4e5a71b1bfea0c0e78971e` and pushed to GitHub and internal Gitea; both remote refs were verified at the same SHA.
- GitHub Issue #85 completion record: https://github.com/Bowei1121/B518_205_207_ATE/issues/85#issuecomment-6265834594.
- LI8 AC1–11 passed. Core/contract suite: 127 passed; real Tk M10 integration: 7 passed; real Tk/Quartz LI6 foreground regression: 1 passed. `compileall` and `git diff --check` passed.
- Commands, environment, limits, and evidence locations are recorded in [`LI8_LOCAL_ACCEPTANCE.md`](LI8_LOCAL_ACCEPTANCE.md) and [`li8-integration evidence index`](../evidence/li8-integration/README.md).
- No KVM_Log, JetKVM, Dock, LabVIEW, or field ATE acceptance is claimed. Parent Issue #77 remains open.
