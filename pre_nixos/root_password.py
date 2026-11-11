"""The installed system's hashed root password (reqs R-A1, R-A2; task queue item 45).

Design: ``plans/2026-11-10T140423Z-root-password-design.md``.

A site may give ``rootHashedPassword``.  ``nix/site.nix`` validates it when
the image is built, and the flake embeds it in this package as
``root_hashed_password`` (D3).  At install time pre-nixos

* writes it as ``users.users.root.hashedPassword`` in the managed block, and
* sets root's password field in an existing ``/mnt/etc/shadow`` to it (D4):
  with mutable users NixOS applies ``hashedPassword`` only to a new shadow
  entry, so a reinstall over an earlier attempt would otherwise keep root
  locked.

Everything here except :func:`load_embedded` and :func:`apply_to_shadow_file`
is pure.
"""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

EMBEDDED_FILE = Path(__file__).with_name("root_hashed_password")

# nix/site.nix cryptSchemeIds, which the flake check ``crypt-schemes`` keeps
# equal to nixpkgs' libxcrypt.enabledCryptSchemeIds.  tests/test_root_password.py
# checks that this list matches site.nix.
CRYPT_SCHEME_IDS = ("y", "gy", "sm3y", "7", "2b", "2y", "2a", "6")

# NixOS's Modular Crypt Format pattern (nixos/modules/config/users-groups.nix),
# as nix/site.nix uses it.
_BASE64 = r"[a-zA-Z0-9./]+"
_NAME = r"[a-z0-9-]+"
_VALUE = r"[a-zA-Z0-9/+.-]+"
_OPTIONS = rf"{_NAME}(={_VALUE})?(,{_NAME}={_VALUE})*"
_SCHEME = rf"({'|'.join(re.escape(i) for i in CRYPT_SCHEME_IDS)})(\${_OPTIONS})?"
_CONTENT = rf"{_BASE64}\${_BASE64}(\${_BASE64})?"
MCF_PATTERN = re.compile(rf"\${_SCHEME}\${_CONTENT}")


class InvalidRootHash(ValueError):
    """The embedded hash breaks the invariant site.nix established (R-A2)."""


@dataclass(frozen=True)
class RootHash:
    """A crypt hash NixOS accepts; the constructor enforces it."""

    value: str

    def __post_init__(self) -> None:
        if not is_crypt_hash(self.value):
            # The value is not echoed: it could be a plain password.
            raise InvalidRootHash("the embedded root password is not a crypt hash")


def is_crypt_hash(value: str) -> bool:
    """Whether ``value`` is, in full, a crypt hash of an accepted scheme."""

    return MCF_PATTERN.fullmatch(value) is not None


def parse_embedded(text: str) -> RootHash:
    """The hash from the embedded file's text.

    The flake writes the site's string as is (``pkgs.writeText``), so there is
    no trailing newline; one is tolerated, anything else is an error.
    """

    stripped = text[:-1] if text.endswith("\n") else text
    return RootHash(stripped)


def load_embedded(path: Path = EMBEDDED_FILE) -> Optional[RootHash]:
    """The image's hash, or ``None`` when the site set none (no file)."""

    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    return parse_embedded(text)


def nix_lines(root_hash: Optional[RootHash]) -> list[str]:
    """The managed block's lines for the hash (none when unset)."""

    if root_hash is None:
        return []
    # MCF has no quote, backslash or "${", so the hash is a safe Nix string.
    assert '"' not in root_hash.value and "\\" not in root_hash.value and "${" not in root_hash.value
    return [f'  users.users.root.hashedPassword = "{root_hash.value}";', ""]


@dataclass(frozen=True)
class ShadowEdit:
    """The result of :func:`with_root_hash`."""

    text: str
    changed: bool


def with_root_hash(shadow_text: str, root_hash: RootHash) -> ShadowEdit:
    """``shadow_text`` with root's password field set to ``root_hash``.

    Only the line whose first field is ``root`` changes, and only its second
    field.  Other lines, including malformed ones, are kept byte for byte.
    With no root line nothing changes (NixOS adds root with the hash).
    """

    lines = shadow_text.splitlines(keepends=True)
    out: list[str] = []
    changed = False
    for line in lines:
        body = line.rstrip("\n")
        ending = line[len(body):]
        fields = body.split(":")
        if fields[0] == "root" and len(fields) >= 2:
            if fields[1] != root_hash.value:
                fields[1] = root_hash.value
                changed = True
            out.append(":".join(fields) + ending)
        else:
            out.append(line)
    result = "".join(out)
    assert changed == (result != shadow_text)
    return ShadowEdit(result, changed)


def apply_to_shadow_file(shadow_path: Path, root_hash: RootHash) -> bool:
    """Set root's password in an existing shadow file; True if it changed.

    A missing file is left missing (NixOS creates it with the hash).  The file
    is replaced atomically, with its mode and owner kept.
    """

    try:
        text = shadow_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return False
    edit = with_root_hash(text, root_hash)
    if not edit.changed:
        return False
    stat = shadow_path.stat()
    fd, temp_name = tempfile.mkstemp(dir=shadow_path.parent, prefix=".shadow.")
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(edit.text)
        os.chmod(temp, stat.st_mode & 0o7777)
        try:
            os.chown(temp, stat.st_uid, stat.st_gid)
        except PermissionError:
            # Only root may give a file away; tests run as other users, and
            # then the owner is already the caller.
            if (stat.st_uid, stat.st_gid) != (os.getuid(), os.getgid()):
                raise
        os.replace(temp, shadow_path)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    return True
