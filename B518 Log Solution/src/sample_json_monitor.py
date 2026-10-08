"""Controlled JSON Lines source used to verify the platform extension seam."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from log_monitoring import BaseMonitor, MonitorEvent, TERMINAL


@dataclass(frozen=True)
class SampleObservation:
    kind: str
    position: int
    sn: str
    status: str
    source: str
    source_id: str
    source_time: str
    batch_id: str
    message: str = ""
    message_id: str = ""

    def evidence(self) -> Dict[str, str]:
        evidence = {
            "source_id": self.source_id,
            "source_time": self.source_time or "unknown",
            "format": "sample-json/v1",
        }
        if self.position > 0:
            evidence["source_position"] = str(self.position)
        if self.batch_id:
            evidence.update({
                "batch_id": self.batch_id,
                "round_evidence_id": "sample-json:{}:{}".format(self.batch_id, self.position),
                "same_round_evidence": "explicit_sample_batch_id_and_position",
            })
        return evidence


class SampleJsonLinesSource:
    """Consume only complete appended JSON records; never infer source evidence."""

    def __init__(self, root: Path, slots: Sequence[int]):
        self.root = Path(root)
        self.slots = set(slots)
        self._offsets = {}
        self._line_numbers = {}
        self._read_failures = {}
        if self.root.is_dir():
            for path in self.root.glob("*.jsonl"):
                try:
                    self._offsets[path] = path.stat().st_size
                except OSError:
                    continue

    def poll(self) -> tuple:
        observations = []
        if not self.root.is_dir():
            return ()
        for path in sorted(self.root.glob("*.jsonl")):
            try:
                with path.open("rb") as handle:
                    offset = self._offsets.get(path, 0)
                    handle.seek(offset)
                    content = handle.read()
            except OSError as error:
                failure = str(error)
                if self._read_failures.get(path) != failure:
                    self._read_failures[path] = failure
                    observations.append(self._warning(
                        path, path.name, "{}: {}".format(path.name, failure),
                        "platform.sample_json.unreadable",
                    ))
                continue
            self._read_failures.pop(path, None)
            last_newline = content.rfind(b"\n")
            if last_newline < 0:
                continue
            complete = content[:last_newline + 1]
            self._offsets[path] = offset + len(complete)
            for line_number, raw in enumerate(complete.splitlines(), start=1):
                if not raw.strip():
                    continue
                absolute_line = self._line_numbers.get(path, 0) + line_number
                source_id = "{}#{}".format(path.name, absolute_line)
                try:
                    value = json.loads(raw.decode("utf-8"))
                    observation = self._parse(value, path, source_id)
                except (UnicodeDecodeError, json.JSONDecodeError) as error:
                    observation = self._warning(path, source_id,
                                                "JSON Lines 記錄格式錯誤：{}".format(error),
                                                "platform.sample_json.invalid_record")
                if observation is not None:
                    observations.append(observation)
            self._line_numbers[path] = self._line_numbers.get(path, 0) + len(complete.splitlines())
        order = {"warning": -1, "activity": 0, "final": 1}
        return tuple(sorted(observations, key=lambda item: (
            item.source_time or "", item.position, order[item.kind], item.batch_id,
            item.sn, item.status, item.source_id,
        )))

    def _parse(self, value, path: Path, source_id: str) -> Optional[SampleObservation]:
        if not isinstance(value, dict):
            return self._warning(path, source_id, "JSON Lines 記錄必須是物件。",
                                 "platform.sample_json.invalid_record")
        kind = value.get("kind")
        position = value.get("position")
        if kind not in {"activity", "final"} or type(position) is not int or not 1 <= position <= 20:
            return self._warning(path, source_id, "JSON Lines 記錄的 kind／position 不受支援。",
                                 "platform.sample_json.unsupported_record")
        sn = value.get("sn", "")
        source_time = value.get("source_time", "")
        batch_id = value.get("batch_id", "")
        if not all(isinstance(item, str) for item in (sn, source_time, batch_id)):
            return self._warning(path, source_id, "JSON Lines 的 SN、時間與批次識別必須是文字。",
                                 "platform.sample_json.invalid_fields")
        if kind == "activity":
            status = "TESTING"
        else:
            status = value.get("status")
            if status not in {"PASS", "FAIL", "NOTEST"}:
                return self._warning(path, source_id, "JSON Lines final 狀態不受支援。",
                                     "platform.sample_json.invalid_status")
        return SampleObservation(kind, position, sn, status, str(path), source_id,
                                 source_time, batch_id)

    @staticmethod
    def _warning(path: Path, source_id: str, message: str,
                 message_id: str) -> SampleObservation:
        return SampleObservation("warning", 0, "", "", str(path), source_id, "", "",
                                 message, message_id)


class SampleJsonLogMonitor(BaseMonitor):
    """Translate controlled source records to the existing shared round API."""

    def __init__(self, source_root: Path, slots: Sequence[int], **kwargs):
        super().__init__("FCT", {"format": "sample-json/v1", "source_root": str(source_root)},
                         slots, **kwargs)
        self.source = SampleJsonLinesSource(source_root, slots)

    def poll_once(self) -> None:
        if self.finished or self._stop.is_set():
            return
        for observation in self.source.poll():
            evidence = observation.evidence()
            if observation.kind == "warning":
                evidence["raw_diagnostic"] = observation.message
                self.emit(MonitorEvent("warning", observation.message,
                                       source=observation.source, detail=evidence,
                                       message_id=observation.message_id,
                                       message_parameters={"source_filename": Path(
                                           observation.source).name},
                                       diagnostic=observation.message))
                continue
            if observation.position not in self.results:
                candidate = MonitorEvent(
                    "result_candidate", "受控樣本包含未映射來源位置",
                    observation.position, observation.sn, observation.status,
                    observation.source, evidence,
                )
                if self.callback:
                    self.callback(candidate)
                continue
            current = self.results[observation.position]
            if observation.kind == "activity" and current.status in TERMINAL:
                continue
            if observation.kind == "final" and current.status in TERMINAL:
                candidate = MonitorEvent(
                    "result_candidate", "受控樣本提供新的最終結果候選",
                    observation.position, observation.sn, observation.status,
                    observation.source, evidence,
                )
                if self.callback:
                    self.callback(candidate)
                continue
            self.set_result(observation.position, observation.status, observation.sn,
                            observation.source, evidence)
