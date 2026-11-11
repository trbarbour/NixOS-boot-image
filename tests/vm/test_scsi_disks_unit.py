"""Unit tests for tests/vm/scsi_disks.py (no QEMU needed)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.vm.scsi_disks import Bus, ScsiDisk, scsi_disk_args


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
        "scsi-hd,bus=scsi0.0,drive=scsidisk0,rotation_rate=1,serial=ssd,scsi-id=0,id=scsihd0",
        "scsi-hd,bus=scsi0.0,drive=scsidisk1,rotation_rate=7200,serial=hdd1,scsi-id=1,id=scsihd1",
    ]
    assert f"file={tmp_path / 'ssd.img'},if=none,id=scsidisk0,format=raw" in args


def test_serial_must_be_alphanumeric(tmp_path: Path) -> None:
    with pytest.raises(AssertionError):
        ScsiDisk(tmp_path / "x.img", rotational=True, serial="bad,serial")


def test_unreported_rotation_and_product(tmp_path: Path) -> None:
    """Task queue item 34: an SSD reporting no rotation rate, named SSD."""

    disk = ScsiDisk(tmp_path / "x.img", rotational=None, serial="ssd", model="TEST SSD")
    (device,) = [a for a in scsi_disk_args([disk]) if a.startswith("scsi-hd")]
    assert device == (
        "scsi-hd,bus=scsi0.0,drive=scsidisk0,rotation_rate=0,product=TEST SSD,serial=ssd,scsi-id=0,id=scsihd0"
    )


@pytest.mark.parametrize("model", ["A" * 17, "bad,name"])
def test_scsi_model_must_fit_scsi_and_qemu(tmp_path: Path, model: str) -> None:
    with pytest.raises(AssertionError):
        ScsiDisk(tmp_path / "x.img", rotational=None, serial="ssd", model=model)


def test_sata_disks_on_ahci_with_full_ata_model(tmp_path: Path) -> None:
    """#336: the user's SSD on SATA, with its 17-character model."""

    disks = [
        ScsiDisk(tmp_path / "s.img", rotational=None, serial="ssd", model="G.SKILL 128GB SSD", bus=Bus.SATA),
        ScsiDisk(tmp_path / "h.img", rotational=True, serial="hdd1", bus=Bus.SATA),
    ]
    args = scsi_disk_args(disks)
    assert args[:2] == ["-device", "ich9-ahci,id=ahci0"]
    assert [a for a in args if a.startswith("ide-hd")] == [
        "ide-hd,bus=ahci0.0,drive=satadisk0,rotation_rate=0,model=G.SKILL 128GB SSD,serial=ssd",
        "ide-hd,bus=ahci0.1,drive=satadisk1,rotation_rate=7200,serial=hdd1",
    ]
    assert not any(a.startswith("virtio-scsi") for a in args)
    with pytest.raises(AssertionError):
        ScsiDisk(tmp_path / "x.img", rotational=None, serial="x", model="A" * 41, bus=Bus.SATA)


def test_mptsas_disks_attach_to_an_lsi_sas1068(tmp_path: Path) -> None:
    """Task queue item 48: the user's late HDD sits behind an LSI SAS1068."""

    disks = [
        ScsiDisk(tmp_path / "ssd.img", rotational=False, serial="ssd"),
        ScsiDisk(tmp_path / "hba.img", rotational=True, serial="hba", bus=Bus.MPTSAS),
    ]
    args = scsi_disk_args(disks)
    assert args.count("-device") == 4
    assert "mptsas1068,id=mptsas0" in args
    assert "scsi-hd,bus=mptsas0.0,drive=sasdisk0,rotation_rate=7200,serial=hba,scsi-id=0" in args
    assert f"file={tmp_path / 'hba.img'},if=none,id=sasdisk0,format=raw" in args
