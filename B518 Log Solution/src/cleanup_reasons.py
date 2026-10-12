"""Safe presentation of current and historical cleanup reasons.

This module owns presentation only. Cleanup eligibility and deletion decisions
remain with the retention and archive validators.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from language_catalog import (
    DEFAULT_LANGUAGE,
    ENGLISH,
    LANGUAGE_RESOURCES,
    TRADITIONAL_CHINESE,
    make_bilingual_message,
    translate,
)


_LEGACY_REASON_IDS = {
    "期限時間缺少時區": "app_events_timezone",
    "App 事件清理拒絕符號連結": "app_events_symlink",
    "App 事件檔不在管理根目錄": "app_events_outside",
    "App 事件目標不是一般檔案": "app_events_not_regular",
    "App 事件紀錄在清理期間已變更": "app_events_changed",
    "App 事件管理路徑在清理期間已變更": "app_events_path_changed",
    "App 事件保存待補存或狀態尚未確認完整": "app_events_pending",
    "App 事件紀錄格式或版本不受支援": "app_events_unknown_format",
    "App 事件紀錄內容不完整或序號不連續": "app_events_invalid",
    "App 事件紀錄序號保留資訊需要新版格式": "app_events_sequence_invalid",
    "App 事件紀錄序號保留資訊不完整": "app_events_sequence_missing",
    "App 事件紀錄序號保留資訊無效": "app_events_sequence_invalid",
    "App 事件紀錄序號保留範圍無效": "app_events_sequence_invalid",
    "App 事件紀錄存在未解釋的序號缺口": "app_events_sequence_gap",
    "App 事件紀錄已刪除序號仍有事件": "app_events_sequence_invalid",
    "App 事件時間格式無效": "app_events_time_invalid",
    "App 事件時間缺少時區": "app_events_time_missing",
    "App 事件清理提交閘門未完成原子替換": "app_events_invalid",
    "關閉保存期間不啟動新清理": "close",
    "封存資訊版本未知": "archive_unknown_version",
    "封存時間無效或缺少時區": "archive_invalid_time",
    "封存資訊格式不正確": "archive_format_invalid",
    "封存資訊完整性驗證失敗": "archive_integrity_failed",
    "封存輪次身分不一致": "archive_round_identity_mismatch",
    "封存完整性資訊缺失": "archive_integrity_missing",
    "封存組成資料不完整": "archive_components_incomplete",
    "封存組成資料格式不正確": "archive_component_format_invalid",
    "封存組成資料路徑不正確": "archive_component_path_invalid",
    "必要輪次紀錄內容已變更": "archive_component_changed",
    "磁碟紀錄未完整保存或輪次身分不一致": "archive_disk_incomplete",
    "關閉保存期間暫停清理": "close",
    "本次 App 執行仍受保護": "protected",
    "可信封存時間缺少時區": "timezone",
    # Preserve the former App-view priority for this shared legacy string.
    "尚未到保存期限": "app_events_not_expired",
    "已完整刪除可信輪次資料": "deleted",
    "封存檔路徑含符號連結或越界": "unsafe_manifest",
    "封存證據無效": "invalid_archive",
    "必要資料路徑含符號連結或不在 App 管理範圍": "unsafe_component",
    "封存路徑與驗證後路徑不一致": "archive_path_mismatch",
    "輪次目錄含未知檔案，整輪保留": "unknown_file",
    "中斷清理輪次目前仍受保護": "recovery_protected",
    "持久刪除計畫格式或輪次組件不可信": "invalid_plan",
    "刪除已完成，補寫先前中斷的摘要": "recovery_summary",
    "目前保存期限尚未到期；已還原中斷時的暫置資料並保留其餘進度":
        "recovered_not_expired",
    "保存期限在清理期間變更，保留剩餘資料等待重新判定": "period_changed",
    "依持久刪除計畫完成中斷復原": "recovered_deleted",
}

# These exact producer prefixes are emitted by the archive and App-event readers.
# Matching is limited to the full prefix; no token, substring or fuzzy matching is used.
_LEGACY_DIAGNOSTIC_PREFIXES = {
    "App 事件紀錄無法讀取：": "app_events_read_failed",
    "封存資訊無法讀取：": "archive_read_failed",
    "必要輪次紀錄缺失或無法讀取：": "archive_component_read_failed",
    "必要輪次紀錄無法重建：": "archive_component_rebuild_failed",
}


@dataclass(frozen=True)
class ReasonPresentation:
    """Display text plus untouched evidence for a cleanup reason."""

    text: str
    original: object
    diagnostic: str = ""
    recognized: bool = False


def capture_cleanup_reason(message_id: str, parameters: Mapping[str, object],
                           diagnostic: str = "") -> dict:
    """Capture a cleanup reason as one English/Traditional Chinese record."""
    return make_bilingual_message(message_id, parameters, diagnostic).as_record()


def present_cleanup_reason(reason: object, language: str = DEFAULT_LANGUAGE) -> ReasonPresentation:
    """Render a structured reason or an exact, documented legacy reason safely."""
    if isinstance(reason, Mapping):
        return _present_structured_reason(reason, language)
    if isinstance(reason, str):
        return _present_legacy_reason(reason, language)
    return ReasonPresentation(_unrecognized_text(language), reason, recognized=False)


def _present_structured_reason(reason: Mapping[str, object], language: str) -> ReasonPresentation:
    diagnostic = reason.get("diagnostic")
    diagnostic_text = diagnostic if isinstance(diagnostic, str) else ""
    message_id = reason.get("message_id")
    parameters = reason.get("parameters")
    english = reason.get("en")
    chinese = reason.get("zh-TW")
    valid = (type(reason.get("version")) is int and reason.get("version") == 1 and
             isinstance(message_id, str) and bool(message_id) and
             isinstance(parameters, Mapping) and
             all(isinstance(key, str) for key in parameters) and
             all(_is_safe_parameter(value) for value in parameters.values()) and
             isinstance(english, str) and bool(english) and
             isinstance(chinese, str) and bool(chinese) and
             ("diagnostic" not in reason or isinstance(diagnostic, str)))
    if not valid:
        return ReasonPresentation(_unrecognized_text(language), dict(reason), diagnostic_text)

    resources = LANGUAGE_RESOURCES.get(ENGLISH, {})
    if message_id not in resources:
        return ReasonPresentation(_unrecognized_text(language), dict(reason), diagnostic_text)
    try:
        rendered = translate(message_id, language, **dict(parameters))
    except (KeyError, TypeError, ValueError):
        rendered = english
    return ReasonPresentation(rendered, dict(reason), diagnostic_text, recognized=True)


def _present_legacy_reason(reason: str, language: str) -> ReasonPresentation:
    message_id = _LEGACY_REASON_IDS.get(reason)
    if message_id is not None:
        return ReasonPresentation(_legacy_translation(message_id, language, {}), reason,
                                  recognized=True)
    for prefix, message_id in _LEGACY_DIAGNOSTIC_PREFIXES.items():
        if reason.startswith(prefix) and len(reason) > len(prefix):
            parameter = {"diagnostic": reason[len(prefix):]}
            return ReasonPresentation(_legacy_translation(message_id, language, parameter),
                                      reason, reason[len(prefix):], recognized=True)
    return ReasonPresentation(_unrecognized_text(language), reason)


def _legacy_translation(suffix: str, language: str, parameters: Mapping[str, object]) -> str:
    message_id = "app.settings.retention.reason." + suffix
    try:
        return translate(message_id, language, **dict(parameters))
    except (KeyError, TypeError, ValueError):
        try:
            return translate(message_id, ENGLISH, **dict(parameters))
        except (KeyError, TypeError, ValueError):
            return _unrecognized_text(language)


def _unrecognized_text(language: str) -> str:
    message_id = "app.settings.retention.reason.unrecognized"
    try:
        return translate(message_id, language)
    except (KeyError, TypeError, ValueError):
        try:
            return translate(message_id, ENGLISH)
        except (KeyError, TypeError, ValueError):
            return "Cleanup reason is not recognized."


def _is_safe_parameter(value: object) -> bool:
    return value is None or type(value) in (str, int, float, bool)
