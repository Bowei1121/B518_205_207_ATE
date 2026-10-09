import json
import tempfile
import unittest
from dataclasses import replace
from unittest.mock import patch
from pathlib import Path

from historical_event_display import read_historical_events, render_historical_event
from language_catalog import ENGLISH, LANGUAGE_RESOURCES, TRADITIONAL_CHINESE


class HistoricalEventDisplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sessions = self.root / "sessions"
        self.sessions.mkdir()

    def _write_audit(self, round_id, station, events, platform="atlas"):
        path = self.sessions / round_id / "audit.jsonl"
        path.parent.mkdir(parents=True)
        header = {"record_type": "round", "schema_version": 1, "round_id": round_id,
                  "station": station, "accepted_start_at": "2026-10-08T10:00:00+08:00",
                  "accepted_start_monotonic": 10.0, "config": {"platform": platform},
                  "time_contract": {"observed_at": "app observation"},
                  "legacy_session_path": None}
        path.write_text("\n".join(json.dumps(item, ensure_ascii=False) for item in
                                    [header] + events) + "\n", encoding="utf-8")
        return path

    @staticmethod
    def _legacy_event(round_id, sequence, kind, message, **values):
        event = {"record_type": "event", "schema_version": 1, "round_id": round_id,
                 "sequence": sequence, "kind": kind, "message": message,
                 "observed_at": "2026-10-08T10:01:00+08:00", "elapsed_seconds": 60.0,
                 "display_position": None, "detail": {}}
        event.update(values)
        return event

    def test_reads_mixed_rounds_and_translates_only_whitelisted_legacy_contract(self):
        round_id = "round-old"
        path = self._write_audit(round_id, "FCT", [
            self._legacy_event(round_id, 1, "round_started", "FCT 本輪已接受開始"),
            self._legacy_event(round_id, 2, "custom_note", "FCT 本輪已接受開始"),
        ])
        before = path.read_bytes()

        records = read_historical_events(self.sessions)

        self.assertEqual(len(records), 2)
        self.assertEqual(render_historical_event(records[0], ENGLISH).message,
                         "FCT round start accepted")
        self.assertEqual(render_historical_event(records[0], TRADITIONAL_CHINESE).message,
                         "FCT 已接受開始本輪")
        unknown = render_historical_event(records[1], TRADITIONAL_CHINESE)
        self.assertTrue(unknown.unrecognized)
        self.assertEqual(unknown.message, "無法安全翻譯此歷史事件；詳細資料保留原始紀錄。")
        self.assertIn('"original_message": "FCT 本輪已接受開始"', unknown.detail)
        self.assertEqual(path.read_bytes(), before)

    def test_equal_timestamp_round_events_keep_numeric_audit_sequence_order(self):
        round_id = "round-sequence-order"
        self._write_audit(round_id, "FCT", [
            self._legacy_event(round_id, 2, "round_started", "FCT 本輪已接受開始"),
            self._legacy_event(round_id, 10, "round_ready", "FCT 來源已就緒"),
        ])

        records = read_historical_events(self.sessions)

        self.assertEqual([record.sequence for record in records if record.source == "round"],
                         [2, 10])

    def test_legacy_result_requires_real_position_and_status_instead_of_filling_values(self):
        round_id = "round-result"
        path = self._write_audit(round_id, "FCT", [
            self._legacy_event(round_id, 1, "result", "slot1 PASS", display_position=1,
                               status="PASS", sn="SN-1"),
            self._legacy_event(round_id, 2, "timeout", "slot2 timeout", display_position=2,
                               status="TIMEOUT", detail={"kind": "test"}),
        ])

        records = read_historical_events(self.sessions)

        self.assertEqual(render_historical_event(records[0], ENGLISH).message,
                         "FCT Slot 1 result: PASS")
        unknown = render_historical_event(records[1], ENGLISH)
        self.assertTrue(unknown.unrecognized)
        self.assertIn('"original_message": "slot2 timeout"', unknown.detail)

    def test_legacy_platform_event_requires_platform_and_producer_contract(self):
        round_id = "round-atlas-legacy"
        path = self._write_audit(round_id, "FCT", [
            self._legacy_event(round_id, 1, "final", "slot1 最終 PASS", display_position=1,
                               status="PASS", source="/logs/slot1.csv"),
            self._legacy_event(round_id, 2, "warning", "Atlas source read failed: permission denied",
                               source="/logs/slot2.csv", detail={"raw_diagnostic": "permission denied"}),
        ])
        payload = path.read_text(encoding="utf-8").splitlines()
        header = json.loads(payload[0])
        header["config"]["platform"] = "atlas"
        payload[0] = json.dumps(header, ensure_ascii=False)
        path.write_text("\n".join(payload) + "\n", encoding="utf-8")

        records = read_historical_events(self.sessions)

        self.assertEqual(render_historical_event(records[0], ENGLISH).message,
                         "Atlas Slot 1 final result: PASS")
        self.assertEqual(render_historical_event(records[1], ENGLISH).message,
                         "Atlas source file could not be read: slot2.csv")
        self.assertIn("permission denied", render_historical_event(records[1], ENGLISH).detail)

    def test_legacy_platform_warning_with_non_path_source_stays_readable(self):
        round_id = "round-malformed-source"
        path = self._write_audit(round_id, "FCT", [
            self._legacy_event(round_id, 1, "warning", "Atlas source read failed: denied",
                               source={"unexpected": "object"}),
        ])
        payload = path.read_text(encoding="utf-8").splitlines()
        header = json.loads(payload[0])
        header["config"]["platform"] = "atlas"
        payload[0] = json.dumps(header, ensure_ascii=False)
        path.write_text("\n".join(payload) + "\n", encoding="utf-8")

        record = next(item for item in read_historical_events(self.sessions)
                      if item.source == "round")
        rendered = render_historical_event(record, ENGLISH)

        self.assertTrue(rendered.unrecognized)
        self.assertIn("Atlas source read failed: denied", rendered.detail)
        self.assertIn('"unexpected": "object"', rendered.detail)

    def test_legacy_platform_translation_rejects_malformed_station_and_status_types(self):
        bad_status_round = "round-bad-status"
        self._write_audit(bad_status_round, "FCT", [
            self._legacy_event(bad_status_round, 1, "final", "slot1 PASS",
                               display_position=1, status={"unexpected": "object"}),
        ])
        bad_station_round = "round-bad-station"
        self._write_audit(bad_station_round, {"unexpected": "object"}, [
            self._legacy_event(bad_station_round, 1, "round_started", "round started"),
        ])

        records = {record.key: record for record in read_historical_events(self.sessions)}

        bad_status = render_historical_event(
            records["round:{}:1".format(bad_status_round)], ENGLISH)
        bad_station = render_historical_event(
            records["round:{}:1".format(bad_station_round)], ENGLISH)
        self.assertTrue(bad_status.unrecognized)
        self.assertTrue(bad_station.unrecognized)
        self.assertIn('"unexpected": "object"', bad_station.detail)

    def test_positioned_legacy_timeout_rejects_malformed_status_type(self):
        round_id = "round-bad-timeout-status"
        self._write_audit(round_id, "FCT", [
            self._legacy_event(round_id, 1, "timeout", "slot1 timeout",
                               display_position=1, status={"unexpected": "object"},
                               elapsed_seconds=20, detail={"deadline_seconds": 10}),
        ])

        record = next(item for item in read_historical_events(self.sessions)
                      if item.source == "round")
        rendered = render_historical_event(record, ENGLISH)

        self.assertTrue(rendered.unrecognized)
        self.assertIn('"original_message": "slot1 timeout"', rendered.detail)
        self.assertIn('"unexpected": "object"', rendered.detail)

    def test_legacy_b482_and_rswmt_events_require_platform_and_producer_contract(self):
        batch_id = "B-2026-10-09"
        b482_round = "round-b482-legacy"
        self._write_audit(b482_round, "BT", [
            self._legacy_event(b482_round, 1, "batch", "BT observed old batch",
                               detail={"batch_id": batch_id}),
            self._legacy_event(b482_round, 2, "batch_observed", "BT mismatch", display_position=3),
            self._legacy_event(b482_round, 3, "warning", "B482 source read failed: denied",
                               source="/b482/caseinfo.csv"),
        ], platform="b482")
        rswmt_round = "round-rswmt-legacy"
        self._write_audit(rswmt_round, "BT", [
            self._legacy_event(rswmt_round, 1, "batch", "RS batch"),
            self._legacy_event(rswmt_round, 2, "warning",
                               "RS-WMT: source log could not be read: denied",
                               source="/rswmt/output.csv"),
            self._legacy_event(rswmt_round, 3, "warning", "custom note with source",
                               source="/rswmt/output.csv"),
        ], platform="rswmt")

        records = {record.key: record for record in read_historical_events(self.sessions)}

        self.assertEqual(render_historical_event(
            records["round:{}:1".format(b482_round)], ENGLISH).message,
            "B482 source batch observed: {}".format(batch_id))
        self.assertEqual(render_historical_event(
            records["round:{}:2".format(b482_round)], ENGLISH).message,
            "B482 Slot 3 evidence belongs to a different batch")
        self.assertEqual(render_historical_event(
            records["round:{}:3".format(b482_round)], ENGLISH).message,
            "B482 source file could not be read: caseinfo.csv")
        self.assertEqual(render_historical_event(
            records["round:{}:1".format(rswmt_round)], ENGLISH).message,
            "RS-WMT source batch observed")
        self.assertEqual(render_historical_event(
            records["round:{}:2".format(rswmt_round)], ENGLISH).message,
            "RS-WMT source could not be accepted: output.csv")
        self.assertTrue(render_historical_event(
            records["round:{}:3".format(rswmt_round)], ENGLISH).unrecognized)

    def test_bad_legacy_lines_have_distinct_view_keys(self):
        legacy = self.sessions / "old-session" / "events.log"
        legacy.parent.mkdir()
        legacy.write_text("{broken one\n{broken two\n", encoding="utf-8")

        records = read_historical_events(self.sessions)

        self.assertEqual(len(records), 2)
        self.assertEqual(len({record.key for record in records}), 2)
        details = [render_historical_event(record, ENGLISH).detail for record in records]
        self.assertTrue(any("{broken one" in detail for detail in details))
        self.assertTrue(any("{broken two" in detail for detail in details))

    def test_mixed_timezone_offsets_sort_by_instant_and_legacy_sequence_types_stay_safe(self):
        app_path = self.root / "app-events.json"
        payload = {"record_type": "app_event_store", "schema_version": 1, "events": [
            {"record_type": "app_event", "schema_version": 1, "event_id": "earlier",
             "sequence": 1, "occurred_at": "2026-10-08T09:30:00+08:00",
             "kind": "app_diagnostic", "message": "earlier",
             "localized_message": {"version": 1, "message_id": "app.startup.started",
                                   "parameters": {}, "en": "earlier", "zh-TW": "earlier"},
             "diagnostic": ""},
            {"record_type": "app_event", "schema_version": 1, "event_id": "later",
             "sequence": 2, "occurred_at": "2026-10-08T02:00:00+00:00",
             "kind": "app_diagnostic", "message": "later",
             "localized_message": {"version": 1, "message_id": "app.startup.started",
                                   "parameters": {}, "en": "later", "zh-TW": "later"},
             "diagnostic": ""},
        ]}
        app_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        records = read_historical_events(self.sessions, app_path)
        self.assertEqual([record.key for record in records], ["app:earlier", "app:later"])

        legacy = self.sessions / "legacy-sequence" / "events.log"
        legacy.parent.mkdir()
        legacy.write_text("\n".join(json.dumps({
            "timestamp": "2026-10-08T10:00:00", "sequence": sequence,
            "message": message,
        }, ensure_ascii=False) for sequence, message in (("invalid", "first"), (2, "second")))
                          + "\n", encoding="utf-8")
        legacy_records = [record for record in read_historical_events(self.sessions)
                          if record.source == "legacy_session"]
        self.assertEqual([record.message for record in legacy_records], ["first", "second"])

    def test_new_app_event_uses_current_resource_and_keeps_saved_english_and_diagnostic(self):
        app_path = self.root / "app-events.json"
        payload = {"record_type": "app_event_store", "schema_version": 1, "events": [{
            "record_type": "app_event", "schema_version": 1, "event_id": "event-1",
            "sequence": 1, "occurred_at": "2026-10-08T10:00:00+00:00",
            "kind": "app_diagnostic", "message": "saved English at event time",
            "localized_message": {"version": 1, "message_id": "app.startup.started",
                                  "parameters": {}, "en": "saved English at event time",
                                  "zh-TW": "當時保存的中文"},
            "diagnostic": "OSError: original path",
        }]}
        app_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        before = app_path.read_bytes()

        records = read_historical_events(self.sessions, app_path)

        self.assertEqual(len(records), 1)
        english = render_historical_event(records[0], ENGLISH)
        chinese = render_historical_event(records[0], TRADITIONAL_CHINESE)
        self.assertEqual(english.message, "Application started")
        self.assertEqual(chinese.message, "App 已啟動")
        self.assertIn("saved English at event time", english.detail)
        self.assertIn("OSError: original path", chinese.detail)
        self.assertEqual(app_path.read_bytes(), before)

    def test_resource_updates_change_only_display_and_missing_or_unsupported_resources_fall_back(self):
        app_path = self.root / "app-events.json"
        payload = {"record_type": "app_event_store", "schema_version": 1, "events": [{
            "record_type": "app_event", "schema_version": 1, "event_id": "event-1",
            "sequence": 1, "occurred_at": "2026-10-08T10:00:00+00:00",
            "kind": "app_diagnostic", "message": "captured English",
            "localized_message": {"version": 1, "message_id": "app.startup.started",
                                  "parameters": {}, "en": "captured English",
                                  "zh-TW": "捕捉時中文"},
            "diagnostic": "original exception",
        }]}
        app_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        before = app_path.read_bytes()
        event = read_historical_events(self.sessions, app_path)[0]

        with patch.dict(LANGUAGE_RESOURCES[ENGLISH], {"app.startup.started": "Application launched"}):
            self.assertEqual(render_historical_event(event, ENGLISH).message, "Application launched")
        unknown = replace(event, localized_message=dict(
            event.localized_message, message_id="removed.message"))
        self.assertEqual(render_historical_event(unknown, ENGLISH).message, "captured English")
        self.assertEqual(render_historical_event(unknown, TRADITIONAL_CHINESE).message,
                         "captured English")
        unsupported = replace(event, localized_message=dict(
            event.localized_message, version=88))
        self.assertEqual(render_historical_event(unsupported, TRADITIONAL_CHINESE).message,
                         "captured English")
        self.assertEqual(app_path.read_bytes(), before)

    def test_legacy_session_without_machine_kind_is_kept_as_original(self):
        legacy = self.sessions / "old-session" / "events.log"
        legacy.parent.mkdir()
        legacy.write_text(json.dumps({"timestamp": "2026-10-08T10:00:00",
                                      "message": "FCT 本輪已接受開始",
                                      "detail": {"operator_text": "do not translate"}},
                                     ensure_ascii=False) + "\n", encoding="utf-8")

        record = read_historical_events(self.sessions)[0]
        rendered = render_historical_event(record, ENGLISH)

        self.assertTrue(rendered.unrecognized)
        self.assertIn("FCT 本輪已接受開始", rendered.detail)
        self.assertIsNone(record.round_id)


if __name__ == "__main__":
    unittest.main()
