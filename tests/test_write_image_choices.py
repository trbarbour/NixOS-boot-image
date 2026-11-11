"""What the image writer offers, and its defaults (task queue item 42).

User request (2026-11-11): the TUI should present machine architecture,
console and image type well, with sensible defaults.  The choices live in one
pure module that both the CLI and the TUI use.  The console defaults follow
reqs R-C2: display on x86_64, serial on AArch64.
"""

from __future__ import annotations

import pytest

from write_image import choices, tui
from write_image.choices import Selection


def test_architectures_and_default() -> None:
    assert [a.value for a in choices.ARCHITECTURES] == ["x86_64", "aarch64"]
    assert choices.default_index(choices.ARCHITECTURES) == 0
    assert all(option.label and option.detail for option in choices.ARCHITECTURES)


@pytest.mark.parametrize("arch,fmt", [("x86_64", "iso"), ("aarch64", "sd")])
def test_image_types_follow_the_architecture(arch: str, fmt: str) -> None:
    types = choices.image_types(arch)
    assert [t.value for t in types] == [fmt]
    assert choices.default_index(types) == 0


@pytest.mark.parametrize("arch,default", [("x86_64", "display"), ("aarch64", "serial")])
def test_console_default_follows_r_c2(arch: str, default: str) -> None:
    consoles = choices.consoles(arch)
    assert {c.value for c in consoles} == {"display", "serial"}
    assert consoles[choices.default_index(consoles)].value == default
    assert "(default)" in choices.menu_label(consoles[choices.default_index(consoles)])


@pytest.mark.parametrize(
    "fmt,console,attribute",
    [
        ("iso", "default", "bootImage"),
        ("iso", "display", "bootImage"),
        ("iso", "serial", "bootImageSerial"),
        ("sd", "default", "bootImageSd"),
        ("sd", "serial", "bootImageSd"),
        ("sd", "display", "bootImageSdDisplay"),
    ],
)
def test_flake_attribute_for_format_and_console(fmt: str, console: str, attribute: str) -> None:
    assert choices.attribute(fmt, console) == attribute


def test_summary_lists_every_choice() -> None:
    selection = Selection(arch="aarch64", fmt="sd", console="display", site="/home/me/site",
                          image=None, device="mmcblk0", verify=True)
    lines = "\n".join(choices.summary(selection, device_description="/dev/mmcblk0: SC64G, 63.9 GB, mmc"))
    for text in ("AArch64", "SD", "display", "/home/me/site", "/dev/mmcblk0", "verify"):
        assert text.lower() in lines.lower(), text


def test_tui_passes_the_console_to_the_cli() -> None:
    selection = Selection(arch="x86_64", fmt="iso", console="serial", site="./site",
                          image=None, device="sdb", verify=False)
    assert tui.cli_argv(selection) == ["--format", "iso", "--console", "serial", "--site", "./site", "--device", "sdb"]
