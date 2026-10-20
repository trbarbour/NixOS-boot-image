"""EEPROM BOOT_ORDER verification (AArch64 plan item 9; requirement R-B2).

Design: plans/2026-10-20T031948Z-aarch64-item9-boot-order-check-design.md.
Digit meanings: raspberrypi/documentation eeprom-bootloader.adoc @ ddea98e (E11).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from pre_nixos import boot_order
from pre_nixos.boot_order import BootMode, Known, Ok, Refused, Unknown

# `rpi-eeprom-config` on the user's CM4, 2026-10-18 (plans/2026-10-18T220351Z-aarch64-user-answers.txt).
USER_CM4_CONFIG = """[all]
BOOT_UART=1
WAKE_ON_GPIO=1
POWER_OFF_ON_HALT=0

# Boot Order Codes, from https://www.raspberrypi.com/documentation/computers/raspberry-pi.html#BOOT_ORDER
## Try SD first (1), followed by, USB PCIe, NVMe PCIe, USB SoC XHCI then network
#BOOT_ORDER=0xf25641
# Try NVMe PCIe first (6), followed by, SD, BCM-USB-MSD (SoC XHCI) then network
BOOT_ORDER=0xf2516

# Set to 0 to prevent bootloader updates from USB/Network boot
# For remote units EEPROM hardware write protection should be used.
ENABLE_SELF_UPDATE=1
"""


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0xF2516, (6, 1, 5, 2, 0xF)),
        (0xF41, (1, 4, 0xF)),
        (0xF16F6, (6, 0xF)),  # nothing after RESTART is reached
        (0x0, (0,)),  # SD CARD DETECT alone
        (0x61, (1, 6)),  # no terminator: ends with the value
    ],
)
def test_digits_are_tried_least_significant_first(value: int, expected: tuple[int, ...]) -> None:
    assert boot_order.digits(value) == expected


def test_the_users_cm4_config_is_read() -> None:
    assert boot_order.parse_config(USER_CM4_CONFIG, "cm4") == Known(0xF2516, "cm4")


def test_absent_boot_order_is_the_documented_default() -> None:
    reading = boot_order.parse_config("[all]\nBOOT_UART=1\n", "x")
    assert isinstance(reading, Known) and reading.value == 0xF41


def test_last_unconditional_assignment_wins() -> None:
    text = "BOOT_ORDER=0xf41\n[all]\nBOOT_ORDER=0xf16\n"
    assert boot_order.parse_config(text, "x") == Known(0xF16, "x")


@pytest.mark.parametrize(
    "text",
    [
        "[cm4]\nBOOT_ORDER=0xf16\n",
        "[all]\nBOOT_ORDER=0xf16\n[gpio8=0]\nBOOT_ORDER=0xf41\n",
        "BOOT_ORDER=nvme\n",
        "BOOT_ORDER=0x1ffffffff\n",
    ],
)
def test_unverifiable_configs_are_unknown(text: str) -> None:
    assert isinstance(boot_order.parse_config(text, "x"), Unknown)


@pytest.mark.parametrize("value", [0xF2516, 0xF25146, 0xF16, 0xF16F6, 0x6])
def test_nvme_before_sd_is_accepted(value: int) -> None:
    assert isinstance(boot_order.check(Known(value, "x"), BootMode.NVME), Ok)


@pytest.mark.parametrize(
    ("value", "suggestion"),
    [
        (0xF41, 0xF416),  # the default: SD first, no NVMe
        (0xF461, 0xF416),  # NVMe after SD
        (0xF1, 0xF16),  # no NVMe
        (0xF60, 0xF06),  # SD CARD DETECT (0) before NVMe
        (0x41, 0xF416),  # no terminator: RESTART appended
    ],
)
def test_sd_first_or_no_nvme_is_refused_with_a_suggestion(value: int, suggestion: int) -> None:
    verdict = boot_order.check(Known(value, "x"), BootMode.NVME)
    assert isinstance(verdict, Refused), verdict
    assert verdict.suggestion == suggestion
    assert isinstance(boot_order.check(Known(suggestion, "x"), BootMode.NVME), Ok)


def test_unknown_reading_is_refused() -> None:
    verdict = boot_order.check(Unknown("no blconfig"), BootMode.NVME)
    assert isinstance(verdict, Refused) and "no blconfig" in verdict.reason
    assert verdict.suggestion == 0xF416


@pytest.mark.parametrize(
    ("disk", "supported"),
    [("nvme0n1", True), ("mmcblk0", False), ("sda", False), (None, False)],
)
def test_only_nvme_targets_are_supported(disk: str | None, supported: bool) -> None:
    target = boot_order.target_mode(disk)
    assert (target is BootMode.NVME) == supported
    if not supported:
        assert isinstance(boot_order.check(Known(0xF2516, "x"), target), Refused)


def test_refusal_message_names_the_value_to_set() -> None:
    message = boot_order.describe_refusal(Refused("BOOT_ORDER 0xf41 never tries NVME", 0xF416))
    assert message.startswith("Refusing to install: BOOT_ORDER 0xf41 never tries NVME.")
    assert "Set BOOT_ORDER=0xf416" in message


def _fake_sysfs(tmp_path: Path, config: str) -> tuple[Path, Path]:
    dt = tmp_path / "dt"
    node = dt / "reserved-memory" / "nvram@0"
    node.mkdir(parents=True)
    (dt / "aliases").mkdir()
    # The firmware's alias is a NUL-terminated device-tree path.
    (dt / "aliases" / "blconfig").write_bytes(b"/reserved-memory/nvram@0\x00")
    nvmem = tmp_path / "nvmem"
    other = nvmem / "rmem0"
    other.mkdir(parents=True)
    (other / "of_node").symlink_to(tmp_path)
    device = nvmem / "rmem1"
    device.mkdir()
    (device / "of_node").symlink_to(node)
    (device / "nvmem").write_bytes(config.encode() + b"\x00" * 16)
    return dt, nvmem


def test_reader_follows_the_blconfig_alias_to_its_nvmem_device(tmp_path: Path) -> None:
    dt, nvmem = _fake_sysfs(tmp_path, USER_CM4_CONFIG)
    assert boot_order.read_current(dt, nvmem) == Known(0xF2516, "blconfig (rmem1)")


def test_reader_without_blconfig_is_unknown(tmp_path: Path) -> None:
    """qemu virt and non-Pi boards: fail safe."""

    reading = boot_order.read_current(tmp_path / "dt", tmp_path / "nvmem")
    assert isinstance(reading, Unknown) and "blconfig" in reading.reason


def test_reader_without_a_matching_device_is_unknown(tmp_path: Path) -> None:
    dt, nvmem = _fake_sysfs(tmp_path, USER_CM4_CONFIG)
    (nvmem / "rmem1" / "of_node").unlink()
    assert isinstance(boot_order.read_current(dt, nvmem), Unknown)


def test_disk_of_a_partition_is_its_parent(tmp_path: Path) -> None:
    block = tmp_path / "devices" / "nvme0n1"
    (block / "nvme0n1p1").mkdir(parents=True)
    (block / "nvme0n1p1" / "partition").write_text("1\n")
    links = tmp_path / "dev-block"
    links.mkdir()
    (links / "259:1").symlink_to(block / "nvme0n1p1")
    (links / "259:0").symlink_to(block)

    assert boot_order.disk_of_device(os.makedev(259, 1), links) == "nvme0n1"
    assert boot_order.disk_of_device(os.makedev(259, 0), links) == "nvme0n1"
    assert boot_order.disk_of_device(os.makedev(8, 0), links) is None


def test_verify_for_install_uses_the_disk_behind_root_boot(tmp_path: Path) -> None:
    seen: list[Path] = []

    def disk_of(path: Path) -> str:
        seen.append(path)
        return "nvme0n1"

    verdict = boot_order.verify_for_install(
        tmp_path, read=lambda: Known(0xF2516, "x"), disk_of=disk_of
    )
    assert isinstance(verdict, Ok) and seen == [tmp_path / "boot"]


def test_verify_for_install_refuses_when_boot_cannot_be_inspected(tmp_path: Path) -> None:
    def missing(path: Path) -> str:
        raise FileNotFoundError(path)

    verdict = boot_order.verify_for_install(tmp_path, read=lambda: Known(0xF2516, "x"), disk_of=missing)
    assert isinstance(verdict, Refused) and "cannot inspect" in verdict.reason
