"""A failed image build shows Nix's error (task queue item 37).

When the ISO build failed (2026-11-08: out of disk, ``xorriso : FAILURE :
Image size … exceeds free space on media``), the VM fixture reported only
``CalledProcessError`` with the command; Nix's stderr was in neither the
pytest output nor the run log, so the cause was found only by rerunning the
build by hand.  The failure must carry the tail of Nix's stderr.
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from tests.vm.fixtures import SSHKeyPair, build_boot_artifact


def _fake_nix(tmp_path: Path, script: str) -> Path:
    fake = tmp_path / "nix"
    fake.write_text("#!/bin/sh\n" + script)
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    return fake


def _keys(tmp_path: Path) -> SSHKeyPair:
    keys = tmp_path / "keys"
    keys.mkdir()
    (keys / "id").write_text("private")
    (keys / "id.pub").write_text("ssh-ed25519 AAAA test")
    return SSHKeyPair(keys / "id", keys / "id.pub")


def test_failed_build_reports_the_tail_of_nix_stderr(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("PRE_NIXOS_NIX_GIT_INPUTS", raising=False)
    fake = _fake_nix(
        tmp_path,
        'for i in $(seq 1 200); do echo "building line $i" >&2; done\n'
        "echo 'xorriso : FAILURE : Image size 769296s exceeds free space on media 485468s' >&2\n"
        "exit 1\n",
    )
    with pytest.raises(AssertionError) as info:
        build_boot_artifact(str(fake), ".#bootImage", _keys(tmp_path), "ssh-keygen")
    message = str(info.value)
    assert "exceeds free space on media" in message
    assert ".#bootImage" in message and "exit status 1" in message
    assert "building line 200" in message
    assert "building line 1\n" not in message  # only the tail
