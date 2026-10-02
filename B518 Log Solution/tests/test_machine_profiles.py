import json
import unittest
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory

from machine_profiles import (
    MachineProfile, MachineProfileStore, ProfileCatalog, ProfileError, migrate_legacy_preferences,
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
            self.assertTrue(store.migration_required)
            store.save(catalog, project, machine, preserve_legacy=store.migration_required)
            self.assertTrue((path.parent / "preferences.legacy.json").is_file())
            restarted = MachineProfileStore(path).load()
            self.assertEqual((restarted[1], restarted[2]), ("B518", "BT"))
            self.assertEqual(restarted[0].get("B518", "BT").paths["final"], "/tmp/rswmt")

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


if __name__ == "__main__":
    unittest.main()
