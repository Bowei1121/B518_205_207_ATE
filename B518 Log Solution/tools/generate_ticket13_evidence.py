"""Create synthetic, disk-reconstructed evidence for Ticket 13."""

import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT / "src"))

from log_monitoring import MonitorEvent, SlotResult
from monitoring_round import RoundCoordinator
from audit_records import read_round_audit


class EvidenceMonitor:
    def __init__(self, callback):
        self.callback = callback
        self.results = {slot: SlotResult(slot) for slot in (1, 2)}
        self.limits = {"start": 10, "test": 20, "round": 30}
        self.pending = []
        self.session = None

    def round_results(self):
        return tuple(self.results.values())

    def timeout_seconds(self, kind):
        return self.limits[kind]

    def update_round_settings(self, _settings):
        pass

    def publish_round_event(self, event):
        self.callback(event)

    def start(self):
        pass

    def poll_once(self):
        pending, self.pending = self.pending, []
        for action in pending:
            action()

    def apply_round_result(self, slot, status, sn="", source="", detail=None, lock_terminal=False):
        result = self.results[slot]
        result.status, result.sn, result.source = status, sn, source
        self.callback(MonitorEvent("result", "slot{} {}".format(slot, status), slot, sn,
                                   status, source, detail or {}))

    def set_result(self, slot, status, detail=None, lock_terminal=False):
        self.apply_round_result(slot, status, detail=detail, lock_terminal=lock_terminal)

    def stop_collection(self):
        pass

    def finish(self):
        pass

    def stop(self):
        pass


def make_round(case, root):
    clock = [0.0]
    coordinator = RoundCoordinator(monotonic=lambda: clock[0], audit_root=root,
                                   wall_clock=lambda: datetime(2026, 10, 5, 12, 0, 0))
    holder = {}

    def factory(callback):
        monitor = EvidenceMonitor(callback)
        holder["monitor"] = monitor
        return monitor

    started = coordinator.start(
        "FCT", factory, run_async=False, round_timeout_seconds=3 if case == "round-timeout" else 30,
        capacity=2,
        audit_context={"project": "SYNTHETIC", "machine": "FCT", "platform": "atlas",
                       "profile_version": 1, "capacity": 2,
                       "mapping": [{"source": 2, "display": 1}, {"source": 4, "display": 2}],
                       "timeouts": {"start": 10, "test": 20,
                                    "round": 3 if case == "round-timeout" else 30}},
    )
    monitor = holder["monitor"]
    if case == "round-timeout":
        monitor.limits["round"] = 3
    if case == "normal":
        monitor.pending.extend([
            lambda: monitor.apply_round_result(1, "PASS", "SYNTHETIC-001", "fixture/A",
                                                {"source_position": 2, "source_time": "2026-10-05T11:59:00"}),
            lambda: monitor.apply_round_result(2, "FAIL", "SYNTHETIC-002", "fixture/B",
                                                {"source_position": 4, "source_time": "2026-10-05T11:59:01"}),
        ])
        coordinator.poll_once()
    elif case == "conflict":
        monitor.pending.append(lambda: monitor.apply_round_result(
            1, "PASS", "SYNTHETIC-001", "fixture/original",
            {"source_position": 2, "source_id": "synthetic-original", "source_time": "2026-10-05T11:59:00",
             "round_evidence_id": "synthetic-batch"},
        ))
        coordinator.poll_once()
        monitor.callback(MonitorEvent(
            "result_candidate", "synthetic candidate", 1, "SYNTHETIC-001", "FAIL", "fixture/candidate",
            {"source_position": 2, "source_id": "synthetic-candidate", "source_time": "2026-10-05T11:59:02",
             "round_evidence_id": "synthetic-batch"},
        ))
        monitor.pending.append(lambda: monitor.apply_round_result(2, "PASS", "SYNTHETIC-002", "fixture/B"))
        coordinator.poll_once()
        conflict_id = coordinator.snapshot().pending_conflicts[0].conflict_id
        coordinator.resolve_review(conflict_id, "accept_candidate")
    else:
        monitor.pending.append(lambda: monitor.apply_round_result(1, "PASS", "SYNTHETIC-001", "fixture/A"))
        coordinator.poll_once()
        clock[0] = 3.0
        waiting = coordinator.poll_once()
        coordinator.acknowledge_round_alarm(started.round_id, waiting.round_alarm.alarm_id)

    if not coordinator.flush_audit():
        raise RuntimeError("稽核事件未能完整保存：{}".format(case))
    path = Path(root) / started.round_id / "audit.jsonl"
    rebuilt = read_round_audit(path)
    return {
        "case": case,
        "evidence_kind": "synthetic_anonymized",
        "round": rebuilt["round"],
        "events": rebuilt["events"],
        "results": rebuilt["results"],
        "alarms": rebuilt["alarms"],
        "conflicts": rebuilt["conflicts"],
        "collection_stopped": rebuilt["collection_stopped"],
        "manual_stop": rebuilt["manual_stop"],
        "result_available": rebuilt["result_available"],
        "audit_complete": rebuilt["audit_complete"],
    }


def main():
    output = APP_ROOT.parent / "docs/refactoring/evidence/ticket-13"
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="b518-ticket13-evidence-") as temporary:
        for case in ("normal", "conflict", "round-timeout"):
            evidence = make_round(case, Path(temporary) / case)
            destination = output / "{}.json".format(case)
            destination.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                                   encoding="utf-8")
            print("{}: {} events, result_available={}, audit_complete={}".format(
                destination.name, len(evidence["events"]), evidence["result_available"],
                evidence["audit_complete"],
            ))


if __name__ == "__main__":
    main()
