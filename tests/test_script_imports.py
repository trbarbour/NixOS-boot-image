"""Every helper script must at least import: none is otherwise exercised by CI.

Regression: after the VM helpers moved into ``tests/vm/`` (``11aa4b6``) the VM
debug scripts kept importing ``_resolve_iso_path`` from the legacy
``tests.test_boot_image_vm`` shim, whose star-import omits underscored names,
so they failed at import time without any test noticing.

They are also run by path (``python scripts/manual_vm_debug.py``, as the work
notes do), where ``sys.path`` holds ``scripts/`` rather than the repository
root.  ``manual_vm_debug.py`` failed so, with ``No module named 'scripts'``
(found while doing task queue item 7).
"""
from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
SCRIPT_MODULES = sorted(path.stem for path in SCRIPTS_DIR.glob("*.py"))


def test_script_modules_are_discovered() -> None:
    assert "manual_vm_debug" in SCRIPT_MODULES


@pytest.mark.parametrize("module", SCRIPT_MODULES)
def test_script_imports(module: str) -> None:
    importlib.import_module(f"scripts.{module}")


@pytest.mark.parametrize("module", SCRIPT_MODULES)
def test_script_runs_by_path(module: str, tmp_path: Path) -> None:
    """``--help`` from another directory: no reliance on the caller's cwd."""

    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / f"{module}.py"), "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
