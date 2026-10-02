"""Versioned engineer profiles selected by operators using project and machine."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import tempfile
from typing import Dict, Iterable, Mapping, Tuple


PROFILE_SCHEMA_VERSION = 1
SUPPORTED_MACHINES = ("DFU", "FCT", "BT")
SUPPORTED_PLATFORMS = ("atlas", "b482", "rswmt")
MAX_CAPACITY = 20
TIMEOUT_FIELDS = ("start", "test", "round")


class ProfileError(ValueError):
    """A profile cannot be loaded or used safely."""


@dataclass(frozen=True)
class MachineProfile:
    project: str
    machine: str
    platform: str
    capacity: int
    paths: Mapping[str, str]
    mapping: Tuple[Tuple[int, int], ...]
    timeouts: Mapping[str, int]

    @property
    def key(self) -> Tuple[str, str]:
        return self.project, self.machine

    def to_dict(self) -> dict:
        return {
            "project": self.project,
            "machine": self.machine,
            "platform": self.platform,
            "capacity": self.capacity,
            "paths": dict(self.paths),
            "mapping": [{"source": source, "display": display}
                        for source, display in self.mapping],
            "timeouts": dict(self.timeouts),
        }


class ProfileCatalog:
    """Validated profile collection with a stable, versioned JSON contract."""

    def __init__(self, profiles: Iterable[MachineProfile]):
        self._profiles = {}
        for profile in profiles:
            validate_profile(profile)
            if profile.key in self._profiles:
                raise ProfileError("專案與機型組合重複：{} / {}。".format(*profile.key))
            self._profiles[profile.key] = profile
        if not self._profiles:
            raise ProfileError("至少需要一個專案與機型配置。")

    def get(self, project: str, machine: str) -> MachineProfile:
        try:
            return self._profiles[(project, machine)]
        except KeyError:
            raise ProfileError("找不到配置：{} / {}。".format(project, machine))

    def for_project(self, project: str) -> Tuple[MachineProfile, ...]:
        return tuple(profile for key, profile in self._profiles.items() if key[0] == project)

    @property
    def projects(self) -> Tuple[str, ...]:
        return tuple(dict.fromkeys(key[0] for key in self._profiles))

    @property
    def profiles(self) -> Tuple[MachineProfile, ...]:
        return tuple(self._profiles.values())

    def with_profile(self, profile: MachineProfile) -> "ProfileCatalog":
        profiles = [item for item in self._profiles.values() if item.key != profile.key]
        profiles.append(profile)
        return ProfileCatalog(profiles)

    def to_dict(self) -> dict:
        return {"schema_version": PROFILE_SCHEMA_VERSION,
                "profiles": [profile.to_dict() for profile in self._profiles.values()]}

    def to_json(self) -> str:
        """Serialize a portable profile document without checking local paths."""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n"

    @classmethod
    def from_json(cls, document: str) -> "ProfileCatalog":
        """Parse and structurally validate a portable profile document."""
        try:
            payload = json.loads(document)
        except (TypeError, json.JSONDecodeError) as error:
            raise ProfileError("配置 JSON 格式錯誤：{}".format(error))
        return cls.from_dict(payload)

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "ProfileCatalog":
        if not isinstance(payload, Mapping):
            raise ProfileError("配置檔必須是 JSON 物件。")
        version = payload.get("schema_version")
        if type(version) is not int or version != PROFILE_SCHEMA_VERSION:
            raise ProfileError("不支援的配置版本：{}。".format(version))
        records = payload.get("profiles")
        if not isinstance(records, list):
            raise ProfileError("配置缺少 profiles 清單。")
        return cls(_profile_from_dict(record) for record in records)


class MachineProfileStore:
    """Read, migrate and atomically persist profile choices in one file."""

    def __init__(self, preferences_path: Path):
        self.path = Path(preferences_path)
        self.migration_required = False

    def load(self):
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ProfileError("偏好檔根節點必須是 JSON 物件。")
        except FileNotFoundError:
            raw = {}
        except (OSError, json.JSONDecodeError, ProfileError) as error:
            catalog, project, machine = migrate_legacy_preferences({})
            return catalog, project, machine, "無法讀取偏好檔：{}".format(error)

        if type(raw.get("schema_version")) is int and raw.get("schema_version") == PROFILE_SCHEMA_VERSION:
            try:
                catalog = ProfileCatalog.from_dict(raw)
                project, machine = raw.get("project"), raw.get("machine")
                try:
                    catalog.get(project, machine)
                    return catalog, project, machine, None
                except ProfileError:
                    fallback = catalog.profiles[0]
                    return catalog, fallback.project, fallback.machine, "已保存的專案與機型選擇已不存在，請重新選擇。"
            except (ProfileError, TypeError) as error:
                catalog, project, machine = migrate_legacy_preferences({})
                return catalog, project, machine, "配置無效：{}".format(error)
        if "schema_version" in raw:
            catalog, project, machine = migrate_legacy_preferences({})
            return catalog, project, machine, "不支援的偏好版本：{}。".format(raw.get("schema_version"))

        try:
            catalog, project, machine = migrate_legacy_preferences(raw)
        except (ProfileError, TypeError, AttributeError) as error:
            catalog, project, machine = migrate_legacy_preferences({})
            self.migration_required = False
            return catalog, project, machine, "舊偏好遷移失敗：{}".format(error)
        self.migration_required = True
        return catalog, project, machine, None

    def save(self, catalog: ProfileCatalog, project: str, machine: str,
             preserve_legacy: bool = False) -> None:
        catalog.get(project, machine)
        payload = catalog.to_dict()
        payload.update({"project": project, "machine": machine})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if preserve_legacy and self.path.exists():
            legacy_path = self.path.with_name("preferences.legacy.json")
            if not legacy_path.exists():
                _atomic_write_text(legacy_path, self.path.read_text(encoding="utf-8"))
        _atomic_write_text(self.path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
        self.migration_required = False

    def import_document(self, document: str, selected_project: str, selected_machine: str):
        """Validate a complete catalog, then atomically replace the saved catalog."""
        catalog = ProfileCatalog.from_json(document)
        try:
            catalog.get(selected_project, selected_machine)
        except ProfileError:
            selected_project, selected_machine = catalog.profiles[0].key
        self.save(catalog, selected_project, selected_machine)
        return catalog, selected_project, selected_machine


def _atomic_write_text(path: Path, text: str) -> None:
    """Replace one text file atomically and remove a temporary file on failure."""
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent),
                                         prefix=path.name + ".", suffix=".tmp", delete=False) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(text)
        os.replace(str(temporary_path), str(path))
    except OSError:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except OSError:
                pass
        raise

def _profile_from_dict(record: object) -> MachineProfile:
    if not isinstance(record, Mapping):
        raise ProfileError("每筆配置必須是 JSON 物件。")
    required = ("project", "machine", "platform", "capacity", "paths", "mapping", "timeouts")
    missing = [field for field in required if field not in record]
    if missing:
        raise ProfileError("配置缺少必要欄位：{}。".format(", ".join(missing)))
    raw_mapping = record["mapping"]
    if not isinstance(raw_mapping, list):
        raise ProfileError("mapping 必須是清單。")
    pairs = []
    for item in raw_mapping:
        if not isinstance(item, Mapping) or "source" not in item or "display" not in item:
            raise ProfileError("每筆 mapping 必須包含 source 與 display。")
        pairs.append((item["source"], item["display"]))
    paths = record["paths"]
    timeouts = record["timeouts"]
    if not isinstance(paths, Mapping) or not isinstance(timeouts, Mapping):
        raise ProfileError("paths 與 timeouts 必須是 JSON 物件。")
    profile = MachineProfile(
        project=record["project"], machine=record["machine"], platform=record["platform"],
        capacity=record["capacity"], paths=dict(paths), mapping=tuple(pairs), timeouts=dict(timeouts),
    )
    validate_profile(profile)
    return profile


def validate_profile(profile: MachineProfile) -> None:
    if not isinstance(profile.project, str) or not profile.project.strip():
        raise ProfileError("project 不可空白。")
    if profile.machine not in SUPPORTED_MACHINES:
        raise ProfileError("未知機型：{}。".format(profile.machine))
    if profile.platform not in SUPPORTED_PLATFORMS:
        raise ProfileError("未知平台：{}。".format(profile.platform))
    if profile.platform == "atlas" and profile.machine not in {"DFU", "FCT"}:
        raise ProfileError("Atlas 僅支援 DFU／FCT 機型。")
    if profile.platform in {"b482", "rswmt"} and profile.machine != "BT":
        raise ProfileError("{} 平台僅支援 BT 機型。".format(profile.platform))
    if type(profile.capacity) is not int or not 1 <= profile.capacity <= MAX_CAPACITY:
        raise ProfileError("capacity 必須是 1 至 {} 的整數。".format(MAX_CAPACITY))
    required_paths = {"atlas": {"active", "final"}, "b482": {"final"},
                      "rswmt": {"final"}}[profile.platform]
    if not isinstance(profile.paths, Mapping) or not required_paths.issubset(profile.paths):
        raise ProfileError("paths 缺少平台必要路徑：{}。".format(", ".join(sorted(required_paths))))
    if any(not isinstance(value, str) for value in profile.paths.values()):
        raise ProfileError("所有路徑都必須是文字。")
    if not isinstance(profile.mapping, tuple) or len(profile.mapping) != profile.capacity:
        raise ProfileError("mapping 必須為每個容量位置提供一筆對應。")
    sources, displays = [], []
    for pair in profile.mapping:
        if not isinstance(pair, tuple) or len(pair) != 2:
            raise ProfileError("mapping 必須是 source/display 整數組。")
        source, display = pair
        if type(source) is not int or source < 1:
            raise ProfileError("mapping source 必須是正整數。")
        if type(display) is not int or not 1 <= display <= profile.capacity:
            raise ProfileError("mapping display 超出配置容量。")
        sources.append(source)
        displays.append(display)
    if len(set(sources)) != len(sources) or len(set(displays)) != len(displays):
        raise ProfileError("mapping 的來源與顯示位置不可重複。")
    if set(displays) != set(range(1, profile.capacity + 1)):
        raise ProfileError("mapping 必須涵蓋 1 至 capacity 的每個顯示位置。")
    if not isinstance(profile.timeouts, Mapping) or set(TIMEOUT_FIELDS) - set(profile.timeouts):
        raise ProfileError("timeouts 必須包含 start、test 與 round。")
    for name in TIMEOUT_FIELDS:
        value = profile.timeouts[name]
        if type(value) is not int or value <= 0:
            raise ProfileError("{} timeout 必須是正整數秒數。".format(name))


def migrate_legacy_preferences(preferences: Mapping[str, object]) -> Tuple[ProfileCatalog, str, str]:
    """Convert the former station/path preferences to one selected profile."""
    machine = preferences.get("station", "FCT")
    if machine not in SUPPORTED_MACHINES:
        machine = "FCT"
    bt_format = preferences.get("bt_format", "B482 TestData")
    if machine == "BT":
        platform = "rswmt" if bt_format == "B518 RS-WMT" else "b482"
        project = "B518" if platform == "rswmt" else "B482"
    else:
        platform, project = "atlas", "B518"
    legacy_paths = preferences.get("paths", {})
    legacy_timeouts = preferences.get("timeouts", {})
    profiles = []
    for project_name, machine_name, platform_name in (
        ("B518", "DFU", "atlas"), ("B518", "FCT", "atlas"),
        ("B482", "BT", "b482"), ("B518", "BT", "rswmt"),
    ):
        matches_legacy = machine_name != "BT" or (
            project_name == project and machine_name == machine and platform_name == platform
        )
        paths = legacy_paths.get(machine_name, {}) if matches_legacy and isinstance(legacy_paths, Mapping) else {}
        old_timeouts = legacy_timeouts.get(machine_name, {}) \
            if matches_legacy and isinstance(legacy_timeouts, Mapping) else {}
        defaults = {"start": 240 if platform_name == "rswmt" else 30, "test": 480, "round": 7200}
        timeouts = {}
        for field, default in defaults.items():
            raw = old_timeouts.get(field, default) if isinstance(old_timeouts, Mapping) else default
            try:
                value = int(raw)
            except (TypeError, ValueError):
                value = default
            timeouts[field] = value if value > 0 else default
        profile_paths = {key: value for key, value in paths.items() if key in {"active", "final", "caseinfo"}} \
            if isinstance(paths, Mapping) else {}
        if platform_name == "atlas":
            profile_paths.setdefault("active", "")
            profile_paths.setdefault("final", "")
            capacity = 7 if machine_name == "DFU" else 6
        else:
            profile_paths.setdefault("final", "")
            profile_paths.setdefault("caseinfo", "")
            capacity = 4
        profiles.append(MachineProfile(
            project_name, machine_name, platform_name, capacity, profile_paths,
            tuple((slot, slot) for slot in range(1, capacity + 1)), timeouts,
        ))
    return ProfileCatalog(profiles), project, machine
