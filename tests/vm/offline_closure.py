"""Check that a derivation can be built offline from a system closure.

The boot image builds disko's generated script at run time, without network
access.  Every output that build needs must therefore already be in the
image's closure.  nixpkgs 26.05 dropped ``pkgs.stdenv`` (with a C compiler)
from the installer's ``system.extraDependencies``; the guest then tried to
bootstrap gcc from source and disko failed (2026-10-18, see
docs/work-notes/2026-10-18T222729Z-nixpkgs-26.05-pin.md).

``inputs.srcs`` are not checked: Nix creates them at evaluation time from
sources the image already holds (its nixpkgs and disko).
"""

from __future__ import annotations

from typing import Any, Collection, Mapping

STORE_DIR = "/nix/store"


def _store_path(name: str) -> str:
    return name if name.startswith("/") else f"{STORE_DIR}/{name}"


def required_input_outputs(show: Mapping[str, Any], drv: str) -> frozenset[str]:
    """Output paths of ``drv``'s direct inputs, from ``nix derivation show --recursive``.

    ``show`` is the parsed JSON (``{"derivations": {basename: {...}}}``, the
    Nix 2.34 shape).  Only the outputs ``drv`` actually uses are returned.
    """

    derivations: Mapping[str, Any] = show["derivations"]
    key = drv.removeprefix(f"{STORE_DIR}/")
    needed: set[str] = set()
    for input_drv, spec in derivations[key]["inputs"]["drvs"].items():
        input_outputs = derivations[input_drv.removeprefix(f"{STORE_DIR}/")]["outputs"]
        for name in spec["outputs"]:
            needed.add(_store_path(input_outputs[name]["path"]))
    return frozenset(needed)


def missing_from_closure(required: Collection[str], closure: Collection[str]) -> list[str]:
    present = set(closure)
    return sorted(path for path in required if path not in present)


__all__ = ["missing_from_closure", "required_input_outputs"]
