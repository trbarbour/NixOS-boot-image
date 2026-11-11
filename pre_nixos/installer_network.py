"""The installer adopts the static network settings (task queue item 41).

Design: plans/2026-11-11T183853Z-installer-static-network-design.md.

With no DHCP server, the installer's ``lan`` has no address, and saving static
settings for the installed system (TUI ``[C]``, ``pre-nixos
--install-ip-address``) used to leave the installer unconfigured.  The same
settings now go to the installer too, as a runtime systemd-networkd unit whose
name sorts before the boot's DHCP unit (``20-lan.network``), so networkd
prefers it.  It lives in ``/run`` and is gone at reboot.
"""

from __future__ import annotations

import enum
import re
import subprocess
from pathlib import Path
from typing import Callable, List, Optional, Sequence

from .install import InstallNetworkConfig
from .network import NetworkReadiness

UNIT_DIR = Path("/run/systemd/network")
UNIT_NAME = "10-lan-static.network"
INTERFACE = "lan"

Runner = Callable[[List[str]], None]


class Mode(enum.Enum):
    """When the installer adopts the static settings (R-N1)."""

    AUTO = "auto"  # only when the installer has no IPv4 address
    YES = "yes"
    NO = "no"


def _run(cmd: List[str]) -> None:
    subprocess.run(cmd, check=True)


def decide(mode: Mode, readiness: NetworkReadiness) -> bool:
    """Whether to configure the installer with the static settings."""

    if mode is Mode.YES:
        return True
    if mode is Mode.NO:
        return False
    return readiness.address is None


def parse_dns(text: str) -> List[str]:
    """DNS servers from a comma- or space-separated list."""

    return [item for item in re.split(r"[\s,]+", text.strip()) if item]


def render_unit(config: InstallNetworkConfig, *, mac_address: Optional[str]) -> str:
    """The networkd unit giving ``lan`` the static settings."""

    match = f"MACAddress={mac_address}" if mac_address else f"Name={INTERFACE}"
    lines = [
        "# pre-nixos: the installer's static network (task queue item 41)",
        "[Match]",
        match,
        "",
        "[Network]",
        "DHCP=no",
        f"Address={config.cidr}",
        f"Gateway={config.gateway}",
        *(f"DNS={server}" for server in config.dns),
    ]
    return "\n".join(lines) + "\n"


def _reconfigure(run: Runner) -> None:
    run(["networkctl", "reload"])
    run(["networkctl", "reconfigure", INTERFACE])


def apply(
    config: InstallNetworkConfig,
    *,
    mac_address: Optional[str],
    unit_dir: Path = UNIT_DIR,
    run: Runner = _run,
) -> Path:
    """Give the installer's ``lan`` the static settings; return the unit's path."""

    unit_dir.mkdir(parents=True, exist_ok=True)
    path = unit_dir / UNIT_NAME
    path.write_text(render_unit(config, mac_address=mac_address), encoding="utf-8")
    _reconfigure(run)
    return path


def remove(*, unit_dir: Path = UNIT_DIR, run: Runner = _run) -> bool:
    """Return the installer to DHCP (R-N3); ``False`` if there was nothing to undo."""

    path = unit_dir / UNIT_NAME
    if not path.exists():
        return False
    path.unlink()
    _reconfigure(run)
    return True


__all__ = ["INTERFACE", "Mode", "UNIT_DIR", "UNIT_NAME", "apply", "decide", "parse_dns", "remove", "render_unit"]
