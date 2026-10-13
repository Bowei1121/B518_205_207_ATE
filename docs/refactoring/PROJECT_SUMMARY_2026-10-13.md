# 專案摘要 — 2026-10-13

## 前次討論與結果

- 延續 2026-10-12 的多視窗語言更新與清理原因表述工作。C1（清理原因組 #33）已實作集中原因捕捉／呈現、新舊 ledger 相容讀取、未知原因安全說明與真正 Tk 查閱；C2（#34）與 C3（#35）正式 producer 遷移、C4（#36）全畫面整合仍是後續票。
- C1 固定審查基準為 `14d7c23195d66962b86b8b301cdcc587b3a15c3d`。最終程式／測試 SHA 為 `5cf609d7a4a168d3701490b2ce51b27bafe25d3e`，票分支最終文件提交為 `fc43073eafcfb47053b6948086d9754ef1588b58`。缺少目前語言資源時使用捕捉時保存英文的回歸測試先失敗、實作後通過；固定基準 Standards／Spec 複審無阻擋。
- 真正 Tk 桌面完整套件在程式／測試 SHA `5cf609d` 通過 394 項／145.474 秒；本機主線快轉合併後，最初一次套件執行停在既有提示視窗重開案例。受控 Tk 檢查確認提示視窗可見、確認按鈕持有焦點與模態 grab，Escape 能關閉視窗；隔離測試通過 1 項／2.444 秒。之後主線完整套件於 Python 3.11.7／Tk 8.6 通過 394 項／127.882 秒／結束碼 0，第一次停住未再重現，也未因該次停住修改產品或測試。

## C1 本機整合與遠端狀態

- 乾淨整合 worktree `/private/tmp/B518-C1-merge` 將 `B518-Log-Solution` 從 `14d7c23` fast-forward 至 `fc43073eafcfb47053b6948086d9754ef1588b58`，沒有建立 merge commit。主線完整含 Tk 套件通過後，透過既有 `origin` push destinations 推送主線；推送命令回報 Gitea 與 GitHub 均由 `14d7c23` 前進至 `fc43073`。
- 2026-10-13 08:33 Asia/Taipei 的 push 前直接 `ls-remote` 查詢兩個目的地都顯示主線 `14d7c23`、`LanguageRefresh/ticket-05` 為 `fc43073`。最終文件提交後再次直接查詢目的地的結果應記錄在交付回報，避免在本摘要內自引用文件提交 SHA。
- 正式 worktree `/Users/tsengbowei/Desktop/公司資料/專案/FQ III/2026/B518/專案名稱/3. 程式/0. PC/B518 Log Solution` 原有 `PROJECT_SUMMARY_2026-10-09.md` 與 `PROJECT_SUMMARY_2026-10-12.md` 未提交修改受到保護，沒有併入 C1。只使用乾淨整合 worktree 更新 C1 文件及本摘要。
- 尚未直接完成 final-document push 查詢前，不刪除 C1 票分支或其 worktree；不移除任何其他分支、worktree 或 push destination。

## C2（清理原因組 #34）

- C2 固定 review base 為 `d3068bff31fb1f99422121cf9d48e3c925a1c3c2`；查證 C1 最終程式 `5cf609d7a4a168d3701490b2ce51b27bafe25d3e` 是其祖先，且基準已含 C1 ledger 相容讀取、原因捕捉／呈現、原始診斷、英文回退、真 Tk 與審查完成證據。C1 先前提示視窗重開測試的暫停問題已在固定基準前以可見視窗／焦點／modal grab／Escape 操作及後續完整桌面套件驗證處理；本次 C2 另重新完成全套。
- 輪次清理成功／跳過／失敗、即時狀態及封存驗證 producer 現於正式產生點捕捉 C1 原因識別、參數、同筆英文／繁中與診斷；schema 2、active plans、刪除進度、可信封存時間、資格與路徑／完整性門檻維持。補強後符號連結、路徑不一致及未知檔案有專屬原因識別，仍維持原 skipped 與保留結果。App-event producer 留在 C3，完整畫面遷移留在 C4。
- 固定基準及 C2 版的 `tests.test_round_archival tests.test_round_retention` 均各 45 tests / OK。C2 code/test SHA `316fc7005b3e1ca4992da5601a9882b543228177` 的 Python 3.11.7 / Tk 8.6 桌面完整套件通過 394 tests / 143.542 s / exit 0；在本機快轉主線 SHA `657ce8a2f53aba543fac663217d2057f0abb489a` 再通過 394 tests / 168.394 s / exit 0。首次受限 runner 在 `tkinter.Tk()` 的 AppKit/LaunchServices `NSException`（exit 134）中止並記錄為失敗；相同全套之後在已授權桌面環境完整通過，未將中止當成功或跳過 Tk 案例。無專案既有型別檢查設定。
- 基準／C2 使用相同暫存 fixture 的正式清理入口，對照期限前／後、期限變更、受保護輪次、損壞封存、外部 symlink、目錄替換、初始計畫保存失敗，以及刪除完成後摘要保存失敗和全新讀取器恢復；所有正規化結果一致，外部檔案雜湊不變。最後 Spec 複審者獨立重跑五個延伸情境並確認一致。詳細 fixture／harness 證據見 [C2 local validation](evidence/retention-reason-ticket-02/local-validation.md)。
- C2 真 Tk 使用正式輪次封存及公開清理入口、隔離暫存資料、保存 ledger、全新 coordinator 讀取與既有 Settings 摘要視窗；雙語原因、原始診斷、磁碟 bytes 不變及 archive write failure/retry 有驗收證據。固定基準 Standards／Spec 雙軸複審無阻擋；非阻擋整理建議為移除 `_archive_failure` 未使用參數並考慮合併兩個小型捕捉包裝函式。
- C2 本機快轉後的主線已推送至 Gitea 與 GitHub。最後文件 SHA `344337f256f3ee45461ee7d7f0e108c1d96ef2be`；2026-10-13 09:47 Asia/Taipei 逐一直接查詢兩目的地皆回報主線 `344337f256f3ee45461ee7d7f0e108c1d96ef2be`，且 `LanguageRefresh/ticket-06` refs 均不存在。已用一般刪除移除已合併的本地／遠端票分支及乾淨 C2 專用 worktree；其他 C1、L1 及專案 worktree 保留。原先兩份主線 summary 修改另以 stash `4a27ee0f7dc51a60740a6efe24d16fbd426f53ae` 保護，待完成文件提交後原樣還原並驗證。

## 驗收界線

- C1 的原因表述只控制顯示，不參與清理資格；可信封存時間、App 原事件時間、期限、保存保護、路徑／符號連結、原子替換及 fsync 行為沿用既有契約。正式輪次／封存與 App 事件 producer 尚未分別由 C2／C3 遷移；C4 才負責全部畫面及父規格第二項完整驗收。
- 清理原因父規格第二項尚未完成。C2、C3、C4 未交付前，不宣稱全部清理原因雙語化或全 App 畫面整合完成。遠端 Issue #28 與各拆票均未修改或關閉。
