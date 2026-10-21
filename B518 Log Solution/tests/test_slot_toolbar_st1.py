"""ST1 acceptance at the real operator App/Tk boundary."""
import json
import os
import time
import tkinter as tk
from dataclasses import replace
from pathlib import Path
from tkinter import font
import unittest

from test_log_solution_ui import LogSolutionUiTests, FakeHotkey, capture_tk_window_evidence
from b518_log_solution import (
    B518LogSolutionApp, LIGHT_BACKGROUND, STATUS_COLOURS,
)


class SlotViewportTests(LogSolutionUiTests):
    # The loader below selects only this test; lifecycle stays shared with the
    # existing App acceptance harness.
    @classmethod
    def setUpClass(cls):
        cls._original_display_mode = None
        if os.environ.get("B518_ST1_LARGE_DESKTOP") == "1":
            import Quartz
            display = Quartz.CGMainDisplayID()
            cls._original_display_mode = Quartz.CGDisplayCopyDisplayMode(display)
            modes = Quartz.CGDisplayCopyAllDisplayModes(display, None)
            selected = next(mode for mode in modes
                            if Quartz.CGDisplayModeGetWidth(mode) == 1650
                            and Quartz.CGDisplayModeGetHeight(mode) == 1050)
            if Quartz.CGDisplaySetDisplayMode(display, selected, None) != 0:
                raise RuntimeError("native display mode change failed")
            time.sleep(.5)
        try:
            super().setUpClass()
        except BaseException:
            cls._restore_display()
            raise

    @classmethod
    def _restore_display(cls):
        if cls._original_display_mode is not None:
            import Quartz
            display = Quartz.CGMainDisplayID()
            mode = cls._original_display_mode
            result = Quartz.CGDisplaySetDisplayMode(display, mode, None)
            actual = Quartz.CGDisplayCopyDisplayMode(display)
            if result != 0 or (Quartz.CGDisplayModeGetWidth(actual), Quartz.CGDisplayModeGetHeight(actual)) != (Quartz.CGDisplayModeGetWidth(mode), Quartz.CGDisplayModeGetHeight(mode)):
                raise AssertionError("original display mode was not restored")
            print("Restored native display: {}x{}".format(Quartz.CGDisplayModeGetWidth(actual), Quartz.CGDisplayModeGetHeight(actual)))

    @classmethod
    def tearDownClass(cls):
        try:
            super().tearDownClass()
        finally:
            cls._restore_display()

    def test_st1_compact_rows_and_small_window_keep_all_slots_reachable(self):
        root = tk.Tk()
        app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey)
        root.deiconify()
        self.addCleanup(root.destroy)
        records = []
        for capacity in (1, 10, 11, 20):
            profile = replace(app.profiles.get("B518", "FCT"), project="ST1", capacity=capacity,
                              mapping=tuple((slot, slot) for slot in range(1, capacity + 1)))
            app.profiles = app.profiles.with_profile(profile)
            app.project_choice.configure(values=app.profiles.projects)
            app.project_choice.set("ST1")
            app.project_choice.event_generate("<<ComboboxSelected>>")
            root.update()
            root.resizable(True, True)
            root.minsize(376, 450)
            root.maxsize(376, 1400)
            for height in (1200, 650):
                root.geometry("376x{}+50+40".format(height))
                for _ in range(15):
                    root.update()
                    time.sleep(.02)
                for language in ("zh-TW", "en"):
                    app.language_menu.invoke(1 if language == "zh-TW" else 0)
                    root.update()
                    app.rows_canvas.yview_moveto(0)
                    root.update()
                    top = app.rows_canvas.winfo_rooty() + 1
                    bottom = top + app.rows_canvas.winfo_height() - 2
                    def visible(cell):
                        return cell.winfo_rooty() >= top and cell.winfo_rooty() + cell.winfo_height() <= bottom
                    count = sum(visible(row["slot"]) for row in app.status_rows.values())
                    self.assertGreaterEqual(count, 1)
                    self.assertLessEqual(count, capacity)
                    if capacity > 10 and height == 1200 and root.winfo_screenheight() >= 1050:
                        self.assertGreater(count, 10, (capacity, height, language, count))
                    self.assertEqual(font.Font(root=root, font=app.status_rows[1]["slot"].cget("font")).actual("size"), 14)
                    row = app.rows_box.winfo_children()[0]
                    self.assertEqual(row.cget("background"), "#000000")
                    self.assertGreaterEqual(
                        row.winfo_height(),
                        max(cell.winfo_reqheight() for cell in app.status_rows[1].values()),
                    )
                    for control in (app.start_button, app.stop_button, app.save_status, app.app_diagnostics_button):
                        self.assertLessEqual(control.winfo_rooty() + control.winfo_height(), root.winfo_rooty() + root.winfo_height())
                        self.assertTrue(control.winfo_ismapped())
                    self.assertTrue(app.rows_scrollbar.winfo_ismapped())
                    self.assertEqual(app.rows_canvas.cget("background"), LIGHT_BACKGROUND)
                    self.assertEqual((app.kvm_state_marker.winfo_x(), app.kvm_state_marker.winfo_y(),
                                      app.kvm_state_marker.winfo_width(), app.kvm_state_marker.winfo_height()),
                                     (250, 0, 26, 26))
                    for slot, block in app.kvm_result_blocks.items():
                        if block.winfo_ismapped():
                            self.assertEqual((block.winfo_x(), block.winfo_y(), block.winfo_width(), block.winfo_height()),
                                             (((slot - 1) % 10) * 34, 34 if slot <= 10 else 61, 34, 26))
                            if slot > capacity:
                                self.assertEqual(block.cget("background"), "#000000")
                    first = app.rows_canvas.yview()
                    width = app.rows_canvas.winfo_width()
                    # Exercise the actual scrollbar's trough/buttons, rather
                    # than merely asserting its disabled flag or style.
                    scrollbar = app.rows_scrollbar
                    arrow_clicks = 1
                    scrollbar.event_generate("<ButtonPress-1>", x=5, y=scrollbar.winfo_height() - 7)
                    scrollbar.event_generate("<ButtonRelease-1>", x=5, y=scrollbar.winfo_height() - 7)
                    root.update()
                    if count == capacity:
                        self.assertEqual(app.rows_canvas.yview(), first)
                    else:
                        self.assertGreater(app.rows_canvas.yview()[0], first[0])
                    self.assertEqual(app.rows_canvas.winfo_width(), width)
                    if count == capacity:
                        scrollbar.event_generate("<ButtonPress-1>", x=5, y=25)
                        scrollbar.event_generate("<B1-Motion>", x=5, y=scrollbar.winfo_height() - 25)
                        scrollbar.event_generate("<ButtonRelease-1>", x=5, y=scrollbar.winfo_height() - 25)
                    else:
                        for _ in range(200):
                            arrow_clicks += 1
                            scrollbar.event_generate("<ButtonPress-1>", x=5, y=scrollbar.winfo_height() - 7)
                            scrollbar.event_generate("<ButtonRelease-1>", x=5, y=scrollbar.winfo_height() - 7)
                            root.update()
                            if app.rows_canvas.yview()[1] >= 1:
                                break
                    root.update()
                    self.assertEqual(app.rows_canvas.yview()[1], 1.0)
                    self.assertTrue(visible(app.status_rows[capacity]["slot"]), (capacity, height, app.rows_canvas.yview()))
                    if count == capacity:
                        self.assertEqual(app.rows_canvas.yview(), first)
                    else:
                        self.assertGreater(app.rows_canvas.yview()[0], first[0])
                    record = capture_tk_window_evidence(root, "st1-cap{}-h{}".format(capacity, height), language, {
                        "canvas": app.rows_canvas, "scrollbar": app.rows_scrollbar,
                        "start": app.start_button, "stop": app.stop_button,
                        "last_slot": app.status_rows[capacity]["slot"], "kvm": app.kvm_results,
                        "marker": app.kvm_state_marker,
                    })
                    record.update(capacity=capacity, requested_height=height, screen_height=root.winfo_screenheight(), language=language, visible_rows=count,
                                  yview=list(app.rows_canvas.yview()), arrow_clicks=arrow_clicks,
                                  row_height=app.status_rows[1]["slot"].winfo_height(),
                                  font_requested_height=app.status_rows[1]["slot"].winfo_reqheight(),
                                  horizontal_grid_width=(
                                      app.rows_box.winfo_children()[0].winfo_height() -
                                      app.status_rows[1]["slot"].winfo_height()),
                                  vertical_grid_widths=[
                                      app.status_rows[1]["status"].winfo_x() -
                                      (app.status_rows[1]["slot"].winfo_x() +
                                       app.status_rows[1]["slot"].winfo_width()),
                                      app.status_rows[1]["sn"].winfo_x() -
                                      (app.status_rows[1]["status"].winfo_x() +
                                       app.status_rows[1]["status"].winfo_width()),
                                  ])
                    records.append(record)
        # Capacity reduction must repair a scrolled-to-end position and leave
        # the reserved scrollbar column at the same horizontal location.
        before_width = app.rows_canvas.winfo_width()
        profile = replace(profile, capacity=1, mapping=((1, 1),))
        app.profiles = app.profiles.with_profile(profile)
        app.machine_choice.event_generate("<<ComboboxSelected>>")
        root.update()
        self.assertEqual(app.rows_canvas.yview(), (0.0, 1.0))
        self.assertTrue(app.rows_scrollbar.instate(("disabled",)))
        self.assertEqual(app.rows_canvas.winfo_width(), before_width)
        self.assertTrue(app.rows_scrollbar.winfo_ismapped())
        if os.environ.get("B518_TK_EVIDENCE_DIR"):
            (Path(os.environ["B518_TK_EVIDENCE_DIR"]) / "st1-matrix.json").write_text(json.dumps(records, indent=2), encoding="utf-8")

    def test_hc2_real_app_rows_fit_font_and_black_grid_at_two_scales(self):
        root = tk.Tk()
        root.deiconify()
        app = B518LogSolutionApp(root, hotkey_factory=FakeHotkey)
        self.addCleanup(root.destroy)
        profile = replace(app.profiles.get("B518", "FCT"), project="HC2", capacity=20,
                          mapping=tuple((slot, slot) for slot in range(1, 21)))
        app.profiles = app.profiles.with_profile(profile)
        app.project_choice.configure(values=app.profiles.projects)
        app.project_choice.set("HC2")
        app.project_choice.event_generate("<<ComboboxSelected>>")
        for slot, status in enumerate(("PASS", "FAIL", "TESTING", "NOTEST"), start=1):
            app._set_row(slot, "HC2SN{:02d}".format(slot), status)
        root.resizable(True, True)
        root.minsize(376, 450)
        root.maxsize(376, 1400)
        requested_height = min(1200, root.winfo_screenheight() - 64)
        root.geometry("376x{}+50+40".format(requested_height))
        original_scaling = float(root.tk.call("tk", "scaling"))
        evidence = []
        try:
            for scaling in (1.0, 1.5):
                root.tk.call("tk", "scaling", scaling)
                for _ in range(10):
                    root.update()
                    time.sleep(.02)
                first = app.status_rows[1]
                row = app.rows_box.winfo_children()[0]
                self.assertEqual(row.cget("background"), "#000000")
                vertical_grid_widths = [
                    first["status"].winfo_x() -
                    (first["slot"].winfo_x() + first["slot"].winfo_width()),
                    first["sn"].winfo_x() -
                    (first["status"].winfo_x() + first["status"].winfo_width()),
                ]
                self.assertTrue(all(width >= 1 for width in vertical_grid_widths))
                horizontal_grid_width = row.winfo_height() - first["slot"].winfo_height()
                self.assertGreaterEqual(horizontal_grid_width, 1)
                self.assertEqual(font.Font(root=root, font=first["slot"].cget("font")).actual("size"), 14)
                for cell in first.values():
                    self.assertLessEqual(cell.winfo_reqheight(), first["slot"].winfo_height())
                for slot, status in enumerate(("PASS", "FAIL", "TESTING", "NOTEST"), start=1):
                    self.assertEqual(app.status_rows[slot]["status"].cget("text"), status)
                    self.assertEqual(app.status_rows[slot]["status"].cget("background"),
                                     STATUS_COLOURS[status])
                    self.assertEqual(app.status_rows[slot]["sn"].cget("text"),
                                     "HC2SN{:02d}".format(slot))

                top = app.rows_canvas.winfo_rooty() + 1
                bottom = top + app.rows_canvas.winfo_height() - 2
                visible = lambda cell: (cell.winfo_rooty() >= top and
                                        cell.winfo_rooty() + cell.winfo_height() <= bottom)
                visible_rows = sum(visible(item["slot"]) for item in app.status_rows.values())
                if root.winfo_screenheight() >= 1050:
                    self.assertGreater(visible_rows, 10, (scaling, visible_rows))

                app.rows_canvas.yview_moveto(1.0)
                root.update()
                self.assertTrue(visible(app.status_rows[20]["slot"]))
                if os.environ.get("B518_TK_EVIDENCE_DIR"):
                    controls = {
                        "canvas": app.rows_canvas, "scrollbar": app.rows_scrollbar,
                        "first_slot": app.status_rows[1]["slot"],
                        "last_slot": app.status_rows[20]["slot"], "kvm": app.kvm_results,
                    }
                    bottom_screenshot = capture_tk_window_evidence(
                        root, "hc2-cap20-scale-{}-bottom".format(scaling), "zh-TW", controls)
                    bottom_screenshot.update(
                        tk_scaling=scaling, last_row_fully_visible=True,
                        yview=list(app.rows_canvas.yview()))
                    app.rows_canvas.yview_moveto(0.0)
                    root.update()
                    top_screenshot = capture_tk_window_evidence(
                        root, "hc2-cap20-scale-{}-top".format(scaling), "zh-TW", controls)
                    top_screenshot.update(
                        tk_scaling=scaling,
                        row_height=first["slot"].winfo_height(),
                        font_requested_height=first["slot"].winfo_reqheight(),
                        horizontal_grid_width=horizontal_grid_width,
                        vertical_grid_widths=vertical_grid_widths, visible_rows=visible_rows,
                        statuses=["PASS", "FAIL", "TESTING", "NOTEST"],
                        yview=list(app.rows_canvas.yview()))
                    evidence.extend((top_screenshot, bottom_screenshot))
            if os.environ.get("B518_TK_EVIDENCE_DIR"):
                output = Path(os.environ["B518_TK_EVIDENCE_DIR"]) / "hc2-scaling-measurements.json"
                output.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        finally:
            root.tk.call("tk", "scaling", original_scaling)

def load_tests(loader, tests, pattern):
    return unittest.TestSuite([SlotViewportTests(
        "test_st1_compact_rows_and_small_window_keep_all_slots_reachable"),
        SlotViewportTests("test_hc2_real_app_rows_fit_font_and_black_grid_at_two_scales")])
