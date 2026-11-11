"""The CLI writes only to the disks it planned for (task queue item 50, R-D3).

Design: plans/2026-11-11T194943Z-disk-settle-design.md (D5).
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import pytest

from pre_nixos import inventory, pre_nixos
from pre_nixos.install import AutoInstallResult
from pre_nixos.inventory import Disk
from pre_nixos.storage_detection import ExistingStorageDevice

GIB = 1024**3
SDA = Disk(name="sda", model="Samsung SSD 850", size=250 * GIB, serial="A")
SDB = Disk(name="sdb", model="Samsung SSD 850", size=250 * GIB, serial="B")
LATE = Disk(name="sdc", model="ST3750528AS", size=750 * GIB, rotational=True, serial="C")


@pytest.fixture
def cli(monkeypatch, tmp_path, existing_storage):
    """Disks that change after the first inventory; writes recorded, not run."""

    monkeypatch.setenv("PRE_NIXOS_STATE_DIR", str(tmp_path / "state"))
    reads: List[List[Disk]] = [[SDA, SDB]]  # the plan's inventory; later reads see the last entry
    monkeypatch.setattr(
        pre_nixos.inventory, "enumerate_disks", lambda: list(reads.pop(0) if len(reads) > 1 else reads[0])
    )
    monkeypatch.setattr(pre_nixos.inventory, "detect_ram_gb", lambda: 16)
    lan = pre_nixos.network.LanConfiguration(authorized_key=tmp_path / "key.pub", interface="lan")
    monkeypatch.setattr(pre_nixos.network, "configure_lan", lambda: lan)
    calls: dict = {"apply": [], "install": [], "cleanup": [], "reads": reads}
    monkeypatch.setattr(
        pre_nixos.apply,
        "apply_plan",
        lambda plan, dry_run=False, protected_disks=frozenset(): calls["apply"].append(plan),
    )

    def fake_install(lan_config, plan, **kwargs):
        calls["install"].append(plan)
        return AutoInstallResult(status="skipped", reason="execution-disabled")

    monkeypatch.setattr(pre_nixos.install, "auto_install", fake_install)
    monkeypatch.setattr(
        pre_nixos.storage_cleanup,
        "perform_storage_cleanup",
        lambda action, devices, **kwargs: calls["cleanup"].append((action, devices)),
    )
    existing_storage.devices = []
    return calls


def _late_disk(cli) -> None:
    """The next inventory (the re-check) also sees the late disk."""

    cli["reads"][:] = [[SDA, SDB], [SDA, SDB, LATE]]


def test_the_plan_records_its_disks(cli, capsys) -> None:
    pre_nixos.main([])
    (plan,) = cli["apply"]
    assert [entry["name"] for entry in plan[inventory.PLAN_KEY]] == ["sda", "sdb"]


def test_a_disk_that_appears_before_writing_stops_the_run(cli, tmp_path, capsys) -> None:
    _late_disk(cli)
    with pytest.raises(SystemExit) as excinfo:
        pre_nixos.main([])
    assert excinfo.value.code == pre_nixos.EXIT_DISKS_CHANGED == 4
    assert cli["apply"] == [] and cli["install"] == []
    err = capsys.readouterr().err
    assert "added sdc (750 GiB, serial C)" in err
    status = (tmp_path / "state" / "auto-install-status").read_text()
    assert "STATE=skipped" in status and f"REASON={inventory.CHANGED_REASON}" in status


def test_existing_storage_is_not_wiped_for_a_changed_set(cli, monkeypatch, existing_storage, capsys) -> None:
    """The first write is the cleanup, so the re-check comes before it (D5)."""

    _late_disk(cli)
    existing_storage.devices = [ExistingStorageDevice(device="/dev/sda1", reasons=("ext4",))]
    monkeypatch.setenv("PRE_NIXOS_EXEC", "1")
    monkeypatch.setenv("PRE_NIXOS_FORCE_CLEANUP", "1")
    with pytest.raises(SystemExit) as excinfo:
        pre_nixos.main(["--plan-only"])
    assert excinfo.value.code == pre_nixos.EXIT_DISKS_CHANGED
    assert cli["cleanup"] == [] and cli["apply"] == []


def test_plan_only_does_not_check(cli, capsys) -> None:
    _late_disk(cli)
    pre_nixos.main(["--plan-only"])
    assert cli["apply"] == []
    assert "added sdc" not in capsys.readouterr().err


def test_dry_run_does_not_check(cli, capsys) -> None:
    _late_disk(cli)
    pre_nixos.main(["--dry-run"])
    assert len(cli["apply"]) == 1


def test_service_maps_the_exit_to_plan_only() -> None:
    """The boot service reports the stop as plan-only, and the login notice
    explains it (D4, D5)."""

    from pre_nixos import disk_settle

    modules = Path(__file__).resolve().parents[1] / "modules" / "pre-nixos"
    service = (modules / "service-script.nix").read_text()
    notice = (modules / "login-notice.sh").read_text()
    assert f'if [ "$pre_status" -eq {pre_nixos.EXIT_DISKS_CHANGED} ]; then' in service
    assert f'status_detail="{inventory.CHANGED_REASON}"' in service
    assert f'"$wait_status" -eq {disk_settle.EXIT_UNSETTLED}' in service
    for detail in (inventory.CHANGED_REASON, disk_settle.UNSETTLED_DETAIL, disk_settle.ERROR_DETAIL):
        assert f'"$detail" = "{detail}"' in notice
    # Shown on the consoles, so a pause at boot is explained (and the VM test
    # knows when to plug its late disk).
    assert f'wait_msg="{disk_settle.CONSOLE_NOTICE}"' in service
    # The wait comes before storage detection, which reads the same disks (D1).
    assert service.index("pre-nixos-wait-disks") < service.index("detectStorageCmd}; then")
