"""Replay supplied Atlas, B482 TestData, and RS-WMT samples read-only.

The tool copies only the selected sample files into temporary directories,
uses simulated clocks, and prints aggregate results without serial numbers or
source paths. It never writes to the supplied sample tree.
"""

import argparse
import hashlib
import json
import shutil
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from log_monitoring import (
    AtlasActiveArchiveMonitor,
    BtLogMonitor,
    CASEINFO_FILE,
    CASEINFO_TIMESTAMP,
    parse_archive_timestamp,
    parse_bt_csv,
    parse_bt_filename,
    records_status,
    trusted_sn_from_records,
)
from replay_rswmt import replay as replay_rswmt


def source_signature(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    stat = Path(path).stat()
    return stat.st_size, stat.st_mtime_ns, digest.hexdigest()


def require_unchanged(path, before):
    if source_signature(path) != before:
        raise ValueError("A supplied sample changed during replay.")


def replay_atlas_archive_sample(sample, source_root, station):
    relative = sample.relative_to(source_root)
    archive_folder = sample.parent.parent.name
    archive_time = parse_archive_timestamp(archive_folder)
    serial = trusted_sn_from_records(sample)
    if not archive_time or not serial:
        raise ValueError("An Atlas archive sample is missing trusted identity or archive time.")

    before = source_signature(sample)
    with tempfile.TemporaryDirectory(prefix="b518-atlas-baseline-") as temporary:
        root = Path(temporary)
        active_root, final_root = root / "active", root / "archive"
        active_record = active_root / "group0-slot1" / "system" / "records.csv"
        active_record.parent.mkdir(parents=True)
        clock = {"now": archive_time, "elapsed": 0.0}
        monitor = AtlasActiveArchiveMonitor(
            station,
            active_root,
            final_root,
            (1,),
            now=lambda: clock["now"],
            monotonic=lambda: clock["elapsed"],
            session_root=root / "sessions",
        )

        # These supplied directories contain archive records, not active trees.
        # Reuse the sample as an active observation, then feed the original
        # archive record to verify the real final-result parser and transition.
        shutil.copyfile(sample, active_record)
        monitor.poll_once()
        if monitor.results[1].status != "TESTING":
            raise ValueError("Atlas active observation did not produce TESTING.")

        shutil.rmtree(active_root / "group0-slot1")
        final_record = final_root / relative
        final_record.parent.mkdir(parents=True)
        shutil.copyfile(sample, final_record)
        clock["now"] += timedelta(seconds=1)
        clock["elapsed"] = 1.0
        monitor.poll_once()

        expected = records_status(sample)
        observed = monitor.results[1].status
        if observed != expected:
            raise ValueError("Atlas archive result did not match the source sample.")
        clock["now"] += timedelta(seconds=3)
        clock["elapsed"] = 4.0
        monitor.poll_once()
        finished = monitor.finished
        monitor.stop()

    require_unchanged(sample, before)
    return observed, finished


def replay_atlas(source_root, station):
    source_root = Path(source_root)
    samples = sorted(source_root.rglob("records.csv"))
    if not samples:
        raise ValueError("No Atlas records.csv samples were found.")
    results = Counter()
    finished = 0
    for sample in samples:
        status, did_finish = replay_atlas_archive_sample(sample, source_root, station)
        results[status] += 1
        finished += bool(did_finish)
    return {"samples": len(samples), "statuses": dict(sorted(results.items())), "finished": finished}


def replay_b482_run(samples):
    first = parse_bt_filename(samples[0])
    if not first:
        raise ValueError("A B482 TestData sample has an unsupported filename.")
    started = datetime.strptime(first["stamp"], "%Y%m%d%H%M%S")
    date_folder = started.strftime("%Y-%m-%d")
    clock = {"now": started, "elapsed": 0.0}
    parsed_samples = []
    for sample in samples:
        filename = parse_bt_filename(sample)
        parsed = parse_bt_csv(sample)
        if not filename or not parsed:
            raise ValueError("A B482 TestData sample could not be parsed.")
        parsed_samples.append((sample, parsed, filename))
    expected = {int(parsed["slot"]): parsed["status"] for _, parsed, _ in parsed_samples}

    with tempfile.TemporaryDirectory(prefix="b518-b482-baseline-") as temporary:
        root = Path(temporary)
        testdata = root / "TestData"
        monitor = BtLogMonitor(
            testdata,
            tuple(sorted(expected)),
            now=lambda: clock["now"],
            monotonic=lambda: clock["elapsed"],
            session_root=root / "sessions",
        )
        copied = []
        for sample, parsed, filename in parsed_samples:
            before = source_signature(sample)
            # The source filename carries PASSED/FAILED, while parser status
            # carries PASS/FAIL/NOTEST. Preserve the original directory rule.
            filename_status = filename["status"].upper()
            target = testdata / date_folder / filename_status / sample.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(sample, target)
            copied.append((sample, before))
        monitor.poll_once()
        clock["elapsed"] = 5.1
        clock["now"] += timedelta(seconds=5)
        monitor.poll_once()
        observed = {slot: result.status for slot, result in monitor.results.items()}
        if observed != expected:
            raise ValueError("B482 TestData results did not match the source samples.")
        clock["elapsed"] += 3.0
        clock["now"] += timedelta(seconds=3)
        monitor.poll_once()
        finished = monitor.finished
        monitor.stop()

    for sample, before in copied:
        require_unchanged(sample, before)
    return observed, finished


def replay_b482(source_root):
    source_root = Path(source_root)
    groups = defaultdict(dict)
    for sample in source_root.rglob("*.csv"):
        parsed = parse_bt_filename(sample)
        if not parsed:
            continue
        key = (parsed["stamp"], parsed["status"].upper())
        slot = int(parsed["thread"]) + 1
        groups[key].setdefault(slot, []).append(sample)

    complete_runs = []
    for files_by_slot in groups.values():
        if set(files_by_slot) != {1, 2, 3, 4} or any(len(files) != 1 for files in files_by_slot.values()):
            continue
        complete_runs.append([files_by_slot[slot][0] for slot in range(1, 5)])
    if not complete_runs:
        raise ValueError("No complete four-slot B482 TestData run was found.")

    statuses = Counter()
    finished = 0
    for run in sorted(complete_runs, key=lambda files: parse_bt_filename(files[0])["stamp"]):
        observed, did_finish = replay_b482_run(run)
        statuses.update(observed.values())
        finished += bool(did_finish)

    caseinfo = replay_b482_caseinfo(source_root)
    return {"runs": len(complete_runs), "slots": sum(statuses.values()),
            "statuses": dict(sorted(statuses.items())), "finished_runs": finished,
            "caseinfo": caseinfo}


def replay_b482_caseinfo(source_root):
    by_date = defaultdict(dict)
    for sample in Path(source_root).glob("thread*CaseInfo_*.txt"):
        match = CASEINFO_FILE.fullmatch(sample.name)
        if match:
            by_date[match.group("date")][int(match.group("thread"))] = sample
    candidates = [files for files in by_date.values() if set(files) == {1, 2, 3, 4}]
    if not candidates:
        raise ValueError("No four-thread B482 CaseInfo sample day was found.")
    samples = max(candidates, key=lambda files: sum(path.stat().st_size for path in files.values()))

    event_times = []
    for sample in samples.values():
        text = sample.read_text(encoding="utf-8", errors="replace")
        for match in CASEINFO_TIMESTAMP.finditer(text):
            try:
                value = datetime.strptime(match.group("time")[:19].replace("/", "-"), "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
            event_times.append(value)
    if not event_times:
        raise ValueError("B482 CaseInfo samples contain no parseable event time.")

    before = {sample: source_signature(sample) for sample in samples.values()}
    # Replay the supplied day from its first event so SNRead evidence isn't
    # filtered out simply because the file also contains later test rounds.
    started = min(event_times) - timedelta(seconds=1)
    clock = {"now": started, "elapsed": 0.0}
    with tempfile.TemporaryDirectory(prefix="b518-caseinfo-baseline-") as temporary:
        root = Path(temporary)
        caseinfo_root = root / "CaseInfo"
        monitor = BtLogMonitor(
            root / "TestData",
            (1, 2, 3, 4),
            caseinfo_root=caseinfo_root,
            now=lambda: clock["now"],
            monotonic=lambda: clock["elapsed"],
            session_root=root / "sessions",
        )
        caseinfo_root.mkdir(parents=True)
        for sample in samples.values():
            shutil.copyfile(sample, caseinfo_root / sample.name)
        monitor.poll_once()
        observed = [result for result in monitor.results.values() if result.status != "WAITING"]
        serials = sum(bool(result.sn) for result in observed)
        states = Counter(result.status for result in observed)
        monitor.stop()

    for sample, signature in before.items():
        require_unchanged(sample, signature)
    if not observed:
        raise ValueError("B482 CaseInfo samples produced no monitor observations.")
    return {"input_files": len(samples), "observed_slots": len(observed),
            "slots_with_serial": serials, "statuses": dict(sorted(states.items()))}


def replay_rswmt_summary(source):
    files = [path for path in Path(source).glob("*") if path.is_file() and path.suffix.lower() in {".csv", ".log"}]
    before = {path: source_signature(path) for path in files}
    results = replay_rswmt(source)
    for path, signature in before.items():
        require_unchanged(path, signature)
    statuses = Counter(result["status"] for result in results)
    return {"slots": len(results), "statuses": dict(sorted(statuses.items()))}


def find_rswmt_run(source_root):
    candidates = []
    for path in Path(source_root).iterdir():
        if not path.is_dir():
            continue
        csv_count = sum(1 for sample in path.glob("*.csv") if sample.is_file())
        if csv_count:
            candidates.append((csv_count, path))
    if not candidates:
        raise ValueError("No RS-WMT result run directory was found.")
    return max(candidates, key=lambda item: item[0])[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("samples_root", type=Path, help="Root containing B482 DFU, B482 FCT, B482 BT, and B518 BT sample directories")
    args = parser.parse_args()
    root = args.samples_root.expanduser().resolve()

    rswmt_run = find_rswmt_run(root / "B518 BT")
    report = {
        "atlas_dfu": replay_atlas(root / "B482 DFU" / "test_data", "DFU"),
        "atlas_fct": replay_atlas(root / "B482 FCT" / "unit-archive", "FCT"),
        "b482_testdata": replay_b482(root / "B482 BT"),
        "rswmt": replay_rswmt_summary(rswmt_run),
        "source_policy": "Sample inputs are copied to temporary directories; serial numbers and source paths are omitted.",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as error:
        raise SystemExit("Baseline replay failed: {}".format(error))
