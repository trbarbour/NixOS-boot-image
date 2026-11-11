"""Copy an image to a device and read it back (R-W1, R-W4)."""

from __future__ import annotations

import fcntl
import hashlib
import os
import stat
from typing import BinaryIO, Callable, Optional

from write_image.image import CHUNK

# linux/fs.h: _IO(0x12, 97), flush the block device's buffer cache.
BLKFLSBUF = 0x1261

Progress = Optional[Callable[[int], None]]


def copy_stream(src: BinaryIO, fd: int, progress: Progress) -> int:
    """Write ``src`` to ``fd`` from its start in 4 MiB blocks, then fsync;
    return the number of bytes written."""

    os.lseek(fd, 0, os.SEEK_SET)
    written = 0
    while True:
        block = src.read(CHUNK)
        if not block:
            break
        view = memoryview(block)
        while view:
            count = os.write(fd, view)
            view = view[count:]
            written += count
        if progress is not None:
            progress(written)
    os.fsync(fd)
    return written


def drop_caches(fd: int) -> None:
    """Make the next read come from the medium, not from memory."""

    os.fsync(fd)
    if stat.S_ISBLK(os.fstat(fd).st_mode):
        fcntl.ioctl(fd, BLKFLSBUF, 0)
    os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)


def read_back_sha256(fd: int, length: int) -> str:
    """SHA-256 of the first ``length`` bytes of ``fd``, read after dropping caches."""

    drop_caches(fd)
    os.lseek(fd, 0, os.SEEK_SET)
    sha = hashlib.sha256()
    remaining = length
    while remaining > 0:
        block = os.read(fd, min(CHUNK, remaining))
        if not block:
            raise OSError(f"device ended {remaining} bytes before the image did")
        sha.update(block)
        remaining -= len(block)
    return sha.hexdigest()


__all__ = ["BLKFLSBUF", "copy_stream", "drop_caches", "read_back_sha256"]
