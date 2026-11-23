"""The VM debug scripts build from a site, like the VM fixtures (task queue item 19).

``scripts/manual_vm_debug.py`` and ``scripts/collect_sshd_pre_nixos_debug.py``
passed the root key through the legacy environment fallback
(``PRE_NIXOS_ROOT_KEY`` with ``--impure``; site-settings design D2c), while
``tests/vm/fixtures.py`` already used ``--override-input site path:<dir>``.
All three now share one helper, ``tests.vm.site_build``.  The fallback itself
is gone since item 57; a pure build (no ``--impure``) cannot read the
environment, so the absence of ``--impure`` is what keeps it out.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, List

import pytest

from scripts import collect_sshd_pre_nixos_debug, manual_vm_debug
from tests.vm import site_build

STORE_PATH = "/nix/store/0000000000000000000000000000000-pre-nixos.iso"


def _capture(monkeypatch, module) -> List[Dict[str, Any]]:
    calls: List[Dict[str, Any]] = []

    def fake_run(cmd, **kwargs):
        calls.append({"cmd": list(cmd), "env": kwargs.get("env")})
        return subprocess.CompletedProcess(cmd, 0, stdout=STORE_PATH + "\n", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    # No real `nix flake metadata` from nix_command's verified overrides.
    monkeypatch.delenv("PRE_NIXOS_NIX_GIT_INPUTS", raising=False)
    return calls


def _build_call(calls: List[Dict[str, Any]]) -> Dict[str, Any]:
    builds = [c for c in calls if "build" in c["cmd"]]
    assert len(builds) == 1, calls
    return builds[0]


def _assert_site_build(call: Dict[str, Any], key: Path) -> None:
    cmd = call["cmd"]
    assert "--impure" not in cmd, cmd
    site = Path(cmd[cmd.index("--override-input") + 2].removeprefix("path:"))
    assert cmd[cmd.index("--override-input") + 1] == "site"
    assert (site / "root_key.pub").read_text() == key.read_text()
    assert "rootKey = ./root_key.pub;" in (site / "pre-nixos-site.nix").read_text()


@pytest.fixture
def key(tmp_path: Path) -> Path:
    path = tmp_path / "keys" / "id.pub"
    path.parent.mkdir()
    path.write_text("ssh-ed25519 AAAATEST test@local\n")
    return path


def _assert_key_dir_untouched(key: Path) -> None:
    """Codex on #360: a supplied key may sit in a read-only directory (the
    Nix store, a shared key directory); only reading it is allowed."""

    assert sorted(p.name for p in key.parent.iterdir()) == [key.name]


def test_manual_vm_debug_builds_from_a_site(monkeypatch, key: Path, tmp_path: Path) -> None:
    calls = _capture(monkeypatch, manual_vm_debug)
    monkeypatch.setattr(manual_vm_debug, "require_executable", lambda name: name)
    monkeypatch.setattr(manual_vm_debug, "describe_boot_image", lambda path, public_key: path)
    site = tmp_path / "work" / "site"
    assert manual_vm_debug.build_boot_image(key, site_dir=site) == Path(STORE_PATH)
    call = _build_call(calls)
    _assert_site_build(call, key)
    assert f"path:{site}" in call["cmd"]
    _assert_key_dir_untouched(key)


def test_collect_sshd_debug_builds_from_a_site(monkeypatch, key: Path, tmp_path: Path) -> None:
    calls = _capture(monkeypatch, collect_sshd_pre_nixos_debug)
    monkeypatch.setattr(collect_sshd_pre_nixos_debug, "resolve_iso_path", lambda path: path)
    site = tmp_path / "work" / "site"
    try:
        collect_sshd_pre_nixos_debug.build_boot_image(key, site_dir=site)
    except Exception:
        pass  # what follows the build (path-info parsing) is not under test
    call = _build_call(calls)
    _assert_site_build(call, key)
    assert f"path:{site}" in call["cmd"]
    _assert_key_dir_untouched(key)


def test_the_site_helper_writes_key_and_optional_hash(tmp_path: Path, key: Path) -> None:
    site = site_build.write_test_site(tmp_path / "site", key)
    assert (site / "root_key.pub").read_text() == key.read_text()
    assert "rootHashedPassword" not in (site / "pre-nixos-site.nix").read_text()
    site = site_build.write_test_site(tmp_path / "site2", key, root_hashed_password="$6$x$y")
    assert 'rootHashedPassword = "$6$x$y";' in (site / "pre-nixos-site.nix").read_text()


def test_the_build_arguments(tmp_path: Path) -> None:
    assert site_build.build_args(".#bootImage", tmp_path) == [
        "build", ".#bootImage", "--no-link", "--print-out-paths",
        "--override-input", "site", f"path:{tmp_path}",
    ]


def test_every_build_boot_image_caller_passes_a_site_dir() -> None:
    """``scripts/`` is not type-checked (task queue item 7), so a caller left
    without the new keyword would fail only at run time.  Two did, until
    this test (Codex on #360)."""

    import ast

    scripts = Path(__file__).resolve().parents[1] / "scripts"
    missing = []
    for path in sorted(scripts.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            if name == "build_boot_image" and "site_dir" not in {k.arg for k in node.keywords}:
                missing.append(f"{path.name}:{node.lineno}")
    assert missing == []


def test_no_harness_or_script_evaluates_impurely() -> None:
    """Item 57: the flake reads the environment only under ``--impure``, where
    the removed ``PRE_NIXOS_ROOT_KEY`` / ``PRE_NIXOS_AUTO_INSTALL`` now stop
    the build.  Nothing here needs impurity, so no string literal in the
    scripts or the VM harness may say ``--impure`` (docstrings aside)."""

    import ast

    repo = Path(__file__).resolve().parents[1]
    found = []
    for path in sorted([*(repo / "scripts").glob("*.py"), *(repo / "tests" / "vm").glob("*.py")]):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docstrings = {
            id(node.body[0].value)
            for node in ast.walk(tree)
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
        }
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and "--impure" in node.value
                and id(node) not in docstrings
            ):
                found.append(f"{path.relative_to(repo)}:{node.lineno}")
    assert found == []
