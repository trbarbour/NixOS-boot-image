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
    # Non-interactive: mdadm 4.4 otherwise asks about a bitmap and hangs.
    assert "--run" in mdadm_command and "--bitmap=none" in mdadm_command
    assert plan.sentinel_path == "/dev/vg_residue/lv_residue"


def test_raid_residue_plan_records_verification_commands() -> None:
    plan = build_raid_residue_plan()
    assert any("lsblk" in command for command in plan.verification_commands)
    assert any("blkid" in command for command in plan.verification_commands)
    assert plan.teardown_expectations


def test_residue_script_uses_the_same_mdadm_command() -> None:
    from tests.vm.cleanup_plan import MDADM_CREATE_RESIDUE, RAID_LVM_RESIDUE_SCRIPT

    assert MDADM_CREATE_RESIDUE in RAID_LVM_RESIDUE_SCRIPT
    assert "{mdadm_create}" not in RAID_LVM_RESIDUE_SCRIPT
