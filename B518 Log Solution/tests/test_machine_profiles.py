import json
import unittest
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory

from machine_profiles import (
    MachineProfile, MachineProfileStore, ProfileCatalog, ProfileError,
    migrate_legacy_preferences, profile_from_editor_fields,
)


def valid_profile():
    return {
        "project": "B518",
        "machine": "DFU",
        "platform": "atlas",
        "capacity": 2,
        "paths": {"active": "/tmp/active", "final": "/tmp/final"},
        "mapping": [{"source": 1, "display": 2}, {"source": 2, "display": 1}],
        "timeouts": {"start": 30, "test": 480, "round": 7200},
    }


class MachineProfileTests(unittest.TestCase):
    def test_global_language_defaults_to_english_and_reloads_from_preferences_disk(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "preferences.json"
            store = MachineProfileStore(path)
            store.load()
            self.assertEqual(store.language, "en")

            store.save_language("zh-TW")

            restarted = MachineProfileStore(path)
            restarted.load()
            self.assertEqual(restarted.language, "zh-TW")

    def test_legacy_preferences_without_language_default_to_english(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "preferences.json"
            catalog, _project, _machine = migrate_legacy_preferences({})
            path.write_text(catalog.to_json(), encoding="utf-8")

            store = MachineProfileStore(path)
            store.load()

            self.assertEqual(store.language, "en")
            self.assertIsNone(store.language_error)

    def test_profile_save_and_import_keep_global_language_but_export_only_profiles(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "preferences.json"
            export_path = Path(temporary) / "profiles.json"
            store = MachineProfileStore(path)
            catalog, _project, _machine, _error = store.load()
            store.save_language("zh-TW")

            store.save(catalog, "B518", "FCT")
            MachineProfileStore.export_document(export_path, catalog)
            store.import_document(catalog.to_json(), "B518", "FCT")

            restarted = MachineProfileStore(path)
            restarted.load()
            self.assertEqual(restarted.language, "zh-TW")
            self.assertNotIn("language", json.loads(export_path.read_text(encoding="utf-8")))

    def test_language_replace_failure_preserves_effective_setting_and_preferences_file(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "preferences.json"
            store = MachineProfileStore(path)
            catalog, _project, _machine, _error = store.load()
            store.save(catalog, "B518", "FCT")
            original = path.read_bytes()

            with patch("machine_profiles.os.replace", side_effect=OSError("disk full")):
                with self.assertRaisesRegex(OSError, "disk full"):
                    store.save_language("zh-TW")

            self.assertEqual(store.language, "en")
            self.assertEqual(path.read_bytes(), original)

    def test_unknown_saved_language_falls_back_to_english_with_diagnostic(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "preferences.json"
            catalog, _project, _machine = migrate_legacy_preferences({})
            raw = json.loads(catalog.to_json())
            raw.update({"project": "B518", "machine": "FCT", "language": "fr"})
            path.write_text(json.dumps(raw), encoding="utf-8")

            store = MachineProfileStore(path)
            store.load()

            self.assertEqual(store.language, "en")
            self.assertIn("語言設定無效", store.language_error)

    def test_global_retention_days_defaults_and_reload_from_preferences_disk(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "preferences.json"
            store = MachineProfileStore(path)
            store.load()
            self.assertEqual(store.retention_days, 365)

            store.save_retention_days(180)

            restarted = MachineProfileStore(path)
            restarted.load()
            self.assertEqual(restarted.retention_days, 180)

    def test_global_retention_days_reject_invalid_values_without_changing_saved_setting(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "preferences.json"
            store = MachineProfileStore(path)
            store.load()
            store.save_retention_days(730)
            original = path.read_bytes()

            for invalid in ("", "not-a-number", 0, -1, 1.5, True):
                with self.subTest(value=invalid), self.assertRaises(ProfileError):
                    store.save_retention_days(invalid)
                self.assertEqual(store.retention_days, 730)
                self.assertEqual(path.read_bytes(), original)

    def test_global_retention_save_failure_preserves_disk_and_effective_value(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "preferences.json"
            store = MachineProfileStore(path)
            store.load()
            original_catalog, _project, _machine = migrate_legacy_preferences({})
            store.save(original_catalog, "B518", "FCT")
            original = path.read_bytes()

            with patch("machine_profiles.os.replace", side_effect=OSError("disk full")):
                with self.assertRaisesRegex(OSError, "disk full"):
                    store.save_retention_days(180)

            self.assertEqual(store.retention_days, 365)
            self.assertEqual(path.read_bytes(), original)

    def test_profile_save_and_import_preserve_global_retention_but_exports_do_not_include_it(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "preferences.json"
            export_path = Path(temporary) / "profiles.json"
            store = MachineProfileStore(path)
            catalog, _project, _machine, _error = store.load()
            store.save(catalog, "B518", "FCT")
            store.save_retention_days(180)
            replacement = catalog.with_profile(MachineProfileStore(path).load()[0].get("B518", "FCT"))
            store.save(replacement, "B518", "FCT")
            MachineProfileStore.export_document(export_path, replacement)
            store.import_document(replacement.to_json(), "B518", "FCT")

            self.assertEqual(MachineProfileStore(path).load()[0].profiles, replacement.profiles)
            restarted = MachineProfileStore(path)
            restarted.load()
            self.assertEqual(restarted.retention_days, 180)
            self.assertNotIn("retention_days", json.loads(export_path.read_text(encoding="utf-8")))

    def test_profile_save_from_fresh_store_preserves_existing_global_retention(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "preferences.json"
            seeded = MachineProfileStore(path)
            catalog, _project, _machine, _error = seeded.load()
            seeded.save(catalog, "B518", "FCT")
            seeded.save_retention_days(180)

            fresh_writer = MachineProfileStore(path)
            fresh_writer.save(catalog, "B518", "FCT")

            restarted = MachineProfileStore(path)
            restarted.load()
            self.assertEqual(restarted.retention_days, 180)

    def test_capacity_and_source_positions_follow_parser_capabilities(self):
        for capacity in (1, 4, 6, 10, 12, 20):
            pairs = [{"source": source, "display": display}
                     for display, source in enumerate(range(20, 20 - capacity, -1), 1)]
            record = valid_profile()
            record.update({"capacity": capacity, "mapping": pairs})
            catalog = ProfileCatalog.from_dict({"schema_version": 1, "profiles": [record]})
            self.assertEqual(catalog.get("B518", "DFU").capacity, capacity)

        atlas_one_position = valid_profile()
        atlas_one_position.update({"capacity": 1, "mapping": [{"source": 20, "display": 1}]})
        self.assertEqual(ProfileCatalog.from_dict({"schema_version": 1, "profiles": [atlas_one_position]})
                         .get("B518", "DFU").mapping, ((20, 1),))

        for platform, project, paths in (
                ("b482", "B482", {"final": "/tmp/b482"}),
                ("rswmt", "B518", {"final": "/tmp/rswmt"})):
            record = {"project": project, "machine": "BT", "platform": platform,
                      "capacity": 1, "paths": paths,
                      "mapping": [{"source": 4, "display": 1}],
                      "timeouts": {"start": 30, "test": 240, "round": 7200}}
            catalog = ProfileCatalog.from_dict({"schema_version": 1, "profiles": [record]})
            self.assertEqual(catalog.get(project, "BT").mapping, ((4, 1),))

        for platform, project, paths in (
                ("b482", "B482", {"final": "/tmp/b482"}),
                ("rswmt", "B518", {"final": "/tmp/rswmt"})):
            record = {"project": project, "machine": "BT", "platform": platform,
                      "capacity": 5, "paths": paths,
                      "mapping": [{"source": source, "display": source} for source in range(1, 6)],
                      "timeouts": {"start": 30, "test": 240, "round": 7200}}
            with self.subTest(platform=platform), self.assertRaises(ProfileError):
                ProfileCatalog.from_dict({"schema_version": 1, "profiles": [record]})

    def test_versioned_profile_round_trip_preserves_project_machine_and_mapping(self):
        catalog = ProfileCatalog.from_dict({"schema_version": 1, "profiles": [valid_profile()]})

        restored = ProfileCatalog.from_dict(catalog.to_dict()).get("B518", "DFU")

        self.assertEqual(restored.platform, "atlas")
        self.assertEqual(restored.capacity, 2)
        self.assertEqual(restored.mapping, ((1, 2), (2, 1)))

    def test_profile_document_json_round_trip_preserves_equivalent_catalog(self):
        catalog = ProfileCatalog.from_dict({"schema_version": 1, "profiles": [valid_profile()]})

        restored = ProfileCatalog.from_json(catalog.to_json())

        self.assertEqual(restored.to_dict(), catalog.to_dict())

    def test_profile_document_json_rejects_invalid_text_without_path_checks(self):
        payload = {"schema_version": 1, "profiles": [valid_profile()]}
        payload["profiles"][0]["paths"]["active"] = "/path/not/on-this-computer"

        restored = ProfileCatalog.from_json(json.dumps(payload))

        self.assertEqual(restored.get("B518", "DFU").paths["active"], "/path/not/on-this-computer")
        with self.assertRaisesRegex(ProfileError, "JSON"):
            ProfileCatalog.from_json("{")

    def test_invalid_profile_matrix_is_rejected(self):
        cases = []
        unknown_platform = valid_profile()
        unknown_platform["platform"] = "mystery"
        cases.append(unknown_platform)
        missing = valid_profile()
        del missing["capacity"]
        cases.append(missing)
        for capacity in (0, 21, True, 2.5):
            invalid = valid_profile()
            invalid["capacity"] = capacity
            cases.append(invalid)
        duplicate_source = valid_profile()
        duplicate_source["mapping"][1]["source"] = 1
        cases.append(duplicate_source)
        duplicate_display = valid_profile()
        duplicate_display["mapping"][1]["display"] = 2
        cases.append(duplicate_display)
        out_of_range_source = valid_profile()
        out_of_range_source["mapping"][1]["source"] = 21
        cases.append(out_of_range_source)
        out_of_range = valid_profile()
        out_of_range["mapping"][1]["display"] = 3
        cases.append(out_of_range)
        for timeout in (0, -1, True, 1.5, "5"):
            invalid = valid_profile()
            invalid["timeouts"]["test"] = timeout
            cases.append(invalid)

        for profile in cases:
            with self.subTest(profile=profile), self.assertRaises(ProfileError):
                ProfileCatalog.from_dict({"schema_version": 1, "profiles": [profile]})

    def test_unknown_schema_and_incompatible_platform_machine_pair_are_rejected(self):
        with self.assertRaises(ProfileError):
            ProfileCatalog.from_dict({"schema_version": 2, "profiles": [valid_profile()]})
        incompatible = valid_profile()
        incompatible["machine"] = "BT"
        with self.assertRaises(ProfileError):
            ProfileCatalog.from_dict({"schema_version": 1, "profiles": [incompatible]})

    def test_duplicate_project_and_machine_profiles_are_rejected(self):
        record = valid_profile()
        with self.assertRaisesRegex(ProfileError, "重複"):
            ProfileCatalog.from_dict({"schema_version": 1, "profiles": [record, record]})

    def test_legacy_preferences_migrate_to_a_profile_and_restore_selection(self):
        catalog, project, machine = migrate_legacy_preferences({
            "station": "BT",
            "bt_format": "B518 RS-WMT",
            "paths": {"BT": {"final": "/tmp/output", "caseinfo": "/tmp/progress"}},
            "timeouts": {"BT": {"start": "240", "test": "480"}},
        })

        profile = catalog.get(project, machine)
        self.assertEqual((project, machine), ("B518", "BT"))
        self.assertEqual(profile.platform, "rswmt")
        self.assertEqual(profile.paths["final"], "/tmp/output")
        self.assertEqual(profile.timeouts["round"], 7200)

    def test_store_migrates_legacy_preferences_and_restores_saved_selection(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "preferences.json"
            path.write_text(json.dumps({
                "station": "BT", "bt_format": "B518 RS-WMT",
                "paths": {"BT": {"final": "/tmp/rswmt"}},
                "timeouts": {"BT": {"start": 240, "test": 480}},
            }), encoding="utf-8")
            store = MachineProfileStore(path)

            catalog, project, machine, error = store.load()

            self.assertIsNone(error)
            self.assertEqual((project, machine), ("B518", "BT"))
            self.assertEqual(store.retention_days, 365)
            self.assertTrue(store.migration_required)
            store.save(catalog, project, machine, preserve_legacy=store.migration_required)
            self.assertTrue((path.parent / "preferences.legacy.json").is_file())
            restarted_store = MachineProfileStore(path)
            restarted = restarted_store.load()
            self.assertEqual((restarted[1], restarted[2]), ("B518", "BT"))
            self.assertEqual(restarted[0].get("B518", "BT").paths["final"], "/tmp/rswmt")
            self.assertEqual(restarted_store.retention_days, 365)

    def test_malformed_legacy_profile_returns_error_and_preserves_original_file(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "preferences.json"
            original = json.dumps({
                "station": "DFU", "paths": {"DFU": {"active": None, "final": "/tmp/final"}},
            })
            path.write_text(original, encoding="utf-8")

            catalog, project, machine, error = MachineProfileStore(path).load()

            self.assertIn("遷移失敗", error)
            self.assertEqual((project, machine), ("B518", "FCT"))
            self.assertTrue(catalog.profiles)
            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_store_rejects_unknown_schema_without_overwriting_preferences(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "preferences.json"
            original = '{"schema_version": 42, "important": "keep"}'
            path.write_text(original, encoding="utf-8")

            _catalog, _project, _machine, error = MachineProfileStore(path).load()

            self.assertIn("不支援的偏好版本", error)
            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_import_document_replaces_catalog_only_after_validated_save(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "preferences.json"
            original_catalog, _project, _machine = migrate_legacy_preferences({})
            store = MachineProfileStore(path)
            store.save(original_catalog, "B518", "FCT")
            original = path.read_text(encoding="utf-8")
            imported = ProfileCatalog.from_dict({"schema_version": 1, "profiles": [valid_profile()]})

            with self.assertRaisesRegex(ProfileError, "JSON"):
                store.import_document("{", "B518", "DFU")
            self.assertEqual(path.read_text(encoding="utf-8"), original)

            restored, project, machine = store.import_document(imported.to_json(), "B518", "FCT")

            self.assertEqual((project, machine), ("B518", "DFU"))
            self.assertEqual(restored.to_dict(), imported.to_dict())
            persisted = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(persisted["project"], "B518")
            self.assertEqual(persisted["machine"], "DFU")

    def test_import_save_failure_keeps_existing_preference_file(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "preferences.json"
            store = MachineProfileStore(path)
            original_catalog, _project, _machine = migrate_legacy_preferences({})
            store.save(original_catalog, "B518", "FCT")
            original = path.read_text(encoding="utf-8")
            imported = ProfileCatalog.from_dict({"schema_version": 1, "profiles": [valid_profile()]})

            with patch("machine_profiles.os.replace", side_effect=OSError("disk full")):
                with self.assertRaisesRegex(OSError, "disk full"):
                    store.import_document(imported.to_json(), "B518", "DFU")

            self.assertEqual(path.read_text(encoding="utf-8"), original)

    def test_engineer_fields_build_a_profile_and_validate_required_paths(self):
        profile = profile_from_editor_fields(
            "Demo", "DFU", "atlas", "2",
            {"active": "/deployed/active", "final": "/deployed/final", "caseinfo": ""},
            "1:2, 2:1", {"start": "30", "test": "480", "round": "7200"},
        )

        self.assertEqual(profile.key, ("Demo", "DFU"))
        self.assertEqual(profile.mapping, ((1, 2), (2, 1)))
        self.assertEqual(profile.paths["active"], "/deployed/active")
        with self.assertRaisesRegex(ProfileError, "容量"):
            profile_from_editor_fields(
                "Demo", "DFU", "atlas", "2.0", {"active": "", "final": ""}, "1:1,2:2",
                {"start": "30", "test": "480", "round": "7200"},
            )
        with self.assertRaisesRegex(ProfileError, "mapping"):
            profile_from_editor_fields(
                "Demo", "DFU", "atlas", "2", {"active": "/a", "final": "/b"}, "1:1,2:oops",
                {"start": "30", "test": "480", "round": "7200"},
            )
        with self.assertRaisesRegex(ProfileError, "路徑"):
            profile_from_editor_fields(
                "Demo", "DFU", "atlas", "2", {"final": "/b"}, "1:1,2:2",
                {"start": "30", "test": "480", "round": "7200"},
            )


if __name__ == "__main__":
    unittest.main()
