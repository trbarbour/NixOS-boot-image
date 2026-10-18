"""Forced cleanup must release mounts and swap before deactivating LVM/md.

Regression for trbarbour/NixOS-boot-image#307 (VM run 2026-10-18,
notes/2026-10-18T155000Z-vm-run.md): after the boot-time auto-apply, disko
leaves the target mounted (``/mnt`` on main/slash, ``/mnt/boot`` on the ESP)
and swap active.  The forced cleanup then

1. ran ``lvchange -an`` on the ``lvs`` alias of an LV (``/dev/main/slash``)
   before the ``lsblk`` alias carrying the mountpoint was unmounted;
2. unmounted ``/mnt`` before ``/mnt/boot`` (alphabetical node order), which
   fails as busy and was never retried;
3. ran ``umount '[SWAP]'``.

The runner below enforces the kernel's rules, so the fake reproduces the
failure instead of just recording commands.
"""
from __future__ import annotations

import subprocess
from typing import Dict, List, Sequence, Set

import pytest

from pre_nixos import storage_cleanup

LV_ALIASES = {
    "/dev/main/slash": "main/slash",
    "/dev/mapper/main-slash": "main/slash",
    "/dev/main/swap": "main/swap",
    "/dev/mapper/main-swap": "main/swap",
}


class KernelModel:
    """Tracks mounts, swaps and active LVs; refuses what the kernel refuses."""

    def __init__(self) -> None:
        self.mounts: Dict[str, str] = {
            "/mnt": "main/slash",
            "/mnt/boot": "/dev/vda1",
        }
        self.active_swaps: Set[str] = {"main/swap"}
        self.active_lvs: Set[str] = {"main/slash", "main/swap"}
        self.commands: List[tuple[str, ...]] = []
        self.failures: List[tuple[str, ...]] = []

    def _lv_in_use(self, lv: str) -> bool:
        return lv in self.mounts.values() or lv in self.active_swaps

    def _result(self, cmd: Sequence[str], code: int) -> subprocess.CompletedProcess:
        if code != 0:
            self.failures.append(tuple(cmd))
        return subprocess.CompletedProcess(cmd, code, stdout="", stderr="")

    def __call__(self, cmd: Sequence[str]) -> subprocess.CompletedProcess:
        self.commands.append(tuple(cmd))
        name, args = cmd[0], list(cmd[1:])
        if name == "umount":
            recursive = "-R" in args
            target = [a for a in args if not a.startswith("-")][-1]
            if target not in self.mounts:
                return self._result(cmd, 32)  # not mounted / no mount point
            nested = [m for m in self.mounts if m.startswith(target.rstrip("/") + "/")]
            if nested and not recursive:
                return self._result(cmd, 32)  # target is busy
            for mountpoint in [target, *nested]:
                del self.mounts[mountpoint]
            return self._result(cmd, 0)
        if name == "swapoff":
            lv = LV_ALIASES.get(args[-1], args[-1])
            if lv not in self.active_swaps:
                return self._result(cmd, 1)
            self.active_swaps.discard(lv)
            return self._result(cmd, 0)
        if name == "lvchange" and args[:1] == ["-an"]:
            lv = LV_ALIASES.get(args[-1], args[-1])
            if self._lv_in_use(lv):
                return self._result(cmd, 5)  # contains a filesystem in use
            self.active_lvs.discard(lv)
            return self._result(cmd, 0)
        if name == "vgchange" and args[:1] == ["-an"]:
            if any(self._lv_in_use(lv) for lv in self.active_lvs):
                return self._result(cmd, 5)
            self.active_lvs.clear()
            return self._result(cmd, 0)
        return self._result(cmd, 0)


def install_mounted_target(monkeypatch: pytest.MonkeyPatch) -> KernelModel:
    """The storage state disko leaves behind after the boot-time auto-apply."""

    lsblk = [
        {
            "name": "/dev/vda",
            "type": "disk",
            "children": [
                {"name": "/dev/vda1", "type": "part", "fstype": "vfat", "mountpoints": ["/mnt/boot"]},
                {
                    "name": "/dev/vda2",
                    "type": "part",
                    "fstype": "LVM2_member",
                    "children": [
                        {"name": "/dev/mapper/main-slash", "type": "lvm", "fstype": "ext4", "mountpoints": ["/mnt"]},
                        {"name": "/dev/mapper/main-swap", "type": "lvm", "fstype": "swap", "mountpoints": ["[SWAP]"]},
                    ],
                },
            ],
        }
    ]
    monkeypatch.setattr(storage_cleanup, "_list_block_devices", lambda: lsblk)
    monkeypatch.setattr(storage_cleanup, "_list_pvs", lambda: [{"pv_name": "/dev/vda2", "vg_name": "main"}])
    monkeypatch.setattr(storage_cleanup, "_list_vgs", lambda: [{"vg_name": "main"}])
    monkeypatch.setattr(
        storage_cleanup,
        "_list_lvs",
        lambda: [
            {"lv_path": "/dev/main/slash", "vg_name": "main"},
            {"lv_path": "/dev/main/swap", "vg_name": "main"},
        ],
    )
    monkeypatch.setattr(storage_cleanup, "_list_losetup", lambda: [])
    monkeypatch.setattr(storage_cleanup, "_verify_md_lvm_absent", lambda *a, **k: None)
    return KernelModel()


@pytest.fixture
def mounted_target(monkeypatch: pytest.MonkeyPatch) -> KernelModel:
    return install_mounted_target(monkeypatch)


def _run_cleanup(model: KernelModel) -> None:
    storage_cleanup.perform_storage_cleanup(
        storage_cleanup.WIPE_SIGNATURES, ["/dev/vda"], execute=True, runner=model
    )


def test_cleanup_releases_everything_on_a_mounted_target(mounted_target: KernelModel) -> None:
    _run_cleanup(mounted_target)

    assert mounted_target.mounts == {}
    assert mounted_target.active_swaps == set()
    assert mounted_target.active_lvs == set()


def test_no_lvm_or_md_deactivation_is_attempted_while_in_use(mounted_target: KernelModel) -> None:
    _run_cleanup(mounted_target)

    refused = [c for c in mounted_target.failures if c[0] in {"lvchange", "vgchange", "umount"}]
    assert refused == []


def test_pseudo_mountpoints_are_never_unmounted(mounted_target: KernelModel) -> None:
    _run_cleanup(mounted_target)

    assert not any(c[0] == "umount" and c[-1].startswith("[") for c in mounted_target.commands)
