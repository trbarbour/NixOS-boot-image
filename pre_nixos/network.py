"""Network utilities."""

from __future__ import annotations

import errno
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Optional

from .logging_utils import log_event


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
    """Execute ``cmd`` when ``PRE_NIXOS_EXEC`` is ``1``."""

    log_event("pre_nixos.network.command.start", command=cmd)
    if os.environ.get("PRE_NIXOS_EXEC") != "1":
        log_event(
            "pre_nixos.network.command.skip",
            command=cmd,
            reason="execution disabled",
        )
        return

    result = subprocess.run(cmd, check=False)
    status = "success" if result.returncode == 0 else "error"
    log_event(
        "pre_nixos.network.command.finished",
        command=cmd,
        status=status,
        returncode=result.returncode,
    )
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, cmd)


def _systemctl(args: list[str], *, ignore_missing: bool = False) -> None:
    """Invoke ``systemctl`` with optional missing-unit tolerance."""

    command = ["systemctl", *args]
    log_event("pre_nixos.network.systemctl.start", command=command, ignore_missing=ignore_missing)
    if os.environ.get("PRE_NIXOS_EXEC") != "1":
        log_event(
            "pre_nixos.network.systemctl.skip",
            command=command,
            reason="execution disabled",
        )
        return

    result = subprocess.run(command, check=False)
    if result.returncode == 5 and ignore_missing:
        log_event(
            "pre_nixos.network.systemctl.ignored",
            command=command,
            returncode=result.returncode,
        )
        return

    status = "success" if result.returncode == 0 else "error"
    log_event(
        "pre_nixos.network.systemctl.finished",
        command=command,
        status=status,
        returncode=result.returncode,
    )
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, command)


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
            log_event(
                "pre_nixos.network.identify_lan.detected",
                interface=iface.name,
                signal="carrier",
            )
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
            log_event(
                "pre_nixos.network.identify_lan.detected",
                interface=iface.name,
                signal="operstate",
            )
            return iface.name
    return None


def wait_for_lan(
    net_path: Path = Path("/sys/class/net"),
    *,
    attempts: int = 30,
    delay: float = 2.0,
) -> Optional[str]:
    """Poll for an active LAN interface and return its name when detected."""

    log_event(
        "pre_nixos.network.wait_for_lan.start",
        attempts=attempts,
        delay_seconds=delay,
        net_path=net_path,
    )
    for _ in range(attempts):
        iface = identify_lan(net_path)
        if iface is not None:
            log_event(
                "pre_nixos.network.wait_for_lan.detected",
                interface=iface,
            )
            return iface
        time.sleep(delay)
    log_event("pre_nixos.network.wait_for_lan.timeout", attempts=attempts, delay_seconds=delay)
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

    log_event(
        "pre_nixos.network.write_lan_rename_rule.start",
        net_path=net_path,
        rules_dir=rules_dir,
    )

    iface = wait_for_lan(net_path)
    if iface is None:
        log_event(
            "pre_nixos.network.write_lan_rename_rule.skipped",
            reason="no interface detected",
        )
        return None

    rules_dir.mkdir(parents=True, exist_ok=True)
    rule_path = rules_dir / "10-lan.link"
    rule_path.write_text(
        f"[Match]\nOriginalName={iface}\n\n[Link]\nName=lan\n",
        encoding="utf-8",
    )
    log_event(
        "pre_nixos.network.write_lan_rename_rule.finished",
        interface=iface,
        rule_path=rule_path,
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

    log_event(
        "pre_nixos.network.secure_ssh.start",
        ssh_dir=ssh_dir,
        ssh_service=ssh_service,
        authorized_key=authorized_key,
    )

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
        log_event(
            "pre_nixos.network.secure_ssh.error",
            reason="missing authorized key",
            authorized_key=authorized_key,
        )
        raise FileNotFoundError(
            f"Missing {authorized_key}. Place your public key at this path before building."
        )
    root_ssh = root_home / ".ssh"
    root_ssh.mkdir(parents=True, exist_ok=True)
    auth_path = root_ssh / "authorized_keys"
    auth_path.write_text(authorized_key.read_text(), encoding="utf-8")
    os.chmod(root_ssh, 0o700)
    os.chmod(auth_path, 0o600)

    log_event(
        "pre_nixos.network.secure_ssh.authorized_key_written",
        authorized_keys_path=auth_path,
    )

    _systemctl(["start", ssh_service])
    _systemctl(["reload", ssh_service])
    log_event(
        "pre_nixos.network.secure_ssh.finished",
        authorized_keys_path=auth_path,
    )
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

    log_event(
        "pre_nixos.network.configure_lan.start",
        net_path=net_path,
        network_dir=network_dir,
        ssh_dir=ssh_dir,
        ssh_service=ssh_service,
        authorized_key=authorized_key,
        root_home=root_home,
    )

    if authorized_key is None:
        authorized_key = Path(__file__).with_name("root_key.pub")
    if not authorized_key.exists():
        log_event(
            "pre_nixos.network.configure_lan.skipped",
            reason="missing authorized key",
            authorized_key=authorized_key,
        )
        return None

    iface = wait_for_lan(net_path)
    if iface is None:
        log_event(
            "pre_nixos.network.configure_lan.no_interface",
            message="no interface with carrier detected",
        )
        secure_ssh(ssh_dir, ssh_service, authorized_key, root_home)
        return None

    log_event(
        "pre_nixos.network.configure_lan.detected_interface",
        interface=iface,
    )
    write_lan_rename_rule(net_path, network_dir)

    network_dir.mkdir(parents=True, exist_ok=True)
    net_path_conf = network_dir / "20-lan.network"
    net_path_conf.write_text(
        "[Match]\nName=lan\n\n[Network]\nDHCP=yes\n",
        encoding="utf-8",
    )
    log_event(
        "pre_nixos.network.configure_lan.network_file_written",
        network_file=net_path_conf,
    )

    # Rename the interface for the current session and ensure networking/SSH
    # services are active.
    _run(["ip", "link", "set", iface, "down"])
    _run(["ip", "link", "set", iface, "name", "lan"])
    _run(["ip", "link", "set", "lan", "up"])
    _systemctl(["restart", "systemd-networkd"], ignore_missing=True)
    secure_ssh(ssh_dir, ssh_service, authorized_key, root_home)

    log_event(
        "pre_nixos.network.configure_lan.finished",
        interface=iface,
        network_file=net_path_conf,
    )
    return net_path_conf
