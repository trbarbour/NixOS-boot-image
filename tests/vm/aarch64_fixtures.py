"""Fixtures for the AArch64 SD image VM test (AArch64 plan §4, item 7).

Builds ``packages.aarch64-linux.bootImageSd`` (under binfmt emulation, R-T1)
with the test root key, and boots the system closure inside it on
``qemu-system-aarch64 -M virt`` (``tests/vm/machines.py``).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Iterator

import pytest

from tests.vm.fixtures import (
    BootImageBuild,
    SSHKeyPair,
    _launch_boot_image_vm,
    _require_executable,
    build_boot_artifact,
)
from tests.vm.machines import Aarch64System, aarch64_machine

if TYPE_CHECKING:  # pragma: no cover - type checking only
    import pexpect

    from tests.vm.controller import BootImageVM

SD_IMAGE_ATTRIBUTE = ".#packages.aarch64-linux.bootImageSd"
# E5 run6: an image-sized card leaves the first-boot grow nothing to grow
# into, and disko then ran out of space; real cards are larger.
SD_CARD_BYTES = 8 * 1024**3


@dataclass(frozen=True)
class Aarch64Build:
    image: BootImageBuild  # ``iso_path`` is the compressed SD image file
    system: Aarch64System


def image_system(image_store_path: Path) -> Path:
    """The system closure *inside* the image, taken from its own derivation.

    A separate evaluation of the system attribute can disagree with the image:
    the package source is the whole flake (``src = ./.``), so a tree change
    between two evaluations yields a different system (first run, 2026-10-19:
    test files committed mid-run).  Deriving it from the image cannot.
    """

    deriver = subprocess.run(
        ["nix-store", "--query", "--deriver", str(image_store_path)],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    closure = subprocess.run(
        ["nix-store", "--query", "--requisites", deriver],
        check=True, capture_output=True, text=True,
    ).stdout.split()
    systems = [d for d in closure if "-nixos-system-" in d and d.endswith(".drv")]
    assert len(systems) == 1, systems
    return Path(
        subprocess.run(
            ["nix-store", "--realise", systems[0]], check=True, capture_output=True, text=True
        ).stdout.split()[-1]
    )


@pytest.fixture(scope="session")
def aarch64_boot_image_build(
    nix_executable: str,
    boot_ssh_key_pair: SSHKeyPair,
    ssh_keygen_executable: str,
) -> Aarch64Build:
    image = build_boot_artifact(
        nix_executable, SD_IMAGE_ATTRIBUTE, boot_ssh_key_pair, ssh_keygen_executable
    )
    (sd_file,) = sorted((image.store_path / "sd-image").glob("*.img.zst"))
    return Aarch64Build(
        image=BootImageBuild(
            iso_path=sd_file,
            store_path=image.store_path,
            deriver=image.deriver,
            nar_hash=image.nar_hash,
            root_key_fingerprint=image.root_key_fingerprint,
            build_duration_seconds=image.build_duration_seconds,
        ),
        system=Aarch64System(image_system(image.store_path)),
    )


@pytest.fixture(scope="session")
def aarch64_sd_card(
    aarch64_boot_image_build: Aarch64Build, tmp_path_factory: pytest.TempPathFactory
) -> Path:
    """A writable, card-sized copy of the SD image."""

    card = tmp_path_factory.mktemp("aarch64-sd-card") / "sd.img"
    subprocess.run(
        [_require_executable("zstd"), "-d", "-q", "-o", str(card),
         str(aarch64_boot_image_build.image.iso_path)],
        check=True,
    )
    assert card.stat().st_size < SD_CARD_BYTES, "image no longer fits the virtual card"
    subprocess.run(["truncate", "-s", str(SD_CARD_BYTES), str(card)], check=True)
    return card


@pytest.fixture(scope="session")
def aarch64_boot_image_vm(
    _pexpect: "pexpect",
    aarch64_boot_image_build: Aarch64Build,
    aarch64_sd_card: Path,
    vm_disk_image_factory: Callable[..., Path],
    ssh_executable: str,
    request: pytest.FixtureRequest,
) -> Iterator["BootImageVM"]:
    """The AArch64 image with an empty 4 GiB virtio target disk (``/dev/vdb``)."""

    yield from _launch_boot_image_vm(
        _pexpect=_pexpect,
        machine=aarch64_machine(
            _require_executable("qemu-system-aarch64"),
            aarch64_boot_image_build.system,
            aarch64_sd_card,
        ),
        boot_image_build=aarch64_boot_image_build.image,
        vm_disk_image=vm_disk_image_factory(prefix="boot-image-disk-aarch64-target"),
        extra_disks=[],
        ssh_executable=ssh_executable,
        request=request,
    )
