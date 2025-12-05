"""Helpers for managing pre-nixos runtime state artifacts."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

_STORAGE_PLAN_FILENAME = "storage-plan.json"
_INSTALL_NETWORK_FILENAME = "install-network.json"


def _default_state_dir() -> Path:
    """Return the default directory for runtime state artifacts."""

    override = os.environ.get("PRE_NIXOS_STATE_DIR")
    if override:
        return Path(override)
    return Path("/run/pre-nixos")


def storage_plan_path(*, state_dir: Optional[Path] = None) -> Path:
    """Return the path to the recorded storage plan JSON file."""

    base = state_dir if state_dir is not None else _default_state_dir()
    return base / _STORAGE_PLAN_FILENAME


def install_network_path(*, state_dir: Optional[Path] = None) -> Path:
    """Return the path to the recorded install-time network settings file."""

    base = state_dir if state_dir is not None else _default_state_dir()
    return base / _INSTALL_NETWORK_FILENAME


def record_storage_plan(plan: Dict[str, Any], *, state_dir: Optional[Path] = None) -> Path:
    """Persist ``plan`` to ``state_dir`` and return the written path."""

    path = storage_plan_path(state_dir=state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(plan, indent=2, sort_keys=True)
    path.write_text(text, encoding="utf-8")
    return path


def record_install_network_config(
    config: Dict[str, str], *, state_dir: Optional[Path] = None
) -> Path:
    """Persist static network configuration for the installer."""

    path = install_network_path(state_dir=state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(config, indent=2, sort_keys=True)
    path.write_text(text, encoding="utf-8")
    return path


def clear_install_network_config(*, state_dir: Optional[Path] = None) -> None:
    """Remove any persisted install-time network configuration."""

    path = install_network_path(state_dir=state_dir)
    try:
        path.unlink()
    except FileNotFoundError:
        return


def load_storage_plan(*, state_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Return the previously recorded storage plan when available."""

    path = storage_plan_path(state_dir=state_dir)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def load_install_network_config(
    *, state_dir: Optional[Path] = None
) -> Optional[Dict[str, str]]:
    """Return the persisted install-time network configuration when available."""

    path = install_network_path(state_dir=state_dir)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    address = data.get("address")
    netmask = data.get("netmask")
    gateway = data.get("gateway")
    if not all(isinstance(item, str) for item in (address, netmask, gateway)):
        return None
    return {"address": address, "netmask": netmask, "gateway": gateway}
