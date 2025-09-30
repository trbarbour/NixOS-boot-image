"""Tests for partitioning utilities."""

from pre_nixos import partition, pre_nixos
from pre_nixos.inventory import Disk


def test_create_partitions_with_efi():
    cmds = partition.create_partitions("/dev/sda", dry_run=True)
    assert cmds[0] == "sgdisk --zap-all /dev/sda"
    assert "sgdisk -n1:0:+512MiB -t1:EF00 /dev/sda" in cmds
    assert "sgdisk -n2:0:0 -t2:8E00 /dev/sda" in cmds
    assert "parted -s /dev/sda set 1 boot on" in cmds
    assert "parted -s /dev/sda set 2 lvm on" in cmds


def test_create_partitions_lvm_only():
    cmds = partition.create_partitions("/dev/sdb", with_efi=False, dry_run=True)
    assert cmds[0] == "sgdisk --zap-all /dev/sdb"
    assert "sgdisk -n1:0:0 -t1:8E00 /dev/sdb" in cmds
    assert "parted -s /dev/sdb set 1 lvm on" in cmds
    assert all("EF00" not in c for c in cmds)


def test_cli_partition_invoked(monkeypatch):
    monkeypatch.setattr(
        pre_nixos.inventory,
        "enumerate_disks",
        lambda: [Disk(name="sda", size=1000, rotational=False)],
    )
    called = []

    def fake_part(dev, *, with_efi=True, efi_size="512MiB", dry_run=False):
        called.append((dev, with_efi, dry_run))
        return []

    monkeypatch.setattr(pre_nixos.partition, "create_partitions", fake_part)
    monkeypatch.setattr(pre_nixos.network, "configure_lan", lambda: None)
    pre_nixos.main([
        "--dry-run",
        "--partition-boot",
        "/dev/sda",
        "--partition-lvm",
        "/dev/sdb",
        "--plan-only",
    ])
    assert called == [
        ("/dev/sda", True, True),
        ("/dev/sdb", False, True),
    ]
