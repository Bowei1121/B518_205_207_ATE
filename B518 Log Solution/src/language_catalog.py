"""Supported App languages and their native display names."""

import json
from dataclasses import dataclass
from string import Formatter
from typing import Dict, Mapping, Optional, Tuple

ENGLISH = "en"
TRADITIONAL_CHINESE = "zh-TW"
DEFAULT_LANGUAGE = ENGLISH
LANGUAGE_OPTIONS = (
    (ENGLISH, "English"),
    (TRADITIONAL_CHINESE, "繁體中文"),
)
SUPPORTED_LANGUAGE_CODES = frozenset(code for code, _name in LANGUAGE_OPTIONS)

LANGUAGE_RESOURCES: Dict[str, Dict[str, str]] = {
    ENGLISH: {
        "app.title": "B518 Log Solution-V0.1.0",
        "term.test_round": "Test Round",
        "term.awaiting_review": "Awaiting Review",
        "term.station_type": "Station Type",
        "term.original_result": "Original Result",
        "term.new_candidate": "New Candidate",
        "term.source_time": "Source Time",
        "term.source_filename": "Source Filename",
        "language.menu_hint": "Choose display language",
        "language.save_failed": "Language changed for this session but could not be saved: {reason}",
        "language.invalid_saved": "The saved language is unavailable. English will be used.",
        "language.invalid_saved_title": "Language Preference",
        "language.save_failed_title": "Language Preference Not Saved",
        "app.startup.preferences_read_failed": "Preferences could not be read: {reason}",
        "app.startup.started": "Application started",
        "app.startup.title": "App Initialization",
        "app.preferences.invalid_language": "The saved language is unavailable; English will be used.",
        "app.profile.validation_failed": "The selected configuration is invalid: {reason}",
        "app.profile.save_failed": "Configuration preferences could not be saved; the active configuration remains unchanged: {reason}",
        "app.profile.import_failed": "Configuration could not be imported; the saved configuration remains unchanged: {reason}",
        "app.profile.export_failed": "Configuration could not be exported: {reason}",
        "app.hotkey.unavailable": "Global hotkey is unavailable",
        "app.hotkey.title": "Global Hotkey",
        "app.profile.validation_title": "Configuration Error",
        "app.profile.save_title": "Configuration Save Failed",
        "app.settings.title": "B518 Log Solution Settings",
        "app.settings.tab.configuration": "Engineer Configuration",
        "app.settings.tab.events": "Events & Session",
        "app.settings.tab.retention": "Retention",
        "app.settings.session.open": "Open Session Records",
        "app.settings.session.open_failed": "Session records could not be opened: {reason}",
        "app.settings.profile.project": "Project Code",
        "app.settings.profile.station_type": "Station Type",
        "app.settings.profile.platform": "Platform",
        "app.settings.profile.capacity": "Test Capacity",
        "app.settings.profile.mapping": "Source:Display Position Mapping",
        "app.settings.profile.path_active": "Active Log Path",
        "app.settings.profile.path_final": "Final Result Path",
        "app.settings.profile.path_caseinfo": "CaseInfo / Progress Path (Optional)",
        "app.settings.profile.choose_directory": "Choose Local Folder",
        "app.settings.profile.timeout_start": "Start Timeout (seconds)",
        "app.settings.profile.timeout_test": "Test Timeout (seconds)",
        "app.settings.profile.timeout_round": "Round Timeout (seconds)",
        "app.settings.profile.load": "Load Saved Configuration",
        "app.settings.profile.validate": "Validate Draft",
        "app.settings.profile.apply": "Apply and Save",
        "app.settings.profile.cancel": "Cancel Draft",
        "app.settings.profile.import": "Import Configuration",
        "app.settings.profile.export": "Export Configuration",
        "app.settings.profile.reload": "Reload Deployed Configurations",
        "app.settings.profile.status.draft": "Edit a draft. Paths are structurally checked here; access is checked before monitoring starts.",
        "app.settings.profile.status.invalid": "Configuration fields are invalid: {reason}",
        "app.settings.profile.status.valid": "Structural validation passed. Paths will be checked on the deployment computer before monitoring starts.",
        "app.settings.profile.status.saved": "Configuration applied and saved for future rounds.",
        "app.settings.profile.status.cancelled": "Draft cancelled. Saved configuration is unchanged.",
        "app.settings.profile.status.not_found": "No saved configuration matches this selection: {reason}",
        "app.settings.profile.status.loaded": "Saved configuration loaded as a draft.",
        "app.settings.profile.status.imported": "Configuration validated, imported, and saved.",
        "app.settings.profile.status.import_selection": "The previous selection is unavailable after import. Switched to the valid configuration in the file: {project} / {machine}.",
        "app.settings.profile.status.exported": "Exported {count} configurations.",
        "app.settings.profile.status.reload_failed": "Could not reload configurations. The active configuration is unchanged: {reason}",
        "app.settings.profile.status.reloaded": "Deployed configurations reloaded. The active round keeps its original snapshot.",
        "app.settings.profile.status.reload_selection": "The previous selection is unavailable after reload. Switched to the valid configuration in preferences: {project} / {machine}.",
        "app.settings.profile.status.active_removed": "The current selection was removed from the configuration list. Choose a valid project and Station Type.",
        "app.settings.profile.status.import_selection_missing": "Import or reload did not provide a valid suggested selection.",
        "app.settings.profile.import.title": "Import Engineer Configuration",
        "app.settings.profile.import.type_json": "JSON configuration",
        "app.settings.profile.import.type_all": "All files",
        "app.settings.profile.export.title": "Export Engineer Configuration",
        "app.settings.profile.export.type_json": "JSON configuration",
        "app.settings.profile.path.title": "Choose Configuration Path",
        "app.settings.retention.effective": "Effective setting: {days} days",
        "app.settings.retention.days": "Global Retention (days)",
        "app.settings.retention.save": "Save Setting",
        "app.settings.retention.status.saved": "Setting saved.",
        "app.settings.retention.status.invalid": "Invalid setting: retention days must be a positive integer.",
        "app.settings.retention.status.read_failed": "Setting is invalid or preferences could not be read. {days} days remains effective: {reason}",
        "app.settings.retention.status.save_failed": "Could not save. {days} days remains effective: {reason}",
        "app.settings.retention.status.shortened": "Retention updated. Existing eligible records may expire during the next background cleanup.",
        "app.settings.retention.status.updated": "Retention updated and saved.",
        "app.settings.retention.help": "Retention starts from the trusted archive time. One day means a full 24 hours.\nShortening the period may make existing eligible records expire during the next background cleanup.\nEligible, completely saved rounds are handled by background cleanup; the results are summarized below.",
        "app.settings.retention.cleanup.heading": "Background Cleanup Summary",
        "app.settings.retention.cleanup.idle": "Background cleanup has not run.",
        "app.settings.retention.cleanup.running": "Background cleanup is running.",
        "app.settings.retention.cleanup.complete": "Background cleanup complete.",
        "app.settings.retention.cleanup.failed": "Background cleanup failed.",
        "app.settings.retention.cleanup.skipped": "Background cleanup was skipped: {reason}",
        "app.settings.retention.cleanup.summary": "Latest run {time} · retention {days} days · deleted {deleted} rounds, retained {skipped}, failed {failed}",
        "app.settings.retention.cleanup.failures": "Failures: {items}",
        "app.settings.retention.cleanup.protected": "Retained because: {items}",
        "app.settings.retention.cleanup.item": "{round_id}: {reason}",
        "app.settings.retention.reason.close": "Cleanup paused while records are being saved for app close.",
        "app.settings.retention.reason.protected": "Protected during this app session.",
        "app.settings.retention.reason.timezone": "Trusted archive time has no time zone.",
        "app.settings.retention.reason.not_expired": "The retention period has not elapsed.",
        "app.settings.retention.reason.deleted": "Trusted round records were completely deleted.",
        "app.settings.retention.reason.unsafe_manifest": "The archive path contains a symbolic link or is outside the managed area.",
        "app.settings.retention.reason.invalid_archive": "Archive evidence is invalid.",
        "app.settings.retention.reason.unsafe_component": "A required record path contains a symbolic link or is outside the managed area.",
        "app.settings.retention.reason.archive_path_mismatch": "The archive path does not match its verified path.",
        "app.settings.retention.reason.unknown_file": "The round directory contains an unknown file; the round was retained.",
        "app.settings.retention.reason.recovery_protected": "The interrupted round is currently protected.",
        "app.settings.retention.reason.invalid_plan": "The persistent deletion plan or round components could not be trusted.",
        "app.settings.retention.reason.recovery_summary": "Deletion was already complete; the interrupted summary was restored.",
        "app.settings.retention.reason.recovered_not_expired": "The current retention period has not elapsed. Staged data was restored and remaining records were retained.",
        "app.settings.retention.reason.period_changed": "The retention period changed during cleanup; remaining records were retained for reassessment.",
        "app.settings.retention.reason.recovered_deleted": "The interrupted deletion plan was completed.",
        "app.settings.retention.reason.archive_unknown_version": "The archive metadata version is not supported.",
        "app.settings.retention.reason.archive_invalid_time": "The archive time is invalid or has no time zone.",
        "app.settings.retention.reason.archive_read_failed": "Archive metadata could not be read: {diagnostic}",
        "app.settings.retention.reason.archive_format_invalid": "Archive metadata format is invalid.",
        "app.settings.retention.reason.archive_integrity_failed": "Archive integrity verification failed.",
        "app.settings.retention.reason.archive_round_identity_mismatch": "The archive round identity does not match.",
        "app.settings.retention.reason.archive_integrity_missing": "Archive integrity data is missing.",
        "app.settings.retention.reason.archive_components_incomplete": "Archive components are incomplete.",
        "app.settings.retention.reason.archive_component_format_invalid": "Archive component metadata format is invalid.",
        "app.settings.retention.reason.archive_component_path_invalid": "An archive component path is invalid.",
        "app.settings.retention.reason.archive_component_read_failed": "A required round record is missing or unreadable: {diagnostic}",
        "app.settings.retention.reason.archive_component_changed": "A required round record changed after archival.",
        "app.settings.retention.reason.archive_component_rebuild_failed": "Required round records could not be rebuilt: {diagnostic}",
        "app.settings.retention.reason.archive_disk_incomplete": "Disk records are incomplete or bound to another round.",
        "app.settings.event.profile.validation_failed": "Configuration draft validation failed: {reason}",
        "app.settings.event.profile.validated": "Engineer configuration draft validated",
        "app.settings.event.profile.path_selected": "Configuration folder selected",
        "app.settings.event.profile.saved": "Engineer configuration saved",
        "app.settings.event.profile.loaded": "Saved engineer configuration loaded",
        "app.settings.event.profile.imported": "Engineer configuration imported",
        "app.settings.event.profile.exported": "Engineer configuration exported",
        "app.settings.event.profile.cancelled": "Engineer configuration draft cancelled",
        "app.settings.event.retention.invalid": "Retention setting was rejected: {reason}",
        "app.settings.event.retention.save_failed": "Retention setting could not be saved: {reason}",
        "app.settings.event.retention.saved": "Global retention setting saved",
        "app.settings.event.session.open_failed": "Session records could not be opened: {reason}",
        "app.language.preference_save_failed": "Language changed for this session but could not be saved: {reason}",
        "app.event_store.initialize_failed": "App diagnostic history could not be initialized: {reason}",
        "app.event_store.write_failed": "App diagnostic history could not be saved: {reason}",
        "app.event_store.recovered": "App diagnostic history save recovery completed",
        "app.event_store.title": "App Diagnostics Not Saved",
        "app.save.retry_started": "Retrying App diagnostic saves",
        "app.save.pending": "Saving App diagnostics ({count} pending)",
        "app.save.failed": "App diagnostic records are not fully saved: {reason}",
        "app.save.complete": "App diagnostic records are fully saved",
        "app.diagnostic.heading": "App diagnostics",
        "app.diagnostic.retry": "Retry App Saves",
        "app.diagnostic.close": "Close",
        "app.diagnostic.event_time": "Event time",
        "app.diagnostic.event_id": "Event identity",
        "app.diagnostic.message_id": "Message identity",
        "app.diagnostic.parameters": "Captured parameters",
        "app.diagnostic.raw": "Original diagnostic",
        "app.diagnostic.save_history": "Previous App save errors (current status: {status}): {history}",
        "app.diagnostic.save_state.failed": "failed",
        "app.diagnostic.save_state.saving": "saving",
        "app.diagnostic.save_state.complete": "complete",
        "app.close.saving": "Stopping collection and saving App diagnostics and round records…",
        "app.close.waiting": "Waiting for required App and round save handoffs…",
        "app.close.failed": "Required App diagnostics or round records are not fully saved. Repair storage and retry; this window remains open.",
        "app.close.complete": "All required App diagnostics, Session and audit records for this run are fully saved.",
        "app.close.cancelled": "Close cancelled. Save work continues, and stopped sources will not restart automatically.",
        "app.close.title": "Save Before Closing",
        "app.close.language_disabled": "Language changes are unavailable while this close-and-save request is active. Cancel closing to change language.",
        "app.close.diagnostic": "Original save diagnostic: {reason}",
        "app.close.retry": "Retry Save",
        "app.close.cancel": "Cancel Closing",
        "main.settings": "Settings",
        "main.review": "Awaiting Review",
        "main.review_count": "Awaiting Review ({count})",
        "main.round_alarm": "Round Alarm",
        "main.round_alarm_pending": "Round Alarm (Awaiting Review)",
        "main.round_alarm_acknowledged": "Round Alarm (Acknowledged)",
        "conflict.title": "Same-Round Result Conflict",
        "conflict.instructions": "Choose whether to keep the original result or accept the captured new candidate for each item. Closing this window does not make a decision.",
        "conflict.position": "Display position: {position}",
        "conflict.unknown": "Unknown",
        "conflict.path.root": "root",
        "conflict.path.relative": "relative path",
        "conflict.empty": "There are no items awaiting review.",
        "conflict.list_item": "Position {position}: {original_sn} {original_status} → {candidate_sn} {candidate_status}",
        "conflict.comparison.item": "Item",
        "conflict.comparison.original": "Original Result",
        "conflict.comparison.candidate": "New Candidate",
        "conflict.field.result": "Result",
        "conflict.field.sn": "SN",
        "conflict.detail.round": "Test Round",
        "conflict.detail.conflict": "Conflict",
        "conflict.detail.position": "Display position",
        "conflict.detail.same_round_evidence": "Same-round evidence",
        "conflict.detail.original": "Original Result",
        "conflict.detail.candidate_snapshot": "New Candidate Snapshot",
        "conflict.detail.sn": "SN",
        "conflict.detail.result": "Result",
        "conflict.detail.source": "Source",
        "conflict.detail.source_identity": "Source identity",
        "conflict.detail.source_time": "Source Time",
        "conflict.detail.evidence": "Evidence",
        "conflict.button.keep_original": "Keep Original Result",
        "conflict.button.accept_candidate": "Accept New Candidate",
        "conflict.button.close": "Close",
        "alarm.title": "Round Monitoring Timeout",
        "alarm.body": "The round monitoring limit was reached. New source reads have stopped. Existing terminal results were retained, and unfinished positions were handled using their observed activity.\n\n{round_label}: {round_id}\n{alarm_label}: {alarm_id}\n{created_label}: {created_at}\n{status}",
        "alarm.round": "Test Round",
        "alarm.identity": "Alarm",
        "alarm.created_at": "Created at",
        "alarm.status.pending": "Acknowledge this alarm to continue. Result conflicts still require individual review.",
        "alarm.status.acknowledged": "This alarm is acknowledged; other review items still require individual decisions.",
        "alarm.status.preparation_pending": "Source preparation is still running. The alarm cannot be acknowledged yet.",
        "alarm.status.conflict_note": "Acknowledging this alarm does not accept or clear result conflicts.",
        "alarm.button.acknowledge": "Acknowledge Round Alarm",
        "alarm.button.acknowledged": "Acknowledged",
        "alarm.button.close": "Close",
        "main.project": "Project",
        "main.machine_type": "Station Type",
        "main.kvm_result": "KVM RESULT",
        "main.kvm_legend": "KVM Status Template",
        "main.slot_heading": "Slot",
        "main.status_heading": "Status",
        "main.serial_heading": "Product SN",
        "main.start_monitor": "Start Monitoring  (Command+Shift+M)",
        "main.stop": "Stop",
        "main.save.waiting": "Waiting to save",
        "main.save.saving": "Saving",
        "main.save.failed": "Save Failed",
        "main.save.complete": "Saved Completely",
        "main.retry_save": "Retry Save",
        "main.unsaved_rounds": "Unsaved rounds: {count}",
        "main.retry_selected": "Retry Selected",
        "main.retry_archive": "Retry Archive",
        "main.archive_summary": "Rounds: {unsaved} unsaved · {saved} saved · {archived} archived",
        "main.archive_protected": "Saved · Protected",
        "main.archived": "Trusted Archive",
        "main.slot": "Slot {number}",
        "main.station_title": "{machine} Log Monitoring",
        'round.started': '{station} round start accepted',
        'round.ready': '{station} monitoring source ready',
        'round.collection_stopped': '{station} stopped collecting new source data',
        'round.stopped': '{station} monitoring stopped by operator',
        'round.finished': '{station} round completed',
        'round.timeout.slot': '{station} Slot {slot} timed out: {status} after {elapsed} seconds (limit {deadline} seconds)',
        'round.timeout.whole': '{station} round monitoring timed out after {elapsed} seconds (limit {deadline} seconds)',
        'round.alarm.created': '{station} round timeout alarm created',
        'round.alarm.acknowledged': 'Round timeout alarm acknowledged; other review items remain',
        'round.alarm.ignored': 'Round alarm acknowledgement ignored',
        'round.conflict.detected': 'Slot {slot} has a same-round result conflict and awaits review',
        'round.conflict.detected.unknown_position': 'A result conflict with unknown position awaits review',
        'round.conflict.kept_original': 'Slot {slot}: original result kept',
        'round.conflict.kept_original.unknown_position': 'Original result kept for a conflict with unknown position',
        'round.conflict.accepted_candidate': 'Slot {slot}: new candidate accepted',
        'round.conflict.accepted_candidate.unknown_position': 'A new candidate was accepted for a conflict with unknown position',
        'round.duplicate_source': 'Slot {slot}: duplicate source recorded',
        'round.duplicate_source.unknown_position': 'A duplicate source with unknown position was recorded',
        'round.unknown_candidate_rejected': 'Slot {slot}: source could not be linked to this round; candidate rejected and result set to FAIL',
        'round.unknown_candidate_rejected.unknown_position': 'A source with unknown position could not be linked to this round; candidate rejected',
        'round.audit_write_failed': '{station} audit event could not be saved',
        'round.session_write_failed': '{station} Session event could not be saved',
        'round.save_recovered': '{station} Session and audit save recovery completed',
        'round.start_failed': '{station} monitoring source preparation failed',
        "monitor.idle": "Standby",
        "monitor.active": "Monitoring",
        "monitor.starting": "Starting",
        "monitor.closing": "Saving before close",
        "monitor.start_failed": "Start Failed",
        "monitor.timeout_stopped": "Stopped after timeout",
        "monitor.awaiting_conflicts": "Awaiting Review: {count} conflicts",
        "monitor.awaiting_alarm": "Awaiting Review: Round Alarm",
        "monitor.awaiting_both": "Awaiting Review: {count} conflicts · Round Alarm",
        "monitor.completed": "Round Complete",
        "monitor.stopped": "Stopped",
        "round.result": "{station} Slot {slot} result: {status}",
        "round.result.unknown_position": "{station} result: {status} (position unknown)",
        "platform.atlas.source_prepared": "Atlas source snapshot is ready",
        "platform.atlas.sn_locked": "Atlas Slot {slot} trusted serial number locked",
        "platform.atlas.final": "Atlas Slot {slot} final result: {status}",
        "platform.atlas.unresolved_conflict": "Atlas Slot {slot} source identity changed; evidence retained for review",
        "platform.atlas.source_error": "Atlas source file could not be read: {source_filename}",
        "platform.b482.batch": "B482 source batch observed: {batch_id}",
        "platform.b482.batch_mismatch": "B482 Slot {slot} evidence belongs to a different batch",
        "platform.b482.source_error": "B482 source file could not be read: {source_filename}",
        "platform.rswmt.batch": "RS-WMT source batch observed",
        "platform.rswmt.warning": "RS-WMT source could not be accepted: {source_filename}",
        "platform.sample_json.invalid_record": "Sample JSON source record is invalid: {source_filename}",
        "platform.sample_json.unsupported_record": "Sample JSON record is unsupported: {source_filename}",
        "platform.sample_json.invalid_fields": "Sample JSON fields are invalid: {source_filename}",
        "platform.sample_json.invalid_status": "Sample JSON final status is unsupported: {source_filename}",
        "platform.sample_json.unreadable": "Sample JSON source could not be read: {source_filename}",
    },
    TRADITIONAL_CHINESE: {
        "app.title": "B518 Log Solution-V0.1.0",
        "term.test_round": "測試輪次",
        "term.awaiting_review": "待確認",
        "term.station_type": "工站類型",
        "term.original_result": "原結果",
        "term.new_candidate": "新候選",
        "term.source_time": "來源時間",
        "term.source_filename": "來源檔名",
        "language.menu_hint": "選擇顯示語言",
        "language.save_failed": "語言已切換供本次使用，但保存失敗：{reason}",
        "language.invalid_saved": "已保存的語言無法使用，將改用 English。",
        "language.invalid_saved_title": "語言設定",
        "language.save_failed_title": "語言設定未保存",
        "app.startup.preferences_read_failed": "無法讀取偏好設定：{reason}",
        "app.startup.started": "App 已啟動",
        "app.startup.title": "App 初始化",
        "app.preferences.invalid_language": "已保存的語言無法使用，將改用 English。",
        "app.profile.validation_failed": "所選配置無效：{reason}",
        "app.profile.save_failed": "無法保存配置偏好；目前有效配置保持不變：{reason}",
        "app.profile.import_failed": "無法匯入配置；原配置仍有效：{reason}",
        "app.profile.export_failed": "無法匯出配置：{reason}",
        "app.hotkey.unavailable": "全域快捷鍵無法使用",
        "app.hotkey.title": "全域快捷鍵",
        "app.profile.validation_title": "配置錯誤",
        "app.profile.save_title": "配置保存失敗",
        "app.settings.title": "B518 Log Solution 設定",
        "app.settings.tab.configuration": "工程師配置",
        "app.settings.tab.events": "事件與 Session",
        "app.settings.tab.retention": "保存期限",
        "app.settings.session.open": "開啟 Session 紀錄",
        "app.settings.session.open_failed": "無法開啟 Session 紀錄：{reason}",
        "app.settings.profile.project": "專案代號",
        "app.settings.profile.station_type": "工站類型",
        "app.settings.profile.platform": "平台",
        "app.settings.profile.capacity": "測試容量",
        "app.settings.profile.mapping": "來源:顯示位置映射",
        "app.settings.profile.path_active": "即時 Log 路徑",
        "app.settings.profile.path_final": "最終結果路徑",
        "app.settings.profile.path_caseinfo": "CaseInfo／進度路徑（選填）",
        "app.settings.profile.choose_directory": "選擇本機資料夾",
        "app.settings.profile.timeout_start": "開始期限（秒）",
        "app.settings.profile.timeout_test": "測試期限（秒）",
        "app.settings.profile.timeout_round": "整輪期限（秒）",
        "app.settings.profile.load": "載入已保存配置",
        "app.settings.profile.validate": "驗證草稿",
        "app.settings.profile.apply": "套用並保存",
        "app.settings.profile.cancel": "取消草稿",
        "app.settings.profile.import": "匯入配置",
        "app.settings.profile.export": "匯出配置",
        "app.settings.profile.reload": "重新載入部署配置",
        "app.settings.profile.status.draft": "編輯草稿；路徑只做結構檢查，實際可讀性在開始監控前檢查。",
        "app.settings.profile.status.invalid": "配置欄位錯誤：{reason}",
        "app.settings.profile.status.valid": "結構驗證通過；部署電腦仍會在開始前檢查路徑。",
        "app.settings.profile.status.saved": "配置已套用並保存；更新供後續輪次使用。",
        "app.settings.profile.status.cancelled": "草稿已取消，已保存配置未變更。",
        "app.settings.profile.status.not_found": "找不到符合此選擇的已保存配置：{reason}",
        "app.settings.profile.status.loaded": "已載入已保存配置作為草稿。",
        "app.settings.profile.status.imported": "配置已驗證、匯入並保存。",
        "app.settings.profile.status.import_selection": "匯入後原選擇不存在；已切換至文件中的有效配置：{project} / {machine}。",
        "app.settings.profile.status.exported": "已匯出 {count} 組配置。",
        "app.settings.profile.status.reload_failed": "重新載入失敗，目前有效配置保持不變：{reason}",
        "app.settings.profile.status.reloaded": "已重新載入部署配置；進行中的輪次仍使用原快照。",
        "app.settings.profile.status.reload_selection": "重新載入後原選擇不存在；已切換至偏好檔中的有效配置：{project} / {machine}。",
        "app.settings.profile.status.active_removed": "目前選擇已從配置清單移除；請選擇有效專案與工站類型。",
        "app.settings.profile.status.import_selection_missing": "匯入或重新載入的建議選擇無效。",
        "app.settings.profile.import.title": "匯入工程師配置",
        "app.settings.profile.import.type_json": "JSON 配置",
        "app.settings.profile.import.type_all": "所有檔案",
        "app.settings.profile.export.title": "匯出工程師配置",
        "app.settings.profile.export.type_json": "JSON 配置",
        "app.settings.profile.path.title": "選擇配置路徑",
        "app.settings.retention.effective": "目前生效：{days} 天",
        "app.settings.retention.days": "全域保存天數",
        "app.settings.retention.save": "保存設定",
        "app.settings.retention.status.saved": "設定已保存。",
        "app.settings.retention.status.invalid": "設定無效：保存天數必須是正整數。",
        "app.settings.retention.status.read_failed": "設定無效或偏好檔無法讀取，目前仍生效 {days} 天：{reason}",
        "app.settings.retention.status.save_failed": "保存失敗，目前仍生效 {days} 天：{reason}",
        "app.settings.retention.status.shortened": "保存天數已更新；既有符合條件的紀錄可能於下一次背景清理到期。",
        "app.settings.retention.status.updated": "保存天數已更新並持久保存。",
        "app.settings.retention.help": "保存期限從輪次可信封存時間起算，每天按完整 24 小時計算。\n縮短期限可能使既有符合條件的紀錄於下一次背景清理時到期。\n符合期限且可信完整保存的輪次會在背景清理，執行結果列於下方摘要。",
        "app.settings.retention.cleanup.heading": "背景清理摘要",
        "app.settings.retention.cleanup.idle": "背景清理尚未執行。",
        "app.settings.retention.cleanup.running": "背景清理進行中。",
        "app.settings.retention.cleanup.complete": "背景清理完成。",
        "app.settings.retention.cleanup.failed": "背景清理失敗。",
        "app.settings.retention.cleanup.skipped": "背景清理已略過：{reason}",
        "app.settings.retention.cleanup.summary": "最近執行 {time} · 保存 {days} 天 · 刪除 {deleted} 輪、保留 {skipped} 輪、失敗 {failed} 輪",
        "app.settings.retention.cleanup.failures": "失敗：{items}",
        "app.settings.retention.cleanup.protected": "保留原因：{items}",
        "app.settings.retention.cleanup.item": "{round_id}：{reason}",
        "app.settings.retention.reason.close": "關閉保存期間暫停清理。",
        "app.settings.retention.reason.protected": "本次 App 執行仍受保護。",
        "app.settings.retention.reason.timezone": "可信封存時間缺少時區。",
        "app.settings.retention.reason.not_expired": "尚未到保存期限。",
        "app.settings.retention.reason.deleted": "已完整刪除可信輪次資料。",
        "app.settings.retention.reason.unsafe_manifest": "封存檔路徑含符號連結或越界。",
        "app.settings.retention.reason.invalid_archive": "封存證據無效。",
        "app.settings.retention.reason.unsafe_component": "必要資料路徑含符號連結或不在 App 管理範圍。",
        "app.settings.retention.reason.archive_path_mismatch": "封存路徑與驗證後路徑不一致。",
        "app.settings.retention.reason.unknown_file": "輪次目錄含未知檔案，整輪保留。",
        "app.settings.retention.reason.recovery_protected": "中斷清理輪次目前仍受保護。",
        "app.settings.retention.reason.invalid_plan": "持久刪除計畫格式或輪次組件不可信。",
        "app.settings.retention.reason.recovery_summary": "刪除已完成，補寫先前中斷的摘要。",
        "app.settings.retention.reason.recovered_not_expired": "目前保存期限尚未到期；已還原中斷時的暫置資料並保留其餘進度。",
        "app.settings.retention.reason.period_changed": "保存期限在清理期間變更，保留剩餘資料等待重新判定。",
        "app.settings.retention.reason.recovered_deleted": "依持久刪除計畫完成中斷復原。",
        "app.settings.retention.reason.archive_unknown_version": "封存資訊版本不受支援。",
        "app.settings.retention.reason.archive_invalid_time": "封存時間無效或缺少時區。",
        "app.settings.retention.reason.archive_read_failed": "無法讀取封存資訊：{diagnostic}",
        "app.settings.retention.reason.archive_format_invalid": "封存資訊格式不正確。",
        "app.settings.retention.reason.archive_integrity_failed": "封存資訊完整性驗證失敗。",
        "app.settings.retention.reason.archive_round_identity_mismatch": "封存輪次身分不一致。",
        "app.settings.retention.reason.archive_integrity_missing": "封存完整性資訊缺失。",
        "app.settings.retention.reason.archive_components_incomplete": "封存組成資料不完整。",
        "app.settings.retention.reason.archive_component_format_invalid": "封存組成資料格式不正確。",
        "app.settings.retention.reason.archive_component_path_invalid": "封存組成資料路徑不正確。",
        "app.settings.retention.reason.archive_component_read_failed": "必要輪次紀錄缺失或無法讀取：{diagnostic}",
        "app.settings.retention.reason.archive_component_changed": "必要輪次紀錄內容已變更。",
        "app.settings.retention.reason.archive_component_rebuild_failed": "必要輪次紀錄無法重建：{diagnostic}",
        "app.settings.retention.reason.archive_disk_incomplete": "磁碟紀錄未完整保存或輪次身分不一致。",
        "app.settings.event.profile.validation_failed": "配置草稿驗證失敗：{reason}",
        "app.settings.event.profile.validated": "工程師配置草稿驗證通過",
        "app.settings.event.profile.path_selected": "已選擇配置資料夾",
        "app.settings.event.profile.saved": "工程師配置已保存",
        "app.settings.event.profile.loaded": "已載入工程師配置",
        "app.settings.event.profile.imported": "已匯入工程師配置",
        "app.settings.event.profile.exported": "已匯出工程師配置",
        "app.settings.event.profile.cancelled": "已取消工程師配置草稿",
        "app.settings.event.retention.invalid": "保存期限設定遭拒絕：{reason}",
        "app.settings.event.retention.save_failed": "無法保存保存期限設定：{reason}",
        "app.settings.event.retention.saved": "全域保存期限設定已保存",
        "app.settings.event.session.open_failed": "無法開啟 Session 紀錄：{reason}",
        "app.language.preference_save_failed": "語言已切換供本次使用，但保存失敗：{reason}",
        "app.event_store.initialize_failed": "無法初始化 App 診斷紀錄：{reason}",
        "app.event_store.write_failed": "無法保存 App 診斷紀錄：{reason}",
        "app.event_store.recovered": "App 診斷紀錄已完成保存復原",
        "app.event_store.title": "App 診斷紀錄未保存",
        "app.save.retry_started": "正在重試保存 App 診斷紀錄",
        "app.save.pending": "正在保存 App 診斷紀錄（待保存 {count} 筆）",
        "app.save.failed": "App 診斷紀錄尚未完整保存：{reason}",
        "app.save.complete": "App 診斷紀錄已完整保存",
        "app.diagnostic.heading": "App 診斷",
        "app.diagnostic.retry": "重試 App 保存",
        "app.diagnostic.close": "關閉",
        "app.diagnostic.event_time": "事件時間",
        "app.diagnostic.event_id": "事件識別",
        "app.diagnostic.message_id": "訊息識別",
        "app.diagnostic.parameters": "捕捉參數",
        "app.diagnostic.raw": "原始診斷",
        "app.diagnostic.save_history": "過去的 App 保存錯誤（目前狀態：{status}）：{history}",
        "app.diagnostic.save_state.failed": "失敗",
        "app.diagnostic.save_state.saving": "保存中",
        "app.diagnostic.save_state.complete": "完整保存",
        "app.close.saving": "正在停止收集並保存 App 診斷及輪次紀錄…",
        "app.close.waiting": "正在等待 App 與輪次保存交接完成…",
        "app.close.failed": "App 診斷或輪次紀錄尚未完整保存。修復保存位置或磁碟問題後可重試；視窗仍保持開啟。",
        "app.close.complete": "本次執行的全部必要 App 診斷、Session 與 audit 紀錄均已完整保存。",
        "app.close.cancelled": "已取消關閉；保存工作會繼續，來源不會自動重新啟動。",
        "app.close.title": "關閉前保存",
        "app.close.language_disabled": "關閉與保存作業進行中，暫時無法切換語言。取消關閉後即可切換。",
        "app.close.diagnostic": "原始保存診斷：{reason}",
        "app.close.retry": "重試保存",
        "app.close.cancel": "取消關閉",
        "main.settings": "設定",
        "main.review": "待確認",
        "main.review_count": "待確認 ({count})",
        "main.round_alarm": "整輪警報",
        "main.round_alarm_pending": "整輪警報（待確認）",
        "main.round_alarm_acknowledged": "整輪警報已確認",
        "conflict.title": "同輪結果衝突",
        "conflict.instructions": "請逐項選擇保留原結果或採用已捕捉的新候選；關閉視窗不會做出裁決。",
        "conflict.position": "顯示位置：{position}",
        "conflict.unknown": "未知",
        "conflict.path.root": "根目錄",
        "conflict.path.relative": "相對路徑",
        "conflict.empty": "目前沒有待確認項目。",
        "conflict.list_item": "位置 {position}：{original_sn} {original_status} → {candidate_sn} {candidate_status}",
        "conflict.comparison.item": "項目",
        "conflict.comparison.original": "原結果",
        "conflict.comparison.candidate": "新候選",
        "conflict.field.result": "結果",
        "conflict.field.sn": "SN",
        "conflict.detail.round": "測試輪次",
        "conflict.detail.conflict": "衝突",
        "conflict.detail.position": "顯示位置",
        "conflict.detail.same_round_evidence": "同輪證據",
        "conflict.detail.original": "原結果",
        "conflict.detail.candidate_snapshot": "新候選快照",
        "conflict.detail.sn": "SN",
        "conflict.detail.result": "結果",
        "conflict.detail.source": "來源",
        "conflict.detail.source_identity": "來源識別",
        "conflict.detail.source_time": "來源時間",
        "conflict.detail.evidence": "證據",
        "conflict.button.keep_original": "保留原結果",
        "conflict.button.accept_candidate": "採用新候選",
        "conflict.button.close": "關閉",
        "alarm.title": "整輪監控逾時",
        "alarm.body": "整輪監控已到達設定上限。新的來源讀取已停止，既有終態已保留，未完成位置已依活動證據裁決。\n\n{round_label}：{round_id}\n{alarm_label}：{alarm_id}\n{created_label}：{created_at}\n{status}",
        "alarm.round": "測試輪次",
        "alarm.identity": "警報",
        "alarm.created_at": "建立時間",
        "alarm.status.pending": "請確認此警報以解除提醒；結果衝突仍須逐項覆核。",
        "alarm.status.acknowledged": "此警報已確認；其他待確認事項仍須逐項處理。",
        "alarm.status.preparation_pending": "來源準備仍在進行，暫時無法確認此警報。",
        "alarm.status.conflict_note": "確認此警報不會接受或清除結果衝突。",
        "alarm.button.acknowledge": "確認整輪警報",
        "alarm.button.acknowledged": "已確認",
        "alarm.button.close": "關閉",
        "main.project": "專案",
        "main.machine_type": "機型",
        "main.kvm_result": "KVM RESULT",
        "main.kvm_legend": "KVM 狀態模板",
        "main.slot_heading": "通道",
        "main.status_heading": "狀態",
        "main.serial_heading": "產品 SN",
        "main.start_monitor": "開始監控  (Command+Shift+M)",
        "main.stop": "停止",
        "main.save.waiting": "等待保存",
        "main.save.saving": "保存中",
        "main.save.failed": "保存失敗",
        "main.save.complete": "完整保存",
        "main.retry_save": "重試保存",
        "main.unsaved_rounds": "未保存輪次 {count}",
        "main.retry_selected": "重試所選",
        "main.retry_archive": "重試封存",
        "main.archive_summary": "輪次：未完整保存 {unsaved} · 完整保存 {saved} · 可信封存 {archived}",
        "main.archive_protected": "完整保存・受保護",
        "main.archived": "可信封存",
        "main.slot": "通道 {number}",
        "main.station_title": "{machine} Log 監控",
        'round.started': '{station} 已接受開始本輪',
        'round.ready': '{station} 監控來源已就緒',
        'round.collection_stopped': '{station} 已停止收集新來源資料',
        'round.stopped': '{station} 監控已由人員停止',
        'round.finished': '{station} 本輪已完成',
        'round.timeout.slot': '{station} 通道 {slot} 逾時：經過 {elapsed} 秒，期限 {deadline} 秒，結果 {status}',
        'round.timeout.whole': '{station} 整輪監控逾時：經過 {elapsed} 秒，期限 {deadline} 秒',
        'round.alarm.created': '{station} 已建立整輪逾時警報',
        'round.alarm.acknowledged': '整輪逾時警報已確認；仍有其他項目待確認',
        'round.alarm.ignored': '整輪警報確認已忽略',
        'round.conflict.detected': '通道 {slot} 發現同輪結果衝突，等待人工確認',
        'round.conflict.detected.unknown_position': '位置未知的結果衝突等待人工確認',
        'round.conflict.kept_original': '通道 {slot}：已保留原結果',
        'round.conflict.kept_original.unknown_position': '位置未知的衝突已保留原結果',
        'round.conflict.accepted_candidate': '通道 {slot}：已採用新候選',
        'round.conflict.accepted_candidate.unknown_position': '位置未知的衝突已採用新候選',
        'round.duplicate_source': '通道 {slot}：已記錄重複來源',
        'round.duplicate_source.unknown_position': '已記錄位置未知的重複來源',
        'round.unknown_candidate_rejected': '通道 {slot}：無法確認來源屬於本輪；已拒絕候選並判定 FAIL',
        'round.unknown_candidate_rejected.unknown_position': '無法確認位置未知的來源屬於本輪；已拒絕候選',
        'round.audit_write_failed': '{station} 稽核事件保存失敗',
        'round.session_write_failed': '{station} Session 事件保存失敗',
        'round.save_recovered': '{station} Session 與稽核紀錄已完成保存復原',
        'round.start_failed': '{station} 監控來源準備失敗',
        "monitor.idle": "待命",
        "monitor.active": "監控中",
        "monitor.starting": "啟動中",
        "monitor.closing": "關閉前保存中",
        "monitor.start_failed": "啟動失敗",
        "monitor.timeout_stopped": "逾時停止",
        "monitor.awaiting_conflicts": "待確認：衝突 {count} 項",
        "monitor.awaiting_alarm": "待確認：整輪警報",
        "monitor.awaiting_both": "待確認：衝突 {count} 項、整輪警報",
        "monitor.completed": "本輪完成",
        "monitor.stopped": "已停止",
        "round.result": "{station} 通道 {slot} 結果：{status}",
        "round.result.unknown_position": "{station} 結果：{status}（位置未知）",
        "platform.atlas.source_prepared": "Atlas 來源快照已就緒",
        "platform.atlas.sn_locked": "Atlas 通道 {slot} 已鎖定可信序號",
        "platform.atlas.final": "Atlas 通道 {slot} 最終結果：{status}",
        "platform.atlas.unresolved_conflict": "Atlas 通道 {slot} 來源身分改變；證據已保留供覆核",
        "platform.atlas.source_error": "Atlas 來源檔案無法讀取：{source_filename}",
        "platform.b482.batch": "B482 已觀察來源批次：{batch_id}",
        "platform.b482.batch_mismatch": "B482 通道 {slot} 證據屬於不同批次",
        "platform.b482.source_error": "B482 來源檔案無法讀取：{source_filename}",
        "platform.rswmt.batch": "RS-WMT 已觀察來源批次",
        "platform.rswmt.warning": "RS-WMT 來源無法接受：{source_filename}",
        "platform.sample_json.invalid_record": "Sample JSON 來源記錄無效：{source_filename}",
        "platform.sample_json.unsupported_record": "Sample JSON 記錄不受支援：{source_filename}",
        "platform.sample_json.invalid_fields": "Sample JSON 欄位無效：{source_filename}",
        "platform.sample_json.invalid_status": "Sample JSON 最終狀態不受支援：{source_filename}",
        "platform.sample_json.unreadable": "Sample JSON 來源無法讀取：{source_filename}",
    },
}


def is_supported_language(value: object) -> bool:
    return isinstance(value, str) and value in SUPPORTED_LANGUAGE_CODES


def language_name(language: str) -> str:
    for code, name in LANGUAGE_OPTIONS:
        if code == language:
            return name
    return dict(LANGUAGE_OPTIONS)[DEFAULT_LANGUAGE]


def save_state_message_id(state: str) -> str:
    return {
        "waiting": "main.save.waiting",
        "saving": "main.save.saving",
        "failed": "main.save.failed",
        "complete": "main.save.complete",
    }.get(state, "main.save.saving")


def translate(message_id: str, language: str = DEFAULT_LANGUAGE, **parameters: object) -> str:
    english = LANGUAGE_RESOURCES[ENGLISH].get(message_id)
    if english is None:
        raise KeyError("Unknown message identifier: {}".format(message_id))
    template = LANGUAGE_RESOURCES.get(language, {}).get(message_id) or english
    return template.format(**parameters)


@dataclass(frozen=True)
class BilingualMessage:
    """One immutable bilingual rendering snapshot attached to one event."""

    message_id: str
    parameters_json: str
    english: str
    traditional_chinese: str
    diagnostic: str = ""
    version: int = 1

    def as_record(self) -> dict:
        return {
            "version": self.version,
            "message_id": self.message_id,
            "parameters": json.loads(self.parameters_json),
            "en": self.english,
            "zh-TW": self.traditional_chinese,
            "diagnostic": self.diagnostic,
        }


def make_bilingual_message(message_id: str, parameters: Mapping[str, object],
                           diagnostic: str = "") -> BilingualMessage:
    """Capture parameters and both rendered languages once, at event creation."""
    parameters_json = json.dumps(dict(parameters), ensure_ascii=False, sort_keys=True)
    captured = json.loads(parameters_json)
    return BilingualMessage(
        message_id=message_id,
        parameters_json=parameters_json,
        english=translate(message_id, ENGLISH, **captured),
        traditional_chinese=translate(message_id, TRADITIONAL_CHINESE, **captured),
        diagnostic=diagnostic,
    )


def capture_round_event_message(kind: str, station: str, slot: object, status: str,
                                detail: Mapping[str, object], legacy_message: str,
                                display_slot: object = None) -> Optional[BilingualMessage]:
    """Capture the bilingual description for one supported shared-round event."""
    message_id = None
    parameters = {"station": station}
    diagnostic = ""
    if kind == "result":
        if slot is not None and display_slot is None:
            return None
        if slot is None:
            message_id = "round.result.unknown_position"
            parameters["status"] = status or "unknown"
        else:
            message_id = "round.result"
            parameters.update(slot=display_slot, status=status or "unknown")
    elif kind == "round_started":
        message_id = "round.started"
    elif kind == "round_ready":
        message_id = "round.ready"
    elif kind == "collection_stopped":
        message_id = "round.collection_stopped"
    elif kind == "stopped":
        message_id = "round.stopped"
    elif kind == "finished":
        message_id = "round.finished"
    elif kind == "timeout":
        parameters.update(elapsed=detail.get("elapsed_seconds", "unknown"),
                          deadline=detail.get("deadline_seconds", "unknown"))
        if slot is not None:
            if display_slot is None:
                return None
            message_id = "round.timeout.slot"
            parameters.update(slot=display_slot, status=status or "unknown")
        else:
            message_id = "round.timeout.whole"
    elif kind == "round_alarm_created":
        message_id = "round.alarm.created"
    elif kind == "round_alarm_acknowledged":
        message_id = "round.alarm.acknowledged"
    elif kind == "round_alarm_acknowledgement_ignored":
        message_id = "round.alarm.ignored"
    elif kind == "conflict_detected":
        if slot is not None and display_slot is None:
            return None
        if display_slot is None:
            message_id = "round.conflict.detected.unknown_position"
        else:
            message_id = "round.conflict.detected"
            parameters["slot"] = display_slot
    elif kind == "conflict_resolved":
        if slot is not None and display_slot is None:
            return None
        accepted = detail.get("choice") == "accept_candidate"
        message_id = ("round.conflict.accepted_candidate" if accepted
                      else "round.conflict.kept_original")
        if display_slot is None:
            message_id += ".unknown_position"
        else:
            parameters["slot"] = display_slot
    elif kind == "duplicate_source":
        if slot is not None and display_slot is None:
            return None
        if display_slot is None:
            message_id = "round.duplicate_source.unknown_position"
        else:
            message_id = "round.duplicate_source"
            parameters["slot"] = display_slot
    elif kind == "unknown_round_candidate_rejected":
        if slot is not None and display_slot is None:
            return None
        if display_slot is None:
            message_id = "round.unknown_candidate_rejected.unknown_position"
        else:
            message_id = "round.unknown_candidate_rejected"
            parameters["slot"] = display_slot
    elif kind == "audit_write_failed":
        message_id, diagnostic = "round.audit_write_failed", legacy_message
    elif kind == "session_write_failed":
        message_id, diagnostic = "round.session_write_failed", legacy_message
    elif kind == "save_recovered":
        message_id = "round.save_recovered"
    elif kind == "start_failed":
        message_id, diagnostic = "round.start_failed", legacy_message
    if message_id is None:
        return None
    return make_bilingual_message(message_id, parameters, diagnostic)


def render_bilingual_message(message: object, language: str, fallback: str = "") -> str:
    """Render a captured event in the selected language without changing it."""
    if isinstance(message, BilingualMessage):
        record = message.as_record()
    elif isinstance(message, Mapping):
        record = dict(message)
    else:
        return fallback
    if record.get("version") != 1:
        return fallback
    try:
        return translate(str(record["message_id"]), language,
                         **dict(record.get("parameters", {})))
    except (KeyError, TypeError, ValueError):
        localized = record.get("zh-TW" if language == TRADITIONAL_CHINESE else "en")
        return localized if isinstance(localized, str) else fallback


def validate_translations() -> Tuple[str, ...]:
    """Return missing or parameter-mismatched localized resources."""
    english = LANGUAGE_RESOURCES[ENGLISH]
    expected_keys = set(english)
    errors = []
    formatter = Formatter()
    for language, _name in LANGUAGE_OPTIONS:
        resources = LANGUAGE_RESOURCES.get(language, {})
        for missing in sorted(expected_keys - set(resources)):
            errors.append("{} is missing {}".format(language, missing))
        for extra in sorted(set(resources) - expected_keys):
            errors.append("{} has unknown message {}".format(language, extra))
        for message_id in sorted(expected_keys & set(resources)):
            english_parameters = {field for _literal, field, _spec, _conversion
                                  in formatter.parse(english[message_id]) if field}
            translated_parameters = {field for _literal, field, _spec, _conversion
                                     in formatter.parse(resources[message_id]) if field}
            if english_parameters != translated_parameters:
                errors.append("{} has mismatched parameters for {}".format(language, message_id))
    return tuple(errors)
