"""Unit coverage for RAID/LVM residue plan helpers."""

from __future__ import annotations

from tests.vm.cleanup_plan import RaidResiduePlan, build_raid_residue_plan


def test_raid_residue_plan_shapes_commands() -> None:
    plan = build_raid_residue_plan()
    assert isinstance(plan, RaidResiduePlan)
    assert plan.preseed_commands, "preseed commands should not be empty"
    mdadm_command = plan.preseed_commands[0]
    assert "mdadm --create /dev/md127" in mdadm_command
    assert "--level=1" in mdadm_command
    assert "--raid-devices=2" in mdadm_command
    assert "--raid1" not in mdadm_command
    assert plan.sentinel_path == "/dev/vg_residue/lv_residue"


def test_raid_residue_plan_records_verification_commands() -> None:
    plan = build_raid_residue_plan()
    assert any("lsblk" in command for command in plan.verification_commands)
    assert any("blkid" in command for command in plan.verification_commands)
    assert plan.teardown_expectations
