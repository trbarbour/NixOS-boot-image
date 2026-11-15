"""Product code behaves the same under pytest (task queue item 14).

``install._is_mount_ready`` treated ``ROOT/etc`` existing as "mounted", and
``install._request_reboot`` skipped the reboot, whenever ``PYTEST_CURRENT_TEST``
was set.  Pytest sets it during every test, so these tests run with it set:
they show the product paths, not the shortcuts.  Tests now inject the
behaviour they need instead.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from pre_nixos import install

PACKAGE = Path(install.__file__).resolve().parent
# The real function, taken at import: tests/conftest.py replaces it during
# every test, so that no test can reboot the host.
REAL_REQUEST_REBOOT = install._request_reboot


def test_no_product_module_checks_for_pytest() -> None:
    offenders = [
        str(path.relative_to(PACKAGE))
        for path in sorted(PACKAGE.rglob("*.py"))
        if "PYTEST_CURRENT_TEST" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_an_unmounted_root_with_etc_is_not_mounted(tmp_path: Path) -> None:
    assert os.environ.get("PYTEST_CURRENT_TEST")  # the condition the shortcut keyed on
    (tmp_path / "etc").mkdir()
    assert install._is_mount_ready(tmp_path) is False


def test_reboot_runs_systemctl(monkeypatch) -> None:
    calls: list = []

    def fake_run(cmd, check=False):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(install.subprocess, "run", fake_run)
    assert REAL_REQUEST_REBOOT() is True
    assert calls == [["systemctl", "reboot"]]
