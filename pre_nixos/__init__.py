"""Pre-NixOS setup package."""

from __future__ import annotations

from importlib import resources
from importlib.metadata import PackageNotFoundError, version as pkg_version

__all__ = ["inventory", "planner", "apply", "network", "partition", "tui", "install"]


def _discover_version() -> str:
    try:
        return pkg_version("pre-nixos")
    except PackageNotFoundError:
        try:
            return resources.files(__package__).joinpath("VERSION").read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return "unknown"


__version__ = _discover_version()
