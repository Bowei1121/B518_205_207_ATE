"""Safe, resumable cleanup of expired App-managed round archives."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Dict, Iterable, Optional, Tuple

from round_archival import normalize_archive_time, read_round_archive


LEDGER_SCHEMA_VERSION = 2


@dataclass(frozen=True)
class RetentionRoundResult:
    round_id: str
    outcome: str
    reason: str = ""


@dataclass(frozen=True)
class RetentionSummary:
    run_id: str
    started_at: str
    completed_at: str
    retention_days: int
    trigger: str
    status: str
    results: Tuple[RetentionRoundResult, ...] = ()
    message: str = ""

    @property
    def deleted_round_ids(self) -> Tuple[str, ...]:
        return tuple(item.round_id for item in self.results if item.outcome == "deleted")


@dataclass(frozen=True)
class RetentionStatus:
    status: str = "idle"
    message: str = "尚未執行背景清理"
    summaries: Tuple[RetentionSummary, ...] = ()


class RoundRetentionStore:
    """Validate archive ownership and remove only explicitly sealed files."""

    def __init__(self, managed_root: Path, ledger_path: Path,
                 wall_clock: Callable[[], datetime],
                 protected_round_ids: Callable[[], Iterable[str]],
                 cleanup_allowed: Callable[[], bool]):
        requested_root = Path(managed_root).absolute()
        self._root_is_symlink = requested_root.is_symlink()
        self.root = requested_root.resolve()
        self.ledger_path = Path(ledger_path).absolute()
        self._wall_clock = wall_clock
        self._protected_round_ids = protected_round_ids
        self._cleanup_allowed = cleanup_allowed
        self._lock = threading.RLock()
        self._status = RetentionStatus()
        self._summaries = ()
        try:
            ledger = self._load_ledger()
            self._summaries = tuple(_summary_from_dict(item) for item in ledger["runs"])
            if ledger.get("active_plans") or (self._summaries and
                                                self._summaries[-1].status == "running"):
                self._status = RetentionStatus(
                    "failed", "上次背景清理中斷；將依持久進度重新驗證", self._summaries)
        except Exception as error:
            self._status = RetentionStatus(
                "failed", "既有清理摘要或復原進度無法讀取：{}".format(error), self._summaries)

    @property
    def status(self) -> RetentionStatus:
        with self._lock:
            return RetentionStatus(self._status.status, self._status.message, self._summaries)

    @property
    def summaries(self) -> Tuple[RetentionSummary, ...]:
        with self._lock:
            return self._summaries

    def run(self, retention_days: int, trigger: str) -> RetentionStatus:
        if type(retention_days) is not int or retention_days <= 0:
            return self._finish_status("failed", "保存天數無效，未執行清理")
        started = self._wall_clock().astimezone().isoformat(timespec="seconds")
        run_id = str(uuid.uuid4())
        results = []
        summary = RetentionSummary(run_id, started, "", retention_days, trigger, "running")
        with self._lock:
            try:
                ledger = self._load_ledger()
                ledger["runs"].append(_summary_to_dict(summary))
                ledger["runs"] = ledger["runs"][-1000:]
                self._write_ledger(ledger)
                self._status = RetentionStatus("running", "背景清理進行中", self._summaries)
            except Exception as error:
                return self._finish_status("failed", "無法保存清理摘要，未刪除資料：{}".format(error))

        try:
            self._resume_active_plan(results, retention_days)
            candidates, rejected = self._discover()
            results.extend(rejected)
            now = normalize_archive_time(self._wall_clock())
            cutoff = now - timedelta(days=retention_days)
            for round_id, manifests, components in candidates:
                if not self._cleanup_allowed():
                    results.append(RetentionRoundResult(round_id, "skipped", "關閉保存期間暫停清理"))
                    continue
                if round_id in set(self._protected_round_ids()):
                    results.append(RetentionRoundResult(round_id, "skipped", "本次 App 執行仍受保護"))
                    continue
                archive_times = [datetime.fromisoformat(item.archived_at) for item in manifests]
                if any(value.tzinfo is None or value.utcoffset() is None for value in archive_times):
                    results.append(RetentionRoundResult(round_id, "skipped", "可信封存時間缺少時區"))
                    continue
                archived_at = min(archive_times)
                if archived_at > cutoff:
                    results.append(RetentionRoundResult(round_id, "skipped", "尚未到保存期限"))
                    continue
                try:
                    self._delete_round(run_id, round_id, manifests, components, retention_days)
                    results.append(RetentionRoundResult(round_id, "deleted", "已完整刪除可信輪次資料"))
                except Exception as error:
                    results.append(RetentionRoundResult(round_id, "failed", str(error)))
        except Exception as error:
            results.append(RetentionRoundResult("", "failed", str(error)))

        completed = self._wall_clock().astimezone().isoformat(timespec="seconds")
        status = "failed" if any(item.outcome == "failed" for item in results) else "complete"
        message = "清理完成：刪除 {} 輪、保留 {} 輪、失敗 {} 輪".format(
            sum(item.outcome == "deleted" for item in results),
            sum(item.outcome == "skipped" for item in results),
            sum(item.outcome == "failed" for item in results))
        final = RetentionSummary(run_id, started, completed, retention_days, trigger,
                                 status, tuple(results), message)
        with self._lock:
            try:
                ledger = self._load_ledger()
                ledger["runs"] = [item for item in ledger["runs"] if item.get("run_id") != run_id]
                ledger["runs"].append(_summary_to_dict(final))
                ledger["runs"] = ledger["runs"][-1000:]
                self._write_ledger(ledger)
                self._summaries = tuple((_summary_from_dict(item) for item in ledger["runs"]))
                self._status = RetentionStatus(status, message, self._summaries)
            except Exception as error:
                return self._finish_status("failed", "清理結果摘要保存失敗：{}；請檢查清理進度".format(error))
        return self.status

    def _discover(self):
        if not self.root.exists():
            return [], []
        if self._root_is_symlink or not self._safe_directory(self.root):
            raise ValueError("輪次資料根目錄不是安全的 App 管理目錄")
        groups: Dict[str, list] = {}
        rejected = []
        for current, dirs, files in os.walk(str(self.root), followlinks=False):
            base = Path(current)
            dirs[:] = [name for name in dirs if not (base / name).is_symlink()]
            for name in files:
                if name != "round-archive.json":
                    continue
                manifest = base / name
                if not self._safe_file(manifest):
                    rejected.append(RetentionRoundResult("", "skipped", "封存檔路徑含符號連結或越界"))
                    continue
                snapshot = read_round_archive(manifest)
                if snapshot.status != "archived":
                    rejected.append(RetentionRoundResult(snapshot.round_id, "skipped",
                                                          snapshot.message or "封存證據無效"))
                    continue
                try:
                    payload = json.loads(manifest.read_text(encoding="utf-8"))
                    raw_paths = tuple(Path(entry["path"]) for entry in payload["components"])
                    if any(not self._safe_file(path) for path in raw_paths):
                        raise ValueError("必要資料路徑含符號連結或不在 App 管理範圍")
                    expected_by_name = {component.name: component.path for component in snapshot.components}
                    if any(path.resolve() != expected_by_name.get(path.name) for path in raw_paths):
                        raise ValueError("封存路徑與驗證後路徑不一致")
                    if not self._only_known_files(manifest, raw_paths):
                        raise ValueError("輪次目錄含未知檔案，整輪保留")
                    record = (snapshot, manifest, raw_paths)
                    groups.setdefault(snapshot.round_id, []).append(record)
                except (OSError, ValueError, KeyError, TypeError) as error:
                    rejected.append(RetentionRoundResult(snapshot.round_id, "skipped", str(error)))

        candidates = []
        blocked_round_ids = {item.round_id for item in rejected if item.round_id}
        for round_id, records in groups.items():
            if round_id in blocked_round_ids:
                continue
            manifests = [item[0] for item in records]
            components = {}
            for _snapshot, _manifest, paths in records:
                for path in paths:
                    components[str(path)] = path
            manifests_paths = [item[1] for item in records]
            candidates.append((round_id, manifests, tuple(Path(path) for path in
                                                           sorted(set(manifests_paths + list(components.values()))))))
        return candidates, rejected

    def _delete_round(self, run_id, round_id, snapshots, planned_paths, retention_days):
        if round_id in set(self._protected_round_ids()) or not self._cleanup_allowed():
            raise ValueError("刪除前輪次保護狀態已變更")
        fresh = [read_round_archive(item.path, expected_round_id=round_id) for item in snapshots]
        if any(item.status != "archived" for item in fresh):
            raise ValueError("刪除前完整性重新驗證失敗")
        current = normalize_archive_time(self._wall_clock())
        for item in fresh:
            archived = datetime.fromisoformat(item.archived_at)
            if archived + timedelta(days=retention_days) > current:
                raise ValueError("刪除前保存期限重新判定為未到期")
        expected = {}
        for item in fresh:
            expected[str(item.path)] = _file_record(item.path)
            for component in item.components:
                expected[str(component.path)] = _file_record(component.path)
        paths = tuple(sorted(expected, key=lambda value: (value.endswith("round-archive.json"), value)))
        ledger = self._load_ledger()
        ledger.setdefault("active_plans", {})[round_id] = {
            "run_id": run_id, "round_id": round_id,
            "retention_days": retention_days, "paths": expected,
            "path_order": list(paths), "next_index": 0,
            "archived_at": min(item.archived_at for item in fresh)}
        self._write_ledger(ledger)
        for index, raw_path in enumerate(paths):
            if not self._cleanup_allowed():
                raise ValueError("關閉保存開始，刪除進度已保留供復原")
            path = Path(raw_path)
            record = expected[raw_path]
            ledger = self._load_ledger()
            ledger["active_plans"][round_id]["next_index"] = index
            self._write_ledger(ledger)
            self._unlink_managed_file(path, record)
            ledger = self._load_ledger()
            ledger["active_plans"][round_id]["next_index"] = index + 1
            self._write_ledger(ledger)
        ledger = self._load_ledger()
        ledger["active_plans"].pop(round_id, None)
        self._write_ledger(ledger)
        self._remove_empty_managed_directories(paths)

    def _resume_active_plan(self, results, retention_days: int) -> None:
        """Continue an interrupted whole-round delete from its durable intent."""
        ledger = self._load_ledger()
        plans = tuple(ledger.get("active_plans", {}).items())
        for round_id, plan in plans:
            ledger = self._load_ledger()
            plan = ledger.get("active_plans", {}).get(round_id)
            if plan is None:
                continue
            if round_id in set(self._protected_round_ids()) or not self._cleanup_allowed():
                results.append(RetentionRoundResult(round_id, "skipped", "中斷清理輪次目前仍受保護"))
                continue
            try:
                archived_at = datetime.fromisoformat(plan["archived_at"])
                current = normalize_archive_time(self._wall_clock())
                if (archived_at.tzinfo is None or archived_at.utcoffset() is None or
                        archived_at + timedelta(days=retention_days) > current):
                    raise ValueError("目前保存期限不再允許繼續中斷的刪除計畫")
                paths = plan["path_order"]
                expected = plan["paths"]
                next_index = plan["next_index"]
                if (not isinstance(paths, list) or not isinstance(expected, dict) or
                        not isinstance(next_index, int) or not 0 <= next_index <= len(paths) or
                        set(paths) != set(expected) or
                        any(Path(raw_path).name not in {
                            "audit.jsonl", "session.json", "events.log", "results.csv",
                            "round-archive.json"} for raw_path in paths)):
                    raise ValueError("持久刪除計畫格式或輪次組件不可信")
                self._validate_resume_directories(paths, next_index)
                for index, raw_path in enumerate(paths):
                    path = Path(raw_path)
                    if not self._safe_target(path):
                        raise ValueError("復原計畫路徑已越界或含符號連結：{}（管理根目錄 {}）".format(
                            path, self.root))
                    current_record = self._managed_file_record(path)
                    if current_record is not None:
                        if current_record != expected[raw_path]:
                            raise ValueError("復原計畫中的剩餘檔案內容已變更")
                        if index < next_index:
                            raise ValueError("已完成的刪除步驟意外重新出現")
                        if index > next_index:
                            raise ValueError("中斷進度與剩餘檔案不一致")
                        plan["next_index"] = index
                        ledger["active_plans"][round_id] = plan
                        self._write_ledger(ledger)
                        self._unlink_managed_file(path, expected[raw_path])
                        plan["next_index"] = index + 1
                        next_index = index + 1
                        ledger["active_plans"][round_id] = plan
                        self._write_ledger(ledger)
                    elif index > next_index:
                        raise ValueError("尚未執行的刪除步驟已缺少資料，停止復原")
                    elif index == next_index:
                        # The durable intent was written immediately before unlink.
                        # A crash may have occurred after unlink and before progress update.
                        plan["next_index"] = index + 1
                        next_index = index + 1
                        ledger["active_plans"][round_id] = plan
                        self._write_ledger(ledger)
                ledger["active_plans"].pop(round_id, None)
                self._write_ledger(ledger)
                self._remove_empty_managed_directories(paths)
                results.append(RetentionRoundResult(round_id, "deleted", "依持久刪除計畫完成中斷復原"))
            except Exception as error:
                results.append(RetentionRoundResult(round_id, "failed", "中斷刪除復原失敗：{}".format(error)))

    def _validate_resume_directories(self, paths, next_index: int) -> None:
        """Reject new or unknown files before resuming an interrupted round delete."""
        remaining = {}
        for raw_path in paths[next_index:]:
            path = Path(raw_path)
            remaining.setdefault(path.parent, set()).add(path.name)
        for directory in {Path(raw_path).parent for raw_path in paths}:
            if not self._safe_target(directory):
                raise ValueError("復原計畫目錄已越界或含符號連結")
            if not directory.exists():
                continue
            if not directory.is_dir():
                raise ValueError("復原計畫目錄已被非目錄內容取代")
            allowed = remaining.get(directory, set())
            for child in directory.iterdir():
                if child.is_symlink() or child.is_dir() or child.name not in allowed:
                    raise ValueError("復原目錄出現未列入原計畫的新資料：{}".format(child.name))

    def _managed_parent_fd(self, path: Path):
        if os.open not in os.supports_dir_fd:
            raise NotImplementedError("dir_fd unavailable on this platform")
        relative = path.absolute().relative_to(self.root)
        if not relative.parts or self._root_is_symlink:
            raise ValueError("刪除路徑不在安全的 App 管理根目錄")
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(str(self.root), flags)
        try:
            for part in relative.parts[:-1]:
                child = os.open(part, flags, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = child
            return descriptor, relative.parts[-1]
        except Exception:
            os.close(descriptor)
            raise

    def _managed_file_record(self, path: Path):
        if os.open not in os.supports_dir_fd or os.stat not in os.supports_dir_fd:
            if not self._safe_file(path):
                return None
            return _file_record(path)
        descriptor, name = self._managed_parent_fd(path)
        try:
            try:
                before = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            except FileNotFoundError:
                return None
            if not stat.S_ISREG(before.st_mode):
                raise ValueError("清理目標不是一般檔案或已成為符號連結")
            file_descriptor = os.open(name, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
                                      dir_fd=descriptor)
            try:
                opened = os.fstat(file_descriptor)
                if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino):
                    raise ValueError("清理目標在驗證期間被替換")
                digest = hashlib.sha256()
                size = 0
                while True:
                    chunk = os.read(file_descriptor, 1024 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
                    size += len(chunk)
                return {"size": size, "sha256": digest.hexdigest()}
            finally:
                os.close(file_descriptor)
        finally:
            os.close(descriptor)

    def _unlink_managed_file(self, path: Path, expected: dict) -> None:
        actual = self._managed_file_record(path)
        if actual is None:
            return
        if actual != expected:
            raise ValueError("刪除前檔案內容或身分已變更")
        if os.unlink not in os.supports_dir_fd:
            if not self._safe_file(path):
                raise ValueError("刪除目標路徑已變更或包含符號連結")
            path.unlink()
            return
        descriptor, name = self._managed_parent_fd(path)
        try:
            os.unlink(name, dir_fd=descriptor)
        finally:
            os.close(descriptor)

    def _remove_empty_managed_directories(self, paths) -> None:
        directories = {Path(path).parent for path in paths}
        for directory in sorted(directories, key=lambda item: len(item.parts), reverse=True):
            if directory == self.root:
                continue
            if os.rmdir not in os.supports_dir_fd:
                try:
                    if self._safe_target(directory):
                        directory.rmdir()
                except OSError:
                    pass
                continue
            try:
                descriptor, name = self._managed_parent_fd(directory)
                try:
                    os.rmdir(name, dir_fd=descriptor)
                finally:
                    os.close(descriptor)
            except (OSError, ValueError):
                pass

    def _only_known_files(self, manifest: Path, paths: Tuple[Path, ...]) -> bool:
        known_names = {manifest.name} | {item.name for item in paths}
        for directory in {manifest.parent} | {item.parent for item in paths}:
            try:
                children = tuple(directory.iterdir())
            except OSError:
                return False
            if any(child.is_dir() or child.name not in known_names for child in children):
                return False
        return True

    def _safe_directory(self, path: Path) -> bool:
        try:
            if path.is_symlink() or not path.is_dir():
                return False
            return path.resolve().is_relative_to(self.root.resolve()) or path.resolve() == self.root.resolve()
        except (OSError, AttributeError):
            try:
                path.resolve().relative_to(self.root.resolve())
                return True
            except (OSError, ValueError):
                return False

    def _safe_file(self, path: Path) -> bool:
        try:
            absolute = path.absolute()
            absolute.relative_to(self.root)
            cursor = self.root
            relative = absolute.relative_to(self.root)
            for part in relative.parts:
                cursor = cursor / part
                if cursor.is_symlink():
                    return False
            return absolute.is_file() and absolute.resolve().is_relative_to(self.root.resolve())
        except (OSError, ValueError, AttributeError):
            try:
                absolute.resolve().relative_to(self.root.resolve())
                return absolute.is_file() and not absolute.is_symlink()
            except (OSError, ValueError):
                return False

    def _safe_target(self, path: Path) -> bool:
        try:
            absolute = path.absolute()
            relative = absolute.relative_to(self.root)
            cursor = self.root
            for part in relative.parts:
                cursor = cursor / part
                if cursor.is_symlink():
                    return False
            return True
        except (OSError, ValueError):
            return False

    def _finish_status(self, status: str, message: str) -> RetentionStatus:
        with self._lock:
            self._status = RetentionStatus(status, message, self._summaries)
            return self._status

    def _load_ledger(self) -> dict:
        try:
            payload = json.loads(self.ledger_path.read_text(encoding="utf-8"))
            if payload.get("schema_version") not in {1, LEDGER_SCHEMA_VERSION} or not isinstance(
                    payload.get("runs"), list):
                raise ValueError("清理摘要格式未知")
            if payload.get("schema_version") == 1:
                old_plan = payload.pop("active_plan", None)
                payload["schema_version"] = LEDGER_SCHEMA_VERSION
                payload["active_plans"] = ({old_plan["round_id"]: old_plan} if old_plan else {})
            payload.setdefault("active_plans", {})
            if not isinstance(payload["active_plans"], dict):
                raise ValueError("清理復原進度格式錯誤")
            return payload
        except FileNotFoundError:
            return {"schema_version": LEDGER_SCHEMA_VERSION, "runs": [], "active_plans": {}}

    def _write_ledger(self, payload: dict) -> None:
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".round-retention-", dir=str(self.ledger_path.parent))
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, sort_keys=True, indent=2)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, str(self.ledger_path))
            try:
                fd = os.open(str(self.ledger_path.parent), os.O_RDONLY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
            except OSError:
                pass
        except Exception:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise


def _file_record(path: Path) -> dict:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return {"size": size, "sha256": digest.hexdigest()}


def _summary_to_dict(item: RetentionSummary) -> dict:
    return {"run_id": item.run_id, "started_at": item.started_at,
            "completed_at": item.completed_at, "retention_days": item.retention_days,
            "trigger": item.trigger, "status": item.status, "message": item.message,
            "results": [{"round_id": result.round_id, "outcome": result.outcome,
                         "reason": result.reason} for result in item.results]}


def _summary_from_dict(item: dict) -> RetentionSummary:
    return RetentionSummary(item["run_id"], item["started_at"], item.get("completed_at", ""),
                            item["retention_days"], item.get("trigger", "unknown"),
                            item.get("status", "failed"), tuple(
                                RetentionRoundResult(row.get("round_id", ""),
                                                     row.get("outcome", "failed"),
                                                     row.get("reason", ""))
                                for row in item.get("results", [])), item.get("message", ""))
