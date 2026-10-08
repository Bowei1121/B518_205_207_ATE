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
        "main.settings": "Settings",
        "main.review": "Awaiting Review",
        "main.review_count": "Awaiting Review ({count})",
        "main.round_alarm": "Round Alarm",
        "main.round_alarm_pending": "Round Alarm (Awaiting Review)",
        "main.round_alarm_acknowledged": "Round Alarm (Acknowledged)",
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
        "main.settings": "設定",
        "main.review": "待確認",
        "main.review_count": "待確認 ({count})",
        "main.round_alarm": "整輪警報",
        "main.round_alarm_pending": "整輪警報（待確認）",
        "main.round_alarm_acknowledged": "整輪警報已確認",
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
