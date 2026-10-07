"""Persistent, verifiable archive evidence for one fully saved monitoring round."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

from audit_records import AuditRecordError, read_round_audit


ARCHIVE_SCHEMA_VERSION = 1
_REQUIRED_SESSION_FILES = ("session.json", "events.log", "results.csv")


@dataclass(frozen=True)
class ArchiveComponent:
    name: str
    path: Path
    size: int
    sha256: str


@dataclass(frozen=True)
class ArchiveLocation:
    audit_path: Path
    session_path: Path
    station: str


@dataclass(frozen=True)
class ArchiveSnapshot:
    round_id: str
    status: str
    archived_at: str = ""
    message: str = ""
    path: Optional[Path] = None
    components: Tuple[ArchiveComponent, ...] = ()
    save_state: str = "waiting"
    station: str = ""

    @property
    def cleanup_eligible(self) -> bool:
        return self.status == "archived"


def _aware_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("封存時間必須包含時區")
    return value.isoformat(timespec="seconds")


def normalize_archive_time(value: datetime) -> datetime:
    """Attach the local timezone to a naive injected wall-clock value."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value.astimezone()
    return value


def _component(path: Path) -> ArchiveComponent:
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError("必要輪次紀錄不存在：{}".format(path.name))
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            digest.update(chunk)
    return ArchiveComponent(path.name, path, size, digest.hexdigest())


def _validate_round_components(audit_path: Path, session_path: Path):
    audit_path = Path(audit_path).resolve()
    session_path = Path(session_path).resolve()
    try:
        audit = read_round_audit(audit_path)
    except (AuditRecordError, OSError, ValueError) as error:
        raise ValueError("audit 無法驗證：{}".format(error))
    round_id = audit["round"]["round_id"]
    if not audit["audit_complete"]:
        raise ValueError("audit 尚未完整保存")
    if not audit["collection_stopped"]:
        raise ValueError("輪次仍在收集，不能封存")
    for event in audit["events"]:
        detail = event.get("detail", {})
        if event["kind"] in {"conflict_detected", "conflict_resolved"}:
            if not isinstance(detail.get("conflict_id"), str) or not detail["conflict_id"]:
                raise ValueError("衝突事件缺少可驗證的身分")
        if event["kind"] in {"round_alarm_created", "round_alarm_acknowledged"}:
            if not isinstance(detail.get("alarm_id"), str) or not detail["alarm_id"]:
                raise ValueError("警報事件缺少可驗證的身分")
    if any(conflict.get("resolution") is None for conflict in audit["conflicts"].values()):
        raise ValueError("仍有未處理衝突")
    if any("created" not in alarm for alarm in audit["alarms"].values()):
        raise ValueError("警報缺少建立事件")
    if any("acknowledged" not in alarm for alarm in audit["alarms"].values()):
        raise ValueError("仍有未確認警報")

    session_file = session_path / "session.json"
    try:
        metadata = json.loads(session_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Session metadata 無法驗證：{}".format(error))
    if (not isinstance(metadata, dict) or metadata.get("schema_version") != 1 or
            not isinstance(metadata.get("settings"), dict) or
            metadata["settings"].get("round_id") != round_id):
        raise ValueError("Session metadata 缺少相同輪次身分或格式不支援")
    if (not isinstance(metadata.get("started_at"), str) or not metadata["started_at"].strip() or
            not isinstance(metadata.get("finished_at"), str) or not metadata["finished_at"].strip()):
        raise ValueError("Session 缺少有效的開始或完成時間")
    if (not isinstance(metadata.get("sources"), list) or
            any(not isinstance(source, str) or not source.strip() for source in metadata["sources"])):
        raise ValueError("Session 來源 metadata 不完整")

    events_path = session_path / "events.log"
    try:
        text = events_path.read_text(encoding="utf-8")
        for line in text.splitlines():
            record = json.loads(line)
            if (not isinstance(record, dict) or not isinstance(record.get("timestamp"), str) or
                    not record["timestamp"].strip() or not isinstance(record.get("message"), str) or
                    not isinstance(record.get("detail", {}), dict)):
                raise ValueError("Session event 欄位不完整")
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Session events 無法驗證：{}".format(error))

    results_path = session_path / "results.csv"
    try:
        with results_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != ["slot", "sn", "status", "source", "updated_at"]:
                raise ValueError("Session results 欄位不完整")
            for row in reader:
                slot = int(row["slot"])
                if (slot < 1 or any(row[key] is None for key in reader.fieldnames) or
                        not row["status"].strip() or not row["updated_at"].strip()):
                    raise ValueError("Session result 欄位不完整")
    except (OSError, UnicodeError, csv.Error) as error:
        raise ValueError("Session results 無法驗證：{}".format(error))

    components = (_component(audit_path),) + tuple(
        _component(session_path / name) for name in _REQUIRED_SESSION_FILES)
    return round_id, components


def _manifest_payload(round_id: str, archived_at: str,
                      components: Tuple[ArchiveComponent, ...]):
    return {
        "record_type": "round_archive",
        "schema_version": ARCHIVE_SCHEMA_VERSION,
        "round_id": round_id,
        "archived_at": archived_at,
        "integrity": "sha256-and-size",
        "components": [
            {"name": item.name, "path": str(item.path), "size": item.size,
             "sha256": item.sha256}
            for item in components
        ],
    }


def _manifest_digest(payload: dict) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def write_round_archive(audit_path: Path, session_path: Path,
                        archived_at: datetime,
                        expected_round_id: Optional[str] = None) -> ArchiveSnapshot:
    """Validate all durable round parts, then atomically write and reread the seal."""
    timestamp = _aware_timestamp(archived_at)
    round_id, components = _validate_round_components(audit_path, session_path)
    if expected_round_id is not None and round_id != expected_round_id:
        raise ValueError("封存輪次身分不一致")
    manifest_path = Path(audit_path).resolve().parent / "round-archive.json"
    previous = read_round_archive(manifest_path, expected_round_id=round_id)
    if (previous.cleanup_eligible and
            previous.components == tuple(sorted(components, key=lambda item: item.name))):
        return previous
    payload = _manifest_payload(round_id, timestamp, components)
    payload["seal_sha256"] = _manifest_digest(payload)
    encoded = (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=".round-archive-", dir=str(manifest_path.parent))
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, str(manifest_path))
        try:
            directory_fd = os.open(str(manifest_path.parent), os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            pass
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    snapshot = read_round_archive(manifest_path, expected_round_id=round_id)
    if not snapshot.cleanup_eligible:
        raise ValueError("封存資訊寫入後驗證失敗：{}".format(snapshot.message))
    return snapshot


def read_round_archive(path: Path, expected_round_id: Optional[str] = None) -> ArchiveSnapshot:
    """Verify archive metadata and every bound file using only fresh disk reads."""
    path = Path(path)
    round_id = expected_round_id or ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        return ArchiveSnapshot(round_id, "protected", message="封存資訊無法讀取：{}".format(error), path=path)
    if not isinstance(payload, dict):
        return ArchiveSnapshot(round_id, "protected", message="封存資訊格式不正確", path=path)
    candidate_id = payload.get("round_id")
    if isinstance(candidate_id, str):
        round_id = candidate_id
    if payload.get("record_type") != "round_archive" or payload.get("schema_version") != ARCHIVE_SCHEMA_VERSION:
        return ArchiveSnapshot(round_id, "protected", message="封存資訊版本未知", path=path)
    seal_digest = payload.get("seal_sha256")
    unsigned_payload = dict(payload)
    unsigned_payload.pop("seal_sha256", None)
    if not isinstance(seal_digest, str) or seal_digest != _manifest_digest(unsigned_payload):
        return ArchiveSnapshot(round_id, "protected", message="封存資訊完整性驗證失敗", path=path)
    if (not round_id or (expected_round_id is not None and round_id != expected_round_id)):
        return ArchiveSnapshot(round_id, "protected", message="封存輪次身分不一致", path=path)
    archived_at = payload.get("archived_at")
    try:
        parsed_time = datetime.fromisoformat(archived_at) if isinstance(archived_at, str) else None
    except ValueError:
        parsed_time = None
    if parsed_time is None or parsed_time.tzinfo is None or parsed_time.utcoffset() is None:
        return ArchiveSnapshot(round_id, "protected", message="封存時間無效或缺少時區", path=path)
    entries = payload.get("components")
    if payload.get("integrity") != "sha256-and-size" or not isinstance(entries, list):
        return ArchiveSnapshot(round_id, "protected", archived_at, "封存完整性資訊缺失", path)
    expected_names = {"audit.jsonl", *_REQUIRED_SESSION_FILES}
    if len(entries) != len(expected_names) or {item.get("name") for item in entries
                                                if isinstance(item, dict)} != expected_names:
        return ArchiveSnapshot(round_id, "protected", archived_at, "封存組成資料不完整", path)
    components = []
    for entry in entries:
        if not isinstance(entry, dict):
            return ArchiveSnapshot(round_id, "protected", archived_at, "封存組成資料格式不正確", path)
        try:
            component_path = Path(entry.get("path", ""))
        except (TypeError, ValueError):
            return ArchiveSnapshot(round_id, "protected", archived_at,
                                   "封存組成資料路徑不正確", path)
        try:
            actual = _component(component_path)
        except (OSError, ValueError) as error:
            return ArchiveSnapshot(round_id, "protected", archived_at,
                                   "必要輪次紀錄缺失或無法讀取：{}".format(error), path)
        if (not isinstance(entry.get("size"), int) or isinstance(entry.get("size"), bool) or
                entry.get("size") != actual.size or entry.get("sha256") != actual.sha256 or
                component_path.name != entry.get("name")):
            return ArchiveSnapshot(round_id, "protected", archived_at,
                                   "必要輪次紀錄內容已變更", path)
        components.append(actual)
    audit_components = [item for item in components if item.name == "audit.jsonl"]
    session_meta = [item for item in components if item.name == "session.json"]
    try:
        verified_round_id, verified_components = _validate_round_components(
            audit_components[0].path, session_meta[0].path.parent)
    except (AuditRecordError, OSError, UnicodeError, json.JSONDecodeError, IndexError,
            TypeError, ValueError) as error:
        return ArchiveSnapshot(round_id, "protected", archived_at,
                               "必要輪次紀錄無法重建：{}".format(error), path)
    if (verified_round_id != round_id or
            tuple(sorted(verified_components, key=lambda item: item.name)) !=
            tuple(sorted(components, key=lambda item: item.name))):
        return ArchiveSnapshot(round_id, "protected", archived_at,
                               "磁碟紀錄未完整保存或輪次身分不一致", path)
    return ArchiveSnapshot(round_id, "archived", archived_at, path=path,
                           components=tuple(sorted(components, key=lambda item: item.name)))
