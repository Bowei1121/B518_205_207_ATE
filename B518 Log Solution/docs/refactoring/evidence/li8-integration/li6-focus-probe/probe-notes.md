# LI6 minimize/restore focus probe

This was one authorized Aqua desktop run of the unmodified candidate product path with temporary test instrumentation. The temporary instrumentation has been removed from `tests/test_li6_foreground.py`; only this probe record and raw output remain.

## Result

The proposed hypothesis that the queue captured a real prior key window and the 250 ms callback later saw `current_key=None` is disproved for this run:

- At `_queue_foreground_raise` entry for `li6-restored-round`, `NSApplication.keyWindow()` was already `None`; `_pending_foreground_key_window` was `None` before and after the queue operation.
- The queue captured `NSWorkspace.frontmostApplication()` as `loginwindow`, PID 184.
- Before and after the deferred `_finish_native_restore` callback, `keyWindow()` remained `None`. The callback argument `previous_key_window` remained `None`, and `previous_app` remained `loginwindow` PID 184.
- At the deferred callback, the Log window was visible and not miniaturized; `LI6 Other Local Window` was visible; neither native window was key or main. Tk focus was `.` before and after the callback.
- The unchanged test still fails its final `minimize-restore` assertion with `focus_get='.'`, `keyWindow=None`.

The test process starts with no native key window even though its Tk `Entry` can report focus and earlier window-order/focus assertions run. With no captured prior key window and no active parent application, calling AppKit's `makeKeyWindow` on an inferred target would invent ownership and can steal focus. No production change was made. Revalidation requires an Aqua session in which the test's other application window is actually the native key window when the round event queues.

The complete temporary `[DEBUG-li8-focus]` output is in `debug-run.log`. The logging hooks and imports were removed after collecting it.
