"""The LAN announcement reaches each console exactly once (task queue item 29).

``pre_nixos/scripts/announce-lan-ip.sh`` runs on the installer (the boot
service) and on the installed system (``pre-nixos-auto-install-ip``).  It had
up to four ways to the console, independent of one another:
- its stdout, which the installed system's unit sent to ``journal+console``;
- the broadcast command (``pre-nixos-console``, absent on the installed system);
- a write to each active console;
- a "fallback" write to ``/dev/console``, which ran even when the active
  consoles had been written.  ``/dev/console`` is the primary console, which
  the active list already names (#327).

Rule, as ``pre_nixos.console`` already applies it: the broadcast command if it
works; otherwise each active console once; ``/dev/console`` only when no
console is known.  The console paths are overridable in the environment, as
``console.get_console_paths`` takes ``active_path``.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Dict, Optional

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "pre_nixos" / "scripts" / "announce-lan-ip.sh"
TEMPLATE = REPO / "pre_nixos" / "templates" / "auto-install-ip.nix"
MESSAGE = "LAN IPv4 address: 192.0.2.10"


def _run(tmp_path: Path, *, active: Optional[str], broadcast: Optional[str]) -> Dict[str, str]:
    """Run the script with fake consoles; return what each received."""

    dev = tmp_path / "dev"
    dev.mkdir()
    for name in ("ttyS0", "tty0", "console"):
        (dev / name).write_text("")
    active_file = tmp_path / "active"
    if active is not None:
        active_file.write_text(active + "\n")
    status = tmp_path / "network-status"
    status.write_text("LAN_IPV4=192.0.2.10\n")  # the script then needs no `ip`
    env = {
        "PATH": os.environ["PATH"],
        "ANNOUNCE_STATUS_FILE": str(status),
        "ANNOUNCE_MAX_ATTEMPTS": "1",
        "ANNOUNCE_DELAY": "0",
        "ANNOUNCE_NOTIFY_CONSOLES": "1",
        "ANNOUNCE_CONSOLE_FALLBACK": "1",
        "ANNOUNCE_STDOUT_MESSAGE": "1",
        "ANNOUNCE_CONSOLE_ACTIVE": str(active_file),
        "ANNOUNCE_DEV_DIR": str(dev),
        "BROADCAST_CONSOLE_CMD": broadcast or "",
    }
    result = subprocess.run(
        ["bash", str(SCRIPT)], env=env, capture_output=True, text=True, check=True
    )
    received = {name: (dev / name).read_text() for name in ("ttyS0", "tty0", "console")}
    received["stdout"] = result.stdout
    return received


def test_without_the_broadcast_command_each_active_console_gets_one_line(tmp_path: Path) -> None:
    """The installed system: no pre-nixos-console, two consoles."""

    got = _run(tmp_path, active="ttyS0 tty0", broadcast=None)
    assert got["ttyS0"] == MESSAGE + "\n"
    assert got["tty0"] == MESSAGE + "\n"
    assert got["console"] == ""  # the primary console, already written as ttyS0 or tty0


def test_with_a_working_broadcast_command_the_script_writes_no_console(tmp_path: Path) -> None:
    """The installer: pre-nixos-console has written every console already."""

    log = tmp_path / "broadcast.log"
    fake = tmp_path / "fake-broadcast"
    fake.write_text(f'#!/bin/sh\nprintf "%s\\n" "$1" >> {log}\n')
    fake.chmod(0o755)
    got = _run(tmp_path, active="ttyS0 tty0", broadcast=str(fake))
    assert log.read_text() == MESSAGE + "\n"
    assert (got["ttyS0"], got["tty0"], got["console"]) == ("", "", "")


def test_a_failing_broadcast_command_falls_back_to_the_consoles(tmp_path: Path) -> None:
    fake = tmp_path / "fake-broadcast"
    fake.write_text("#!/bin/sh\nexit 1\n")
    fake.chmod(0o755)
    got = _run(tmp_path, active="ttyS0", broadcast=str(fake))
    assert (got["ttyS0"], got["console"]) == (MESSAGE + "\n", "")


@pytest.mark.parametrize("active", [None, ""])
def test_dev_console_only_when_no_console_is_known(tmp_path: Path, active) -> None:
    got = _run(tmp_path, active=active, broadcast=None)
    assert got["console"] == MESSAGE + "\n"
    assert (got["ttyS0"], got["tty0"]) == ("", "")


def test_the_installed_service_keeps_stdout_off_the_console() -> None:
    """The script writes the consoles itself; ``journal+console`` added a copy."""

    text = TEMPLATE.read_text()
    service = text[text.index('systemd.services."pre-nixos-auto-install-ip"') :]
    service = service[: service.index("script =")]
    assert 'StandardOutput = "journal";' in service, service
    assert "journal+console" not in service, service
