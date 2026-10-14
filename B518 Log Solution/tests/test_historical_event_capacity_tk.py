"""Optional true-Tk App acceptance for a prepared H8 capacity fixture."""

import hashlib
import json
import os
import shutil
import tempfile
import threading
import time
import tkinter as tk
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from b518_log_solution import B518LogSolutionApp
from historical_event_query import HistoricalEventDateRange, query_historical_events
from monitoring_round import RoundCoordinator


class _CapacityHotkey:
    available = True
    message = "available"

    def __init__(self, callback):
        self.callback = callback

    def close(self):
        pass


@unittest.skipUnless(
    os.environ.get("B518_TK_TESTS") == "1" and
    os.environ.get("B518_H8_CAPACITY_ROOT"),
    "requires B518_TK_TESTS=1 and a prepared H8 capacity fixture")
class HistoricalEventCapacityTkTests(unittest.TestCase):
    @staticmethod
    def _widget_exists(widget):
        if widget is None:
            return False
        try:
            return bool(widget.winfo_exists())
        except tk.TclError:
            return False

    def _pump_until(self, root, predicate, timeout, reason):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                root.update()
            except tk.TclError:
                break
            if predicate():
                return
            time.sleep(0.005)
        self.fail("timed out waiting for {}".format(reason))

    @staticmethod
    def _click_widget(root, widget):
        root.update_idletasks()
        widget.event_generate(
            "<ButtonPress-1>", x=max(2, widget.winfo_width() // 2),
            y=max(2, widget.winfo_height() // 2))
        widget.event_generate(
            "<ButtonRelease-1>", x=max(2, widget.winfo_width() // 2),
            y=max(2, widget.winfo_height() // 2))
        root.update()

    def test_real_app_query_remains_responsive_and_matches_disk_baseline(self):
        fixture_root = Path(os.environ["B518_H8_CAPACITY_ROOT"]).resolve()
        manifest = json.loads(
            (fixture_root / "fixture-manifest.json").read_text(encoding="utf-8"))
        self.assertIn(manifest["event_count"], (50000, 2160000),
                      "Tk capacity acceptance requires a specified H8 fixture size")
        query_range = HistoricalEventDateRange(
            date.fromisoformat(manifest["range_start"]),
            date.fromisoformat(manifest["range_end"]))
        heartbeat_times = []
        heartbeat_id = None
        gate_entered = threading.Event()
        gate_release = threading.Event()
        baseline_cancelled = threading.Event()
        baseline_worker = None
        app = None
        root = None
        app_root = None
        report = {"fixture_event_count": manifest["event_count"],
                  "fixture_source_count": manifest["source_count"],
                  "range_start": manifest["range_start"],
                  "range_end": manifest["range_end"],
                  "tk_runtime": {}}

        with tempfile.TemporaryDirectory(prefix="b518-h8-capacity-tk-") as temporary:
            app_root = Path(temporary)
            session_root = app_root / "sessions"
            shutil.copytree(fixture_root / "sessions", session_root)
            app_event_path = app_root / "app-events.json"
            shutil.copy2(fixture_root / "app-events.json", app_event_path)
            source_paths = [app_root / relative_path
                            for relative_path in manifest["source_sha256"]]
            try:
                root = tk.Tk()
                root.deiconify()
                report["tk_runtime"] = {
                    "python_tk": tk.TkVersion,
                    "tcl_patchlevel": root.tk.call("info", "patchlevel"),
                    "windowing_system": root.tk.call("tk", "windowingsystem"),
                }
                with patch("b518_log_solution.APP_ROOT", app_root), \
                        patch("b518_log_solution.PREFS_PATH", app_root / "preferences.json"), \
                        patch.object(RoundCoordinator, "start_retention_schedule",
                                     return_value=None):
                    app = B518LogSolutionApp(
                        root, hotkey_factory=_CapacityHotkey,
                        session_root=session_root, app_event_path=app_event_path)
                    self._pump_until(root, lambda: app.app_events.status().complete,
                                     300, "App startup event persistence")

                    # Establish an independent public raw-file baseline after legitimate
                    # App startup records have been appended to the isolated journal.
                    baseline_box = {}

                    def read_public_raw_baseline():
                        baseline = query_historical_events(
                            session_root, app_event_path, query_range,
                            cancellation_event=baseline_cancelled, index_path=None)
                        try:
                            first = baseline.get_page(1)
                            middle = baseline.get_page(
                                max(1, (baseline.page_count + 1) // 2))
                            last = baseline.get_page(max(1, baseline.page_count))
                            baseline_box["count"] = baseline.total_count
                            baseline_box["page_count"] = baseline.page_count
                            baseline_box["first_page"] = len(first.events)
                            baseline_box["middle_page"] = len(middle.events)
                            baseline_box["last_page"] = len(last.events)
                            baseline_box["selected_detail"] = (
                                baseline.get_detail(first.events[0].key) is not None)
                        except BaseException as error:
                            baseline_box["error"] = error
                        finally:
                            baseline.close()

                    baseline_finished = threading.Event()

                    def run_baseline():
                        try:
                            read_public_raw_baseline()
                        finally:
                            baseline_finished.set()

                    baseline_worker = threading.Thread(
                        target=run_baseline, name="H8RawBaseline", daemon=True)
                    baseline_worker.start()
                    self._pump_until(root, baseline_finished.is_set, 7200,
                                     "public raw-file capacity baseline")
                    baseline_worker.join(timeout=1)
                    if "error" in baseline_box:
                        raise baseline_box["error"]
                    expected_count = baseline_box["count"]
                    self.assertGreater(expected_count, 100)
                    self.assertEqual(baseline_box["first_page"], 100)
                    self.assertEqual(baseline_box["middle_page"], 100)
                    self.assertLessEqual(baseline_box["last_page"], 100)
                    self.assertTrue(baseline_box["selected_detail"])
                    report["raw_file_baseline_pages"] = {
                        "page_count": baseline_box["page_count"],
                        "first": baseline_box["first_page"],
                        "middle": baseline_box["middle_page"],
                        "last": baseline_box["last_page"],
                        "selected_detail": baseline_box["selected_detail"],
                    }

                    source_hashes_before = {
                        str(path.relative_to(app_root)): hashlib.sha256(
                            path.read_bytes()).hexdigest() for path in source_paths}
                    index_path = app_root / "historical-event-query-index.sqlite3"
                    self.assertFalse(index_path.exists())
                    app.open_historical_events()
                    root.update()
                    self.assertFalse(index_path.exists(),
                                     "opening history must not start a full read")
                    for path in source_paths:
                        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                                         source_hashes_before[
                                             str(path.relative_to(app_root))])

                    app.historical_start_entry.delete(0, "end")
                    app.historical_start_entry.insert(0, query_range.start.isoformat())
                    app.historical_end_entry.delete(0, "end")
                    app.historical_end_entry.insert(0, query_range.end.isoformat())
                    app_events_before_query = app_event_path.read_bytes()

                    original_query = query_historical_events

                    def gated_real_query(sessions, event_path, date_range, **options):
                        gate_entered.set()
                        if not gate_release.wait(120):
                            raise RuntimeError("capacity Tk query gate timed out")
                        return original_query(sessions, event_path, date_range, **options)

                    last_heartbeat = [None]

                    def heartbeat():
                        now = time.monotonic()
                        if last_heartbeat[0] is not None:
                            heartbeat_times.append(now - last_heartbeat[0])
                        last_heartbeat[0] = now
                        if root.winfo_exists():
                            root.after(5, heartbeat)

                    heartbeat_id = root.after(5, heartbeat)
                    with patch("b518_log_solution.query_historical_events",
                               side_effect=gated_real_query):
                        self._click_widget(root, app.historical_event_refresh_button)
                        self._pump_until(root, gate_entered.is_set, 10,
                                         "query worker to enter controlled gate")
                        app.historical_start_entry.delete(0, "end")
                        app.historical_start_entry.insert(0, query_range.end.isoformat())
                        app.historical_end_entry.delete(0, "end")
                        app.historical_end_entry.insert(0, query_range.end.isoformat())
                        root.update()
                        report["draft_edit_during_query"] = {
                            "start": app.historical_start_var.get(),
                            "end": app.historical_end_var.get(),
                            "query_started": True,
                        }
                        gate_release.set()
                        expected_page_count = (expected_count + 99) // 100
                        self._pump_until(
                            root,
                            lambda: "Page 1 of {}".format(expected_page_count) in
                            app.historical_page_label.cget("text"),
                            7200, "2.16-million capacity query first page")

                    visible_status = app.historical_query_status.cget("text")
                    self.assertIn(str(expected_count), visible_status)
                    self.assertIn(query_range.start.isoformat(), visible_status)
                    self.assertIn(query_range.end.isoformat(), visible_status)
                    self.assertEqual(app.historical_event_list.size(), 100)
                    self.assertEqual(app.historical_start_var.get(),
                                     query_range.end.isoformat())
                    self.assertGreaterEqual(len(heartbeat_times), 3)
                    report.update({
                        "raw_file_baseline_count": expected_count,
                        "visible_first_page_rows": app.historical_event_list.size(),
                        "visible_page_label": app.historical_page_label.cget("text"),
                        "visible_query_status": visible_status,
                        "max_tk_heartbeat_gap_seconds": max(heartbeat_times),
                        "tk_heartbeat_samples": len(heartbeat_times),
                        "submitted_range_retained_while_draft_changed": True,
                        "query_index_size_bytes": index_path.stat().st_size,
                        "index_generation_metrics": {
                            "parsed_source_count":
                                app._historical_query_result.index_metrics.parsed_source_count,
                            "reused_source_count":
                                app._historical_query_result.index_metrics.reused_source_count,
                            "source_bytes_read_by_reader":
                                app._historical_query_result.index_metrics.source_bytes_read,
                        },
                    })
                    app.historical_event_list.see(0)
                    root.update()
                    detail_before_selection = app.historical_event_detail.get("1.0", "end")
                    bounds = app.historical_event_list.bbox(0)
                    self.assertIsNotNone(bounds)
                    x, y, _width, height = bounds
                    app.historical_event_list.event_generate(
                        "<ButtonPress-1>", x=max(2, x + 5),
                        y=y + max(1, height // 2))
                    app.historical_event_list.event_generate(
                        "<ButtonRelease-1>", x=max(2, x + 5),
                        y=y + max(1, height // 2))
                    self._pump_until(
                        root,
                        lambda: app.historical_event_detail.get("1.0", "end") !=
                        detail_before_selection and
                        bool(app.historical_event_detail.get("1.0", "end").strip()),
                        30, "selected first-page event detail")
                    report["selected_detail_visible"] = bool(
                        app.historical_event_detail.get("1.0", "end").strip())
                    app_event_bytes_after_query = app_event_path.read_bytes()
                    self.assertEqual(app_event_bytes_after_query, app_events_before_query)
                    hashes_after_query = {
                        str(path.relative_to(app_root)): hashlib.sha256(
                            path.read_bytes()).hexdigest() for path in source_paths}
                    self.assertEqual(hashes_after_query, source_hashes_before)
                    report["source_hashes_unchanged_during_query"] = True
                    report["app_journal_unchanged_during_query"] = True
                    report["source_hashes_before_query"] = source_hashes_before
                    report["source_hashes_after_query"] = hashes_after_query
                    report["app_journal_sha256_before_query"] = hashlib.sha256(
                        app_events_before_query).hexdigest()
                    report["app_journal_sha256_after_query"] = hashlib.sha256(
                        app_event_bytes_after_query).hexdigest()
            finally:
                gate_release.set()
                baseline_cancelled.set()
                if baseline_worker is not None:
                    baseline_worker.join(timeout=10)
                if self._widget_exists(root):
                    if heartbeat_id is not None:
                        try:
                            root.after_cancel(heartbeat_id)
                        except tk.TclError:
                            pass
                    if app is not None:
                        if app.historical_event_window and \
                                app.historical_event_window.winfo_exists():
                            app.historical_event_window.destroy()
                        app.close()
                        deadline = time.monotonic() + 300
                        while self._widget_exists(root) and time.monotonic() < deadline:
                            try:
                                root.update()
                            except tk.TclError:
                                break
                            time.sleep(0.01)
                        if self._widget_exists(root):
                            app.app_events.stop()
                            root.destroy()
                    else:
                        root.destroy()
                    if app is not None:
                        report["app_close_status"] = app.rounds.close_status().status
                        report["app_event_store_complete"] = app.app_events.status().complete
                        report["tk_root_destroyed"] = not self._widget_exists(root)
                evidence_path = os.environ.get("B518_H8_TK_EVIDENCE")
                if evidence_path:
                    Path(evidence_path).write_text(
                        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
        self.assertEqual(report.get("app_close_status"), "complete")
        self.assertTrue(report.get("app_event_store_complete"))
        self.assertTrue(report.get("tk_root_destroyed"))


if __name__ == "__main__":
    unittest.main()
