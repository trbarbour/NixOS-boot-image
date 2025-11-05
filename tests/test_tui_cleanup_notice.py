"""Unit tests for cleanup notices in the TUI header."""

from pre_nixos import storage_cleanup, tui
from pre_nixos.storage_detection import ExistingStorageDevice


def _device(name: str) -> ExistingStorageDevice:
    return ExistingStorageDevice(device=name, reasons=("signatures",))


def test_format_cleanup_notice_without_devices() -> None:
    """No notice should be shown when no existing storage is detected."""

    assert tui._format_cleanup_notice([]) == []


def test_format_cleanup_notice_includes_summary_and_options() -> None:
    """Summaries list devices and expose available wipe options."""

    devices = [_device("/dev/sda"), _device("/dev/sdb")]
    lines = tui._format_cleanup_notice(devices)

    assert len(lines) == 2
    assert "2 device(s)" in lines[0]
    assert "/dev/sda" in lines[0]
    assert "/dev/sdb" in lines[0]
    assert "Options:" in lines[1]
    for option in storage_cleanup.CLEANUP_OPTIONS:
        assert option.key in lines[1]
        assert tui._short_cleanup_description(option.description) in lines[1]


def test_format_cleanup_notice_truncates_device_list() -> None:
    """Only a sample of devices is shown to keep the notice concise."""

    devices = [_device(f"/dev/sd{chr(ord('a') + idx)}") for idx in range(5)]
    lines = tui._format_cleanup_notice(devices)

    assert "5 device(s)" in lines[0]
    assert "…" in lines[0]
