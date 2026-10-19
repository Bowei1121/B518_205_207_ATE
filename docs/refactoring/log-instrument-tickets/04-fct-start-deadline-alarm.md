## Parent

[父規格 #77：Log Solution 儀器狀態、人工停止與顯示契約 1.2](https://github.com/Bowei1121/B518_205_207_ATE/issues/77)

## What to build

現場實際使用的FCT配置採120秒；整輪到期仍無可信活動／結果時停止、NOTEST並警報待確認，人員確認後才本地完成；準備尚未返回也按開始期限處理。

同一條期限路徑包含profile更新／載入、受控時鐘裁決、警報操作、HMI與重建；不把DFU／BT一併改120，也不實作橋接確認。

主責使用者故事：37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50。
依父規格實作決策：7, 11, 12, 13, 14, 18, 19；測試決策：6, 7, 8, 11, 14。

本票只驗收本程式的公開輪次行為／磁碟資料與必要真App／Tk輸出；不要求KVM_Log、JetKVM或LabVIEW驗收。

## Acceptance criteria

- [x] 目標已存／匯入且實際選取的FCT profile確實採start=120秒；不只改新建預設，DFU／BT既有值保持，開始後修改設定不改本輪凍結期限。
- [x] 從接受開始監控計時、包含來源準備，不於MONITORING才重設；100秒才有可信活動不受舊30秒鎖定。
- [x] 開始期限到整輪仍無可信活動也無有效結果，停止收集、全部未開始格NOTEST，建立一次「未偵測到測試開始」警報與REVIEW，不自稱已證明ATE當機。
- [x] 準備工作仍阻塞時也於開始期限裁決，不能等到更長整輪上限才處理；後續來源成功／失敗不重新開始或覆寫已定案格位／原因。
- [x] 人員關閉警報視窗不等於確認；警報可確認時機須維持結果及停止一致性，人工確認且無其他待確認才本地COMPLETE／READY，不自動裁決其他衝突。
- [x] 部分位置已有可信活動或結果時不套用整輪完全無開始警報；其餘未開始格、測試期限及整輪上限依既有規則，已定案結果保留。
- [x] 到期限的該次輪詢先判deadline再讀來源；覆蓋期限前已接受、恰好到期才讀到、到期後遲到三類，不用來源自報時間挽回。
- [x] 事件及新讀取者重建保留期限、停止、警報與確認事實及雙語說明，結果可交付與保存成功分離。
- [x] 由受控時鐘與可阻塞來源及真正App警報操作驗證，不用真等120秒；未見監控就緒而需人工核對的橋接行為不列本票驗收。

## LI4 completion record

- B518/FCT 的建立、舊設定正規化、儲存、匯入、載入及實際開始凍結皆固定 start=120 秒；DFU/BT 值維持既有行為。
- deadline 從 accepted start 單調計時，涵蓋 source preparation；deadline polling 先裁決，再 poll source。空輪次停止並把未開始格寫為 NOTEST，建立單一警報並停在 AWAITING_REVIEW；部分活動不建立「整輪未開始」警報。人工 ack 才解除該警報的結果阻擋，晚到 preparation 不會重啟或改寫已裁決結果。
- Audit/session 測試從磁碟重新讀取 alarm、停止與 ack 事件；開始期限事件保留雙語 message ID 和中英文內容。
- 驗證：`PYTHONPATH=src /opt/anaconda3/bin/python3 -m unittest tests.test_machine_profiles tests.test_log_monitoring tests.test_round_start_preparation tests.test_monitoring_round tests.test_language_catalog -v` — 132 tests passed；新增雙語覆蓋後又執行 `tests.test_language_catalog` 與磁碟 audit 測試，共 10 tests passed。
- 真 App/Tk：`PYTHONPATH=src /opt/anaconda3/bin/python3 tools/smoke_li4_start_alarm_app.py` — macOS/Tk 8.6.12，使用 5 秒受控 monotonic deadline，未等待真實 120 秒；驗證真實 B518 App 視窗呈現兩格 NOTEST/REVIEW，Close 不會 ack，實際 Ack 後輪次 COMPLETE 且結果可交付。證據：`docs/refactoring/evidence/li4-real-app/{alarm-pending.png,main-review.png,main-complete.png,run.json}`。
- 真 Tk 回歸：`test_real_tk_notification_badge_stays_until_alarm_is_acknowledged` passed。`test_real_tk_close_keeps_conflict_and_alarm_actions_available` 初次在 LI4 source 嘗試兩次，均於既有 conflict-control hover hint 等待逾時，未抵達 alarm 行為斷言。2026-10-19 在同一 macOS/Tk 桌面環境以相同命令分別於 LI4 integration base `08f5d38` 與 source `cc4f75c` 重跑，兩邊各 1/1 passed；現有實證顯示初次 timeout 為間歇性桌面 hover 事件，未能重現為 LI4 回歸。另於 LI4 source 重跑 badge regression，1/1 passed。LI4 真 App 操作 smoke 通過：使用 5 秒受控 monotonic deadline，真實 B518 FCT App 畫面呈現兩格 NOTEST/REVIEW；關閉警報不會 ack，實際 ack 後輪次 COMPLETE 且結果可交付。證據位置：`B518 Log Solution/docs/refactoring/evidence/li4-real-app/`。
- 限制：只使用合成的等待來源與受控時鐘，沒有連接現場 ATE、bridge TCP、KVM_Log 或 JetKVM；這些不屬本票驗收範圍。

## Blocked by

- https://github.com/Bowei1121/B518_205_207_ATE/issues/78
