"""Tests for the inventory module."""

from pathlib import Path

from pre_nixos.inventory import enumerate_disks


def create_disk(root: Path, name: str, *, removable: str = "0", rotational: str = "0", size: str = "0", model: str = "", serial: str = "") -> None:
    disk = root / name
    (disk / "device").mkdir(parents=True)
    (disk / "queue").mkdir()
    (disk / "removable").write_text(removable)
    (disk / "queue" / "rotational").write_text(rotational)
    (disk / "size").write_text(size)
    (disk / "device" / "model").write_text(model)
    (disk / "device" / "serial").write_text(serial)


def test_enumerate_disks(tmp_path: Path) -> None:
    create_disk(
        tmp_path,
        "sda",
        removable="0",
        rotational="0",
        size="2097152",
        model="TestDisk",
        serial="ABC123",
    )
    create_disk(tmp_path, "sdb", removable="1")
    (tmp_path / "loop0").mkdir()

    disks = enumerate_disks(tmp_path)
    assert len(disks) == 1
    d = disks[0]
    assert d.name == "sda"
    assert d.model == "TestDisk"
    assert d.serial == "ABC123"
    assert d.size == 2097152 * 512
    assert d.rotational is False
    assert d.nvme is False
