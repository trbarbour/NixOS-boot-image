"""Check the Raspberry Pi EEPROM ``BOOT_ORDER`` before installing (R-B2).

AArch64 plan item 9; design and debate:
``plans/2026-10-20T031948Z-aarch64-item9-boot-order-check-design.md``.
The installer is an SD image, so the installed system boots with the card
still inserted only if the target's boot mode comes before SD.  pre-nixos only
reads the EEPROM configuration; it never writes it.
"""

from __future__ import annotations

import enum
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Sequence, Union

# Documented default when BOOT_ORDER is absent (E11: eeprom-bootloader.adoc).
DEFAULT_BOOT_ORDER = 0xF41
_MAX_DIGITS = 8

_SYSFS_DT_BASE = Path("/sys/firmware/devicetree/base")
_SYSFS_NVMEM = Path("/sys/bus/nvmem/devices")


class BootMode(enum.IntEnum):
    """``BOOT_ORDER`` digits (raspberrypi/documentation @ ddea98e)."""

    SD_CARD_DETECT = 0x0
    SD_CARD = 0x1  # also the CM4's eMMC
    NETWORK = 0x2
    RPIBOOT = 0x3
    USB_MSD = 0x4
    BCM_USB_MSD = 0x5
    NVME = 0x6
    HTTP = 0x7
    STOP = 0xE
    RESTART = 0xF


_SD_MODES = frozenset({BootMode.SD_CARD, BootMode.SD_CARD_DETECT})
_TERMINATORS = frozenset({BootMode.STOP, BootMode.RESTART})


@dataclass(frozen=True)
class Known:
    """An effective BOOT_ORDER value and where it came from."""

    value: int
    source: str

    def __post_init__(self) -> None:
        if not 0 <= self.value < 1 << (4 * _MAX_DIGITS):
            raise ValueError(f"BOOT_ORDER {self.value:#x} is not a 32-bit value")


@dataclass(frozen=True)
class Unknown:
    """The effective BOOT_ORDER could not be determined."""

    reason: str


BootOrderReading = Union[Known, Unknown]


@dataclass(frozen=True)
class Ok:
    order: tuple[int, ...]


@dataclass(frozen=True)
class Refused:
    reason: str
    suggestion: Optional[int]


Verdict = Union[Ok, Refused]


def digits(value: int) -> tuple[int, ...]:
    """Boot modes in the order tried: least significant nibble first, up to
    the first STOP/RESTART (later digits are never reached).  A zero high part
    ends the list, except that ``0`` alone is SD CARD DETECT."""

    result: list[int] = []
    remaining = value
    for _ in range(_MAX_DIGITS):
        nibble = remaining & 0xF
        result.append(nibble)
        remaining >>= 4
        if nibble in _TERMINATORS or remaining == 0:
            break
    return tuple(result)


def _encode(order: Sequence[int]) -> int:
    value = 0
    for position, nibble in enumerate(order):
        value |= (nibble & 0xF) << (4 * position)
    return value


_SECTION = re.compile(r"^\[(?P<name>[^\]]*)\]\s*$")
_ASSIGNMENT = re.compile(r"^BOOT_ORDER\s*=\s*(?P<value>\S+)\s*$")


def parse_config(text: str, source: str) -> BootOrderReading:
    """Return the effective BOOT_ORDER of EEPROM config ``text`` (design D2)."""

    section = "all"
    found: Optional[int] = None
    for raw in text.replace("\x00", "").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        heading = _SECTION.match(line)
        if heading:
            section = heading.group("name").strip().lower()
            continue
        assignment = _ASSIGNMENT.match(line)
        if assignment is None:
            continue
        if section != "all":
            return Unknown(f"BOOT_ORDER is set under the conditional section [{section}]")
        try:
            found = int(assignment.group("value"), 0)
        except ValueError:
            return Unknown(f"BOOT_ORDER value {assignment.group('value')!r} is not a number")
    if found is None:
        return Known(DEFAULT_BOOT_ORDER, f"{source} (no BOOT_ORDER: documented default)")
    try:
        return Known(found, source)
    except ValueError as exc:
        return Unknown(str(exc))


def read_current(
    dt_base: Path = _SYSFS_DT_BASE, nvmem_base: Path = _SYSFS_NVMEM
) -> BootOrderReading:
    """Read the running bootloader's configuration via ``blconfig`` (design D1;
    the same lookup as rpi-eeprom-config's read_current_config())."""

    alias = dt_base / "aliases" / "blconfig"
    try:
        node = alias.read_bytes().rstrip(b"\x00").decode("utf-8")
    except OSError:
        return Unknown(f"{alias} is missing (not a Raspberry Pi bootloader, or too old)")
    node_path = os.path.normpath(str(dt_base) + "/" + node.lstrip("/"))
    try:
        devices = sorted(nvmem_base.iterdir())
    except OSError as exc:
        return Unknown(f"cannot list {nvmem_base}: {exc}")
    for device in devices:
        if os.path.realpath(device / "of_node") != os.path.realpath(node_path):
            continue
        try:
            text = (device / "nvmem").read_bytes().decode("utf-8", errors="replace")
        except OSError as exc:
            return Unknown(f"cannot read {device / 'nvmem'}: {exc}")
        return parse_config(text, f"blconfig ({device.name})")
    return Unknown(f"no nvmem device for the blconfig node {node}")


def disk_of_device(device_number: int, sys_dev_block: Path = Path("/sys/dev/block")) -> Optional[str]:
    """Kernel name of the disk holding block device ``device_number`` (the
    ``st_dev`` of a mounted path): its own name, or its parent's for a partition."""

    entry = sys_dev_block / f"{os.major(device_number)}:{os.minor(device_number)}"
    try:
        resolved = Path(os.path.realpath(entry))
    except OSError:
        return None
    if not resolved.exists():
        return None
    if (resolved / "partition").exists():
        return resolved.parent.name
    return resolved.name


def target_mode(disk: Optional[str]) -> Union[BootMode, str]:
    """The boot mode that reaches ``disk``, or why it is not supported (D3)."""

    if disk is None:
        return "cannot tell which disk holds /boot"
    if disk.startswith("nvme"):
        return BootMode.NVME
    if disk.startswith("mmcblk"):
        return f"{disk}: eMMC shares boot mode 1 with the SD card, so it cannot boot first"
    return f"{disk}: only NVMe install targets are supported on the Raspberry Pi"


def suggest(order: Sequence[int], target: BootMode) -> int:
    """The target first, then the current order without other copies of it."""

    rest = [mode for mode in order if mode != target]
    if not rest or rest[-1] not in _TERMINATORS:
        rest.append(BootMode.RESTART)
    return _encode([target, *rest])


def check(reading: BootOrderReading, target: Union[BootMode, str]) -> Verdict:
    """Pure R-B2 rule: the target's mode is tried, and before SD."""

    if isinstance(target, str):
        return Refused(target, None)
    if isinstance(reading, Unknown):
        return Refused(
            f"cannot verify BOOT_ORDER: {reading.reason}", suggest(digits(DEFAULT_BOOT_ORDER), target)
        )
    order = digits(reading.value)
    if target not in order:
        return Refused(
            f"BOOT_ORDER {reading.value:#x} never tries {target.name}", suggest(order, target)
        )
    first_sd = min((order.index(mode) for mode in _SD_MODES if mode in order), default=None)
    if first_sd is not None and first_sd < order.index(target):
        return Refused(
            f"BOOT_ORDER {reading.value:#x} tries the SD card before {target.name}, "
            "so the installer would boot again instead of the installed system",
            suggest(order, target),
        )
    return Ok(order)


def describe_refusal(verdict: Refused) -> str:
    """One operator-facing line (console, TUI, status file)."""

    advice = (
        f" Set BOOT_ORDER={verdict.suggestion:#x} (rpi-eeprom-config --edit), then reboot."
        if verdict.suggestion is not None
        else ""
    )
    return f"Refusing to install: {verdict.reason}.{advice}"


def _disk_of_mount(path: Path) -> Optional[str]:
    return disk_of_device(os.stat(path).st_dev)


def verify_for_install(
    root_path: Path,
    *,
    read: Optional[Callable[[], BootOrderReading]] = None,
    disk_of: Optional[Callable[[Path], Optional[str]]] = None,
) -> Verdict:
    """R-B2 for an install onto ``root_path``: the disk mounted on
    ``ROOT/boot`` must be booted before the SD card (design D3/D4)."""

    try:
        disk = (disk_of or _disk_of_mount)(root_path / "boot")
    except OSError as exc:
        return Refused(f"cannot inspect {root_path / 'boot'}: {exc}", None)
    return check((read or read_current)(), target_mode(disk))
