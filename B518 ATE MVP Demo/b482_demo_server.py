#!/usr/bin/env python3
"""Local B482 HMI simulator for demonstrating Atlas Agent without hardware."""
from __future__ import annotations

import argparse
import csv
import json
import re
import threading
import time
from datetime import datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

SN_VALID = re.compile(r"^[^/\\,\s]{1,80}$")
BT_TEST_CONFIG = "B482FLDG_FQ3-5FAP-02B_29_BT-COND"
BT_STATION_ID = "FLDG_FQ3-5FAP-02B_29_BT-COND"


class Simulator:
    def __init__(self, csv_root: Path, duration_seconds: float = 30.0) -> None:
        self.csv_root = csv_root
        self.duration_seconds = duration_seconds
        self.lock = threading.Lock()
        self.batches: dict[str, dict] = {}

    def start(self, payload: dict) -> dict:
        station = str(payload.get("station", "FCT")).upper()
        if station not in ("DFU", "FCT", "BT"):
            raise ValueError("station 或 SN 格式不正確")
        assignments = self._assignments(station, payload)
        sns = [sn for _, sn in assignments]
        batch = datetime.now().strftime("demo-%H%M%S-%f")
        state = {
            "station": station,
            "sns": sns,
            "assignments": assignments,
            "started_at": datetime.now().replace(microsecond=0),
            "status": {sn: "TESTING" for sn in sns},
        }
        with self.lock:
            self.batches[batch] = state
        threading.Thread(target=self._run, args=(batch, bool(payload.get("fail_last"))), daemon=True).start()
        return {"batch": batch, **self._public_state(state)}

    @staticmethod
    def _public_state(state: dict) -> dict:
        return {"station": state["station"], "sns": list(state["sns"]), "status": dict(state["status"])}

    @staticmethod
    def _assignments(station: str, payload: dict) -> list[tuple[int, str]]:
        if station != "BT":
            sns = [str(value).strip() for value in payload.get("sns", []) if str(value).strip()]
            maximum = 7 if station == "DFU" else 4
            if not 1 <= len(sns) <= maximum or any(not SN_VALID.fullmatch(sn) for sn in sns) or len(set(sns)) != len(sns):
                raise ValueError("station 或 SN 格式不正確")
            return list(enumerate(sns, start=1))

        raw_assignments = payload.get("assignments")
        if not isinstance(raw_assignments, list) or not raw_assignments:
            raise ValueError("BT 必須提供 slot 與 SN 對應")
        assignments: list[tuple[int, str]] = []
        for item in raw_assignments:
            if not isinstance(item, dict):
                raise ValueError("BT slot 資料格式不正確")
            try:
                slot = int(item.get("slot"))
            except (TypeError, ValueError) as exc:
                raise ValueError("BT slot 資料格式不正確") from exc
            sn = str(item.get("sn", "")).strip()
            if slot not in (1, 2, 3, 4) or not SN_VALID.fullmatch(sn):
                raise ValueError("BT slot 或 SN 格式不正確")
            assignments.append((slot, sn))
        slots, sns = zip(*assignments)
        if len(assignments) > 4 or len(set(slots)) != len(slots) or len(set(sns)) != len(sns):
            raise ValueError("BT slot 或 SN 不可重複")
        return assignments

    def status(self, batch: str) -> dict:
        with self.lock:
            if batch not in self.batches:
                raise KeyError(batch)
            return {"batch": batch, **self._public_state(self.batches[batch])}

    def _run(self, batch: str, fail_last: bool) -> None:
        with self.lock:
            state = self.batches[batch]
            sns = list(state["sns"])
            assignments = list(state["assignments"])
            started_at = state["started_at"]
        if state["station"] == "BT":
            time.sleep(self.duration_seconds)
            ended_at = datetime.now().replace(microsecond=0)
            for index, (slot, sn) in enumerate(assignments):
                result = "FAILED" if fail_last and index == len(assignments) - 1 else "PASSED"
                self._write_bt_result(slot, sn, result, started_at, ended_at)
                with self.lock:
                    self.batches[batch]["status"][sn] = "FAIL" if result == "FAILED" else "PASS"
            return

        folders: dict[str, Path] = {}
        stamp = datetime.now().strftime("%Y%m%d_%H-%M-%S") + ".B482DEMO"
        for sn in sns:
            system = self.csv_root / sn / stamp / "system"
            system.mkdir(parents=True, exist_ok=True)
            (system / "device.log").write_text(f"{station_line(state['station'])}\nSN={sn}\nTESTING\n", encoding="utf-8")
            folders[sn] = system
        time.sleep(self.duration_seconds)
        for index, sn in enumerate(sns):
            result = "FAIL" if fail_last and index == len(sns) - 1 else "PASS"
            system = folders[sn]
            with (system / "device.log").open("a", encoding="utf-8") as log:
                log.write(f"RESULT={result}\nTEST COMPLETE\n")
            (system / "records.csv").write_text(f"test,status\nB482 Demo,{result}\n", encoding="utf-8")
            with self.lock:
                self.batches[batch]["status"][sn] = result

    def _write_bt_result(self, slot: int, sn: str, status: str,
                         started_at: datetime, ended_at: datetime) -> Path:
        """Write the core shape of a physical BT TestData export atomically."""
        directory = self.csv_root / ended_at.date().isoformat() / status
        directory.mkdir(parents=True, exist_ok=True)
        thread = slot - 1
        filename = f"[Thread{thread}][{BT_TEST_CONFIG}][{sn}][{status}][{started_at:%Y%m%d%H%M%S}].csv"
        destination = directory / filename
        temporary = destination.with_suffix(".csv.tmp")
        headers = [
            "Site", "Product", "SerialNumber", "Special Build Name", "Special Build Description",
            "Unit Number", "Station ID", "Test Pass/Fail Status", "StartTime", "EndTime",
            "Version", "List of Failing Tests",
        ]
        row = [
            "FLDG", "B482", sn, "", "", str(thread), BT_STATION_ID, status,
            started_at.strftime("%Y/%m/%d %H:%M:%S"), ended_at.strftime("%Y/%m/%d %H:%M:%S"),
            "B482 Demo", "Simulated BT failure" if status == "FAILED" else "",
        ]
        with temporary.open("w", encoding="utf-8", newline="") as target:
            writer = csv.writer(target)
            writer.writerow(headers)
            writer.writerow(row)
        temporary.replace(destination)
        return destination


def station_line(station: str) -> str:
    return f"B482 {station} simulated test started"


class Handler(SimpleHTTPRequestHandler):
    simulator: Simulator

    def end_headers(self) -> None:
        # Safari can retain a previously opened local HMI document in its page
        # cache.  The simulator is edited frequently during validation, so
        # always serve the current HTML rather than an old Start-button script.
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        super().end_headers()

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/start":
            self.send_error(HTTPStatus.NOT_FOUND); return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            result = self.simulator.start(json.loads(self.rfile.read(length)))
            self._json(HTTPStatus.OK, result)
        except (ValueError, json.JSONDecodeError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/status":
            try:
                batch = parsed.query.split("batch=", 1)[1]
                self._json(HTTPStatus.OK, self.simulator.status(batch))
            except (IndexError, KeyError):
                self._json(HTTPStatus.NOT_FOUND, {"error": "unknown batch"})
            return
        if parsed.path == "/": self.path = "/b482_demo_hmi.html"
        super().do_GET()

    def _json(self, status: HTTPStatus, value: dict) -> None:
        data = json.dumps(value).encode("utf-8")
        self.send_response(status); self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)


def main() -> None:
    parser = argparse.ArgumentParser(description="B482 local HTML HMI simulator")
    parser.add_argument("--csv-root", required=True, type=Path, help="Atlas Agent CSV 根路徑")
    parser.add_argument("--port", default=8080, type=int)
    parser.add_argument("--duration", default=30.0, type=float, help="模擬測試秒數（預設：30）")
    args = parser.parse_args()
    args.csv_root.mkdir(parents=True, exist_ok=True)
    Handler.simulator = Simulator(args.csv_root, args.duration)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"B482 Demo HMI: http://127.0.0.1:{args.port}")
    print(f"CSV root: {args.csv_root}")
    server.serve_forever()


if __name__ == "__main__": main()
