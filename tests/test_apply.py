"""Tests for apply module."""

from pre_nixos.inventory import Disk
from pre_nixos.planner import plan_storage
from pre_nixos.apply import apply_plan


def test_apply_plan_returns_commands() -> None:
    disks = [
        Disk(name="sda", size=1000, rotational=False),
        Disk(name="sdb", size=2000, rotational=True),
        Disk(name="sdc", size=2000, rotational=True),
    ]
    plan = plan_storage("fast", disks)
    commands = apply_plan(plan)
    assert any(cmd.startswith("mdadm") for cmd in commands)
    assert any("vgcreate main" in cmd for cmd in commands)
    assert any("lvcreate -n root" in cmd for cmd in commands)
