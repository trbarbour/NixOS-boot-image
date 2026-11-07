"""Unit tests for tests/vm/scsi_disks.py (no QEMU needed)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.vm.scsi_disks import ScsiDisk, scsi_disk_args


def test_no_disks_adds_no_controller() -> None:
    assert scsi_disk_args([]) == []


def test_rotation_rates_and_order(tmp_path: Path) -> None:
    disks = [
        ScsiDisk(tmp_path / "ssd.img", rotational=False, serial="ssd"),
        ScsiDisk(tmp_path / "hdd.img", rotational=True, serial="hdd1"),
    ]
    args = scsi_disk_args(disks)
    assert args[:2] == ["-device", "virtio-scsi-pci,id=scsi0"]
    devices = [a for a in args if a.startswith("scsi-hd")]
    assert devices == [
        "scsi-hd,bus=scsi0.0,drive=scsidisk0,rotation_rate=1,serial=ssd,scsi-id=0",
        "scsi-hd,bus=scsi0.0,drive=scsidisk1,rotation_rate=7200,serial=hdd1,scsi-id=1",
    ]
    assert f"file={tmp_path / 'ssd.img'},if=none,id=scsidisk0,format=raw" in args


def test_serial_must_be_alphanumeric(tmp_path: Path) -> None:
    with pytest.raises(AssertionError):
        ScsiDisk(tmp_path / "x.img", rotational=True, serial="bad,serial")


def test_unreported_rotation_and_product(tmp_path: Path) -> None:
    """Task queue item 34: an SSD reporting no rotation rate, named SSD."""

    disk = ScsiDisk(tmp_path / "x.img", rotational=None, serial="ssd", product="TEST SSD")
    (device,) = [a for a in scsi_disk_args([disk]) if a.startswith("scsi-hd")]
    assert device == (
        "scsi-hd,bus=scsi0.0,drive=scsidisk0,rotation_rate=0,product=TEST SSD,serial=ssd,scsi-id=0"
    )


@pytest.mark.parametrize("product", ["A" * 17, "bad,name"])
def test_product_must_fit_scsi_and_qemu(tmp_path: Path, product: str) -> None:
    with pytest.raises(AssertionError):
        ScsiDisk(tmp_path / "x.img", rotational=None, serial="ssd", product=product)
