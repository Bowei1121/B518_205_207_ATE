"""Replay a single RS-WMT result directory with an aligned, simulated clock.

Read-only for originals. Uses temporary monitoring/session directories; never
changes application preferences or connects to test equipment.
"""
import argparse
import json
import shutil
import tempfile
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path

# Allow direct CLI execution from any working directory.
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from monitoring_round import RoundCoordinator
from platform_registry import DEFAULT_PLATFORM_REGISTRY
from rswmt_monitoring import parse_rswmt_csv


def replay(source):
    files = sorted(Path(source).glob('*.csv'))
    records = [parse_rswmt_csv(path) for path in files]
    if not files or any(record is None for record in records):
        raise ValueError('Select one run directory containing valid per-DUT RS-WMT CSV files.')
    starts = {record.started for record in records}
    if len(starts) != 1 or len({record.slot for record in records}) != len(records):
        raise ValueError('Mixed runs or duplicate slots; replay one run at a time.')
    start = next(iter(starts))
    elapsed = 0.0
    with tempfile.TemporaryDirectory(prefix='b518-rswmt-replay-') as temporary:
        root = Path(temporary)
        output = root / 'output/SmtCal'
        output.mkdir(parents=True)
        rounds = RoundCoordinator()
        rounds.start('BT', lambda callback: DEFAULT_PLATFORM_REGISTRY.create_monitor(
            'rswmt', station='BT', paths={'final': output}, source_slots=tuple(
                sorted(record.slot for record in records)), callback=callback,
            now=lambda: start + timedelta(seconds=elapsed), monotonic=lambda: elapsed,
            session_root=root / 'sessions', async_session_writes=False,
            timeouts={'start': 240, 'test': 480, 'round': 7200},
        ), run_async=False)
        elapsed = max((record.stopped - start).total_seconds() for record in records)
        for path in files:
            shutil.copyfile(path, output / path.name)
            log = path.with_suffix('.log')
            if log.is_file():
                shutil.copyfile(log, output / log.name)
        rounds.poll_once()
        elapsed += 5.0
        rounds.poll_once()
        snapshot = rounds.snapshot()
        for record in records:
            observed = next(result for result in snapshot.results if result.slot == record.slot)
            if (observed.sn, observed.status) != (record.sn, record.status):
                raise ValueError('Replay mismatch for slot {}'.format(record.slot))
        results = [asdict(value) for value in rounds.snapshot().results]
        rounds.stop()
        return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_directory', type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(replay(args.run_directory), indent=2, ensure_ascii=False))
    except ValueError as error:
        parser.exit(1, str(error) + '\n')
