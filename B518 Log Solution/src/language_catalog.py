"""Supported App languages and their native display names."""

from string import Formatter
from typing import Dict, Tuple

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
