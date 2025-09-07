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
