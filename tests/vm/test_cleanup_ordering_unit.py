"""The RAID/LVM residue scenario must not race the boot-time pre-nixos run.

Regressions (2026-10-18, ``notes/2026-10-18T040407Z-vm-run.md`` and
``notes/2026-10-18T044623Z-vm-run.md``): the boot-time ``pre-nixos`` run
provisions every disk it can see.  Seeding residue while it ran let it tear the
residue down; seeding after it finished failed because it had taken the disks
("Device or resource busy").  The scenario therefore waits for the boot-time
run and only then hot-plugs fresh disks for the residue.  On a real VM the
outcome depended on timing, so the ordering is pinned here against a fake VM
that models the boot-time run deterministically.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

import tests.vm.test_pre_nixos_cleanup as cleanup_scenario
from tests.vm.cleanup_plan import build_raid_residue_plan

# Commands that create or destroy storage state on the VM's disks.
STORAGE_MUTATION = re.compile(r"^(mdadm --(create|stop)|wipefs|pvcreate|vgcreate|lvcreate)\b|\bdd of=")


class RacingVM:
    """Fake VM: the boot-time run is active until awaited; extra disks are absent until hot-plugged."""

    def __init__(self) -> None:
        self.boot_run_active = True
        self.attached: Dict[str, str] = {}
        self.violations: List[str] = []
        self.residue_present = False
        self.cleanup_requested = False

    def assert_commands_available(self, *commands: str) -> None:
        pass

    def wait_for_unit_inactive(self, unit: str, *, timeout: int = 240) -> str:
        assert unit == "pre-nixos"
        self.boot_run_active = False
        if self.cleanup_requested:
            self.residue_present = False
        return "inactive"

    def hotplug_disk(self, image: Path, *, serial: str, timeout: int = 120) -> str:
        if self.boot_run_active:
            self.violations.append(f"hotplug {serial} while boot-time pre-nixos is active")
        device = f"/dev/vd{'bcdefg'[len(self.attached)]}"
        self.attached[serial] = device
        return device

    def run_as_root_checked(self, command: str, *, timeout: int = 180) -> str:
        return self.run_as_root(command, timeout=timeout)

    def run_as_root(self, command: str, *, timeout: int = 180) -> str:
        if STORAGE_MUTATION.search(command):
            if self.boot_run_active:
                self.violations.append(f"{command!r} while boot-time pre-nixos is active")
            if len(self.attached) < 2:
                self.violations.append(f"{command!r} before the residue disks are attached")
            if "dd of=" in command:
                self.residue_present = True
            return ""
        if command.startswith("systemctl restart pre-nixos"):
            self.cleanup_requested = True
            return ""
        if command.startswith("ls -l /dev/vd"):
            return "\n".join(["/dev/vda", *self.attached.values()])
        if "dd if=" in command:
            return "|residue-marker..|" if self.residue_present else ""
        return ""


def test_storage_mutation_pattern_matches_the_seeding_commands() -> None:
    """Guard the fake: every preseed command that writes storage is classified."""

    plan = build_raid_residue_plan()
    writers = [c for c in plan.preseed_commands if STORAGE_MUTATION.search(c)]
    assert len(writers) == 5  # mdadm --create, pvcreate, vgcreate, lvcreate, dd of=
    assert not STORAGE_MUTATION.search("mdadm --detail /dev/md127")


def test_residue_scenario_waits_then_hotplugs_then_seeds() -> None:
    vm = RacingVM()
    disks = [Path("/fake/disk1.img"), Path("/fake/disk2.img")]

    cleanup_scenario.test_pre_nixos_cleans_raid_lvm_residue(vm, disks)  # type: ignore[arg-type]

    assert vm.violations == []
    assert vm.attached == {"residue-a": "/dev/vdb", "residue-b": "/dev/vdc"}
