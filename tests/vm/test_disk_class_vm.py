"""A blank machine whose SSD is reported as rotating (R-S3; task queue item 34).

The user's first BIOS PC had a ``G.SKILL 128GB SSD`` that reports no rotation
rate, so the kernel calls it rotating; pre-nixos planned it as an HDD.  Here
the stand-in is a QEMU disk with no rotation rate named "TEST SSD" (U1), plus
an equal HDD pair.  On blank disks the boot service provisions storage even
without auto-install (design F3), so it must stop before touching any disk
(D2 (b)) and say why.  Design: plans/2026-11-07T161535Z-ssd-model-name-design.md.
"""

from __future__ import annotations

import json

import pytest

from tests.vm.controller import BootImageVM

pytestmark = [pytest.mark.vm, pytest.mark.slow]


def test_boot_run_waits_for_the_disk_class_answer(
    boot_image_vm_with_ambiguous_ssd: BootImageVM,
) -> None:
    vm = boot_image_vm_with_ambiguous_ssd

    # The guest names SCSI disks in probe-completion order, not by target id
    # (2026-11-07: target 0 was sda in one run and sdb in the next), so find
    # the stand-in SSD by its model.  The scenario only means something if
    # the guest sees it as the user's drive: rotating, named SSD.
    listing = vm.run_as_root_checked(
        'for d in /sys/block/sd*; do echo "${d##*/} $(cat $d/queue/rotational) $(cat $d/device/model)"; done',
        timeout=120,
    )
    disks = [line.split(maxsplit=2) for line in listing.splitlines() if line.startswith("sd")]
    (ssd,) = [name for name, _rota, model in disks if model.strip() == "TEST SSD"]
    assert len(disks) == 3 and all(rota == "1" for _name, rota, _model in disks), listing

    status = vm.wait_for_storage_status()
    if (status.get("STATE"), status.get("DETAIL")) != ("plan-only", "disk-class-unconfirmed"):
        pytest.fail(
            "the boot run did not stop for the disk-class answer:\n"
            f"status={status}\n{vm.collect_journal('pre-nixos.service')}"
        )
    assert status.get("AUTO_INSTALL_REASON", "disk-class-unconfirmed") == "disk-class-unconfirmed"

    # Nothing was provisioned: no partitions, arrays or volume groups.
    names = vm.run_as_root_checked("lsblk -nro NAME /dev/sda /dev/sdb /dev/sdc", timeout=120)
    assert sorted(names.split()) == ["sda", "sdb", "sdc"], names
    # No arrays.  /proc/mdstat exists only once the md driver is loaded, and
    # nothing loads it when nothing is provisioned (first run, 2026-11-07).
    mdstat = vm.run_as_root_checked("cat /proc/mdstat 2>/dev/null || true", timeout=120)
    assert "active" not in mdstat, mdstat
    assert vm.run_as_root_checked("vgs --noheadings -o vg_name", timeout=120).strip() == ""

    journal = vm.collect_journal("pre-nixos.service")
    assert f"Disk type unconfirmed: {ssd} (TEST SSD)" in journal, journal
    assert "pre-nixos.service: Failed" not in journal, journal

    # The answer on the command line plans `main` on the SSD (D3 (c)).
    plan = json.loads(
        vm.run_as_root_checked(f"pre-nixos --plan-only --ssd {ssd} 2>/dev/null", timeout=300)
    )
    vgs = {vg["name"]: vg["devices"] for vg in plan["vgs"]}
    assert vgs["main"] == [f"{ssd}3"] and vgs["swap"] == ["md0"], vgs
    assert plan["disk_classes"] == {ssd: "ssd"}
