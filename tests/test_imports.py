"""Basic import tests for the pre_nixos package."""

from pathlib import Path
import sys

# Ensure repository root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_import_package() -> None:
    import pre_nixos  # noqa: F401


def test_import_modules() -> None:
    from pre_nixos import apply, inventory, network, planner  # noqa: F401


def test_import_cli_entrypoint() -> None:
    """Ensure the CLI module imports without missing dependencies."""

    __import__("pre_nixos.pre_nixos")
