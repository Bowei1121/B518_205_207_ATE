"""Real source/App acceptance must release Tk before later worker collection."""
import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path


@unittest.skipUnless(os.environ.get("B518_TK_TESTS") == "1", "requires desktop Tk")
class M10TkLifecycleTests(unittest.TestCase):
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
