"""Network utilities."""

from __future__ import annotations

import errno
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Optional


_TRANSIENT_SYSFS_ERRNOS = {
    errno.EINVAL,
    errno.ENODEV,
    errno.ENXIO,
}


def _is_transient_sysfs_error(error: OSError) -> bool:
    """Return ``True`` for ignorable sysfs read errors."""

    err_no = error.errno
    if err_no in _TRANSIENT_SYSFS_ERRNOS:
        return True
    # Some kernels surface transient sysfs read failures with ``errno`` unset
    # (``None``) or ``0``.  Treat these as soft failures so the caller can
    # retry or fall back to alternative signals.
    if err_no in (None, 0):
        return True
    return False


def _run(cmd: list[str]) -> None:
    """Execute ``cmd`` when ``PRE_NIXOS_EXEC`` is ``1``.

    Commands are executed without shell interpretation and failures are not
    silently ignored.
    """

    if os.environ.get("PRE_NIXOS_EXEC") != "1":
        return
    subprocess.run(cmd, check=True)


def _systemctl(args: list[str], *, ignore_missing: bool = False) -> None:
    """Invoke ``systemctl`` with optional missing-unit tolerance."""

    if os.environ.get("PRE_NIXOS_EXEC") != "1":
        return
    result = subprocess.run(["systemctl", *args], check=False)
    if result.returncode == 5 and ignore_missing:
        print(
            "systemctl {}: unit missing; skipping".format(" ".join(args)),
            flush=True,
        )
        return
    result.check_returncode()


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
            carrier_path = iface / "carrier"
            carrier = carrier_path.read_text().strip()
        except FileNotFoundError:
            carrier = None
        except OSError as error:
            if _is_transient_sysfs_error(error):
                carrier = None
            else:
                raise
        if carrier == "1":
            return iface.name
        if carrier is not None:
            continue

        # Some virtual interfaces (notably virtio) briefly reject ``carrier``
        # reads while still exposing link state via ``operstate``.  When the
        # carrier cannot be determined, fall back to ``operstate`` to avoid
        # crashing during provisioning.
        try:
            operstate = (iface / "operstate").read_text().strip().lower()
        except FileNotFoundError:
            continue
        except OSError as error:
            if _is_transient_sysfs_error(error):
                continue
            raise
        if operstate == "up":
            return iface.name
    return None


def wait_for_lan(
    net_path: Path = Path("/sys/class/net"),
    *,
    attempts: int = 30,
    delay: float = 2.0,
) -> Optional[str]:
    """Poll for an active LAN interface and return its name when detected."""

    for _ in range(attempts):
        iface = identify_lan(net_path)
        if iface is not None:
            return iface
        time.sleep(delay)
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

    iface = wait_for_lan(net_path)
    if iface is None:
        return None

    rules_dir.mkdir(parents=True, exist_ok=True)
    rule_path = rules_dir / "10-lan.link"
    rule_path.write_text(
        f"[Match]\nOriginalName={iface}\n\n[Link]\nName=lan\n",
        encoding="utf-8",
    )
    return rule_path


def get_ip_address(iface: str = "lan") -> Optional[str]:
    """Return the IPv4 address of ``iface``.

    Parameters:
        iface: Name of the network interface to query.

    Returns:
        The IPv4 address as a string, or ``None`` if the interface has no
        address or the query fails.
    """

    try:
        result = subprocess.run(
            ["ip", "-j", "-4", "addr", "show", iface],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError:
        return None

    try:
        payload = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return None

    if not isinstance(payload, list):
        return None

    for entry in payload:
        if not isinstance(entry, dict):
            continue
        for addr in entry.get("addr_info", []):
            if not isinstance(addr, dict):
                continue
            if addr.get("family") != "inet":
                continue
            local = addr.get("local")
            if isinstance(local, str) and local:
                return local
    return None


def get_lan_status(authorized_key: Optional[Path] = None, iface: str = "lan") -> str:
    """Return the LAN IP address or diagnostic message for the TUI.

    If the embedded public SSH key is missing, ``secure_ssh`` never ran and
    the TUI should inform the operator.  When the key exists but no IPv4
    address is assigned to ``iface``, a different message is returned.

    Parameters:
        authorized_key: Path to the expected public key; defaults to the
            built-in key alongside this module.
        iface: Interface name to query for an IP address.

    Returns:
        Either the IPv4 address as a string or a message describing why the
        address is unavailable.
    """

    if authorized_key is None:
        authorized_key = Path(__file__).with_name("root_key.pub")
    if not authorized_key.exists():
        return "missing SSH public key"
    ip = get_ip_address(iface)
    if ip is None:
        return "no IP address"
    return ip


def secure_ssh(
    ssh_dir: Path,
    ssh_service: str = "sshd",
    authorized_key: Optional[Path] = None,
    root_home: Path = Path("/root"),
) -> Path:
    """Disable SSH password login and provision a root SSH key.

    The main ``sshd_config`` file is updated to prohibit password logins,
    an authorized key is installed for the root account, and the SSH service
    is started and reloaded. The root password itself remains usable for
    console logins.
    """

    ssh_dir.mkdir(parents=True, exist_ok=True)
    conf_path = ssh_dir / "sshd_config"
    existing = conf_path.read_text(encoding="utf-8") if conf_path.exists() else ""
    if conf_path.is_symlink():
        conf_path.unlink()

    # Drop insecure directives from the existing configuration but preserve
    # everything else to minimise surprises for the user.
    sanitized: list[str] = []
    for line in existing.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            sanitized.append(line)
            continue
        parts = stripped.split()
        if len(parts) >= 2 and (
            (parts[0] == "PasswordAuthentication" and parts[1].lower() == "yes")
            or (parts[0] == "PermitRootLogin" and parts[1].lower() == "yes")
        ):
            continue
        sanitized.append(line)
    existing = "\n".join(sanitized)
    if existing and not existing.endswith("\n"):
        existing += "\n"
    conf_path.write_text(
        existing + "PermitRootLogin prohibit-password\nPasswordAuthentication no\n",
        encoding="utf-8",
    )

    if authorized_key is None:
        authorized_key = Path(__file__).with_name("root_key.pub")
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

    _systemctl(["start", ssh_service])
    _systemctl(["reload", ssh_service])
    return conf_path


def configure_lan(
    net_path: Path = Path("/sys/class/net"),
    network_dir: Path = Path("/etc/systemd/network"),
    ssh_dir: Path = Path("/etc/ssh"),
    ssh_service: str = "sshd",
    authorized_key: Optional[Path] = None,
    root_home: Path = Path("/root"),
) -> Optional[Path]:
    """Configure the active NIC for DHCP and optionally enable secure SSH.

    When a root public key is present, the interface with an active carrier is
    renamed to ``lan`` via a persistent systemd ``.link`` file and renamed
    immediately for the running system.  A matching ``.network`` file enables
    DHCP and SSH access is secured with the provided key.  If no key is
    available, networking and SSH are left in their NixOS boot image defaults.

    Returns the path to the created network file or ``None`` when no LAN
    interface is detected or no key is provided.
    """

    if authorized_key is None:
        authorized_key = Path(__file__).with_name("root_key.pub")
    if not authorized_key.exists():
        return None

    iface = wait_for_lan(net_path)
    if iface is None:
        print(
            "configure_lan: no interface with carrier detected; skipping LAN setup",
            flush=True,
        )
        secure_ssh(ssh_dir, ssh_service, authorized_key, root_home)
        return None

    print(f"configure_lan: detected active interface '{iface}'", flush=True)
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
    _systemctl(["restart", "systemd-networkd"], ignore_missing=True)
    secure_ssh(ssh_dir, ssh_service, authorized_key, root_home)

    return net_path_conf
