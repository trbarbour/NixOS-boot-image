#!/usr/bin/env python3
"""Evaluate every flake check's derivation without building anything.

Every check's assertions run during evaluation, so this is the cheap form of
``nix flake check`` (task queue item 58).  ``nix flake check --no-build``
cannot do it for this flake: it evaluates against a read-only store, where a
path that evaluation adds to the store and then reads back (the site's key,
generated Nix files) is "not valid".

Extra arguments go to ``nix``.  CI passes ``--override-input site
path:./nix/site-default``: with any input overridden, Nix gives the flake no
git revision, as in the README's site build, and the checks must hold then
too.  ``PRE_NIXOS_NIX_GIT_INPUTS=1`` adds the git overrides of
``scripts/nix_git_inputs.py``::

    scripts/eval_checks.py
    scripts/eval_checks.py --override-input site path:./nix/site-default
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.nix_git_inputs import nix_command  # noqa: E402

DEFAULT_SYSTEM = "x86_64-linux"
APPLY = "checks: builtins.mapAttrs (_: check: check.drvPath) checks"


def eval_args(system: str, extra: Sequence[str]) -> List[str]:
    """``nix`` arguments that print every check's ``drvPath`` as JSON."""

    return ["eval", "--json", f".#checks.{system}", "--apply", APPLY, *extra]


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--system", default=DEFAULT_SYSTEM, help="checks of this system (default: %(default)s)")
    args, extra = parser.parse_known_args(argv)
    result = subprocess.run(
        nix_command("nix", eval_args(args.system, extra)),
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr, end="")
        print(f"check evaluation failed (nix exit {result.returncode})", file=sys.stderr)
        return 1
    try:
        drvs = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        print(f"nix printed no JSON: {exc}: {result.stdout[:200]!r}", file=sys.stderr)
        return 1
    if not isinstance(drvs, dict) or not drvs:
        print(f"expected a non-empty set of checks, got {result.stdout[:200]!r}", file=sys.stderr)
        return 1
    bad = sorted(
        name for name, drv in drvs.items()
        if not (isinstance(drv, str) and drv.startswith("/nix/store/") and drv.endswith(".drv"))
    )
    if bad:
        print(f"not a derivation path: {', '.join(bad)}", file=sys.stderr)
        return 1
    print(f"{len(drvs)} checks evaluated ({args.system})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
