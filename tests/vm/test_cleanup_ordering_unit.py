"""The RAID/LVM residue scenario must not race the boot-time pre-nixos run.

Regression (2026-10-18, ``notes/2026-10-18T040407Z-vm-run.md``): the scenario
seeded residue while the boot-time ``pre-nixos`` run was still waiting for the
LAN; that run then tore the residue down ("Tearing down existing storage") a
second after it was written, so the scenario's sanity read came back empty.
On a real VM this only happens with unlucky timing, so the ordering is pinned
here against a fake VM that models the boot-time run deterministically.
"""
from __future__ import annotations

import re
from typing import List

import tests.vm.test_pre_nixos_cleanup as cleanup_scenario
from tests.vm.cleanup_plan import build_raid_residue_plan

# Commands that create or destroy storage state on the VM's disks.
STORAGE_MUTATION = re.compile(r"^(mdadm --(create|stop)|wipefs|pvcreate|vgcreate|lvcreate)\b|\bdd of=")


class RacingVM:
    """Fake VM whose boot-time ``pre-nixos`` run stays active until awaited."""

    def __init__(self) -> None:
        self.boot_run_active = True
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

    def run_as_root_checked(self, command: str, *, timeout: int = 180) -> str:
        return self.run_as_root(command, timeout=timeout)

    def run_as_root(self, command: str, *, timeout: int = 180) -> str:
        if STORAGE_MUTATION.search(command):
            if self.boot_run_active:
                self.violations.append(command)
            if "dd of=" in command:
                self.residue_present = True
            return ""
        if command.startswith("systemctl restart pre-nixos"):
            self.cleanup_requested = True
            return ""
        if command.startswith("ls -l /dev/vd"):
            return "/dev/vda\n/dev/vdb\n/dev/vdc\n/dev/md127"
        if "dd if=" in command:
            return "|residue-marker..|" if self.residue_present else ""
        return ""


def test_storage_mutation_pattern_matches_the_seeding_commands() -> None:
    """Guard the fake: every preseed command that writes storage is classified."""

    plan = build_raid_residue_plan()
    writers = [c for c in plan.preseed_commands if STORAGE_MUTATION.search(c)]
    assert len(writers) == 5  # mdadm --create, pvcreate, vgcreate, lvcreate, dd of=
    assert not STORAGE_MUTATION.search("mdadm --detail /dev/md127")


def test_residue_scenario_waits_for_boot_time_pre_nixos_before_touching_disks() -> None:
    vm = RacingVM()

    cleanup_scenario.test_pre_nixos_cleans_raid_lvm_residue(vm)  # type: ignore[arg-type]

    assert vm.violations == []
