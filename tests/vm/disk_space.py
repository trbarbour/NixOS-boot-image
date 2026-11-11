"""Disk-space handling for VM runs (task queue item 38).

Runs were lost to the session's disk allowance on 2026-10-18, 10-19, 11-07,
11-08 and 11-10: each run builds a ~1.5 GB image into the Nix store (kept,
unrooted, until a GC), and RAID resyncs turn sparse VM disk images into fully
allocated ones.

``statvfs``'s available blocks (``shutil.disk_usage(...).free``, ``df``'s
Avail) are the real limit, root included: on the cloud session's ext4
(``resv_strict``), a ``fallocate`` just over Avail fails with ENOSPC and one
2 GiB under it succeeds (2026-11-11).  So:

* :func:`delete_stale_images`: after a build, delete this repository's other
  image store paths that nothing references (``nix-store --delete`` refuses
  live ones);
* :func:`require_free_space`: refuse to start a VM below a minimum, saying what
  to free;
* :class:`FreeSpaceGuard`: while a VM runs, call back once when free space
  drops below a floor, so the harness can stop QEMU and fail with the reason
  instead of an ENOSPC halfway through an install.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import AbstractSet, Callable, Iterable, List, Optional, Sequence, Union

GIB = 1024**3
DEFAULT_MIN_FREE_GIB = 4.0
DEFAULT_FLOOR_GIB = 1.0
MIN_FREE_ENV = "PRE_NIXOS_VM_MIN_FREE_GIB"
FLOOR_ENV = "PRE_NIXOS_VM_FLOOR_GIB"
KEEP_IMAGES_ENV = "PRE_NIXOS_VM_KEEP_IMAGES"
STORE = Path("/nix/store")

# The flake's image outputs (flake.nix imageBaseName): the ISO directory and
# the SD image, e.g. <hash>-pre-nixos-0.29.0-g1234567-…-x86_64-linux.iso.
# Not the Python package (<hash>-pre-nixos-0.29.0) nor derivations.
_IMAGE_NAME = re.compile(r"^[0-9a-z]{32}-pre-nixos-.+-linux\.(iso|img|img\.zst)$")

FreeBytes = Callable[[Path], int]
Keep = Union[Path, AbstractSet[Path]]
Paths = Union[Path, Sequence[Path]]


def _as_set(keep: Keep) -> AbstractSet[Path]:
    return {keep} if isinstance(keep, Path) else keep


def _as_list(paths: Paths) -> List[Path]:
    return [paths] if isinstance(paths, Path) else list(paths)
Runner = Callable[[List[str]], "subprocess.CompletedProcess[str]"]


class InsufficientSpace(RuntimeError):
    """Too little free space to start the step safely."""


def free_bytes(path: Path) -> int:
    """Bytes available to this process on ``path``'s filesystem (``df`` Avail)."""

    return shutil.disk_usage(path).free


def _gib_from_env(name: str, default: float) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return int(default * GIB)
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name}={raw!r} is not a number of GiB") from exc
    if value < 0:
        raise ValueError(f"{name}={raw!r} is negative")
    return int(value * GIB)


def min_free_bytes() -> int:
    """Free space required before a VM starts (``PRE_NIXOS_VM_MIN_FREE_GIB``)."""

    return _gib_from_env(MIN_FREE_ENV, DEFAULT_MIN_FREE_GIB)


def floor_bytes() -> int:
    """Free space below which a running VM is stopped (``PRE_NIXOS_VM_FLOOR_GIB``)."""

    return _gib_from_env(FLOOR_ENV, DEFAULT_FLOOR_GIB)


def stale_image_paths(names: Iterable[str], *, keep: Keep, store: Path = STORE) -> List[Path]:
    """This repository's image store paths not in ``keep``, in ``names``' order.

    ``keep`` is every image the test session still holds: the session-scoped
    builds are not GC roots (Codex on #349).
    """

    kept = _as_set(keep)
    return [
        store / name
        for name in names
        if _IMAGE_NAME.match(name) and store / name not in kept
    ]


def _run(cmd: List[str]) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(cmd, check=False, capture_output=True, text=True)


def delete_stale_images(
    nix_store: str,
    *,
    keep: Keep,
    names: Optional[Sequence[str]] = None,
    store: Path = STORE,
    run: Runner = _run,
) -> List[Path]:
    """Delete the other image store paths that nothing references; return them.

    A path that is still referenced (a GC root, a ``result`` link) is refused
    by ``nix-store --delete`` and kept.
    """

    listing = list(names) if names is not None else [entry.name for entry in store.iterdir()]
    deleted: List[Path] = []
    for path in stale_image_paths(listing, keep=keep, store=store):
        if run([nix_store, "--delete", str(path)]).returncode == 0:
            deleted.append(path)
    return deleted


def least_free(paths: Paths, free: FreeBytes = free_bytes) -> "tuple[Path, int]":
    """The path among ``paths`` whose filesystem has the least space, and that space."""

    readings = [(path, free(path)) for path in _as_list(paths)]
    assert readings, "no paths to check"
    return min(readings, key=lambda reading: reading[1])


def require_free_space(
    paths: Paths, *, minimum_bytes: int, purpose: str, free: FreeBytes = free_bytes
) -> None:
    """Raise :class:`InsufficientSpace` unless every filesystem of ``paths`` has
    ``minimum_bytes`` free: the log directory and each VM disk's (Codex on #349)."""

    path, available = least_free(paths, free)
    if available < minimum_bytes:
        raise InsufficientSpace(
            f"only {available / GIB:.1f} GiB free on {path}'s filesystem, below the"
            f" {minimum_bytes / GIB:.1f} GiB needed before {purpose}. Free space first:"
            " old VM disk images (stale pytest-of-* directories), unreferenced store paths"
            f" (nix-store --gc); or lower {MIN_FREE_ENV}."
        )


@dataclass
class FreeSpaceGuard:
    """Polls free space and calls ``on_low`` once when the fullest of ``path``'s
    filesystems drops below the floor."""

    path: Paths
    floor_bytes: int
    on_low: Callable[[int], None]
    poll_seconds: float = 10.0
    free: FreeBytes = free_bytes
    tripped: bool = field(default=False, init=False)
    _stop: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _thread: Optional[threading.Thread] = field(default=None, init=False, repr=False)

    def start(self) -> None:
        assert self._thread is None, "guard already started"
        self._thread = threading.Thread(target=self._watch, name="free-space-guard", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(5.0, 2 * self.poll_seconds))

    def _watch(self) -> None:
        while not self._stop.is_set():
            try:
                _, available = least_free(self.path, self.free)
            except OSError:
                available = None
            if available is not None and available < self.floor_bytes:
                self.tripped = True
                self.on_low(available)
                return
            self._stop.wait(self.poll_seconds)


__all__ = [
    "DEFAULT_FLOOR_GIB",
    "DEFAULT_MIN_FREE_GIB",
    "FreeSpaceGuard",
    "InsufficientSpace",
    "delete_stale_images",
    "floor_bytes",
    "free_bytes",
    "least_free",
    "min_free_bytes",
    "require_free_space",
    "stale_image_paths",
]
