"""Built-in platform capabilities and monitor construction registry."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Mapping, Tuple


@dataclass(frozen=True)
class PlatformDefinition:
    name: str
    machines: Tuple[str, ...]
    source_positions: Tuple[int, ...]
    required_paths: Tuple[str, ...]
    optional_paths: Tuple[str, ...]
    path_labels: Mapping[str, str]
    monitor_factory: Callable[..., object]


class PlatformRegistry:
    """Register supported formats and their configuration and adapter boundary."""

    def __init__(self):
        self._definitions = {}  # type: Dict[str, PlatformDefinition]

    def register(self, definition: PlatformDefinition) -> None:
        if not definition.name or definition.name in self._definitions:
            raise ValueError("平台名稱不可空白或重複：{}。".format(definition.name))
        if (not definition.machines or not definition.source_positions or
                any(position < 1 for position in definition.source_positions)):
            raise ValueError("平台必須宣告機型與正整數來源位置。")
        if len(set(definition.source_positions)) != len(definition.source_positions):
            raise ValueError("平台來源位置不可重複。")
        if set(definition.required_paths).intersection(definition.optional_paths):
            raise ValueError("平台必要與選填路徑不可重複。")
        self._definitions[definition.name] = definition

    def get(self, name: str) -> PlatformDefinition:
        try:
            return self._definitions[name]
        except KeyError:
            raise ValueError("未知平台：{}。".format(name))

    @property
    def names(self) -> Tuple[str, ...]:
        return tuple(self._definitions)

    def create_monitor(self, name: str, **context):
        return self.get(name).monitor_factory(**context)


def _base_context(context):
    timeouts = context["timeouts"]
    return {
        "callback": context["callback"],
        "session_root": context["session_root"],
        "async_session_writes": context["async_session_writes"],
        "start_timeout_seconds": timeouts["start"],
        "test_timeout_seconds": timeouts["test"],
        "round_timeout_seconds": timeouts["round"],
    }


def _atlas_monitor(**context):
    from log_monitoring import AtlasActiveArchiveMonitor

    return AtlasActiveArchiveMonitor(
        context["station"], context["paths"]["active"], context["paths"]["final"],
        context["source_slots"], **_base_context(context),
    )


def _b482_monitor(**context):
    from log_monitoring import BtLogMonitor

    return BtLogMonitor(
        context["paths"]["final"], context["source_slots"],
        caseinfo_root=context["paths"].get("caseinfo"), **_base_context(context),
    )


def _rswmt_monitor(**context):
    from rswmt_monitoring import RsWmtLogMonitor

    return RsWmtLogMonitor(
        context["paths"]["final"], slots=context["source_slots"],
        progress_root=context["paths"].get("caseinfo"), **_base_context(context),
    )


def _sample_json_monitor(**context):
    from sample_json_monitor import SampleJsonLogMonitor

    return SampleJsonLogMonitor(
        context["paths"]["active"], context["source_slots"], **_base_context(context),
    )


def _built_in_registry() -> PlatformRegistry:
    from atlas_source_adapter import MAX_SOURCE_POSITION as atlas_max
    from b482_source_adapter import MAX_SOURCE_POSITION as b482_max
    from rswmt_source_adapter import MAX_SOURCE_POSITION as rswmt_max

    registry = PlatformRegistry()
    registry.register(PlatformDefinition(
        "atlas", ("DFU", "FCT"), tuple(range(1, atlas_max + 1)),
        ("active", "final"), (),
        {"active": "Atlas 即時 Log 路徑", "final": "Atlas 最終結果路徑"}, _atlas_monitor,
    ))
    registry.register(PlatformDefinition(
        "b482", ("BT",), tuple(range(1, b482_max + 1)), ("final",), ("caseinfo",),
        {"final": "B482 TestData 根路徑", "caseinfo": "B482 CaseInfo／進度路徑（選填）"}, _b482_monitor,
    ))
    registry.register(PlatformDefinition(
        "rswmt", ("BT",), tuple(range(1, rswmt_max + 1)), ("final",), ("caseinfo",),
        {"final": "RS-WMT output/SmtCal", "caseinfo": "RS-WMT Live logs（選填）"}, _rswmt_monitor,
    ))
    registry.register(PlatformDefinition(
        "sample-json", ("FCT",), tuple(range(1, 21)), ("active",), (),
        {"active": "受控 JSON Lines 樣本來源"}, _sample_json_monitor,
    ))
    return registry


DEFAULT_PLATFORM_REGISTRY = _built_in_registry()

