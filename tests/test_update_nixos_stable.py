"""Tests for the update_nixos_stable helper script."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def update_script():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "update_nixos_stable.py"
    spec = importlib.util.spec_from_file_location("update_nixos_stable", script_path)
    assert spec and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[assignment]
    return module


def test_update_flake_nix_replaces_channel(tmp_path, update_script):
    flake_nix = tmp_path / "flake.nix"
    flake_nix.write_text(
        """
{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.11";
  };
}
""".strip(),
        encoding="utf-8",
    )

    update_script.update_flake_nix(flake_nix, "nixos-25.05")

    updated = flake_nix.read_text(encoding="utf-8")
    assert "nixos-25.05" in updated
    assert "\\1" not in updated


def test_update_flake_nix_requires_existing_entry(tmp_path, update_script):
    flake_nix = tmp_path / "flake.nix"
    flake_nix.write_text("{ inputs = { }; }", encoding="utf-8")

    with pytest.raises(SystemExit):
        update_script.update_flake_nix(flake_nix, "nixos-25.05")


def test_update_flake_nix_replaces_with_release_tag(tmp_path, update_script):
    flake_nix = tmp_path / "flake.nix"
    flake_nix.write_text(
        """
{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.11";
  };
}
""".strip(),
        encoding="utf-8",
    )

    update_script.update_flake_nix(flake_nix, "25.05")

    updated = flake_nix.read_text(encoding="utf-8")
    assert 'nixpkgs.url = "github:NixOS/nixpkgs/25.05";' in updated


def test_newest_stable_release_tag_selects_highest(update_script):
    tags = ["release-16.03-start", "24.11", "23.11", "25.05", "v208"]
    assert update_script.newest_stable_release_tag(tags) == "25.05"


def test_remote_ref_names_strips_prefixes_and_peeled_suffixes(update_script, monkeypatch):
    """Discovery uses git ls-remote (the GitHub API answered 403 on 2026-10-18)."""

    listing = {
        "refs/tags/26.05": "a" * 40,
        "refs/tags/26.05^{}": "b" * 40,
        "refs/tags/25.05": "c" * 40,
        "refs/heads/master": "d" * 40,
    }
    calls = []

    def fake_ls_remote(url, *patterns):
        calls.append((url, patterns))
        return listing

    monkeypatch.setattr(update_script.nix_git_inputs, "ls_remote", fake_ls_remote)
    assert update_script.remote_ref_names("tags") == ["25.05", "26.05"]
    assert update_script.remote_ref_names("heads") == ["master"]
    assert calls[0] == (update_script.NIXPKGS_URL, ("refs/tags/*",))
