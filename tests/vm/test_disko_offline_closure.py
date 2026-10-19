"""disko's run-time script must build offline from the boot image's closure.

Regression for trbarbour/NixOS-boot-image#311 (nixpkgs 26.05, 2026-10-18): the image lacked
``pkgs.stdenv`` with a C compiler, so disko's script could not be built in
the guest and every boot-time apply failed.  This builds the image's system
closure and its disko, dry-runs a planner-rendered configuration, and checks
every input output the script's build needs is in the closure, without
booting a VM (minutes instead of a full boot cycle).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from pre_nixos import apply, planner
from pre_nixos.inventory import Disk
from scripts.nix_git_inputs import nix_command
from tests.vm.fixtures import REPO_ROOT
from tests.vm.offline_closure import missing_from_closure, required_input_outputs

pytestmark = [pytest.mark.vm, pytest.mark.slow]

CONFIG = ".#nixosConfigurations.pre-installer"


def _nix(nix: str, args: list[str]) -> str:
    result = subprocess.run(
        nix_command(nix, args), cwd=REPO_ROOT, capture_output=True, text=True
    )
    assert result.returncode == 0, f"nix {' '.join(args)} failed:\n{result.stderr[-4000:]}"
    return result.stdout


def _build(nix: str, attr: str) -> Path:
    return Path(_nix(nix, ["build", "--impure", "--no-link", "--print-out-paths", attr]).split()[-1])


GIB = 1024**3
LAYOUTS = {
    "single-disk": [Disk(name="vda", size=4 * GIB)],
    # SSD + HDD pair: the pair becomes a raid1 swap group (reqs §2.2).
    "raid1": [
        Disk(name="sda", size=4 * GIB),
        Disk(name="sdb", size=5 * GIB, rotational=True),
        Disk(name="sdc", size=5 * GIB, rotational=True),
    ],
}


@pytest.mark.parametrize("layout", sorted(LAYOUTS))
def test_disko_script_builds_from_the_image_closure(
    nix_executable: str, tmp_path: Path, layout: str
) -> None:
    toplevel = _build(nix_executable, f"{CONFIG}.config.system.build.toplevel")
    disko = _build(nix_executable, f"{CONFIG}.pkgs.disko")

    plan = planner.plan_storage("fast", LAYOUTS[layout], ram_gb=2)
    config = tmp_path / "disko-config.nix"
    config.write_text(apply._render_disko_config(plan["disko"]))
    dry = subprocess.run(
        [str(disko / "bin" / "disko"), "--dry-run", "--mode", "destroy,format,mount", str(config)],
        capture_output=True,
        text=True,
    )
    assert dry.returncode == 0, dry.stderr[-4000:]
    script = Path(dry.stdout.split()[-1])  # .../bin/disko-destroy-format-mount
    creates = [line for line in script.read_text().splitlines() if "mdadm --create" in line]
    assert bool(creates) == bool(plan["arrays"]), creates
    # Reqs §2.2 [R-R1]: arrays are created without a write-intent bitmap.
    assert all("--bitmap=none" in line for line in creates), creates
    drv = subprocess.run(
        ["nix-store", "--query", "--deriver", str(script.parents[1])],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    show = json.loads(_nix(nix_executable, ["derivation", "show", "--recursive", drv]))
    closure = subprocess.run(
        ["nix-store", "--query", "--requisites", str(toplevel)],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()

    missing = missing_from_closure(required_input_outputs(show, drv), closure)
    assert missing == [], "disko's script would need network access to build:\n" + "\n".join(missing)
