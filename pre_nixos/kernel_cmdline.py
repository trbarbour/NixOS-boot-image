"""The kernel command line (``/proc/cmdline``), shared by the modules that read
boot parameters (install, storage detection, the disk wait)."""

from __future__ import annotations

from pathlib import Path
from typing import Tuple

PROC_CMDLINE = Path("/proc/cmdline")


def tokens(path: Path = PROC_CMDLINE) -> Tuple[str, ...]:
    """The whitespace-separated tokens; none when it cannot be read."""

    try:
        return tuple(path.read_text(encoding="utf-8").split())
    except OSError:
        return ()
