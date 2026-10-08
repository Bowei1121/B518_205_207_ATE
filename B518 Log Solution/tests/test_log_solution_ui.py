import csv
import io
import json
import os
import queue
import tkinter as tk
import time
import threading
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from tkinter import font as tkfont, ttk
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from b518_log_solution import (
    B518LogSolutionApp, MAIN_FONT_SIZE, ROW_HEIGHT, STATUS_COLOURS, configured_directory,
    STATUS_TEMPLATE_STATES, UNAVAILABLE_COLOUR, WINDOW_WIDTH, KVM_BLOCK_COUNT, kvm_block_colour,
    sn_font_size, visible_detail_rows, window_height,
)
from global_hotkey import COMMAND_SHIFT_M_KEYCODE, COMMAND_SHIFT_MODIFIERS, GlobalHotkeyError, UnavailableHotkey, create_global_hotkey
from log_monitoring import MonitorEvent
from log_monitoring import BaseMonitor, SessionStore, SlotResult
from monitoring_round import (
    ConflictSide, RoundConflict, RoundCoordinator, RoundEvent, RoundSnapshot, RoundState,
)
import audit_records
from audit_records import read_round_audit
from machine_profiles import MachineProfileStore, ProfileCatalog, migrate_legacy_preferences


class FakeHotkey:
    available = True
    message = "available"

    def __init__(self, callback):
        self.callback = callback
        self.closed = False

    def close(self):
        self.closed = True


def install_test_profile(app, station, platform, active=".", final=".", caseinfo=""):
    """Give a lightweight App fixture the same required profile seam as production."""
    project = "B482" if platform == "b482" else "B518"
    with TemporaryDirectory() as temporary:
        defaults, _project, _machine, _error = MachineProfileStore(
            Path(temporary) / "preferences.json",
        ).load()
    profile = defaults.get(project, station)
    profile = replace(profile, platform=platform, paths={
        "active": active, "final": final, "caseinfo": caseinfo,
    })
    app.profiles = defaults.with_profile(profile)
    app.profile_error = None
    app.project = SimpleNamespace(get=lambda: project, set=lambda _value: None)
    app.station = SimpleNamespace(get=lambda: station)
    app.active_profile_snapshot = None
    return profile


def install_snapshot_results(app, results):
    snapshot = SimpleNamespace(
        round_id="round-under-test", results=tuple(results), audit_complete=True,
        audit_errors=(), state=SimpleNamespace(value="RUNNING"),
    )
    app.active_round_id = snapshot.round_id
    app.rounds = MagicMock()
    app.rounds.snapshot.return_value = snapshot
    app._apply_round_snapshot = MagicMock()


def conflict_summary_rows(app):
    lines = app.conflict_comparison.get("1.0", "end-1c").splitlines()
    return [tuple(line.split("\t")[:3]) for line in lines]


class LogSolutionUiTests(unittest.TestCase):
    def wait_for(self, predicate, timeout=3):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.01)
        self.fail("Timed out waiting for asynchronous monitor preparation")

    def test_real_tk_global_retention_setting_validates_persists_and_preserves_round_files(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.withdraw()
            session_root = Path(temporary) / "sessions"
            round_path = session_root / "existing-round" / "session.json"
            round_path.parent.mkdir(parents=True)
            round_path.write_text('{"result": "preserve"}', encoding="utf-8")
            original_round_data = round_path.read_bytes()
            app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey, session_root=session_root)
            try:
                app.open_settings()
                self.assertEqual(app.retention_days_var.get(), "365")
                help_text = app.retention_help_label.cget("text")
                self.assertIn("完整 24 小時", help_text)
                self.assertIn("下一次背景清理", help_text)

                app.retention_days_var.set("730")
                app.retention_save_button.invoke()
                second_value = MachineProfileStore(Path(temporary) / "preferences.json")
                second_value.load()
                self.assertEqual(second_value.retention_days, 730)

                app.retention_days_var.set("180")
                app.retention_save_button.invoke()
                persisted = MachineProfileStore(Path(temporary) / "preferences.json")
                persisted.load()
                self.assertEqual(persisted.retention_days, 180)
                self.assertIn("下一次背景清理", app.retention_status.get())

                valid_preferences = Path(temporary, "preferences.json").read_bytes()
                for invalid in ("", "not-a-number", "0", "-1"):
                    app.retention_days_var.set(invalid)
                    app.retention_save_button.invoke()
                    rejected = MachineProfileStore(Path(temporary) / "preferences.json")
                    rejected.load()
                    self.assertEqual(rejected.retention_days, 180)
                    self.assertEqual(Path(temporary, "preferences.json").read_bytes(), valid_preferences)
                    self.assertIn("正整數", app.retention_status.get())

                app.retention_days_var.set("730")
                with patch.object(app.profile_store, "save_retention_days",
                                  side_effect=OSError("disk full")):
                    app.retention_save_button.invoke()
                failed = MachineProfileStore(Path(temporary) / "preferences.json")
                failed.load()
                self.assertEqual(failed.retention_days, 180)
                self.assertEqual(app.retention_effective_label.cget("text"), "目前生效：180 天")
                self.assertIn("保存失敗", app.retention_status.get())
                self.assertEqual(round_path.read_bytes(), original_round_data)
                self.assertEqual(tuple(session_root.rglob("*")), (round_path.parent, round_path))
            finally:
                app._close_settings()
                app.rounds.request_close()
                self.wait_for(lambda: app.rounds.close_status().status == "complete")
                app.hotkey.close()
                root.destroy()

    @unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1",
                         "requires an accessible macOS Tk desktop session")
    def test_real_tk_shows_startup_cleanup_summary_after_disk_deletion(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            session_root = Path(temporary) / "sessions"
            root = tk.Tk()
            root.withdraw()
            archived_at = datetime.now(timezone.utc) - timedelta(days=200)
            writer = RoundCoordinator(audit_root=session_root, wall_clock=lambda: archived_at)

            class OldRoundMonitor(BaseMonitor):
                def __init__(self, callback):
                    super().__init__("FCT", {}, (1,), callback=callback, session_root=session_root,
                                     now=lambda: archived_at, round_timeout_seconds=3600)
                    self.done = False

                def poll_once(self):
                    if not self.done:
                        self.done = True
                        self.set_result(1, "PASS", "SERIAL000001", "source.csv", {
                            "round_evidence_id": "tk-retention", "source_time": "2024-01-01T08:01:00",
                        })

            archived_round = writer.start("FCT", OldRoundMonitor, run_async=False)
            writer.poll_once()
            self.wait_for(lambda: writer.archive_status(archived_round.round_id) is not None and
                          writer.archive_status(archived_round.round_id).cleanup_eligible)
            archive_path = writer.archive_status(archived_round.round_id).path
            protected_files = {
                Path(temporary) / "manual-export.json": b'{"keep": true}',
                Path(temporary) / "source-log.txt": b"external source log",
            }
            for path, contents in protected_files.items():
                path.write_bytes(contents)

            app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey, session_root=session_root)
            try:
                app.open_settings()
                heartbeat = [0]

                def pump_ui():
                    heartbeat[0] += 1
                    root.after(10, pump_ui)

                root.after(0, pump_ui)
                deadline = time.monotonic() + 5
                while (time.monotonic() < deadline and
                       app.rounds.retention_cleanup_status().status not in {"complete", "failed"}):
                    root.update()
                    time.sleep(0.01)
                root.update()
                self.assertEqual(app.rounds.retention_cleanup_status().status, "complete",
                                 app.rounds.retention_cleanup_status())
                app._refresh_retention_cleanup_status()
                self.assertEqual(app.retention_cleanup_heading.cget("text"), "背景清理摘要")
                self.assertIn("保留 1 輪", app.retention_cleanup_status.get())
                self.assertTrue(archive_path.parent.exists())

                previous_count = len(app.rounds.retention_cleanup_summaries())
                app.retention_days_var.set("180")
                app.retention_save_button.invoke()
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    root.update()
                    summaries = app.rounds.retention_cleanup_summaries()
                    status = app.rounds.retention_cleanup_status()
                    if (len(summaries) > previous_count and status.status in {"complete", "failed"}):
                        break
                    time.sleep(0.01)
                root.update()
                self.assertEqual(app.rounds.retention_cleanup_status().status, "complete",
                                 app.rounds.retention_cleanup_status())
                self.assertFalse(archive_path.parent.exists())
                app._refresh_retention_cleanup_status()
                self.assertIn("刪除 1 輪", app.retention_cleanup_status.get())
                persisted = MachineProfileStore(Path(temporary) / "preferences.json")
                persisted.load()
                self.assertEqual(persisted.retention_days, 180)
                for path, contents in protected_files.items():
                    self.assertEqual(path.read_bytes(), contents)
                self.assertFalse(archive_path.parent.exists())
                self.assertGreater(heartbeat[0], 1)
            finally:
                app._close_settings()
                app.rounds.request_close()
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline and app.rounds.close_status().status != "complete":
                    root.update()
                    time.sleep(0.01)
                app.hotkey.close()
                root.destroy()

    def test_real_tk_distinguishes_unsaved_saved_and_archived_round_states(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.withdraw()
            session_root = Path(temporary) / "sessions"
            app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey, session_root=session_root)
            now = datetime(2026, 10, 7, 10, 0, tzinfo=timezone(timedelta(hours=8)))
            rounds = RoundCoordinator(app.events.put, audit_root=session_root, wall_clock=lambda: now)

            class OneResultMonitor(BaseMonitor):
                def __init__(self, callback):
                    super().__init__("FCT", {}, (1,), callback=callback, session_root=session_root,
                                     now=lambda: now)
                    self.done = False

                def poll_once(self):
                    if not self.done:
                        self.done = True
                        self.set_result(1, "PASS", "SERIAL000001", "source.csv", {
                            "round_evidence_id": "tk-archive-round",
                            "source_time": "2026-10-07T10:01:00",
                        })

            try:
                app.rounds = rounds
                self.assertIn("未完整保存 0", app.archive_status_label.cget("text"))
                started = rounds.start("FCT", OneResultMonitor, run_async=False)
                app.active_round_id = started.round_id
                app._apply_round_snapshot(rounds.snapshot())
                app._refresh_archive_statuses()
                self.assertIn("未完整保存 1", app.archive_status_label.cget("text"))

                import round_archival
                original_replace = round_archival.os.replace

                def fail_archive_replace(source, destination):
                    if str(destination).endswith("round-archive.json"):
                        raise OSError("temporary archive fault")
                    return original_replace(source, destination)

                with patch.object(round_archival.os, "replace", side_effect=fail_archive_replace):
                    rounds.poll_once()
                    def archive_failure_visible():
                        app._refresh_archive_statuses()
                        return (rounds.archive_status(started.round_id).status == "failed" and
                                str(app.archive_retry_button["state"]) == "normal" and
                                "temporary archive fault" in app.archive_round_detail.cget("text"))
                    self.wait_for(archive_failure_visible)
                    self.assertIn("temporary archive fault", app.archive_round_detail.cget("text"))

                app.archive_retry_button.invoke()
                self.wait_for(lambda: rounds.archive_status(started.round_id).status == "archived")
                root.update()

                app._refresh_archive_statuses()
                self.assertIn(started.round_id, app.archive_round_detail.cget("text"))
                self.assertIn("可信封存", app.archive_round_detail.cget("text"))
                self.assertIn("2026-10-07T10:00:00+08:00", app.archive_round_detail.cget("text"))
                self.assertEqual(app.status_rows[1]["status"].cget("text"), "PASS")
            finally:
                root.destroy()

    def test_real_tk_retry_button_recovers_disk_record_once_without_blocking_ui(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.withdraw()
            app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey,
                                     session_root=Path(temporary) / "sessions")
            coordinator = RoundCoordinator(app.events.put, audit_root=Path(temporary) / "sessions")
            holder = {}

            class Monitor:
                def __init__(self, callback):
                    self.callback = callback
                    self.session = SessionStore("tk-round", {}, Path(temporary) / "sessions")
                    self.results = (SlotResult(1),)

                def round_results(self):
                    return self.results

                def timeout_seconds(self, kind):
                    return {"start": 30, "test": 60, "round": 10}[kind]

                def update_round_settings(self, settings):
                    self.session.update_settings(settings)

                def publish_round_event(self, event):
                    self.session.enqueue_event(event.message, event.detail)
                    self.callback(event)

                def start(self):
                    pass

                def stop_collection(self):
                    pass

                def finish(self):
                    self.session.enqueue_finish()

                def stop(self):
                    self.callback(MonitorEvent("stopped", "stopped"))

                def poll_once(self):
                    pass

            try:
                self.assertEqual(app.save_status.cget("text"), "等待保存")
                app.rounds = coordinator
                started = coordinator.start("FCT", lambda callback: holder.setdefault(
                    "monitor", Monitor(callback)), run_async=False, capacity=1)
                app.active_round_id = started.round_id
                app._apply_round_snapshot(coordinator.snapshot())
                monitor = holder["monitor"]
                original_write = audit_records.os.write
                failed = threading.Event()
                retry_entered = threading.Event()
                release_retry = threading.Event()
                write_number = [0]

                def inject_fault(descriptor, content):
                    if b"tk_retry_probe" in content:
                        write_number[0] += 1
                        if write_number[0] == 1:
                            failed.set()
                            raise OSError("temporary disk fault")
                        if write_number[0] == 2:
                            retry_entered.set()
                            release_retry.wait(2)
                            raise OSError("disk still unavailable")
                    return original_write(descriptor, content)

                with patch.object(audit_records.os, "write", side_effect=inject_fault):
                    monitor.callback(MonitorEvent("tk_retry_probe", "persist from Tk"))
                    self.assertTrue(failed.wait(2))
                    deadline = time.monotonic() + 2
                    while (coordinator.snapshot().save_state != "failed" or
                           str(app.retry_save_button["state"]) != "normal") and time.monotonic() < deadline:
                        root.update()
                    self.assertEqual(coordinator.snapshot().save_state, "failed")
                    self.assertEqual(str(app.retry_save_button["state"]), "normal")
                    self.assertTrue(any("temporary disk fault" in line for line in app.event_lines))
                    coordinator.stop()

                    app.retry_save_button.invoke()
                    self.assertTrue(retry_entered.wait(2))
                    self.assertEqual(str(app.retry_save_button["state"]), "disabled")
                    ui_tick = threading.Event()
                    root.after(0, ui_tick.set)
                    root.update()
                    self.assertTrue(ui_tick.is_set())
                    app.retry_save_button.invoke()
                    self.assertEqual(write_number[0], 2)
                    release_retry.set()
                    deadline = time.monotonic() + 3
                    while (coordinator.snapshot().save_state != "failed" or
                           str(app.retry_save_button["state"]) != "normal") and time.monotonic() < deadline:
                        root.update()
                        time.sleep(0.01)
                    self.assertEqual(coordinator.snapshot().save_state, "failed")
                    self.assertEqual(str(app.retry_save_button["state"]), "normal")
                    ui_tick.clear()
                    root.after(0, ui_tick.set)
                    root.update()
                    self.assertTrue(ui_tick.is_set())
                    app.retry_save_button.invoke()
                    deadline = time.monotonic() + 3
                    while (coordinator.snapshot().save_state != "complete" or
                           "完整保存" not in app.save_status.cget("text")) and time.monotonic() < deadline:
                        root.update()
                        time.sleep(0.01)

                self.assertEqual(coordinator.snapshot().save_state, "complete")
                self.assertIn("完整保存", app.save_status.cget("text"))
                self.assertTrue(coordinator.flush_session(timeout=2))
                rebuilt = read_round_audit(coordinator.session_path / "audit.jsonl")
                self.assertEqual(len([event for event in rebuilt["events"]
                                      if event["kind"] == "tk_retry_probe"]), 1)
                recovery = next(event for event in rebuilt["events"]
                                if event["kind"] == "save_recovered")
                self.assertTrue(recovery["detail"]["recovered_errors"])
                self.assertTrue(rebuilt["audit_complete"])
                session_events = [json.loads(line) for line in
                                  (coordinator.session_path / "events.log").read_text(
                                      encoding="utf-8").splitlines()]
                self.assertTrue(any("保存復原" in event["message"] for event in session_events))
                self.assertTrue(coordinator.snapshot().save_history)
            finally:
                app.hotkey.close()
                root.destroy()

    def test_real_tk_can_select_and_retry_previous_round_without_changing_current_board(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.withdraw()
            session_root = Path(temporary) / "sessions"
            app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey, session_root=session_root)
            coordinator = RoundCoordinator(app.events.put, audit_root=session_root)
            app.rounds = coordinator
            monitors = []

            class Monitor:
                def __init__(self, callback, index):
                    self.callback = callback
                    self.session = SessionStore("tk-round-{}".format(index), {}, session_root)
                    self.results = (SlotResult(1),)

                def round_results(self):
                    return self.results

                def timeout_seconds(self, kind):
                    return {"start": 30, "test": 60, "round": 10}[kind]

                def update_round_settings(self, settings):
                    self.session.update_settings(settings)

                def publish_round_event(self, event):
                    self.session.enqueue_event(event.message, event.detail)
                    self.callback(event)

                def start(self):
                    pass

                def stop_collection(self):
                    pass

                def finish(self):
                    self.session.enqueue_finish()

                def stop(self):
                    self.callback(MonitorEvent("stopped", "stopped"))

                def poll_once(self):
                    pass

            def create(callback):
                monitor = Monitor(callback, len(monitors))
                monitors.append(monitor)
                return monitor

            def pump_until(predicate, timeout=4):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    root.update()
                    if predicate():
                        return True
                    time.sleep(0.01)
                return predicate()

            try:
                previous = coordinator.start("FCT", create, run_async=False, capacity=1)
                app.active_round_id = previous.round_id
                app._apply_round_snapshot(previous)
                self.assertTrue(coordinator.flush_audit())
                self.assertTrue(coordinator.flush_session())
                original_write = audit_records.os.write
                first_failure = threading.Event()

                def fail_once(descriptor, content):
                    if b"cross_round_ui_probe" in content:
                        first_failure.set()
                        raise OSError("temporary previous round UI fault")
                    return original_write(descriptor, content)

                with patch.object(audit_records.os, "write", side_effect=fail_once):
                    monitors[0].callback(MonitorEvent("cross_round_ui_probe", "old result only"))
                    self.assertTrue(first_failure.wait(2))
                    self.assertTrue(pump_until(lambda: coordinator.round_snapshot(
                        previous.round_id).save_state == "failed"))

                coordinator.stop()
                current = coordinator.start("FCT", create, run_async=False, capacity=1)
                app.active_round_id = current.round_id
                app._apply_round_snapshot(current)
                app._refresh_unsaved_rounds()
                label = next(label for label, round_id in app._unsaved_round_ids.items()
                             if round_id == previous.round_id)
                app.unsaved_round_choice.set(label)
                app._update_selected_round_retry()
                self.assertEqual(str(app.unsaved_round_retry_button["state"]), "normal")
                self.assertIn("temporary previous round UI fault",
                              app.unsaved_round_detail.cget("text"))

                retry_entered = threading.Event()
                release_retry = threading.Event()
                attempts = []

                def pause_old_retry(descriptor, content):
                    if b"cross_round_ui_probe" in content:
                        attempts.append(content)
                        retry_entered.set()
                        release_retry.wait(3)
                    return original_write(descriptor, content)

                with patch.object(audit_records.os, "write", side_effect=pause_old_retry):
                    app.unsaved_round_retry_button.invoke()
                    self.assertTrue(retry_entered.wait(2))
                    self.assertEqual(str(app.unsaved_round_retry_button["state"]), "disabled")
                    ui_tick = threading.Event()
                    root.after(0, ui_tick.set)
                    root.update()
                    self.assertTrue(ui_tick.is_set())
                    app.unsaved_round_retry_button.invoke()
                    self.assertEqual(len(attempts), 1)
                    release_retry.set()
                    self.assertTrue(pump_until(
                        lambda: coordinator.round_snapshot(previous.round_id) is None and
                        previous.round_id not in app._unsaved_round_ids.values()))

                rebuilt = read_round_audit(monitors[0].session.path / "audit.jsonl")
                probe = [event for event in rebuilt["events"]
                         if event["kind"] == "cross_round_ui_probe"]
                self.assertTrue(rebuilt["audit_complete"])
                self.assertEqual(len(probe), 1)
                self.assertEqual(probe[0]["round_id"], previous.round_id)
                self.assertEqual(app.active_round_id, current.round_id)
                self.assertEqual(coordinator.snapshot().round_id, current.round_id)
                self.assertTrue(all(result.status == "WAITING"
                                    for result in coordinator.snapshot().results))
                self.assertNotIn(previous.round_id, app._unsaved_round_ids.values())
            finally:
                coordinator.stop()
                coordinator.flush_audit()
                coordinator.flush_session()
                app.hotkey.close()
                root.destroy()

    def test_running_round_keeps_its_capacity_and_mapping_after_profile_update(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.withdraw()
            active = Path(temporary) / "active"
            final = Path(temporary) / "final"
            active.mkdir()
            final.mkdir()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey, session_root=Path(temporary) / "sessions")
            try:
                app.open_settings()
                app.profile_editor_capacity.set("3")
                app.profile_editor_mapping.set("1:3, 2:2, 3:1")
                app.profile_editor_paths["active"].set(str(active))
                app.profile_editor_paths["final"].set(str(final))
                app._apply_profile_editor()
                app.start_monitor()

                preparation_deadline = time.monotonic() + 3
                while app.rounds.session_path is None and time.monotonic() < preparation_deadline:
                    root.update()
                    time.sleep(0.01)

                self.assertIsNotNone(app.rounds.session_path)
                self.assertEqual(app.active_profile_snapshot.capacity, 3)
                self.assertEqual(len(app.status_rows), 3)
                session_metadata = json.loads((app.rounds.session_path / "session.json").read_text(
                    encoding="utf-8"))
                self.assertEqual(session_metadata["settings"]["profile_snapshot"]["profile"]["mapping"], [
                    {"source": 1, "display": 3},
                    {"source": 2, "display": 2},
                    {"source": 3, "display": 1},
                ])

                app.profile_editor_capacity.set("12")
                app.profile_editor_mapping.set(", ".join("{}:{}".format(slot, slot)
                                                            for slot in range(1, 13)))
                app._apply_profile_editor()
                self.assertEqual(app.profiles.get("B518", "FCT").capacity, 12)
                self.assertEqual(len(app.status_rows), 3)
                self.assertEqual(app.active_profile_snapshot.capacity, 3)

                record = active / "group0-slot1" / "system" / "records.csv"
                record.parent.mkdir(parents=True)
                record.write_text("MLB_SN,status\nSERIAL00000001,Pass\n", encoding="utf-8")
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    root.update()
                    snapshot = app.rounds.snapshot()
                    if any(event.event.kind == "sn_locked" for event in snapshot.events):
                        break
                    time.sleep(0.05)
                else:
                    self.fail("The running Atlas round did not report the controlled source position")

                result = next(result for result in app.rounds.snapshot().results if result.slot == 3)
                self.assertEqual((result.sn, result.status), ("SERIAL00000001", "TESTING"))
                self.assertEqual(app.kvm_result_blocks[4].cget("background"), UNAVAILABLE_COLOUR)

                archive_stamp = (datetime.now() + timedelta(seconds=1)).strftime("%Y%m%d_%H-%M-%S")
                archive = final / "SERIAL00000001" / archive_stamp / "system" / "records.csv"
                archive.parent.mkdir(parents=True)
                archive.write_text("MLB_SN,status\nSERIAL00000001,Pass\n", encoding="utf-8")
                record.unlink()
                record.parent.rmdir()
                (active / "group0-slot1").rmdir()
                deadline = time.monotonic() + 4
                while time.monotonic() < deadline:
                    root.update()
                    snapshot = app.rounds.snapshot()
                    result = next(result for result in snapshot.results if result.slot == 3)
                    if result.status == "PASS":
                        break
                    time.sleep(0.05)
                else:
                    self.fail("The Atlas final result did not reach its configured display position")

                ui_deadline = time.monotonic() + 2
                while time.monotonic() < ui_deadline:
                    root.update()
                    if app.status_rows[3]["status"].cget("text") == "PASS":
                        break
                    time.sleep(0.02)
                self.assertEqual(app.status_rows[3]["status"].cget("text"), "PASS")
                self.assertEqual(app.kvm_result_blocks[3].cget("background"), STATUS_COLOURS["PASS"])
                self.assertEqual(app.kvm_result_blocks[4].cget("background"), UNAVAILABLE_COLOUR)

                app.stop_monitor()
                stop_deadline = time.monotonic() + 2
                while time.monotonic() < stop_deadline:
                    root.update()
                    if app.rounds.snapshot().state == "STOPPED":
                        break
                    time.sleep(0.02)
                self.assertEqual(app.rounds.snapshot().state, "STOPPED")
                app._drain_events()
                root.update_idletasks()
                self.assertEqual(app._display_capacity(), 3)
                self.assertEqual(app.kvm_result_blocks[4].cget("background"), UNAVAILABLE_COLOUR)
            finally:
                if app._round_is_active():
                    app.rounds.stop()
                app.rounds.flush_session(timeout=3)
                app.rounds.flush_audit(timeout=3)
                app._close_settings()
                app.hotkey.close()
                root.destroy()

    def test_atlas_round_shows_nonblocking_conflict_and_releases_after_other_slot_finishes(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.deiconify()
            active = Path(temporary) / "active"
            final = Path(temporary) / "final"
            active.mkdir()
            final.mkdir()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey, session_root=Path(temporary) / "sessions")
            def wait_ui(predicate, timeout=5):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    root.update()
                    if predicate():
                        return
                    time.sleep(0.02)
                self.fail("Timed out waiting for the controlled Atlas conflict flow")
            try:
                app.open_settings()
                app.profile_editor_project.set("B518")
                app.profile_editor_machine.set("FCT")
                app.profile_editor_platform.set("atlas")
                app.profile_editor_capacity.set("2")
                app.profile_editor_mapping.set("1:2, 2:1")
                app.profile_editor_paths["active"].set(str(active))
                app.profile_editor_paths["final"].set(str(final))
                app._apply_profile_editor()
                app._close_settings()
                app.start_monitor()
                wait_ui(lambda: app.rounds.session_path is not None)

                def write_records(path, serial, status="Pass"):
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("MLB_SN,status\n{},{}\n".format(serial, status), encoding="utf-8")

                first_sn, second_sn = "SERIAL00000001", "SERIAL00000002"
                first_active = active / "group0-slot1" / "system" / "records.csv"
                second_active = active / "group0-slot2" / "system" / "records.csv"
                write_records(first_active, first_sn)
                write_records(second_active, second_sn)
                wait_ui(lambda: len(app.rounds.snapshot().results) == 2 and all(
                    result.status == "TESTING" for result in app.rounds.snapshot().results))

                stamp = (datetime.now() + timedelta(seconds=1)).strftime("%Y%m%d_%H-%M-%S.000-run")
                first_archive = final / first_sn / stamp / "system" / "records.csv"
                first_active.unlink()
                first_active.parent.rmdir()
                (active / "group0-slot1").rmdir()
                write_records(first_archive, first_sn)
                wait_ui(lambda: any(result.slot == 2 and result.status == "PASS"
                                    for result in app.rounds.snapshot().results), timeout=5)
                write_records(first_archive, first_sn, "FAIL")
                wait_ui(lambda: len(app.rounds.snapshot().pending_conflicts) == 1, timeout=5)
                wait_ui(lambda: app.conflict_window is not None, timeout=5)
                root.update_idletasks()

                self.assertIsNotNone(app.conflict_window, app.event_lines)
                self.assertTrue(app.conflict_window.winfo_exists())
                self.assertTrue(app.conflict_window.winfo_viewable())
                self.assertEqual((app.conflict_window.winfo_width(), app.conflict_window.winfo_height()),
                                 (820, 430))
                self.assertLessEqual(app.conflict_window.winfo_rootx() + app.conflict_window.winfo_width(),
                                     root.winfo_rootx())
                self.assertEqual(app._display_capacity(), 2)
                self.assertEqual(app.rounds.snapshot().results[0].status, "TESTING")
                self.assertEqual(app.rounds.snapshot().results[1].status, "PASS")
                conflict = app.rounds.snapshot().pending_conflicts[0]
                self.assertEqual(conflict.slot, 2)
                self.assertEqual(conflict.original.status, "PASS")
                self.assertEqual(conflict.candidate.status, "FAIL")

                comparison_rows = conflict_summary_rows(app)
                self.assertEqual(comparison_rows[0], ("項目", "原結果", "新候選"))
                self.assertEqual([row[0] for row in comparison_rows[1:]],
                                 ["結果", "SN", "來源時間", "來源檔名"])
                self.assertEqual(comparison_rows[1][1:], ("PASS", "FAIL"))
                self.assertEqual(comparison_rows[2][1:],
                                 (conflict.original.sn, conflict.candidate.sn))
                self.assertEqual(comparison_rows[3][1:],
                                 (conflict.original.source_time, conflict.candidate.source_time))
                self.assertEqual(comparison_rows[4][1:],
                                 (Path(conflict.original.source).name,
                                  Path(conflict.candidate.source).name))
                for field, expected in (("結果", [True, True]), ("SN", [False, False]),
                                        ("來源時間", [False, False]),
                                        ("來源檔名", [False, False])):
                    self.assertEqual(["comparison_difference" in
                                      app.conflict_comparison.tag_names(start)
                                      for start, _end in app._conflict_value_ranges[field]],
                                     expected, field)
                self.assertEqual(app.conflict_comparison.tag_cget(
                    "comparison_difference", "foreground"), "#b00020")
                actual_difference_font = tkfont.Font(
                    root=root,
                    font=app.conflict_comparison.tag_cget("comparison_difference", "font"),
                )
                self.assertEqual(actual_difference_font.actual("weight"), "bold")
                self.assertEqual(app.conflict_position_label.cget("text"), "顯示位置：2")
                detail_text = app.conflict_details.get("1.0", "end")
                self.assertIn(conflict.round_id, detail_text)
                self.assertIn(conflict.conflict_id, detail_text)
                self.assertIn(conflict.original.source, detail_text)
                self.assertIn(conflict.candidate.source, detail_text)
                root.update_idletasks()
                pane_height = app.conflict_panes.winfo_height()
                initial_sash = app.conflict_panes.sashpos(0)
                self.assertGreater(pane_height, 0)
                self.assertGreater(initial_sash / float(pane_height), 0.32)
                self.assertLess(initial_sash / float(pane_height), 0.48)
                app.conflict_panes.event_generate(
                    "<ButtonPress-1>", x=app.conflict_panes.winfo_width() - 8,
                    y=initial_sash + 2,
                )
                app.conflict_panes.event_generate(
                    "<B1-Motion>", x=app.conflict_panes.winfo_width() - 8,
                    y=initial_sash + 32,
                )
                app.conflict_panes.event_generate(
                    "<ButtonRelease-1>", x=app.conflict_panes.winfo_width() - 8,
                    y=initial_sash + 32,
                )
                root.update_idletasks()
                self.assertGreater(app.conflict_panes.sashpos(0), initial_sash)

                app.conflict_window.geometry("720x360")
                root.update_idletasks()
                self.assertGreaterEqual(app.conflict_window.winfo_width(), 720)
                self.assertGreaterEqual(app.conflict_window.winfo_height(), 360)
                self.assertGreater(app.conflict_list.winfo_height(), 0)
                self.assertGreater(app.conflict_comparison.winfo_width(), 0)
                self.assertEqual(str(app.resolve_conflict_original_button["state"]), "normal")
                self.assertEqual(str(app.resolve_conflict_candidate_button["state"]), "normal")

                second_stamp = (datetime.now() + timedelta(seconds=2)).strftime("%Y%m%d_%H-%M-%S.000-run")
                second_archive = final / second_sn / second_stamp / "system" / "records.csv"
                second_active.unlink()
                second_active.parent.rmdir()
                (active / "group0-slot2").rmdir()
                write_records(second_archive, second_sn)
                wait_ui(lambda: app.rounds.snapshot().collection_stopped
                        and next(result for result in app.rounds.snapshot().results
                                 if result.slot == 1).status == "PASS", timeout=5)
                self.assertFalse(app.rounds.snapshot().result_available)
                self.assertEqual(len(app.rounds.snapshot().pending_conflicts), 1)

                app.conflict_close_button.invoke()
                root.update_idletasks()
                self.assertFalse(app.conflict_window.winfo_viewable())
                self.assertEqual(len(app.rounds.snapshot().pending_conflicts), 1)

                captured_candidate_path = Path(conflict.candidate.source)
                self.assertTrue(captured_candidate_path.is_file())
                changed_source_path = captured_candidate_path.with_name("changed-after-capture.csv")
                captured_candidate_path.rename(changed_source_path)
                app._open_conflict_review()
                app.conflict_list.selection_set(0)
                root.update_idletasks()
                selected_source_row = conflict_summary_rows(app)[4][1:]
                self.assertEqual(selected_source_row[1], captured_candidate_path.name)
                self.assertIn(conflict.candidate.source,
                              app.conflict_details.get("1.0", "end"))
                app.resolve_conflict_original_button.invoke()
                self.assertFalse(app.rounds.snapshot().pending_conflicts)
                self.assertEqual(app.rounds.snapshot().results[1].status, "PASS")
                self.assertTrue(app.rounds.snapshot().result_available)
                self.assertEqual([result.status for result in app.rounds.snapshot().results], ["PASS", "PASS"])
                self.assertEqual(app.rounds.snapshot().state.value, "COMPLETED")
                app._drain_events()
                self.assertEqual(app.status_rows[1]["status"].cget("text"), "PASS")
                self.assertEqual(app.status_rows[2]["status"].cget("text"), "PASS")
                self.assertTrue(app.rounds.flush_session(timeout=3))
                self.assertTrue(app.rounds.flush_audit(timeout=3))
                rebuilt = read_round_audit(app.rounds.session_path / "audit.jsonl")
                resolved = [event for event in rebuilt["events"]
                            if event["kind"] == "conflict_resolved"]
                self.assertTrue(rebuilt["audit_complete"])
                self.assertEqual(len(resolved), 1)
                self.assertEqual(resolved[0]["detail"]["choice"], "keep_original")
                self.assertEqual(resolved[0]["detail"]["conflict_id"], conflict.conflict_id)
            finally:
                if app._round_is_active():
                    app.rounds.stop()
                app.rounds.flush_session(timeout=3)
                app.rounds.flush_audit(timeout=3)
                app._close_settings()
                app.hotkey.close()
                root.destroy()

    def test_real_tk_conflict_selection_keeps_both_sections_on_same_snapshot(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.deiconify()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey, session_root=Path(temporary) / "sessions",
            )
            coordinator = app.rounds

            def side(sn, status, source, source_id, source_time, evidence):
                return ConflictSide(sn, status, source, source_id, source_time,
                                    tuple(sorted(evidence.items())))

            first = RoundConflict(
                "conflict-first", "round-first", 1,
                side("SN-FIRST", "PASS", "/capture/original/first.csv", "original-id",
                     "", {"round_evidence_id": "evidence-first"}),
                side("", "FAIL", "", "candidate-id-must-not-become-a-path", "",
                     {"round_evidence_id": "evidence-first"}),
                (("round_evidence_id", "evidence-first"),), "2026-10-08T10:00:00",
            )
            second = RoundConflict(
                "conflict-second", "round-first", 2,
                side("SN-SECOND", "FAIL", "/capture/second/original.csv", "second-original",
                     "2026-10-08T10:01:00", {"round_evidence_id": "evidence-second"}),
                side("SN-SECOND-NEW", "PASS",
                     "/capture/second/" + ("long-candidate-" * 12) + ".csv", "second-new",
                     "2026-10-08T10:02:00", {"round_evidence_id": "evidence-second"}),
                (("round_evidence_id", "evidence-second"),), "2026-10-08T10:03:00",
            )
            third = RoundConflict(
                "conflict-third", "round-first", 3,
                side("SN-SAME", "PASS", "/line-A/group0-slot1/system/records.csv",
                     "third-original", "2026-10-08T10:04:00",
                     {"round_evidence_id": "evidence-third"}),
                side("SN-SAME", "PASS", "/line-B/group0-slot1/system/records.csv",
                     "third-candidate", "2026-10-08T10:04:00",
                     {"round_evidence_id": "evidence-third"}),
                (("round_evidence_id", "evidence-third"),), "2026-10-08T10:04:01",
            )
            fourth = RoundConflict(
                "conflict-fourth", "round-first", 4,
                side("SN-SHARED", "PASS", "/same/source/records.csv", "fourth-original",
                     "2026-10-08T10:05:00", {"round_evidence_id": "evidence-fourth"}),
                side("SN-SHARED", "FAIL", "/same/source/records.csv", "fourth-candidate",
                     "2026-10-08T10:05:00", {"round_evidence_id": "evidence-fourth"}),
                (("round_evidence_id", "evidence-fourth"),), "2026-10-08T10:05:01",
            )
            fifth = RoundConflict(
                "conflict-fifth", "round-first", 5,
                side("SN-OLD", "PASS", "/same/sn/source.csv", "fifth-original",
                     "2026-10-08T10:06:00", {"round_evidence_id": "evidence-fifth"}),
                side("SN-NEW", "PASS", "/same/sn/source.csv", "fifth-candidate",
                     "2026-10-08T10:06:00", {"round_evidence_id": "evidence-fifth"}),
                (("round_evidence_id", "evidence-fifth"),), "2026-10-08T10:06:01",
            )
            sixth = RoundConflict(
                "conflict-sixth", "round-first", 6,
                side("SN-TIME", "PASS", "/same/time/source.csv", "sixth-original",
                     "2026-10-08T10:07:00", {"round_evidence_id": "evidence-sixth"}),
                side("SN-TIME", "PASS", "/same/time/source.csv", "sixth-candidate",
                     "2026-10-08T10:08:00", {"round_evidence_id": "evidence-sixth"}),
                (("round_evidence_id", "evidence-sixth"),), "2026-10-08T10:08:01",
            )
            snapshot = RoundSnapshot(
                "round-first", "FCT", RoundState.AWAITING_REVIEW, (), False, 0, (),
                pending_conflicts=(first, second, third, fourth, fifth, sixth),
            )

            class SnapshotCoordinator:
                def __getattr__(self, name):
                    return getattr(coordinator, name)

                def snapshot(self):
                    return snapshot

            app.rounds = SnapshotCoordinator()
            app.active_round_id = snapshot.round_id
            try:
                app.events.put(RoundEvent(snapshot.round_id, 1, MonitorEvent(
                    "conflict_detected", "controlled conflict", detail={"round_id": snapshot.round_id},
                )))
                deadline = time.monotonic() + 3
                while time.monotonic() < deadline:
                    root.update()
                    if app.conflict_window and app.conflict_window.winfo_exists():
                        break
                    time.sleep(0.01)
                self.assertTrue(app.conflict_window and app.conflict_window.winfo_exists())
                root.update_idletasks()
                self.assertEqual(app.conflict_position_label.cget("text"), "顯示位置：1")
                first_rows = conflict_summary_rows(app)
                self.assertEqual(first_rows[1], ("結果", "PASS", "FAIL"))
                self.assertEqual(first_rows[2], ("SN", "SN-FIRST", "未知"))
                self.assertEqual(first_rows[3], ("來源時間", "未知", "未知"))
                self.assertEqual(first_rows[4], ("來源檔名", "first.csv", "未知"))
                result_ranges = app._conflict_value_ranges["結果"]
                self.assertEqual(["comparison_difference" in
                                  app.conflict_comparison.tag_names(start)
                                  for start, _end in result_ranges], [True, True])
                self.assertEqual(app.conflict_comparison.tag_cget(
                    "comparison_difference", "foreground"), "#b00020")
                difference_font = tkfont.Font(
                    root=root,
                    font=app.conflict_comparison.tag_cget("comparison_difference", "font"),
                )
                self.assertEqual(difference_font.actual("weight"), "bold")
                same_unknown_time = app._conflict_value_ranges["來源時間"]
                self.assertEqual(["comparison_difference" in
                                  app.conflict_comparison.tag_names(start)
                                  for start, _end in same_unknown_time], [False, False])
                first_detail = app.conflict_details.get("1.0", "end")
                self.assertIn("candidate-id-must-not-become-a-path", first_detail)
                self.assertIn("/capture/original/first.csv", first_detail)
                self.assertNotIn("candidate-id-must-not-become-a-path.csv", first_rows[3][1])

                app.conflict_list.selection_clear(0, "end")
                app.conflict_list.selection_set(1)
                app.conflict_list.event_generate("<<ListboxSelect>>")
                root.update_idletasks()
                second_rows = conflict_summary_rows(app)
                self.assertEqual(app.conflict_position_label.cget("text"), "顯示位置：2")
                self.assertEqual(second_rows[1], ("結果", "FAIL", "PASS"))
                self.assertEqual(second_rows[2], ("SN", "SN-SECOND", "SN-SECOND-NEW"))
                self.assertEqual(second_rows[3],
                                 ("來源時間", "2026-10-08T10:01:00", "2026-10-08T10:02:00"))
                self.assertEqual(second_rows[4],
                                 ("來源檔名", "original.csv", ("long-candidate-" * 12) + ".csv"))
                for field in ("結果", "SN", "來源時間", "來源檔名"):
                    self.assertEqual(["comparison_difference" in
                                      app.conflict_comparison.tag_names(start)
                                      for start, _end in app._conflict_value_ranges[field]],
                                     [True, True], field)
                self.assertLess(app.conflict_comparison.xview()[1], 1.0)
                second_detail = app.conflict_details.get("1.0", "end")
                self.assertIn("conflict-second", second_detail)
                self.assertNotIn("conflict-first", second_detail)
                app.conflict_comparison.xview_moveto(1)
                self.assertGreater(app.conflict_comparison.xview()[0], 0.0)
                app.conflict_list.selection_clear(0, "end")
                app.conflict_list.selection_set(2)
                app.conflict_list.event_generate("<<ListboxSelect>>")
                root.update_idletasks()
                third_rows = conflict_summary_rows(app)
                self.assertEqual(third_rows[4], (
                    "來源檔名",
                    "records.csv · line-A/group0-slot1/system",
                    "records.csv · line-B/group0-slot1/system",
                ))
                self.assertTrue(all("comparison_difference" in
                                    app.conflict_comparison.tag_names(start)
                                    for start, _end in app._conflict_value_ranges["來源檔名"]))
                third_detail = app.conflict_details.get("1.0", "end")
                self.assertIn("/line-A/group0-slot1/system/records.csv", third_detail)
                self.assertIn("/line-B/group0-slot1/system/records.csv", third_detail)
                app.conflict_list.selection_clear(0, "end")
                app.conflict_list.selection_set(3)
                app.conflict_list.event_generate("<<ListboxSelect>>")
                root.update_idletasks()
                fourth_rows = conflict_summary_rows(app)
                self.assertEqual(fourth_rows[4], ("來源檔名", "records.csv", "records.csv"))
                self.assertEqual(["comparison_difference" in
                                  app.conflict_comparison.tag_names(start)
                                  for start, _end in app._conflict_value_ranges["來源檔名"]],
                                 [False, False])
                self.assertEqual(["comparison_difference" in
                                  app.conflict_comparison.tag_names(start)
                                  for start, _end in app._conflict_value_ranges["結果"]],
                                 [True, True])
                app.conflict_list.selection_clear(0, "end")
                app.conflict_list.selection_set(4)
                app.conflict_list.event_generate("<<ListboxSelect>>")
                root.update_idletasks()
                self.assertEqual(conflict_summary_rows(app)[2], ("SN", "SN-OLD", "SN-NEW"))
                for field, expected in (("結果", [False, False]), ("SN", [True, True]),
                                        ("來源時間", [False, False]),
                                        ("來源檔名", [False, False])):
                    self.assertEqual(["comparison_difference" in
                                      app.conflict_comparison.tag_names(start)
                                      for start, _end in app._conflict_value_ranges[field]],
                                     expected, field)
                app.conflict_list.selection_clear(0, "end")
                app.conflict_list.selection_set(5)
                app.conflict_list.event_generate("<<ListboxSelect>>")
                root.update_idletasks()
                self.assertEqual(conflict_summary_rows(app)[3], (
                    "來源時間", "2026-10-08T10:07:00", "2026-10-08T10:08:00",
                ))
                for field, expected in (("結果", [False, False]), ("SN", [False, False]),
                                        ("來源時間", [True, True]),
                                        ("來源檔名", [False, False])):
                    self.assertEqual(["comparison_difference" in
                                      app.conflict_comparison.tag_names(start)
                                      for start, _end in app._conflict_value_ranges[field]],
                                     expected, field)
                app.conflict_list.selection_clear(0, "end")
                app.conflict_list.selection_set(0)
                app.conflict_list.event_generate("<<ListboxSelect>>")
                root.update_idletasks()
                self.assertEqual(app.conflict_comparison.xview()[0], 0.0)
                self.assertEqual(app.conflict_position_label.cget("text"), "顯示位置：1")
                for field, expected in (("結果", [True, True]), ("SN", [True, True]),
                                        ("來源時間", [False, False]),
                                        ("來源檔名", [True, True])):
                    self.assertEqual(["comparison_difference" in
                                      app.conflict_comparison.tag_names(start)
                                      for start, _end in app._conflict_value_ranges[field]],
                                     expected, field)
                app.conflict_window.geometry("720x360")
                root.update_idletasks()
                self.assertTrue(app.conflict_comparison_scrollbar.winfo_viewable())
                self.assertTrue(app.conflict_close_button.winfo_viewable())
                first_detail = app.conflict_details.get("1.0", "end")
                self.assertIn("conflict-first", first_detail)
                self.assertNotIn("conflict-second", first_detail)
            finally:
                app.rounds = coordinator
                app.hotkey.close()
                coordinator.request_close()
                root.destroy()

    def test_unknown_atlas_identity_change_is_visible_as_fail_and_audited_without_reason(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.deiconify()
            active = Path(temporary) / "active"
            final = Path(temporary) / "final"
            active.mkdir()
            final.mkdir()
            app = B518LogSolutionApp(
                root, hotkey_factory=FakeHotkey, session_root=Path(temporary) / "sessions")

            def wait_ui(predicate, timeout=5):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    root.update()
                    if predicate():
                        return
                    time.sleep(0.02)
                self.fail("Timed out waiting for the unknown-source FAIL flow")

            try:
                app.open_settings()
                app.profile_editor_project.set("B518")
                app.profile_editor_machine.set("FCT")
                app.profile_editor_platform.set("atlas")
                app.profile_editor_capacity.set("1")
                app.profile_editor_mapping.set("1:1")
                app.profile_editor_paths["active"].set(str(active))
                app.profile_editor_paths["final"].set(str(final))
                app._apply_profile_editor()
                app._close_settings()
                app.start_monitor()
                wait_ui(lambda: app.rounds.session_path is not None)

                record = active / "group0-slot1" / "system" / "records.csv"
                record.parent.mkdir(parents=True)
                record.write_text("MLB_SN,status\nSERIAL00000001,Pass\n", encoding="utf-8")
                wait_ui(lambda: len(app.rounds.snapshot().results) == 1 and
                        app.rounds.snapshot().results[0].status == "TESTING")
                record.write_text("MLB_SN,status\nSERIAL00000002,Pass\n", encoding="utf-8")
                wait_ui(lambda: app.rounds.snapshot().results[0].status == "FAIL")
                wait_ui(lambda: app.status_rows[1]["status"].cget("text") == "FAIL")

                snapshot = app.rounds.snapshot()
                self.assertTrue(snapshot.result_available)
                self.assertEqual(snapshot.results[0].sn, "SERIAL00000001")
                rejected = next(item.event for item in snapshot.events
                                if item.event.kind == "unknown_round_candidate_rejected")
                self.assertEqual(rejected.detail["operation"], "fail_unconfirmed_candidate")
                self.assertNotIn("reason", rejected.detail)
                self.assertTrue(app.rounds.flush_audit(timeout=3))
                from audit_records import read_round_audit
                stored = read_round_audit(app.rounds.session_path / "audit.jsonl")
                audit_event = next(item for item in stored["events"]
                                   if item["kind"] == "unknown_round_candidate_rejected")
                self.assertEqual(audit_event["status"], "TESTING")
                self.assertTrue(audit_event["operation_at"])
                self.assertEqual(audit_event["detail"]["candidate_sn"], "SERIAL00000002")
                self.assertNotIn("reason", audit_event["detail"])
            finally:
                if app._round_is_active():
                    app.rounds.stop()
                app.rounds.flush_session(timeout=3)
                app.rounds.flush_audit(timeout=3)
                app._close_settings()
                app.hotkey.close()
                root.destroy()

    def test_twenty_position_profile_renders_two_fixed_bands_and_scrollable_details(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.withdraw()
            app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey)
            try:
                app.open_settings()
                app.profile_editor_capacity.set("10")
                app.profile_editor_mapping.set(", ".join("{}:{}".format(source, source)
                                                            for source in range(1, 11)))
                app._apply_profile_editor()
                root.deiconify()
                root.update()
                self.assertTrue(app.kvm_result_blocks[10].winfo_ismapped())
                self.assertFalse(app.kvm_result_blocks[11].winfo_ismapped())
                self.assertEqual([app.kvm_layout_marker.itemcget(cell, "fill") for cell in
                                  app.kvm_layout_marker.find_withtag("layout-cell")],
                                 ["#000000", "#ffffff"])
                self.assertEqual(root.winfo_height(), window_height(10, root.winfo_screenheight()))

                app.profile_editor_capacity.set("11")
                app.profile_editor_mapping.set(", ".join("{}:{}".format(source, source)
                                                            for source in range(1, 12)))
                app._apply_profile_editor()
                root.update()
                self.assertTrue(app.kvm_result_blocks[11].winfo_ismapped())
                self.assertEqual([app.kvm_layout_marker.itemcget(cell, "fill") for cell in
                                  app.kvm_layout_marker.find_withtag("layout-cell")],
                                 ["#ffffff", "#000000"])
                self.assertGreater(app.kvm_result_blocks[11].winfo_y(),
                                   app.kvm_result_blocks[10].winfo_y())
                self.assertEqual(root.winfo_height(), window_height(11, root.winfo_screenheight()))

                app.profile_editor_capacity.set("20")
                app.profile_editor_mapping.set(", ".join("{}:{}".format(source, source)
                                                            for source in range(1, 21)))
                app._apply_profile_editor()
                root.update_idletasks()
                root.update()

                self.assertTrue(root.winfo_ismapped())
                self.assertEqual(root.winfo_width(), WINDOW_WIDTH)
                self.assertEqual(root.winfo_height(), window_height(20, root.winfo_screenheight()))
                self.assertLessEqual(root.winfo_height(), root.winfo_screenheight())
                self.assertEqual(len(app.status_rows), 20)
                self.assertEqual(len(app.kvm_result_blocks), 20)
                self.assertEqual(app.kvm_state_marker.winfo_x(), 278)
                self.assertEqual(app.kvm_state_marker.winfo_y(), 0)
                self.assertEqual(app.kvm_state_marker.winfo_width(), 26)
                self.assertGreater(app.kvm_result_blocks[1].winfo_y(),
                                   app.kvm_state_marker.winfo_y() + app.kvm_state_marker.winfo_height())
                self.assertEqual(app.kvm_result_blocks[1].winfo_y(), app.kvm_result_blocks[10].winfo_y())
                self.assertGreater(app.kvm_result_blocks[11].winfo_y(), app.kvm_result_blocks[10].winfo_y())
                self.assertEqual(app.kvm_result_blocks[11].winfo_x(), app.kvm_result_blocks[1].winfo_x())
                self.assertEqual(app.kvm_result_blocks[20].winfo_y(), app.kvm_result_blocks[11].winfo_y())
                self.assertEqual(app.kvm_result_blocks[20].cget("background"), STATUS_COLOURS["WAITING"])
                self.assertLess(app.rows_canvas.winfo_height(), len(app.status_rows) * ROW_HEIGHT)

                original_scaling = float(root.tk.call("tk", "scaling"))
                root.tk.call("tk", "scaling", 1.5)
                root.update_idletasks()
                self.assertLessEqual(app.rows_panel.winfo_rooty() + app.rows_panel.winfo_height(),
                                     root.winfo_rooty() + root.winfo_height())
                for label in app.template_labels.values():
                    self.assertLessEqual(label.winfo_reqheight(), label.winfo_height())
                for row in app.status_rows.values():
                    self.assertLessEqual(row["status"].winfo_reqheight(), ROW_HEIGHT)
                root.tk.call("tk", "scaling", original_scaling)
                root.update_idletasks()

                marker_y = app.kvm_result_blocks[1].winfo_rooty()
                app.rows_canvas.yview_scroll(100, "units")
                root.update_idletasks()
                self.assertEqual(app.kvm_result_blocks[1].winfo_rooty(), marker_y)
                self.assertEqual(app.rows_canvas.yview()[1], 1.0)
            finally:
                app._close_settings()
                app.hotkey.close()
                root.destroy()

    def test_engineer_can_apply_and_cancel_a_complete_profile_draft(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.withdraw()
            app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey)
            try:
                app.open_settings()
                app.profile_editor_project.set("Demo")
                app.profile_editor_machine.set("DFU")
                app.profile_editor_platform.set("atlas")
                app.profile_editor_capacity.set("2")
                app.profile_editor_paths["active"].set("/deployment/active")
                app.profile_editor_paths["final"].set("/deployment/final")
                app.profile_editor_mapping.set("1:2, 2:1")
                app.profile_editor_timeouts["start"].set("45")
                app._apply_profile_editor()

                saved = app.profiles.get("Demo", "DFU")
                self.assertEqual(saved.mapping, ((1, 2), (2, 1)))
                self.assertEqual(saved.timeouts["start"], 45)
                self.assertIn("Demo", app.project_choice.cget("values"))
                self.assertEqual(MachineProfileStore(Path(temporary) / "preferences.json").load()[0]
                                 .get("Demo", "DFU"), saved)

                app.profile_editor_project.set("Unsaved")
                app.profile_editor_capacity.set("3")
                app._cancel_profile_editor()

                self.assertEqual(app.profile_editor_project.get(), "Demo")
                self.assertEqual(app.profile_editor_capacity.get(), "2")
                self.assertNotIn("Unsaved", app.profiles.projects)
            finally:
                app._close_settings()
                app.hotkey.close()
                root.destroy()

    def test_engineer_can_load_an_existing_profile_before_editing_it(self):
        root = tk.Tk()
        root.withdraw()
        app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey)
        try:
            app.open_settings()
            app.profile_editor_project.set("B482")
            app.profile_editor_machine.set("BT")
            app._load_profile_editor_selection()

            self.assertEqual(app.profile_editor_platform.get(), "b482")
            self.assertEqual(app.profile_editor_capacity.get(), "4")
            self.assertEqual(app.profile_editor_mapping.get(), "1:1, 2:2, 3:3, 4:4")
            app._cancel_profile_editor()
            self.assertEqual(app.profile_editor_project.get(), "B482")
            self.assertEqual(app.profile_editor_machine.get(), "BT")
            self.assertEqual(app.profile_editor_capacity.get(), "4")
        finally:
            app._close_settings()
            app.hotkey.close()
            root.destroy()

    def test_failed_profile_save_keeps_the_active_catalog_and_selected_configuration(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.withdraw()
            app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey)
            try:
                app.open_settings()
                original_catalog = app.profiles.to_dict()
                original_selection = (app.project.get(), app.station.get())
                app.profile_editor_project.set("Unsaved")
                with patch.object(app.profile_store, "save", side_effect=OSError("disk full")):
                    app._apply_profile_editor()

                self.assertEqual(app.profiles.to_dict(), original_catalog)
                self.assertEqual((app.project.get(), app.station.get()), original_selection)
                self.assertIn("原配置仍有效", app.profile_editor_status.get())
            finally:
                app._close_settings()
                app.hotkey.close()
                root.destroy()


    def test_engineer_import_export_and_reload_preserve_a_deployable_catalog(self):
        with TemporaryDirectory() as temporary:
            source_preferences = Path(temporary) / "source.json"
            deployment_preferences = Path(temporary) / "deployed" / "preferences.json"
            exported = Path(temporary) / "deployment-profile.json"
            single_profile_export = Path(temporary) / "single-profile.json"
            with patch("b518_log_solution.PREFS_PATH", source_preferences):
                root = tk.Tk()
                root.withdraw()
                source = B518LogSolutionApp(root, hotkey_factory=FakeHotkey)
                try:
                    source.open_settings()
                    source.retention_days_var.set("180")
                    source.retention_save_button.invoke()
                    source.profile_editor_project.set("Demo")
                    source.profile_editor_machine.set("DFU")
                    source.profile_editor_platform.set("atlas")
                    source.profile_editor_capacity.set("2")
                    source.profile_editor_paths["active"].set("/deployment/active")
                    source.profile_editor_paths["final"].set("/deployment/final")
                    source.profile_editor_mapping.set("1:2, 2:1")
                    source.profile_editor_timeouts["start"].set("45")
                    source._apply_profile_editor()
                    with patch("b518_log_solution.filedialog.asksaveasfilename", return_value=str(exported)):
                        source._export_profiles()
                    self.assertNotIn("retention_days", json.loads(exported.read_text(encoding="utf-8")))
                    MachineProfileStore.export_document(
                        single_profile_export,
                        ProfileCatalog((source.profiles.get("Demo", "DFU"),)),
                    )
                finally:
                    source._close_settings()
                    source.hotkey.close()
                    root.destroy()

            with patch("b518_log_solution.PREFS_PATH", deployment_preferences):
                deploy_root = tk.Tk()
                deploy_root.withdraw()
                deployed = B518LogSolutionApp(deploy_root, hotkey_factory=FakeHotkey)
                try:
                    deployed.open_settings()
                    deployed.retention_days_var.set("730")
                    deployed.retention_save_button.invoke()
                    with patch("b518_log_solution.filedialog.askopenfilename",
                               return_value=str(single_profile_export)):
                        deployed._import_profiles()
                    reloaded = MachineProfileStore(deployment_preferences)
                    reloaded.load()
                    self.assertEqual(reloaded.retention_days, 730)
                    self.assertEqual(deployed.profiles.get("Demo", "DFU").paths["active"],
                                     "/deployment/active")
                    self.assertEqual((deployed.project.get(), deployed.station.get()), ("Demo", "DFU"))
                    self.assertIn("原選擇不存在", deployed.profile_editor_status.get())
                    original = deployed.profiles.to_dict()
                    invalid_export = Path(temporary) / "invalid.json"
                    invalid_export.write_text("{", encoding="utf-8")
                    with patch("b518_log_solution.filedialog.askopenfilename",
                               return_value=str(invalid_export)):
                        deployed._import_profiles()
                    self.assertEqual(deployed.profiles.to_dict(), original)
                    self.assertIn("原配置保留", deployed.profile_editor_status.get())

                    replacement = deployed.profiles.with_profile(replace(
                        deployed.profiles.get("Demo", "DFU"),
                        paths={"active": "/updated/active", "final": "/updated/final"},
                    ))
                    deployed.project.set("Demo")
                    deployed.station.set("DFU")
                    deployed.profile_store.save(replacement, "Demo", "DFU")
                    deployed._reload_profiles()

                    self.assertEqual(deployed.profiles.get("Demo", "DFU").paths["active"],
                                     "/updated/active")
                    self.assertEqual(deployed.profile_editor_project.get(), "Demo")
                    self.assertEqual(deployed.profiles.get("Demo", "DFU").paths["active"],
                                     "/updated/active")
                finally:
                    deployed._close_settings()
                    deployed.hotkey.close()
                    deploy_root.destroy()

    def test_app_completes_rswmt_final_only_round_through_shared_entry(self):
        with TemporaryDirectory() as temporary:
            output = Path(temporary) / "output" / "SmtCal"
            output.mkdir(parents=True)
            app = object.__new__(B518LogSolutionApp)
            app.root = MagicMock()
            app.events = queue.Queue()
            app.rounds = RoundCoordinator(app.events.put)
            app.active_round_id = None
            install_test_profile(app, "BT", "rswmt", final=str(output))
            profile = app.profiles.get("B518", "BT")
            app.profiles = app.profiles.with_profile(replace(
                profile, paths=dict(profile.paths, final=str(output)),
                timeouts=dict(profile.timeouts, start=240),
            ))
            app.start_button = MagicMock()
            app.monitor_state = MagicMock()
            app.event_lines = []
            app.settings_log = None
            app._save_preferences = MagicMock()
            app._reset_rows = MagicMock()
            app._set_monitor_controls = MagicMock()

            with patch("log_monitoring.SessionStore"):
                app.start_monitor()
                prepare_deadline = time.monotonic() + 3
                while app.rounds.session_path is None and time.monotonic() < prepare_deadline:
                    time.sleep(0.01)
                self.assertIsNotNone(app.rounds.session_path)
                start = datetime.now().replace(microsecond=0)
                stop = start + timedelta(seconds=5)
                headers = ['Serial Number', 'Test Pass/Fail Status', 'List of Failing Tests',
                           'Error Description', 'Test Start Time', 'Test Stop Time', 'PRODUCT',
                           'tc=Slot:tech=None:band=None;subtc=None:rate=None:freq=None:pwr=None;']
                for slot in range(1, 5):
                    name = "SERIAL{:06d}".format(slot)
                    result_dir = output / stop.strftime("%Y-%m-%d_%H-%M-%S")
                    result_dir.mkdir(exist_ok=True)
                    content = io.StringIO()
                    writer = csv.writer(content)
                    writer.writerow(["Overlay", "SmtCal"] + [""] * 6)
                    writer.writerow(headers)
                    writer.writerow([name, "Pass", "[]", "", start.strftime("%Y/%d/%m %H:%M:%S"),
                                     stop.strftime("%Y/%d/%m %H:%M:%S"), "B518", slot])
                    (result_dir / (name + "_" + stop.strftime("%Y-%m-%d_%H-%M-%S") + ".csv")).write_text(
                        content.getvalue(), encoding="utf-8",
                    )

                deadline = time.monotonic() + 12
                while time.monotonic() < deadline:
                    snapshot = app.rounds.snapshot()
                    if snapshot.result_available:
                        break
                    time.sleep(0.1)
                else:
                    app.rounds.stop()
                    self.fail("RS-WMT final-only files did not complete the App round")
                app.rounds.stop()

            snapshot = app.rounds.snapshot()
            self.assertEqual(snapshot.station, "BT")
            self.assertEqual([result.status for result in snapshot.results], ["PASS"] * 4)
            self.assertFalse(any(event.event.status == "TESTING" for event in snapshot.events))

    def test_legacy_profile_migration_preserves_valid_default_capacities(self):
        profiles, _project, _machine = migrate_legacy_preferences({})
        self.assertEqual(profiles.get("B518", "DFU").capacity, 7)
        self.assertEqual(profiles.get("B518", "FCT").capacity, 6)
        self.assertEqual(profiles.get("B482", "BT").capacity, 4)
        self.assertEqual(window_height(4), 514)
        self.assertEqual(window_height(6), 608)
        self.assertEqual(window_height(7), 655)
        self.assertEqual(window_height(20), 682)
        self.assertEqual(visible_detail_rows(20, 500), 1)
        self.assertGreaterEqual(WINDOW_WIDTH, 342 + 2 + 12)

    def test_all_display_statuses_have_explicit_colours(self):
        for status in ("PASS", "FAIL", "TESTING", "NOTEST", "WAITING", "COMPLETING", "STALLED", "STOPPED", "TIMEOUT"):
            self.assertRegex(STATUS_COLOURS[status], r"^#[0-9a-fA-F]{6}$")
        self.assertRegex(UNAVAILABLE_COLOUR, r"^#[0-9a-fA-F]{6}$")
        self.assertEqual(KVM_BLOCK_COUNT, 20)

    def test_kvm_band_separates_capacity_colours_from_unavailable_positions(self):
        self.assertEqual(kvm_block_colour(20, 20, "PASS"), STATUS_COLOURS["PASS"])
        self.assertEqual(kvm_block_colour(12, 12, "NOTEST"), STATUS_COLOURS["NOTEST"])
        self.assertEqual(kvm_block_colour(12, 13, "PASS"), UNAVAILABLE_COLOUR)
        self.assertEqual(kvm_block_colour(4, 4, "FAIL"), STATUS_COLOURS["FAIL"])
        self.assertEqual(kvm_block_colour(4, 5, "TESTING"), UNAVAILABLE_COLOUR)

    def test_all_serial_numbers_use_fixed_fourteen_point_font(self):
        self.assertEqual(MAIN_FONT_SIZE, 14)
        self.assertEqual(sn_font_size("HK5HUX6STQ800003YV"), 14)
        self.assertEqual(sn_font_size("X" * 128), 14)

    def test_global_hotkey_success_delivers_callback_and_can_close(self):
        fired = []
        registration = create_global_hotkey(lambda: fired.append(True), platform_name="darwin", implementation=FakeHotkey)
        self.assertTrue(registration.available)
        registration.callback()
        self.assertEqual(fired, [True])
        registration.close()
        self.assertTrue(registration.closed)

    def test_global_hotkey_uses_command_shift_m(self):
        self.assertEqual(COMMAND_SHIFT_M_KEYCODE, 46)
        self.assertEqual(COMMAND_SHIFT_MODIFIERS, 0x0100 | 0x0200)

    def test_global_hotkey_conflict_is_a_safe_fallback(self):
        def conflict(_callback):
            raise GlobalHotkeyError("shortcut already used")

        registration = create_global_hotkey(lambda: None, platform_name="darwin", implementation=conflict)
        self.assertIsInstance(registration, UnavailableHotkey)
        self.assertFalse(registration.available)
        self.assertIn("already used", registration.message)

    def test_non_macos_is_a_safe_local_only_fallback(self):
        registration = create_global_hotkey(lambda: None, platform_name="linux", implementation=FakeHotkey)
        self.assertIsInstance(registration, UnavailableHotkey)
        self.assertFalse(registration.available)

    def test_dashboard_row_cells_fill_the_full_row_geometry(self):
        root = tk.Tk()
        root.withdraw()
        app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey)
        root.update_idletasks()
        try:
            for row in app.status_rows.values():
                self.assertGreaterEqual(row["slot"].winfo_width(), 59)
                self.assertGreaterEqual(row["status"].winfo_width(), 93)
                self.assertGreaterEqual(row["sn"].winfo_width(), 188)
                for cell in row.values():
                    self.assertGreaterEqual(cell.winfo_height(), ROW_HEIGHT)
                    self.assertEqual(int(cell.cget("font").split()[1]), MAIN_FONT_SIZE)
            self.assertEqual(tuple(app.template_labels), STATUS_TEMPLATE_STATES)
            for status, label in app.template_labels.items():
                self.assertEqual(label.cget("text"), status)
                self.assertEqual(label.cget("background"), STATUS_COLOURS[status])
        finally:
            app.hotkey.close()
            root.destroy()

    def test_empty_paths_are_rejected_before_monitor_creation(self):
        root = tk.Tk()
        root.withdraw()
        app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey)
        app.station.set("DFU")
        profile = app.profiles.get("B518", "DFU")
        app.profiles = app.profiles.with_profile(replace(profile, paths={"active": "", "final": ""}))
        try:
            with patch("b518_log_solution.DEFAULT_PLATFORM_REGISTRY.create_monitor") as monitor_type, \
                    patch("b518_log_solution.messagebox.showerror") as show_error:
                app.start_monitor()
            monitor_type.assert_not_called()
            show_error.assert_called_once()
            self.assertIsNone(app.rounds.snapshot())
        finally:
            app.hotkey.close()
            root.destroy()

    def test_configured_directory_never_treats_blank_as_current_directory(self):
        self.assertIsNone(configured_directory(""))
        self.assertIsNone(configured_directory("   "))
        self.assertIsNone(configured_directory("/path/that/does/not/exist"))
        self.assertEqual(configured_directory("."), Path("."))

    def test_configured_directory_rejects_a_directory_without_read_access(self):
        with patch("b518_log_solution.os.access", return_value=False):
            self.assertIsNone(configured_directory("."))

    def test_operator_selects_project_and_machine_and_choice_survives_restart(self):
        with TemporaryDirectory() as temporary:
            app_root = Path(temporary) / "B518LogSolution"
            prefs = app_root / "preferences.json"
            with patch("b518_log_solution.APP_ROOT", app_root), patch("b518_log_solution.PREFS_PATH", prefs):
                root = tk.Tk()
                root.withdraw()
                app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey)
                try:
                    self.assertEqual(app.project_choice.cget("values"), ("B518", "B482"))
                    app.project.set("B482")
                    app._project_changed()
                    self.assertEqual(app.machine_choice.cget("values"), ("BT",))
                    profile = app.profiles.get(app.project.get(), app.station.get())
                    self.assertEqual(profile.platform, "b482")
                    profile_paths = dict(profile.paths)
                    profile_paths["final"] = temporary
                    profile_timeouts = dict(profile.timeouts)
                    profile_timeouts["round"] = 6300
                    app.profiles = app.profiles.with_profile(
                        replace(profile, paths=profile_paths, timeouts=profile_timeouts),
                    )
                    self.assertEqual(app.profiles.get("B482", "BT").timeouts["round"], 6300)
                    app._save_preferences()
                finally:
                    self.wait_for(lambda: app.rounds.retention_cleanup_status().status in {
                        "complete", "failed",
                    })
                    app.hotkey.close()
                    root.destroy()

                restarted_root = tk.Tk()
                restarted_root.withdraw()
                restarted = B518LogSolutionApp(restarted_root, hotkey_factory=FakeHotkey)
                try:
                    self.assertEqual((restarted.project.get(), restarted.station.get()), ("B482", "BT"))
                    self.assertEqual(restarted.profiles.get("B482", "BT").timeouts["round"], 6300)
                    with patch("b518_log_solution.DEFAULT_PLATFORM_REGISTRY.create_monitor") as monitor_factory:
                        restarted.start_monitor()
                    self.assertEqual(monitor_factory.call_args.args[0], "b482")
                    self.assertEqual(monitor_factory.call_args.kwargs["timeouts"]["round"], 6300)
                finally:
                    self.wait_for(lambda: restarted.rounds.retention_cleanup_status().status in {
                        "complete", "failed",
                    })
                    restarted.hotkey.close()
                    restarted_root.destroy()

    def test_monitor_creation_error_is_visible_and_returns_to_standby(self):
        root = tk.Tk()
        root.withdraw()
        app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey)
        app.station.set("DFU")
        try:
            with patch("b518_log_solution.DEFAULT_PLATFORM_REGISTRY.create_monitor",
                       side_effect=PermissionError("denied")), \
                    patch("b518_log_solution.messagebox.showerror") as show_error:
                app.start_monitor()
                deadline = time.monotonic() + 3
                while not show_error.called and time.monotonic() < deadline:
                    root.update()
                    time.sleep(0.01)
            self.assertFalse(app._round_is_active())
            self.assertEqual(app.monitor_state.cget("text"), "啟動失敗")
            self.assertIn("denied", app.event_lines[-1])
            show_error.assert_called_once()
        finally:
            app.hotkey.close()
            root.destroy()

    def test_settings_expose_profile_editor_and_session_log_without_legacy_monitor_tab(self):
        root = tk.Tk()
        root.withdraw()
        app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey)
        try:
            app.open_settings()
            tabs = tuple(app.settings_notebook.tab(tab, "text")
                         for tab in app.settings_notebook.tabs())
            self.assertEqual(tabs, ("工程師配置", "事件與 Session", "保存期限"))
        finally:
            app._close_settings()
            app.hotkey.close()
            root.destroy()

    def test_explicit_light_theme_keeps_dark_mode_controls_readable(self):
        root = tk.Tk()
        root.withdraw()
        app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey)
        app.open_settings()
        root.update_idletasks()
        try:
            style = ttk.Style(root)
            self.assertEqual(style.theme_use(), "clam")
            self.assertEqual(style.lookup("TLabel", "foreground"), "#111827")
            self.assertEqual(style.lookup("TEntry", "fieldbackground"), "#ffffff")
            self.assertEqual(style.lookup("TButton", "foreground"), "#111827")
            self.assertEqual(app.settings_window.cget("background"), "#f3f4f6")
            self.assertEqual(app.settings_log.cget("background"), "#ffffff")
            self.assertEqual(app.settings_log.cget("foreground"), "#111827")

            def descendants(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from descendants(child)

            main_labels = [widget for widget in descendants(root) if isinstance(widget, tk.Label)]
            self.assertTrue(main_labels)
            for label in main_labels:
                self.assertTrue(label.cget("foreground"))
        finally:
            app._close_settings()
            app.hotkey.close()
            root.destroy()





    def test_monitor_lifecycle_never_changes_window_topmost_attribute(self):
        monitor = MagicMock()
        app = object.__new__(B518LogSolutionApp)
        app.root = MagicMock()
        app.events = queue.Queue()
        app.rounds = RoundCoordinator(app.events.put)
        app.active_round_id = None
        install_test_profile(app, "DFU", "atlas")
        app.start_button = MagicMock()
        app.monitor_state = MagicMock()
        app.event_lines = []
        app.settings_log = None
        app._save_preferences = MagicMock()
        app._reset_rows = MagicMock()
        app._set_monitor_controls = MagicMock()
        with patch("b518_log_solution.DEFAULT_PLATFORM_REGISTRY.create_monitor", return_value=monitor):
            app.start_monitor()
            self.wait_for(lambda: monitor.start.called)

        monitor.start.assert_called_once()
        self.assertIsNotNone(app.rounds.snapshot())
        self.assertEqual(app.rounds.snapshot().station, "DFU")
        app.root.attributes.assert_not_called()

        app._handle_event(MonitorEvent("finished", "monitor ended"))
        app.root.attributes.assert_not_called()
        app.rounds.stop()

    def test_existing_monitor_sources_start_through_the_shared_round_entry(self):
        scenarios = (("DFU", "atlas"), ("FCT", "atlas"), ("BT", "b482"), ("BT", "rswmt"))
        for station, expected_platform in scenarios:
            with self.subTest(station=station, platform=expected_platform):
                app = object.__new__(B518LogSolutionApp)
                app.root = MagicMock()
                app.events = queue.Queue()
                app.rounds = RoundCoordinator(app.events.put)
                app.active_round_id = None
                install_test_profile(app, station, expected_platform)
                app.start_button = MagicMock()
                app.monitor_state = MagicMock()
                app.event_lines = []
                app.settings_log = None
                app._save_preferences = MagicMock()
                app._reset_rows = MagicMock()
                app._set_monitor_controls = MagicMock()
                with patch("b518_log_solution.DEFAULT_PLATFORM_REGISTRY.create_monitor") as factory:
                    app.start_monitor()
                    self.wait_for(lambda: factory.called)
                    preparation_deadline = time.monotonic() + 8
                    while (not factory.return_value.start.called and
                           app.rounds.snapshot().completion_reason != "start_failed" and
                           time.monotonic() < preparation_deadline):
                        time.sleep(0.01)

                snapshot = app.rounds.snapshot()
                self.assertTrue(factory.return_value.start.called,
                                "monitor preparation did not start: {}".format(snapshot))
                self.assertEqual(snapshot.station, station)
                self.assertEqual(snapshot.state, "RUNNING")
                factory.assert_called_once()
                self.assertEqual(factory.call_args.args[0], expected_platform)
                factory.return_value.start.assert_called_once()
                app.rounds.stop()

    def test_repeated_app_start_keeps_the_round_and_does_not_reset_rows(self):
        app = object.__new__(B518LogSolutionApp)
        app.root = MagicMock()
        app.events = queue.Queue()
        app.rounds = RoundCoordinator(app.events.put)
        app.active_round_id = None
        install_test_profile(app, "DFU", "atlas")
        app.start_button = MagicMock()
        app.monitor_state = MagicMock()
        app.event_lines = []
        app.settings_log = None
        app._save_preferences = MagicMock()
        app._reset_rows = MagicMock()
        app._set_monitor_controls = MagicMock()
        with patch("b518_log_solution.DEFAULT_PLATFORM_REGISTRY.create_monitor") as factory:
            app.start_monitor()
            first_round_id = app.active_round_id
            self.wait_for(lambda: factory.called)
            app.start_monitor()
            self.wait_for(lambda: factory.return_value.start.called)

        self.assertEqual(app.active_round_id, first_round_id)
        self.assertEqual(app.rounds.snapshot().state, "RUNNING")
        factory.assert_called_once()
        factory.return_value.start.assert_called_once()
        app._reset_rows.assert_called_once()
        app.rounds.stop()

    def test_queued_prior_round_event_cannot_change_the_new_round_ui(self):
        app = object.__new__(B518LogSolutionApp)
        app.root = MagicMock()
        app.events = queue.Queue()
        app.rounds = RoundCoordinator(app.events.put)
        app.active_round_id = None
        install_test_profile(app, "DFU", "atlas")
        app.start_button = MagicMock()
        app.monitor_state = MagicMock()
        app.event_lines = []
        app.settings_log = None
        app._save_preferences = MagicMock()
        app._reset_rows = MagicMock()
        app._set_monitor_controls = MagicMock()
        app._set_row = MagicMock()
        with patch("b518_log_solution.DEFAULT_PLATFORM_REGISTRY.create_monitor") as factory:
            app.start_monitor()
            old_round_id = app.active_round_id
            self.wait_for(lambda: factory.called)
            app.rounds.stop()
            app.start_monitor()
            new_round_id = app.active_round_id
            self.wait_for(lambda: factory.call_count == 2)
            before = app.rounds.snapshot()
            messages_before_stale_event = list(app.event_lines)
            app._handle_event(RoundEvent(old_round_id, 99, MonitorEvent(
                "result", "stale PASS", 1, "TESTSERIAL0001", "PASS")))

        after = app.rounds.snapshot()
        self.assertNotEqual(old_round_id, new_round_id)
        self.assertEqual(after.results, before.results)
        self.assertEqual(after.result_available, before.result_available)
        self.assertEqual(app.event_lines, messages_before_stale_event)
        app._set_row.assert_not_called()
        self.assertEqual(factory.call_count, 2)
        app.rounds.stop()

    def test_final_result_brings_dashboard_to_front_without_permanent_topmost(self):
        app = object.__new__(B518LogSolutionApp)
        app.root = MagicMock()
        install_snapshot_results(app, (SimpleNamespace(slot=1, sn="SN123", status="PASS"),))
        app.event_lines = []
        app.settings_log = None
        app._set_row = MagicMock()
        app._set_monitor_controls = MagicMock()

        app._handle_event(MonitorEvent("result", "slot1 PASS", 1, "SN123", "PASS"))

        app._set_row.assert_called_once_with(1, "SN123", "PASS")
        app.root.attributes.assert_not_called()
        app.root.deiconify.assert_called_once()
        app.root.lift.assert_called_once()
        app.root.focus_force.assert_called_once()

    def test_timeout_event_returns_dashboard_to_timeout_stopped_state(self):
        app = object.__new__(B518LogSolutionApp)
        app.root = MagicMock()
        install_snapshot_results(app, (SimpleNamespace(slot=1, sn="SN123", status="TIMEOUT"),))
        app.event_lines = []
        app.settings_log = None
        app._set_row = MagicMock()
        app._set_monitor_controls = MagicMock()

        app._handle_event(MonitorEvent("timeout", "FCT 尚未開始測試逾時", status="TIMEOUT",
                                       detail={"kind": "start"}))

        app._set_row.assert_not_called()
        app._set_monitor_controls.assert_called_once_with(False, "逾時停止")

    def test_test_timeout_keeps_monitoring_other_slots(self):
        app = object.__new__(B518LogSolutionApp)
        app.root = MagicMock()
        install_snapshot_results(app, (SimpleNamespace(slot=2, sn="SN123", status="TIMEOUT"),))
        app.event_lines = []
        app.settings_log = None
        app._set_row = MagicMock()
        app._set_monitor_controls = MagicMock()

        app._handle_event(MonitorEvent("timeout", "FCT slot2 測試逾時", 2, status="TIMEOUT",
                                       detail={"kind": "test"}))

        app._set_row.assert_called_once_with(2, "SN123", "TIMEOUT")
        app._set_monitor_controls.assert_not_called()

    def test_stopped_event_does_not_change_window_topmost_attribute(self):
        app = object.__new__(B518LogSolutionApp)
        app.root = MagicMock()
        app.event_lines = []
        app.settings_log = None
        app._set_monitor_controls = MagicMock()

        app._handle_event(MonitorEvent("stopped", "monitor ended"))

        app.root.attributes.assert_not_called()
        app._set_monitor_controls.assert_called_once_with(False)

    def test_close_waits_responsively_and_cancellation_invalidates_old_completion(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.withdraw()
            session_root = Path(temporary) / "sessions"
            app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey, session_root=session_root)
            rounds = RoundCoordinator(app.events.put, audit_root=session_root)
            app.rounds = rounds
            monitor_holder = {}

            class Monitor:
                def __init__(self, callback):
                    self.callback = callback
                    self.session = SessionStore("close-round", {}, session_root)
                    self.results = (SlotResult(1),)
                    self.start_count = 0

                def round_results(self):
                    return self.results

                def timeout_seconds(self, kind):
                    return {"start": 30, "test": 60, "round": 10}[kind]

                def update_round_settings(self, settings):
                    self.session.update_settings(settings)

                def publish_round_event(self, event):
                    self.session.enqueue_event(event.message, event.detail)
                    self.callback(event)

                def start(self):
                    self.start_count += 1

                def stop_collection(self):
                    pass

                def finish(self):
                    self.session.enqueue_finish()

                def stop(self):
                    self.callback(MonitorEvent("stopped", "stopped"))

                def poll_once(self):
                    pass

            def create(callback):
                monitor = Monitor(callback)
                monitor_holder["monitor"] = monitor
                return monitor

            def root_is_alive():
                try:
                    return bool(root.winfo_exists())
                except tk.TclError:
                    return False

            entered = threading.Event()
            release = threading.Event()
            original_write = audit_records.os.write
            blocked = [False]

            def hold_collection_stop(descriptor, content):
                if b"collection_stopped" in content and not blocked[0]:
                    blocked[0] = True
                    entered.set()
                    release.wait(8)
                return original_write(descriptor, content)

            try:
                started = rounds.start("FCT", create, run_async=False, capacity=1)
                app.active_round_id = started.round_id
                with patch.object(audit_records.os, "write", side_effect=hold_collection_stop):
                    app.close()
                    self.assertTrue(entered.wait(2))
                    ticks = []
                    root.after(0, lambda: ticks.append("responsive"))
                    deadline = time.monotonic() + 2.2
                    while time.monotonic() < deadline:
                        root.update()
                        time.sleep(0.01)
                    self.assertTrue(root.winfo_exists())
                    self.assertIn("responsive", ticks)
                    self.assertTrue(app._close_window.winfo_exists())

                    app.cancel_close()
                    self.assertFalse(app.hotkey.closed)
                    release.set()
                    self.wait_for(lambda: rounds.round_snapshot(started.round_id).save_state == "complete")
                    self.assertEqual(monitor_holder["monitor"].start_count, 1)
                    self.assertTrue(root.winfo_exists())

                app.close()
                self.wait_for(lambda: rounds.close_status().status == "complete")
                deadline = time.monotonic() + 2
                while root_is_alive() and time.monotonic() < deadline:
                    root.update()
                self.assertFalse(root_is_alive())
                self.assertTrue(app.hotkey.closed)
                rebuilt = read_round_audit(monitor_holder["monitor"].session.path / "audit.jsonl")
                self.assertTrue(rebuilt["audit_complete"])
                self.assertTrue(any(event["kind"] == "collection_stopped"
                                    for event in rebuilt["events"]))
            finally:
                release.set()
                if root_is_alive():
                    app.hotkey.close()
                    root.destroy()

    def test_close_failure_keeps_window_open_and_real_retry_rebuilds_complete_audit(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.withdraw()
            session_root = Path(temporary) / "sessions"
            app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey, session_root=session_root)
            rounds = RoundCoordinator(app.events.put, audit_root=session_root)
            app.rounds = rounds
            monitors = []

            class Monitor:
                def __init__(self, callback):
                    self.callback = callback
                    self.session = SessionStore("failed-close-round-{}".format(len(monitors)),
                                                {}, session_root)
                    self.results = (SlotResult(1),)

                def round_results(self):
                    return self.results

                def timeout_seconds(self, kind):
                    return {"start": 30, "test": 60, "round": 10}[kind]

                def update_round_settings(self, settings):
                    self.session.update_settings(settings)

                def publish_round_event(self, event):
                    self.session.enqueue_event(event.message, event.detail)
                    self.callback(event)

                def start(self):
                    pass

                def stop_collection(self):
                    pass

                def finish(self):
                    self.session.enqueue_finish()

                def stop(self):
                    self.callback(MonitorEvent("stopped", "stopped"))

                def poll_once(self):
                    pass

            def create(callback):
                monitor = Monitor(callback)
                monitors.append(monitor)
                return monitor

            original_write = audit_records.os.write
            fault_enabled = [True]
            retry_blocked = [False]
            retry_entered = threading.Event()
            release_retry = threading.Event()

            def persistent_fault(descriptor, content):
                if fault_enabled[0] and b"collection_stopped" in content:
                    if retry_blocked[0]:
                        retry_entered.set()
                        release_retry.wait(4)
                    raise OSError("persistent close audit fault")
                return original_write(descriptor, content)

            def pump_until(predicate, timeout=4):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    try:
                        root.update()
                    except tk.TclError:
                        if predicate():
                            return
                        raise
                    if predicate():
                        return
                    time.sleep(0.01)
                self.fail("Timed out while pumping the Tk close dialog")

            def root_is_alive():
                try:
                    return bool(root.winfo_exists())
                except tk.TclError:
                    return False

            try:
                previous = rounds.start("FCT", create, run_async=False, capacity=1)
                with patch.object(audit_records.os, "write", side_effect=persistent_fault):
                    rounds.stop()
                    pump_until(lambda: rounds.round_snapshot(previous.round_id).save_state == "failed")
                    current = rounds.start("FCT", create, run_async=False, capacity=1)
                    self.assertNotEqual(previous.round_id, current.round_id)
                    app.active_round_id = current.round_id
                    app.close()
                    pump_until(lambda: rounds.close_status().status == "failed" and
                               str(app._close_retry_button["state"]) == "normal")
                    self.assertFalse(rounds.round_snapshot(previous.round_id).audit_complete)
                    self.assertFalse(rounds.round_snapshot(current.round_id).audit_complete)
                    self.assertTrue(root_is_alive())
                    self.assertEqual(str(app._close_retry_button["state"]), "normal")
                    self.assertIn("persistent close audit fault", app._close_error_label.cget("text"))

                    failed_generation = rounds.close_status().generation
                    retry_blocked[0] = True
                    app._close_retry_button.invoke()
                    app._close_retry_button.invoke()
                    pump_until(lambda: rounds.close_status().status == "saving" and
                               rounds.close_status().generation > failed_generation and
                               retry_entered.is_set())
                    app.cancel_close()
                    release_retry.set()
                    cancelled_generation = rounds.close_status().generation
                    self.assertEqual(rounds.close_status().status, "cancelled")
                    self.assertFalse(app.hotkey.closed)
                    self.assertTrue(root_is_alive())
                    pump_until(lambda: all(not rounds.round_snapshot(round_id).retry_in_progress
                                           for round_id in (previous.round_id, current.round_id)))
                    app.close()
                    pump_until(lambda: rounds.close_status().status == "failed" and
                               rounds.close_status().generation > cancelled_generation and
                               str(app._close_retry_button["state"]) == "normal")
                    self.assertTrue(root_is_alive())
                    ui_tick = []
                    root.after(0, lambda: ui_tick.append(True))
                    root.update()
                    self.assertEqual(ui_tick, [True])
                    fault_enabled[0] = False

                app._close_retry_button.invoke()
                pump_until(lambda: rounds.close_status().status == "complete")
                pump_until(lambda: not root_is_alive())
                for round_id, monitor in zip((previous.round_id, current.round_id), monitors):
                    rebuilt = read_round_audit(monitor.session.path / "audit.jsonl")
                    self.assertTrue(rebuilt["audit_complete"])
                    self.assertEqual([event["kind"] for event in rebuilt["events"]].count(
                        "collection_stopped"), 1)
                    self.assertTrue(any(event["kind"] == "save_recovered"
                                        for event in rebuilt["events"]))
                    self.assertTrue(all(event["detail"].get("round_id", round_id) == round_id
                                        for event in rebuilt["events"]))
            finally:
                if root_is_alive():
                    app.hotkey.close()
                    root.destroy()

    def test_real_tk_close_waits_for_source_preparation_before_destroy(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.withdraw()
            session_root = Path(temporary) / "sessions"
            app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey, session_root=session_root)
            rounds = RoundCoordinator(app.events.put, audit_root=session_root)
            app.rounds = rounds
            preparation_entered = threading.Event()
            release_preparation = threading.Event()
            stopped = threading.Event()
            monitor_holder = {}

            class Monitor:
                def __init__(self, callback):
                    self.callback = callback
                    self.session = SessionStore("preparing-close-round", {}, session_root)
                    self.results = (SlotResult(1),)

                def round_results(self):
                    return self.results

                def timeout_seconds(self, kind):
                    return {"start": 30, "test": 60, "round": 10}[kind]

                def update_round_settings(self, settings):
                    self.session.update_settings(settings)

                def publish_round_event(self, event):
                    self.session.enqueue_event(event.message, event.detail)
                    self.callback(event)

                def start(self):
                    self.callback(MonitorEvent("round_ready", "ready"))

                def stop_collection(self):
                    pass

                def finish(self):
                    self.session.enqueue_finish()

                def stop(self):
                    stopped.set()
                    self.callback(MonitorEvent("stopped", "stopped"))

                def poll_once(self):
                    pass

            def create(callback):
                preparation_entered.set()
                if not release_preparation.wait(5):
                    raise RuntimeError("test did not release source preparation")
                monitor = Monitor(callback)
                monitor_holder["monitor"] = monitor
                return monitor

            def pump_until(predicate, timeout=5):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    try:
                        root.update()
                    except tk.TclError:
                        if predicate():
                            return
                        raise
                    if predicate():
                        return
                    time.sleep(0.01)
                self.fail("Timed out while pumping the Tk preparation/close flow")

            def root_is_alive():
                try:
                    return bool(root.winfo_exists())
                except tk.TclError:
                    return False

            try:
                started = rounds.start("FCT", create, run_async=True, capacity=1)
                app.active_round_id = started.round_id
                self.assertTrue(preparation_entered.wait(2))
                app.close()
                ticks = []
                root.after(0, lambda: ticks.append("responsive"))
                pump_until(lambda: rounds.close_status().status == "waiting")
                self.assertIn("responsive", ticks)
                self.assertTrue(root_is_alive())
                self.assertTrue(app._close_window.winfo_exists())
                self.assertNotIn("monitor", monitor_holder)

                release_preparation.set()
                pump_until(lambda: rounds.close_status().status == "complete")
                pump_until(lambda: not root_is_alive())
                self.assertTrue(stopped.is_set())
                monitor = monitor_holder["monitor"]
                rebuilt = read_round_audit(monitor.session.path / "audit.jsonl")
                self.assertTrue(rebuilt["audit_complete"])
                self.assertEqual([event["kind"] for event in rebuilt["events"]].count(
                    "collection_stopped"), 1)
                self.assertTrue(app.hotkey.closed)
            finally:
                release_preparation.set()
                if root_is_alive():
                    app.hotkey.close()
                    root.destroy()

    def test_real_tk_close_keeps_conflict_and_alarm_actions_available(self):
        with TemporaryDirectory() as temporary, \
                patch("b518_log_solution.PREFS_PATH", Path(temporary) / "preferences.json"):
            root = tk.Tk()
            root.withdraw()
            session_root = Path(temporary) / "sessions"
            app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey, session_root=session_root)
            elapsed = [0.0]
            rounds = RoundCoordinator(app.events.put, monotonic=lambda: elapsed[0],
                                      audit_root=session_root)
            app.rounds = rounds
            holder = {}

            class Monitor:
                def __init__(self, callback):
                    self.callback = callback
                    self.session = SessionStore("operator-close-round", {}, session_root)
                    self.results = (SlotResult(1), SlotResult(2))

                def round_results(self):
                    return self.results

                def timeout_seconds(self, kind):
                    return {"start": 30, "test": 60, "round": 1}[kind]

                def update_round_settings(self, settings):
                    self.session.update_settings(settings)

                def publish_round_event(self, event):
                    self.session.enqueue_event(event.message, event.detail)
                    self.callback(event)

                def start(self):
                    pass

                def stop_collection(self):
                    pass

                def finish(self):
                    self.session.enqueue_finish()

                def stop(self):
                    self.callback(MonitorEvent("stopped", "stopped"))

                def poll_once(self):
                    pass

                def apply_round_result(self, slot, status, sn="", source="", detail=None,
                                       lock_terminal=False):
                    result = self.results[slot - 1]
                    result.sn = sn or result.sn
                    result.status = status
                    result.source = source or result.source
                    self.session.enqueue_results(self.results)
                    self.publish_round_event(MonitorEvent(
                        "result", "slot{} {}".format(slot, status), slot=slot, sn=result.sn,
                        status=status, source=source, detail=detail or {},
                    ))

                def set_result(self, slot, status, detail=None, lock_terminal=False):
                    self.apply_round_result(slot, status, detail=detail, lock_terminal=lock_terminal)

            def create(callback):
                holder["monitor"] = Monitor(callback)
                return holder["monitor"]

            def pump_until(predicate, timeout=5):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    try:
                        root.update()
                    except tk.TclError:
                        if predicate():
                            return
                        raise
                    if predicate():
                        return
                    time.sleep(0.01)
                self.fail("Timed out while pumping the Tk operator/close flow")

            def root_is_alive():
                try:
                    return bool(root.winfo_exists())
                except tk.TclError:
                    return False

            try:
                started = rounds.start("FCT", create, run_async=False,
                                       round_timeout_seconds=1, capacity=2)
                app.active_round_id = started.round_id
                monitor = holder["monitor"]
                evidence = {"round_evidence_id": "fct:1:run-a",
                            "source_time": "2026-10-07T10:00:00", "source_id": "active.csv"}
                monitor.apply_round_result(1, "PASS", "SERIAL000001", "active.csv", evidence)
                candidate = MonitorEvent(
                    "result_candidate", "conflicting final result", slot=1, sn="SERIAL000001",
                    status="FAIL", source="final.csv",
                    detail=dict(evidence, source_id="final.csv"),
                )
                self.assertEqual(monitor.callback(candidate), "defer")
                elapsed[0] = 2.0
                expired = rounds.poll_once()
                self.assertEqual(len(expired.pending_conflicts), 1)
                self.assertIsNotNone(expired.round_alarm)
                pump_until(lambda: app.conflict_window and app.conflict_window.winfo_exists() and
                           app.round_alarm_window and app.round_alarm_window.winfo_exists())

                app.close()
                pump_until(lambda: rounds.close_status().status == "waiting")
                self.assertTrue(root_is_alive())
                self.assertEqual(str(app.resolve_conflict_original_button["state"]), "normal")
                self.assertEqual(str(app.round_alarm_ack_button["state"]), "normal")

                app.conflict_list.selection_set(0)
                app.resolve_conflict_original_button.invoke()
                self.assertEqual(len(rounds.round_snapshot(started.round_id).pending_conflicts), 0)
                self.assertEqual(rounds.close_status().status, "waiting")
                app.round_alarm_ack_button.invoke()
                pump_until(lambda: rounds.close_status().status == "complete")
                pump_until(lambda: not root_is_alive())

                rebuilt = read_round_audit(monitor.session.path / "audit.jsonl")
                kinds = [event["kind"] for event in rebuilt["events"]]
                self.assertTrue(rebuilt["audit_complete"])
                self.assertEqual(kinds.count("conflict_resolved"), 1)
                self.assertEqual(kinds.count("round_alarm_acknowledged"), 1)
                self.assertTrue(all(event["detail"].get("round_id", started.round_id) ==
                                    started.round_id for event in rebuilt["events"]))
            finally:
                if root_is_alive():
                    app.hotkey.close()
                    root.destroy()


if __name__ == "__main__":
    unittest.main()
