# 2026-10-12 M10 source 交付摘要

與當日既有摘要分開保存，因同工作樹另有未提交的架構討論；本票保護10/09、10/12摘要及未追蹤討論文件，不納入本票提交。

使用者前次認為M10仍缺全入口／多視窗整合並要求source先驗，全部source通過後可合併至B518-Log-Solution。此授權取代原bundle必須先完成的source合併門檻；正式發布／目標設備仍待驗，不宣稱通過。

本次固定review baseline95b791c2cf1a54b10db4f07cbc606ddd06db8280；程式修正4b6efd7、a1ece06、079b519。補真Tk可見notice、原診斷分區、全入口／資源盤點、五窗真實來源長流程、文字與診斷閱讀／選取保留、Session目錄初始化提示。最終程式／測試SHA079b5191598b39182ef6e7acd3269c3cc3d703a9。

第一次全套371tests／120.172秒有3項失敗：兩項原diagnostic-inline預期過時、一項notice等待map時提早關閉交錯。保留原有效行為斷言、改為外層+詳細診斷預期，並安全處理已關閉notice。最後6聚焦8.024秒、舊2項0.719/1.102秒皆通過，完整套件結果見M10 local-validation；完整成功後才合併。

正式bundle及目標OS/HMI/KVM接續見release-validation。所有產品故障與刪除回歸使用隔離暫存資料；沒有新增產品裁決、schema、平台、排程或發布方式。公司Gitea本次可達，兩目的地完整同步後才安全清理票分支。最終merge／main重跑／遠端直接query與保護檔案結果後補。

最後source全套371tests／114.119秒OK，catalog322/322、compileall/diff-check通過；無既有型別檢查設定。固定基準95b至079b519的Standards／Spec無未解source問題，文件核對另確認正式发布待驗與source合併門檻分開。
