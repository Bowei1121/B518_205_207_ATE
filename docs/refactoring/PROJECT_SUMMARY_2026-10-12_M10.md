# 2026-10-12 M10 source 交付摘要

與當日既有摘要分開保存，因同工作樹另有未提交的架構討論；本票保護10/09、10/12摘要及未追蹤討論文件，不納入本票提交。

使用者前次認為M10仍缺全入口／多視窗整合並要求source先驗，全部source通過後可合併至B518-Log-Solution。此授權取代原bundle必須先完成的source合併門檻；正式發布／目標設備仍待驗，不宣稱通過。

本次固定review baseline95b791c2cf1a54b10db4f07cbc606ddd06db8280；程式修正4b6efd7、a1ece06、079b519。補真Tk可見notice、原診斷分區、全入口／資源盤點、五窗真實來源長流程、文字與診斷閱讀／選取保留、Session目錄初始化提示。最終程式／測試SHA079b5191598b39182ef6e7acd3269c3cc3d703a9。

第一次全套371tests／120.172秒有3項失敗：兩項原diagnostic-inline預期過時、一項notice等待map時提早關閉交錯。保留原有效行為斷言、改為外層+詳細診斷預期，並安全處理已關閉notice。最後6聚焦8.024秒、舊2項0.719/1.102秒皆通過，完整套件結果見M10 local-validation；完整成功後才合併。

正式bundle及目標OS/HMI/KVM接續見release-validation。所有產品故障與刪除回歸使用隔離暫存資料；沒有新增產品裁決、schema、平台、排程或發布方式。公司Gitea本次可達，兩目的地完整同步後才安全清理票分支。最終merge／main重跑／遠端直接query與保護檔案結果後補。

最後source全套371tests／114.119秒OK，catalog322/322、compileall/diff-check通過；無既有型別檢查設定。固定基準95b至079b519的Standards／Spec無未解source問題，文件核對另確認正式发布待驗與source合併門檻分開。


## 本機source合併與主線複驗（2026-10-12）

合併前兩目的地直接查得main95b791c2、票分支74019aec3b1e3df9ab83b92fb4c8cdd4e26bc438。確認目標工作樹沒有未提交變更後，以no-ff合併；實際merge SHA為`6c55fd24c8a8c4afc5da8b32edfb8a96a095e376`。合併未改最後079b519程式／測試內容，`git diff 079b519 HEAD -- 'B518 Log Solution/src' 'B518 Log Solution/tests'`為空。

主線由同一Python目錄執行完整命令，**371tests／111.476秒，OK**；compileall、diff-check及catalog322/322／零errors通過。完整source及main命令輸出分別提交於 M10 evidence/source-suite.txt與main-suite.txt。兩軸code-review與證據複審無未解必要source問題。

既存兩份摘要修改及未追蹤架構討論先限定路徑stash／備份，再原樣還原並逐檔SHA256確認一致；沒有加入本票提交。這些既存修改使最終工作樹不是完全乾淨，但本票沒有未提交程式／測試或交付文件。實際遠端最後query及票分支清理結果由下一交付紀錄追加。


## 遠端同步與安全清理（2026-10-12 09:25，Asia/Taipei）

推送後逐一 `git ls-remote <URL> refs/heads/B518-Log-Solution refs/heads/Multilingual/ticket-10`，GitHub `git@github.com:Bowei1121/B518_205_207_ATE.git`、Gitea `http://10.64.76.34:3000/8362/B518-205_207_ATE.git` 皆直接查得main `18f3a46d032f7c50d71341b1fd3634fe2500b272`（合併後結果文件提交），票分支74019ae已被main包含。兩遠端票分支正常delete後再直接query，均只回main行，確認票分支不存在。

本地第一次 `git branch -d`因過時github upstream被安全檢查拒絕，沒有改用強制刪除；對兩remote `fetch --prune`刷新已刪ref，再確認ancestry，`git branch -d Multilingual/ticket-10`成功。所有既有push目的地保留。正式Log Solution工作樹目前在B518-Log-Solution；沒有移除仍使用的主線／BT工作樹。

本節18f3a46是09:25收尾文件提交前的查詢，不是此最後文件commit的自我SHA。最後文件提交後會再push兩目的地、直接核對最終HEAD與票分支不存在，結果在回報提供；不將上述歷史query冒充目前HEAD。正式bundle／目標設備仍待驗，沒有發布／修改／關閉遠端Issue。
