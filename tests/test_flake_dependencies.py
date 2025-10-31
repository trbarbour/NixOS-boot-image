"""Tests for ensuring Nix flake packaging retains required dependencies."""

from __future__ import annotations

import re
from pathlib import Path


def _extract_propagated_inputs() -> set[str]:
    flake_text = Path("flake.nix").read_text(encoding="utf-8")
    required_names_block = re.search(
        r"requiredToolNames\s*=\s*\[(?P<body>[^\]]+)\];",
        flake_text,
        re.DOTALL,
    )
    if required_names_block is not None:
        body = required_names_block.group("body")
        return set(re.findall(r'"([^\"]+)"', body))

    with_block = re.search(
        r"propagatedBuildInputs\s*=\s*with pkgs;\s*\[(?P<body>[^\]]+)\];",
        flake_text,
        re.DOTALL,
    )
    if with_block is not None:
        body = with_block.group("body")
        # The ``with pkgs;`` statement omits the ``pkgs.`` prefix from
        # identifiers. Extract bare package names so the assertion remains
        # robust even if the list is reformatted across multiple lines.
        return set(re.findall(r"[A-Za-z0-9_-]+", body))

    attrvals_block = re.search(
        r"propagatedBuildInputs\s*=\s*pkgs\.lib\.attrVals\s*\[(?P<body>[^\]]+)\]\s*pkgs;",
        flake_text,
        re.DOTALL,
    )
    if attrvals_block is not None:
        body = attrvals_block.group("body")
        return set(re.findall(r'"([^"]+)"', body))

    raise AssertionError("propagatedBuildInputs block not found in flake.nix")


def test_pre_nixos_runtime_dependencies_include_required_tools() -> None:
    propagated = _extract_propagated_inputs()
    required_tools = {
        # Storage partitioning utilities
        "disko",
        "gptfdisk",
        "mdadm",
        "lvm2",
        "kmod",
        # Network diagnostics
        "ethtool",
        # General system tooling used during installation (e.g. findmnt)
        "util-linux",
    }

    missing = required_tools - propagated
    assert not missing, (
        "pre-nixos must propagate the expected tool packages for the boot "
        f"environment (missing: {sorted(missing)})"
    )


def test_pre_nixos_scripts_wrap_required_tool_path() -> None:
    flake_text = Path("flake.nix").read_text(encoding="utf-8")
    loop_pattern = r"for prog in pre-nixos pre-nixos-detect-storage pre-nixos-tui; do"
    assert re.search(loop_pattern, flake_text), (
        "pre-nixos flake must wrap all CLI entry points in postFixup"
    )
    assert "wrapProgram \"$out/bin/$prog\" --prefix PATH :" in flake_text, (
        "pre-nixos flake must extend PATH for wrapped CLI entry points"
    )


def test_pre_nixos_installs_root_key_during_post_install() -> None:
    flake_text = Path("flake.nix").read_text(encoding="utf-8")
    assert "postInstall = pkgs.lib.optionalString (rootPub != null)" in flake_text, (
        "pre-nixos flake must guard postInstall with the embedded key condition"
    )
    install_snippet = (
        "install -Dm0644 ${rootPub} \"$out/${pkgs.python3.sitePackages}/pre_nixos/root_key.pub\""
    )
    assert install_snippet in flake_text, (
        "pre-nixos flake must install the embedded root key into site-packages"
    )
