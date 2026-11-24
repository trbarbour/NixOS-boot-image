"""``scripts/eval_checks.py``: evaluate every flake check without building (task
queue item 58).

``nix flake check --no-build`` cannot do this for this flake: it evaluates
against a read-only store, so a path that evaluation adds to the store and
then reads back (``builtins.path`` or ``builtins.toFile``, then ``readFile`` or
``import``) is "not valid" (toy-flake experiment, Nix 2.34.6,
``notes/2026-11-24T013105Z-item58-flake-check-no-build.md``).  Evaluating each
check's ``drvPath`` runs every check's assertions all the same, and CI runs it
under a site override (``--override-input site path:<dir>``), the README's
build, where ``self`` has no git revision.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any, Dict, List

import pytest

from scripts import eval_checks

DRV = "/nix/store/00000000000000000000000000000000-{}.drv"


def _fake_run(monkeypatch: pytest.MonkeyPatch, result: subprocess.CompletedProcess[str]) -> List[List[str]]:
    calls: List[List[str]] = []

    def fake(cmd: List[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append(list(cmd))
        return result

    monkeypatch.setattr(eval_checks.subprocess, "run", fake)
    monkeypatch.delenv("PRE_NIXOS_NIX_GIT_INPUTS", raising=False)  # no real `nix flake metadata`
    return calls


def _ok(checks: Dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], 0, stdout=json.dumps(checks), stderr="")


def test_the_command_evaluates_every_check_drv_path() -> None:
    assert eval_checks.eval_args("x86_64-linux", ["--override-input", "site", "path:./s"]) == [
        "eval", "--json", ".#checks.x86_64-linux",
        "--apply", "checks: builtins.mapAttrs (_: check: check.drvPath) checks",
        "--override-input", "site", "path:./s",
    ]


def test_success_reports_the_count(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    calls = _fake_run(monkeypatch, _ok({"a": DRV.format("a"), "b": DRV.format("b")}))
    assert eval_checks.main(["--override-input", "site", "path:./nix/site-default"]) == 0
    assert calls[0][0] == "nix" and calls[0][1:4] == ["eval", "--json", ".#checks.x86_64-linux"]
    assert calls[0][-3:] == ["--override-input", "site", "path:./nix/site-default"]
    assert "2 checks evaluated (x86_64-linux)" in capsys.readouterr().out


def test_the_system_is_selectable(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _fake_run(monkeypatch, _ok({"a": DRV.format("a")}))
    assert eval_checks.main(["--system", "aarch64-linux"]) == 0
    assert ".#checks.aarch64-linux" in calls[0]


def test_a_failing_check_fails_with_nix_error(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    _fake_run(monkeypatch, subprocess.CompletedProcess([], 1, stdout="", stderr="error: SD file name x\n"))
    assert eval_checks.main([]) == 1
    assert "error: SD file name x" in capsys.readouterr().err


@pytest.mark.parametrize("output", ["[]", "{}", '{"a": "not-a-drv"}', "not json"])
def test_unexpected_output_is_an_error(monkeypatch: pytest.MonkeyPatch, output: str) -> None:
    _fake_run(monkeypatch, subprocess.CompletedProcess([], 0, stdout=output, stderr=""))
    assert eval_checks.main([]) == 1


def test_ci_evaluates_the_checks_under_a_site_override() -> None:
    """The permanent regression test for item 58's ``image-file-names`` bug:
    CI's own ``nix flake check`` sees a git revision, so only an overridden
    evaluation exercises the fallback source id."""

    from pathlib import Path

    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml").read_text()
    assert "python3 scripts/eval_checks.py --override-input site path:./nix/site-default" in workflow
