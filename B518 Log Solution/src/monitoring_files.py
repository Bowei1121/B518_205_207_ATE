"""Shared local-file signatures and CSV identity helpers."""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple


def file_signature(path: Path) -> Tuple[int, int]:
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns


def snapshot_files(root: Path, suffix: str = "") -> Dict[str, Tuple[int, int]]:
    if not root.is_dir():
        return {}
    answer: Dict[str, Tuple[int, int]] = {}
    for path in root.rglob("*"):
        if not path.is_file() or (suffix and path.suffix.lower() != suffix.lower()):
            continue
        try:
            answer[str(path.resolve())] = file_signature(path)
        except OSError:
            pass
    return answer


def normalise_sn(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "").upper())


def is_trusted_sn(value: object) -> bool:
    sn = normalise_sn(value)
    invalid = {"", "N/A", "NA", "NONE", "UNKNOWN", "NUMBER_SOF0"}
    return len(sn) >= 6 and sn not in invalid and not sn.startswith("NUMBER_")


def read_csv_rows(path: Path, on_error: Optional[Callable[[Exception], None]] = None
                  ) -> List[Dict[str, str]]:
    last_error = None
    for encoding in ("utf-8-sig", "utf-8", "big5", "latin-1"):
        try:
            with path.open("r", encoding=encoding, newline="") as handle:
                return [{str(k or "").strip(): str(v or "").strip() for k, v in row.items()}
                        for row in csv.DictReader(handle)]
        except (UnicodeError, csv.Error, OSError) as error:
            last_error = error
            continue
    if last_error is not None and on_error is not None:
        on_error(last_error)
    return []
