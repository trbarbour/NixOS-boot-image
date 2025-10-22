#!/usr/bin/env nix-shell
#!nix-shell -i python3 -p python3
"""Update the repository to the latest stable NixOS channel.

The script performs three steps:

1. Query the GitHub API for nixpkgs branches and find the newest stable
   "nixos-YY.MM" channel.
2. Update ``flake.nix`` so that ``inputs.nixpkgs.url`` references that channel.
3. Refresh ``flake.lock`` for the ``nixpkgs`` input.

Requires network access and ``nix`` to be available in ``PATH``. Set
``GITHUB_TOKEN`` (or ``GH_TOKEN``) to increase the GitHub API rate limit when
running the script repeatedly.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Iterable

RE_CHANNEL = re.compile(r"^nixos-(\d{2})\.(\d{2})$")
RE_FLAKE_INPUT = re.compile(
    r'(nixpkgs\.url\s*=\s*"github:NixOS/nixpkgs/)(nixos-\d{2}\.\d{2})(";)'
)
GITHUB_BRANCHES_URL = "https://api.github.com/repos/NixOS/nixpkgs/branches"
USER_AGENT = "nixos-boot-image-update-script"


def github_request(url: str) -> urllib.request.Request:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.Request(url, headers=headers)


def fetch_all_branches() -> list[str]:
    branches: list[str] = []
    page = 1
    while True:
        url = f"{GITHUB_BRANCHES_URL}?per_page=100&page={page}"
        request = github_request(url)
        try:
            with urllib.request.urlopen(request) as response:
                payload = response.read()
        except urllib.error.HTTPError as exc:  # pragma: no cover - network failure
            message = getattr(exc, "reason", exc)
            raise SystemExit(f"GitHub API request failed: {message}")
        except urllib.error.URLError as exc:  # pragma: no cover - network failure
            raise SystemExit(f"Could not reach GitHub: {exc.reason}")

        data = json.loads(payload)
        if not data:
            break
        branches.extend(item["name"] for item in data)
        page += 1
    return branches


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


def update_flake_nix(path: Path, channel: str) -> None:
    original = path.read_text(encoding="utf-8")
    updated, replacements = RE_FLAKE_INPUT.subn(r"\\1" + channel + r"\\3", original, count=1)
    if replacements == 0:
        raise SystemExit(
            "Did not find an existing nixpkgs.url entry in flake.nix to update."
        )
    path.write_text(updated, encoding="utf-8")


def run(*args: str, cwd: Path) -> None:
    try:
        subprocess.run(args, cwd=cwd, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise SystemExit(f"Command {' '.join(args)} failed: {exc}")


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    print("Fetching nixpkgs branches from GitHub…", file=sys.stderr)
    branches = fetch_all_branches()
    channel = newest_stable_channel(branches)
    print(f"Latest stable channel: {channel}", file=sys.stderr)

    flake_path = repo_root / "flake.nix"
    print(f"Updating {flake_path}…", file=sys.stderr)
    update_flake_nix(flake_path, channel)

    print("Updating flake.lock…", file=sys.stderr)
    run("nix", "flake", "lock", "--update-input", "nixpkgs", cwd=repo_root)
    print("Update complete.", file=sys.stderr)


if __name__ == "__main__":
    main()
