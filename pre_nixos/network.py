"""Network utilities."""

from pathlib import Path
from typing import Optional


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
