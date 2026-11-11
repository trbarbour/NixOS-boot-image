"""The late-disk plugger for the item 50 VM test (no VM needed)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.vm.late_disk import LateDiskPlugger

TRIGGER = "pre-nixos: waiting for the disks to settle"


def _plugger(tmp_path: Path, plugged: list, **kwargs) -> LateDiskPlugger:
    return LateDiskPlugger(
        serial_log=tmp_path / "serial.log",
        trigger=TRIGGER,
        plug=lambda: plugged.append("plugged"),
        delay=kwargs.pop("delay", 0.0),
        poll=0.01,
        **kwargs,
    )


def test_plugs_after_the_trigger_line(tmp_path: Path) -> None:
    log = tmp_path / "serial.log"
    log.write_text("booting\n")
    plugged: list = []
    plugger = _plugger(tmp_path, plugged, timeout=5)
    plugger.start()
    with log.open("a") as handle:
        handle.write(f"{TRIGGER}\n")
    plugger.join(5)
    assert plugged == ["plugged"]
    assert plugger.error is None and plugger.plugged_at is not None


def test_times_out_without_the_trigger(tmp_path: Path) -> None:
    (tmp_path / "serial.log").write_text("booting\n")
    plugged: list = []
    plugger = _plugger(tmp_path, plugged, timeout=0.1)
    plugger.start()
    plugger.join(5)
    assert plugged == []
    assert plugger.plugged_at is None
    assert isinstance(plugger.error, TimeoutError)


def test_a_failed_plug_is_recorded(tmp_path: Path) -> None:
    (tmp_path / "serial.log").write_text(f"{TRIGGER}\n")

    def broken() -> None:
        raise RuntimeError("QMP refused")

    plugger = LateDiskPlugger(
        serial_log=tmp_path / "serial.log", trigger=TRIGGER, plug=broken, delay=0, poll=0.01, timeout=5
    )
    plugger.start()
    plugger.join(5)
    assert isinstance(plugger.error, RuntimeError) and plugger.plugged_at is None


def test_check_reports_what_went_wrong(tmp_path: Path) -> None:
    (tmp_path / "serial.log").write_text("")
    plugger = _plugger(tmp_path, [], timeout=0.05)
    plugger.start()
    plugger.join(5)
    with pytest.raises(AssertionError, match="late disk was not plugged"):
        plugger.check()
