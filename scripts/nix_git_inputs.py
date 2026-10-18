#!/usr/bin/env python3
"""Fetch ``github:`` flake inputs over git instead of GitHub archive tarballs.

Some build hosts (notably Claude Code cloud sessions) sit behind a proxy that
serves anonymous ``git`` reads of public GitHub repositories but refuses
``https://github.com/<owner>/<repo>/archive/<rev>.tar.gz`` downloads, which is
how Nix fetches ``github:`` flake inputs.  This module derives, from
``flake.lock``, one ``--override-input <path> git+https://...?rev=<rev>``
argument pair per locked ``github`` input, pinned to the same revision.

Overriding an input drops its locked ``narHash`` (Nix 2.34 does not accept
``narHash`` in a ``git+https`` URL; it is forwarded to git as part of the
remote URL).  To keep builds repeatable and deterministic (requirements §3),
the overridden inputs are fetched once via ``nix flake metadata --json`` and
every resulting ``narHash`` is checked against ``flake.lock`` before use.

Activation is explicit: callers inside the repository use
:func:`nix_command`, which applies the overrides only when
``PRE_NIXOS_NIX_GIT_INPUTS=1``.  Running this file directly always applies
them::

    scripts/nix_git_inputs.py build .#bootImage --impure   # runs nix
    scripts/nix_git_inputs.py --print                       # shows the args
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_VAR = "PRE_NIXOS_NIX_GIT_INPUTS"
SUPPORTED_LOCK_VERSION = 7


class NixGitInputsError(RuntimeError):
    """Raised for malformed lock files, bad settings, or hash mismatches."""


@dataclass(frozen=True)
class GithubInput:
    """A locked ``github`` input reachable from the root flake."""

    path: tuple[str, ...]
    node: str
    owner: str
    repo: str
    rev: str
    nar_hash: str

    def __post_init__(self) -> None:
        assert self.path, "input path must be non-empty"
        assert len(self.rev) == 40, f"rev must be a full commit hash: {self.rev!r}"

    @property
    def override_path(self) -> str:
        return "/".join(self.path)

    @property
    def git_url(self) -> str:
        return f"git+https://github.com/{self.owner}/{self.repo}?rev={self.rev}&shallow=1"


def _require(mapping: Mapping[str, Any], key: str, where: str) -> Any:
    if key not in mapping:
        raise NixGitInputsError(f"flake.lock: missing {key!r} in {where}")
    return mapping[key]


def parse_lock(lock: Mapping[str, Any]) -> tuple[GithubInput, ...]:
    """Return every ``github`` input reachable from the root, in path order.

    ``follows`` references (lists in ``inputs``) are skipped: they resolve to
    nodes that are reached, and therefore overridden, via their own path.
    Inputs of other types are left untouched.
    """

    version = _require(lock, "version", "top level")
    if version != SUPPORTED_LOCK_VERSION:
        raise NixGitInputsError(
            f"flake.lock: unsupported version {version!r} "
            f"(expected {SUPPORTED_LOCK_VERSION})"
        )
    nodes: Mapping[str, Any] = _require(lock, "nodes", "top level")
    root: str = _require(lock, "root", "top level")

    found: list[GithubInput] = []

    def visit(node_name: str, path: tuple[str, ...], ancestors: frozenset[str]) -> None:
        if node_name in ancestors:
            raise NixGitInputsError(
                f"flake.lock: input cycle through {node_name!r} at {'/'.join(path)}"
            )
        node = _require(nodes, node_name, "nodes")
        locked = node.get("locked")
        if path and locked is not None and locked.get("type") == "github":
            where = f"nodes.{node_name}.locked"
            found.append(
                GithubInput(
                    path=path,
                    node=node_name,
                    owner=_require(locked, "owner", where),
                    repo=_require(locked, "repo", where),
                    rev=_require(locked, "rev", where),
                    nar_hash=_require(locked, "narHash", where),
                )
            )
        for input_name, target in sorted(node.get("inputs", {}).items()):
            if isinstance(target, str):
                visit(target, path + (input_name,), ancestors | {node_name})
            elif not isinstance(target, list):
                raise NixGitInputsError(
                    f"flake.lock: unexpected input reference {target!r} "
                    f"for {node_name}.{input_name}"
                )

    visit(root, (), frozenset())
    return tuple(found)


def override_args(inputs: Sequence[GithubInput]) -> list[str]:
    """Return the ``--override-input`` arguments for ``inputs``."""

    args: list[str] = []
    for item in inputs:
        args += ["--override-input", item.override_path, item.git_url]
    return args


def find_hash_mismatches(
    inputs: Sequence[GithubInput], metadata: Mapping[str, Any]
) -> list[str]:
    """Compare ``nix flake metadata --json`` output against the locked hashes.

    Returns a human-readable description per mismatching or missing input;
    an empty list means every overridden input matches ``flake.lock``.
    """

    try:
        meta_nodes: Mapping[str, Any] = metadata["locks"]["nodes"]
    except (KeyError, TypeError) as exc:
        raise NixGitInputsError("nix flake metadata output lacks locks.nodes") from exc

    problems: list[str] = []
    for item in inputs:
        locked = meta_nodes.get(item.node, {}).get("locked", {})
        actual = locked.get("narHash")
        if actual is None:
            problems.append(f"{item.override_path}: no narHash reported by nix")
        elif actual != item.nar_hash:
            problems.append(
                f"{item.override_path}: fetched {actual}, flake.lock has {item.nar_hash}"
            )
    return problems


def load_inputs(repo_root: Path = REPO_ROOT) -> tuple[GithubInput, ...]:
    lock_path = repo_root / "flake.lock"
    try:
        lock = json.loads(lock_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise NixGitInputsError(f"cannot read {lock_path}: {exc}") from exc
    return parse_lock(lock)


def verified_override_args(nix: str, repo_root: Path = REPO_ROOT) -> list[str]:
    """Fetch the git-overridden inputs, verify their hashes, return the args."""

    inputs = load_inputs(repo_root)
    args = override_args(inputs)
    if not inputs:
        return args
    result = subprocess.run(
        [nix, "flake", "metadata", "--json", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise NixGitInputsError(
            f"nix flake metadata failed (exit {result.returncode}):\n{result.stderr}"
        )
    try:
        metadata = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise NixGitInputsError(f"nix flake metadata emitted invalid JSON: {exc}") from exc
    problems = find_hash_mismatches(inputs, metadata)
    if problems:
        raise NixGitInputsError(
            "git-fetched inputs do not match flake.lock:\n  " + "\n  ".join(problems)
        )
    return args


def git_inputs_enabled(environ: Mapping[str, str]) -> bool:
    """Interpret ``PRE_NIXOS_NIX_GIT_INPUTS``; reject anything but unset/0/1."""

    value = environ.get(ENV_VAR, "0")
    if value not in ("0", "1"):
        raise NixGitInputsError(f"{ENV_VAR} must be '0' or '1', got {value!r}")
    return value == "1"


def nix_command(
    nix: str,
    args: Sequence[str],
    *,
    repo_root: Path = REPO_ROOT,
    environ: Mapping[str, str] | None = None,
) -> list[str]:
    """Return ``[nix, *args]``, plus verified overrides when enabled."""

    env = os.environ if environ is None else environ
    command = [nix, *args]
    if git_inputs_enabled(env):
        command += verified_override_args(nix, repo_root)
    return command


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--print",
        action="store_true",
        help="print the verified override arguments instead of running nix",
    )
    parser.add_argument("nix_args", nargs=argparse.REMAINDER, help="arguments for nix")
    options = parser.parse_args(argv)
    nix_args = options.nix_args[1:] if options.nix_args[:1] == ["--"] else options.nix_args

    nix = shutil.which("nix")
    if nix is None:
        print("nix is not available in PATH", file=sys.stderr)
        return 1
    try:
        overrides = verified_override_args(nix)
    except NixGitInputsError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if options.print:
        print(" ".join(overrides))
        return 0
    if not nix_args:
        parser.error("no nix arguments given (use --print to show the overrides)")
    os.execv(nix, [nix, *nix_args, *overrides])
    return 1  # pragma: no cover - execv does not return


if __name__ == "__main__":
    sys.exit(main())
