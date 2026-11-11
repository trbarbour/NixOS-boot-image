"""The image writer's CLI, root helper and TUI glue (task queue item 42).

R-W1 build as the user and write in one command; R-W3 typed confirmation;
R-W5 the root helper re-checks eligibility; R-W6 the TUI runs the CLI.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys
from pathlib import Path
from typing import List, Tuple

import pytest

from tests.test_write_image_devices import FakeSys
from write_image import cli, helper, tui

GIB = 1024**3


@pytest.fixture
def fake(tmp_path: Path) -> FakeSys:
    sys_ = FakeSys(tmp_path)
    sys_.disk("sda", bus_path="pci0000:00/0000:00:11.0/ata1/host0/t/0:0:0:0", model="Internal")
    sys_.disk("sdb", bus_path="pci0000:00/0000:00:14.0/usb2/2-1/2-1:1.0/host6/t/6:0:0:0",
              removable=True, model="SanDisk Ultra", size_bytes=1 * GIB)
    sys_.disk("mmcblk0", bus_path="platform/fe340000.mmc/mmc_host/mmc0/mmc0:aaaa", model="SC64G", serial=None)
    return sys_


@pytest.fixture
def iso_output(tmp_path: Path) -> Path:
    out = tmp_path / "nix-store-output"
    (out / "iso").mkdir(parents=True)
    (out / "iso/pre-nixos-0.30.0-x86_64-linux.iso").write_bytes(b"ISO" * 1000)
    return out


class Recorder:
    """A fake command runner: ``nix build`` prints the output path."""

    def __init__(self, output: Path, helper_status: int = 0) -> None:
        self.calls: List[Tuple[List[str], bool]] = []
        self.output = output
        self.helper_status = helper_status

    def __call__(self, cmd: List[str], capture: bool) -> Tuple[int, str]:
        self.calls.append((cmd, capture))
        if cmd[0] == "nix":
            return 0, f"{self.output}\n"
        return self.helper_status, ""


def _flag(cmd: List[str], name: str) -> str:
    return cmd[cmd.index(name) + 1]


def _cli(fake: FakeSys, runner: Recorder, argv: List[str], answers: List[str], euid: int = 1000) -> Tuple[int, str]:
    out = io.StringIO()
    replies = iter(answers)
    status = cli.main(
        argv, run=runner, view=fake.view, prompt=lambda text: next(replies), euid=lambda: euid, out=out
    )
    return status, out.getvalue()


def test_build_as_the_user_then_write_through_sudo(fake: FakeSys, iso_output: Path, tmp_path: Path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    runner = Recorder(iso_output)
    status, out = _cli(fake, runner, ["--format", "iso", "--site", str(site), "--device", "sdb", "--verify"], ["sdb"])
    assert status == 0, out
    (build, captured), (write, _) = runner.calls
    assert build == [
        "nix", "build", ".#bootImage", "--no-link", "--print-out-paths",
        "--override-input", "site", f"path:{site}",
    ] and captured
    assert write[:2] == ["sudo", "--"] and write[2] == sys.executable and write[3] == "-I"
    assert _flag(write, "--device") == "sdb" and write[-1] == "--verify"
    assert _flag(write, "--image") == str(iso_output / "iso/pre-nixos-0.30.0-x86_64-linux.iso")
    assert "SanDisk Ultra" in out


def test_sd_format_builds_the_sd_image(fake: FakeSys, tmp_path: Path) -> None:
    out_dir = tmp_path / "sd-out"
    (out_dir / "sd-image").mkdir(parents=True)
    (out_dir / "sd-image/x-aarch64-linux.img.zst").write_bytes(b"z")
    runner = Recorder(out_dir)
    status, _ = _cli(fake, runner, ["--format", "sd", "--site", str(tmp_path), "--device", "mmcblk0", "--yes"], [])
    assert status == 0
    assert runner.calls[0][0][2] == ".#bootImageSd"


def test_wrong_confirmation_writes_nothing(fake: FakeSys, iso_output: Path) -> None:
    runner = Recorder(iso_output)
    status, out = _cli(fake, runner, ["--format", "iso", "--image", str(next(iso_output.glob("iso/*.iso"))), "--device", "sdb"], ["sda"])
    assert status == cli.EXIT_REFUSED
    assert runner.calls == []
    assert "not confirmed" in out


def test_ineligible_device_is_refused_before_anything_runs(fake: FakeSys, iso_output: Path) -> None:
    runner = Recorder(iso_output)
    status, out = _cli(fake, runner, ["--format", "iso", "--site", ".", "--device", "sda", "--yes"], [])
    assert status == cli.EXIT_REFUSED and runner.calls == []
    assert "not removable" in out


def test_device_chosen_from_a_numbered_list(fake: FakeSys, iso_output: Path) -> None:
    runner = Recorder(iso_output)
    iso = str(next(iso_output.glob("iso/*.iso")))
    status, out = _cli(fake, runner, ["--format", "iso", "--image", iso], ["1", "sdb"])
    assert status == 0, out
    assert "1) /dev/sdb" in out and "2) /dev/mmcblk0" in out  # USB first for the ISO
    assert _flag(runner.calls[0][0], "--device") == "sdb" and _flag(runner.calls[0][0], "--image") == iso


def test_as_root_the_helper_runs_without_sudo(fake: FakeSys, iso_output: Path) -> None:
    runner = Recorder(iso_output)
    iso = str(next(iso_output.glob("iso/*.iso")))
    status, _ = _cli(fake, runner, ["--format", "iso", "--image", iso, "--device", "sdb", "--yes"], [], euid=0)
    assert status == 0 and runner.calls[0][0][0] == sys.executable


def test_helper_failure_is_passed_on(fake: FakeSys, iso_output: Path) -> None:
    runner = Recorder(iso_output, helper_status=helper.EXIT_VERIFY_FAILED)
    iso = str(next(iso_output.glob("iso/*.iso")))
    status, _ = _cli(fake, runner, ["--format", "iso", "--image", iso, "--device", "sdb", "--yes"], [])
    assert status == helper.EXIT_VERIFY_FAILED


def test_list_as_json(fake: FakeSys, iso_output: Path) -> None:
    status, out = _cli(fake, Recorder(iso_output), ["--list", "--json", "--format", "sd"], [])
    assert status == 0
    listing = json.loads(out)
    assert [c["name"] for c in listing["candidates"]] == ["mmcblk0", "sdb"]
    assert listing["refusals"] == [{"name": "sda", "reason": "not removable (sata disk)"}]


# --- the root helper (R-W5) ---------------------------------------------------


def test_helper_writes_and_verifies(fake: FakeSys, tmp_path: Path) -> None:
    data = bytes(range(256)) * 4096
    img = tmp_path / "image.iso"
    img.write_bytes(data)
    device = tmp_path / "device"
    device.write_bytes(b"\0" * len(data))
    opened: List[str] = []

    def open_device(path: str) -> int:
        opened.append(path)
        return os.open(device, os.O_RDWR)

    status = helper.main(["--device", "sdb", "--image", str(img), "--verify"], view=fake.view, open_device=open_device)
    assert status == 0
    assert opened == ["/dev/sdb"]
    assert hashlib.sha256(device.read_bytes()).hexdigest() == hashlib.sha256(data).hexdigest()


def test_helper_rechecks_eligibility(fake: FakeSys, tmp_path: Path) -> None:
    img = tmp_path / "image.iso"
    img.write_bytes(b"x")
    status = helper.main(["--device", "sda", "--image", str(img)], view=fake.view,
                         open_device=lambda path: pytest.fail("opened an ineligible device"))
    assert status == helper.EXIT_REFUSED


def test_helper_refuses_an_image_larger_than_the_device(fake: FakeSys, tmp_path: Path) -> None:
    img = tmp_path / "image.iso"
    with img.open("wb") as handle:
        handle.truncate(2 * GIB)  # sparse; sdb is 1 GiB
    status = helper.main(["--device", "sdb", "--image", str(img)], view=fake.view,
                         open_device=lambda path: pytest.fail("opened a device that is too small"))
    assert status == helper.EXIT_REFUSED


# --- the TUI runs the CLI (R-W6) --------------------------------------------


def test_tui_choices_become_cli_arguments() -> None:
    choices = tui.Choices(fmt="sd", site="/home/me/site", image=None, device="mmcblk0", verify=True)
    assert tui.cli_argv(choices) == ["--format", "sd", "--site", "/home/me/site", "--device", "mmcblk0", "--verify"]
    plain = tui.Choices(fmt="iso", site=None, image="/tmp/x.iso", device="sdb", verify=False)
    argv = tui.cli_argv(plain)
    assert argv == ["--format", "iso", "--image", "/tmp/x.iso", "--device", "sdb"]
    assert "--yes" not in argv  # the CLI asks for the typed confirmation


# --- Codex on #350 ------------------------------------------------------------


def test_cli_passes_the_confirmed_identity(fake: FakeSys, iso_output: Path) -> None:
    runner = Recorder(iso_output)
    iso = str(next(iso_output.glob("iso/*.iso")))
    status, _ = _cli(fake, runner, ["--format", "iso", "--image", iso, "--device", "sdb", "--yes"], [])
    assert status == 0
    cmd = runner.calls[0][0]
    for flag, value in (("--expect-model", "SanDisk Ultra"), ("--expect-serial", "SER123"), ("--expect-size", str(GIB))):
        assert cmd[cmd.index(flag) + 1] == value


def test_helper_refuses_a_replacement_disk_with_the_same_name(fake: FakeSys, tmp_path: Path) -> None:
    """Finding 1: the confirmed stick was swapped during the build; the new disk
    got the same kernel name.  It must not be written."""

    img = tmp_path / "image.iso"
    img.write_bytes(b"x")
    argv = ["--device", "sdb", "--image", str(img),
            "--expect-model", "Kingston DataTraveler", "--expect-serial", "OTHER", "--expect-size", str(GIB)]
    status = helper.main(argv, view=fake.view, open_device=lambda path: pytest.fail("opened a replacement disk"))
    assert status == helper.EXIT_REFUSED


def test_helper_refuses_when_the_opened_file_is_another_device(fake: FakeSys, tmp_path: Path) -> None:
    """The name could change between the check and the open: the opened block
    device must be the one sysfs describes."""

    (fake.block / "sdb" / "dev").write_text("8:16\n")
    img = tmp_path / "image.iso"
    img.write_bytes(b"x")
    calls: List[str] = []
    status = helper.main(
        ["--device", "sdb", "--image", str(img)], view=fake.view,
        open_device=lambda path: calls.append(path) or os.open(img, os.O_RDONLY),
        device_number=lambda fd: (8, 32),
    )
    assert calls == ["/dev/sdb"] and status == helper.EXIT_REFUSED
