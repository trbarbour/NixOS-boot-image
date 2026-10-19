#!/usr/bin/env nix-shell
#!nix-shell -i python3 -p python3
"""Update the repository to the latest stable NixOS channel or release tag.

The script performs three steps:

1. List the nixpkgs branches/tags with ``git ls-remote`` and find either:
   - the newest stable ``nixos-YY.MM`` channel branch (default), or
   - the newest stable ``YY.MM`` release tag (``--latest-release`` mode).
2. Update ``flake.nix`` so that ``inputs.nixpkgs.url`` references that target.
3. Refresh ``flake.lock`` for the ``nixpkgs`` input.

Requires network access, ``git`` and ``nix`` in ``PATH``.  Both steps that
touch the network use git (``git ls-remote``, and a git fetch for the lock via
``scripts/nix_git_inputs.py``), not the GitHub REST API or archive tarballs,
so the script also works behind proxies that refuse those (e.g. Claude Code
cloud sessions, where the API answered 403 on 2026-10-18).
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import nix_git_inputs  # noqa: E402

RE_CHANNEL = re.compile(r"^nixos-(\d{2})\.(\d{2})$")
RE_RELEASE_TAG = re.compile(r"^(\d{2})\.(\d{2})$")
RE_FLAKE_INPUT = re.compile(
    r'(nixpkgs\.url\s*=\s*"github:NixOS/nixpkgs/)(?:nixos-\d{2}\.\d{2}|\d{2}\.\d{2})(";)'
)
NIXPKGS_URL = "https://github.com/NixOS/nixpkgs"


def remote_ref_names(kind: str) -> list[str]:
    """Return nixpkgs branch (``kind="heads"``) or tag (``"tags"``) names."""

    assert kind in ("heads", "tags"), kind
    prefix = f"refs/{kind}/"
    try:
        # A pattern, not --heads/--tags: options after the URL match nothing.
        refs = nix_git_inputs.ls_remote(NIXPKGS_URL, f"refs/{kind}/*")
    except nix_git_inputs.NixGitInputsError as exc:
        raise SystemExit(str(exc))
    return sorted(
        {name[len(prefix) :].removesuffix("^{}") for name in refs if name.startswith(prefix)}
    )


def newest_stable_channel(branches: Iterable[str]) -> str:
    best_channel: tuple[int, int] | None = None
    best_name = None
    for name in branches:
        match = RE_CHANNEL.match(name)
        if not match:
            continue
        major, minor = map(int, match.groups())
        version_tuple = (major, minor)
        if best_channel is None or version_tuple > best_channel:
            best_channel = version_tuple
            best_name = name
    if best_name is None:
        raise SystemExit("Could not determine the latest stable nixos channel from GitHub branches.")
    return best_name


def newest_stable_release_tag(tags: Iterable[str]) -> str:
    best_release: tuple[int, int] | None = None
    best_name = None
    for name in tags:
        match = RE_RELEASE_TAG.match(name)
        if not match:
            continue
        major, minor = map(int, match.groups())
        version_tuple = (major, minor)
        if best_release is None or version_tuple > best_release:
            best_release = version_tuple
            best_name = name
    if best_name is None:
        raise SystemExit("Could not determine the latest stable nixos release tag from GitHub tags.")
    return best_name


def update_flake_nix(path: Path, channel: str) -> None:
    original = path.read_text(encoding="utf-8")
    def replacement(match: re.Match[str]) -> str:
        return f"{match.group(1)}{channel}{match.group(2)}"

    updated, replacements = RE_FLAKE_INPUT.subn(replacement, original, count=1)
    if replacements == 0:
        raise SystemExit(
            "Did not find an existing nixpkgs.url entry in flake.nix to update."
        )
    path.write_text(updated, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Update nixpkgs to the latest stable channel or release tag.")
    parser.add_argument(
        "--latest-release",
        action="store_true",
        help="Pin to the newest stable release tag (YY.MM) instead of the newest stable channel branch (nixos-YY.MM).",
    )
    args = parser.parse_args()

    repo_root = REPO_ROOT
    if args.latest_release:
        print("Listing nixpkgs tags…", file=sys.stderr)
        tags = remote_ref_names("tags")
        target = newest_stable_release_tag(tags)
        print(f"Latest stable release tag: {target}", file=sys.stderr)
    else:
        print("Listing nixpkgs branches…", file=sys.stderr)
        branches = remote_ref_names("heads")
        target = newest_stable_channel(branches)
        print(f"Latest stable channel: {target}", file=sys.stderr)

    flake_path = repo_root / "flake.nix"
    print(f"Updating {flake_path}…", file=sys.stderr)
    update_flake_nix(flake_path, target)

    print("Updating flake.lock…", file=sys.stderr)
    nix = shutil.which("nix")
    if nix is None:
        raise SystemExit("nix is not available in PATH")
    try:
        revision = nix_git_inputs.update_input(nix, "nixpkgs", target, repo_root)
    except nix_git_inputs.NixGitInputsError as exc:
        raise SystemExit(f"Updating flake.lock failed: {exc}")
    print(f"nixpkgs: {target} -> {revision.rev}", file=sys.stderr)
    print("Update complete.", file=sys.stderr)


if __name__ == "__main__":
    main()
