"""Regression tests for boot console ordering in the pre-installer image."""

from __future__ import annotations

from pathlib import Path


def test_boot_kernel_params_keep_vga_console_primary() -> None:
    module_text = Path("modules/pre-nixos.nix").read_text(encoding="utf-8")

    serial_index = module_text.find('"console=ttyS0,115200n8"')
    vga_index = module_text.find('"console=tty0"')

    assert serial_index != -1, "pre-installer boot kernel params must include ttyS0 for debug serial logs"
    assert vga_index != -1, "pre-installer boot kernel params must include tty0 for local display output"
    assert serial_index < vga_index, (
        "tty0 must remain the last console= kernel parameter so non-serial systems "
        "keep boot output on the physical display"
    )
