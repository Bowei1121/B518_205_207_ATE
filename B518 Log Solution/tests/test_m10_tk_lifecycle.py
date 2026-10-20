"""Real source/App acceptance must release Tk before later worker collection."""
import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path


@unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1", "requires desktop Tk")
class M10TkLifecycleTests(unittest.TestCase):
    def test_global_hint_cleanup_releases_root_owned_commands(self):
        import tkinter as tk
        from tkinter import ttk
        from b518_log_solution import _LocalizedControlHint

        for destroy_widget in (False, True):
            with self.subTest(destroy_widget=destroy_widget):
                root = tk.Tk()
                errors = []
                root.report_callback_exception = lambda *args: errors.append(args)
                first = ttk.Button(root)
                second = ttk.Button(root)
                hint = _LocalizedControlHint(first, lambda: "first")
                peer = _LocalizedControlHint(second, lambda: "second")
                command = hint._global_motion_binding
                pointer_poll = hint._pointer_poll_id
                peer_command = peer._global_motion_binding
                try:
                    self.assertIn(command, root._tclCommands)
                    if destroy_widget:
                        first.destroy()
                    else:
                        hint.close()
                    self.assertNotIn(command, root._tclCommands)
                    if pointer_poll is not None:
                        self.assertNotIn(pointer_poll, root.tk.call("after", "info"))
                    self.assertFalse(root.tk.call("info", "commands", command))
                    self.assertIn(peer_command, root._tclCommands)
                    self.assertIn(peer_command, root.bind_all("<Motion>"))
                    self.assertEqual(errors, [])
                finally:
                    peer.close()
                    root.destroy()

    def test_destroyed_locator_releases_widget_graph_without_collection(self):
        import gc
        import tkinter as tk
        import weakref
        from b518_log_solution import B518LogSolutionApp

        enabled = gc.isenabled()
        gc.disable()
        try:
            root = tk.Tk()
            locator = B518LogSolutionApp._build_kvm_locator(root, 0, 0, False)
            references = [weakref.ref(widget) for widget in
                          (root, locator, locator.winfo_children()[0])]
            root.destroy()
            del root, locator
            self.assertTrue(all(reference() is None for reference in references))
        finally:
            gc.collect()
            if enabled:
                gc.enable()

    def test_closed_source_app_scenario_releases_interpreter_before_worker_gc(self):
        # Fault-injection exceptions can keep their traceback/widget graph in a
        # cycle. A later writer's collection must never dispose of that graph
        # on its background thread. Keep native aborts inside this subprocess.
        script = textwrap.dedent("""\
            import gc, threading, tkinter as tk, unittest, weakref
            from unittest.mock import patch
            from test_m10_integration import M10SourceIntegrationTests

            gc.disable()
            roots = []
            actual_root = tk.Tk
            def create_root(*args, **kwargs):
                root = actual_root(*args, **kwargs)
                roots.append(weakref.ref(root))
                return root

            with patch('tkinter.Tk', side_effect=create_root):
                suite = unittest.TestSuite([M10SourceIntegrationTests(
                    'test_real_source_all_windows_switch_cancel_and_single_decisions')])
                result = unittest.TextTestRunner(verbosity=2).run(suite)
                assert result.wasSuccessful(), 'source/App scenario did not complete'
                del suite, result

            assert roots, 'the scenario did not construct a real Tk interpreter'
            assert all(ref() is None for ref in roots), (
                'Closed Tk interpreter survived its main-thread test cleanup')
            worker = threading.Thread(target=gc.collect)
            worker.start()
            worker.join(10)
            assert not worker.is_alive(), 'background collection hung'
        """)
        environment = dict(os.environ)
        root = Path(__file__).resolve().parents[1]
        environment["PYTHONPATH"] = os.pathsep.join(
            str(root / directory) for directory in ("src", "tests"))
        completed = subprocess.run(
            [sys.executable, "-X", "faulthandler", "-c", script],
            env=environment, capture_output=True, text=True, timeout=30)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)


if __name__ == "__main__":
    unittest.main()
