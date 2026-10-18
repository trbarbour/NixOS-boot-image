"""Unit tests for scripts/nix_git_inputs.py (git-based flake input overrides)."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from scripts import nix_git_inputs as ngi

REPO_ROOT = Path(__file__).resolve().parents[1]

REV_A = "a" * 40
REV_B = "b" * 40
REV_C = "c" * 40

SAMPLE_LOCK: dict[str, Any] = {
    "version": 7,
    "root": "root",
    "nodes": {
        "root": {"inputs": {"nixpkgs": "nixpkgs", "utils": "utils", "local": "local"}},
        "nixpkgs": {
            "locked": {
                "type": "github",
                "owner": "NixOS",
                "repo": "nixpkgs",
                "rev": REV_A,
                "narHash": "sha256-A",
            }
        },
        "utils": {
            "inputs": {"systems": "systems", "nixpkgs": ["nixpkgs"]},
            "locked": {
                "type": "github",
                "owner": "numtide",
                "repo": "flake-utils",
                "rev": REV_B,
                "narHash": "sha256-B",
            },
        },
        "systems": {
            "locked": {
                "type": "github",
                "owner": "nix-systems",
                "repo": "default",
                "rev": REV_C,
                "narHash": "sha256-C",
            }
        },
        "local": {"locked": {"type": "path", "path": "/src", "narHash": "sha256-L"}},
    },
}


def _metadata(hashes: dict[str, str]) -> dict[str, Any]:
    return {"locks": {"nodes": {n: {"locked": {"narHash": h}} for n, h in hashes.items()}}}


def test_parse_lock_finds_nested_github_inputs_and_skips_follows_and_other_types() -> None:
    inputs = ngi.parse_lock(SAMPLE_LOCK)
    assert [(i.override_path, i.node, i.rev) for i in inputs] == [
        ("nixpkgs", "nixpkgs", REV_A),
        ("utils", "utils", REV_B),
        ("utils/systems", "systems", REV_C),
    ]


def test_override_args_pin_each_input_to_its_locked_rev() -> None:
    args = ngi.override_args(ngi.parse_lock(SAMPLE_LOCK))
    assert args[:3] == [
        "--override-input",
        "nixpkgs",
        f"git+https://github.com/NixOS/nixpkgs?rev={REV_A}&shallow=1",
    ]
    assert args[-3:] == [
        "--override-input",
        "utils/systems",
        f"git+https://github.com/nix-systems/default?rev={REV_C}&shallow=1",
    ]
    assert len(args) == 9


def test_parse_lock_rejects_unsupported_version() -> None:
    lock = copy.deepcopy(SAMPLE_LOCK)
    lock["version"] = 6
    with pytest.raises(ngi.NixGitInputsError, match="unsupported version"):
        ngi.parse_lock(lock)


def test_parse_lock_rejects_missing_rev() -> None:
    lock = copy.deepcopy(SAMPLE_LOCK)
    del lock["nodes"]["systems"]["locked"]["rev"]
    with pytest.raises(ngi.NixGitInputsError, match="'rev'"):
        ngi.parse_lock(lock)


def test_parse_lock_rejects_cycles() -> None:
    lock = copy.deepcopy(SAMPLE_LOCK)
    lock["nodes"]["systems"]["inputs"] = {"back": "utils"}
    with pytest.raises(ngi.NixGitInputsError, match="cycle"):
        ngi.parse_lock(lock)


def test_find_hash_mismatches_accepts_matching_hashes() -> None:
    inputs = ngi.parse_lock(SAMPLE_LOCK)
    meta = _metadata({"nixpkgs": "sha256-A", "utils": "sha256-B", "systems": "sha256-C"})
    assert ngi.find_hash_mismatches(inputs, meta) == []


def test_find_hash_mismatches_reports_wrong_and_missing_hashes() -> None:
    inputs = ngi.parse_lock(SAMPLE_LOCK)
    meta = _metadata({"nixpkgs": "sha256-X", "utils": "sha256-B"})
    assert ngi.find_hash_mismatches(inputs, meta) == [
        "nixpkgs: fetched sha256-X, flake.lock has sha256-A",
        "utils/systems: no narHash reported by nix",
    ]


@pytest.mark.parametrize("value, expected", [(None, False), ("0", False), ("1", True)])
def test_git_inputs_enabled_accepts_only_unset_zero_or_one(
    value: str | None, expected: bool
) -> None:
    env = {} if value is None else {ngi.ENV_VAR: value}
    assert ngi.git_inputs_enabled(env) is expected


@pytest.mark.parametrize("value", ["", "yes", "true", "2"])
def test_git_inputs_enabled_rejects_other_values(value: str) -> None:
    with pytest.raises(ngi.NixGitInputsError, match=ngi.ENV_VAR):
        ngi.git_inputs_enabled({ngi.ENV_VAR: value})


def test_nix_command_is_unchanged_when_disabled() -> None:
    assert ngi.nix_command("nix", ["build", ".#x"], environ={}) == ["nix", "build", ".#x"]


def test_nix_command_appends_verified_overrides_when_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "flake.lock").write_text(json.dumps(SAMPLE_LOCK))
    calls: list[list[str]] = []

    class Result:
        returncode = 0
        stdout = json.dumps(
            _metadata({"nixpkgs": "sha256-A", "utils": "sha256-B", "systems": "sha256-C"})
        )
        stderr = ""

    def fake_run(cmd: list[str], **kwargs: Any) -> Result:
        calls.append(cmd)
        assert kwargs["cwd"] == tmp_path
        return Result()

    monkeypatch.setattr(ngi.subprocess, "run", fake_run)
    command = ngi.nix_command(
        "nix", ["build"], repo_root=tmp_path, environ={ngi.ENV_VAR: "1"}
    )
    overrides = ngi.override_args(ngi.parse_lock(SAMPLE_LOCK))
    assert command == ["nix", "build", *overrides]
    assert calls == [["nix", "flake", "metadata", "--json", *overrides]]


def test_nix_command_refuses_hash_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "flake.lock").write_text(json.dumps(SAMPLE_LOCK))

    class Result:
        returncode = 0
        stdout = json.dumps(
            _metadata({"nixpkgs": "sha256-EVIL", "utils": "sha256-B", "systems": "sha256-C"})
        )
        stderr = ""

    monkeypatch.setattr(ngi.subprocess, "run", lambda cmd, **kw: Result())
    with pytest.raises(ngi.NixGitInputsError, match="nixpkgs: fetched sha256-EVIL"):
        ngi.nix_command("nix", ["build"], repo_root=tmp_path, environ={ngi.ENV_VAR: "1"})


def test_nix_command_reports_nix_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "flake.lock").write_text(json.dumps(SAMPLE_LOCK))

    class Result:
        returncode = 1
        stdout = ""
        stderr = "HTTP error 403"

    monkeypatch.setattr(ngi.subprocess, "run", lambda cmd, **kw: Result())
    with pytest.raises(ngi.NixGitInputsError, match="exit 1"):
        ngi.nix_command("nix", ["build"], repo_root=tmp_path, environ={ngi.ENV_VAR: "1"})


def test_repository_flake_lock_is_supported() -> None:
    """The real flake.lock must parse and yield at least the nixpkgs input."""

    paths = [i.override_path for i in ngi.load_inputs(REPO_ROOT)]
    assert "nixpkgs" in paths


# --- updating an input without tarball fetches (--update/--ref) ---

REV_D = "d" * 40
NEW_REVISION = ngi.GithubRevision(
    owner="NixOS",
    repo="nixpkgs",
    ref="nixos-26.05",
    rev=REV_D,
    nar_hash="sha256-D",
    last_modified=1792030654,
)


def test_updated_lock_rewrites_only_the_named_input() -> None:
    before = copy.deepcopy(SAMPLE_LOCK)
    new = ngi.updated_lock(SAMPLE_LOCK, "nixpkgs", NEW_REVISION)

    assert SAMPLE_LOCK == before, "input lock must not be mutated"
    assert new["nodes"]["nixpkgs"]["locked"] == {
        "lastModified": 1792030654,
        "narHash": "sha256-D",
        "owner": "NixOS",
        "repo": "nixpkgs",
        "rev": REV_D,
        "type": "github",
    }
    assert new["nodes"]["nixpkgs"]["original"] == {
        "owner": "NixOS",
        "ref": "nixos-26.05",
        "repo": "nixpkgs",
        "type": "github",
    }
    for other in ("utils", "systems", "local"):
        assert new["nodes"][other] == SAMPLE_LOCK["nodes"][other]


def test_updated_lock_refuses_another_repository() -> None:
    other = ngi.GithubRevision(**{**NEW_REVISION.__dict__, "repo": "not-nixpkgs"})
    with pytest.raises(ngi.NixGitInputsError, match="is not github:NixOS/not-nixpkgs"):
        ngi.updated_lock(SAMPLE_LOCK, "nixpkgs", other)


def test_updated_lock_refuses_unknown_and_non_github_inputs() -> None:
    with pytest.raises(ngi.NixGitInputsError, match="missing 'absent'"):
        ngi.updated_lock(SAMPLE_LOCK, "absent", NEW_REVISION)
    with pytest.raises(ngi.NixGitInputsError, match="is not github"):
        ngi.updated_lock(SAMPLE_LOCK, "local", NEW_REVISION)


def test_format_lock_matches_the_repository_lock_byte_for_byte() -> None:
    text = (REPO_ROOT / "flake.lock").read_text()
    assert ngi.format_lock(json.loads(text)) == text


class _Completed:
    def __init__(self, stdout: str, returncode: int = 0, stderr: str = "") -> None:
        self.stdout, self.returncode, self.stderr = stdout, returncode, stderr


def _fake_run(ls_remote: str, metadata: dict[str, Any]):  # type: ignore[no-untyped-def]
    calls: list[list[str]] = []

    def run(cmd, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(list(cmd))
        if cmd[:2] == ["git", "ls-remote"]:
            return _Completed(ls_remote)
        if cmd[1:4] == ["flake", "metadata", "--json"]:
            return _Completed(json.dumps(metadata))
        raise AssertionError(f"unexpected command {cmd}")

    return run, calls


def test_fetch_github_revision_pins_the_branch_head(monkeypatch: pytest.MonkeyPatch) -> None:
    run, calls = _fake_run(
        f"{REV_D}\trefs/heads/nixos-26.05\n",
        {"locked": {"rev": REV_D, "narHash": "sha256-D", "lastModified": 1792030654}},
    )
    monkeypatch.setattr(ngi.subprocess, "run", run)

    assert ngi.fetch_github_revision("nix", "NixOS", "nixpkgs", "nixos-26.05") == NEW_REVISION
    assert calls[1][-1] == f"git+https://github.com/NixOS/nixpkgs?rev={REV_D}&shallow=1"


def test_fetch_github_revision_refuses_a_different_fetched_rev(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run, _ = _fake_run(
        f"{REV_D}\trefs/heads/nixos-26.05\n",
        {"locked": {"rev": REV_A, "narHash": "sha256-A", "lastModified": 1}},
    )
    monkeypatch.setattr(ngi.subprocess, "run", run)
    with pytest.raises(ngi.NixGitInputsError, match="not " + REV_D):
        ngi.fetch_github_revision("nix", "NixOS", "nixpkgs", "nixos-26.05")


def test_fetch_github_revision_refuses_a_missing_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    run, _ = _fake_run("", {})
    monkeypatch.setattr(ngi.subprocess, "run", run)
    with pytest.raises(ngi.NixGitInputsError, match="no branch or tag named 'nixos-99.99'"):
        ngi.fetch_github_revision("nix", "NixOS", "nixpkgs", "nixos-99.99")


def test_commit_for_ref_peels_annotated_release_tags() -> None:
    """Listing shape observed 2026-10-18 for nixpkgs ``refs/tags/26.05``."""

    refs = {"refs/tags/26.05": REV_A, "refs/tags/26.05^{}": REV_D}
    assert ngi.commit_for_ref(refs, "26.05") == REV_D
    assert ngi.commit_for_ref({"refs/tags/v1": REV_B}, "v1") == REV_B
    assert ngi.commit_for_ref({"refs/heads/nixos-26.05": REV_D}, "nixos-26.05") == REV_D


def test_commit_for_ref_refuses_a_name_that_is_branch_and_tag() -> None:
    refs = {"refs/heads/x": REV_A, "refs/tags/x": REV_B}
    with pytest.raises(ngi.NixGitInputsError, match="both a branch and a tag"):
        ngi.commit_for_ref(refs, "x")


def test_update_and_ref_must_be_given_together() -> None:
    with pytest.raises(SystemExit):
        ngi.main(["--update", "nixpkgs"])
