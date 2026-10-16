# 專案摘要 — 2026-10-17

## 換日接續：可查證的前次結果

依據 `PROJECT_SUMMARY_2026-10-16.md`、現有規格及 Git 紀錄整理，不將其他工作階段的測試當成本次實跑。

- HF1–HF7 的實作、桌面驗收與主線整合已有文件紀錄；父票 #60 及子票已完成結案同步。正式 bundle／工廠 KVM 仍有各自的驗收範圍，不能以本地畫面替代。
- Slot／頂列第二輪需求已定稿，父規格 #68、ST1–ST8 #69–#76 已發布；本次未重新查核遠端票狀態，不宣稱目前均未開工。
- 工作目錄保留先前未提交的主 UI／UI 測試暫稿及 input-probe／window-bounds 證據；不納入本次文件提交。

## 本次架構分析與契約 1.2 對照

使用者要求先分析程式，再讀另一專案的 `LOG_SOLUTION_CONTRACT_1.2_PROPOSAL.md`，排序後再討論；未授權本輪實作產品。

- 基準：`B518-Log-Solution` `65cd07a0558842a82a0f5742998063a150b919a9` 加工作目錄 UI 暫稿。先讀 CONTEXT.md 與九份 ADR，再由主分析及獨立子代理分析程式；子代理未先讀 proposal。
- 純架構熱點為歷史查詢互動生命週期，其次 KVM 顯示責任與通知恢復投影。四個主要 module 的既有 ADR 分工仍適用，不建議全面重寫。
- 綜合建議排序：P0 C1＋C2 人工停止完整結果／放行；P1 C4 FCT profile（可獨立先落地）、C3 前景策略、C6＋C5 KVM 幾何與 1.2 發布；P2 通知恢復投影；P3 歷史查詢互動。這是分析建議，尚非使用者核可的實作設計。
- C1 必須同步考量稽核重建：`audit_records.read_round_audit` 目前只於 `finished` 設為結果已放行；不能只改快照與標記。準備中停止的完整格位、延遲來源返回／失敗、待確認與啟動失敗皆需覆蓋。
- C4 已有 profile 能力；120 秒是待現場實測候選。更改 migration default 不會自動更新已存 profile。Atlas 歸檔門檻基於 monitor.started，慢準備時不能直接等同 accepted start。
- C3 的 deiconify／lift 不呼叫 focus_force，仍須原生桌面驗證是否保留 ATE 焦點；不能只靠假 root。
- C6 第一格現為 x=0，須同時驗證定位點左緣及外側白留白。移動上方定位點不能保證偵測所有只遮色帶的視窗形狀；consumer 必須保留格位可讀性驗證。橋接先支援新舊距離，才部署 Log Solution 1.2。
- 完整 HTML 報告按技能寫在 OS 暫存目錄，未放進 repo：`/var/folders/gk/zpblb4q57bl24pt55p1m933h0000gn/T/architecture-review-20261017-004512.html`。包括六個優先候選前後圖及兩項後排探索方向。

## 本次實跑驗證

`python3 "B518 Log Solution/scripts/run_tests.py" test_kvm_display_contract test_monitoring_round test_round_start_preparation test_configured_monitor`

結果：69 tests，12.716 秒，OK。驗證的是現有 1.1 基準；未修改產品、未執行完整 Tk／JetKVM／1.2 驗收。HTML 已檢查六張候選卡及 C1–C6 內容；本機 `open` 無可用預設 HTML 應用，已透過 Codex 排入開啟檔案。
