"""Tests for pre_nixos.console."""

from __future__ import annotations

from pathlib import Path

import pytest

from pre_nixos.console import broadcast_line, get_console_paths


def test_get_console_paths_reads_active_file(tmp_path: Path) -> None:
    """#327: /dev/console is the primary console, already listed, so adding it
    wrote every broadcast twice on the primary (seen on the CM4's serial)."""

    active = tmp_path / "active"
    active.write_text("ttyS0 tty0\n")

    paths = get_console_paths(active_path=active)

    assert paths == [Path("/dev/ttyS0"), Path("/dev/tty0")]


@pytest.mark.parametrize("contents", [None, "", "\n"])
def test_get_console_paths_falls_back_to_dev_console(tmp_path: Path, contents: str | None) -> None:
    active = tmp_path / "active"
    if contents is not None:
        active.write_text(contents)

    assert get_console_paths(active_path=active) == [Path("/dev/console")]


def test_get_console_paths_deduplicates_and_adds_extra(tmp_path: Path) -> None:
    active = tmp_path / "active"
    active.write_text("/dev/ttyS0 ttyS0\n")
    extra = [tmp_path / "custom", Path("/dev/ttyS0"), Path("ttyS1")]

    paths = get_console_paths(active_path=active, extra_paths=extra)

    assert paths == [
        Path("/dev/ttyS0"),
        tmp_path / "custom",
        Path("/dev/ttyS1"),
    ]


def test_broadcast_line_writes_to_each_console(tmp_path: Path) -> None:
    console_a = tmp_path / "console_a"
    console_b = tmp_path / "console_b"
    # Ensure broadcast_line respects provided consoles even when the active file
    # is missing or empty.
    active = tmp_path / "active"
    active.write_text("")

    results = broadcast_line(
        "example message",
        active_path=active,
        console_paths=[console_a, console_b],
    )

    expected = b"example message\r\n"
    assert console_a.read_bytes() == expected
    assert console_b.read_bytes() == expected
    assert results == {console_a: True, console_b: True}


def test_broadcast_line_reports_failures(tmp_path: Path) -> None:
    console_dir = tmp_path / "console_dir"
    console_dir.mkdir()
    active = tmp_path / "active"
    active.write_text("")

    results = broadcast_line(
        "message",
        active_path=active,
        console_paths=[console_dir],
    )

    assert results == {console_dir: False}

