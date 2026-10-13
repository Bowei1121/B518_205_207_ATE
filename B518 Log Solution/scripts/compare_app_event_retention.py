#!/usr/bin/env python3
"""Compare public App-event retention outcomes for two source checkouts."""

import argparse
import json
import os
import subprocess


DRIVER = r'''import json, tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from app_event_store import AppEventStore, read_app_event_store

now = datetime(2026, 10, 9, 8, 0, tzinfo=timezone.utc)
cutoff = now - timedelta(days=30)
result = {}

def seed(store, stamps):
    events = []
    for stamp in stamps:
        store._clock = lambda stamp=stamp: stamp
        events.append(store.record("app.hotkey.unavailable", {}, "fixed diagnostic"))
    assert store.flush()
    return events

def summarize(store, outcome):
    data = read_app_event_store(store.path)
    result[outcome].update({
        "remaining_sequences": sorted(item["sequence"] for item in data["events"]),
        "retired_sequences": data.get("retired_sequences", []),
        "next_sequence": data.get("next_sequence", len(data["events"]) + 1),
    })

with tempfile.TemporaryDirectory() as folder:
    root = Path(folder)
    store = AppEventStore(root / "mixed.json", clock=lambda: now)
    seed(store, [cutoff - timedelta(seconds=1), cutoff, cutoff + timedelta(seconds=1)])
    r = store.cleanup_expired(cutoff, root)
    result["mixed"] = {"status": r.status, "deleted": r.deleted_count,
                        "skipped": r.skipped_count, "failed": r.failed_count}
    summarize(store, "mixed")
    store.stop()

with tempfile.TemporaryDirectory() as folder:
    root = Path(folder)
    store = AppEventStore(root / "future.json", clock=lambda: now)
    seed(store, [cutoff + timedelta(seconds=1)])
    r = store.cleanup_expired(cutoff, root)
    result["not_expired"] = {"status": r.status, "deleted": r.deleted_count,
                             "skipped": r.skipped_count, "failed": r.failed_count}
    summarize(store, "not_expired")
    store.stop()

with tempfile.TemporaryDirectory() as folder:
    root = Path(folder)
    path = root / "bad.json"
    path.write_bytes(b'{broken')
    store = AppEventStore(path, clock=lambda: now)
    r = store.cleanup_expired(cutoff, root)
    result["corrupt"] = {"status": r.status, "deleted": r.deleted_count,
                         "skipped": r.skipped_count, "failed": r.failed_count,
                         "bytes_unchanged": path.read_bytes() == b'{broken'}
    store.stop()

with tempfile.TemporaryDirectory() as folder:
    root = Path(folder)
    managed = root / "managed"
    managed.mkdir()
    target = managed / "journal.json"
    store = AppEventStore(target, clock=lambda: now)
    seed(store, [cutoff - timedelta(seconds=1)])
    outside_dir = root / "outside"
    outside_dir.mkdir()
    external = outside_dir / target.name
    external.write_bytes(b'external sentinel')
    original = external.read_bytes()
    moved = root / "moved"
    def replace_after_swap(instant, commit):
        managed.rename(moved)
        managed.symlink_to(outside_dir, target_is_directory=True)
        commit()
    r = store.cleanup_expired(cutoff, root, before_replace=replace_after_swap)
    result["path_swap"] = {"status": r.status, "deleted": r.deleted_count,
                            "skipped": r.skipped_count, "failed": r.failed_count,
                            "external_unchanged": external.read_bytes() == original,
                            "managed_original_exists": (moved / target.name).exists()}
    store.stop()

print(json.dumps(result, sort_keys=True))
'''


def run(python, source_dir):
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(source_dir)
    completed = subprocess.run(
        [python, "-c", DRIVER], env=environment, check=True, text=True,
        capture_output=True)
    return json.loads(completed.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", required=True, help="Python interpreter to use")
    parser.add_argument("--baseline-src", required=True,
                        help="src directory from the fixed pre-ticket checkout")
    parser.add_argument("--candidate-src", required=True,
                        help="src directory from the candidate checkout")
    args = parser.parse_args()

    outputs = {
        "fixed_base": run(args.python, args.baseline_src),
        "candidate": run(args.python, args.candidate_src),
    }
    print(json.dumps(outputs, indent=2, sort_keys=True))
    if outputs["fixed_base"] != outputs["candidate"]:
        raise SystemExit("outcome parity mismatch")
    print("PARITY: identical deletion/retention/count/sequence results")


if __name__ == "__main__":
    main()
