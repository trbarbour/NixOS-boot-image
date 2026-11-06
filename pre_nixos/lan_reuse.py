"""Reuse the LAN the boot-time run configured (task queue item 35).

``network.configure_lan`` renames the NIC to ``lan``, bounces the link and
waits up to 60 s for a DHCP lease.  The boot-time run does that once; a manual
run of ``pre-nixos`` or ``pre-nixos-tui`` later in the same boot reuses its
result, recorded in the runtime state directory (``/run/pre-nixos``, so a
reboot forgets it).

The record is reused only while what it describes still holds: the ``lan``
interface exists with the recorded MAC address, and the recorded files exist.
Otherwise the LAN is configured afresh and the record replaced.  Nothing is
recorded when no interface had a carrier, so a later run looks for a link
again (a cable plugged in since boot).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from . import network, state
from .logging_utils import log_event
from .network import LanConfiguration

_FILENAME = "lan-configuration.json"
_NET_PATH = Path("/sys/class/net")
_OPTIONAL_PATHS = ("rename_rule", "network_unit")


def lan_configuration_path(*, state_dir: Optional[Path] = None) -> Path:
    base = state_dir if state_dir is not None else state.default_state_dir()
    return base / _FILENAME


def _to_json(config: LanConfiguration) -> Dict[str, Optional[str]]:
    def text(value: Optional[Path]) -> Optional[str]:
        return None if value is None else str(value)

    return {
        "authorized_key": str(config.authorized_key),
        "interface": config.interface,
        "rename_rule": text(config.rename_rule),
        "network_unit": text(config.network_unit),
        "mac_address": config.mac_address,
    }


def _from_json(data: Any) -> Optional[LanConfiguration]:
    if not isinstance(data, dict):
        return None
    key = data.get("authorized_key")
    if not isinstance(key, str):
        return None
    optional = {
        name: data.get(name)
        for name in ("interface", "mac_address", *_OPTIONAL_PATHS)
    }
    if not all(value is None or isinstance(value, str) for value in optional.values()):
        return None

    def path(name: str) -> Optional[Path]:
        value = optional[name]
        return None if value is None else Path(value)

    return LanConfiguration(
        authorized_key=Path(key),
        interface=optional["interface"],
        rename_rule=path("rename_rule"),
        network_unit=path("network_unit"),
        mac_address=optional["mac_address"],
    )


def record_lan_configuration(
    config: LanConfiguration, *, state_dir: Optional[Path] = None
) -> Path:
    """Write ``config`` (atomically) and return the record's path."""

    path = lan_configuration_path(state_dir=state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".tmp")
    partial.write_text(json.dumps(_to_json(config), indent=2, sort_keys=True), encoding="utf-8")
    os.replace(partial, path)
    return path


def load_lan_configuration(*, state_dir: Optional[Path] = None) -> Optional[LanConfiguration]:
    """The recorded configuration, or ``None`` when absent or malformed."""

    path = lan_configuration_path(state_dir=state_dir)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as error:
        log_event("pre_nixos.network.ensure_lan.record_unreadable", record=path, error=str(error))
        return None
    try:
        return _from_json(json.loads(text))
    except json.JSONDecodeError:
        return None


def _stale_reason(config: LanConfiguration, net_path: Path) -> Optional[str]:
    """Why ``config`` no longer describes this machine, or ``None`` if it does."""

    if config.interface != "lan":
        return f"recorded interface is {config.interface!r}, not 'lan'"
    if not (net_path / "lan").exists():
        return "no 'lan' interface"
    if config.mac_address is not None:
        current = network._read_mac_address(net_path, "lan")
        if current != config.mac_address:
            return f"'lan' has MAC address {current!r}, not {config.mac_address!r}"
    for name in ("authorized_key", *_OPTIONAL_PATHS):
        value = getattr(config, name)
        if value is not None and not value.exists():
            return f"{name} {value} is missing"
    return None


def ensure_lan(
    *, net_path: Optional[Path] = None, state_dir: Optional[Path] = None
) -> Optional[LanConfiguration]:
    """The LAN configuration: the boot's, if still valid, else a fresh one."""

    net_path = net_path if net_path is not None else _NET_PATH
    record_path = lan_configuration_path(state_dir=state_dir)
    recorded = load_lan_configuration(state_dir=state_dir)
    if recorded is not None:
        reason = _stale_reason(recorded, net_path)
        if reason is None:
            log_event("pre_nixos.network.ensure_lan.reused", record=record_path)
            return recorded
        log_event("pre_nixos.network.ensure_lan.stale", record=record_path, reason=reason)
        try:
            record_path.unlink(missing_ok=True)
        except OSError as error:
            log_event("pre_nixos.network.ensure_lan.record_failed", record=record_path, error=str(error))

    config = network.configure_lan()
    if config is None or config.interface is None:
        return config
    try:
        record_lan_configuration(config, state_dir=state_dir)
    except OSError as error:
        log_event(
            "pre_nixos.network.ensure_lan.record_failed",
            record=record_path,
            error=str(error),
        )
    return config
