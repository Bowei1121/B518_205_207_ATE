# QP2 本機驗收 — 2026-10-15

## 固定基準與 fixture

- Ticket #49 固定 review base：`94d98b192f5521bb27faa7d61c44fd10d766b737`，parents `31d08141add7bf9a936e701d99f193455bf40ede` 與 `8bf877bbb77c0f7dc15f9cd06081a239f9097045`。
- Runtime：macOS 10.16 x86_64、Python 3.8.10；OS disk cache 未控制。
- Fixture 命令：`python3 "B518 Log Solution/scripts/historical_event_capacity.py" prepare --root /private/tmp/qp2-benchmark-fixture --events 2000 --as-of 2026-10-13`。
- Fixture：2,000 筆合成事件、4 個邏輯來源/5 個實體檔、1,520 筆符合查詢範圍、16 頁、810,593 source bytes。App event source SHA-256 為 `4c073c3820cbe9a19a9e47d5c0c67dab58a4b5d4693e34d2aac1f84be2cc47a8`；本機 fixture manifest SHA-256 為 `b7a3ad7988a75845ea5f62f866968626903d007b98b4ce12b5b0eae54b2b93ad`。全部來源檔案 SHA-256 在量測後與 manifest 相同。
- QP1 v5 evidence 的 `0.13935 + 0.02216 s` 是固定基準 `31d0814` 對 QP1 v5 `8bf877b`；QP2 review base 是 merge commit `94d98b1`。QP2 下表另用 `94d98b1` 與 QP2 branch，沒有混用 QP1 v5 的固定基準數字。

## 首批可讀與完整準備：同口徑隔離測試

[`phase-benchmark.py`](phase-benchmark.py) 每次由新的 Python process 執行；baseline 呼叫固定 base 的 `HistoricalEventQueryService.submit`，每 10 ms 輪詢 `take_result`。QP2 同樣 submit/10 ms 輪詢，但先呼叫 `take_initial_result`。兩者用同 fixture、各自已建立且重用的暖 index；`digest=none`。取到結果後，兩版都透過正式 `get_page(1..5)` 取得前五頁共 500 筆並記錄實讀時間；QP2 再輪詢到 `take_result`。兩版都在 full completion 後，對第一筆 round event 呼叫 `get_detail`，detail 欄只量該單次呼叫；另列從 submit 到 detail 完成的總時間。時間從 submit 前起算。OS cache 未控制，這是短 fixture 本機 wall-clock 觀察。

三輪各版三個獨立 process 的原始值，單位秒；每輪均在無 Tk / 重測並行時以同一 fixture、各自已建立且重用的 index 執行。第二、三輪修正了 detail 欄位計時方式；第一輪的 submit/500-readable、五頁 API 與 full completion 原始值保留，但其 detail 值不可比較，因舊公式把五頁讀取後等待剩餘準備的時間也算進 detail。之前與 HM2 Tk 重測並行的 phase/official-runner 樣本全部 discard，不列入計算。

| Round / 版本/run | Submit → 可實讀500筆 | 五頁 API | Detail 單次呼叫 | Submit → 全部完成 | QP2 讀頁當下狀態 |
| --- | ---: | ---: | ---: | ---: | --- |
| 1 / base/1 | 0.301828 | 0.015302 | — | 0.286526 | 無分階段 API |
| 1 / QP2/1 | 0.315444 | 0.000067 | — | 0.415430 | `prepared_count=600`, `complete=false` |
| 1 / base/2 | 0.421114 | 0.023054 | — | 0.398060 | 無分階段 API |
| 1 / QP2/2 | 0.307584 | 0.000058 | — | 0.408413 | `prepared_count=600`, `complete=false` |
| 1 / base/3 | 0.234728 | 0.015468 | — | 0.219259 | 無分階段 API |
| 1 / QP2/3 | 0.228979 | 0.000167 | — | 0.327021 | `prepared_count=700`, `complete=false` |
| 2 / base/1 | 0.199500 | 0.012943 | 0.001478 | 0.186557 | 無分階段 API |
| 2 / QP2/1 | 0.195311 | 0.000162 | 0.002493 | 0.306120 | `prepared_count=500`, `complete=false` |
| 2 / base/2 | 0.213494 | 0.014931 | 0.000502 | 0.198563 | 無分階段 API |
| 2 / QP2/2 | 0.204069 | 0.000094 | 0.001134 | 0.303975 | `prepared_count=500`, `complete=false` |
| 2 / base/3 | 0.223586 | 0.015433 | 0.000647 | 0.208153 | 無分階段 API |
| 2 / QP2/3 | 0.253461 | 0.000041 | 0.001508 | 0.342009 | `prepared_count=600`, `complete=false` |
| 3 / base/1 | 0.259903 | 0.014739 | 0.000590 | 0.245163 | 無分階段 API |
| 3 / QP2/1 | 0.261328 | 0.000065 | 0.000679 | 0.351548 | `prepared_count=600`, `complete=false` |
| 3 / base/2 | 0.192317 | 0.012931 | 0.000540 | 0.179387 | 無分階段 API |
| 3 / QP2/2 | 0.193578 | 0.000037 | 0.000987 | 0.284553 | `prepared_count=600`, `complete=false` |
| 3 / base/3 | 0.182648 | 0.012867 | 0.000546 | 0.169781 | 無分階段 API |
| 3 / QP2/3 | 0.180127 | 0.000036 | 0.000688 | 0.279230 | `prepared_count=500`, `complete=false` |

第三輪中位數（各輪分列，未把主機波動較大的輪次混算）：

| 指標 | 固定 base `94d98b1` | QP2 | 觀察差異 |
| --- | ---: | ---: | ---: |
| 前500筆實際可讀 | 0.192317 s | 0.193578 s | QP2 約慢 0.66%，在此短 fixture 測量噪音內 |
| 首500發布後讀五頁 | 0.012931 s | 0.000037 s | 前500已物化，五頁 API 讀取量不同 |
| Detail 單次呼叫 | 0.000546 s | 0.000688 s | 三樣本短測，沒有顯著差異；同結果額外連續8次為 0.000675–0.001037 s |
| 全部準備完成 | 0.179387 s | 0.284553 s | QP2 約慢 58.6%，本機短 fixture 有可見額外背景準備成本 |

範圍限制：2,000-event fixture、每輪每版三個樣本、OS cache 未控制，跨輪首500及full completion時間波動明顯，不能推論大型歷史資料或普遍效能。第三輪首500中位數慢 0.66%，屬噪音內，不宣稱改善；full preparation 慢 58.6%，是本次需由 QP6 獨立判定的成本風險，不因 QP2 功能驗收通過而略過。detail 舊 32–36 ms 數字是錯誤計時欄位，已標為無效；後續兩輪只計 `get_detail()` 單次呼叫，沒有重現該異常。本結果不替代父規格成本門檻，也不能推論現場容量。

精確命令（`N=1,2,3`；baseline 與 QP2 各用暖 index）：

- `PYTHONPATH="/private/tmp/qp2-baseline/src" python3 docs/refactoring/evidence/query-preparation-qp2/phase-benchmark.py baseline /private/tmp/qp2-benchmark-fixture /private/tmp/qp2-base-official.sqlite3`
- `PYTHONPATH="/private/tmp/b518-qp2/B518 Log Solution/src" python3 docs/refactoring/evidence/query-preparation-qp2/phase-benchmark.py staged /private/tmp/qp2-benchmark-fixture /private/tmp/qp2-current-official.sqlite3`

這組 phase runner 沒有暫停 worker；`complete=false` 與實際 `prepared_count` 是讀頁時直接取得。額外的 Event-gate 測試在 QP2 初批發布後攔住實際後頁寫入，檢查 snapshot 的 `matching_events=501` refs、`prepared_events=500` rows，並證明 page6 尚未備妥；同時透過正式 page/detail API 讀前五頁及 detail。release 後 page6 row 寫入、page service 完成、`prepared_count=501`。真 Tk 對應案例亦在 gate 期間讀前五頁、選 detail、切語言；在第六頁等待時保留第5頁並顯示 loading，release後才跳到第6頁。

## 功能及 UI 驗收

從 `B518 Log Solution` 執行：

- `python3 scripts/run_tests.py test_historical_event_query` — 52 tests 全部通過。涵蓋 0/1/99/100/101/499/500/501 總數邊界、來源原 bytes、generation replace/cancel/close、初批可讀、snapshot真實prepared rows、fallback兩遍版本變更中止、背景錯誤保留與服務 ownership。
- `python3 scripts/run_tests.py test_historical_event_query test_historical_event_display test_historical_event_capacity test_round_retention` — 105 tests 全部通過（最終重跑 28.791 s）。
- `B518_TK_TESTS=1 python3 scripts/run_tests.py test_log_solution_ui.LogSolutionUiTests.test_real_tk_reads_five_pages_while_remaining_batches_are_paused` — 通過；真實 Tk 前五頁、detail、切換語言、後續頁等待/loading、背景 Event gate。
- `B518_TK_TESTS=1 PYTHONPATH=src:tests python3 -u -m unittest -v test_log_solution_ui.LogSolutionUiTests.test_real_tk_historical_pages_load_details_on_selection` — 通過。
- `B518_TK_TESTS=1 PYTHONPATH=src:tests python3 -u -m unittest -v test_log_solution_ui.LogSolutionUiTests.test_real_tk_history_query_latest_request_cancel_and_window_lifecycle` — 通過。
- `B518_TK_TESTS=1 PYTHONPATH=src:tests python3 -u -m unittest -v test_log_solution_ui.LogSolutionUiTests.test_real_tk_keeps_later_preparation_failure_visible` — 通過（1 test，1.417 s）；後續整理失敗原因留在狀態列，初批結果仍保留可讀。
- `python3 -m py_compile src/historical_event_query.py src/b518_log_solution.py src/language_catalog.py tests/test_historical_event_query.py tests/test_log_solution_ui.py` — 通過。
- `git diff --check` — 通過。

所有 Tk case 依序使用授權的 macOS WindowServer。官方容量 runner 的舊樣本曾與 HM2 Tk 重測並行，已全部 discard / no compare；本文件只採用後來的隔離 phase runner。這些結果可供 #49 ticket review；關閉子票仍需協調者確認完整票規與整合驗收，父規格的關閉條件另行判定。

## Review follow-up — fallback preparation gate

- Spec review found that the no-index fallback constructed its result with the default `preparation_complete=True`, even though only the first 500 summary rows had been persisted. The fallback now constructs the result with `preparation_complete=False` before publishing its initial result; `_finish_preparation()` remains the point that wakes page waiters after later batches finish.
- Added `test_fallback_page_service_waits_for_later_preparation_batch`: while the fallback worker is gated, the result reports 500/501 prepared rows, direct page 6 reads raise `HistoricalEventPageNotReady`, and the page service returns only after release. Passed.
- Added `test_real_tk_fallback_keeps_page_six_loading_until_prepared` for the UI loading/page-preservation path with the index disabled. This shell could not execute the Tk test: Python aborted during the test class's `tk.Tk()` setup (`Fatal Python error: Aborted`, `test_log_solution_ui.py:511`) before entering the test body. The pre-existing indexed-path true-Tk gate test remains separately recorded above.
- Re-ran the complete related non-Tk suites after the fix: `test_historical_event_query`, `test_historical_event_display`, `test_historical_event_capacity`, and `test_round_retention` — 106 tests passed in 32.945 s. `py_compile` and `git diff --check` passed.
