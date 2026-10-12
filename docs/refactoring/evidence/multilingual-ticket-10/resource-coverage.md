# M10 source 資源逐鍵／參數清單

程式／測試版本 `079b5191598b39182ef6e7acd3269c3cc3d703a9`，English／繁中各322鍵；`validate_translations()==()`。核准術語與關鍵警報／裁決／保存文案另由`test_language_catalog`驗證。

|稳定ID|English|繁體中文|
|---|---|---|
|`app.title`|B518 Log Solution-V0.1.0|B518 Log Solution-V0.1.0|
|`term.test_round`|Test Round|測試輪次|
|`term.awaiting_review`|Awaiting Review|待確認|
|`term.station_type`|Station Type|工站類型|
|`term.original_result`|Original Result|原結果|
|`term.new_candidate`|New Candidate|新候選|
|`term.source_time`|Source Time|來源時間|
|`term.source_filename`|Source Filename|來源檔名|
|`language.menu_hint`|Choose display language|選擇顯示語言|
|`language.save_failed`|Language changed for this session but could not be saved: {reason}|語言已切換供本次使用，但保存失敗：{reason}|
|`language.invalid_saved`|The saved language is unavailable. English will be used.|已保存的語言無法使用，將改用 English。|
|`language.invalid_saved_title`|Language Preference|語言設定|
|`language.save_failed_title`|Language Preference Not Saved|語言設定未保存|
|`app.startup.preferences_read_failed`|Preferences could not be read: {reason}|無法讀取偏好設定：{reason}|
|`app.startup.started`|Application started|App 已啟動|
|`app.round.audit_incomplete`|The round audit is incomplete.|本輪稽核紀錄不完整。|
|`app.round.save_failed`|Round data could not be saved.|本輪資料保存失敗。|
|`app.dashboard.focus_failed`|The result dashboard could not be brought to the foreground.|無法將結果看板帶到前景。|
|`app.notice.ok`|OK|確定|
|`app.notice.diagnostic_below`|See the original diagnostic below.|請查看下方原始診斷。|
|`app.startup.title`|App Initialization|App 初始化|
|`app.preferences.invalid_language`|The saved language is unavailable; English will be used.|已保存的語言無法使用，將改用 English。|
|`app.profile.validation_failed`|The selected configuration is invalid: {reason}|所選配置無效：{reason}|
|`app.profile.save_failed`|Configuration preferences could not be saved; the active configuration remains unchanged: {reason}|無法保存配置偏好；目前有效配置保持不變：{reason}|
|`app.profile.import_failed`|Configuration could not be imported; the saved configuration remains unchanged: {reason}|無法匯入配置；原配置仍有效：{reason}|
|`app.profile.export_failed`|Configuration could not be exported: {reason}|無法匯出配置：{reason}|
|`app.hotkey.unavailable`|Global hotkey is unavailable|全域快捷鍵無法使用|
|`app.hotkey.title`|Global Hotkey|全域快捷鍵|
|`app.profile.validation_title`|Configuration Error|配置錯誤|
|`app.profile.save_title`|Configuration Save Failed|配置保存失敗|
|`app.settings.title`|B518 Log Solution Settings|B518 Log Solution 設定|
|`app.settings.tab.configuration`|Engineer Configuration|工程師配置|
|`app.settings.tab.events`|Events & Session|事件與 Session|
|`app.settings.tab.retention`|Retention|保存期限|
|`app.settings.session.open`|Open Session Records|開啟 Session 紀錄|
|`app.settings.history.open`|Browse Event History|瀏覽歷史事件|
|`app.settings.history.title`|Historical Events|歷史事件|
|`app.settings.history.events`|Events|事件|
|`app.settings.history.detail`|Original Record and Diagnostic|原始紀錄與診斷|
|`app.settings.history.refresh`|Refresh History|重新整理歷史紀錄|
|`app.settings.history.source.app`|App|App|
|`app.settings.history.source.round`|Round|輪次|
|`app.settings.history.source.legacy`|Legacy Session|舊版 Session|
|`app.settings.history.source.error`|Record Warning|紀錄警示|
|`app.settings.history.empty`|No historical events are available.|目前沒有可讀取的歷史事件。|
|`history.unrecognized`|This historical event cannot be safely translated. See the original record for details.|無法安全翻譯此歷史事件；詳細資料保留原始紀錄。|
|`history.read_error`|A historical record could not be read: {reason}|無法讀取歷史紀錄：{reason}|
|`history.incomplete`|The existing audit indicates that some round data may not have been completely saved.|既有 audit 顯示部分輪次資料可能未完整保存。|
|`app.settings.session.open_failed`|Session records could not be opened: {reason}|無法開啟 Session 紀錄：{reason}|
|`app.settings.profile.project`|Project Code|專案代號|
|`app.settings.profile.station_type`|Station Type|工站類型|
|`app.settings.profile.platform`|Platform|平台|
|`app.settings.profile.capacity`|Test Capacity|測試容量|
|`app.settings.profile.mapping`|Source:Display Position Mapping|來源:顯示位置映射|
|`app.settings.profile.path_active`|Active Log Path|即時 Log 路徑|
|`app.settings.profile.path_final`|Final Result Path|最終結果路徑|
|`app.settings.profile.path_caseinfo`|CaseInfo / Progress Path (Optional)|CaseInfo／進度路徑（選填）|
|`app.settings.profile.choose_directory`|Choose Local Folder|選擇本機資料夾|
|`app.settings.profile.timeout_start`|Start Timeout (seconds)|開始期限（秒）|
|`app.settings.profile.timeout_test`|Test Timeout (seconds)|測試期限（秒）|
|`app.settings.profile.timeout_round`|Round Timeout (seconds)|整輪期限（秒）|
|`app.settings.profile.load`|Load Saved Configuration|載入已保存配置|
|`app.settings.profile.validate`|Validate Draft|驗證草稿|
|`app.settings.profile.apply`|Apply and Save|套用並保存|
|`app.settings.profile.cancel`|Cancel Draft|取消草稿|
|`app.settings.profile.import`|Import Configuration|匯入配置|
|`app.settings.profile.export`|Export Configuration|匯出配置|
|`app.settings.profile.reload`|Reload Deployed Configurations|重新載入部署配置|
|`app.settings.profile.status.draft`|Edit a draft. Paths are structurally checked here; access is checked before monitoring starts.|編輯草稿；路徑只做結構檢查，實際可讀性在開始監控前檢查。|
|`app.settings.profile.status.invalid`|Configuration fields are invalid: {reason}|配置欄位錯誤：{reason}|
|`app.settings.profile.status.valid`|Structural validation passed. Paths will be checked on the deployment computer before monitoring starts.|結構驗證通過；部署電腦仍會在開始前檢查路徑。|
|`app.settings.profile.status.saved`|Configuration applied and saved for future rounds.|配置已套用並保存；更新供後續輪次使用。|
|`app.settings.profile.status.cancelled`|Draft cancelled. Saved configuration is unchanged.|草稿已取消，已保存配置未變更。|
|`app.settings.profile.status.not_found`|No saved configuration matches this selection: {reason}|找不到符合此選擇的已保存配置：{reason}|
|`app.settings.profile.status.loaded`|Saved configuration loaded as a draft.|已載入已保存配置作為草稿。|
|`app.settings.profile.status.imported`|Configuration validated, imported, and saved.|配置已驗證、匯入並保存。|
|`app.settings.profile.status.import_selection`|The previous selection is unavailable after import. Switched to the valid configuration in the file: {project} / {machine}.|匯入後原選擇不存在；已切換至文件中的有效配置：{project} / {machine}。|
|`app.settings.profile.status.exported`|Exported {count} configurations.|已匯出 {count} 組配置。|
|`app.settings.profile.status.reload_failed`|Could not reload configurations. The active configuration is unchanged: {reason}|重新載入失敗，目前有效配置保持不變：{reason}|
|`app.settings.profile.status.reloaded`|Deployed configurations reloaded. The active round keeps its original snapshot.|已重新載入部署配置；進行中的輪次仍使用原快照。|
|`app.settings.profile.status.reload_selection`|The previous selection is unavailable after reload. Switched to the valid configuration in preferences: {project} / {machine}.|重新載入後原選擇不存在；已切換至偏好檔中的有效配置：{project} / {machine}。|
|`app.settings.profile.status.active_removed`|The current selection was removed from the configuration list. Choose a valid project and Station Type.|目前選擇已從配置清單移除；請選擇有效專案與工站類型。|
|`app.settings.profile.status.import_selection_missing`|Import or reload did not provide a valid suggested selection.|匯入或重新載入的建議選擇無效。|
|`app.settings.profile.import.title`|Import Engineer Configuration|匯入工程師配置|
|`app.settings.profile.import.type_json`|JSON configuration|JSON 配置|
|`app.settings.profile.import.type_all`|All files|所有檔案|
|`app.settings.profile.export.title`|Export Engineer Configuration|匯出工程師配置|
|`app.settings.profile.export.type_json`|JSON configuration|JSON 配置|
|`app.settings.profile.path.title`|Choose Configuration Path|選擇配置路徑|
|`app.settings.retention.effective`|Effective setting: {days} days|目前生效：{days} 天|
|`app.settings.retention.days`|Global Retention (days)|全域保存天數|
|`app.settings.retention.save`|Save Setting|保存設定|
|`app.settings.retention.status.saved`|Setting saved.|設定已保存。|
|`app.settings.retention.status.invalid`|Invalid setting: retention days must be a positive integer.|設定無效：保存天數必須是正整數。|
|`app.settings.retention.status.read_failed`|Setting is invalid or preferences could not be read. {days} days remains effective: {reason}|設定無效或偏好檔無法讀取，目前仍生效 {days} 天：{reason}|
|`app.settings.retention.status.save_failed`|Could not save. {days} days remains effective: {reason}|保存失敗，目前仍生效 {days} 天：{reason}|
|`app.settings.retention.status.shortened`|Retention updated. Existing eligible records may expire during the next background cleanup.|保存天數已更新；既有符合條件的紀錄可能於下一次背景清理到期。|
|`app.settings.retention.status.updated`|Retention updated and saved.|保存天數已更新並持久保存。|
|`app.settings.retention.help`|Round retention starts from the trusted archive time; App event retention starts from each event's original time. One day means a full 24 hours. / Shortening the period may make existing eligible records expire during the next background cleanup. / Only completely saved, eligible records are handled by background cleanup; the results are summarized below.|輪次保存期限從可信封存時間起算；App 事件從各自原事件時間起算。每天按完整 24 小時計算。 / 縮短期限可能使既有符合條件的紀錄於下一次背景清理時到期。 / 只有符合期限且完整保存的紀錄會由背景清理，執行結果列於下方摘要。|
|`app.settings.retention.cleanup.heading`|Background Cleanup Summary|背景清理摘要|
|`app.settings.retention.cleanup.idle`|Background cleanup has not run.|背景清理尚未執行。|
|`app.settings.retention.cleanup.running`|Background cleanup is running.|背景清理進行中。|
|`app.settings.retention.cleanup.complete`|Background cleanup complete.|背景清理完成。|
|`app.settings.retention.cleanup.failed`|Background cleanup failed.|背景清理失敗。|
|`app.settings.retention.cleanup.skipped`|Background cleanup was skipped: {reason}|背景清理已略過：{reason}|
|`app.settings.retention.cleanup.summary`|Latest run {time} · retention {days} days · deleted {deleted} rounds, retained {skipped}, failed {failed} · App events deleted {app_deleted}, retained {app_skipped}, failed {app_failed}|最近執行 {time} · 保存 {days} 天 · 輪次：刪除 {deleted}、保留 {skipped}、失敗 {failed} · App 事件：刪除 {app_deleted}、保留 {app_skipped}、失敗 {app_failed}|
|`app.settings.retention.cleanup.app_events_reason`|App event cleanup: {reason}|App 事件清理：{reason}|
|`app.settings.retention.cleanup.retry`|Retry Background Cleanup|重試背景清理|
|`app.settings.retention.reason.app_events_not_expired`|not yet expired|尚未到保存期限|
|`app.settings.retention.reason.app_events_timezone`|The cleanup cutoff has no time zone.|清理期限時間缺少時區。|
|`app.settings.retention.reason.app_events_root_invalid`|The App event managed root is not a real directory.|App 事件管理根目錄不是實體目錄。|
|`app.settings.retention.reason.app_events_symlink`|App event cleanup refused a symbolic link.|App 事件清理拒絕符號連結。|
|`app.settings.retention.reason.app_events_outside`|The App event journal is outside the managed area.|App 事件紀錄不在管理範圍。|
|`app.settings.retention.reason.app_events_not_regular`|The App event journal is not a regular file.|App 事件紀錄不是一般檔案。|
|`app.settings.retention.reason.app_events_changed`|The App event journal changed during cleanup.|App 事件紀錄在清理期間已變更。|
|`app.settings.retention.reason.app_events_path_changed`|The App event managed path changed during cleanup.|App 事件管理路徑在清理期間已變更。|
|`app.settings.retention.reason.app_events_pending`|App event saves are pending or completeness is not confirmed.|App 事件仍有待補存，或完整保存狀態尚未確認。|
|`app.settings.retention.reason.app_events_unknown_format`|The App event journal format or version is unsupported.|App 事件紀錄格式或版本不受支援。|
|`app.settings.retention.reason.app_events_invalid`|The App event journal is incomplete or invalid.|App 事件紀錄不完整或無效。|
|`app.settings.retention.reason.app_events_sequence_invalid`|The App event sequence-retention metadata is invalid.|App 事件序號保留資訊無效。|
|`app.settings.retention.reason.app_events_sequence_missing`|The App event sequence-retention metadata is incomplete.|App 事件序號保留資訊不完整。|
|`app.settings.retention.reason.app_events_sequence_gap`|The App event journal has an unexplained sequence gap.|App 事件紀錄存在未解釋的序號缺口。|
|`app.settings.retention.reason.app_events_read_failed`|The App event journal could not be read: {diagnostic}|App 事件紀錄無法讀取：{diagnostic}|
|`app.settings.retention.reason.app_events_time_invalid`|An App event has an invalid original time.|App 事件原始時間格式無效。|
|`app.settings.retention.reason.app_events_time_missing`|An App event original time has no time zone.|App 事件原始時間缺少時區。|
|`app.settings.retention.reason.app_events_path_invalid`|The App event cleanup target is not a regular file or directory.|App 事件清理目標不是一般檔案或目錄。|
|`app.settings.retention.cleanup.failures`|Failures: {items}|失敗：{items}|
|`app.settings.retention.cleanup.protected`|Retained because: {items}|保留原因：{items}|
|`app.settings.retention.cleanup.item`|{round_id}: {reason}|{round_id}：{reason}|
|`app.settings.retention.reason.close`|Cleanup paused while records are being saved for app close.|關閉保存期間暫停清理。|
|`app.settings.retention.reason.protected`|Protected during this app session.|本次 App 執行仍受保護。|
|`app.settings.retention.reason.timezone`|Trusted archive time has no time zone.|可信封存時間缺少時區。|
|`app.settings.retention.reason.not_expired`|The retention period has not elapsed.|尚未到保存期限。|
|`app.settings.retention.reason.deleted`|Trusted round records were completely deleted.|已完整刪除可信輪次資料。|
|`app.settings.retention.reason.unsafe_manifest`|The archive path contains a symbolic link or is outside the managed area.|封存檔路徑含符號連結或越界。|
|`app.settings.retention.reason.invalid_archive`|Archive evidence is invalid.|封存證據無效。|
|`app.settings.retention.reason.unsafe_component`|A required record path contains a symbolic link or is outside the managed area.|必要資料路徑含符號連結或不在 App 管理範圍。|
|`app.settings.retention.reason.archive_path_mismatch`|The archive path does not match its verified path.|封存路徑與驗證後路徑不一致。|
|`app.settings.retention.reason.unknown_file`|The round directory contains an unknown file; the round was retained.|輪次目錄含未知檔案，整輪保留。|
|`app.settings.retention.reason.recovery_protected`|The interrupted round is currently protected.|中斷清理輪次目前仍受保護。|
|`app.settings.retention.reason.invalid_plan`|The persistent deletion plan or round components could not be trusted.|持久刪除計畫格式或輪次組件不可信。|
|`app.settings.retention.reason.recovery_summary`|Deletion was already complete; the interrupted summary was restored.|刪除已完成，補寫先前中斷的摘要。|
|`app.settings.retention.reason.recovered_not_expired`|The current retention period has not elapsed. Staged data was restored and remaining records were retained.|目前保存期限尚未到期；已還原中斷時的暫置資料並保留其餘進度。|
|`app.settings.retention.reason.period_changed`|The retention period changed during cleanup; remaining records were retained for reassessment.|保存期限在清理期間變更，保留剩餘資料等待重新判定。|
|`app.settings.retention.reason.recovered_deleted`|The interrupted deletion plan was completed.|依持久刪除計畫完成中斷復原。|
|`app.settings.retention.reason.archive_unknown_version`|The archive metadata version is not supported.|封存資訊版本不受支援。|
|`app.settings.retention.reason.archive_invalid_time`|The archive time is invalid or has no time zone.|封存時間無效或缺少時區。|
|`app.settings.retention.reason.archive_read_failed`|Archive metadata could not be read: {diagnostic}|無法讀取封存資訊：{diagnostic}|
|`app.settings.retention.reason.archive_format_invalid`|Archive metadata format is invalid.|封存資訊格式不正確。|
|`app.settings.retention.reason.archive_integrity_failed`|Archive integrity verification failed.|封存資訊完整性驗證失敗。|
|`app.settings.retention.reason.archive_round_identity_mismatch`|The archive round identity does not match.|封存輪次身分不一致。|
|`app.settings.retention.reason.archive_integrity_missing`|Archive integrity data is missing.|封存完整性資訊缺失。|
|`app.settings.retention.reason.archive_components_incomplete`|Archive components are incomplete.|封存組成資料不完整。|
|`app.settings.retention.reason.archive_component_format_invalid`|Archive component metadata format is invalid.|封存組成資料格式不正確。|
|`app.settings.retention.reason.archive_component_path_invalid`|An archive component path is invalid.|封存組成資料路徑不正確。|
|`app.settings.retention.reason.archive_component_read_failed`|A required round record is missing or unreadable: {diagnostic}|必要輪次紀錄缺失或無法讀取：{diagnostic}|
|`app.settings.retention.reason.archive_component_changed`|A required round record changed after archival.|必要輪次紀錄內容已變更。|
|`app.settings.retention.reason.archive_component_rebuild_failed`|Required round records could not be rebuilt: {diagnostic}|必要輪次紀錄無法重建：{diagnostic}|
|`app.settings.retention.reason.archive_disk_incomplete`|Disk records are incomplete or bound to another round.|磁碟紀錄未完整保存或輪次身分不一致。|
|`app.settings.event.profile.validation_failed`|Configuration draft validation failed: {reason}|配置草稿驗證失敗：{reason}|
|`app.settings.event.profile.validated`|Engineer configuration draft validated|工程師配置草稿驗證通過|
|`app.settings.event.profile.path_selected`|Configuration folder selected|已選擇配置資料夾|
|`app.settings.event.profile.saved`|Engineer configuration saved|工程師配置已保存|
|`app.settings.event.profile.loaded`|Saved engineer configuration loaded|已載入工程師配置|
|`app.settings.event.profile.imported`|Engineer configuration imported|已匯入工程師配置|
|`app.settings.event.profile.exported`|Engineer configuration exported|已匯出工程師配置|
|`app.settings.event.profile.cancelled`|Engineer configuration draft cancelled|已取消工程師配置草稿|
|`app.settings.event.retention.invalid`|Retention setting was rejected: {reason}|保存期限設定遭拒絕：{reason}|
|`app.settings.event.retention.save_failed`|Retention setting could not be saved: {reason}|無法保存保存期限設定：{reason}|
|`app.settings.event.retention.saved`|Global retention setting saved|全域保存期限設定已保存|
|`app.settings.event.session.open_failed`|Session records could not be opened: {reason}|無法開啟 Session 紀錄：{reason}|
|`app.language.preference_save_failed`|Language changed for this session but could not be saved: {reason}|語言已切換供本次使用，但保存失敗：{reason}|
|`app.event_store.initialize_failed`|App diagnostic history could not be initialized: {reason}|無法初始化 App 診斷紀錄：{reason}|
|`app.event_store.write_failed`|App diagnostic history could not be saved: {reason}|無法保存 App 診斷紀錄：{reason}|
|`app.event_store.recovered`|App diagnostic history save recovery completed|App 診斷紀錄已完成保存復原|
|`app.event_store.title`|App Diagnostics Not Saved|App 診斷紀錄未保存|
|`app.save.retry_started`|Retrying App diagnostic saves|正在重試保存 App 診斷紀錄|
|`app.save.pending`|Saving App diagnostics ({count} pending)|正在保存 App 診斷紀錄（待保存 {count} 筆）|
|`app.save.failed`|App diagnostic records are not fully saved: {reason}|App 診斷紀錄尚未完整保存：{reason}|
|`app.save.complete`|App diagnostic records are fully saved|App 診斷紀錄已完整保存|
|`app.diagnostic.heading`|App diagnostics|App 診斷|
|`app.diagnostic.retry`|Retry App Saves|重試 App 保存|
|`app.diagnostic.close`|Close|關閉|
|`app.diagnostic.event_time`|Event time|事件時間|
|`app.diagnostic.event_id`|Event identity|事件識別|
|`app.diagnostic.message_id`|Message identity|訊息識別|
|`app.diagnostic.parameters`|Captured parameters|捕捉參數|
|`app.diagnostic.raw`|Original diagnostic|原始診斷|
|`app.diagnostic.save_history`|Previous App save errors (current status: {status}): {history}|過去的 App 保存錯誤（目前狀態：{status}）：{history}|
|`app.diagnostic.save_state.failed`|failed|失敗|
|`app.diagnostic.save_state.saving`|saving|保存中|
|`app.diagnostic.save_state.complete`|complete|完整保存|
|`app.close.saving`|Stopping collection and saving App diagnostics and round records…|正在停止收集並保存 App 診斷及輪次紀錄…|
|`app.close.waiting`|Waiting for required App and round save handoffs…|正在等待 App 與輪次保存交接完成…|
|`app.close.failed`|Required App diagnostics or round records are not fully saved. Repair storage and retry; this window remains open.|App 診斷或輪次紀錄尚未完整保存。修復保存位置或磁碟問題後可重試；視窗仍保持開啟。|
|`app.close.complete`|All required App diagnostics, Session and audit records for this run are fully saved.|本次執行的全部必要 App 診斷、Session 與 audit 紀錄均已完整保存。|
|`app.close.cancelled`|Close cancelled. Save work continues, and stopped sources will not restart automatically.|已取消關閉；保存工作會繼續，來源不會自動重新啟動。|
|`app.close.title`|Save Before Closing|關閉前保存|
|`app.close.language_disabled`|Language changes are unavailable while this close-and-save request is active. Cancel closing to change language.|關閉與保存作業進行中，暫時無法切換語言。取消關閉後即可切換。|
|`app.close.diagnostic`|Original save diagnostic: {reason}|原始保存診斷：{reason}|
|`app.close.retry`|Retry Save|重試保存|
|`app.close.cancel`|Cancel Closing|取消關閉|
|`main.settings`|Settings|設定|
|`main.review`|Awaiting Review|待確認|
|`main.review_count`|Awaiting Review ({count})|待確認 ({count})|
|`main.round_alarm`|Round Alarm|整輪警報|
|`main.round_alarm_pending`|Round Alarm (Awaiting Review)|整輪警報（待確認）|
|`main.round_alarm_acknowledged`|Round Alarm (Acknowledged)|整輪警報已確認|
|`conflict.title`|Same-Round Result Conflict|同輪結果衝突|
|`conflict.instructions`|Choose whether to keep the original result or accept the captured new candidate for each item. Closing this window does not make a decision.|請逐項選擇保留原結果或採用已捕捉的新候選；關閉視窗不會做出裁決。|
|`conflict.position`|Display position: {position}|顯示位置：{position}|
|`conflict.unknown`|Unknown|未知|
|`conflict.path.root`|root|根目錄|
|`conflict.path.relative`|relative path|相對路徑|
|`conflict.empty`|There are no items awaiting review.|目前沒有待確認項目。|
|`conflict.list_item`|Position {position}: {original_sn} {original_status} → {candidate_sn} {candidate_status}|位置 {position}：{original_sn} {original_status} → {candidate_sn} {candidate_status}|
|`conflict.comparison.item`|Item|項目|
|`conflict.comparison.original`|Original Result|原結果|
|`conflict.comparison.candidate`|New Candidate|新候選|
|`conflict.field.result`|Result|結果|
|`conflict.field.sn`|SN|SN|
|`conflict.detail.round`|Test Round|測試輪次|
|`conflict.detail.conflict`|Conflict|衝突|
|`conflict.detail.position`|Display position|顯示位置|
|`conflict.detail.same_round_evidence`|Same-round evidence|同輪證據|
|`conflict.detail.original`|Original Result|原結果|
|`conflict.detail.candidate_snapshot`|New Candidate Snapshot|新候選快照|
|`conflict.detail.sn`|SN|SN|
|`conflict.detail.result`|Result|結果|
|`conflict.detail.source`|Source|來源|
|`conflict.detail.source_identity`|Source identity|來源識別|
|`conflict.detail.source_time`|Source Time|來源時間|
|`conflict.detail.evidence`|Evidence|證據|
|`conflict.button.keep_original`|Keep Original Result|保留原結果|
|`conflict.button.accept_candidate`|Accept New Candidate|採用新候選|
|`conflict.button.close`|Close|關閉|
|`alarm.title`|Round Monitoring Timeout|整輪監控逾時|
|`alarm.body`|The round monitoring limit was reached. New source reads have stopped. Existing terminal results were retained, and unfinished positions were handled using their observed activity. /  / {round_label}: {round_id} / {alarm_label}: {alarm_id} / {created_label}: {created_at} / {status}|整輪監控已到達設定上限。新的來源讀取已停止，既有終態已保留，未完成位置已依活動證據裁決。 /  / {round_label}：{round_id} / {alarm_label}：{alarm_id} / {created_label}：{created_at} / {status}|
|`alarm.round`|Test Round|測試輪次|
|`alarm.identity`|Alarm|警報|
|`alarm.created_at`|Created at|建立時間|
|`alarm.status.pending`|Acknowledge this alarm to continue. Result conflicts still require individual review.|請確認此警報以解除提醒；結果衝突仍須逐項覆核。|
|`alarm.status.acknowledged`|This alarm is acknowledged; other review items still require individual decisions.|此警報已確認；其他待確認事項仍須逐項處理。|
|`alarm.status.preparation_pending`|Source preparation is still running. The alarm cannot be acknowledged yet.|來源準備仍在進行，暫時無法確認此警報。|
|`alarm.status.conflict_note`|Acknowledging this alarm does not accept or clear result conflicts.|確認此警報不會接受或清除結果衝突。|
|`alarm.button.acknowledge`|Acknowledge Round Alarm|確認整輪警報|
|`alarm.button.acknowledged`|Acknowledged|已確認|
|`alarm.button.close`|Close|關閉|
|`main.project`|Project|專案|
|`main.machine_type`|Station Type|機型|
|`main.kvm_result`|KVM RESULT|KVM RESULT|
|`main.kvm_legend`|KVM Status Template|KVM 狀態模板|
|`main.slot_heading`|Slot|通道|
|`main.status_heading`|Status|狀態|
|`main.serial_heading`|Product SN|產品 SN|
|`main.start_monitor`|Start Monitoring  (Command+Shift+M)|開始監控  (Command+Shift+M)|
|`main.stop`|Stop|停止|
|`main.save.waiting`|Waiting to save|等待保存|
|`main.save.saving`|Saving|保存中|
|`main.save.failed`|Save Failed|保存失敗|
|`main.save.complete`|Saved Completely|完整保存|
|`main.retry_save`|Retry Save|重試保存|
|`main.unsaved_rounds`|Unsaved rounds: {count}|未保存輪次 {count}|
|`main.retry_selected`|Retry Selected|重試所選|
|`main.retry_archive`|Retry Archive|重試封存|
|`main.archive_summary`|Rounds: {unsaved} unsaved · {saved} saved · {archived} archived|輪次：未完整保存 {unsaved} · 完整保存 {saved} · 可信封存 {archived}|
|`main.archive_protected`|Saved · Protected|完整保存・受保護|
|`main.archived`|Trusted Archive|可信封存|
|`main.slot`|Slot {number}|通道 {number}|
|`main.station_title`|{machine} Log Monitoring|{machine} Log 監控|
|`round.started`|{station} round start accepted|{station} 已接受開始本輪|
|`round.ready`|{station} monitoring source ready|{station} 監控來源已就緒|
|`round.collection_stopped`|{station} stopped collecting new source data|{station} 已停止收集新來源資料|
|`round.stopped`|{station} monitoring stopped by operator|{station} 監控已由人員停止|
|`round.finished`|{station} round completed|{station} 本輪已完成|
|`round.timeout.slot`|{station} Slot {slot} timed out: {status} after {elapsed} seconds (limit {deadline} seconds)|{station} 通道 {slot} 逾時：經過 {elapsed} 秒，期限 {deadline} 秒，結果 {status}|
|`round.timeout.whole`|{station} round monitoring timed out after {elapsed} seconds (limit {deadline} seconds)|{station} 整輪監控逾時：經過 {elapsed} 秒，期限 {deadline} 秒|
|`round.alarm.created`|{station} round timeout alarm created|{station} 已建立整輪逾時警報|
|`round.alarm.acknowledged`|Round timeout alarm acknowledged; other review items remain|整輪逾時警報已確認；仍有其他項目待確認|
|`round.alarm.ignored`|Round alarm acknowledgement ignored|整輪警報確認已忽略|
|`round.conflict.detected`|Slot {slot} has a same-round result conflict and awaits review|通道 {slot} 發現同輪結果衝突，等待人工確認|
|`round.conflict.detected.unknown_position`|A result conflict with unknown position awaits review|位置未知的結果衝突等待人工確認|
|`round.conflict.kept_original`|Slot {slot}: original result kept|通道 {slot}：已保留原結果|
|`round.conflict.kept_original.unknown_position`|Original result kept for a conflict with unknown position|位置未知的衝突已保留原結果|
|`round.conflict.accepted_candidate`|Slot {slot}: new candidate accepted|通道 {slot}：已採用新候選|
|`round.conflict.accepted_candidate.unknown_position`|A new candidate was accepted for a conflict with unknown position|位置未知的衝突已採用新候選|
|`round.duplicate_source`|Slot {slot}: duplicate source recorded|通道 {slot}：已記錄重複來源|
|`round.duplicate_source.unknown_position`|A duplicate source with unknown position was recorded|已記錄位置未知的重複來源|
|`round.unknown_candidate_rejected`|Slot {slot}: source could not be linked to this round; candidate rejected and result set to FAIL|通道 {slot}：無法確認來源屬於本輪；已拒絕候選並判定 FAIL|
|`round.unknown_candidate_rejected.unknown_position`|A source with unknown position could not be linked to this round; candidate rejected|無法確認位置未知的來源屬於本輪；已拒絕候選|
|`round.audit_write_failed`|{station} audit event could not be saved|{station} 稽核事件保存失敗|
|`round.session_write_failed`|{station} Session event could not be saved|{station} Session 事件保存失敗|
|`round.save_recovered`|{station} Session and audit save recovery completed|{station} Session 與稽核紀錄已完成保存復原|
|`round.start_failed`|{station} monitoring source preparation failed|{station} 監控來源準備失敗|
|`monitor.idle`|Standby|待命|
|`monitor.active`|Monitoring|監控中|
|`monitor.starting`|Starting|啟動中|
|`monitor.closing`|Saving before close|關閉前保存中|
|`monitor.start_failed`|Start Failed|啟動失敗|
|`monitor.timeout_stopped`|Stopped after timeout|逾時停止|
|`monitor.awaiting_conflicts`|Awaiting Review: {count} conflicts|待確認：衝突 {count} 項|
|`monitor.awaiting_alarm`|Awaiting Review: Round Alarm|待確認：整輪警報|
|`monitor.awaiting_both`|Awaiting Review: {count} conflicts · Round Alarm|待確認：衝突 {count} 項、整輪警報|
|`monitor.completed`|Round Complete|本輪完成|
|`monitor.stopped`|Stopped|已停止|
|`round.result`|{station} Slot {slot} result: {status}|{station} 通道 {slot} 結果：{status}|
|`round.result.unknown_position`|{station} result: {status} (position unknown)|{station} 結果：{status}（位置未知）|
|`platform.atlas.source_prepared`|Atlas source snapshot is ready|Atlas 來源快照已就緒|
|`platform.atlas.sn_locked`|Atlas Slot {slot} trusted serial number locked|Atlas 通道 {slot} 已鎖定可信序號|
|`platform.atlas.final`|Atlas Slot {slot} final result: {status}|Atlas 通道 {slot} 最終結果：{status}|
|`platform.atlas.unresolved_conflict`|Atlas Slot {slot} source identity changed; evidence retained for review|Atlas 通道 {slot} 來源身分改變；證據已保留供覆核|
|`platform.atlas.source_error`|Atlas source file could not be read: {source_filename}|Atlas 來源檔案無法讀取：{source_filename}|
|`platform.b482.batch`|B482 source batch observed: {batch_id}|B482 已觀察來源批次：{batch_id}|
|`platform.b482.batch_mismatch`|B482 Slot {slot} evidence belongs to a different batch|B482 通道 {slot} 證據屬於不同批次|
|`platform.b482.source_error`|B482 source file could not be read: {source_filename}|B482 來源檔案無法讀取：{source_filename}|
|`platform.rswmt.batch`|RS-WMT source batch observed|RS-WMT 已觀察來源批次|
|`platform.rswmt.warning`|RS-WMT source could not be accepted: {source_filename}|RS-WMT 來源無法接受：{source_filename}|
|`platform.sample_json.invalid_record`|Sample JSON source record is invalid: {source_filename}|Sample JSON 來源記錄無效：{source_filename}|
|`platform.sample_json.unsupported_record`|Sample JSON record is unsupported: {source_filename}|Sample JSON 記錄不受支援：{source_filename}|
|`platform.sample_json.invalid_fields`|Sample JSON fields are invalid: {source_filename}|Sample JSON 欄位無效：{source_filename}|
|`platform.sample_json.invalid_status`|Sample JSON final status is unsupported: {source_filename}|Sample JSON 最終狀態不受支援：{source_filename}|
|`platform.sample_json.unreadable`|Sample JSON source could not be read: {source_filename}|Sample JSON 來源無法讀取：{source_filename}|
