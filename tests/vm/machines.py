"""The emulated machine a VM test boots: emulator, platform arguments, timeouts.

x86_64 boots the ISO (CD-ROM or USB stick, ``tests/vm/boot_medium.py``).
AArch64 (AArch64 plan §4, item 7) boots the SD image's own system closure with
a direct kernel boot on ``qemu-system-aarch64 -M virt``: the Pi firmware chain
is not emulated (user decision U5).  Every test-only kernel parameter is
justified in notes/2026-10-19T031843Z-aarch64-e5-spike.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from tests.vm.boot_medium import UsbStick, boot_medium_args

# E5 run3: under TCG, udev coldplug outlasts systemd's 90 s default device
# timeout, so serial-getty@ttyAMA0 failed ("Timed out waiting for device").
AARCH64_TEST_KERNEL_PARAMS = ("systemd.default_device_timeout_sec=900",)
# E5 runs 4-7: boot to root login took 234-280 s under TCG.
AARCH64_LOGIN_TIMEOUT = 900


@dataclass(frozen=True)
class Machine:
    executable: str
    platform_args: Tuple[str, ...]
    login_timeout: int

    def __post_init__(self) -> None:
        assert self.login_timeout > 0, self.login_timeout


@dataclass(frozen=True)
class Aarch64System:
    """Boot files of a NixOS system closure (``config.system.build.toplevel``)."""

    toplevel: Path

    @property
    def kernel_params(self) -> str:
        return (self.toplevel / "kernel-params").read_text(encoding="utf-8").strip()

    def kernel_command_line(self) -> str:
        return " ".join(
            [self.kernel_params, f"init={self.toplevel}/init", *AARCH64_TEST_KERNEL_PARAMS]
        )


def x86_machine(
    executable: str, iso_path: Path, usb_stick: Optional[UsbStick], login_timeout: int
) -> Machine:
    return Machine(
        executable=executable,
        platform_args=tuple(boot_medium_args(iso_path, usb_stick)),
        login_timeout=login_timeout,
    )


def aarch64_machine(executable: str, system: Aarch64System, sd_card: Path) -> Machine:
    """``virt`` with the SD card as the first virtio disk (``/dev/vda``)."""

    return Machine(
        executable=executable,
        platform_args=(
            "-M", "virt",
            "-cpu", "cortex-a72",
            "-kernel", str(system.toplevel / "kernel"),
            "-initrd", str(system.toplevel / "initrd"),
            "-append", system.kernel_command_line(),
            "-drive", f"file={sd_card},if=virtio,format=raw",
        ),
        login_timeout=AARCH64_LOGIN_TIMEOUT,
    )


__all__ = [
    "AARCH64_LOGIN_TIMEOUT",
    "AARCH64_TEST_KERNEL_PARAMS",
    "Aarch64System",
    "Machine",
    "aarch64_machine",
    "x86_machine",
]
