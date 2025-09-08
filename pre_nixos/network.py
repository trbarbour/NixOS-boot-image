"""Network utilities."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional


def _run(cmd: list[str]) -> None:
    """Execute ``cmd`` when ``PRE_NIXOS_EXEC`` is set to ``1``.

    This best-effort helper allows the module to write configuration files during
    tests without attempting to invoke missing system utilities such as
    ``systemctl`` or ``ip``.
    """

    if os.environ.get("PRE_NIXOS_EXEC") != "1":
        return
    subprocess.run(cmd, check=False)


def identify_lan(net_path: Path = Path("/sys/class/net")) -> Optional[str]:
    """Identify the NIC with link and return its name.

    Args:
        net_path: Path to ``/sys/class/net`` (overridable for tests).

    Returns:
        Name of the first interface with carrier link or ``None`` if none found.
    """
    for iface in sorted(net_path.iterdir()):
        if not (iface / "device").exists():
            continue
        try:
            carrier = (iface / "carrier").read_text().strip()
        except FileNotFoundError:
            continue
        if carrier == "1":
            return iface.name
    return None


def write_lan_rename_rule(
    net_path: Path = Path("/sys/class/net"),
    rules_dir: Path = Path("/etc/systemd/network"),
) -> Optional[Path]:
    """Persistently rename the detected LAN interface to ``lan``.

    Parameters:
        net_path: Path to ``/sys/class/net`` for interface discovery.
        rules_dir: Directory where the systemd ``.link`` file will be written.

    Returns:
        Path to the written rule file or ``None`` if no active interface is found.
    """

    iface = identify_lan(net_path)
    if iface is None:
        return None

    rules_dir.mkdir(parents=True, exist_ok=True)
    rule_path = rules_dir / "10-lan.link"
    rule_path.write_text(
        f"[Match]\nOriginalName={iface}\n\n[Link]\nName=lan\n",
        encoding="utf-8",
    )
    return rule_path


def configure_lan(
    net_path: Path = Path("/sys/class/net"),
    network_dir: Path = Path("/etc/systemd/network"),
    ssh_service: str = "ssh",
) -> Optional[Path]:
    """Configure the active NIC for DHCP and enable SSH access.

    The interface with an active carrier is renamed to ``lan`` via a persistent
    systemd ``.link`` file and renamed immediately for the running system.  A
    matching ``.network`` file enables DHCP.  When execution is enabled
    (``PRE_NIXOS_EXEC=1``) the interface is brought up, networkd is restarted and
    the specified SSH service is enabled.

    Returns the path to the created network file or ``None`` when no LAN
    interface is detected.
    """

    iface = identify_lan(net_path)
    if iface is None:
        return None

    write_lan_rename_rule(net_path, network_dir)

    network_dir.mkdir(parents=True, exist_ok=True)
    net_path_conf = network_dir / "20-lan.network"
    net_path_conf.write_text(
        "[Match]\nName=lan\n\n[Network]\nDHCP=yes\n",
        encoding="utf-8",
    )

    # Rename the interface for the current session and ensure networking/SSH
    # services are active.
    _run(["ip", "link", "set", iface, "down"])
    _run(["ip", "link", "set", iface, "name", "lan"])
    _run(["ip", "link", "set", "lan", "up"])
    _run(["systemctl", "restart", "systemd-networkd"])
    _run(["systemctl", "enable", "--now", ssh_service])

    return net_path_conf
