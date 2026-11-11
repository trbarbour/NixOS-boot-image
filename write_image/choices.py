"""What the image writer offers, with defaults (task queue item 42).

One pure description of the choices, used by the CLI (flake attributes) and
the TUI (menus, defaults, summary), so they cannot disagree.

* Architecture: the machine the image boots.
* Image type: what the flake builds for that architecture (an ISO for a USB
  stick on x86_64; an SD-card image on AArch64).
* Console: the image's primary console (reqs R-C2), by default display on
  x86_64 and serial on AArch64; the other is a variant package.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Literal, Optional, Sequence, Tuple

Arch = Literal["x86_64", "aarch64"]
Console = Literal["default", "display", "serial"]


@dataclass(frozen=True)
class Option:
    value: str
    label: str
    detail: str
    default: bool = False


@dataclass(frozen=True)
class Selection:
    """Everything the user chose, as the CLI takes it."""

    arch: str
    fmt: str
    console: str
    site: Optional[str]
    image: Optional[str]
    device: str
    verify: bool


ARCHITECTURES: List[Option] = [
    Option("x86_64", "x86_64 PC", "Intel/AMD machines, BIOS or UEFI", default=True),
    Option("aarch64", "AArch64 Raspberry Pi 4 / CM4", "64-bit ARM boards booting from an SD card"),
]

_IMAGE_TYPES: Dict[str, List[Option]] = {
    "x86_64": [Option("iso", "ISO image", "boots from a USB stick (or a CD)", default=True)],
    "aarch64": [Option("sd", "SD-card image", "written to an SD card (or eMMC through a reader)", default=True)],
}

_DEFAULT_CONSOLE: Dict[str, str] = {"x86_64": "display", "aarch64": "serial"}
_CONSOLE_TEXT: Dict[str, Tuple[str, str]] = {
    "display": ("Display", "screen and keyboard; the serial port still gets a login"),
    "serial": ("Serial", "serial port (ttyS0, 115200 baud); the screen still gets a login"),
}

# (format, console) -> flake attribute; "default" means the format's default.
_ATTRIBUTES: Dict[Tuple[str, str], str] = {
    ("iso", "display"): "bootImage",
    ("iso", "serial"): "bootImageSerial",
    ("sd", "serial"): "bootImageSd",
    ("sd", "display"): "bootImageSdDisplay",
}
_FORMAT_ARCH: Dict[str, str] = {"iso": "x86_64", "sd": "aarch64"}


def image_types(arch: str) -> List[Option]:
    return _IMAGE_TYPES[arch]


def consoles(arch: str) -> List[Option]:
    """The two consoles, the architecture's default first."""

    default = _DEFAULT_CONSOLE[arch]
    order = [default] + [c for c in ("display", "serial") if c != default]
    return [Option(c, _CONSOLE_TEXT[c][0], _CONSOLE_TEXT[c][1], default=(c == default)) for c in order]


def default_index(options: Sequence[Option]) -> int:
    (index,) = [i for i, option in enumerate(options) if option.default]
    return index


def menu_label(option: Option) -> str:
    return f"{option.label}{' (default)' if option.default else ''}: {option.detail}"


def resolved_console(fmt: str, console: str) -> str:
    return _DEFAULT_CONSOLE[_FORMAT_ARCH[fmt]] if console == "default" else console


def attribute(fmt: str, console: str) -> str:
    """The flake attribute that builds ``fmt`` with ``console`` primary."""

    return _ATTRIBUTES[(fmt, resolved_console(fmt, console))]


def summary(selection: Selection, *, device_description: str) -> List[str]:
    arch = next(o for o in ARCHITECTURES if o.value == selection.arch)
    kind = next(o for o in image_types(selection.arch) if o.value == selection.fmt)
    console = resolved_console(selection.fmt, selection.console)
    source = f"build from site {selection.site}" if selection.site else f"image file {selection.image}"
    return [
        f"Architecture: {arch.label}",
        f"Image type:   {kind.label}",
        f"Console:      {_CONSOLE_TEXT[console][0].lower()} primary",
        f"Source:       {source}",
        f"Device:       {device_description}",
        f"Verify:       {'yes, read back and compare SHA-256' if selection.verify else 'no'}",
    ]


__all__ = [
    "ARCHITECTURES",
    "Arch",
    "Console",
    "Option",
    "Selection",
    "attribute",
    "consoles",
    "default_index",
    "image_types",
    "menu_label",
    "resolved_console",
    "summary",
]
