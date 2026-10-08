"""Prepare a fixed profile-backed round without depending on the desktop UI."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Mapping, Optional

from configured_monitor import ConfiguredMonitor
from machine_profiles import MachineProfile, ProfileError, validate_profile
from monitoring_round import RoundCoordinator, RoundSnapshot
from platform_registry import DEFAULT_PLATFORM_REGISTRY, PlatformRegistry


def configured_directory(value: str) -> Optional[Path]:
    """Resolve a configured directory while treating blank values as absent."""
    text = value.strip()
    if not text:
        return None
    path = Path(text).expanduser()
    try:
        return path if path.is_dir() and os.access(str(path), os.R_OK | os.X_OK) else None
    except OSError:
        return None


def _fixed_profile(profile: MachineProfile) -> MachineProfile:
    """Copy mutable configuration fields so later edits cannot affect this round."""
    return MachineProfile(
        project=profile.project,
        machine=profile.machine,
        platform=profile.platform,
        capacity=profile.capacity,
        paths=MappingProxyType(dict(profile.paths)),
        mapping=tuple((source, display) for source, display in profile.mapping),
        timeouts=MappingProxyType(dict(profile.timeouts)),
    )


@dataclass(frozen=True)
class PreparedRoundStart:
    """A validated, immutable start request ready for the shared coordinator."""

    _profile: MachineProfile
    _paths: Mapping[str, Optional[Path]]
    _session_root: Path
    _registry: PlatformRegistry
    _async_session_writes: bool
    _now: Optional[Callable]
    _monotonic: Optional[Callable]

    @property
    def station(self) -> str:
        return self._profile.machine

    @property
    def capacity(self) -> int:
        return self._profile.capacity

    @property
    def round_timeout_seconds(self) -> int:
        return self._profile.timeouts["round"]

    def start(self, coordinator: RoundCoordinator, run_async: bool = True) -> RoundSnapshot:
        """Accept this prepared configuration through the existing round API."""
        profile = self._profile
        paths = dict(self._paths)
        timeouts = dict(profile.timeouts)
        mapping = dict(profile.mapping)
        source_slots = tuple(source for source, _display in profile.mapping)
        registry = self._registry
        session_root = self._session_root
        async_session_writes = self._async_session_writes
        now = self._now
        monotonic = self._monotonic

        def monitor_factory(on_event):
            view_holder = {}

            def deliver(event):
                view = view_holder.get("view")
                if view is not None:
                    return view.deliver(event, on_event)
                return on_event(event)

            context = {
                "station": profile.machine,
                "paths": paths,
                "source_slots": source_slots,
                "callback": deliver,
                "timeouts": timeouts,
                "session_root": session_root,
                "async_session_writes": async_session_writes,
            }
            if now is not None:
                context["now"] = now
            if monotonic is not None:
                context["monotonic"] = monotonic
            monitor = registry.create_monitor(profile.platform, **context)
            configured = ConfiguredMonitor(monitor, mapping)
            configured.update_round_settings({
                "profile_snapshot": {
                    "schema_version": 1,
                    "profile": profile.to_dict(),
                },
            })
            view_holder["view"] = configured
            return configured

        profile_data = profile.to_dict()
        audit_context = {
            "project": profile.project,
            "machine": profile.machine,
            "platform": profile.platform,
            "profile_version": 1,
            "config_snapshot": profile_data,
            "capacity": profile.capacity,
            "mapping": [
                {"source": source, "display": display}
                for source, display in profile.mapping
            ],
            # Keep the configured values in the audit record; adapters receive
            # validated paths separately and may resolve them for use.
            "paths": dict(profile.paths),
            "timeouts": timeouts,
        }
        return coordinator.start(
            profile.machine,
            monitor_factory,
            run_async=run_async,
            round_timeout_seconds=timeouts["round"],
            capacity=profile.capacity,
            audit_context=audit_context,
        )


class RoundStartPreparation:
    """Validate and freeze the selected profile before a round is accepted."""

    def __init__(self, registry: PlatformRegistry = DEFAULT_PLATFORM_REGISTRY):
        self._registry = registry

    def prepare(self, profile: MachineProfile, session_root: Path,
                async_session_writes: bool = True, now: Optional[Callable] = None,
                monotonic: Optional[Callable] = None) -> PreparedRoundStart:
        """Validate source access and capture all values needed for one round."""
        validate_profile(profile)
        fixed_profile = _fixed_profile(profile)
        definition = self._registry.get(fixed_profile.platform)
        resolved_paths = {}

        for field in definition.required_paths:
            directory = configured_directory(fixed_profile.paths.get(field, ""))
            if directory is None:
                label = definition.path_labels.get(field, field)
                raise ProfileError("請設定存在且可讀取的{}。".format(label))
            resolved_paths[field] = directory

        for field in definition.optional_paths:
            configured = fixed_profile.paths.get(field, "")
            directory = configured_directory(configured) if configured.strip() else None
            if configured.strip() and directory is None:
                label = definition.path_labels.get(field, field)
                raise ProfileError("{} 不存在或無法讀取。".format(label))
            resolved_paths[field] = directory

        return PreparedRoundStart(
            _profile=fixed_profile,
            _paths=MappingProxyType(resolved_paths),
            _session_root=Path(session_root),
            _registry=self._registry,
            _async_session_writes=async_session_writes,
            _now=now,
            _monotonic=monotonic,
        )
