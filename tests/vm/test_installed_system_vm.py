"""End to end: install with a static address, boot the installed disks, SSH in.

Task queue items 12 and 46 (trbarbour/NixOS-boot-image#342).  On the first
BIOS PC (no DHCP server) the user installed with a static address; the
installed system booted but answered neither ping nor SSH, and its
``pre-nixos-auto-install-ip`` service reported "LAN IPv4 address
unavailable".  No test had booted an installed system before.

1. The installer VM (SSD plus an HDD pair, SeaBIOS, so a legacy-BIOS GRUB
   install) provisions its disks at boot; ``pre-nixos --install-now`` then
   installs with a static address.  QEMU's user network forwards to
   10.0.2.15, so that is the address, with gateway 10.0.2.2.  pre-nixos's
   reboot after the install is swallowed (``-no-reboot`` would end QEMU), and
   the VM is powered off.
   Before installing, the test plants the DHCP unit an earlier attempt left
   on the user's disk; the static address is not the one QEMU's DHCP server
   hands out, so a DHCP fallback fails the test.
2. A second QEMU boots the same disks, without the ISO, with the same NIC
   (QEMU's default MAC, which the installed system matches to rename it to
   ``lan``).  The test SSHes in through the port forward with the image's
   root key, and reads the address and route of ``lan``.

Task queue item 45 (reqs R-A1): the image is built with the test hashed root
password (tests/vm/fixtures.py), and the test plants an earlier attempt's
``/etc/shadow`` with root locked.  The installed system's root must have the
hash: NixOS alone would keep the old entry (design D4,
plans/2026-11-10T140423Z-root-password-design.md).
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import List

import pytest

from tests.root_password_data import TEST_ROOT_PASSWORD_HASH
from tests.vm.controller import BootImageVM
from tests.vm.scsi_disks import ScsiDisk, scsi_disk_args

pytestmark = [pytest.mark.vm, pytest.mark.slow]

INSTALL_TIMEOUT = 5400
BOOT_TIMEOUT = 900
# Not 10.0.2.15, the address QEMU's DHCP server hands out: if the installed
# system fell back to DHCP it would get .15, and SSH to .20 would fail.  The
# first version used .15 and passed although the static configuration was
# overridden (#342).
STATIC_ADDRESS = "10.0.2.20"
# The installer's DHCP unit, as an earlier, failed DHCP install on the user's
# PC left it in the target (#342).
STALE_DHCP_UNIT = "[Match]\nName=lan\n\n[Network]\nDHCP=yes\n"
# An earlier attempt's shadow file, root locked as NixOS writes it.
STALE_SHADOW = "root:!:1::::::\n"

# pre-nixos reboots after a successful install; under -no-reboot that would
# end QEMU in the middle of the command, so the stand-in only swallows it.
SYSTEMCTL_SHIM = """#!/bin/sh
if [ "$1" = reboot ]; then echo "systemctl reboot (skipped by the test)"; exit 0; fi
exec /run/current-system/sw/bin/systemctl "$@"
"""


def _free_port() -> int:
    import socket

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _ssh(ssh_executable: str, key: Path, port: int, command: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            ssh_executable, "-i", str(key),
            "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null", "-o", "ConnectTimeout=10",
            "-p", str(port), "root@127.0.0.1", command,
        ],
        capture_output=True, text=True, timeout=120,
    )


def test_installed_system_with_a_static_address_is_reachable(
    boot_image_vm_with_raid_disks: BootImageVM,
    raid_scsi_disks: List[ScsiDisk],
    qemu_executable: str,
    ssh_executable: str,
    boot_ssh_key_pair,
    tmp_path: Path,
) -> None:
    vm = boot_image_vm_with_raid_disks
    status = vm.wait_for_storage_status()
    assert status.get("STATE") == "applied", status

    vm.run_as_root_checked(
        "mkdir -p /root/shim && cat > /root/shim/systemctl <<'EOF'\n"
        + SYSTEMCTL_SHIM
        + "EOF\nchmod +x /root/shim/systemctl",
        timeout=60,
    )
    # The user's disk: an earlier DHCP attempt left the installer's unit.
    vm.run_as_root_checked(
        "mkdir -p /mnt/etc/systemd/network && printf '"
        + STALE_DHCP_UNIT.replace("\n", "\\n")
        + "' > /mnt/etc/systemd/network/20-lan.network",
        timeout=60,
    )
    vm.run_as_root_checked(
        "printf '" + STALE_SHADOW.replace("\n", "\\n")
        + "' > /mnt/etc/shadow && chmod 640 /mnt/etc/shadow",
        timeout=60,
    )
    out = vm.run_as_root(
        "PATH=/root/shim:$PATH pre-nixos --install-now"
        f" --install-ip-address {STATIC_ADDRESS} --install-netmask 255.255.255.0"
        " --install-gateway 10.0.2.2 > /tmp/install.log 2>&1; echo install-exit=$?",
        timeout=INSTALL_TIMEOUT,
    )
    log_tail = vm.run_as_root("grep -v '^copying path' /tmp/install.log | tail -n 40", timeout=120)
    assert "install-exit=0" in out, f"{out}\n{log_tail}"
    block = vm.run_as_root(
        "sed -n '/auto-install start/,/auto-install end/p' /mnt/etc/nixos/configuration.nix",
        timeout=60,
    )
    vm.shutdown()

    # Boot the installed disks: no ISO, same disks and NIC.
    port = _free_port()
    serial = tmp_path / "installed-serial.log"
    cmd = [
        qemu_executable, "-m", "2048", "-smp", "2", "-display", "none", "-no-reboot",
        "-serial", f"file:{serial}",
        *scsi_disk_args(raid_scsi_disks),
        "-netdev", f"user,id=net0,hostfwd=tcp:127.0.0.1:{port}-{STATIC_ADDRESS}:22",
        "-device", "virtio-net-pci,netdev=net0",
    ]
    installed = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        deadline = time.monotonic() + BOOT_TIMEOUT
        result = None
        while time.monotonic() < deadline and installed.poll() is None:
            result = _ssh(ssh_executable, boot_ssh_key_pair.private_key, port,
                          "ip -4 -o addr show lan; ip -4 route show default;"
                          " echo shadow-root=$(getent shadow root | cut -d: -f2)")
            if result.returncode == 0:
                break
            time.sleep(10)
        serial_tail = serial.read_text(errors="replace")[-6000:] if serial.exists() else ""
        assert result is not None and result.returncode == 0, (
            "no SSH to the installed system\n--- managed block ---\n"
            f"{block}\n--- serial (tail) ---\n{serial_tail}"
        )
        assert f"inet {STATIC_ADDRESS}/24" in result.stdout, result.stdout
        assert "default via 10.0.2.2" in result.stdout, result.stdout
        # R-A1: root can log in on the console with the site's password.
        assert f"shadow-root={TEST_ROOT_PASSWORD_HASH}" in result.stdout, result.stdout
    finally:
        installed.terminate()
        try:
            installed.wait(timeout=60)
        except subprocess.TimeoutExpired:
            installed.kill()
