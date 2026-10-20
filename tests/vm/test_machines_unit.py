"""Unit tests for tests/vm/machines.py (no QEMU needed)."""

from __future__ import annotations

from pathlib import Path

from tests.vm.boot_medium import boot_medium_args
from tests.vm.machines import Aarch64System, aarch64_machine, x86_machine

STOCK = "console=ttyS0,115200n8 console=ttyAMA0,115200n8 console=tty0 nohibernate root=fstab"


def _toplevel(tmp_path: Path) -> Path:
    top = tmp_path / "nixos-system"
    top.mkdir()
    (top / "kernel-params").write_text(STOCK + "\n")
    return top


def test_x86_machine_is_unchanged_boot_medium(tmp_path: Path) -> None:
    iso = tmp_path / "image.iso"
    machine = x86_machine("qemu-system-x86_64", iso, None, 300)
    assert machine.platform_args == tuple(boot_medium_args(iso, None))
    assert machine.login_timeout == 300


def test_aarch64_command_line_starts_with_the_stock_parameters(tmp_path: Path) -> None:
    """R-P2: the image's own kernel parameters come first and unchanged."""

    top = _toplevel(tmp_path)
    line = Aarch64System(top).kernel_command_line()
    assert line.startswith(STOCK + f" init={top}/init ")
    assert line.endswith("systemd.default_device_timeout_sec=900")


def test_aarch64_machine_boots_the_closure_with_the_card_first(tmp_path: Path) -> None:
    top = _toplevel(tmp_path)
    card = tmp_path / "sd.img"
    args = aarch64_machine("qemu-system-aarch64", Aarch64System(top), card).platform_args
    assert args[:4] == ("-M", "virt", "-cpu", "cortex-a72")
    assert args[args.index("-kernel") + 1] == str(top / "kernel")
    assert args[args.index("-initrd") + 1] == str(top / "initrd")
    assert args[-2:] == ("-drive", f"file={card},if=virtio,format=raw")
