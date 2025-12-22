from pathlib import Path
import sys
import pytest

pytest_plugins = ["tests.vm.fixtures"]


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--boot-image-debug",
        action="store_true",
        help=(
            "Drop into an interactive pexpect session for boot-image VM tests "
            "when they fail."
        ),
    )


# Ensure repository root is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
