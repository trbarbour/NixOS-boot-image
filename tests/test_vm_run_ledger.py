"""The VM run ledger (notes/vm-run-ledger.jsonl) stays valid JSONL.

PR trbarbour/NixOS-boot-image#315 review: two committed lines were corrupt.
Cause (proven from the archived harness logs): the buffered append hit ENOSPC
part-way (runs 2026-10-19T011942Z and T055002Z, OSError 28 at the same
instant as their "Failed to append VM run entry" lines), leaving a partial
line that the next entry was appended to.
"""

from __future__ import annotations

import errno
import json
from pathlib import Path

import pytest

from tests.vm import metadata

LEDGER = Path(__file__).resolve().parents[1] / "notes" / "vm-run-ledger.jsonl"


def test_committed_ledger_is_valid_jsonl() -> None:
    for number, line in enumerate(LEDGER.read_text(encoding="utf-8").splitlines(), 1):
        try:
            json.loads(line)
        except json.JSONDecodeError as exc:  # pragma: no cover - failure path
            pytest.fail(f"{LEDGER.name} line {number}: {exc}")


def test_disk_full_part_way_leaves_the_ledger_unchanged(tmp_path: Path, monkeypatch) -> None:
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text('{"a": 1}\n', encoding="utf-8")
    real_write = metadata.os.write
    calls = {"n": 0}

    def write_then_fill_the_disk(fd: int, data: bytes) -> int:
        calls["n"] += 1
        if calls["n"] == 1:
            return real_write(fd, data[:5])  # a short write, as when space runs out
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(metadata.os, "write", write_then_fill_the_disk)
    with pytest.raises(OSError):
        metadata._append_line(ledger, json.dumps({"b": 2}) + "\n")

    monkeypatch.undo()
    assert ledger.read_text(encoding="utf-8") == '{"a": 1}\n'
    metadata._append_line(ledger, json.dumps({"c": 3}) + "\n")
    assert [json.loads(line) for line in ledger.read_text().splitlines()] == [{"a": 1}, {"c": 3}]
