"""Which devices the image writer accepts (task queue item 42; R-W2).

Design: plans/2026-11-11T181058Z-image-writer-design.md.  Fake sysfs trees
model the cases: /sys/block/<name> is a symlink into /sys/devices, whose path
names the transport, as on Linux.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

import pytest

from write_image import devices
from write_image.devices import Candidate, Refusal, SystemView

GIB = 1024**3


class FakeSys:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.block = root / "sys/block"
        self.block.mkdir(parents=True)

    def disk(
        self,
        name: str,
        *,
        bus_path: str,
        size_bytes: int = 32 * GIB,
        removable: bool = False,
        model: str = "Disk",
        serial: Optional[str] = "SER123",
        partitions: Iterable[str] = (),
        holders: Iterable[str] = (),
    ) -> None:
        target = self.root / "sys/devices" / bus_path / "block" / name
        (target / "device").mkdir(parents=True)
        (target / "size").write_text(f"{size_bytes // 512}\n")
        (target / "removable").write_text("1\n" if removable else "0\n")
        (target / "device/model").write_text(model + "\n")
        if serial is not None:
            (target / "device/serial").write_text(serial + "\n")
        (target / "holders").mkdir()
        for part in partitions:
            (target / part / "holders").mkdir(parents=True)
            for holder in holders:
                (target / part / "holders" / holder).mkdir()
        (self.block / name).symlink_to(target)

    def view(self, *, mounted: Iterable[str] = (), system: Iterable[str] = ()) -> SystemView:
        return SystemView(
            sys_block=self.block,
            mounted_sources=frozenset(mounted),
            system_devices=frozenset(system),
        )


@pytest.fixture
def fake(tmp_path: Path) -> FakeSys:
    sys = FakeSys(tmp_path)
    sys.disk("sda", bus_path="pci0000:00/0000:00:11.0/ata1/host0/target0:0:0/0:0:0:0", model="Samsung SSD 860", partitions=["sda1", "sda2"])
    sys.disk("nvme0n1", bus_path="pci0000:00/0000:00:1d.0/0000:3d:00.0/nvme/nvme0", model="WD Black SN850")
    sys.disk("vda", bus_path="pci0000:00/0000:00:04.0/virtio1", model="")
    sys.disk(
        "sdb", bus_path="pci0000:00/0000:00:14.0/usb2/2-1/2-1:1.0/host6/target6:0:0/6:0:0:0",
        removable=True, model="SanDisk Ultra", size_bytes=64 * GIB, partitions=["sdb1"],
    )
    sys.disk(
        "sdc", bus_path="pci0000:00/0000:00:14.0/usb2/2-2/2-2:1.0/host7/target7:0:0/7:0:0:0",
        removable=False, model="Samsung T7", size_bytes=500 * GIB,
    )
    sys.disk("mmcblk0", bus_path="platform/fe340000.mmc/mmc_host/mmc0/mmc0:aaaa", removable=False, model="SC64G", serial=None)
    return sys


def _by_name(view: SystemView) -> dict:
    candidates, refusals = devices.scan(view)
    return {c.name: c for c in candidates} | {r.name: r for r in refusals}


def test_usb_stick_usb_ssd_and_sd_card_are_eligible(fake: FakeSys) -> None:
    found = _by_name(fake.view(system=["sda"]))
    assert found["sdb"] == Candidate("sdb", "SanDisk Ultra", "SER123", 64 * GIB, "usb", True)
    assert isinstance(found["sdc"], Candidate) and found["sdc"].transport == "usb"  # removable=0, USB
    assert isinstance(found["mmcblk0"], Candidate) and found["mmcblk0"].transport == "mmc"


def test_internal_disks_are_refused(fake: FakeSys) -> None:
    found = _by_name(fake.view())
    for name in ("sda", "nvme0n1", "vda"):
        assert isinstance(found[name], Refusal), name
    assert "sata" in found["sda"].reason
    assert "nvme" in found["nvme0n1"].reason
    assert "virtio" in found["vda"].reason


def test_mounted_or_held_or_system_devices_are_refused(fake: FakeSys) -> None:
    found = _by_name(fake.view(mounted=["/dev/sdb1"], system=["sdc"]))
    assert isinstance(found["sdb"], Refusal) and "mounted" in found["sdb"].reason
    assert isinstance(found["sdc"], Refusal) and "system" in found["sdc"].reason


def test_partition_in_use_by_device_mapper_is_refused(tmp_path: Path) -> None:
    sys = FakeSys(tmp_path)
    sys.disk("sdd", bus_path="pci0000:00/0000:00:14.0/usb1/1-1/1-1:1.0/host8/t/8:0:0:0", removable=True,
             partitions=["sdd1"], holders=["dm-0"])
    (found,) = devices.scan(sys.view())[1]
    assert found.name == "sdd" and "in use" in found.reason


def test_empty_card_reader_is_refused(tmp_path: Path) -> None:
    sys = FakeSys(tmp_path)
    sys.disk("sde", bus_path="pci0000:00/0000:00:14.0/usb1/1-2/1-2:1.0/host9/t/9:0:0:0", removable=True, size_bytes=0)
    (found,) = devices.scan(sys.view())[1]
    assert "no medium" in found.reason


def test_check_one_device(fake: FakeSys) -> None:
    view = fake.view()
    assert isinstance(devices.check(view, "sdb"), Candidate)
    assert isinstance(devices.check(view, "sda"), Refusal)
    missing = devices.check(view, "sdz")
    assert isinstance(missing, Refusal) and "no such" in missing.reason
    # Only kernel names: a path or a partition is not a device to write.
    for bad in ("/dev/sdb", "sdb1", "../sda"):
        assert isinstance(devices.check(view, bad), Refusal), bad


def test_preferred_order_depends_on_the_format(fake: FakeSys) -> None:
    candidates, _ = devices.scan(fake.view())
    assert [c.name for c in devices.preferred(candidates, "iso")][-1] == "mmcblk0"
    assert [c.name for c in devices.preferred(candidates, "sd")][0] == "mmcblk0"


def test_disks_backing_a_mount_source(fake: FakeSys, tmp_path: Path) -> None:
    """The system disks are found through partitions and device-mapper slaves."""

    dm = fake.block / "dm-0"
    (tmp_path / "sys/devices/virtual/block/dm-0/slaves").mkdir(parents=True)
    dm.symlink_to(tmp_path / "sys/devices/virtual/block/dm-0")
    (tmp_path / "sys/devices/virtual/block/dm-0/slaves/sda2").mkdir()
    assert devices.disks_of(fake.block, "sda2") == {"sda"}
    assert devices.disks_of(fake.block, "dm-0") == {"sda"}
    assert devices.disks_of(fake.block, "nvme0n1") == {"nvme0n1"}
