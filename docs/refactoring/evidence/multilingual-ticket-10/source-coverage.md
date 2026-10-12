# M10 source 全入口盤點（2026-10-12）

固定 review baseline：`95b791c2cf1a54b10db4f07cbc606ddd06db8280`；程式／測試版本：`079b5191598b39182ef6e7acd3269c3cc3d703a9`。

盤點方式：核對實際 Tk command、bind、after、公開操作入口及各狀態分支，以下 AST 清單只用於可追查 ID 對照，不以文字搜尋零命中代表完成。全套測試再次執行 M1～M9 各路徑，新五視窗案例另驗跨視窗長流程。

## 入口、責任與行為證據

|實際入口／狀態|文案與操作責任|本次測試入口（全部重跑）|
|---|---|---|
|主頁語言滑鼠、Space／方向鍵／Escape、重選、快捷開始|原生名稱、焦點、持久設定、關閉 gate；不改 KVM geometry|`test_real_tk_language_menu_switches_main_page_and_persists_across_app_instances`、`test_real_tk_language_and_profile_controls_fit_fixed_hmi_width`、M1 使用者原生輸入紀錄|
|直接開始、局部／全域要求回 Tk、profile/path/preferences/source建立失敗|同步驗證與偏好、集中準備；自有即時 notice；固定 round.start_failed|`test_real_tk_shortcuts_start_rounds_with_session_and_audit_profile_evidence`、`test_visible_start_validation_notice_refreshes_without_accepting_a_round`、`test_visible_source_failure_notice_and_fixed_bilingual_audit`|
|設定三分頁、載入／驗證／套用／取消／重新載入|草稿、平台原ID、選取、驗證狀態保留|`test_open_settings_refreshes_language_in_place_and_keeps_invalid_draft`、`test_integrated_language_refresh_keeps_open_settings_diagnostics_and_history`|
|選目錄、匯入／匯出、覆寫／取消|App title/type翻譯；OS按鈕依系統；配置格式與路徑不變|`test_file_dialog_buttons_use_current_language_and_cancel_without_changes`、`test_engineer_import_export_and_reload_preserve_a_deployable_catalog`；M5使用者實際原生操作已確認|
|保存天數驗證／保存／縮短提示、背景清理與重試摘要|生效值與草稿分離、M9 原時間清理；兩語原因與原診斷|`test_retention_setting_uses_visible_errors_and_persists_bilingual_app_events`、`test_real_tk_app_event_cleanup_failure_is_visible_and_retryable`、`test_real_tk_localizes_timezone_missing_app_event_cleanup_reason`、`test_app_event_retention`|
|衝突選單、精簡／詳細、選取／移除／空／隱藏重開|四項對照、兩側差異樣式、來源目錄消歧、snapshot不變|`test_sample_platform_conflicts_stay_consistent_through_real_tk_and_disk_rebuild`、`test_real_tk_conflict_selection_keeps_both_sections_on_same_snapshot`、新五窗整合|
|整輪警報、停止後裁決、保留原／採用新／確認警報|未自動確認；每次操作同筆雙語|`test_atlas_round_shows_nonblocking_conflict_and_releases_after_other_slot_finishes`、`test_real_tk_close_keeps_conflict_and_alarm_actions_available`、新五窗整合|
|App診斷／本輪／前輪保存、重試／封存／歷史錯誤|固定事件ID、原時間／序號與原文，非阻塞保存|`test_real_tk_app_diagnostic_is_bilingual_inspectable_and_saved_before_close`、`test_real_tk_can_select_and_retry_previous_round_without_changing_current_board`、`test_real_tk_distinguishes_unsaved_saved_and_archived_round_states`|
|事件頁、App診斷與歷史選讀／詳細／重開|原視窗刷新；事件文字選取與list/detail閱讀位置；新舊資料不回寫|`test_language_refresh_preserves_event_log_reading_position`、`test_real_tk_historical_reader_selects_and_localizes_disk_records_without_rewriting`|
|開啟 Session 目錄及 OS 開啟失敗|mkdir及Popen均在同一OSError處理分支；實際注入mkdir故障進本語言notice與同筆App診斷，Popen為程式路徑查核而非本次直接注入驗收|`test_session_directory_failure_is_visible_and_persisted`|
|關閉等待／失敗／重試／取消／再次關閉|所有App及跨輪完整保存；實際入口停用；generation隔離|`test_close_waits_responsively_and_cancellation_invalidates_old_completion`、`test_close_failure_keeps_window_open_and_real_retry_rebuilds_complete_audit`、新五窗整合|
|Atlas DFU/FCT、B482 BT、RS-WMT BT、sample-json FCT|原producer明確ID、固定兩語／診斷；不改接受與裁決政策|M3 四平台真Tk source矩陣及`test_log_monitoring`、`test_round_start_preparation`全套；producer明細見M3驗收附件|
|初始化／偏好讀取／未知語言／熱鍵不可用／語言保存失敗|自有notice共用生成／刷新，原診斷可讀|`test_real_tk_unknown_saved_language_uses_english_and_shows_diagnostic`、`test_real_tk_hotkey_and_profile_failures_are_saved_and_inspectable`、`test_visible_language_write_error_refresh_keeps_original_preferences`|
|正常開始與snapshot保存／稽核失敗、前景提升失敗|canonical round_started取代重複中文UI行；其他display-only診斷用穩定ID，保留原保存責任|新真實來源整合、catalog完整性、既有保存／KVM故障回歸|


## 可達 App 呈現／producer 的 ID 對照

每行為實際函式內明確傳入的資源 ID（動態 state、reason、歷史事件依各自共用契約解析）；確認沒有因翻譯增加操作或另建保存機制。

|函式（src/b518_log_solution.py）|ID與producer|
|---|---|
|`_build` (L238)|`app.diagnostic.heading`|
|`_apply_main_language` (L424)|`app.diagnostic.heading`、`app.title`、`main.kvm_legend`、`main.kvm_result`、`main.machine_type`、`main.project`、`main.retry_archive`、`main.retry_save`、`main.retry_selected`、`main.settings`、`main.slot`、`main.start_monitor`、`main.stop`|
|`_show_notice` (L468)|`app.diagnostic.raw`、`app.notice.diagnostic_below`、`app.notice.ok`|
|`_apply_settings_language` (L506)|`app.settings.retention.effective`、`app.settings.title`|
|`_refresh_main_round_labels` (L563)|`main.review_count`、`monitor.active`、`monitor.awaiting_alarm`、`monitor.awaiting_both`、`monitor.awaiting_conflicts`、`monitor.completed`、`monitor.idle`、`monitor.stopped`|
|`_render_station_title` (L594)|`main.station_title`|
|`_record_startup_diagnostics` (L602)|`app.event_store.initialize_failed`、`app.preferences.invalid_language`、`app.startup.preferences_read_failed`、`app.startup.started`|
|`_refresh_app_event_status` (L623)|`app.diagnostic.save_history`、`app.save.complete`、`app.save.failed`、`app.save.pending`|
|`_refresh_app_event_records` (L647)|`app.diagnostic.heading`|
|`_show_app_event_detail` (L695)|`app.diagnostic.event_id`、`app.diagnostic.event_time`、`app.diagnostic.message_id`、`app.diagnostic.parameters`、`app.diagnostic.raw`|
|`open_app_diagnostics` (L724)|`app.diagnostic.close`、`app.diagnostic.heading`、`app.diagnostic.retry`|
|`_select_language` (L763)|`app.language.preference_save_failed`、`language.save_failed`、`language.save_failed_title`|
|`_show_invalid_language_warning` (L818)|`language.invalid_saved`、`language.invalid_saved_title`|
|`_show_startup_warning` (L823)|`app.startup.preferences_read_failed`、`app.startup.title`|
|`_show_app_event_store_warning` (L828)|`app.event_store.initialize_failed`、`app.event_store.title`|
|`_apply_round_snapshot` (L894)|`app.round.audit_incomplete`、`app.round.save_failed`|
|`_refresh_unsaved_rounds` (L958)|`main.unsaved_rounds`|
|`_refresh_archive_statuses` (L983)|`main.archive_protected`、`main.archive_summary`、`main.archived`|
|`_render_rows` (L1047)|`main.slot`|
|`_show_hotkey_warning` (L1156)|`app.hotkey.title`、`app.hotkey.unavailable`|
|`_set_monitor_controls` (L1161)|`monitor.closing`|
|`start_monitor` (L1190)|`app.profile.save_failed`、`app.profile.save_title`、`app.profile.validation_failed`、`app.profile.validation_title`、`monitor.starting`|
|`_bring_dashboard_to_front` (L1319)|`app.dashboard.focus_failed`|
|`_handle_event` (L1329)|`monitor.start_failed`、`monitor.timeout_stopped`、`round.start_failed`|
|`_open_conflict_review` (L1379)|`conflict.position`、`conflict.unknown`|
|`_refresh_conflict_review` (L1483)|`conflict.list_item`、`conflict.unknown`、`main.review_count`、`monitor.awaiting_alarm`、`monitor.awaiting_both`、`monitor.awaiting_conflicts`、`monitor.completed`、`monitor.stopped`|
|`_apply_conflict_window_language` (L1560)|`conflict.instructions`、`conflict.title`|
|`_clear_conflict_comparison` (L1581)|`conflict.empty`、`conflict.position`、`conflict.unknown`|
|`_show_selected_conflict` (L1602)|`conflict.comparison.candidate`、`conflict.comparison.item`、`conflict.comparison.original`、`conflict.detail.candidate_snapshot`、`conflict.detail.conflict`、`conflict.detail.original`、`conflict.detail.position`、`conflict.detail.round`、`conflict.detail.same_round_evidence`、`conflict.field.result`、`conflict.field.sn`、`conflict.position`、`conflict.unknown`、`term.source_filename`、`term.source_time`|
|`_refresh_round_alarm` (L1761)|`main.round_alarm`|
|`_open_round_alarm` (L1784)|`alarm.button.acknowledge`、`alarm.button.close`、`alarm.title`|
|`_render_round_alarm` (L1819)|`alarm.body`、`alarm.button.acknowledge`、`alarm.button.acknowledged`、`alarm.button.close`、`alarm.created_at`、`alarm.identity`、`alarm.round`、`alarm.status.conflict_note`、`alarm.title`|
|`open_settings` (L1855)|`app.settings.title`|
|`_build_retention_tab` (L1887)|`app.settings.retention.cleanup.heading`、`app.settings.retention.cleanup.retry`、`app.settings.retention.days`、`app.settings.retention.effective`、`app.settings.retention.help`、`app.settings.retention.save`、`app.settings.retention.status.saved`|
|`_save_retention_days` (L1930)|`app.settings.event.retention.invalid`、`app.settings.event.retention.save_failed`、`app.settings.event.retention.saved`、`app.settings.retention.effective`、`app.settings.retention.status.invalid`、`app.settings.retention.status.read_failed`、`app.settings.retention.status.save_failed`、`app.settings.retention.status.shortened`、`app.settings.retention.status.updated`|
|`_refresh_retention_cleanup_status` (L1975)|`app.settings.retention.cleanup.app_events_reason`、`app.settings.retention.cleanup.failed`、`app.settings.retention.cleanup.failures`、`app.settings.retention.cleanup.heading`、`app.settings.retention.cleanup.item`、`app.settings.retention.cleanup.protected`、`app.settings.retention.cleanup.summary`、`term.test_round`|
|`_retention_reason_text` (L2034)|`app.settings.retention.reason.app_events_not_expired`|
|`_build_profile_editor_tab` (L2102)|`app.settings.profile.capacity`、`app.settings.profile.choose_directory`、`app.settings.profile.mapping`、`app.settings.profile.platform`、`app.settings.profile.project`、`app.settings.profile.station_type`、`app.settings.profile.status.draft`|
|`_choose_profile_editor_path` (L2198)|`app.settings.event.profile.path_selected`、`app.settings.profile.path.title`|
|`_profile_editor_draft` (L2206)|`app.settings.event.profile.validation_failed`、`app.settings.profile.status.invalid`、`app.settings.profile.status.valid`|
|`_validate_profile_editor` (L2224)|`app.settings.event.profile.validated`|
|`_apply_profile_editor` (L2232)|`app.profile.save_failed`、`app.settings.event.profile.saved`、`app.settings.profile.status.saved`|
|`_cancel_profile_editor` (L2262)|`app.settings.event.profile.cancelled`、`app.settings.profile.status.cancelled`|
|`_load_profile_editor_selection` (L2267)|`app.profile.validation_failed`、`app.settings.event.profile.loaded`、`app.settings.profile.status.loaded`、`app.settings.profile.status.not_found`|
|`_import_profiles` (L2296)|`app.profile.import_failed`、`app.settings.event.profile.imported`、`app.settings.profile.import.title`、`app.settings.profile.import.type_all`、`app.settings.profile.import.type_json`、`app.settings.profile.status.import_selection`、`app.settings.profile.status.imported`|
|`_export_profiles` (L2320)|`app.profile.export_failed`、`app.settings.event.profile.exported`、`app.settings.profile.export.title`、`app.settings.profile.export.type_json`、`app.settings.profile.status.exported`|
|`_reload_profiles` (L2341)|`app.settings.event.profile.loaded`、`app.settings.profile.status.reload_failed`、`app.settings.profile.status.reload_selection`、`app.settings.profile.status.reloaded`、`app.startup.preferences_read_failed`|
|`_activate_profile_catalog` (L2355)|`app.settings.profile.status.active_removed`、`app.settings.profile.status.import_selection_missing`|
|`_build_log_tab` (L2392)|`app.settings.history.open`、`app.settings.session.open`|
|`open_historical_events` (L2408)|`app.settings.history.detail`、`app.settings.history.events`、`app.settings.history.refresh`、`app.settings.history.title`|
|`_refresh_historical_event_window` (L2462)|`app.settings.history.detail`、`app.settings.history.empty`、`app.settings.history.events`、`app.settings.history.refresh`、`app.settings.history.title`|
|`open_session` (L2557)|`app.settings.event.session.open_failed`、`app.settings.session.open`、`app.settings.session.open_failed`|
|`close` (L2569)|`app.profile.save_failed`、`app.profile.save_title`|
|`_show_close_progress` (L2589)|`app.close.cancel`、`app.close.retry`、`app.close.title`|
|`_render_close_status` (L2620)|`app.close.cancel`、`app.close.diagnostic`、`app.close.language_disabled`、`app.close.retry`、`app.close.waiting`|
|`text_provider` (L473)|`app.diagnostic.raw`、`app.notice.diagnostic_below`、`app.notice.ok`|
|`source_parts` (L1629)|`conflict.unknown`|


## 例外與發布界線

SN、路徑／檔名、自訂名稱、來源時間／Log／診斷、平台ID、狀態碼保持原值。英文外層說明之後的原始診斷可能包含中文，屬原文證據，不視為漏譯。OS 檔案選擇器按鈕及覆寫文字依 OS；App提供的title/filetypes已翻譯。Menu.invoke只驅動本票整合語言變更，不單獨代表OS原生滑鼠／鍵盤導覽驗收；沿用M1/M5實際操作紀錄及本次重跑的Tk輸入回歸。

所有source資源隨App版本化，未新增語言／schema／裁決政策／排程。正式bundle、目標HMI／實機KVM仍待驗，本文件不宣稱可發布。
