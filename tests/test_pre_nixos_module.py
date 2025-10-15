"""Assertions about the NixOS module wiring for the boot image."""

from __future__ import annotations

import re
from pathlib import Path


def _extract_service_block() -> str:
    module_text = Path("modules/pre-nixos.nix").read_text(encoding="utf-8")
    try:
        start = module_text.index("systemd.services.pre-nixos = {")
    except ValueError as exc:  # pragma: no cover - defensive guard
        raise AssertionError(
            "systemd.services.pre-nixos definition missing from module"
        ) from exc

    end = module_text.find("\n    };", start)
    if end == -1:
        raise AssertionError("systemd.services.pre-nixos block not terminated")

    return module_text[start:end]


def _extract_service_path_packages() -> set[str]:
    block = _extract_service_block()
    match = re.search(r"path\s*=\s*with pkgs;\s*\[(?P<body>[^\]]+)\];", block, re.DOTALL)
    if match is None:
        raise AssertionError("systemd.services.pre-nixos.path definition missing")

    body = match.group("body")
    tokens = {
        token
        for token in re.findall(r"[A-Za-z0-9_-]+", body)
        if token not in {"with", "pkgs"}
    }
    return tokens


def test_service_path_includes_runtime_utilities() -> None:
    packages = _extract_service_path_packages()
    required = {
        "coreutils",
        "disko",
        "dosfstools",
        "e2fsprogs",
        "ethtool",
        "gptfdisk",
        "iproute2",
        "lvm2",
        "mdadm",
        "parted",
        "systemd",
        "util-linux",
    }
    missing = required - packages
    assert not missing, (
        "pre-nixos service path must include runtime tools required for storage "
        f"and networking automation (missing: {sorted(missing)})"
    )


def test_module_enables_systemd_networkd() -> None:
    module_text = Path("modules/pre-nixos.nix").read_text(encoding="utf-8")
    assert "systemd.network.enable = true;" in module_text
    assert "networking.useNetworkd = lib.mkForce true;" in module_text
    assert "networking.useDHCP = lib.mkForce false;" in module_text
    assert "networking.networkmanager.enable = lib.mkForce false;" in module_text


def test_module_sets_nix_path_for_pre_nixos_environment() -> None:
    module_text = Path("modules/pre-nixos.nix").read_text(encoding="utf-8")
    service_block = _extract_service_block()
    assert "preNixosServiceEnv = preNixosExecEnv // {" in module_text
    assert 'NIX_PATH = "nixpkgs=${pkgs.path}";' in module_text
    assert 'PRE_NIXOS_NIXPKGS = "${pkgs.path}";' in module_text
    assert "environment.sessionVariables = lib.mkMerge [" in module_text
    assert 'preNixosExecEnv' in module_text
    assert (
        '{ NIX_PATH = lib.mkForce "nixpkgs=${pkgs.path}"; }' in module_text
    )
    assert "environment = preNixosServiceEnv;" in service_block
