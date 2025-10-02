"""Tests for ensuring Nix flake packaging retains required dependencies."""

from __future__ import annotations

import re
from pathlib import Path


def _extract_propagated_inputs() -> set[str]:
    flake_text = Path("flake.nix").read_text(encoding="utf-8")
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
