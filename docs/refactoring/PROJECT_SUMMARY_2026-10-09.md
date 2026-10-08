# 專案摘要 — 2026-10-09

## 前次討論與查證脈絡

延續 [2026-10-08 專案摘要](PROJECT_SUMMARY_2026-10-08.md)。前次完成 M1 真正 Tk 滑鼠／鍵盤驗收及合併；M2、M3 已納入 GitHub 主線並各自完成必要測試與雙軸審查。使用者已指定公司 Gitea 在週一同步；Gitea 未直接查證前，相關多語言票分支須保留。M4 不應把前票同步收尾混入本票。

## M4：無輪次 App 事件雙語保存（GitHub #17）

- 2026-10-08 開始 M4，實際 Git 根目錄為 `B518-Log-Solution`，Python 專案在其子目錄 `B518 Log Solution/`。以 Git ancestry 確認 M1、M2、M3 已在主線；M2 merge `f128d9f963f60d416d0eaf5917fa5eda87408280`、M3 merge `fb4ffb2286d9c113511482b738a101a11616bd14`，M3 文件整合主線 SHA `648b0c2126aaa6ab29016f2f95deb24ca7c8145f`。固定 M4 Standards／Spec review 基準為 `648b0c2126aaa6ab29016f2f95deb24ca7c8145f`。
- 建立 `Multilingual/ticket-04`；無既有同名票分支。起始 GitHub 主線 SHA 為 `648b0c2`。GitHub 遠端 `github` 可用；`origin` 的 Gitea 位址 `10.64.76.34:3000` 於 10/08 直接查詢連線拒絕，依使用者明示例外延至週一處理，不移除此 push destination。
- 程式批次一 `98525237d0de16f3ec74487b3317ddbd95cca654` 建立版本化 App 事件持久資料契約及讀取器，已推送 GitHub 同名票分支。
- 程式批次二 `9ddfe11` 接上 `RoundCoordinator` 公開 App 記錄／狀態／重試入口、真正主頁 App 診斷入口，以及 App 紀錄納入正常保存與關閉協調；若保存失敗視窗保持開啟，可在關閉流程非阻塞重試。時間資料讀取器驗證 ISO 格式與時區；診斷詳細區明示事件時間、事件／訊息識別、捕捉參數及原始診斷。此批已在桌面 Tk 下完成 2 個實際 Tk 案例及 83 個聚焦測試，並已推送 GitHub。推送完成訊息已確認；仍須直接查詢 GitHub SHA 作為證據。
- M4 程式／測試批次 `7990759`（`test: isolate app diagnostic UI recovery cases`）已驗證並推送 GitHub `Multilingual/ticket-04`。完整含 Tk 命令 `B518_TK_TESTS=1 PYTHONPATH=src python3 scripts/run_tests.py` 通過 328 tests（83.591 秒）；`python3 -m compileall -q src tests` 及 `git diff --check` 通過。四個 M4 重點真 Tk 案例涵蓋診斷明細、語言偏好保存失敗、熱鍵／配置保存失敗、App 寫入故障保持關閉視窗與按鈕重試。UI 測試類別現在把 APP_ROOT、偏好與 App EventStore 隔離至暫存資料，並在清除前等待 App 保存及公開清理狀態；先前測試揭露一個 UI 失敗測試依賴使用者現有配置，已改用有效暫存路徑。
- M4 六項本機驗收證據、producer 清單、持久格式及範圍界線已記於 `docs/refactoring/evidence/multilingual-ticket-04/local-validation.md`；M4 ticket、拆票 README 及母規格適用覆蓋已更新。固定基準 `648b0c2126aaa6ab29016f2f95deb24ca7c8145f` 的 Standards／Spec 雙軸複審與最後文件提交仍待完成。型別檢查設定未找到，不宣稱通過。
- 首次沙盒真 Tk 執行曾於建窗後以 exit 134 中止；同一聚焦案例及最終完整套件皆在可存取桌面圖形工作階段通過。UI 測試隔離修正完成前的早期執行可能曾將測試啟動診斷追加到預設本機 App event journal；未檢視或刪除任何 App 資料。隔離後的最終驗證全程使用暫存 App 根目錄、偏好、事件、來源與輪次紀錄。
- GitHub 推送訊息確認 `Multilingual/ticket-04` 更新至 `7990759`，但最終仍須直接查詢 GitHub SHA。合併需等固定基準審查及文件完成；Gitea 仍延至週一，在直接確認其 SHA 前保留本地與 GitHub 票分支。
- 交付界線：M4 不處理 M5～M10 全部設定／衝突視窗翻譯、完整關閉文案政策、歷史訊息遷移、App 事件清理或 bundle 發布；不啟用任何 App 事件刪除。公司 Gitea 同步未完成前保留本地與 GitHub `Multilingual/ticket-04` 分支，不執行分支清理。
