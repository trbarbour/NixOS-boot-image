"""Basic import tests for the pre_nixos package."""

from pathlib import Path
import sys

# Ensure repository root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_import_package() -> None:
    import pre_nixos  # noqa: F401


def test_import_modules() -> None:
    from pre_nixos import inventory, planner, apply, network  # noqa: F401
