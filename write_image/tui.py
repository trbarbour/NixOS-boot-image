"""``write-image-tui``: choose with menus, then run the CLI (R-W6).

The menus present the machine architecture, the image type and the primary
console, each with its default preselected and marked, and a one-line
explanation (user request, 2026-11-11; the options and defaults come from
:mod:`write_image.choices`).  Then the image source, the device (from the
CLI's own listing) and verification, and a summary to confirm.

After the summary, curses ends and :func:`write_image.cli.main` runs with the
chosen arguments and without ``--yes``: the typed confirmation, the build
log, sudo's password prompt and the progress all appear in the terminal.
"""

from __future__ import annotations

import curses
import os
import sys
from typing import List, Optional, Sequence

from write_image import choices, cli, devices
from write_image.choices import Option, Selection


def cli_argv(selection: Selection) -> List[str]:
    """The CLI arguments for ``selection`` (no ``--yes``: the CLI confirms)."""

    argv = ["--format", selection.fmt, "--console", selection.console]
    if selection.site is not None:
        argv += ["--site", selection.site]
    elif selection.image is not None:
        argv += ["--image", selection.image]
    argv += ["--device", selection.device]
    if selection.verify:
        argv.append("--verify")
    return argv


def _draw(screen: "curses.window", row: int, text: str, attr: int = curses.A_NORMAL) -> None:
    height, width = screen.getmaxyx()
    if 0 <= row < height:
        screen.addstr(row, 0, text[: max(0, width - 1)], attr)


def _menu(
    screen: "curses.window", step: str, title: str, items: Sequence[str], start: int,
    body: Sequence[str] = (),
) -> Optional[int]:
    """A vertical menu starting on ``start``, under optional ``body`` lines;
    the chosen index, or None (q/Esc)."""

    index = start
    while True:
        screen.erase()
        _draw(screen, 0, f"pre-nixos write-image  {step}", curses.A_DIM)
        _draw(screen, 2, title, curses.A_BOLD)
        for row, line in enumerate(body):
            _draw(screen, 4 + row, f"  {line}")
        top = 4 + len(body) + (1 if body else 0)
        for row, item in enumerate(items):
            marker = ">" if row == index else " "
            _draw(screen, top + row, f" {marker} {item}", curses.A_REVERSE if row == index else curses.A_NORMAL)
        _draw(screen, top + 1 + len(items), "Up/Down to move, Enter to choose, q to quit", curses.A_DIM)
        key = screen.getch()
        if key in (curses.KEY_UP, ord("k")):
            index = (index - 1) % len(items)
        elif key in (curses.KEY_DOWN, ord("j")):
            index = (index + 1) % len(items)
        elif key in (curses.KEY_ENTER, 10, 13):
            return index
        elif key in (ord("q"), 27):
            return None


def _options(screen: "curses.window", step: str, title: str, options: Sequence[Option]) -> Optional[Option]:
    chosen = _menu(screen, step, title, [choices.menu_label(o) for o in options], choices.default_index(options))
    return None if chosen is None else options[chosen]


def _text(screen: "curses.window", step: str, label: str, default: str) -> str:
    screen.erase()
    _draw(screen, 0, f"pre-nixos write-image  {step}", curses.A_DIM)
    _draw(screen, 2, f"{label}  (Enter keeps [{default}])", curses.A_BOLD)
    curses.echo()
    curses.curs_set(1)
    try:
        raw = screen.getstr(4, 2, 400).decode(errors="replace").strip()
    finally:
        curses.noecho()
        curses.curs_set(0)
    return raw or default


def _ask(screen: "curses.window") -> Optional[Selection]:
    curses.curs_set(0)
    arch = _options(screen, "1/7", "Machine architecture", choices.ARCHITECTURES)
    if arch is None:
        return None
    kind = _options(screen, "2/7", "Image type", choices.image_types(arch.value))
    if kind is None:
        return None
    console = _options(screen, "3/7", "Primary console", choices.consoles(arch.value))
    if console is None:
        return None
    source = _menu(screen, "4/7", "Image source",
                   ["Build from a site directory (default)", "Write an image file already built"], 0)
    if source is None:
        return None
    default_site = "./site" if os.path.isdir("site") else ""
    site = _text(screen, "4/7", "Site directory", default_site) if source == 0 else None
    image_path = _text(screen, "4/7", "Image file", "") if source == 1 else None
    candidates, _ = cli.listing(devices.live_view(), kind.value)  # type: ignore[arg-type]
    if not candidates:
        return None
    device = _menu(screen, "5/7", "Device (removable only; the first fits the image type best)",
                   [c.describe() for c in candidates], 0)
    if device is None:
        return None
    verify = _menu(screen, "6/7", "Verify after writing?",
                   ["Yes (default): read back and compare SHA-256", "No"], 0)
    if verify is None:
        return None
    selection = Selection(arch=arch.value, fmt=kind.value, console=console.value, site=site,
                          image=image_path, device=candidates[device].name, verify=verify == 0)
    lines = choices.summary(selection, device_description=candidates[device].describe())
    confirm = _menu(screen, "7/7", "Summary", ["Continue: build (if asked) and write", "Cancel"], 0, body=lines)
    return selection if confirm == 0 else None


def main() -> int:
    selection = curses.wrapper(_ask)
    if selection is None:
        print("nothing written (cancelled, or no eligible device: see write-image --list)")
        return cli.EXIT_REFUSED
    return cli.main(cli_argv(selection))


if __name__ == "__main__":
    sys.exit(main())
