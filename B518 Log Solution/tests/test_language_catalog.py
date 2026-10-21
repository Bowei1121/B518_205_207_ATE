import unittest
from unittest.mock import patch

import language_catalog


class LanguageCatalogTests(unittest.TestCase):
    def test_profile_folder_action_uses_the_compact_browse_copy(self):
        self.assertEqual(language_catalog.translate(
            "app.settings.profile.choose_directory", "en"), "📂 Browse")
        self.assertEqual(language_catalog.translate(
            "app.settings.profile.choose_directory", "zh-TW"), "📂 瀏覽")

    def test_main_message_translates_with_named_parameters(self):
        self.assertEqual(language_catalog.translate("main.settings", "en"), "Settings")
        self.assertEqual(language_catalog.translate("main.settings", "zh-TW"), "設定")
        self.assertEqual(language_catalog.translate(
            "app.title", "en", version="0.1.0"), "ATE Log Solution-V0.1.0")
        self.assertEqual(language_catalog.translate(
            "main.language", "zh-TW", current_language="English"),
            "選擇語言（目前：English）")
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

    def test_start_deadline_audit_events_capture_bilingual_explanations(self):
        events = (
            ("timeout", "NOTEST", {"reason": "start_deadline_no_activity",
                                     "deadline_seconds": "120", "elapsed_seconds": "120"},
             "timeout"),
            ("round_alarm_created", "", {"reason": "start_deadline_no_activity"}, "alarm"),
        )
        expected = {
            "timeout": (
                "B518：開始期限 120 秒內未偵測到測試開始。來源收集已停止；這不代表已確認 ATE 故障。",
                "B518: No test start was detected within 120 seconds. Source collection has stopped; this does not confirm an ATE failure.",
            ),
            "alarm": (
                "B518 已建立警報：開始期限內未偵測到測試開始。",
                "B518 alarm: No test start was detected within the configured start deadline.",
            ),
        }

        for kind, status, detail, key in events:
            with self.subTest(kind=kind):
                captured = language_catalog.capture_round_event_message(
                    kind, "B518", None, status, detail, "legacy")
                record = captured.as_record()
                self.assertEqual(record["message_id"],
                                 "round.start_deadline.whole" if key == "timeout"
                                 else "round.start_deadline.alarm.created")
                self.assertEqual(record["zh-TW"], expected[key][0])
                self.assertEqual(record["en"], expected[key][1])

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

    def test_recovery_center_explains_zero_state_and_archive_retry_scope_in_both_languages(self):
        self.assertEqual(language_catalog.translate("recovery.no_alarms", "zh-TW"),
                         "沒有追蹤中的整輪警報")
        self.assertIn("does not acknowledge alarms", language_catalog.translate(
            "recovery.no_alarms_detail", "en"))
        self.assertEqual(language_catalog.translate(
            "recovery.retry_all_archives", "zh-TW", count=3),
            "重試所有符合資格的封存（3）")
        self.assertEqual(language_catalog.translate(
            "recovery.retry_all_archives", "en", count=3),
            "Retry all eligible archives (3)")
        self.assertTrue(language_catalog.translate(
            "alarm.reason.round_deadline", "en"))
        self.assertTrue(language_catalog.translate(
            "alarm.reason.round_deadline", "zh-TW"))

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
        self.assertIsNotNone(result)
        self.assertEqual(result.message_id, "round.result.unknown_position")
        self.assertIn("FCT result: PASS", result.english)
        self.assertIn("位置未知", result.traditional_chinese)
        self.assertNotIn("Slot 0", result.english)
        self.assertNotIn("通道 0", result.traditional_chinese)

    def test_conflict_and_alarm_copy_has_complete_shared_bilingual_resources(self):
        required = {
            "conflict.title", "conflict.instructions", "conflict.position",
            "conflict.empty", "conflict.path.root", "conflict.path.relative",
            "conflict.list_item", "conflict.comparison.item",
            "conflict.detail.round", "conflict.detail.conflict",
            "conflict.detail.same_round_evidence", "conflict.detail.candidate_snapshot",
            "conflict.detail.source_identity", "conflict.button.keep_original",
            "conflict.button.accept_candidate", "conflict.button.close",
            "alarm.title", "alarm.body", "alarm.round", "alarm.identity",
            "alarm.created_at", "alarm.status.pending", "alarm.status.acknowledged",
            "alarm.status.preparation_pending", "alarm.status.conflict_note",
            "alarm.button.acknowledge", "alarm.button.close",
            "alarm.button.acknowledged",
        }
        sample_parameters = {
            "position": 2, "original_sn": "SN-OLD", "original_status": "PASS",
            "candidate_sn": "SN-NEW", "candidate_status": "FAIL",
            "round_label": "Round", "round_id": "round-1", "alarm_label": "Alarm",
            "alarm_id": "alarm-1", "created_label": "Created at",
            "created_at": "2026-10-09T01:02:03", "status": "Awaiting review",
        }
        for language in (language_catalog.ENGLISH, language_catalog.TRADITIONAL_CHINESE):
            for message_id in required:
                with self.subTest(language=language, message_id=message_id):
                    rendered = language_catalog.translate(message_id, language,
                                                           **sample_parameters)
                    self.assertTrue(rendered.strip())
                    self.assertNotEqual(rendered, message_id)
            self.assertEqual(
                language_catalog.translate("conflict.detail.round", language),
                language_catalog.translate("term.test_round", language),
            )
            self.assertEqual(
                language_catalog.translate("alarm.round", language),
                language_catalog.translate("term.test_round", language),
            )

        self.assertEqual(
            language_catalog.translate("conflict.comparison.original", language_catalog.ENGLISH),
            language_catalog.translate("term.original_result", language_catalog.ENGLISH),
        )
        self.assertEqual(
            language_catalog.translate("conflict.comparison.candidate", language_catalog.TRADITIONAL_CHINESE),
            language_catalog.translate("term.new_candidate", language_catalog.TRADITIONAL_CHINESE),
        )

    def test_hc6_hints_explain_actions_and_preserve_review_history_semantics(self):
        expected_copy = {
            "conflict.hint.keep_original": (
                "keeping the original result", "保留這筆原結果"),
            "conflict.hint.accept_candidate": (
                "choosing the new candidate", "選擇這筆新候選作為結果"),
            "conflict.hint.close": (
                "without deciding any result or removing", "不會替你決定結果或移除"),
            "app.settings.history.search_hint": (
                "This result stays fixed", "這次查詢的結果會固定保留"),
            "app.settings.history.retry_hint.ready": (
                "remaining pages", "尚未完成的頁面"),
            "app.diagnostic.retry_hint.enabled": (
                "records that did not save", "尚未存好的 App 問題紀錄"),
        }
        for message_id, (english_phrase, chinese_phrase) in expected_copy.items():
            with self.subTest(message_id=message_id):
                english = language_catalog.translate(message_id, language_catalog.ENGLISH)
                chinese = language_catalog.translate(
                    message_id, language_catalog.TRADITIONAL_CHINESE)
                self.assertIn(english_phrase, english)
                self.assertIn(chinese_phrase, chinese)

        self.assertIn("Other items awaiting review still need a decision",
                      language_catalog.translate(
                          "conflict.hint.accept_candidate", language_catalog.ENGLISH))
        self.assertIn("其他待確認項目仍需逐項決定",
                      language_catalog.translate(
                          "conflict.hint.accept_candidate",
                          language_catalog.TRADITIONAL_CHINESE))
        self.assertIn("saved records are not changed",
                      language_catalog.translate(
                          "app.settings.history.search_hint", language_catalog.ENGLISH))
        self.assertIn("不會修改已保存的紀錄",
                      language_catalog.translate(
                          "app.settings.history.search_hint",
                          language_catalog.TRADITIONAL_CHINESE))

        self.assertEqual(
            language_catalog.translate(
                "app.settings.history.retry_hint.unavailable", language_catalog.ENGLISH),
            "No history pages are currently available to retry.",
        )
        self.assertEqual(
            language_catalog.translate(
                "app.settings.history.retry_hint.unavailable",
                language_catalog.TRADITIONAL_CHINESE),
            "目前沒有可重試的歷史頁面。",
        )


if __name__ == "__main__":
    unittest.main()
