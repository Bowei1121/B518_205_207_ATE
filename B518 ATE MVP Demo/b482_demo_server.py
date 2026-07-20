#!/usr/bin/env python3
"""Local B482 HMI simulator for demonstrating Atlas Agent without hardware."""
from __future__ import annotations

import argparse
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


class Simulator:
    def __init__(self, csv_root: Path) -> None:
        self.csv_root = csv_root
        self.lock = threading.Lock()
        self.batches: dict[str, dict] = {}

    def start(self, payload: dict) -> dict:
        station = str(payload.get("station", "FCT")).upper()
        sns = [str(value).strip() for value in payload.get("sns", []) if str(value).strip()]
        if station not in ("DFU", "FCT", "BT") or not 1 <= len(sns) <= 4 or any(not SN_VALID.fullmatch(sn) for sn in sns):
            raise ValueError("station 或 SN 格式不正確")
        batch = datetime.now().strftime("demo-%H%M%S-%f")
        state = {"station": station, "sns": sns, "status": {sn: "TESTING" for sn in sns}}
        with self.lock:
            self.batches[batch] = state
        threading.Thread(target=self._run, args=(batch, bool(payload.get("fail_last"))), daemon=True).start()
        return {"batch": batch, **state}

    def status(self, batch: str) -> dict:
        with self.lock:
            if batch not in self.batches:
                raise KeyError(batch)
            return {"batch": batch, **self.batches[batch]}

    def _run(self, batch: str, fail_last: bool) -> None:
        with self.lock:
            state = self.batches[batch]
            sns = list(state["sns"])
        folders: dict[str, Path] = {}
        stamp = datetime.now().strftime("%Y%m%d_%H-%M-%S") + ".B482DEMO"
        for sn in sns:
            system = self.csv_root / sn / stamp / "system"
            system.mkdir(parents=True, exist_ok=True)
            (system / "device.log").write_text(f"{station_line(state['station'])}\nSN={sn}\nTESTING\n", encoding="utf-8")
            folders[sn] = system
        # Keep TESTING visible long enough to validate BT's screenshot-based
        # STATUS polling before the simulated instrument publishes its result.
        time.sleep(30)
        for index, sn in enumerate(sns):
            result = "FAIL" if fail_last and index == len(sns) - 1 else "PASS"
            system = folders[sn]
            with (system / "device.log").open("a", encoding="utf-8") as log:
                log.write(f"RESULT={result}\nTEST COMPLETE\n")
            (system / "records.csv").write_text(f"test,status\nB482 Demo,{result}\n", encoding="utf-8")
            with self.lock:
                self.batches[batch]["status"][sn] = result


def station_line(station: str) -> str:
    return f"B482 {station} simulated test started"


class Handler(SimpleHTTPRequestHandler):
    simulator: Simulator

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
    args = parser.parse_args()
    args.csv_root.mkdir(parents=True, exist_ok=True)
    Handler.simulator = Simulator(args.csv_root)
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"B482 Demo HMI: http://127.0.0.1:{args.port}")
    print(f"CSV root: {args.csv_root}")
    server.serve_forever()


if __name__ == "__main__": main()
