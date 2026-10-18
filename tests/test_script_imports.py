"""Every helper script must at least import: none is otherwise exercised by CI.

Regression: after the VM helpers moved into ``tests/vm/`` (``11aa4b6``) the VM
debug scripts kept importing ``_resolve_iso_path`` from the legacy
``tests.test_boot_image_vm`` shim, whose star-import omits underscored names,
so they failed at import time without any test noticing.
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
SCRIPT_MODULES = sorted(path.stem for path in SCRIPTS_DIR.glob("*.py"))


def test_script_modules_are_discovered() -> None:
    assert "manual_vm_debug" in SCRIPT_MODULES


@pytest.mark.parametrize("module", SCRIPT_MODULES)
def test_script_imports(module: str) -> None:
    importlib.import_module(f"scripts.{module}")
