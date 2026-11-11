"""``write-image-tui``: choose with a full-screen menu, then run the CLI (R-W6).

The device list comes from the CLI's own listing, and the work is the CLI's:
after the menu, curses ends and :func:`write_image.cli.main` runs with the
chosen arguments and without ``--yes``, so the typed confirmation, the build
log, sudo's password prompt and the progress all appear in the terminal.
"""

from __future__ import annotations

import curses
import sys
from dataclasses import dataclass
from typing import List, Optional

from write_image import cli, devices
from write_image.devices import Candidate, Format


@dataclass(frozen=True)
class Choices:
    fmt: Format
    site: Optional[str]
    image: Optional[str]
    device: str
    verify: bool


def cli_argv(choices: Choices) -> List[str]:
    """The CLI arguments for ``choices`` (no ``--yes``: the CLI confirms)."""

    argv = ["--format", choices.fmt]
    if choices.site is not None:
        argv += ["--site", choices.site]
    elif choices.image is not None:
        argv += ["--image", choices.image]
    argv += ["--device", choices.device]
    if choices.verify:
        argv.append("--verify")
    return argv


def _menu(screen: "curses.window", title: str, items: List[str]) -> Optional[int]:
    """A vertical menu; returns the chosen index, or None on q/Esc."""

    index = 0
    while True:
        screen.erase()
        screen.addstr(0, 0, title[: curses.COLS - 1], curses.A_BOLD)
        for row, item in enumerate(items):
            attr = curses.A_REVERSE if row == index else curses.A_NORMAL
            screen.addstr(2 + row, 2, item[: curses.COLS - 3], attr)
        screen.addstr(3 + len(items), 0, "Up/Down, Enter to choose, q to quit"[: curses.COLS - 1])
        key = screen.getch()
        if key in (curses.KEY_UP, ord("k")):
            index = (index - 1) % len(items)
        elif key in (curses.KEY_DOWN, ord("j")):
            index = (index + 1) % len(items)
        elif key in (curses.KEY_ENTER, 10, 13):
            return index
        elif key in (ord("q"), 27):
            return None


def _text(screen: "curses.window", label: str, default: str) -> str:
    screen.erase()
    screen.addstr(0, 0, f"{label} [{default}]: "[: curses.COLS - 1])
    curses.echo()
    try:
        raw = screen.getstr(1, 0, 400).decode(errors="replace").strip()
    finally:
        curses.noecho()
    return raw or default


def _ask(screen: "curses.window") -> Optional[Choices]:
    fmt_index = _menu(screen, "Image format", ["ISO (x86_64, USB stick)", "SD image (AArch64, SD card)"])
    if fmt_index is None:
        return None
    fmt: Format = "iso" if fmt_index == 0 else "sd"
    source = _menu(screen, "Image source", ["Build from a site directory", "An image already built"])
    if source is None:
        return None
    site = _text(screen, "Site directory", "./site") if source == 0 else None
    img = _text(screen, "Image file", "") if source == 1 else None
    candidates: List[Candidate]
    candidates, _ = cli.listing(devices.live_view(), fmt)
    if not candidates:
        return None
    device_index = _menu(screen, "Device (removable only)", [c.describe() for c in candidates])
    if device_index is None:
        return None
    verify = _menu(screen, "Verify after writing?", ["Yes", "No"]) == 0
    return Choices(fmt=fmt, site=site, image=img, device=candidates[device_index].name, verify=verify)


def main() -> int:
    choices = curses.wrapper(_ask)
    if choices is None:
        print("nothing chosen (or no eligible device: see write-image --list)")
        return cli.EXIT_REFUSED
    return cli.main(cli_argv(choices))


if __name__ == "__main__":
    sys.exit(main())
