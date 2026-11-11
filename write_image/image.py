"""Locate an image and read it as a byte stream (R-W1, R-W4).

The ISO is written as is; the SD image (``.img.zst``) is decompressed on the
fly by ``zstd -dc``, so nothing large is written to the build host's disk.
"""

from __future__ import annotations

import contextlib
import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterator, Tuple

from write_image import _tools
from write_image.devices import Format

# An absolute store path in the flake's package, so it survives sudo.
ZSTD = _tools.ZSTD
CHUNK = 4 * 1024 * 1024
_PATTERNS = {"iso": ("iso/*.iso",), "sd": ("sd-image/*.img.zst", "sd-image/*.img")}


class ImageError(RuntimeError):
    """The image cannot be read."""


class ImageNotFound(ImageError):
    """A build output holds no image of the expected format."""


@dataclass(frozen=True)
class Image:
    path: Path
    compressed: bool


def image_at(path: Path) -> Image:
    return Image(path, compressed=path.name.endswith(".zst"))


def find_image(output: Path, fmt: Format) -> Image:
    """The single image of ``fmt`` in a ``nix build`` output."""

    found = sorted(p for pattern in _PATTERNS[fmt] for p in output.glob(pattern))
    if len(found) != 1:
        raise ImageNotFound(f"expected one {fmt} image under {output}, found {len(found)}")
    return image_at(found[0])


@contextlib.contextmanager
def open_stream(img: Image) -> Iterator[BinaryIO]:
    """The image's (decompressed) bytes.  A decompressor failure raises
    :class:`ImageError` when the stream is closed."""

    if not img.compressed:
        with img.path.open("rb") as handle:
            yield handle
        return
    proc = subprocess.Popen(
        [ZSTD, "-dc", "--", str(img.path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    assert proc.stdout is not None and proc.stderr is not None
    stdout: BinaryIO = proc.stdout  # type: ignore[assignment]  # a binary pipe
    try:
        yield stdout
    finally:
        proc.stdout.close()
        error = proc.stderr.read().decode(errors="replace").strip()
        proc.stderr.close()
        status = proc.wait()
    if status != 0:
        raise ImageError(f"zstd failed on {img.path} (exit {status}): {error}")


def digest(img: Image) -> Tuple[int, str]:
    """The (decompressed) size and SHA-256 of the image."""

    sha = hashlib.sha256()
    size = 0
    with open_stream(img) as stream:
        while True:
            block = stream.read(CHUNK)
            if not block:
                break
            sha.update(block)
            size += len(block)
    return size, sha.hexdigest()


__all__ = ["CHUNK", "Image", "ImageError", "ImageNotFound", "digest", "find_image", "image_at", "open_stream"]
