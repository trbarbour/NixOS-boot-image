"""What the image writer offers, with defaults (task queue item 42).

One pure description of the choices, used by the CLI (flake attributes) and
the TUI (menus, defaults, summary), so they cannot disagree.

* Architecture: the machine the image boots.
* Image type: what the flake builds for that architecture (an ISO for a USB
  stick on x86_64; an SD-card image on AArch64).
* Console: the image's primary console (reqs R-C2).  "default" builds the
  plain package, which follows the site's ``primaryConsole`` and else the
  format's default (display on x86_64, serial on AArch64).  An explicit display
  or serial builds a forced variant, overriding the site (Codex on #350).
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

# (format, console) -> flake attribute, as a full path: a short name resolves
# under the host's own packages.<system> (Codex on #350).  "default" is the
# plain package, which follows the site; the others force the console.
_ATTRIBUTES: Dict[Tuple[str, str], str] = {
    ("iso", "default"): "packages.x86_64-linux.bootImage",
    ("iso", "display"): "packages.x86_64-linux.bootImageDisplay",
    ("iso", "serial"): "packages.x86_64-linux.bootImageSerial",
    ("sd", "default"): "packages.aarch64-linux.bootImageSd",
    ("sd", "serial"): "packages.aarch64-linux.bootImageSdSerial",
    ("sd", "display"): "packages.aarch64-linux.bootImageSdDisplay",
}
_FORMAT_ARCH: Dict[str, str] = {"iso": "x86_64", "sd": "aarch64"}


def image_types(arch: str) -> List[Option]:
    return _IMAGE_TYPES[arch]


def consoles(arch: str) -> List[Option]:
    """"As the site says" (the default), then explicit display and serial."""

    fallback = _DEFAULT_CONSOLE[arch]
    return [
        Option("default", "As the site says",
               f"the site's primaryConsole if set, else {fallback} for this image", default=True),
        *(Option(c, _CONSOLE_TEXT[c][0], _CONSOLE_TEXT[c][1] + "; overrides the site") for c in ("display", "serial")),
    ]


def default_index(options: Sequence[Option]) -> int:
    (index,) = [i for i, option in enumerate(options) if option.default]
    return index


def menu_label(option: Option) -> str:
    return f"{option.label}{' (default)' if option.default else ''}: {option.detail}"


def attribute(fmt: str, console: str) -> str:
    """The flake attribute that builds ``fmt`` with ``console`` primary."""

    return _ATTRIBUTES[(fmt, console)]


def console_text(fmt: str, console: str) -> str:
    if console == "default":
        return f"as the site says ({_DEFAULT_CONSOLE[_FORMAT_ARCH[fmt]]} unless it sets primaryConsole)"
    return f"{console} primary (overrides the site)"


def summary(selection: Selection, *, device_description: str) -> List[str]:
    arch = next(o for o in ARCHITECTURES if o.value == selection.arch)
    kind = next(o for o in image_types(selection.arch) if o.value == selection.fmt)
    source = f"build from site {selection.site}" if selection.site else f"image file {selection.image}"
    return [
        f"Architecture: {arch.label}",
        f"Image type:   {kind.label}",
        f"Console:      {console_text(selection.fmt, selection.console)}",
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
    "console_text",
    "summary",
]
