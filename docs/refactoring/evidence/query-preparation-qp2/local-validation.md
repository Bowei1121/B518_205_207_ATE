# QP2 本機驗收 — 2026-10-15

## 固定基準與 fixture

- Ticket #49 固定 review base：`94d98b192f5521bb27faa7d61c44fd10d766b737`，parents `31d08141add7bf9a936e701d99f193455bf40ede` 與 `8bf877bbb77c0f7dc15f9cd06081a239f9097045`。
- Runtime：macOS 10.16 x86_64、Python 3.8.10；OS disk cache 未控制。
- Fixture 命令：`python3 "B518 Log Solution/scripts/historical_event_capacity.py" prepare --root /private/tmp/qp2-benchmark-fixture --events 2000 --as-of 2026-10-13`。
- Fixture：2,000 筆合成事件、4 個邏輯來源/5 個實體檔、1,520 筆符合查詢範圍、16 頁、810,593 source bytes。App event source SHA-256 為 `4c073c3820cbe9a19a9e47d5c0c67dab58a4b5d4693e34d2aac1f84be2cc47a8`；本機 fixture manifest SHA-256 為 `b7a3ad7988a75845ea5f62f866968626903d007b98b4ce12b5b0eae54b2b93ad`。全部來源檔案 SHA-256 在量測後與 manifest 相同。
- QP1 v5 evidence 的 `0.13935 + 0.02216 s` 是固定基準 `31d0814` 對 QP1 v5 `8bf877b`；QP2 review base 是 merge commit `94d98b1`。QP2 下表另用 `94d98b1` 與 QP2 branch，沒有混用 QP1 v5 的固定基準數字。

## 首批可讀與完整準備：同口徑隔離測試

[`phase-benchmark.py`](phase-benchmark.py) 每次由新的 Python process 執行；baseline 呼叫固定 base 的 `HistoricalEventQueryService.submit`，每 10 ms 輪詢 `take_result`。QP2 同樣 submit/10 ms 輪詢，但先呼叫 `take_initial_result`。兩者用同 fixture、各自已建立且重用的暖 index；`digest=none`。取到結果後，兩版都透過正式 `get_page(1..5)` 取得前五頁共 500 筆，對第一筆 round event 呼叫 `get_detail`；QP2 隨後繼續輪詢到 `take_result`。時間從 submit 前起算。OS cache 未控制，這是短 fixture 本機 wall-clock 觀察。

每版三個獨立 process 的原始值，單位秒。這是 HM2 完成真 Tk slot 後、沒有 Tk/重測並行時的正式樣本；之前在 HM2 Tk 時段跑出的 phase/official-runner 樣本全部 discard，不列入計算。

| 版本/run | Submit → 可實讀500筆 | 五頁 API | Detail | Submit → 全部完成 | QP2 讀頁當下狀態 |
| --- | ---: | ---: | ---: | ---: | --- |
| base/1 | 0.191096 | 0.013718 | 0.000546 | 0.177378 | 無分階段 API |
| base/2 | 0.178604 | 0.013361 | 0.000583 | 0.165243 | 無分階段 API |
| base/3 | 0.190687 | 0.012828 | 0.000987 | 0.177859 | 無分階段 API |
| QP2/1 | 0.185237 | 0.000024 | 0.036137 | 0.220426 | `prepared_count=600`, `complete=false` |
| QP2/2 | 0.185375 | 0.000028 | 0.034333 | 0.218814 | `prepared_count=600`, `complete=false` |
| QP2/3 | 0.216581 | 0.000035 | 0.032209 | 0.247793 | `prepared_count=700`, `complete=false` |

三次中位數：

| 指標 | 固定 base `94d98b1` | QP2 | 觀察差異 |
| --- | ---: | ---: | ---: |
| 前500筆實際可讀 | 0.190687 s | 0.185375 s | QP2 約快 2.8% |
| 首500發布後讀五頁 | 0.013361 s | 0.000028 s | QP2 約少 99.8% |
| Detail 讀取 | 0.000583 s | 0.034333 s | QP2 有 32–36 ms 異常樣本，原因未定 |
| 全部準備完成 | 0.177378 s | 0.220426 s | QP2 約慢 24.3% |

範圍限制：2,000-event fixture、每版三個樣本、OS cache 未控制，不能推論大型歷史資料或普遍效能。此 fixture 的首500筆實讀時間約快 2.8%；QP2 把五頁 API 讀取成本移至初批發布，且讀頁時後續背景仍未完成。QP2 full preparation 中位數慢 24.3%；首批到完整完成約多 35 ms，與額外走訪剩餘頁面一致，但本次沒有 profiling 來判定具體 SQL、鎖或記憶體成因。QP2 detail 有 32–36 ms 三筆異常樣本，原因未定，不拿來作 detail 效能結論。這不是整體效能改善證據。

精確命令（`N=1,2,3`；baseline 與 QP2 各用暖 index）：

- `PYTHONPATH="/private/tmp/qp2-baseline/src" python3 docs/refactoring/evidence/query-preparation-qp2/phase-benchmark.py baseline /private/tmp/qp2-benchmark-fixture /private/tmp/qp2-base-official.sqlite3`
- `PYTHONPATH="/private/tmp/b518-qp2/B518 Log Solution/src" python3 docs/refactoring/evidence/query-preparation-qp2/phase-benchmark.py staged /private/tmp/qp2-benchmark-fixture /private/tmp/qp2-current-official.sqlite3`

這組 phase runner 沒有暫停 worker；`complete=false` 及 700/800 計數是在五頁讀完時直接由結果取得。額外的 Event-gate 測試會在 QP2 初批發布後攔住 `_prepare_remaining_query_batches`，確認 `prepared_count=500`、`preparation_complete=false` 時仍能實際讀取五頁、detail，釋放 gate 後才完成其餘頁。真 Tk 對應案例也在 gate 期間翻閱前五頁、選 detail、切換語言。

## 功能及 UI 驗收

從 `B518 Log Solution` 執行：

- `PYTHONPATH=src python3 -m unittest tests.test_historical_event_query` — 50 tests 全部通過。涵蓋 0/1/99/100/101/499/500/501 總數邊界、來源原 bytes、generation replace/cancel/close、初批可讀、背景錯誤保留與服務 ownership。
- `B518_TK_TESTS=1 PYTHONPATH=src:tests python3 -u -m unittest -v test_log_solution_ui.LogSolutionUiTests.test_real_tk_reads_five_pages_while_remaining_batches_are_paused` — 通過；真實 Tk 前五頁、detail、切換語言、背景 Event gate。
- `B518_TK_TESTS=1 PYTHONPATH=src:tests python3 -u -m unittest -v test_log_solution_ui.LogSolutionUiTests.test_real_tk_historical_pages_load_details_on_selection` — 通過。
- `B518_TK_TESTS=1 PYTHONPATH=src:tests python3 -u -m unittest -v test_log_solution_ui.LogSolutionUiTests.test_real_tk_history_query_latest_request_cancel_and_window_lifecycle` — 通過。
- `B518_TK_TESTS=1 PYTHONPATH=src:tests python3 -u -m unittest -v test_log_solution_ui.LogSolutionUiTests.test_real_tk_keeps_later_preparation_failure_visible` — 通過（1 test，1.417 s）；後續整理失敗原因留在狀態列，初批結果仍保留可讀。
- `python3 -m py_compile src/historical_event_query.py src/b518_log_solution.py src/language_catalog.py tests/test_historical_event_query.py tests/test_log_solution_ui.py` — 通過。
- `git diff --check` — 通過。

所有 Tk case 依序使用授權的 macOS WindowServer。官方容量 runner 的舊樣本曾與 HM2 Tk 重測並行，已全部 discard / no compare；本文件只採用後來的隔離 phase runner。這些結果可供 #49 ticket review；關閉子票仍需協調者確認完整票規與整合驗收，父規格的關閉條件另行判定。
