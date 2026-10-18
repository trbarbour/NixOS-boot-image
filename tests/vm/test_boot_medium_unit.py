"""Unit tests for the VM boot-medium arguments (no QEMU needed)."""

from __future__ import annotations

from pathlib import Path

from tests.vm.boot_medium import UsbStick, boot_medium_args, file_sha256, make_usb_stick


def test_cdrom_boot_is_the_default(tmp_path: Path) -> None:
    iso = tmp_path / "image.iso"
    assert boot_medium_args(iso, None) == ["-boot", "d", "-cdrom", str(iso)]


def test_usb_stick_is_non_removable_and_first_in_boot_order(tmp_path: Path) -> None:
    stick = UsbStick(path=tmp_path / "stick.img", sha256_before="0" * 64)
    args = boot_medium_args(tmp_path / "image.iso", stick)
    assert "-cdrom" not in args and "-boot" not in args
    assert f"file={stick.path},if=none,id=usbstick,format=raw" in args
    assert "usb-storage,bus=xhci.0,drive=usbstick,removable=off,bootindex=0" in args


def test_make_usb_stick_is_a_writable_identical_copy(tmp_path: Path) -> None:
    iso = tmp_path / "image.iso"
    iso.write_bytes(b"\x00hybrid-iso" * 1000)
    iso.chmod(0o444)
    stick = make_usb_stick(iso, tmp_path / "stick.img")
    assert stick.path.read_bytes() == iso.read_bytes()
    assert stick.sha256_before == file_sha256(iso)
    with stick.path.open("r+b"):
        pass
