# LI3 #80 完成紀錄

分支：`codex/li3-startup-failure-reset`  
基底：`ba026325f167a67f8f623aebd0849d8dccc5e550`  
狀態：實作與本機驗收完成；待整合分支同步、遠端推送及 GitHub Issue 更新。

## 修改與驗收對照

- 接受前啟動錯誤記入 App 診斷紀錄，投影為持續 REVIEW；不建立輪次，且遮蔽上一輪 COMPLETE 的可用結果。復位前所有啟動入口均鎖定；人工復位結束失敗請求，不自動重試。
- 接受後 factory／prepare 例外進入 `AWAITING_REVIEW`，停止收集並保留原始診斷與輪次事件；不合成產品 FAIL。明確復位會記錄失敗輪取消與復位事件，磁碟重建得到已取消狀態；之後須再次明確開始才建立新輪。
- Tk 畫面提供中英文錯誤說明及「確認並復位」按鈕。關閉提示不會解除待確認狀態；復位不自動啟動來源。
- 保留先完成人工停止的輪次語意；晚到的來源錯誤不覆蓋 manual stop。來源尚未回報 ready 的人工停止輪次在 close/archive 後仍受保護，供人工核對。

## 實際驗證

- `PYTHONPATH=src python3 -m unittest tests.test_monitoring_round tests.test_round_start_preparation -q` — 64 tests，通過。
- `PYTHONPATH=src python3 -m unittest tests.test_audit_records tests.test_app_event_store tests.test_kvm_display_contract -q` — 61 tests，通過。
- `B518_TK_TESTS=1 PYTHONPATH=src /opt/anaconda3/bin/python3 -m unittest tests.test_m10_integration -v` — 真正桌面 Tk 整合測試 6 tests，通過；在桌面登入工作階段執行。
- `python3 -m compileall -q src tests` — 通過。
- `git diff --check` — 通過。
- 另以 `screencapture` 擷取畫面時，macOS 未提供可用視窗／顯示影像；未附截圖。Tk 測試實際建立及操作視窗，完整測試輸出為驗收紀錄。

## 範圍與限制

測試涵蓋本程式公開輪次行為、App/Tk 畫面、audit/App 診斷持久化及磁碟重建。KVM_Log、JetKVM、Dock 自動化、LabVIEW、現場 ATE 流程不屬本票驗收。此紀錄不代表已推送、整合或關閉 Issue #80。
