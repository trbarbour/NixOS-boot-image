"""Build a boot image from a test site (README "Site settings"; task queue
item 19).

The site reaches the build purely, as ``--override-input site path:<dir>``:
a pure evaluation cannot read the environment at all, and the legacy
``PRE_NIXOS_ROOT_KEY`` / ``PRE_NIXOS_AUTO_INSTALL`` fallback is gone (task
queue item 57).  Shared by the VM fixtures and the VM debug scripts.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import List, Optional


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


def build_args(attribute: str, site_dir: Path) -> List[str]:
    """``nix`` arguments that build ``attribute`` from the site in ``site_dir``."""

    return [
        "build", attribute, "--no-link", "--print-out-paths",
        "--override-input", "site", f"path:{site_dir}",
    ]
