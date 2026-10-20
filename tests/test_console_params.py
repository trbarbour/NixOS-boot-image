"""Installed-system console parameters keep every booted console (reqs §3 R-C1).

AArch64 plan §3.6.  The fixture is the user's CM4 /proc/cmdline on the stock
NixOS 26.05 SD image (plans/2026-10-18T220351Z-aarch64-user-answers.txt).
"""
from __future__ import annotations

import pytest

from pre_nixos import install

CM4_STOCK_CMDLINE = (
    "init=/nix/store/cqpbgpl9rf4s4bsp9p51af97d5zrkrx9-nixos-system-nixos-sd-card-26.05.11985.26f4107e47e3/init "
    "console=ttyS0,115200n8 console=ttyAMA0,115200n8 console=tty0 nohibernate "
    "root=fstab loglevel=7 lsm=landlock,yama,bpf"
).split()


def test_aarch64_stock_consoles_are_all_kept_in_order() -> None:
    assert install._select_console_kernel_params(CM4_STOCK_CMDLINE) == [
        "console=ttyS0,115200n8",
        "console=ttyAMA0,115200n8",
        "console=tty0",
    ]


def test_last_occurrence_decides_order_so_primary_is_kept() -> None:
    tokens = ("console=ttyAMA0,115200n8", "console=tty0", "console=ttyAMA0,115200n8")
    assert install._select_console_kernel_params(tokens) == [
        "console=tty0",
        "console=ttyAMA0,115200n8",
    ]


@pytest.mark.parametrize(
    "tokens,expected",
    [
        # Only a serial console booted: a VGA console is still provided, serial stays primary.
        (("console=ttyAMA0,115200n8",), ["console=tty0", "console=ttyAMA0,115200n8"]),
        # Only VGA booted: the default serial console is still provided, VGA stays primary.
        (("console=tty0",), ["console=ttyS0,115200n8", "console=tty0"]),
    ],
)
def test_both_kinds_are_always_present(tokens: tuple[str, ...], expected: list[str]) -> None:
    assert install._select_console_kernel_params(tokens) == expected
