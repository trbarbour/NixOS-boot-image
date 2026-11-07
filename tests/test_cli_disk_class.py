"""The CLI and disks named SSD but reported as rotating (R-S3; task queue
item 34; plans/2026-11-07T161535Z-ssd-model-name-design.md, D2 (b), D3 (c))."""

from __future__ import annotations

import json

import pytest

from pre_nixos import pre_nixos
from pre_nixos.install import AutoInstallResult
from tests.test_disk_class import USER_PC


@pytest.fixture
def cli(monkeypatch, tmp_path):
    """The user's PC, with provisioning and installing recorded, not run."""

    monkeypatch.setenv("PRE_NIXOS_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(pre_nixos.inventory, "enumerate_disks", lambda: list(USER_PC))
    monkeypatch.setattr(pre_nixos.inventory, "detect_ram_gb", lambda: 16)
    lan = pre_nixos.network.LanConfiguration(authorized_key=tmp_path / "key.pub", interface="lan")
    monkeypatch.setattr(pre_nixos.network, "configure_lan", lambda: lan)
    calls: dict[str, list] = {"apply": [], "install": []}
    monkeypatch.setattr(
        pre_nixos.apply,
        "apply_plan",
        lambda plan, dry_run=False, protected_disks=frozenset(): calls["apply"].append(plan),
    )

    def fake_install(lan_config, plan, **kwargs):
        calls["install"].append(plan)
        return AutoInstallResult(status="skipped", reason="execution-disabled")

    monkeypatch.setattr(pre_nixos.install, "auto_install", fake_install)
    return calls


def _auto_status(tmp_path) -> str:
    return (tmp_path / "state" / "auto-install-status").read_text()


@pytest.mark.parametrize("auto_install", [True, False])
def test_unanswered_disk_stops_provisioning_and_install(
    cli, monkeypatch, tmp_path, capsys, auto_install
) -> None:
    """D2 (b): not only the install; the boot run provisions blank disks
    even with auto-install off, so it must stop before that too."""

    if auto_install:
        monkeypatch.setenv("PRE_NIXOS_AUTO_INSTALL", "1")
    with pytest.raises(SystemExit) as excinfo:
        pre_nixos.main([])
    assert excinfo.value.code == pre_nixos.EXIT_NEEDS_ANSWER == 3
    assert cli == {"apply": [], "install": []}
    err = capsys.readouterr().err
    assert "sda (G.SKILL 128GB SSD)" in err and "--ssd" in err
    status = _auto_status(tmp_path)
    assert "STATE=skipped" in status and "REASON=disk-class-unconfirmed" in status


def test_plan_only_shows_the_kernel_plan_and_the_question(cli, capsys) -> None:
    pre_nixos.main(["--plan-only"])
    captured = capsys.readouterr()
    plan = json.loads(captured.out)
    assert {vg["name"]: vg["devices"] for vg in plan["vgs"]} == {
        "main": ["md0"],
        "large": ["sda1"],
    }
    assert "disk_classes" not in plan
    assert "Disk type unconfirmed" in captured.err
    assert cli == {"apply": [], "install": []}


def test_answer_ssd_plans_main_on_it_and_provisions(cli, capsys) -> None:
    pre_nixos.main(["--ssd", "/dev/sda"])
    captured = capsys.readouterr()
    assert "Disk type unconfirmed" not in captured.err
    (plan,) = cli["apply"]
    # x86 (UEFI here): BIOS boot partition 1, ESP 2, data 3 (R-B1, D2).
    assert {vg["name"]: vg["devices"] for vg in plan["vgs"]} == {
        "main": ["sda3"],
        "swap": ["md0"],
    }
    assert plan["disk_classes"] == {"sda": "ssd"}
    assert cli["install"] == [plan]


def test_answer_hdd_keeps_the_kernel_plan(cli) -> None:
    pre_nixos.main(["--hdd", "sda"])
    (plan,) = cli["apply"]
    assert {vg["name"] for vg in plan["vgs"]} == {"main", "large"}
    assert plan["disk_classes"] == {"sda": "hdd"}


@pytest.mark.parametrize(
    "argv, message",
    [
        (["--ssd", "sdz"], "sdz"),
        (["--ssd", "sda", "--hdd", "sda"], "both SSD and HDD"),
    ],
)
def test_bad_answers_are_usage_errors(cli, capsys, argv, message) -> None:
    with pytest.raises(SystemExit) as excinfo:
        pre_nixos.main(argv)
    assert excinfo.value.code == 2
    assert message in capsys.readouterr().err
    assert cli == {"apply": [], "install": []}


def test_boot_service_and_login_notice_use_the_same_values() -> None:
    """The exit status and DETAIL are repeated in shell; keep them in step
    (the flake check ``boot-service-status`` runs the service script)."""

    from pathlib import Path

    from pre_nixos import disk_class

    modules = Path(__file__).resolve().parents[1] / "modules" / "pre-nixos"
    service = (modules / "service-script.nix").read_text()
    notice = (modules / "login-notice.sh").read_text()
    assert f'if [ "$pre_status" -eq {pre_nixos.EXIT_NEEDS_ANSWER} ]; then' in service
    assert f'status_detail="{disk_class.UNCONFIRMED_REASON}"' in service
    assert f'"$detail" = "{disk_class.UNCONFIRMED_REASON}"' in notice


def test_install_now_rejects_disk_classes(cli, capsys) -> None:
    """--install-now uses the last applied plan; an answer would be ignored."""

    with pytest.raises(SystemExit) as excinfo:
        pre_nixos.main(["--install-now", "--ssd", "sda"])
    assert excinfo.value.code == 2
    assert "--install-now cannot be combined with planning options" in capsys.readouterr().err
