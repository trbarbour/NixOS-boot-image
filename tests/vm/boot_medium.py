"""How the VM is given the boot image: as a CD-ROM, or as a writable USB stick.

The USB stick reproduces the usual x86 install medium (a dd'd ISO on a
thumb drive) that reports RM=0, for which reqs §2.3 requires the medium to be
neither modified nor counted as existing storage (trbarbour/NixOS-boot-image#306).
Spike 2026-10-18 (notes/2026-10-18T190817Z-usb-stick-spike.md): SeaBIOS boots
the hybrid ISO from ``usb-storage,removable=off``; the guest sees it as
``/dev/sda`` (TRAN=usb, RM=0) with ``/dev/sda1`` mounted on ``/iso``.
"""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

_HASH_CHUNK_BYTES = 1024 * 1024


@dataclass(frozen=True)
class UsbStick:
    """A writable copy of the ISO and its SHA-256 before the VM ran."""

    path: Path
    sha256_before: str


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_HASH_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def make_usb_stick(iso_path: Path, stick_path: Path) -> UsbStick:
    """Copy the (read-only, Nix store) ISO to a writable stick image."""

    shutil.copyfile(iso_path, stick_path)
    stick_path.chmod(0o644)
    stick = UsbStick(path=stick_path, sha256_before=file_sha256(stick_path))
    assert stick.sha256_before == file_sha256(iso_path), "stick copy differs from ISO"
    return stick


def boot_medium_args(iso_path: Path, usb_stick: Optional[UsbStick]) -> List[str]:
    """QEMU arguments attaching the boot medium and booting from it."""

    if usb_stick is None:
        return ["-boot", "d", "-cdrom", str(iso_path)]
    return [
        "-device",
        "qemu-xhci,id=xhci",
        "-drive",
        f"file={usb_stick.path},if=none,id=usbstick,format=raw",
        "-device",
        "usb-storage,bus=xhci.0,drive=usbstick,removable=off,bootindex=0",
    ]


__all__ = ["UsbStick", "boot_medium_args", "file_sha256", "make_usb_stick"]
