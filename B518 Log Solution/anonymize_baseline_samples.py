"""Create a small, serial-redacted replay set from read-only machine samples."""

import argparse
import csv
import hashlib
import re
from collections import defaultdict
from pathlib import Path

from log_monitoring import (
    CASEINFO_FILE,
    is_trusted_sn,
    parse_archive_timestamp,
    parse_bt_csv,
    parse_bt_filename,
    trusted_sn_from_records,
)
from replay_baseline_samples import find_rswmt_run
from rswmt_monitoring import parse_rswmt_csv


def _signature(path):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns, digest


def _replace_identifiers(data, identifiers):
    for original, replacement in sorted(identifiers.items(), key=lambda item: len(item[0]), reverse=True):
        data = re.sub(re.escape(original.encode("utf-8")), replacement.encode("ascii"), data, flags=re.I)
    return data


def _write_redacted(source, target, identifiers):
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(_replace_identifiers(source.read_bytes(), identifiers))


def _copy_redacted_path(source, source_root, target_root, identifiers):
    relative = source.relative_to(source_root)
    parts = []
    for part in relative.parts:
        redacted = part
        for original, replacement in identifiers.items():
            redacted = re.sub(re.escape(original), replacement, redacted, flags=re.I)
        parts.append(redacted)
    _write_redacted(source, target_root.joinpath(*parts), identifiers)


def _caseinfo_identifiers(path, next_id):
    text = path.read_text(encoding="utf-8", errors="replace")
    identifiers = {}
    for line in text.splitlines():
        try:
            row = next(csv.reader([line]))
        except (csv.Error, StopIteration):
            continue
        actions = [row[index].strip().upper() for index in (3, 5) if len(row) > index]
        if "SNREAD" not in actions or len(row) <= 6:
            continue
        value = row[6].strip()
        if is_trusted_sn(value) and value not in identifiers:
            identifiers[value] = "SAMPLESERIAL{:04d}".format(next_id)
            next_id += 1
    return identifiers, next_id


def _atlas_related_identifiers(path):
    """Find fixture and instrument identifiers embedded in Atlas archive CSVs."""
    identifiers = set()
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    identifiers.update(re.findall(r"(?:Xavier|DMM|PWR|Scope)-[A-Za-z0-9/-]+", text, re.I))
    with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as stream:
        for row in csv.reader(stream):
            if len(row) < 2:
                continue
            key, value = row[0].strip(), row[1].strip()
            if key.casefold() in {"fixtureid", "fct_fixture_id"} and value:
                identifiers.add(value)
            elif re.fullmatch(r"(?:Xavier|DMM|PWR|Scope)-[A-Za-z0-9/-]+", key, re.I) and value:
                # These rows pair a fixture instrument label with that device's serial.
                identifiers.add(key)
                identifiers.add(value)
    return identifiers


def build_samples(source_root, output_root):
    source_root, output_root = Path(source_root).resolve(), Path(output_root).resolve()
    if output_root == source_root or source_root in output_root.parents:
        raise ValueError("Output directory must be outside the supplied source tree.")
    if source_root == output_root or output_root in source_root.parents:
        raise ValueError("Output directory must not contain the supplied source tree.")
    if output_root.exists() and any(output_root.iterdir()):
        raise ValueError("Output directory must be missing or empty.")
    output_root.mkdir(parents=True, exist_ok=True)
    signatures = {}
    known_identifiers = {}
    sample_count = defaultdict(int)

    for source_name, relative_root in (
        ("B482 DFU", Path("B482 DFU/test_data")),
        ("B482 FCT", Path("B482 FCT/unit-archive")),
    ):
        source_dir = source_root / relative_root
        candidates = sorted(
            path for path in source_dir.rglob("records.csv")
            if parse_archive_timestamp(path.parent.parent.name)
            and trusted_sn_from_records(path)
        )
        if not candidates:
            raise ValueError("An Atlas archive sample is missing required identity or timestamp evidence.")
        sample = candidates[0]
        serial = trusted_sn_from_records(sample)
        token = "SAMPLESERIAL{:04d}".format(len(known_identifiers) + 1)
        known_identifiers[serial] = token
        for related in sorted(_atlas_related_identifiers(sample)):
            if related not in known_identifiers:
                known_identifiers[related] = "ANONIDENTIFIER{:04d}".format(len(known_identifiers) + 1)
        signatures[sample] = _signature(sample)
        _copy_redacted_path(sample, source_root, output_root, known_identifiers)
        sample_count[source_name] += 1

    b482_root = source_root / "B482 BT"
    groups = defaultdict(dict)
    for sample in b482_root.rglob("*.csv"):
        parsed_name = parse_bt_filename(sample)
        parsed_csv = parse_bt_csv(sample)
        if parsed_name and parsed_csv:
            key = (parsed_name["stamp"], parsed_name["status"].upper())
            slot = int(parsed_name["thread"]) + 1
            groups[key].setdefault(slot, []).append((sample, parsed_name))
    complete = [
        groups[key] for key in sorted(groups)
        if set(groups[key]) == {1, 2, 3, 4} and all(len(group) == 1 for group in groups[key].values())
    ]
    if not complete:
        raise ValueError("No complete four-slot B482 TestData run was found.")
    b482_identifiers = dict(known_identifiers)
    for slot, entries in sorted(complete[0].items()):
        parsed_name = entries[0][1]
        if parsed_name["sn"]:
            b482_identifiers[parsed_name["sn"]] = "SAMPLESERIAL{:04d}".format(slot)
    known_identifiers.update({
        serial: token for serial, token in b482_identifiers.items()
        if serial not in known_identifiers
    })
    for slot, entries in sorted(complete[0].items()):
        sample, parsed_name = entries[0]
        identifiers = dict(b482_identifiers)
        signatures[sample] = _signature(sample)
        source_date = parse_bt_filename(sample)["stamp"][:8]
        target_dir = output_root / "B482 BT" / "{}-{}-{}".format(source_date[:4], source_date[4:6], source_date[6:8]) / parsed_name["status"].upper()
        target_name = sample.name
        target_name = re.sub(re.escape(parsed_name["sn"]), "SAMPLESERIAL{:04d}".format(slot), target_name, flags=re.I) if parsed_name["sn"] else target_name
        target_name = "[Thread{}][ANONCONFIG][{}][{}][{}].csv".format(
            parsed_name["thread"], "SAMPLESERIAL{:04d}".format(slot) if parsed_name["sn"] else "",
            parsed_name["status"].upper(), parsed_name["stamp"],
        )
        _write_redacted(sample, target_dir / target_name, identifiers)
        sample_count["B482 TestData"] += 1

    caseinfo_files = {}
    for sample in b482_root.glob("thread*CaseInfo_2026-08-21.txt"):
        match = CASEINFO_FILE.fullmatch(sample.name)
        if match:
            caseinfo_files[int(match.group("thread"))] = sample
    if set(caseinfo_files) != {1, 2, 3, 4}:
        raise ValueError("The selected B482 CaseInfo date is missing one or more threads.")
    next_id = 20
    for _slot, sample in sorted(caseinfo_files.items()):
        identifiers, next_id = _caseinfo_identifiers(sample, next_id)
        known_identifiers.update(identifiers)
        signatures[sample] = _signature(sample)
        _write_redacted(sample, output_root / "B482 BT" / sample.name, identifiers)
        sample_count["B482 CaseInfo"] += 1

    rswmt_root = source_root / "B518 BT"
    run = find_rswmt_run(rswmt_root)
    records = [(path, parse_rswmt_csv(path)) for path in sorted(run.glob("*.csv"))]
    if len(records) != 4 or any(record is None for _, record in records) or len({record.slot for _, record in records}) != 4:
        raise ValueError("The selected RS-WMT run must contain four distinct valid Slot results.")
    target_run = output_root / "B518 BT" / run.name
    rswmt_identifiers = {
        record.sn: "SAMPLESERIAL{:04d}".format(record.slot)
        for _, record in records
    }
    known_identifiers.update(rswmt_identifiers)
    for sample, record in records:
        token = rswmt_identifiers[record.sn]
        signatures[sample] = _signature(sample)
        _write_redacted(sample, target_run / sample.name.replace(record.sn, token), {record.sn: token})
        sample_count["RS-WMT"] += 1

    for sample, signature in signatures.items():
        if _signature(sample) != signature:
            raise ValueError("A source sample changed during anonymization.")
    for path in output_root.rglob("*"):
        if not path.is_file():
            continue
        data = path.read_bytes()
        name = str(path.relative_to(output_root)).encode("utf-8")
        if any(serial.encode("utf-8").lower() in data.lower()
               or serial.encode("utf-8").lower() in name.lower() for serial in known_identifiers):
            raise ValueError("A source serial number remains in the anonymized output.")
    return dict(sample_count)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_root", type=Path)
    parser.add_argument("output_root", type=Path)
    args = parser.parse_args()
    try:
        print(build_samples(args.source_root, args.output_root))
    except (OSError, ValueError) as error:
        parser.exit(1, "Anonymized sample generation failed: {}\n".format(error))
