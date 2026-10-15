# QP1 本機驗收 — 2026-10-15

## 固定基準與環境

- 審查基準：`31d08141add7bf9a936e701d99f193455bf40ede`。
- 執行環境：macOS 10.16 x86_64、Python 3.8.10、Tk 8.6。
- 成本 fixture：`historical_event_capacity.py prepare --events 2000 --as-of 2026-10-13`；2,000 筆合成事件、4 個來源、1,520 筆符合 90 天查詢、16 頁。來源總大小 810,593 bytes，manifest SHA-256：`4c073c3820cbe9a19a9e47d5c0c67dab58a4b5d4693e34d2aac1f84be2cc47a8`（manifest 中各來源另列 SHA-256）。
- 基準與本版使用同 fixture、同 runtime、同查詢、同一 capacity runner；各以獨立索引建置，之後各重查三次。digest 設為 `none`，成本包含公開 `HistoricalEventQueryService` 提交、查詢結果建立、首頁與單筆詳細讀取；OS 快取未控制，不宣稱冷讀。

## 結果

| 指標 | 固定基準初次建立 | QP1 初次建立 | 固定基準重查中位數 | QP1 重查中位數 |
| --- | ---: | ---: | ---: | ---: |
| 查詢時間 | 0.839 s | 1.699 s | 0.13576 s | 0.34833 s |
| 查詢快照大小 | 3,231,744 B | 2,064,384 B | 3,231,744 B | 471,040 B |
| 複製完整事件 JSON | — | — | 1,520 筆 / 1,440,256 B | 0 筆 / 0 B |
| 來源讀取 | 1,606,298 B | 1,606,298 B | 0 B | 0 B |
| 重用來源數 | 0 | 0 | 4 | 4 |
| 持久索引大小 | 4,894,720 B | 5,619,712 B | 4,894,720 B | 5,619,712 B |

重查快照縮小 85.4%，原文 JSON 的逐查詢複製由 1,440,256 bytes 降至 0。此小 fixture 的重查時間中位數由 0.13576 s 增至 0.34833 s（2.56×）；首建由 0.839 s 增至 1.699 s，因此本次沒有宣稱耗時改善，需由整合驗收評估此交易成本。持久索引增加約 14.8%，用來保存共享不可變內容。QP1 初次建置寫入 2,000 個內容版本、1,889,544 bytes；未變來源的後續查詢新增 0 個版本。QP1 後續修正以 `history_query_contents(query_id, content_id)` 記錄每個查詢快照實際引用的內容；只有來源索引與所有活動查詢都不再引用時才回收。其他查詢仍開啟不會延後無關舊版本回收。上表效能數字是逐查詢引用表加入前的 QP1 v4 短 fixture 測量，包含已觀察到的 2.56× 重查耗時退步；本次 lifecycle 修正未重跑 capacity benchmark，這些數字不代表 schema v5 的新量測。

## 驗證命令與結果

- `PYTHONPATH=src python3 -m unittest tests.test_historical_event_query -v`：46 tests，全部通過。包括 A/B 查詢分別持有新舊 generation、關閉 A 後即回收舊內容且 B 仍可讀、abandoned query lease 回收，以及重查內容複製計數為 0。
- `B518_TK_TESTS=1 PYTHONPATH=src:tests python3 -m unittest tests.test_log_solution_ui.LogSolutionUiTests.test_real_tk_historical_reader_selects_and_localizes_disk_records_without_rewriting -v`：真實 App/Tk 單案例通過（1 test，4.168 s）；確認公開查詢、選取與語言切換、來源 bytes 未改寫及關閉流程。
- `python3 -m py_compile src/historical_event_query.py scripts/historical_event_capacity.py`：通過。
- 公開成本量測以 `scripts/historical_event_capacity.py sample` 執行，基準程式取固定基準 commit；測量為三次重查樣本。只跑短 fixture，沒有啟動全套或極端容量流程。

尚未執行：完整桌面 suite、216 萬筆大型補驗、工廠/設備驗收。以上不屬於 QP1 必要合併門檻。
