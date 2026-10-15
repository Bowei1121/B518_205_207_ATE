# QP6 42-story matrix

Source: `docs/refactoring/query-result-preparation-tickets/README.md`, “使用者故事覆蓋”. Evidence IDs resolve to exact tests in `tests/test_historical_event_query.py`, `tests/test_historical_event_display.py`, `tests/test_historical_event_capacity.py`, `tests/test_log_solution_ui.py`, or to the benchmark report named below. Test names are the runnable evidence; the matrix does not claim factory acceptance.

| # | Requirement | Public owner / acceptance evidence |
|---:|---|---|
| 1 | 查詢不頻繁時也能快速開始閱讀，不必等待整批詳細資料整理完成。 | `HistoricalEventQueryService.take_initial_result`; `test_query_service_publishes_first_five_pages_before_remaining_work`; true Tk `test_real_tk_reads_five_pages_while_remaining_batches_are_paused`. |
| 2 | 先看到可靠總筆數。 | `HistoricalEventQueryResult.total_count`; `test_public_query_prepares_the_first_five_pages_at_count_boundaries`. |
| 3 | 第一次看到結果就知道全部頁數。 | `HistoricalEventQueryResult.page_count`; same boundary test verifies exact pages. |
| 4 | 總數是確定值而非預估。 | Exact source count before initial publication; same boundary test covers 0/1/99/100/101/499/500/501. |
| 5 | 最新前500筆先可讀，可連續查看前五頁。 | Initial batch API; `test_later_summary_rows_are_absent_until_background_batch_is_released`; true Tk `test_real_tk_reads_five_pages_while_remaining_batches_are_paused`. |
| 6 | 每頁維持100筆。 | `HistoricalEventQueryResult.page_size`; `test_exactly_one_hundred_events_stay_on_one_full_page`; boundary test. |
| 7 | 不足500筆時只顯示實際結果。 | Boundary test verifies 1/99/100/101/499 counts and page lengths. |
| 8 | 零筆時清楚顯示空結果。 | `test_empty_single_day_and_mixed_sources_keep_existing_source_precedence`; UI empty-vs-error covered by `test_real_tk_history_failed_query_reason_and_all_unreadable_sources`. |
| 9 | 總數與首批準備期間保留舊結果。 | True Tk `test_real_tk_history_query_latest_request_cancel_and_window_lifecycle`; old rows/details remain until latest result publishes. |
| 10 | 新條件、總數及首批一起替換。 | Same latest-request Tk test; `test_query_service_coalesces_pending_work_and_only_publishes_latest_result`; QP4 retry Tk test. |
| 11 | 後續批次在背景持續整理。 | `test_later_summary_rows_are_absent_until_background_batch_is_released`; `test_query_service_publishes_first_five_pages_before_remaining_work`. |
| 12 | 目前頁面優先載入。 | `test_requested_page_preempts_sequential_preparation_and_cache_stays_at_500`; true Tk `test_real_tk_qp3_cached_pages_detail_language_and_cancelled_requery`. |
| 13 | 選取詳細內容優先載入。 | `HistoricalEventDetailService`; `test_detail_service_coalesces_selection_and_discards_late_detail`; true Tk `test_real_tk_historical_pages_load_details_on_selection`. |
| 14 | 尚未備妥頁面明確顯示載入中。 | QP3/QP4 true Tk tests `test_real_tk_qp3_cached_pages_detail_language_and_cancelled_requery` and `test_real_tk_history_retry_resumes_fixed_snapshot_and_keeps_reading_page`. |
| 15 | 等待新頁時目前內容仍可閱讀。 | Same QP3 true Tk test verifies current page/details remain while page 6 loads. |
| 16 | 新事件不插入正在閱讀的結果。 | `test_persistent_query_result_stays_fixed_until_a_new_query`; `test_formal_app_save_stays_out_of_fixed_result_until_requery_without_flush`. |
| 17 | 再次查詢才更新結果集合。 | Same fixed-result and formal-save tests; true Tk latest-request test. |
| 18 | 來源清理後，已取得固定結果仍可讀原文。 | `test_official_app_event_cleanup_keeps_all_captured_snapshot_details`; true Tk `test_real_tk_fixed_history_coexists_with_official_app_event_cleanup`. |
| 19 | 切換語言保留頁面與選取，不重跑查詢。 | True Tk `test_real_tk_history_language_refresh_preserves_draft_snapshot_page_and_detail`; QP3 cached-page language case. |
| 20 | 首批發布前取消/失敗保留舊結果。 | True Tk `test_real_tk_history_query_latest_request_cancel_and_window_lifecycle`; query cancellation gate verifies prior result remains selected. |
| 21 | 首批發布後失敗保留新結果。 | `test_query_service_preserves_readable_result_and_error_after_later_batch_failure`; `test_fallback_keeps_published_snapshot_after_later_batch_failure_or_cancel`. |
| 22 | 失敗可見且有重試入口。 | True Tk `test_real_tk_history_retry_resumes_fixed_snapshot_and_keeps_reading_page`; `test_real_tk_history_failed_query_reason_and_all_unreadable_sources`. |
| 23 | 重試沿用相同固定版本。 | `test_retry_resumes_only_remaining_rows_from_the_same_fixed_snapshot`; true Tk retry test verifies source-version isolation. |
| 24 | 原版本無法恢復時要求重查，不偽造結果。 | `test_retry_refuses_to_recreate_a_missing_query_index`; UI retry Tk test. |
| 25 | 可修改條件重新送出。 | True Tk latest-request lifecycle test submits newer ranges after a pending/cancelled request. |
| 26 | 舊批次晚到不影響最新要求。 | `test_query_service_coalesces_pending_work_and_only_publishes_latest_result`; true Tk latest-request lifecycle test. |
| 27 | 取消、關窗或 App 退出後失效工作不發布或阻擋保存。 | `test_real_tk_history_query_latest_request_cancel_and_window_lifecycle`; true Tk `test_real_tk_close_waits_for_source_preparation_before_destroy`; `test_close_waits_responsively_and_cancellation_invalidates_old_completion`. |
| 28 | 操作員不需設定快取參數。 | Cache/page limits remain internal constants (`HISTORICAL_EVENT_QUERY_INITIAL_BATCH_SIZE`, `HISTORICAL_EVENT_QUERY_PAGE_SIZE`); `rg` of `src` found no operator-facing cache/page preference or control. |
| 29 | 列表快取最多500筆。 | `test_requested_page_preempts_sequential_preparation_and_cache_stays_at_500`; QP3 true Tk cache navigation case. |
| 30 | 詳細與原文不全量常駐記憶體。 | `test_public_query_returns_latest_hundred_in_stable_order` asserts query rows omit full event JSON; `test_query_snapshot_pages_all_events_and_loads_detail_only_on_request`; display `test_list_message_does_not_format_full_detail_until_record_is_selected`. |
| 31 | 重用未變更事件內容，減少重複完整複製。 | Persistent-index metrics tests and QP6 `historical-original-comparison.json`: warm baseline copied 100,415/574,711 event-JSON bytes; current copied 0. |
| 32 | 共用內容更新不改變舊結果。 | `test_indexed_requery_reclaims_unreferenced_generation_when_owner_closes`; `test_fixed_result_rejects_detail_after_official_same_path_journal_replace`. |
| 33 | 只回收無使用者引用的資料。 | `test_replacing_query_keeps_transferred_snapshot_alive`; `test_index_reclaims_contents_owned_only_by_abandoned_query`; `test_indexed_requery_reclaims_unreferenced_generation_when_owner_closes`. |
| 34 | App 重啟重用有效索引。 | `test_persistent_index_is_reused_by_a_new_query_service`; QP6 benchmark warm re-query has 0 parsed sources, 12 reused sources, 0 source bytes read. |
| 35 | 重開視窗不自動恢復上一個查詢。 | True Tk lifecycle test closes/reopens, verifies query count unchanged and no result is restored until explicit Search. |
| 36 | 分別量首次建立、正常重查及故障恢復。 | QP6 `benchmark-report.json` reports all three lifecycle scenarios, each with three samples per range/revision. |
| 37 | 前後使用相同資料、runtime與追蹤條件。 | Same fixture manifest/hash, Python/macOS runtime, staged public entrypoint, and `tracemalloc` in QP6 raw measurements. |
| 38 | 主要成本驗收對應短日期查詢。 | QP6 report uses one day (84 rows) and near-seven days (588 rows), with three samples per case. |
| 39 | 大型補驗需有具體風險理由，避免數小時無資訊重跑。 | QP6 evidence records why 2.16M rows were not run; H8 capacity reports remain historical only. |
| 40 | 查詢不改變監控、保存與清理政策。 | `test_official_cleanup_completes_while_selected_detail_read_is_in_flight`; `test_formal_app_save_stays_out_of_fixed_result_until_requery_without_flush`; related monitoring/retention suites are part of final regression. |
| 41 | 沿用公開入口並用真 Tk 驗收。 | Public `query_historical_events` / `HistoricalEventQueryService`; five true Tk lifecycle/page/retry/language/close tests listed in QP6 local validation. |
| 42 | 工程與桌面驗收通過即可合併，工廠驗收另追。 | #53 closes only after fixed-base review, matched cost evidence, true Tk and final integration regression; no factory/site acceptance is claimed. |

## Final-suite gate

The functional, display, capacity, retention, language, and monitoring suites and the complete integration suite are run again on the final integration branch before closing parent #46. Results are recorded in `docs/refactoring/EXECUTION_2026-10-15.md`; this matrix maps behavior and does not substitute for those runs.
