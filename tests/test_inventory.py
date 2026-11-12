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


# --- the plan's disks (task queue item 50, R-D3, R-D4) -----------------------
# Design: plans/2026-11-11T194943Z-disk-settle-design.md (D2, D5, D6).

import pytest

from pre_nixos import inventory
from pre_nixos.inventory import Disk, DiskIdentity

GIB = 1024**3
SDA = Disk(name="sda", model="SSD", size=128 * GIB, serial="A", rotational=False)
SDB = Disk(name="sdb", model="HDD", size=750 * GIB, serial="B", rotational=True)


def test_identity_is_name_size_and_serial() -> None:
    assert inventory.disk_identities([SDA]) == frozenset({DiskIdentity("sda", 128 * GIB, "A")})
    # The model and rotational flag are not identity (D2).
    other_model = Disk(name="sda", model="late VPD", size=128 * GIB, serial="A", rotational=True)
    assert inventory.disk_identities([other_model]) == inventory.disk_identities([SDA])


def test_changes_are_named() -> None:
    before = inventory.disk_identities([SDA, SDB])
    swapped = Disk(name="sdb", size=750 * GIB, serial="C")
    sdc = Disk(name="sdc", size=3 * GIB // 2, serial="")
    after = inventory.disk_identities([swapped, sdc])
    assert inventory.describe_changes(before, after) == [
        "removed sda (128 GiB, serial A)",
        "changed sdb: was 750 GiB, serial B; now 750 GiB, serial C",
        "added sdc (1.5 GiB, no serial)",
    ]
    assert inventory.describe_changes(before, before) == []


def test_plan_records_its_disks() -> None:
    plan: dict = {"disko": {}}
    inventory.record_disks(plan, [SDB, SDA])
    assert plan[inventory.PLAN_KEY] == [
        {"name": "sda", "size": 128 * GIB, "serial": "A"},
        {"name": "sdb", "size": 750 * GIB, "serial": "B"},
    ]


def _verify(monkeypatch, plan, present, protected=frozenset()):
    monkeypatch.setattr(inventory, "enumerate_disks", lambda: list(present))
    return inventory.verify_plan_disks(plan, protected)


def test_unchanged_disks_pass(monkeypatch) -> None:
    plan: dict = {}
    inventory.record_disks(plan, [SDA, SDB])
    assert _verify(monkeypatch, plan, [SDB, SDA]) == []


def test_a_disk_added_after_planning_is_reported(monkeypatch) -> None:
    plan: dict = {}
    inventory.record_disks(plan, [SDA])
    assert _verify(monkeypatch, plan, [SDA, SDB]) == ["added sdb (750 GiB, serial B)"]


def test_protected_disks_are_left_out_as_when_planning(monkeypatch) -> None:
    """The plan was made without the running system's disks (D2)."""

    plan: dict = {}
    inventory.record_disks(plan, [SDA])
    assert _verify(monkeypatch, plan, [SDA, SDB], protected={"/dev/sdb"}) == []


def test_a_plan_without_a_record_is_refused(monkeypatch) -> None:
    """D6 (R-D4): a plan from an older version, or written by hand."""

    (change,) = _verify(monkeypatch, {"disko": {}}, [SDA])
    assert "does not record its disks" in change and "re-plan" in change


@pytest.mark.parametrize(
    "record",
    [
        "sda",
        [{"name": "sda"}],
        [{"name": "sda", "size": "big", "serial": "A"}],
        [{"name": 3, "size": 1, "serial": "A"}],
    ],
)
def test_a_malformed_record_is_refused(monkeypatch, record) -> None:
    (change,) = _verify(monkeypatch, {inventory.PLAN_KEY: record}, [SDA])
    assert "malformed" in change


def test_the_planner_records_its_disks() -> None:
    """Every plan records the disks it was made from (D5), wherever it is made."""

    from pre_nixos.planner import plan_storage

    plan = plan_storage("fast", [SDA, SDB], ram_gb=16)
    assert plan[inventory.PLAN_KEY] == [
        {"name": "sda", "size": 128 * GIB, "serial": "A"},
        {"name": "sdb", "size": 750 * GIB, "serial": "B"},
    ]


@pytest.mark.parametrize("hdds", [[SDB], [SDB, Disk(name="sdc", size=750 * GIB, serial="C", rotational=True)]])
def test_the_planner_records_its_disks_on_the_hdd_only_path(hdds) -> None:
    """Codex on #352: one or two HDDs and no SSD return early from the planner."""

    from pre_nixos.planner import plan_storage

    plan = plan_storage("fast", hdds, ram_gb=16)
    assert [entry["name"] for entry in plan[inventory.PLAN_KEY]] == [d.name for d in hdds]


# --- the serial, by bus (task queue item 53) ---------------------------------
# Experiment notes/2026-11-12T014614Z-disk-serial-experiment.md: virtio has
# /sys/block/<d>/serial, NVMe device/serial (space-padded), and SCSI, SAS and
# SATA only the Unit Serial Number VPD page device/vpd_pg80.


def vpd_pg80(serial: bytes) -> bytes:
    """A Unit Serial Number VPD page (SPC): page code 0x80, big-endian length."""

    return bytes([0x00, 0x80, len(serial) >> 8, len(serial) & 0xFF]) + serial


def _bare_disk(root: Path, name: str) -> Path:
    disk = root / name
    (disk / "device").mkdir(parents=True)
    (disk / "queue").mkdir()
    (disk / "removable").write_text("0")
    (disk / "queue" / "rotational").write_text("1")
    (disk / "size").write_text("2097152")
    return disk


@pytest.mark.parametrize(
    "name,layout,expected",
    [
        ("vda", {"serial": b"VIRTSER1\n"}, "VIRTSER1"),
        ("nvme0n1", {"device/serial": b"NVMESER1             \n"}, "NVMESER1"),
        ("sda", {"device/vpd_pg80": vpd_pg80(b"SCSISER1")}, "SCSISER1"),
        ("sdb", {"device/vpd_pg80": vpd_pg80(b"SATASER1            ")}, "SATASER1"),
        ("sdc", {"device/vpd_pg80": vpd_pg80(b"  LEADING")}, "LEADING"),
        ("sdd", {}, ""),
    ],
)
def test_serial_is_read_where_the_bus_puts_it(tmp_path: Path, name, layout, expected) -> None:
    disk = _bare_disk(tmp_path, name)
    for relative, content in layout.items():
        (disk / relative).write_bytes(content)
    (found,) = enumerate_disks(tmp_path)
    assert found.serial == expected


def test_the_first_serial_found_wins(tmp_path: Path) -> None:
    disk = _bare_disk(tmp_path, "sda")
    (disk / "device" / "serial").write_text("FROMDEVICE\n")
    (disk / "device" / "vpd_pg80").write_bytes(vpd_pg80(b"FROMVPD"))
    (found,) = enumerate_disks(tmp_path)
    assert found.serial == "FROMDEVICE"


def test_an_empty_file_does_not_hide_a_later_one(tmp_path: Path) -> None:
    disk = _bare_disk(tmp_path, "sda")
    (disk / "device" / "serial").write_text("   \n")
    (disk / "device" / "vpd_pg80").write_bytes(vpd_pg80(b"FROMVPD"))
    (found,) = enumerate_disks(tmp_path)
    assert found.serial == "FROMVPD"


@pytest.mark.parametrize(
    "page,expected",
    [
        (vpd_pg80(b"SCSISER1"), "SCSISER1"),
        (vpd_pg80(b"SATASER1    ") + b"\x00\x00", "SATASER1"),  # padding past the length is ignored
        (vpd_pg80(b""), None),
        (vpd_pg80(b"   "), None),
        (b"\x00\x83\x00\x04ABCD", None),  # another page
        (b"\x00\x80\x00\x10SHORT", None),  # length beyond the data
        (b"\x00\x80", None),  # truncated header
        (b"", None),
    ],
)
def test_vpd_pg80_parser(page: bytes, expected) -> None:
    assert inventory.serial_from_vpd_pg80(page) == expected
