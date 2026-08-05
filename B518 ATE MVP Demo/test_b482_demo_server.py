import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path

from atlas_agent import discover_bt_csv_results, parse_bt_result_csv
from b482_demo_server import Simulator


class B482DemoServerTests(unittest.TestCase):
    def wait_for_completion(self, simulator, batch):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            state = simulator.status(batch)
            if "TESTING" not in state["status"].values():
                return state
            time.sleep(.01)
        self.fail("模擬測試未在預期時間內完成")

    def test_bt_writes_physical_testdata_csv_for_sparse_slots(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            simulator = Simulator(root, duration_seconds=0)
            state = simulator.start({
                "station": "BT",
                "assignments": [{"slot": 1, "sn": "BTDEMO001"}, {"slot": 3, "sn": "BTDEMO003"},
                                {"slot": 4, "sn": "BTDEMO004"}],
                "fail_last": True,
            })
            self.wait_for_completion(simulator, state["batch"])
            paths = sorted(root.glob("*/*/*.csv"))
            self.assertEqual([path.parent.name for path in paths], ["FAILED", "PASSED", "PASSED"])
            results, errors = discover_bt_csv_results(root, [1, 3, 4], datetime.now())
            self.assertEqual(errors, [])
            self.assertEqual({slot: (item.sn, item.status) for slot, item in results.items()}, {
                1: ("BTDEMO001", "PASS"), 3: ("BTDEMO003", "PASS"), 4: ("BTDEMO004", "FAIL"),
            })
            self.assertEqual(parse_bt_result_csv(paths[0]).slot, 4)

    def test_bt_rejects_missing_duplicate_or_invalid_assignments(self):
        with tempfile.TemporaryDirectory() as directory:
            simulator = Simulator(Path(directory), duration_seconds=0)
            with self.assertRaises(ValueError):
                simulator.start({"station": "BT", "sns": ["BTDEMO001"]})
            with self.assertRaises(ValueError):
                simulator.start({"station": "BT", "assignments": [{"slot": 1, "sn": "A"}, {"slot": 1, "sn": "B"}]})
            with self.assertRaises(ValueError):
                simulator.start({"station": "BT", "assignments": [{"slot": 5, "sn": "A"}]})

    def test_fct_keeps_atlas_records_layout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            simulator = Simulator(root, duration_seconds=0)
            state = simulator.start({"station": "FCT", "sns": ["FCTDEMO001"]})
            self.wait_for_completion(simulator, state["batch"])
            self.assertEqual(len(list(root.glob("FCTDEMO001/*/system/records.csv"))), 1)
            self.assertEqual(list(root.glob("*/*/*.csv")), [])


if __name__ == "__main__":
    unittest.main()
