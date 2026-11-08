"""Re-provisioning over an earlier pre-nixos layout (user report, 2026-11-08).

On the first BIOS PC the user had installed with the old plan: the SSD,
seen as an HDD, was the ``large`` VG on one partition, and the HDD pair a
RAID-1 for ``main``.  With 0.26.1 they answered "SSD" in the TUI and applied
the new plan (``main`` on the SSD, swap on the pair).  After the cleanup:

1. disko's first run skipped ``mkfs.vfat`` on the new ESP, because ``blkid``
   found an old signature there, and mounting ``/boot`` failed (``FAT-fs
   (sda2): bogus number of reserved sectors``);
2. the retry after cleanup failed at ``pvcreate /dev/md/md0``
   ("Can't open /dev/md127 exclusively").

Hypothesis: the cleanup deactivates LVs and stops arrays before it wipes
their signatures, so the wipes find no device and the signatures inside LVs
and arrays survive, reappearing when the new layout puts a partition or array
at the same offsets.

The machine is the SATA disk-class one (``ambiguous_ssd_scsi_disks``); the
user's two layouts come from ``--hdd sda`` and then ``--ssd sda``.
"""

from __future__ import annotations

import pytest

from tests.vm.controller import BootImageVM

pytestmark = [pytest.mark.vm, pytest.mark.slow]

APPLY_TIMEOUT = 1500


def _ssd_name(vm: BootImageVM) -> str:
    """The stand-in SSD (4 GiB; the HDDs are 5 GiB), whatever its sd name (#334)."""

    listing = vm.run_as_root_checked(
        'for d in /sys/block/sd*; do echo "${d##*/} $(cat $d/size)"; done', timeout=120
    )
    sizes = [line.split() for line in listing.splitlines() if line.startswith("sd")]
    (name,) = [name for name, size in sizes if int(size) * 512 == 4 * 1024**3]
    return name


def test_reprovision_from_the_hdd_layout_to_the_ssd_layout(
    boot_image_vm_with_ambiguous_ssd: BootImageVM,
) -> None:
    vm = boot_image_vm_with_ambiguous_ssd
    status = vm.wait_for_storage_status()
    assert status.get("DETAIL") == "disk-class-unconfirmed", status
    ssd = _ssd_name(vm)

    # The user's old install: the SSD planned as an HDD.
    vm.run_as_root_checked(
        f"pre-nixos --hdd {ssd} --no-auto-install > /tmp/first.log 2>&1", timeout=APPLY_TIMEOUT
    )
    first = vm.run_as_root_checked("lvs --noheadings -o lv_name,vg_name,devices", timeout=120)
    assert "large" in first, first

    # The user's second apply: the SSD answered as an SSD, existing storage wiped
    # with option 1 (signatures), non-interactively as the boot service does.
    second = vm.run_as_root(
        f"PRE_NIXOS_FORCE_CLEANUP=1 pre-nixos --ssd {ssd} --no-auto-install"
        " > /tmp/second.log 2>&1; echo second-exit=$?",
        timeout=APPLY_TIMEOUT,
    )
    second_log = vm.run_as_root("grep -v '^+ ' /tmp/second.log | tail -n 80", timeout=120)
    findmnt = vm.run_as_root("findmnt -n -o SOURCE,FSTYPE /mnt/boot; true", timeout=60)
    assert "second-exit=0" in second and "vfat" in findmnt, (
        f"{second.strip()}; /boot: {findmnt.strip()!r}\n{second_log}"
    )

    lvs = vm.run_as_root_checked("lvs --noheadings -o lv_name,vg_name", timeout=120)
    assert "main" in lvs and "large" not in lvs, lvs
    pvs = vm.run_as_root_checked("pvs --noheadings -o pv_name,vg_name", timeout=120)
    assert f"/dev/{ssd}3" in pvs, pvs
