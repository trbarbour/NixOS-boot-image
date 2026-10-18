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

``nix flake update`` fetches tarballs too, so it fails on such hosts.
``--update INPUT --ref REF`` updates one root ``github`` input instead: it
resolves the branch (or tag) with ``git ls-remote``, fetches that revision over
git to learn its ``narHash`` and ``lastModified``, and rewrites the lock entry
as an ordinary ``github`` entry (tarball and git fetches of a revision have
the same ``narHash``, which the verification above already relies on)::

    scripts/nix_git_inputs.py --update nixpkgs --ref nixos-26.05
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


@dataclass(frozen=True)
class GithubRevision:
    """A ``github`` input pinned to a branch head, as recorded in ``flake.lock``."""

    owner: str
    repo: str
    ref: str
    rev: str
    nar_hash: str
    last_modified: int

    def __post_init__(self) -> None:
        assert len(self.rev) == 40, f"rev must be a full commit hash: {self.rev!r}"
        assert self.nar_hash.startswith("sha256-"), self.nar_hash
        assert self.ref and not self.ref.startswith("refs/"), self.ref


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


def updated_lock(
    lock: Mapping[str, Any], input_name: str, revision: GithubRevision
) -> dict[str, Any]:
    """Return a copy of ``lock`` with root input ``input_name`` set to ``revision``.

    Only a root input that is already a ``github`` input of the same
    repository may be updated; anything else is refused rather than guessed.
    """

    parse_lock(lock)  # validates the version and structure
    new = json.loads(json.dumps(lock))
    nodes = new["nodes"]
    node_name = _require(nodes[new["root"]].get("inputs", {}), input_name, "root inputs")
    if not isinstance(node_name, str):
        raise NixGitInputsError(f"flake.lock: root input {input_name!r} is a follows")
    node = nodes[node_name]
    locked = _require(node, "locked", f"nodes.{node_name}")
    if locked.get("type") != "github" or (locked.get("owner"), locked.get("repo")) != (
        revision.owner,
        revision.repo,
    ):
        raise NixGitInputsError(
            f"flake.lock: {input_name!r} is not github:{revision.owner}/{revision.repo}"
        )
    node["locked"] = {
        "lastModified": revision.last_modified,
        "narHash": revision.nar_hash,
        "owner": revision.owner,
        "repo": revision.repo,
        "rev": revision.rev,
        "type": "github",
    }
    node["original"] = {
        "owner": revision.owner,
        "ref": revision.ref,
        "repo": revision.repo,
        "type": "github",
    }
    assert any(
        i.node == node_name and i.rev == revision.rev for i in parse_lock(new)
    ), "updated input not found in the new lock"
    return new


def format_lock(lock: Mapping[str, Any]) -> str:
    """Serialise a lock as Nix writes it (sorted keys, 2-space indent)."""

    return json.dumps(lock, indent=2, sort_keys=True) + "\n"


def ls_remote(url: str, *patterns: str) -> dict[str, str]:
    """Return ``{ref name: object id}`` from ``git ls-remote url patterns...``."""

    result = subprocess.run(
        ["git", "ls-remote", url, *patterns], capture_output=True, text=True
    )
    if result.returncode != 0:
        raise NixGitInputsError(f"git ls-remote {url} failed:\n{result.stderr}")
    refs: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if line.strip():
            object_id, name = line.split()
            refs[name] = object_id
    return refs


def commit_for_ref(refs: Mapping[str, str], ref: str) -> str:
    """Return the commit that branch or tag ``ref`` names in an ls-remote listing.

    Annotated tags list the tag object and, as ``<tag>^{}``, the commit it
    points to (nixpkgs release tags are annotated); the commit is what a lock
    pins.  A name that is both a branch and a tag is refused as ambiguous.
    """

    branch = refs.get(f"refs/heads/{ref}")
    tag = refs.get(f"refs/tags/{ref}^{{}}") or refs.get(f"refs/tags/{ref}")
    if branch and tag:
        raise NixGitInputsError(f"{ref!r} is both a branch and a tag")
    commit = branch or tag
    if commit is None:
        raise NixGitInputsError(f"no branch or tag named {ref!r}")
    return commit


def fetch_github_revision(nix: str, owner: str, repo: str, ref: str) -> GithubRevision:
    """Fetch branch or tag ``ref`` over git and describe it for ``flake.lock``."""

    refs = ls_remote(
        f"https://github.com/{owner}/{repo}",
        f"refs/heads/{ref}",
        f"refs/tags/{ref}",
        f"refs/tags/{ref}^{{}}",
    )
    rev = commit_for_ref(refs, ref)
    url = f"git+https://github.com/{owner}/{repo}?rev={rev}&shallow=1"
    result = subprocess.run(
        [nix, "flake", "metadata", "--json", url], capture_output=True, text=True
    )
    if result.returncode != 0:
        raise NixGitInputsError(
            f"nix flake metadata {url} failed (exit {result.returncode}):\n{result.stderr}"
        )
    try:
        locked = json.loads(result.stdout)["locked"]
        if locked["rev"] != rev:
            raise NixGitInputsError(f"nix fetched {locked['rev']}, not {rev}")
        return GithubRevision(
            owner=owner,
            repo=repo,
            ref=ref,
            rev=locked["rev"],
            nar_hash=locked["narHash"],
            last_modified=int(locked["lastModified"]),
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise NixGitInputsError(f"unexpected nix flake metadata output: {exc}") from exc


def update_input(nix: str, input_name: str, ref: str, repo_root: Path = REPO_ROOT) -> GithubRevision:
    """Point root input ``input_name`` at branch or tag ``ref`` in ``flake.lock``."""

    lock_path = repo_root / "flake.lock"
    lock = json.loads(lock_path.read_text())
    current = {i.path: i for i in parse_lock(lock)}.get((input_name,))
    if current is None:
        raise NixGitInputsError(f"flake.lock: no root github input {input_name!r}")
    revision = fetch_github_revision(nix, current.owner, current.repo, ref)
    lock_path.write_text(format_lock(updated_lock(lock, input_name, revision)))
    return revision


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
    parser.add_argument(
        "--update",
        metavar="INPUT",
        help="point root github input INPUT at branch or tag --ref in flake.lock",
    )
    parser.add_argument("--ref", help="branch or tag for --update (e.g. nixos-26.05)")
    parser.add_argument("nix_args", nargs=argparse.REMAINDER, help="arguments for nix")
    options = parser.parse_args(argv)
    if (options.update is None) != (options.ref is None):
        parser.error("--update and --ref must be given together")
    nix_args = options.nix_args[1:] if options.nix_args[:1] == ["--"] else options.nix_args

    nix = shutil.which("nix")
    if nix is None:
        print("nix is not available in PATH", file=sys.stderr)
        return 1
    if options.update is not None:
        try:
            revision = update_input(nix, options.update, options.ref)
        except NixGitInputsError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"{options.update}: {revision.ref} -> {revision.rev} ({revision.nar_hash})")
        return 0
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
