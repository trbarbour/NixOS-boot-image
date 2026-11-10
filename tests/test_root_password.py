"""The installed system's hashed root password (reqs R-A1, R-A2; item 45).

Design: plans/2026-11-10T140423Z-root-password-design.md.
"""

from __future__ import annotations

import os
import re
import stat
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from pre_nixos import install, root_password
from pre_nixos.root_password import InvalidRootHash, RootHash
from tests.root_password_data import TEST_ROOT_PASSWORD_HASH as HASH
from tests.test_install import _make_lan, _sample_storage_plan

REPO = Path(__file__).resolve().parents[1]
SHA512 = "$6$rounds=5000$saltsalt$hash/hash.hash"


def test_scheme_list_matches_site_nix() -> None:
    """DRY guard: the Python list is nix/site.nix's, which a flake check ties to libxcrypt."""

    text = (REPO / "nix/site.nix").read_text()
    (listing,) = re.findall(r"cryptSchemeIds = \[([^\]]*)\];", text)
    assert tuple(re.findall(r'"([^"]+)"', listing)) == root_password.CRYPT_SCHEME_IDS


def test_fixture_site_hash_is_the_test_hash() -> None:
    text = (REPO / "tests/fixtures/site-example/pre-nixos-site.nix").read_text()
    assert f'rootHashedPassword = "{HASH}";' in text


@pytest.mark.parametrize("value", [HASH, SHA512, "$2b$12$abcdefghijklmnopqrstuv$abc"])
def test_accepts_crypt_hashes(value: str) -> None:
    assert root_password.is_crypt_hash(value)
    assert RootHash(value).value == value


@pytest.mark.parametrize(
    "value",
    ["hunter2", "", "!", "*", "$1$salt$md5", HASH + ":x", HASH + "\n", " " + HASH, "$y$j9T$a${b}$c"],
    ids=["plain", "empty", "locked", "star", "md5", "colon", "newline", "space", "interpolation"],
)
def test_rejects_non_hashes(value: str) -> None:
    assert not root_password.is_crypt_hash(value)
    with pytest.raises(InvalidRootHash) as info:
        RootHash(value)
    if value:
        assert value not in str(info.value)  # never echoed


def test_load_embedded(tmp_path: Path) -> None:
    path = tmp_path / "root_hashed_password"
    assert root_password.load_embedded(path) is None
    path.write_text(HASH)
    assert root_password.load_embedded(path) == RootHash(HASH)
    path.write_text(HASH + "\n")
    assert root_password.load_embedded(path) == RootHash(HASH)
    path.write_text("hunter2")
    with pytest.raises(InvalidRootHash):
        root_password.load_embedded(path)


def test_nix_lines() -> None:
    assert root_password.nix_lines(None) == []
    assert root_password.nix_lines(RootHash(HASH)) == [
        f'  users.users.root.hashedPassword = "{HASH}";',
        "",
    ]


SHADOW = (
    "messagebus:!:1::::::\n"
    "root:!:1::::::\n"
    "nixbld1:!:1::::::\n"
    "malformed-line-without-colons\n"
)


def test_with_root_hash_changes_only_roots_password() -> None:
    edit = root_password.with_root_hash(SHADOW, RootHash(HASH))
    assert edit.changed
    assert edit.text == SHADOW.replace("root:!:", f"root:{HASH}:")
    again = root_password.with_root_hash(edit.text, RootHash(HASH))
    assert again == root_password.ShadowEdit(edit.text, False)


def test_with_root_hash_without_root_line_or_final_newline() -> None:
    text = "messagebus:!:1::::::"
    assert root_password.with_root_hash(text, RootHash(HASH)) == root_password.ShadowEdit(text, False)
    edit = root_password.with_root_hash("root::1::::::", RootHash(HASH))
    assert edit.text == f"root:{HASH}:1::::::"


def test_apply_to_shadow_file_keeps_mode(tmp_path: Path) -> None:
    shadow = tmp_path / "shadow"
    assert not root_password.apply_to_shadow_file(shadow, RootHash(HASH))
    assert not shadow.exists()
    shadow.write_text(SHADOW)
    os.chmod(shadow, 0o640)
    assert root_password.apply_to_shadow_file(shadow, RootHash(HASH))
    assert f"root:{HASH}:1::::::\n" in shadow.read_text()
    assert stat.S_IMODE(shadow.stat().st_mode) == 0o640
    assert not root_password.apply_to_shadow_file(shadow, RootHash(HASH))
    assert sorted(p.name for p in tmp_path.iterdir()) == ["shadow"]  # no temp left


# --- auto_install -----------------------------------------------------------


@dataclass
class Target:
    root: Path
    calls: list[list[str]] = field(default_factory=list)


@pytest.fixture
def target(tmp_path, monkeypatch) -> Target:
    root = tmp_path / "mnt"
    (root / "etc").mkdir(parents=True)
    calls: list[list[str]] = []

    def fake_run(cmd, check=False):
        class Result:
            returncode = 0

        calls.append(list(cmd))
        if cmd[0] == "nixos-generate-config":
            config_dir = root / "etc/nixos"
            config_dir.mkdir(parents=True, exist_ok=True)
            if not (config_dir / "configuration.nix").exists():
                (config_dir / "configuration.nix").write_text("{\n}\n", encoding="utf-8")
            (config_dir / "hardware-configuration.nix").write_text("{\n}\n", encoding="utf-8")
        if cmd[0] == "nixos-install":
            # The shadow edit must precede nixos-install (design D4).
            shadow = root / "etc/shadow"
            calls.append(["shadow-at-install", shadow.read_text() if shadow.exists() else ""])
        return Result()

    monkeypatch.setattr(install.subprocess, "run", fake_run)
    monkeypatch.setattr(install, "_request_reboot", lambda: False)
    monkeypatch.setattr(install, "broadcast_to_consoles", lambda *a, **k: (False, [], {}))
    monkeypatch.setenv("PRE_NIXOS_EXEC", "1")
    return Target(root, calls)


def _install(tmp_path: Path, target: Target, password_file: Path):
    return install.auto_install(
        _make_lan(tmp_path),
        _sample_storage_plan(),
        enabled=True,
        trigger=install.InstallTrigger.REQUESTED,
        root_path=target.root,
        status_dir=tmp_path / "status",
        mount_attempts=1,
        mount_delay=0,
        root_password_file=password_file,
    )


def test_install_with_hash_writes_config_and_existing_shadow(tmp_path, target) -> None:
    """R-A1 and D4: a reinstall over an earlier attempt's shadow gets the hash."""

    (target.root / "etc/shadow").write_text(SHADOW)
    password_file = tmp_path / "root_hashed_password"
    password_file.write_text(HASH)
    result = _install(tmp_path, target, password_file)
    assert result.status == "success", result
    content = (target.root / "etc/nixos/configuration.nix").read_text()
    assert f'  users.users.root.hashedPassword = "{HASH}";' in content
    at_install = [c for c in target.calls if c[0] == "shadow-at-install"]
    assert at_install and f"root:{HASH}:" in at_install[0][1]


def test_install_without_hash_leaves_shadow_and_config_alone(tmp_path, target) -> None:
    (target.root / "etc/shadow").write_text(SHADOW)
    result = _install(tmp_path, target, tmp_path / "absent")
    assert result.status == "success", result
    assert (target.root / "etc/shadow").read_text() == SHADOW
    assert "hashedPassword" not in (target.root / "etc/nixos/configuration.nix").read_text()


def test_install_with_fresh_target_creates_no_shadow(tmp_path, target) -> None:
    password_file = tmp_path / "root_hashed_password"
    password_file.write_text(HASH)
    result = _install(tmp_path, target, password_file)
    assert result.status == "success", result
    assert not (target.root / "etc/shadow").exists()


def test_install_with_invalid_hash_stops_before_touching_the_target(tmp_path, target) -> None:
    (target.root / "etc/shadow").write_text(SHADOW)
    password_file = tmp_path / "root_hashed_password"
    password_file.write_text("hunter2")
    result = _install(tmp_path, target, password_file)
    assert (result.status, result.reason) == ("failed", "root-password-invalid")
    assert target.calls == []
    assert (target.root / "etc/shadow").read_text() == SHADOW
    status = (tmp_path / "status" / "auto-install-status").read_text()
    assert "hunter2" not in status
