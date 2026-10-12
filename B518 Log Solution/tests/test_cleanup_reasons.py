import unittest
from unittest.mock import patch

from cleanup_reasons import capture_cleanup_reason, present_cleanup_reason
from language_catalog import ENGLISH, TRADITIONAL_CHINESE, LANGUAGE_RESOURCES


class CleanupReasonPresentationTests(unittest.TestCase):
    def test_new_reason_is_captured_once_and_rendered_from_current_catalog(self):
        captured = capture_cleanup_reason(
            "app.settings.retention.reason.archive_read_failed",
            {"diagnostic": "disk full"},
            diagnostic="raw disk diagnostic",
        )

        english = present_cleanup_reason(captured, ENGLISH)
        chinese = present_cleanup_reason(captured, TRADITIONAL_CHINESE)

        self.assertEqual(english.text, "Archive metadata could not be read: disk full")
        self.assertEqual(chinese.text, "無法讀取封存資訊：disk full")
        self.assertEqual(captured["en"], english.text)
        self.assertEqual(captured["zh-TW"], chinese.text)
        self.assertEqual(chinese.diagnostic, "raw disk diagnostic")
        self.assertEqual(chinese.original, captured)

    def test_missing_or_incompatible_resource_falls_back_to_captured_english(self):
        captured = capture_cleanup_reason(
            "app.settings.retention.reason.archive_read_failed",
            {"diagnostic": "disk full"},
        )
        with patch.dict(LANGUAGE_RESOURCES[TRADITIONAL_CHINESE],
                        {"app.settings.retention.reason.archive_read_failed": "broken {required}"}):
            rendered = present_cleanup_reason(captured, TRADITIONAL_CHINESE)

        self.assertEqual(rendered.text, captured["en"])

    def test_missing_selected_language_resource_falls_back_to_captured_english(self):
        captured = capture_cleanup_reason(
            "app.settings.retention.reason.archive_read_failed",
            {"diagnostic": "disk full"},
        )
        message_id = "app.settings.retention.reason.archive_read_failed"
        with patch.dict(LANGUAGE_RESOURCES[ENGLISH],
                        {message_id: "Updated catalog text: {diagnostic}"}):
            with patch.dict(LANGUAGE_RESOURCES[TRADITIONAL_CHINESE], {message_id: None}):
                rendered = present_cleanup_reason(captured, TRADITIONAL_CHINESE)

        self.assertEqual(rendered.text, captured["en"])

    def test_valid_record_with_unknown_identifier_uses_localized_unknown_fallback(self):
        unknown = {
            "version": 1,
            "message_id": "internal.cleanup.future_reason",
            "parameters": {"detail": "captured parameter"},
            "en": "Captured English from an unknown producer",
            "zh-TW": "未知產生端保存的繁中",
            "diagnostic": "raw cleanup diagnostic",
        }

        english = present_cleanup_reason(unknown, ENGLISH)
        chinese = present_cleanup_reason(unknown, TRADITIONAL_CHINESE)

        self.assertEqual(english.text, "Cleanup reason is not recognized.")
        self.assertEqual(chinese.text, "無法辨識此清理原因。")
        self.assertFalse(english.recognized)
        self.assertFalse(chinese.recognized)
        self.assertEqual(english.original, unknown)
        self.assertEqual(chinese.original, unknown)
        self.assertEqual(chinese.diagnostic, "raw cleanup diagnostic")

    def test_unknown_legacy_reason_has_localized_outer_message_and_verbatim_detail(self):
        english = present_cleanup_reason("custom operator reason", ENGLISH)
        chinese = present_cleanup_reason("custom operator reason", TRADITIONAL_CHINESE)

        self.assertEqual(english.text, "Cleanup reason is not recognized.")
        self.assertEqual(chinese.text, "無法辨識此清理原因。")
        self.assertEqual(english.original, "custom operator reason")
        self.assertEqual(chinese.original, "custom operator reason")

    def test_legacy_translation_requires_exact_contract_match(self):
        known = present_cleanup_reason("封存資訊版本未知", ENGLISH)
        similar = present_cleanup_reason("封存資訊版本未知；額外文字", ENGLISH)
        prefix_near_miss = present_cleanup_reason("封存資訊無法讀取 disk full", ENGLISH)

        self.assertEqual(known.text, "The archive metadata version is not supported.")
        self.assertEqual(similar.text, "Cleanup reason is not recognized.")
        self.assertEqual(similar.original, "封存資訊版本未知；額外文字")
        self.assertEqual(prefix_near_miss.text, "Cleanup reason is not recognized.")

    def test_exact_producer_prefix_preserves_unmodified_diagnostic(self):
        reason = "封存資訊無法讀取：disk full: errno 28"
        rendered = present_cleanup_reason(reason, ENGLISH)

        self.assertEqual(rendered.text, "Archive metadata could not be read: disk full: errno 28")
        self.assertEqual(rendered.diagnostic, "disk full: errno 28")
        self.assertEqual(rendered.original, reason)

    def test_malformed_new_reason_preserves_full_original_record_without_leaking_id(self):
        malformed = {
            "version": 99,
            "message_id": "internal.secret.key",
            "parameters": [],
            "en": "Captured English",
            "zh-TW": 8,
            "diagnostic": "raw diagnostic",
        }

        rendered = present_cleanup_reason(malformed, TRADITIONAL_CHINESE)

        self.assertEqual(rendered.text, "無法辨識此清理原因。")
        self.assertNotIn("internal.secret.key", rendered.text)
        self.assertEqual(rendered.original, malformed)
        self.assertEqual(rendered.diagnostic, "raw diagnostic")

    def test_incomplete_required_parameter_and_empty_legacy_diagnostic_are_not_guessed(self):
        incomplete = capture_cleanup_reason(
            "app.settings.retention.reason.archive_read_failed", {"diagnostic": "captured"})
        incomplete["parameters"] = {"other": "value"}
        missing_diagnostic = "封存資訊無法讀取："

        rendered = present_cleanup_reason(incomplete, TRADITIONAL_CHINESE)
        old_rendered = present_cleanup_reason(missing_diagnostic, TRADITIONAL_CHINESE)

        self.assertEqual(rendered.text, incomplete["en"])
        self.assertEqual(old_rendered.text, "無法辨識此清理原因。")
        self.assertEqual(old_rendered.original, missing_diagnostic)


if __name__ == "__main__":
    unittest.main()
