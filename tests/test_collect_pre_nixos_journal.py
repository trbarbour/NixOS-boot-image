"""``scripts/collect_pre_nixos_journal.py`` captures the whole boot run (task
queue item 8).

It collected the journal right after login, while ``pre-nixos`` was still
running, so it captured two lines (2026-10-18).  Now it waits for the unit to
stop first, as the VM tests do (``BootImageVM.wait_for_unit_inactive``).  A
unit that failed or did not finish in time still gets its journal, which is
when it is wanted most, and the script then exits non-zero.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import pytest

from scripts import collect_pre_nixos_journal as script

JOURNAL = "pre-nixos-start[1]: whole run\n"


class FakeVM:
    def __init__(self, calls: List[str], *, wait_error: Optional[Exception] = None) -> None:
        self.calls = calls
        self.wait_error = wait_error

    def wait_for_unit_inactive(self, unit: str, *, timeout: int) -> str:
        self.calls.append(f"wait {unit} {timeout}")
        if self.wait_error is not None:
            raise self.wait_error
        return "inactive"

    def collect_journal(self, unit: str) -> str:
        self.calls.append(f"journal {unit}")
        return JOURNAL

    def shutdown(self) -> None:
        self.calls.append("shutdown")


class FakeChild:
    def isalive(self) -> bool:
        return False


class FakeHandle:
    def close(self) -> None:
        pass


def _main(monkeypatch, tmp_path: Path, argv: List[str], vm: FakeVM) -> int:
    monkeypatch.setattr(script, "describe_boot_image", lambda path, public_key: object())
    monkeypatch.setattr(script, "prepare_disk_image", lambda path, size: path)
    monkeypatch.setattr(script, "allocate_ssh_port", lambda: 2222)
    monkeypatch.setattr(script, "launch_vm", lambda **kwargs: (vm, FakeChild(), FakeHandle()))
    out = tmp_path / "journal.txt"
    return script.main(["--iso-path", str(tmp_path), "--journal-output", str(out), *argv])


def test_the_journal_is_taken_after_the_unit_has_finished(monkeypatch, tmp_path: Path) -> None:
    calls: List[str] = []
    assert _main(monkeypatch, tmp_path, [], FakeVM(calls)) == 0
    assert calls == [
        f"wait pre-nixos.service {script.DEFAULT_TIMEOUT}",
        "journal pre-nixos.service",
        "shutdown",
    ]
    assert (tmp_path / "journal.txt").read_text() == JOURNAL + "\n"


def test_the_timeout_is_settable(monkeypatch, tmp_path: Path) -> None:
    calls: List[str] = []
    _main(monkeypatch, tmp_path, ["--timeout", "90"], FakeVM(calls))
    assert calls[0] == "wait pre-nixos.service 90"


@pytest.mark.parametrize("reason", ["Unit pre-nixos.service entered the failed state", "did not reach inactive"])
def test_a_failed_or_unfinished_unit_still_gets_its_journal(monkeypatch, tmp_path: Path, capsys, reason) -> None:
    calls: List[str] = []
    code = _main(monkeypatch, tmp_path, [], FakeVM(calls, wait_error=AssertionError(reason)))
    assert code == script.EXIT_UNIT_NOT_FINISHED == 2
    assert "journal pre-nixos.service" in calls
    assert (tmp_path / "journal.txt").read_text() == JOURNAL + "\n"
    assert reason in capsys.readouterr().err


def test_the_default_timeout_allows_an_emulated_boot() -> None:
    assert script.DEFAULT_TIMEOUT >= 1800
