"""Supported App languages and their native display names."""

import json
from dataclasses import dataclass
from string import Formatter
from typing import Dict, Mapping, Tuple

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
        'round.conflict.kept_original': 'Slot {slot}: original result kept',
        'round.conflict.accepted_candidate': 'Slot {slot}: new candidate accepted',
        'round.duplicate_source': 'Slot {slot}: duplicate source recorded',
        'round.unknown_candidate_rejected': 'Slot {slot}: source could not be linked to this round; candidate rejected and result set to FAIL',
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
        'round.conflict.kept_original': '通道 {slot}：已保留原結果',
        'round.conflict.accepted_candidate': '通道 {slot}：已採用新候選',
        'round.duplicate_source': '通道 {slot}：已記錄重複來源',
        'round.unknown_candidate_rejected': '通道 {slot}：無法確認來源屬於本輪；已拒絕候選並判定 FAIL',
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
                                display_slot: object = None) -> BilingualMessage:
    """Capture the bilingual description for one supported shared-round event."""
    message_id = None
    parameters = {"station": station}
    diagnostic = ""
    if kind == "result":
        if slot is not None and display_slot is None:
            return None
        message_id = "round.result"
        parameters.update(slot=display_slot if display_slot is not None else 0,
                          status=status or "unknown")
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
        message_id = "round.conflict.detected"
        parameters["slot"] = display_slot if display_slot is not None else 0
    elif kind == "conflict_resolved":
        if slot is not None and display_slot is None:
            return None
        message_id = ("round.conflict.accepted_candidate"
                      if detail.get("choice") == "accept_candidate"
                      else "round.conflict.kept_original")
        parameters["slot"] = display_slot if display_slot is not None else 0
    elif kind == "duplicate_source":
        if slot is not None and display_slot is None:
            return None
        message_id = "round.duplicate_source"
        parameters["slot"] = display_slot if display_slot is not None else 0
    elif kind == "unknown_round_candidate_rejected":
        if slot is not None and display_slot is None:
            return None
        message_id = "round.unknown_candidate_rejected"
        parameters["slot"] = display_slot if display_slot is not None else 0
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
