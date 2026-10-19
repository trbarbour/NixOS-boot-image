"""The AArch64 SD image boots, keeps its stock boot settings and provisions.

AArch64 plan §4 (VM layer) and §6 item 7: boot the image's system closure on
``qemu-system-aarch64 -M virt`` (the Pi firmware chain is out of scope, U5),
with the SD card as ``/dev/vda`` and an empty target disk as ``/dev/vdb``.
Requirements: §2.9 R-P2 (stock kernel parameters), §2.3 R-S1 (the boot medium
is never planned or modified), §2.3/§2.4 (empty disks are auto-provisioned
with main/slash), §2.6 (the active NIC becomes ``lan``).  Timings and the
test-only kernel parameter: notes/2026-10-19T031843Z-aarch64-e5-spike.md.
"""

from __future__ import annotations

import pytest

from tests.vm.aarch64_fixtures import Aarch64Build
from tests.vm.controller import BootImageVM
from tests.vm.fixtures import SSHKeyPair

pytestmark = [pytest.mark.vm, pytest.mark.slow]

# E5 run7: pre-nixos finished about 647 s after QEMU started (login at 234 s).
PRE_NIXOS_TIMEOUT = 1800


def _rows(output: str) -> set[tuple[str, ...]]:
    return {tuple(line.split()) for line in output.splitlines() if line.strip()}


def test_aarch64_image_boots_with_stock_kernel_parameters(
    aarch64_boot_image_vm: BootImageVM, aarch64_boot_image_build: Aarch64Build
) -> None:
    vm = aarch64_boot_image_vm
    assert vm.run_as_root_checked("uname -m", timeout=120).strip() == "aarch64"
    cmdline = vm.run_as_root_checked("cat /proc/cmdline", timeout=120).strip()
    assert cmdline.startswith(aarch64_boot_image_build.system.kernel_params), cmdline


def test_aarch64_image_provisions_the_target_and_spares_the_card(
    aarch64_boot_image_vm: BootImageVM,
) -> None:
    vm = aarch64_boot_image_vm
    status = vm.wait_for_storage_status(timeout=PRE_NIXOS_TIMEOUT)
    if status.get("STATE") != "applied" or status.get("DETAIL") != "auto-applied":
        pytest.fail(
            f"pre-nixos did not auto-apply on AArch64: status={status}\n"
            f"{vm.collect_journal('pre-nixos.service')}"
        )

    # R-S1: the SD card keeps exactly its two image partitions and still holds /.
    card = vm.run_as_root_checked("lsblk -nrpo NAME /dev/vda", timeout=120)
    assert set(card.split()) == {"/dev/vda", "/dev/vda1", "/dev/vda2"}, card
    assert vm.run_as_root_checked("findmnt -n -o SOURCE /", timeout=120).strip() == "/dev/vda2"

    pvs = _rows(vm.run_as_root_checked("pvs --noheadings -o pv_name,vg_name", timeout=120))
    assert ("/dev/vdb2", "main") in pvs, pvs
    lvs = _rows(vm.run_as_root_checked("lvs --noheadings -o lv_name,vg_name", timeout=120))
    assert ("slash", "main") in lvs, lvs


def test_aarch64_image_brings_up_lan_with_root_ssh(
    aarch64_boot_image_vm: BootImageVM, boot_ssh_key_pair: SSHKeyPair
) -> None:
    """§2.6 and remote root SSH with the embedded key (PR #315 review)."""

    vm = aarch64_boot_image_vm
    vm.wait_for_unit_inactive("pre-nixos", timeout=PRE_NIXOS_TIMEOUT)
    addresses = vm.wait_for_ipv4("lan", timeout=600)
    assert any("inet " in line for line in addresses), addresses
    identity = vm.run_ssh(
        private_key=boot_ssh_key_pair.private_key, command="id -un", timeout=600
    )
    assert identity == "root"


def test_aarch64_image_puts_the_pi_boot_chain_on_the_target(
    aarch64_boot_image_vm: BootImageVM,
) -> None:
    """Plan item 8 (R-B1): firmware and the NVMe U-Boot reach the target's vfat /boot.

    The image declares the boot chain to the service; the manual-install entry
    point (the same code auto-install runs before ``nixos-install``) copies it
    onto the disko-mounted FAT partition.  Booting it needs the Pi firmware
    (out of scope here, U5): hardware experiments E9b/E9c.
    """

    vm = aarch64_boot_image_vm
    vm.wait_for_unit_inactive("pre-nixos", timeout=PRE_NIXOS_TIMEOUT)
    environment = vm.run_as_root_checked("systemctl show -p Environment pre-nixos", timeout=120)
    assert "PRE_NIXOS_INSTALLED_BOOT=rpi4-uboot-extlinux" in environment, environment
    assert vm.run_as_root_checked("findmnt -n -o FSTYPE /mnt/boot", timeout=120).strip() == "vfat"

    output = vm.run_as_root_checked("pre-nixos-install-boot-files --root /mnt", timeout=300)
    assert "rpi4-uboot-extlinux: copied" in output, output
    vm.run_as_root_checked(
        'cmp "$PRE_NIXOS_RPI_FIRMWARE/u-boot-rpi4.bin" /mnt/boot/u-boot-rpi4.bin', timeout=120
    )
    vm.run_as_root_checked("grep -qx kernel=u-boot-rpi4.bin /mnt/boot/config.txt", timeout=120)
    vm.run_as_root_checked("test -f /mnt/boot/start4.elf", timeout=120)
