"""Network utilities."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional


def _run(cmd: list[str]) -> None:
    """Execute ``cmd`` when ``PRE_NIXOS_EXEC`` is ``1``.

    Commands are executed without shell interpretation and failures are not
    silently ignored.
    """

    if os.environ.get("PRE_NIXOS_EXEC") != "1":
        return
    subprocess.run(cmd, check=True)


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


def secure_ssh(
    ssh_dir: Path,
    ssh_service: str = "ssh",
    authorized_key: Optional[Path] = None,
    root_home: Path = Path("/root"),
) -> Path:
    """Disable password authentication and provision a root SSH key.

    The main ``sshd_config`` file is updated to prohibit password logins, the
    root password is locked, an authorized key is installed for the root
    account, and the SSH service is enabled and reloaded.
    """

    ssh_dir.mkdir(parents=True, exist_ok=True)
    conf_path = ssh_dir / "sshd_config"
    existing = conf_path.read_text(encoding="utf-8") if conf_path.exists() else ""
    if conf_path.is_symlink():
        conf_path.unlink()
    if existing and not existing.endswith("\n"):
        existing += "\n"
    conf_path.write_text(
        existing + "PermitRootLogin prohibit-password\nPasswordAuthentication no\n",
        encoding="utf-8",
    )

    if authorized_key is None:
        authorized_key = Path(__file__).with_name("root_ed25519.pub")
    if not authorized_key.exists():
        raise FileNotFoundError(
            f"Missing {authorized_key}. Place your public key at this path before building."
        )
    root_ssh = root_home / ".ssh"
    root_ssh.mkdir(parents=True, exist_ok=True)
    auth_path = root_ssh / "authorized_keys"
    auth_path.write_text(authorized_key.read_text(), encoding="utf-8")
    os.chmod(root_ssh, 0o700)
    os.chmod(auth_path, 0o600)

    _run(["passwd", "-l", "root"])
    _run(["systemctl", "enable", "--now", ssh_service])
    _run(["systemctl", "reload", ssh_service])
    return conf_path


def configure_lan(
    net_path: Path = Path("/sys/class/net"),
    network_dir: Path = Path("/etc/systemd/network"),
    ssh_dir: Path = Path("/etc/ssh"),
    ssh_service: str = "ssh",
    authorized_key: Optional[Path] = None,
    root_home: Path = Path("/root"),
) -> Optional[Path]:
    """Configure the active NIC for DHCP and enable secure SSH access.

    The interface with an active carrier is renamed to ``lan`` via a persistent
    systemd ``.link`` file and renamed immediately for the running system.  A
    matching ``.network`` file enables DHCP.  When execution is enabled
    (``PRE_NIXOS_EXEC=1`` – set by the boot ISO) the interface is brought up,
    networkd is restarted and the SSH service is secured and enabled.

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
    secure_ssh(ssh_dir, ssh_service, authorized_key, root_home)

    return net_path_conf
