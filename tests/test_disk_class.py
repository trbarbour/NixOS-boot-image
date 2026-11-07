"""Disk classes: SSD/HDD per the kernel, unless the user says otherwise
(reqs R-S3, R-S4; plans/2026-11-07T161535Z-ssd-model-name-design.md)."""

from __future__ import annotations

import pytest

from pre_nixos import disk_class
from pre_nixos.disk_class import DiskClass
from pre_nixos.inventory import Disk
from pre_nixos.planner import plan_storage

GIB = 1024**3
# The user's first BIOS PC (task queue item 34): the kernel calls the SSD rotating.
GSKILL = Disk(name="sda", model="G.SKILL 128GB SSD", size=128 * GIB, rotational=True)
HDD_B = Disk(name="sdb", model="ST3750528AS", size=750 * GIB, rotational=True)
HDD_D = Disk(name="sdd", model="ST3750528AS", size=750 * GIB, rotational=True)
USER_PC = [GSKILL, HDD_B, HDD_D]


@pytest.mark.parametrize(
    "model, expected",
    [
        ("G.SKILL 128GB SSD", True),
        ("Samsung SSD 850 EVO 250GB", True),
        ("INTEL SSDSC2BB120G4", True),
        ("ssd lowercase", True),
        ("ST1000LM014-1EJ164", False),  # a Seagate SSHD (hybrid, rotating)
        ("QEMU HARDDISK", False),
        ("", False),
    ],
)
def test_name_rule(model: str, expected: bool) -> None:
    assert disk_class.name_suggests_ssd(model) is expected


def test_only_rotating_non_nvme_disks_are_ambiguous() -> None:
    assert disk_class.is_ambiguous(GSKILL)
    assert not disk_class.is_ambiguous(HDD_B)
    reported_ssd = Disk(name="sdc", model="Samsung SSD 850 EVO", rotational=False)
    assert not disk_class.is_ambiguous(reported_ssd)
    nvme = Disk(name="nvme0n1", model="WD SSD", rotational=True, nvme=True)
    assert not disk_class.is_ambiguous(nvme)


def test_unconfirmed_until_answered() -> None:
    assert disk_class.unconfirmed(USER_PC, {}) == [GSKILL]
    assert disk_class.unconfirmed(USER_PC, {"sda": DiskClass.HDD}) == []
    assert disk_class.unconfirmed(USER_PC, {"sda": DiskClass.SSD}) == []


def test_parse_answers() -> None:
    assert disk_class.parse_answers(["/dev/sda"], ["sdb"]) == {
        "sda": DiskClass.SSD,
        "sdb": DiskClass.HDD,
    }
    assert disk_class.parse_answers(["sda", "sda"], []) == {"sda": DiskClass.SSD}
    with pytest.raises(ValueError, match="both SSD and HDD"):
        disk_class.parse_answers(["sda"], ["/dev/sda"])
    with pytest.raises(ValueError, match="empty"):
        disk_class.parse_answers([" "], [])


def test_apply_classes_is_pure_and_applies_answers() -> None:
    before = list(USER_PC)
    after = disk_class.apply_classes(USER_PC, {"sda": DiskClass.SSD, "sdb": DiskClass.HDD})
    assert USER_PC == before and GSKILL.rotational  # inputs unchanged
    assert [d.rotational for d in after] == [False, True, True]
    assert after[0].model == GSKILL.model and after[0].size == GSKILL.size
    assert after[1] == HDD_B  # answered as the kernel says: same value
    assert after[2] is HDD_D  # not answered: the same object


def test_apply_classes_rejects_unknown_disks() -> None:
    with pytest.raises(ValueError, match="sdz"):
        disk_class.apply_classes(USER_PC, {"sdz": DiskClass.SSD})


def test_toggle_switches_the_current_class() -> None:
    first = disk_class.toggled({}, GSKILL)
    assert first == {"sda": DiskClass.SSD}
    assert disk_class.toggled(first, GSKILL) == {"sda": DiskClass.HDD}
    ssd = Disk(name="nvme0n1", rotational=False, nvme=True)
    assert disk_class.toggled({}, ssd) == {"nvme0n1": DiskClass.HDD}


def test_user_pc_plans_main_on_the_ssd_once_confirmed() -> None:
    """Item 34: the kernel's view put `main` on the HDD mirror and `sda` in
    `large`; answered SSD, `sda` holds `main` and the HDD pair is swap."""

    unanswered = plan_storage("fast", USER_PC, ram_gb=16)
    assert {vg["name"]: vg["devices"] for vg in unanswered["vgs"]} == {
        "main": ["md0"],
        "large": ["sda1"],
    }

    answers = {"sda": DiskClass.SSD}
    plan = disk_class.annotate_plan(
        plan_storage("fast", disk_class.apply_classes(USER_PC, answers), ram_gb=16), answers
    )
    vgs = {vg["name"]: vg["devices"] for vg in plan["vgs"]}
    assert vgs == {"main": ["sda2"], "swap": ["md0"]}
    assert plan["disk_classes"] == {"sda": "ssd"}


def test_annotate_plan_without_answers_returns_the_plan() -> None:
    plan = {"vgs": []}
    assert disk_class.annotate_plan(plan, {}) is plan
    annotated = disk_class.annotate_plan(plan, {"sdb": DiskClass.HDD, "sda": DiskClass.SSD})
    assert annotated == {"vgs": [], "disk_classes": {"sda": "ssd", "sdb": "hdd"}}
    assert plan == {"vgs": []}


def test_refusal_message_names_the_disks_and_the_answers() -> None:
    message = disk_class.refusal_message([GSKILL])
    assert "sda (G.SKILL 128GB SSD)" in message
    assert "pre-nixos-tui" in message and "--ssd" in message and "--hdd" in message
    with pytest.raises(AssertionError):
        disk_class.refusal_message([])
