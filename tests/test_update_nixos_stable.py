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
