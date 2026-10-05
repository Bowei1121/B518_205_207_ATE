"""Rebuild one round from its versioned audit journal stored on disk."""

import argparse
import json
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT / "src"))

from audit_records import AuditRecordError, read_round_audit


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audit_jsonl", type=Path, help="Session 資料夾內的 audit.jsonl")
    parser.add_argument("--summary", action="store_true", help="只輸出狀態摘要，不輸出序號與來源證據")
    args = parser.parse_args(argv)
    try:
        rebuilt = read_round_audit(args.audit_jsonl)
    except AuditRecordError as error:
        parser.error(str(error))
    if args.summary:
        value = {
            "round_id": rebuilt["round"]["round_id"],
            "station": rebuilt["round"]["station"],
            "state": rebuilt["state"],
            "collection_stopped": rebuilt["collection_stopped"],
            "result_available": rebuilt["result_available"],
            "audit_complete": rebuilt["audit_complete"],
            "event_count": len(rebuilt["events"]),
            "channel_statuses": {str(slot): item["status"]
                                 for slot, item in rebuilt["results"].items()},
        }
    else:
        value = rebuilt
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if rebuilt["audit_complete"] else 2


if __name__ == "__main__":
    sys.exit(main())
