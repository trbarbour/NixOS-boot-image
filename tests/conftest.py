from pathlib import Path
import sys
import pytest

pytest_plugins = ["tests.vm.fixtures", "tests.vm.aarch64_fixtures", "tests.storage_stub"]


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


@pytest.fixture(autouse=True)
def _keep_tests_out_of_host_paths(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Point pre-nixos's host-path defaults into a temporary directory.

    Unset, ``log_event`` appends to /var/log/pre-nixos/actions.log and
    ``apply_plan`` writes /var/log/pre-nixos/disko-config.nix.  As root, tests
    silently wrote there (2522 lines found on the dev host, 2026-10-21); as
    an ordinary user (GitHub Actions, PR #318's first run) the denied write
    added an error line to stderr and broke three JSON-log tests.  A test
    that sets ``PRE_NIXOS_LOG_FILE`` itself still wins (monkeypatch order).
    """

    from pre_nixos import apply

    host_paths = tmp_path_factory.mktemp("pre-nixos-host-paths")
    monkeypatch.setenv("PRE_NIXOS_LOG_FILE", str(host_paths / "actions.log"))
    monkeypatch.setattr(apply, "DISKO_CONFIG_PATH", host_paths / "disko-config.nix")
