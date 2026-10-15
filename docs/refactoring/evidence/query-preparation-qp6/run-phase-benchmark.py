"""Run three matched samples for build, reuse, and index-recovery costs."""

import argparse
import json
import statistics
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--fixture", type=Path, required=True)
parser.add_argument("--baseline", type=Path, required=True,
                    help="fixed pre-QP1 source worktree")
parser.add_argument("--current", type=Path, required=True,
                    help="QP6 fixed-review-base source worktree")
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--timeout", type=int, default=300)
args = parser.parse_args()

fixture = args.fixture.resolve()
output = args.output.resolve()
if not fixture.is_dir() or not output.is_dir() or any(output.iterdir()):
    raise SystemExit("fixture must exist and output must be a new empty directory")
manifest = json.loads((fixture / "fixture-manifest.json").read_text(encoding="utf-8"))
end_date = date.fromisoformat(manifest["range_end"])
date_ranges = {
    "one_day_under_500": (end_date, end_date),
    "seven_days_over_500": (end_date - timedelta(days=6), end_date),
}
runner = Path(__file__).with_name("phase-benchmark.py")
measurements = []


def sample(label, source_root, mode, dates, index_path, run_number, record=True):
    command = [sys.executable, str(runner), mode, str(fixture), str(index_path),
               dates[0].isoformat(), dates[1].isoformat()]
    environment = dict(__import__("os").environ)
    environment["PYTHONPATH"] = str(source_root / "B518 Log Solution" / "src")
    completed = subprocess.run(command, check=True, capture_output=True, text=True,
                               env=environment, timeout=args.timeout)
    result = json.loads(completed.stdout)
    result.update({"implementation": label, "run_number": run_number})
    if record:
        measurements.append(result)
    return result


for range_name, dates in date_ranges.items():
    for label, source_root, mode in (
            ("fixed_base_990a3d8", args.baseline.resolve(), "staged"),
            ("current_qp6_base_990a3d8", args.current.resolve(), "staged")):
        for lifecycle in ("initial_index_build", "warm_index_reuse", "corrupt_index_recovery"):
            if lifecycle == "warm_index_reuse":
                warm_index = output / "{}-{}-warm.sqlite3".format(range_name, label)
                sample(label, source_root, mode, dates, warm_index, 0, record=False)
                indexes = [warm_index] * 3
            else:
                indexes = [output / "{}-{}-{}-{}.sqlite3".format(
                    range_name, label, lifecycle, run_number)
                    for run_number in range(1, 4)]
                if lifecycle == "corrupt_index_recovery":
                    for index_path in indexes:
                        index_path.write_text("controlled corrupt index\n", encoding="utf-8")
            for run_number, index_path in enumerate(indexes, 1):
                result = sample(label, source_root, mode, dates, index_path, run_number)
                result["range_name"] = range_name
                result["lifecycle"] = lifecycle
                if lifecycle == "corrupt_index_recovery" and label.startswith("current"):
                    if not result.get("index_degraded"):
                        raise AssertionError("corrupt index did not report safe recovery")
                if lifecycle == "warm_index_reuse" and result.get("parsed_sources"):
                    raise AssertionError("warm indexed requery parsed source content")

for range_name in date_ranges:
    groups = {}
    for item in measurements:
        if item["range_name"] == range_name:
            key = (item["implementation"], item["lifecycle"])
            groups.setdefault(key, []).append(item)
    expected_digests = {}
    for key, samples in groups.items():
        if len(samples) != 3:
            raise AssertionError("{} {} has {} samples, expected 3".format(
                range_name, key, len(samples)))
        digests = {sample["full_page_order_sha256"] for sample in samples}
        if len(digests) != 1:
            raise AssertionError("{} {} returned inconsistent sorted results".format(
                range_name, key))
        expected_digests.setdefault(key[0], digests.pop())
    if len(set(expected_digests.values())) != 1:
        raise AssertionError("fixed-base and current rows/order differ for {}".format(range_name))

raw_path = output / "raw-measurements.jsonl"
raw_path.write_text("".join(json.dumps(item, ensure_ascii=False, sort_keys=True) + "\n"
                            for item in measurements), encoding="utf-8")
metric_names = (
    "submit_to_total_count_seconds", "submit_to_sorted_initial_batch_seconds",
    "submit_to_first_readable_pages_seconds", "first_pages_read_seconds",
    "submit_to_full_completion_seconds", "full_page_order_digest_seconds",
    "selected_detail_seconds", "parsed_sources", "reused_sources",
    "source_version_checks", "source_bytes_read", "query_content_copy_count",
    "query_content_copy_bytes", "event_json_copied_rows", "event_json_copied_bytes",
    "indexed_content_write_count", "indexed_content_write_bytes", "query_snapshot_bytes",
    "index_bytes", "tracemalloc_peak_bytes")
summaries = {}
for item in measurements:
    key = "{}/{}/{}".format(item["range_name"], item["implementation"], item["lifecycle"])
    summaries[key] = {metric: {
        "median": statistics.median(
            row[metric] for row in measurements
            if row["range_name"] == item["range_name"] and
            row["implementation"] == item["implementation"] and
            row["lifecycle"] == item["lifecycle"] and row.get(metric) is not None),
        "samples": [row[metric] for row in measurements
                    if row["range_name"] == item["range_name"] and
                    row["implementation"] == item["implementation"] and
                    row["lifecycle"] == item["lifecycle"] and row.get(metric) is not None],
    } for metric in metric_names if any(
        row["range_name"] == item["range_name"] and
        row["implementation"] == item["implementation"] and
        row["lifecycle"] == item["lifecycle"] and row.get(metric) is not None
        for row in measurements)}

report = {
    "fixture_root": str(fixture),
    "fixture_manifest_sha256": __import__("hashlib").sha256(
        (fixture / "fixture-manifest.json").read_bytes()).hexdigest(),
    "fixture_manifest": manifest,
    "fixed_base": "990a3d87193035e9dc235fb8f765267fdd8f820a",
    "current_review_base": "990a3d87193035e9dc235fb8f765267fdd8f820a",
    "runtime": manifest["runtime"],
    "ranges": {name: [start.isoformat(), end.isoformat()]
               for name, (start, end) in date_ranges.items()},
    "samples_per_implementation_range_lifecycle": 3,
    "measurement_count": len(measurements),
    "os_cache_condition": "uncontrolled; no cold-disk claim",
    "reports": summaries,
    "raw_measurements": str(raw_path),
}
(output / "benchmark-report.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    encoding="utf-8")
print(json.dumps({"measurement_count": len(measurements),
                  "output": str(output / "benchmark-report.json")}, sort_keys=True))
