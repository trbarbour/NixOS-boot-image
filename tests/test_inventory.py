"""Tests for the inventory module."""

from pathlib import Path

from pre_nixos.inventory import enumerate_disks, detect_ram_gb


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


def test_detect_ram_gb(tmp_path: Path) -> None:
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemTotal:       16777216 kB\n")
    assert detect_ram_gb(meminfo) == 16


FIXTURES = Path(__file__).parent / "fixtures" / "vpd_pg89"


def test_sata_model_comes_from_ata_identify(tmp_path: Path) -> None:
    """#336: for a SATA disk, ``device/model`` is the 16-character SCSI
    product field, so ``G.SKILL 128GB SSD`` read as ``G.SKILL 128GB SS`` and
    the disk-class question (R-S3) was never asked.  The full ATA model is in
    ``device/vpd_pg89`` (captured from the image's kernel in QEMU)."""

    create_disk(tmp_path, "sda", rotational="1", size="250069680", model="G.SKILL 128GB SS")
    (tmp_path / "sda" / "device" / "vpd_pg89").write_bytes(
        (FIXTURES / "qemu-ahci-gskill-128gb-ssd.bin").read_bytes()
    )
    create_disk(tmp_path, "sdb", rotational="1", model="ST3750528AS     ")
    (tmp_path / "sdb" / "device" / "vpd_pg89").write_bytes(
        (FIXTURES / "qemu-ahci-st3750528as.bin").read_bytes()
    )

    disks = {d.name: d for d in enumerate_disks(tmp_path)}

    assert disks["sda"].model == "G.SKILL 128GB SSD"
    assert disks["sdb"].model == "ST3750528AS"

    from pre_nixos import disk_class

    assert disk_class.unconfirmed(disks.values(), {}) == [disks["sda"]]


def test_model_without_vpd_pg89_comes_from_sysfs(tmp_path: Path) -> None:
    """SAS, virtio-scsi and NVMe disks have no ATA page: keep ``device/model``."""

    create_disk(tmp_path, "sda", model="QEMU HARDDISK   ")
    (d,) = enumerate_disks(tmp_path)
    assert d.model == "QEMU HARDDISK"


def test_ata_model_parser_rejects_other_pages() -> None:
    from pre_nixos.inventory import ata_model_from_vpd_pg89

    page = (FIXTURES / "qemu-ahci-gskill-128gb-ssd.bin").read_bytes()
    assert ata_model_from_vpd_pg89(page) == "G.SKILL 128GB SSD"
    assert ata_model_from_vpd_pg89(page[:571]) is None  # truncated
    assert ata_model_from_vpd_pg89(page[:1] + b"\x80" + page[2:]) is None  # not page 0x89
    assert ata_model_from_vpd_pg89(page[:56] + b"\x00" + page[57:]) is None  # no IDENTIFY
    blank = bytearray(page)
    blank[114:154] = b" " * 40
    assert ata_model_from_vpd_pg89(bytes(blank)) is None
    assert ata_model_from_vpd_pg89(b"") is None


def test_unreadable_vpd_pg89_falls_back_to_sysfs(tmp_path: Path) -> None:
    create_disk(tmp_path, "sda", model="G.SKILL 128GB SS")
    (tmp_path / "sda" / "device" / "vpd_pg89").mkdir()  # reading it raises IsADirectoryError
    (d,) = enumerate_disks(tmp_path)
    assert d.model == "G.SKILL 128GB SS"


def test_user_pc_drive_page_gives_the_full_model() -> None:
    """#336 on the real drive: the page read on the user's PC (serial blanked)."""

    from pre_nixos.inventory import ata_model_from_vpd_pg89

    page = (FIXTURES / "gskill-128gb-ssd-user-pc.bin").read_bytes()
    assert ata_model_from_vpd_pg89(page) == "G.SKILL 128GB SSD"
    # IDENTIFY word 217, nominal media rotation rate: 0, not reported.
    assert page[60 + 2 * 217 : 60 + 2 * 218] == b"\x00\x00"
