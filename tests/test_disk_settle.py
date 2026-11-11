"""The boot-time wait for a stable disk set (task queue item 50, R-D1, R-D2).

Design: plans/2026-11-11T194943Z-disk-settle-design.md (D1, D3, D4).
"""

from __future__ import annotations

from typing import List, Sequence

import pytest

from pre_nixos import disk_settle
from pre_nixos.inventory import Disk

GIB = 1024**3
SDA = Disk(name="sda", size=128 * GIB, serial="A")
SDB = Disk(name="sdb", size=750 * GIB, serial="B")


class FakeClock:
    """A clock that only moves when the code under test sleeps."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        assert seconds > 0
        self.now += seconds


def scripted(clock: FakeClock, timeline: Sequence[tuple[float, List[Disk]]]):
    """The disks present at each time: the last entry at or before ``now``."""

    def read() -> List[Disk]:
        current: List[Disk] = []
        for start, disks in timeline:
            if clock.now >= start:
                current = disks
        return current

    return read


def _wait(timeline, *, quiet=15.0, limit=120.0):
    clock = FakeClock()
    result = disk_settle.wait_for_stable(
        scripted(clock, timeline), quiet=quiet, limit=limit, clock=clock, sleep=clock.sleep
    )
    return result, clock


def test_settles_after_the_quiet_period() -> None:
    result, clock = _wait([(0, [SDA])])
    assert result.settled
    assert clock.now == 15
    assert {d.name for d in result.identities} == {"sda"}


def test_a_late_disk_restarts_the_quiet_period() -> None:
    """The user's PC: the HBA disk appears well after the service starts."""

    result, clock = _wait([(0, [SDA]), (10, [SDA, SDB])])
    assert result.settled
    assert clock.now == 25  # 10 s to the change, then 15 s quiet
    assert {d.name for d in result.identities} == {"sda", "sdb"}
    assert result.changes == ["added sdb (750 GiB, serial B)"]


def test_unsettled_at_the_bound() -> None:
    flapping = [(t, [SDA, SDB] if t % 10 else [SDA]) for t in range(0, 200, 5)]
    result, clock = _wait(flapping)
    assert not result.settled
    assert clock.now == 120


def test_quiet_zero_returns_at_once() -> None:
    result, clock = _wait([(0, [SDA])], quiet=0)
    assert result.settled and clock.now == 0


def test_a_bound_shorter_than_the_quiet_period_is_unsettled() -> None:
    """D3: the bound wins; a set unchanged for the whole of it is still not
    unchanged for the quiet period."""

    result, clock = _wait([(0, [SDA])], quiet=15, limit=5)
    assert not result.settled and clock.now == 5


def test_no_disks_is_a_set_like_any_other() -> None:
    result, _ = _wait([(0, [])])
    assert result.settled and result.identities == frozenset()


@pytest.mark.parametrize("quiet,limit", [(-1, 120), (15, -1)])
def test_negative_times_are_a_programming_error(quiet, limit) -> None:
    with pytest.raises(AssertionError):
        _wait([(0, [SDA])], quiet=quiet, limit=limit)


# --- kernel command line (R-D1) ---------------------------------------------


def test_defaults() -> None:
    settings, warnings = disk_settle.settings_from_cmdline(["quiet", "console=ttyS0"])
    assert settings == disk_settle.Settings(quiet=15, limit=120)
    assert warnings == []


def test_parameters_override_the_defaults() -> None:
    settings, warnings = disk_settle.settings_from_cmdline(
        ["pre-nixos-disk-quiet=5", "pre-nixos-disk-wait-max=300"]
    )
    assert settings == disk_settle.Settings(quiet=5, limit=300)
    assert warnings == []


@pytest.mark.parametrize("value", ["", "abc", "-3", "1.5"])
def test_a_bad_value_falls_back_to_the_default_with_a_warning(value) -> None:
    """D3: a typo must not stop the boot."""

    settings, warnings = disk_settle.settings_from_cmdline([f"pre-nixos-disk-quiet={value}"])
    assert settings.quiet == 15
    assert len(warnings) == 1 and "pre-nixos-disk-quiet" in warnings[0]


# --- the command (D4) ---------------------------------------------------------


def _main(monkeypatch, timeline, cmdline=()):
    clock = FakeClock()
    monkeypatch.setattr(disk_settle, "_read_cmdline", lambda: list(cmdline))
    monkeypatch.setattr(disk_settle.inventory, "enumerate_disks", scripted(clock, timeline))
    monkeypatch.setattr(disk_settle.time, "monotonic", clock)
    monkeypatch.setattr(disk_settle.time, "sleep", clock.sleep)
    return disk_settle.main([])


def test_command_exit_0_when_settled(monkeypatch, capsys) -> None:
    assert _main(monkeypatch, [(0, [SDA]), (5, [SDA, SDB])]) == disk_settle.EXIT_SETTLED == 0
    out = capsys.readouterr().out
    assert "waiting for the disks to settle (quiet 15 s, at most 120 s)" in out
    assert "added sdb" in out
    assert "disks settled after 20 s: sda, sdb" in out


def test_command_exit_2_when_unsettled(monkeypatch, capsys) -> None:
    flapping = [(t, [SDA, SDB] if t % 2 else [SDA]) for t in range(0, 30)]
    code = _main(monkeypatch, flapping, ["pre-nixos-disk-wait-max=10"])
    assert code == disk_settle.EXIT_UNSETTLED == 2
    assert "still changing after 10 s" in capsys.readouterr().err


def test_command_exit_1_on_error(monkeypatch, capsys) -> None:
    def broken():
        raise OSError("sysfs unreadable")

    monkeypatch.setattr(disk_settle, "_read_cmdline", lambda: [])
    monkeypatch.setattr(disk_settle.inventory, "enumerate_disks", broken)
    assert disk_settle.main([]) == disk_settle.EXIT_ERROR == 1
    assert "sysfs unreadable" in capsys.readouterr().err


def test_the_consoles_are_told_when_the_wait_starts(monkeypatch) -> None:
    """The notice comes from the wait itself, just before its first
    inventory: Python started slowly (34 s in the test VM, which runs without KVM),
    so a notice from the service script came well before the wait began
    (VM run notes/2026-11-11T200421Z-vm-run)."""

    events: list = []
    monkeypatch.setattr(
        disk_settle.console, "broadcast_to_consoles", lambda message: events.append(("console", message))
    )
    clock = FakeClock()
    read = scripted(clock, [(0, [SDA])])

    def recording_read():
        events.append(("read",))
        return read()

    monkeypatch.setattr(disk_settle, "_read_cmdline", lambda: [])
    monkeypatch.setattr(disk_settle.inventory, "enumerate_disks", recording_read)
    monkeypatch.setattr(disk_settle.time, "monotonic", clock)
    monkeypatch.setattr(disk_settle.time, "sleep", clock.sleep)
    assert disk_settle.main([]) == disk_settle.EXIT_SETTLED
    assert events[0] == ("console", f"{disk_settle.CONSOLE_NOTICE} (quiet 15 s, at most 120 s)")
    assert events[1] == ("read",)
