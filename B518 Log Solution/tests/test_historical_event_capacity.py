import hashlib
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from historical_event_display import iter_historical_event_sources
from historical_event_query import HistoricalEventDateRange, query_historical_events
from historical_event_capacity import generate_fixture, _run_sample_process


class HistoricalEventCapacityFixtureTests(unittest.TestCase):
    def test_mixed_fixture_matches_official_readers_and_public_query(self):
        with tempfile.TemporaryDirectory(prefix="b518-capacity-contract-") as temporary:
            root = Path(temporary)
            as_of = date(2026, 10, 14)
            manifest = generate_fixture(root, 603, as_of)

            self.assertEqual(manifest["event_count"], 603)
            self.assertEqual(manifest["source_event_counts"], {
                "round_audit": 570, "legacy_events_log": 30, "app_journal": 3})
            sources = tuple(iter_historical_event_sources(
                Path(manifest["sessions_path"]), Path(manifest["app_event_path"])))
            self.assertEqual(len(sources), manifest["source_count"])
            self.assertEqual({source.kind for source in sources}, {
                "round-audit", "legacy", "app"})

            start = as_of - timedelta(days=89)
            date_range = HistoricalEventDateRange(start, as_of)
            index_path = root / "query-index.sqlite3"
            result = query_historical_events(
                Path(manifest["sessions_path"]), Path(manifest["app_event_path"]),
                date_range, index_path=index_path)
            try:
                self.assertEqual(result.total_count,
                                 manifest["expected_in_range_event_count"])
                keys = []
                for page_number in range(1, result.page_count + 1):
                    page = result.get_page(page_number)
                    self.assertLessEqual(len(page.events), 100)
                    keys.extend(event.key for event in page.events)
                self.assertEqual(len(keys), len(set(keys)))
                self.assertEqual(len(keys), result.total_count)
                self.assertEqual(result.index_metrics.parsed_source_count,
                                 manifest["source_count"])
                self.assertEqual(result.index_metrics.reused_source_count, 0)
            finally:
                result.close()

            for relative_path, expected_digest in manifest["source_sha256"].items():
                path = root / relative_path
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                                 expected_digest)

    def test_isolated_public_service_sample_measures_reuse_and_degradation(self):
        with tempfile.TemporaryDirectory(prefix="b518-capacity-sample-") as temporary:
            root = Path(temporary)
            fixture = root / "fixture"
            manifest = generate_fixture(fixture, 603, date(2026, 10, 14))
            script = Path(__file__).resolve().parents[1] / "scripts" / \
                "historical_event_capacity.py"
            index_path = root / "query-index.sqlite3"
            initial = _run_sample_process(
                script, fixture, index_path, "initial", 1, "full", 60)
            self.assertEqual(initial["total_count"],
                             manifest["expected_in_range_event_count"])
            self.assertEqual(initial["parsed_source_count"], manifest["source_count"])
            self.assertFalse(initial["index_degraded"])

            reused = _run_sample_process(
                script, fixture, index_path, "reuse", 1, "full", 60)
            self.assertEqual(reused["identity_sha256"], initial["identity_sha256"])
            self.assertEqual(reused["parsed_source_count"], 0)
            self.assertEqual(reused["reused_source_count"], manifest["source_count"])
            self.assertTrue(reused["snapshot_removed"])

            index_path.write_bytes(b"controlled corrupt index")
            degraded = _run_sample_process(
                script, fixture, index_path, "degraded", 1, "full", 60)
            self.assertTrue(degraded["index_degraded"])
            self.assertEqual(degraded["identity_sha256"], initial["identity_sha256"])
            self.assertEqual(degraded["parsed_source_count"], manifest["source_count"])
            self.assertTrue(degraded["snapshot_removed"])


if __name__ == "__main__":
    unittest.main()
