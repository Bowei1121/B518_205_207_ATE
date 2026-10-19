# LI8：父規格 88 項故事責任與本機證據索引

此表按 `ticket-plan.json` 的主責故事分配，逐項連回主責票及其本機驗收證據。LI8 專屬項目另連到同一候選的整合驗收紀錄；外部 KVM、JetKVM、Dock、LabVIEW、ATE 驗收不屬本表前置。故事正文以規格原文摘錄。

| 故事 | 主責票 | 規格要求 | 驗收證據 |
| ---: | --- | --- | --- |
| 1 | LI1 | 以 READY 知道可以開始新一輪 | [LI1 ticket](01-ready-busy-preparation.md); `B518 Log Solution/docs/refactoring/evidence/li1-real-app/run.json` |
| 2 | LI1 | 上一輪結果在 READY 時持續可見直到下一輪開始 | [LI1 ticket](01-ready-busy-preparation.md); `B518 Log Solution/docs/refactoring/evidence/li1-real-app/run.json` |
| 3 | LI1 | 開始命令接受後立即鎖定本輪配置 | [LI1 ticket](01-ready-busy-preparation.md); `B518 Log Solution/docs/refactoring/evidence/li1-real-app/run.json` |
| 4 | LI1 | 所有開始入口在準備中拒絕重複建立輪次 | [LI1 ticket](01-ready-busy-preparation.md); `B518 Log Solution/docs/refactoring/evidence/li1-real-app/run.json` |
| 5 | LI1 | 在來源準備期間看到 BUSY／準備中 | [LI1 ticket](01-ready-busy-preparation.md); `B518 Log Solution/docs/refactoring/evidence/li1-real-app/run.json` |
| 6 | LI1 | 看到獨立 PREPARING 圖樣 | [LI1 ticket](01-ready-busy-preparation.md); `B518 Log Solution/docs/refactoring/evidence/li1-real-app/run.json` |
| 7 | LI1 | 只有 Log 完成來源準備後才取得監控就緒訊號 | [LI1 ticket](01-ready-busy-preparation.md); `B518 Log Solution/docs/refactoring/evidence/li1-real-app/run.json` |
| 8 | LI1 | 舊檔基準完成前不發布 MONITORING | [LI1 ticket](01-ready-busy-preparation.md); `B518 Log Solution/docs/refactoring/evidence/li1-real-app/run.json` |
| 9 | LI1 | 仍由自己掌握放料、治具與條碼準備 | [LI1 ticket](01-ready-busy-preparation.md); `B518 Log Solution/docs/refactoring/evidence/li1-real-app/run.json` |
| 10 | LI1 | RUNNING、準備中或待確認時的重複開始不改變本輪 | [LI1 ticket](01-ready-busy-preparation.md); `B518 Log Solution/docs/refactoring/evidence/li1-real-app/run.json` |
| 11 | LI1 | 來源準備工作可在背景執行且畫面可操作 | [LI1 ticket](01-ready-busy-preparation.md); `B518 Log Solution/docs/refactoring/evidence/li1-real-app/run.json` |
| 12 | LI1 | 來源稍後返回時遵守已定案的停止或逾時 | [LI1 ticket](01-ready-busy-preparation.md); `B518 Log Solution/docs/refactoring/evidence/li1-real-app/run.json` |
| 13 | LI1 | 本輪容量、位置映射、來源及期限使用同一份固定配置 | [LI1 ticket](01-ready-busy-preparation.md); `B518 Log Solution/docs/refactoring/evidence/li1-real-app/run.json` |
| 14 | LI8 | 以六種穩定黑白圖樣表達儀器狀態 | [LI8 local acceptance](LI8_LOCAL_ACCEPTANCE.md); `B518 Log Solution/tests/test_kvm_display_contract.py` and `B518 Log Solution/docs/refactoring/KVM_DISPLAY_CONTRACT.md` |
| 15 | LI8 | 待命、準備中、監控中、待確認、一般完成、人工停止各有明確圖樣 | [LI8 local acceptance](LI8_LOCAL_ACCEPTANCE.md); `B518 Log Solution/tests/test_kvm_display_contract.py` and `B518 Log Solution/docs/refactoring/KVM_DISPLAY_CONTRACT.md` |
| 16 | LI1 | MONITORING 只代表 Log 監控就緒 | [LI1 ticket](01-ready-busy-preparation.md); `B518 Log Solution/docs/refactoring/evidence/li1-real-app/run.json` |
| 17 | LI1 | COMPLETE 可包含不良或未測結果 | [LI1 ticket](01-ready-busy-preparation.md); `B518 Log Solution/docs/refactoring/evidence/li1-real-app/run.json` |
| 18 | LI1 | 有衝突、警報或啟動失敗時 REVIEW 優先 | [LI1 ticket](01-ready-busy-preparation.md); `B518 Log Solution/docs/refactoring/evidence/li1-real-app/run.json` |
| 19 | LI1 | 排數標記繼續獨立表示一排或兩排 | [LI1 ticket](01-ready-busy-preparation.md); `B518 Log Solution/docs/refactoring/evidence/li1-real-app/run.json` |
| 20 | LI1 | 容量外位置固定黑色 | [LI1 ticket](01-ready-busy-preparation.md); `B518 Log Solution/docs/refactoring/evidence/li1-real-app/run.json` |
| 21 | LI1 | 狀態標記與色帶由一致的輪次資料更新 | [LI1 ticket](01-ready-busy-preparation.md); `B518 Log Solution/docs/refactoring/evidence/li1-real-app/run.json` |
| 22 | LI2 | 人工停止後保留已取得的 PASS／FAIL 等終局結果 | [LI2 ticket](02-manual-stop-release.md); `B518 Log Solution/docs/refactoring/evidence/li2-real-app/run.json` |
| 23 | LI2 | 人工停止只將未完成位置定案為 STOPPED | [LI2 ticket](02-manual-stop-release.md); `B518 Log Solution/docs/refactoring/evidence/li2-real-app/run.json` |
| 24 | LI2 | 通道文字與色帶都保留 STOPPED | [LI2 ticket](02-manual-stop-release.md); `B518 Log Solution/docs/refactoring/evidence/li2-real-app/run.json` |
| 25 | LI2 | 由自己決定重工範圍 | [LI2 ticket](02-manual-stop-release.md); `B518 Log Solution/docs/refactoring/evidence/li2-real-app/run.json` |
| 26 | LI2 | 人工停止有獨立整輪識別 | [LI2 ticket](02-manual-stop-release.md); `B518 Log Solution/docs/refactoring/evidence/li2-real-app/run.json` |
| 27 | LI2 | 來源尚未建立時人工停止也能形成全部配置位置的 STOPPED 結果 | [LI2 ticket](02-manual-stop-release.md); `B518 Log Solution/docs/refactoring/evidence/li2-real-app/run.json` |
| 28 | LI2 | 準備中按停止立即停止本輪 | [LI2 ticket](02-manual-stop-release.md); `B518 Log Solution/docs/refactoring/evidence/li2-real-app/run.json` |
| 29 | LI2 | 停止後的延遲來源成功或失敗不覆蓋已定案結果與原因 | [LI2 ticket](02-manual-stop-release.md); `B518 Log Solution/docs/refactoring/evidence/li2-real-app/run.json` |
| 30 | LI2 | 人工停止時仍未處理的衝突與警報保持 REVIEW | [LI2 ticket](02-manual-stop-release.md); `B518 Log Solution/docs/refactoring/evidence/li2-real-app/run.json` |
| 31 | LI2 | 人工停止後仍能逐項處理可信同輪衝突 | [LI2 ticket](02-manual-stop-release.md); `B518 Log Solution/docs/refactoring/evidence/li2-real-app/run.json` |
| 32 | LI2 | 重複停止或重複處理已完成操作不重複定案 | [LI2 ticket](02-manual-stop-release.md); `B518 Log Solution/docs/refactoring/evidence/li2-real-app/run.json` |
| 33 | LI2 | 人工停止快照與磁碟重建都保留 manual_stop 原因 | [LI2 ticket](02-manual-stop-release.md); `B518 Log Solution/docs/refactoring/evidence/li2-real-app/run.json` |
| 34 | LI2 | 結果可交付不額外等待 Session、audit 或封存全部成功 | [LI2 ticket](02-manual-stop-release.md); `B518 Log Solution/docs/refactoring/evidence/li2-real-app/run.json` |
| 35 | LI2 | 缺少可靠來源同輪證據的候選維持既有處置 | [LI2 ticket](02-manual-stop-release.md); `B518 Log Solution/docs/refactoring/evidence/li2-real-app/run.json` |
| 36 | LI5 | 取消本輪時保留原結果及處理紀錄 | [LI5 ticket](05-cancel-unverified-round.md); `B518 Log Solution/docs/refactoring/evidence/li5-real-app/run.json` |
| 37 | LI4 | FCT 等待開始的期限先採 120 秒 | [LI4 ticket](04-fct-start-deadline-alarm.md); `B518 Log Solution/docs/refactoring/evidence/li4-real-app/run.json` |
| 38 | LI4 | FCT 期限從接受開始監控起算並包含來源準備 | [LI4 ticket](04-fct-start-deadline-alarm.md); `B518 Log Solution/docs/refactoring/evidence/li4-real-app/run.json` |
| 39 | LI4 | 更新機台實際選取的已存 FCT profile | [LI4 ticket](04-fct-start-deadline-alarm.md); `B518 Log Solution/docs/refactoring/evidence/li4-real-app/run.json` |
| 40 | LI4 | DFU 與 BT 保留各自已配置的開始期限 | [LI4 ticket](04-fct-start-deadline-alarm.md); `B518 Log Solution/docs/refactoring/evidence/li4-real-app/run.json` |
| 41 | LI4 | 整輪開始期限內完全無可信活動且無有效結果時收到明確警報 | [LI4 ticket](04-fct-start-deadline-alarm.md); `B518 Log Solution/docs/refactoring/evidence/li4-real-app/run.json` |
| 42 | LI4 | 整輪未開始警報出現時停止收集並將未開始格定案 NOTEST | [LI4 ticket](04-fct-start-deadline-alarm.md); `B518 Log Solution/docs/refactoring/evidence/li4-real-app/run.json` |
| 43 | LI4 | 全輪未開始警報必須人工確認 | [LI4 ticket](04-fct-start-deadline-alarm.md); `B518 Log Solution/docs/refactoring/evidence/li4-real-app/run.json` |
| 44 | LI4 | 警報文案描述未偵測到測試開始 | [LI4 ticket](04-fct-start-deadline-alarm.md); `B518 Log Solution/docs/refactoring/evidence/li4-real-app/run.json` |
| 45 | LI4 | 警報確認且無其他待確認後才見可交付狀態 | [LI4 ticket](04-fct-start-deadline-alarm.md); `B518 Log Solution/docs/refactoring/evidence/li4-real-app/run.json` |
| 46 | LI4 | 部分位置已有活動或結果時不套用全輪完全未開始警報 | [LI4 ticket](04-fct-start-deadline-alarm.md); `B518 Log Solution/docs/refactoring/evidence/li4-real-app/run.json` |
| 47 | LI4 | 已開始位置繼續使用測試期限與整輪監控上限 | [LI4 ticket](04-fct-start-deadline-alarm.md); `B518 Log Solution/docs/refactoring/evidence/li4-real-app/run.json` |
| 48 | LI4 | 到期限先判逾時再讀該次來源 | [LI4 ticket](04-fct-start-deadline-alarm.md); `B518 Log Solution/docs/refactoring/evidence/li4-real-app/run.json` |
| 49 | LI4 | 到期後才讀到的證據或來源自報時間不能挽回已到期狀態 | [LI4 ticket](04-fct-start-deadline-alarm.md); `B518 Log Solution/docs/refactoring/evidence/li4-real-app/run.json` |
| 50 | LI4 | 期限前已接受的可信活動及終局結果保留 | [LI4 ticket](04-fct-start-deadline-alarm.md); `B518 Log Solution/docs/refactoring/evidence/li4-real-app/run.json` |
| 51 | LI1 | 快速完成或只提供最終結果的來源不必先出現 TESTING | [LI1 ticket](01-ready-busy-preparation.md); `B518 Log Solution/docs/refactoring/evidence/li1-real-app/run.json` |
| 52 | LI1 | 每格 TESTING／COMPLETING 或有效結果能作為該格活動證據 | [LI1 ticket](01-ready-busy-preparation.md); `B518 Log Solution/docs/refactoring/evidence/li1-real-app/run.json` |
| 53 | LI1 | 只取得確實觀察到活動的通道 | [LI1 ticket](01-ready-busy-preparation.md); `B518 Log Solution/docs/refactoring/evidence/li1-real-app/run.json` |
| 54 | LI1 | WAITING／NOTEST／TIMEOUT／STOPPED 不單獨表示 ATE 曾開始 | [LI1 ticket](01-ready-busy-preparation.md); `B518 Log Solution/docs/refactoring/evidence/li1-real-app/run.json` |
| 55 | LI3 | 配置或路徑驗證失敗顯示異常待確認 | [LI3 completion](03-startup-failure-reset-completion.md); `docs/refactoring/log-instrument-tickets/evidence/LI3-prior-result-review.png` |
| 56 | LI3 | 開始尚未被接受的失敗只記為失敗請求及 App 異常 | [LI3 completion](03-startup-failure-reset-completion.md); `docs/refactoring/log-instrument-tickets/evidence/LI3-prior-result-review.png` |
| 57 | LI3 | 輪次已接受後來源準備失敗保留失敗輪次與原因 | [LI3 completion](03-startup-failure-reset-completion.md); `docs/refactoring/log-instrument-tickets/evidence/LI3-prior-result-review.png` |
| 58 | LI3 | 啟動失敗不產生產品 FAIL 或人工停止完成 | [LI3 completion](03-startup-failure-reset-completion.md); `docs/refactoring/log-instrument-tickets/evidence/LI3-prior-result-review.png` |
| 59 | LI3 | 錯誤原因與原始診斷能在 HMI 查閱 | [LI3 completion](03-startup-failure-reset-completion.md); `docs/refactoring/log-instrument-tickets/evidence/LI3-prior-result-review.png` |
| 60 | LI3 | 排除問題、確認並復位後才回 READY | [LI3 completion](03-startup-failure-reset-completion.md); `docs/refactoring/log-instrument-tickets/evidence/LI3-prior-result-review.png` |
| 61 | LI3 | 復位保留所有既有結果、錯誤與處理紀錄 | [LI3 completion](03-startup-failure-reset-completion.md); `docs/refactoring/log-instrument-tickets/evidence/LI3-prior-result-review.png` |
| 62 | LI3 | 已建立的失敗輪次在復位時取消，未建立者結束失敗請求 | [LI3 completion](03-startup-failure-reset-completion.md); `docs/refactoring/log-instrument-tickets/evidence/LI3-prior-result-review.png` |
| 63 | LI3 | 復位後仍須明確開始新輪 | [LI3 completion](03-startup-failure-reset-completion.md); `docs/refactoring/log-instrument-tickets/evidence/LI3-prior-result-review.png` |
| 64 | LI3 | App 層啟動失敗可優先顯示 REVIEW，即使當下沒有新輪 | [LI3 completion](03-startup-failure-reset-completion.md); `docs/refactoring/log-instrument-tickets/evidence/LI3-prior-result-review.png` |
| 65 | LI3 | 未完整保存的失敗輪仍依原有機制追蹤與補存 | [LI3 completion](03-startup-failure-reset-completion.md); `docs/refactoring/log-instrument-tickets/evidence/LI3-prior-result-review.png` |
| 66 | LI5 | 下一輪與上一輪的事件保持隔離 | [LI5 ticket](05-cancel-unverified-round.md); `B518 Log Solution/docs/refactoring/evidence/li5-real-app/run.json` |
| 67 | LI6 | 需要看畫面的指定事件發生時視窗提升到前面 | [LI6 ticket](06-foreground-without-focus.md); `B518 Log Solution/docs/refactoring/evidence/li6-foreground/run.json` |
| 68 | LI6 | 視窗提升不強制取得鍵盤焦點 | [LI6 ticket](06-foreground-without-focus.md); `B518 Log Solution/docs/refactoring/evidence/li6-foreground/run.json` |
| 69 | LI6 | Log 不永久置頂 | [LI6 ticket](06-foreground-without-focus.md); `B518 Log Solution/docs/refactoring/evidence/li6-foreground/run.json` |
| 70 | LI6 | 同批事件合併提升且狀態未變時不隨輪詢反覆提升 | [LI6 ticket](06-foreground-without-focus.md); `B518 Log Solution/docs/refactoring/evidence/li6-foreground/run.json` |
| 71 | LI6 | 以真正桌面測試檢查前景與焦點 | [LI6 ticket](06-foreground-without-focus.md); `B518 Log Solution/docs/refactoring/evidence/li6-foreground/run.json` |
| 72 | LI7 | 移除 KVM RESULT 字樣並將左定位點移到第一格正上方 | [LI7 ticket](07-left-locator-geometry.md); `B518 Log Solution/docs/refactoring/evidence/li7-geometry/README.md` and `escalated-desktop-20261019/li7-geometry-matrix.json` |
| 73 | LI7 | 新左定位點保留大小、不對稱圖樣與白色留白 | [LI7 ticket](07-left-locator-geometry.md); `B518 Log Solution/docs/refactoring/evidence/li7-geometry/README.md` and `escalated-desktop-20261019/li7-geometry-matrix.json` |
| 74 | LI7 | 右定位點、排數格、狀態格與色帶位置保持 | [LI7 ticket](07-left-locator-geometry.md); `B518 Log Solution/docs/refactoring/evidence/li7-geometry/README.md` and `escalated-desktop-20261019/li7-geometry-matrix.json` |
| 75 | LI7 | 新定位點不被父框裁切、不與其他標記重疊 | [LI7 ticket](07-left-locator-geometry.md); `B518 Log Solution/docs/refactoring/evidence/li7-geometry/README.md` and `escalated-desktop-20261019/li7-geometry-matrix.json` |
| 76 | LI7 | 1.0／1.5 Tk scaling 與不同容量都通過本機幾何驗證 | [LI7 ticket](07-left-locator-geometry.md); `B518 Log Solution/docs/refactoring/evidence/li7-geometry/README.md` and `escalated-desktop-20261019/li7-geometry-matrix.json` |
| 77 | LI8 | 契約版本、圖樣表、幾何表及本機範例同步為 1.2 | [LI8 local acceptance](LI8_LOCAL_ACCEPTANCE.md); `B518 Log Solution/tests/test_kvm_display_contract.py` and `B518 Log Solution/docs/refactoring/KVM_DISPLAY_CONTRACT.md` |
| 78 | LI2 | 新舊保存資料依各自版本語意讀取且不重寫舊資料 | [LI2 ticket](02-manual-stop-release.md); `B518 Log Solution/docs/refactoring/evidence/li2-real-app/run.json` |
| 79 | LI8 | 新的事件與警報延續繁中／英文說明及原始診斷 | [LI8 local acceptance](LI8_LOCAL_ACCEPTANCE.md); `B518 Log Solution/tests/test_kvm_display_contract.py` and `B518 Log Solution/docs/refactoring/KVM_DISPLAY_CONTRACT.md` |
| 80 | LI8 | 既有設定、查詢、保存恢復與關閉流程維持 | [LI8 local acceptance](LI8_LOCAL_ACCEPTANCE.md); `B518 Log Solution/tests/test_kvm_display_contract.py` and `B518 Log Solution/docs/refactoring/KVM_DISPLAY_CONTRACT.md` |
| 81 | LI8 | 主要業務測試經既有輪次公開操作及快照驗證 | [LI8 local acceptance](LI8_LOCAL_ACCEPTANCE.md); `B518 Log Solution/tests/test_kvm_display_contract.py` and `B518 Log Solution/docs/refactoring/KVM_DISPLAY_CONTRACT.md` |
| 82 | LI8 | 用受控時鐘及可阻塞來源穩定驗證臨界時序 | [LI8 local acceptance](LI8_LOCAL_ACCEPTANCE.md); `B518 Log Solution/tests/test_kvm_display_contract.py` and `B518 Log Solution/docs/refactoring/KVM_DISPLAY_CONTRACT.md` |
| 83 | LI8 | 由新讀取者重建磁碟紀錄並比對對外結果 | [LI8 local acceptance](LI8_LOCAL_ACCEPTANCE.md); `B518 Log Solution/tests/test_kvm_display_contract.py` and `B518 Log Solution/docs/refactoring/KVM_DISPLAY_CONTRACT.md` |
| 84 | LI8 | 只用本程式可驗證的項目作為本專案驗收 | [LI8 local acceptance](LI8_LOCAL_ACCEPTANCE.md); `B518 Log Solution/tests/test_kvm_display_contract.py` and `B518 Log Solution/docs/refactoring/KVM_DISPLAY_CONTRACT.md` |
| 85 | LI8 | 取得清楚的輸出圖樣、幾何與狀態語意交接 | [LI8 local acceptance](LI8_LOCAL_ACCEPTANCE.md); `B518 Log Solution/tests/test_kvm_display_contract.py` and `B518 Log Solution/docs/refactoring/KVM_DISPLAY_CONTRACT.md` |
| 86 | LI8 | KVM 端有問題時由該專案提出具體回饋需求 | [LI8 local acceptance](LI8_LOCAL_ACCEPTANCE.md); `B518 Log Solution/tests/test_kvm_display_contract.py` and `B518 Log Solution/docs/refactoring/KVM_DISPLAY_CONTRACT.md` |
| 87 | LI8 | Log 專案不實作 check_start／check_finish 的 TCP server | [LI8 local acceptance](LI8_LOCAL_ACCEPTANCE.md); `B518 Log Solution/tests/test_kvm_display_contract.py` and `B518 Log Solution/docs/refactoring/KVM_DISPLAY_CONTRACT.md` |
| 88 | LI8 | 本批只涵蓋已確認的①～④ | [LI8 local acceptance](LI8_LOCAL_ACCEPTANCE.md); `B518 Log Solution/tests/test_kvm_display_contract.py` and `B518 Log Solution/docs/refactoring/KVM_DISPLAY_CONTRACT.md` |
