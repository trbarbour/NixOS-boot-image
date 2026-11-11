"""Finding, writing and verifying an image (task queue item 42; R-W1, R-W4)."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from write_image import image, writer
from write_image.image import Image

# The SD image is zstd-compressed; the tool and these tests need zstd.
ZSTD = shutil.which("zstd") or "zstd"


def _payload(size: int) -> bytes:
    return bytes((i * 7 + 3) % 256 for i in range(size))


def test_find_image_in_build_outputs(tmp_path: Path) -> None:
    iso_out = tmp_path / "iso-out"
    (iso_out / "iso").mkdir(parents=True)
    (iso_out / "iso/pre-nixos-0.30.0-x86_64-linux.iso").write_bytes(b"x")
    found = image.find_image(iso_out, "iso")
    assert found == Image(iso_out / "iso/pre-nixos-0.30.0-x86_64-linux.iso", compressed=False)

    sd_out = tmp_path / "sd-out"
    (sd_out / "sd-image").mkdir(parents=True)
    (sd_out / "sd-image/pre-nixos-0.30.0-sd-card-aarch64-linux.img.zst").write_bytes(b"x")
    assert image.find_image(sd_out, "sd").compressed

    with pytest.raises(image.ImageNotFound):
        image.find_image(iso_out, "sd")


def test_image_from_a_given_path(tmp_path: Path) -> None:
    raw = tmp_path / "a.img"
    raw.write_bytes(b"x")
    assert image.image_at(raw) == Image(raw, compressed=False)
    assert image.image_at(tmp_path / "b.img.zst").compressed


def test_write_and_verify_a_raw_image(tmp_path: Path) -> None:
    data = _payload(9 * 1024 * 1024 + 123)  # spans several 4 MiB blocks
    src = tmp_path / "image.iso"
    src.write_bytes(data)
    device = tmp_path / "device"
    device.write_bytes(b"\xff" * (len(data) + 4096))
    progress: list[int] = []
    fd = os.open(device, os.O_RDWR)
    try:
        with image.open_stream(Image(src, compressed=False)) as stream:
            written = writer.copy_stream(stream, fd, progress.append)
        assert written == len(data)
        assert progress[-1] == len(data) and progress == sorted(progress)
        assert writer.read_back_sha256(fd, written) == hashlib.sha256(data).hexdigest()
    finally:
        os.close(fd)
    assert image.digest(Image(src, compressed=False)) == (len(data), hashlib.sha256(data).hexdigest())


def test_verification_detects_a_corrupted_byte(tmp_path: Path) -> None:
    data = _payload(1024 * 1024)
    device = tmp_path / "device"
    device.write_bytes(data)
    with device.open("r+b") as handle:
        handle.seek(500_000)
        handle.write(b"\x00" if data[500_000] else b"\x01")
    fd = os.open(device, os.O_RDONLY)
    try:
        assert writer.read_back_sha256(fd, len(data)) != hashlib.sha256(data).hexdigest()
    finally:
        os.close(fd)


def test_compressed_image_is_streamed_decompressed(tmp_path: Path) -> None:
    data = _payload(5 * 1024 * 1024)
    raw = tmp_path / "card.img"
    raw.write_bytes(data)
    subprocess.run([ZSTD, "-q", "-o", str(tmp_path / "card.img.zst"), str(raw)], check=True)
    img = image.image_at(tmp_path / "card.img.zst")
    assert image.digest(img) == (len(data), hashlib.sha256(data).hexdigest())
    device = tmp_path / "device"
    device.write_bytes(b"")
    fd = os.open(device, os.O_RDWR)
    try:
        with image.open_stream(img) as stream:
            assert writer.copy_stream(stream, fd, None) == len(data)
    finally:
        os.close(fd)
    assert device.read_bytes() == data


def test_a_failing_decompressor_is_an_error(tmp_path: Path) -> None:
    bogus = tmp_path / "bad.img.zst"
    bogus.write_bytes(b"not zstd at all")
    with pytest.raises(image.ImageError):
        image.digest(image.image_at(bogus))
