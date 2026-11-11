"""Degraded md arrays are reported on the installed system (task queue item 49; reqs R-S7).

User report (#344, 2026-11-10): the installed system ran its mirror degraded
and nothing said so.  mdadm's monitor mailed ``root`` (``MAILADDR root``), but
there is no sendmail.  User decision (2026-11-11): options 1 and 2:

1. at every login, a notice for each degraded or inactive array, read from
   ``/proc/mdstat`` (``templates/pre-nixos-md-status.sh``);
2. an mdadm ``PROGRAM`` hook (``templates/pre-nixos-md-event.sh``): failure events go to
   the journal at ``crit`` and to logged-in terminals (``wall``).

The scripts run here with fake ``/proc/mdstat`` files and fake ``logger`` and
``wall`` commands.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

TEMPLATES = Path(__file__).resolve().parents[1] / "pre_nixos" / "templates"
STATUS = TEMPLATES / "pre-nixos-md-status.sh"
EVENT = TEMPLATES / "pre-nixos-md-event.sh"

HEALTHY = """Personalities : [raid1]
md0 : active raid1 sdc1[1] sda1[0]
      732440576 blocks super 1.2 [2/2] [UU]

unused devices: <none>
"""
# The user's PC on 2026-11-10 (#344).
DEGRADED = """Personalities : [raid1]
md0 : active raid1 sda1[0]
      732440576 blocks super 1.2 [2/1] [U_]

unused devices: <none>
"""
RECOVERING = """Personalities : [raid1]
md0 : active raid1 sdc1[2] sda1[0]
      732440576 blocks super 1.2 [2/1] [U_]
      [=>...................]  recovery =  7.5% (55000000/732440576) finish=80.1min speed=140000K/sec

unused devices: <none>
"""
INACTIVE = """Personalities : [raid1]
md127 : inactive sdb1[0](S)
      5235712 blocks super 1.2

unused devices: <none>
"""
RAID0_AND_MIRROR = """Personalities : [raid0] [raid1]
md1 : active raid0 nvme1n1p1[1] nvme0n1p1[0]
      1953260544 blocks super 1.2 512k chunks

md0 : active raid1 sdc1[1](F) sda1[0]
      732440576 blocks super 1.2 [2/1] [U_]

unused devices: <none>
"""


def _status(tmp_path: Path, mdstat: str | None) -> subprocess.CompletedProcess[str]:
    path = tmp_path / "mdstat"
    if mdstat is not None:
        path.write_text(mdstat)
    return subprocess.run(
        ["bash", str(STATUS)],
        env={**os.environ, "PRE_NIXOS_MDSTAT": str(path)},
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_healthy_or_absent_is_silent(tmp_path: Path) -> None:
    for index, mdstat in enumerate((HEALTHY, None, "Personalities :\nunused devices: <none>\n")):
        case = tmp_path / str(index)
        case.mkdir()
        result = _status(case, mdstat)
        assert (result.returncode, result.stdout, result.stderr) == (0, "", ""), mdstat


def test_degraded_array_is_reported(tmp_path: Path) -> None:
    result = _status(tmp_path, DEGRADED)
    assert result.returncode == 0
    assert "md0" in result.stdout and "degraded" in result.stdout
    assert "1 of 2" in result.stdout
    assert "mdadm --detail /dev/md0" in result.stdout


def test_recovering_array_says_so(tmp_path: Path) -> None:
    result = _status(tmp_path, RECOVERING)
    assert "md0" in result.stdout and "degraded" in result.stdout
    assert "recovery" in result.stdout and "7.5%" in result.stdout


def test_inactive_array_is_reported(tmp_path: Path) -> None:
    result = _status(tmp_path, INACTIVE)
    assert result.returncode == 0
    assert "md127" in result.stdout and "inactive" in result.stdout


def test_only_the_degraded_array_is_named(tmp_path: Path) -> None:
    result = _status(tmp_path, RAID0_AND_MIRROR)
    assert "md0" in result.stdout and "md1" not in result.stdout


# --- the PROGRAM hook ------------------------------------------------------


@pytest.fixture
def fake_bin(tmp_path: Path) -> Path:
    """``logger`` and ``wall`` that record their arguments and stdin."""

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name in ("logger", "wall"):
        tool = bin_dir / name
        tool.write_text(
            "#!/bin/sh\n"
            f'printf "%s\\n" "{name} $*" >> "$CALLS"\n'
            f'if [ "{name}" = wall ] && [ $# -eq 0 ]; then printf "wall-stdin %s\\n" "$(cat)" >> "$CALLS"; fi\n'
        )
        tool.chmod(tool.stat().st_mode | stat.S_IXUSR)
    return bin_dir


def _event(fake_bin: Path, tmp_path: Path, *args: str) -> list[str]:
    calls = tmp_path / "calls"
    calls.write_text("")
    result = subprocess.run(
        ["bash", str(EVENT), *args],
        env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}", "CALLS": str(calls)},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return calls.read_text().splitlines()


@pytest.mark.parametrize("event", ["Fail", "FailSpare", "DegradedArray", "DeviceDisappeared", "SparesMissing"])
def test_failure_events_are_critical_and_broadcast(fake_bin: Path, tmp_path: Path, event: str) -> None:
    calls = _event(fake_bin, tmp_path, event, "/dev/md0", "/dev/sdc1")
    loggers = [c for c in calls if c.startswith("logger ")]
    walls = [c for c in calls if c.startswith("wall")]
    assert len(loggers) == 1 and "-p daemon.crit" in loggers[0] and "-t mdadm-alert" in loggers[0]
    assert f"{event} on /dev/md0" in loggers[0] and "/dev/sdc1" in loggers[0]
    assert walls and any(f"{event} on /dev/md0" in c for c in walls)


@pytest.mark.parametrize("event", ["NewArray", "RebuildStarted", "RebuildFinished", "SpareActive", "TestMessage"])
def test_other_events_are_logged_quietly(fake_bin: Path, tmp_path: Path, event: str) -> None:
    calls = _event(fake_bin, tmp_path, event, "/dev/md0")
    assert len(calls) == 1 and calls[0].startswith("logger ") and "-p daemon.info" in calls[0]
    assert f"{event} on /dev/md0" in calls[0]


def test_missing_arguments_do_not_fail(fake_bin: Path, tmp_path: Path) -> None:
    calls = _event(fake_bin, tmp_path)
    assert len(calls) == 1 and "daemon.info" in calls[0]
