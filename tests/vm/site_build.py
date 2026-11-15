"""Build a boot image from a test site (README "Site settings"; task queue
item 19).

The site reaches the build purely, as ``--override-input site path:<dir>``.
The legacy environment fallback (``PRE_NIXOS_ROOT_KEY`` /
``PRE_NIXOS_AUTO_INSTALL`` under ``--impure``, site-settings design D2c) is
cleared, so it cannot disagree with the site.  Shared by the VM fixtures and
the VM debug scripts.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional

LEGACY_ENVIRONMENT = ("PRE_NIXOS_ROOT_KEY", "PRE_NIXOS_AUTO_INSTALL")


def write_test_site(
    site_dir: Path, public_key: Path, *, root_hashed_password: Optional[str] = None
) -> Path:
    """Write a site with ``public_key`` as root's key; return its directory."""

    site_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(public_key, site_dir / "root_key.pub")
    lines = ["{", "  rootKey = ./root_key.pub;"]
    if root_hashed_password is not None:
        assert '"' not in root_hashed_password and "\\" not in root_hashed_password
        lines.append(f'  rootHashedPassword = "{root_hashed_password}";')
    lines.append("}")
    (site_dir / "pre-nixos-site.nix").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return site_dir


def build_environment() -> Dict[str, str]:
    """This process's environment without the legacy fallback."""

    env = os.environ.copy()
    for name in LEGACY_ENVIRONMENT:
        env.pop(name, None)
    return env


def build_args(attribute: str, site_dir: Path) -> List[str]:
    """``nix`` arguments that build ``attribute`` from the site in ``site_dir``."""

    return [
        "build", attribute, "--no-link", "--print-out-paths",
        "--override-input", "site", f"path:{site_dir}",
    ]
