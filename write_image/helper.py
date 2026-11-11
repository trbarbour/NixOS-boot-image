"""The privileged step: write an image to a device (R-W5).

Run as root by the CLI through ``sudo``.  It trusts nothing the unprivileged
side decided: it re-checks the device's eligibility, refuses an image larger
than the device, opens the device exclusively (Linux refuses ``O_EXCL`` on a
block device in use), writes and optionally verifies.

Exit codes: 0 written; 2 refused; 3 verification failed; 1 other errors.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Callable, List, Optional, Sequence, TextIO

from write_image import devices, image, writer
from write_image.devices import Refusal, SystemView

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_REFUSED = 2
EXIT_VERIFY_FAILED = 3

OpenDevice = Callable[[str], int]


def _open_device(path: str) -> int:
    return os.open(path, os.O_RDWR | os.O_EXCL | os.O_CLOEXEC)


def _progress(err: TextIO, total: int) -> Callable[[int], None]:
    last = [-1]

    def report(done: int) -> None:
        percent = int(done * 100 / total) if total else 100
        if percent != last[0]:
            last[0] = percent
            err.write(f"\rwritten {done / 1000**2:.0f} of {total / 1000**2:.0f} MB ({percent}%)")
            err.flush()

    return report


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    view: Callable[[], SystemView] = devices.live_view,
    open_device: OpenDevice = _open_device,
    err: TextIO = sys.stderr,
) -> int:
    parser = argparse.ArgumentParser(prog="write-image-helper", description=__doc__.splitlines()[0])
    parser.add_argument("--device", required=True, help="whole-disk kernel name, e.g. sdb")
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    verdict = devices.check(view(), args.device)
    if isinstance(verdict, Refusal):
        err.write(f"refusing /dev/{verdict.name}: {verdict.reason}\n")
        return EXIT_REFUSED
    img = image.image_at(args.image)
    try:
        size, sha256 = image.digest(img)
    except (OSError, image.ImageError) as exc:
        err.write(f"cannot read {img.path}: {exc}\n")
        return EXIT_ERROR
    if size > verdict.size_bytes:
        err.write(
            f"refusing {verdict.path}: the image ({size} bytes) is larger than the device"
            f" ({verdict.size_bytes} bytes)\n"
        )
        return EXIT_REFUSED

    try:
        fd = open_device(verdict.path)
    except OSError as exc:
        err.write(f"cannot open {verdict.path} exclusively (in use?): {exc}\n")
        return EXIT_REFUSED
    try:
        err.write(f"writing {img.path.name} to {verdict.describe()}\n")
        with image.open_stream(img) as stream:
            written = writer.copy_stream(stream, fd, _progress(err, size))
        err.write("\n")
        if written != size:
            err.write(f"wrote {written} bytes, expected {size}\n")
            return EXIT_ERROR
        if args.verify:
            err.write("verifying ...\n")
            if writer.read_back_sha256(fd, size) != sha256:
                err.write(f"VERIFICATION FAILED: {verdict.path} does not hold the image\n")
                return EXIT_VERIFY_FAILED
            err.write(f"verified: sha256 {sha256}\n")
    except (OSError, image.ImageError) as exc:
        err.write(f"\nwriting {verdict.path} failed: {exc}\n")
        return EXIT_ERROR
    finally:
        os.close(fd)
    err.write(f"done: {verdict.path} holds {img.path.name}\n")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
