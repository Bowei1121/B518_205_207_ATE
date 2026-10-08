import unittest
from unittest.mock import patch

import language_catalog


class LanguageCatalogTests(unittest.TestCase):
    def test_main_message_translates_with_named_parameters(self):
        self.assertEqual(language_catalog.translate("main.settings", "en"), "Settings")
        self.assertEqual(language_catalog.translate("main.settings", "zh-TW"), "設定")
        self.assertEqual(
            language_catalog.translate("main.station_title", "zh-TW", machine="B482"),
            "B482 Log 監控",
        )

    def test_missing_translation_falls_back_to_english(self):
        resources = {
            "en": {"main.settings": "Settings"},
            "zh-TW": {},
        }
        with patch.object(language_catalog, "LANGUAGE_RESOURCES", resources):
            self.assertEqual(language_catalog.translate("main.settings", "zh-TW"), "Settings")

    def test_shared_round_and_conflict_terms_use_the_approved_glossary(self):
        expected = {
            "test_round": ("Test Round", "測試輪次"),
            "awaiting_review": ("Awaiting Review", "待確認"),
            "station_type": ("Station Type", "工站類型"),
            "original_result": ("Original Result", "原結果"),
            "new_candidate": ("New Candidate", "新候選"),
            "source_time": ("Source Time", "來源時間"),
            "source_filename": ("Source Filename", "來源檔名"),
        }
        for term, (english, chinese) in expected.items():
            with self.subTest(term=term):
                self.assertEqual(language_catalog.translate("term." + term, "en"), english)
                self.assertEqual(language_catalog.translate("term." + term, "zh-TW"), chinese)

    def test_unknown_language_uses_english_and_release_catalog_is_complete(self):
        self.assertEqual(language_catalog.translate("main.settings", "fr"), "Settings")
        self.assertEqual(language_catalog.validate_translations(), ())

    def test_slotless_round_events_never_invent_slot_zero(self):
        for kind, detail in (
                ("conflict_detected", {}),
                ("conflict_resolved", {"choice": "keep_original"}),
                ("duplicate_source", {}),
                ("unknown_round_candidate_rejected", {})):
            with self.subTest(kind=kind):
                message = language_catalog.capture_round_event_message(
                    kind, "FCT", None, "FAIL", detail, "event",
                )
                self.assertIsNotNone(message)
                self.assertIn("unknown position", message.english.lower())
                self.assertIn("位置未知", message.traditional_chinese)
                self.assertNotIn("Slot 0", message.english)
                self.assertNotIn("通道 0", message.traditional_chinese)
                if kind == "unknown_round_candidate_rejected":
                    self.assertNotIn("result set to FAIL", message.english)
                    self.assertNotIn("判定 FAIL", message.traditional_chinese)

        result = language_catalog.capture_round_event_message(
            "result", "FCT", None, "PASS", {}, "round result",
        )
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
