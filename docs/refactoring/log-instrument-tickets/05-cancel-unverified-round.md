## Parent

[父規格 #77：Log Solution 儀器狀態、人工停止與顯示契約 1.2](https://github.com/Bowei1121/B518_205_207_ATE/issues/77)

## What to build

操作員面對需人工核對的準備中停止／逾時，能在本程式確認必要事項、取消該輪並保留原結果，排除問題後明確開始新輪，沒有強制交付或自動重測捷徑。

擴充LI3失敗輪次取消能力到LI2人工停止與LI4準備逾時的本地操作路徑；不讓Log推測橋接有沒有看見MONITORING，不新增TCP、KVM輪次或遠端取消命令。

主責使用者故事：36, 66。
依父規格實作決策：4, 7, 17, 18, 19；測試決策：5, 6, 9, 11, 14。

本票只驗收本程式的公開輪次行為／磁碟資料與必要真App／Tk輸出；不要求KVM_Log、JetKVM或LabVIEW驗收。

## Acceptance criteria

- [x] 以準備中人工停止及準備逾時實際路徑展示本地取消／復位入口，處理既有必要待確認後由操作員明確取消，不以關閉視窗或換配置默認取消。
- [x] 取消保留原逐格結果、來源、停止／期限／警報原因及處理紀錄；不抹除、不覆寫、不把取消或軟體故障轉產品FAIL。
- [x] 不提供強制把不確定畫面當成本輪結果交付的按鈕；取消不等於替衝突選結果或確認未知同輪候選，既有證據及資料保護政策保持。
- [x] 取消結束後本地回可接受新輪的狀態；舊色帶即使保留也不帶可交付本輪資格，下一次明確開始產生新本地輪次、固定新配置並重新準備。
- [x] 舊準備工作、事件與保存回覆不能覆蓋新輪；重複取消／復位不重複定案，未保存輪仍依原政策追蹤。
- [x] 操作員決定重工範圍，Log不自動重測、不啟動ATE／治具，也不建立橋接／LabVIEW的輪次ID或ACK資料庫。
- [x] 由新讀取者可重建取消及後續新輪的獨立紀錄；已可靠保存的其他輪次不因本操作被一律刪除或禁止查核。
- [x] 公開入口及真App完成「準備中停止→必要確認→取消→新輪」及「準備逾時→警報確認→取消→新輪」；啟動故障復位路徑沿用LI3並做組合回歸。

## Blocked by

- https://github.com/Bowei1121/B518_205_207_ATE/issues/79
- https://github.com/Bowei1121/B518_205_207_ATE/issues/80
- https://github.com/Bowei1121/B518_205_207_ATE/issues/81

## LI5 implementation record

分支：`codex/li5-manual-cancel-restart`
基底：`313ef8a22394e3e55af27f272935862ef39d0ff1`
整合分支：`codex/log-instrument-1-2`
整合 commit：`3bc95142404e0b0f42438550097a4ebef3f5082d`

- 新增本機明確取消未確認輪次的操作，保留原逐格資料、audit 事件及停止／期限／警報原因；取消後才允許明確開始一個新輪次。來源尚未 ready 的人工停止和已確認的整輪 deadline，在取消前將 Start、快捷鍵及 Coordinator 公開 start 入口鎖定，狀態標記維持 REVIEW。
- 來源已 ready 的 LI2 正常人工停止既有放行語意保持；有待解衝突、未確認警報或未完成準備時不會因此解鎖。取消不能代替衝突選擇、警報確認或啟動故障復位。
- 新讀取者重建確認取消事件、舊輪結果及不交付資格；舊的阻塞來源返回後不改寫取消輪次或新輪。LI3 啟動故障復位、LI4 警報待確認及 audit projection 回歸包含在下列測試。

### 實際驗證

- `PYTHONPATH=src /opt/anaconda3/bin/python3 -m unittest tests.test_monitoring_round tests.test_audit_records tests.test_language_catalog tests.test_kvm_display_contract -q` — 109 tests，通過。
- `python3 -m compileall -q src tests` — 通過。
- `git diff --check` — 通過。
- `PYTHONPATH=src B518_LI5_EVIDENCE_DIR=docs/refactoring/evidence/li5-real-app /opt/anaconda3/bin/python3 tools/smoke_li5_manual_cancel_app.py` — 真正 B518 Tk App 通過；macOS 桌面，Python 3.11.7、Tk 8.6.12，進程 PID 5814。真實 Stop/Cancel/Start 操作驗證準備中停止→取消→新輪，以及準備逾時→實際警報 ACK→取消→新輪。擷取證明停止 review 時 Start disabled、timeout ACK 後且取消前 Start disabled、取消後 Start 可建立不同 round ID；舊來源完成 handoff 不會改寫舊取消輪。
- 真 App 截圖及執行明細：`B518 Log Solution/docs/refactoring/evidence/li5-real-app/`，包含 `manual-stop-review.png`、`manual-stop-cancelled.png`、`new-round-after-manual-stop.png`、`preparation-timeout-alarm.png`、`preparation-timeout-review.png`、`preparation-timeout-acknowledged.png`、`preparation-timeout-cancelled.png`、`new-round-after-timeout.png`、`run.json`。

### 範圍與限制

只使用合成的本地來源與受控計時；未連接 bridge TCP、KVM_Log、JetKVM、LabVIEW 或現場 ATE。整合分支已推送至 GitHub 與內部 Gitea；本機／遠端 SHA 與 Issue #82 關閉狀態於完成紀錄確認。
