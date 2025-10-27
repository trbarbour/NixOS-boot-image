import json
from pathlib import Path

import pytest

from tests.test_boot_image_vm import (
    BootImageBuild,
    record_boot_image_diagnostic,
    write_boot_image_metadata,
)


@pytest.fixture()
def sample_boot_image_build(tmp_path: Path) -> BootImageBuild:
    iso_path = tmp_path / "sample.iso"
    store_path = tmp_path / "store"
    iso_path.touch()
    store_path.mkdir()
    return BootImageBuild(
        iso_path=iso_path,
        store_path=store_path,
        deriver="sample.drv",
        nar_hash="sha256-sample",
        root_key_fingerprint="SHA256:sample",
    )


def test_metadata_includes_diagnostics_directory(tmp_path: Path, sample_boot_image_build: BootImageBuild) -> None:
    metadata_path = tmp_path / "metadata.json"
    harness_log = tmp_path / "harness.log"
    serial_log = tmp_path / "serial.log"
    disk_image = tmp_path / "disk.img"

    write_boot_image_metadata(
        metadata_path,
        artifact=sample_boot_image_build,
        harness_log=harness_log,
        serial_log=serial_log,
        qemu_command=["qemu", "--version"],
        qemu_version="QEMU emulator version 8.0.0",
        disk_image=disk_image,
        ssh_host="127.0.0.1",
        ssh_port=2222,
        ssh_executable="/usr/bin/ssh",
    )

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    diagnostics = metadata["diagnostics"]
    assert diagnostics["directory"] == str(tmp_path / "diagnostics")
    assert diagnostics["artifacts"] == []
    assert metadata["qemu"]["version"] == "QEMU emulator version 8.0.0"


def test_metadata_records_qemu_version_when_available(
    tmp_path: Path, sample_boot_image_build: BootImageBuild
) -> None:
    metadata_path = tmp_path / "metadata.json"
    harness_log = tmp_path / "harness.log"
    serial_log = tmp_path / "serial.log"
    disk_image = tmp_path / "disk.img"

    qemu_version = "QEMU emulator version 9.0.1"
    write_boot_image_metadata(
        metadata_path,
        artifact=sample_boot_image_build,
        harness_log=harness_log,
        serial_log=serial_log,
        qemu_command=["qemu", "--version"],
        qemu_version=qemu_version,
        disk_image=disk_image,
        ssh_host="127.0.0.1",
        ssh_port=2222,
        ssh_executable="/usr/bin/ssh",
    )

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["qemu"]["version"] == qemu_version


def test_record_boot_image_diagnostic_appends_entries(
    tmp_path: Path, sample_boot_image_build: BootImageBuild
) -> None:
    metadata_path = tmp_path / "metadata.json"
    harness_log = tmp_path / "harness.log"
    serial_log = tmp_path / "serial.log"
    disk_image = tmp_path / "disk.img"

    write_boot_image_metadata(
        metadata_path,
        artifact=sample_boot_image_build,
        harness_log=harness_log,
        serial_log=serial_log,
        qemu_command=["qemu", "--version"],
        disk_image=disk_image,
        ssh_host="127.0.0.1",
        ssh_port=2222,
        ssh_executable="/usr/bin/ssh",
    )

    diagnostics_dir = tmp_path / "diagnostics"
    diagnostics_dir.mkdir(exist_ok=True)
    artifact_path = diagnostics_dir / "example.log"
    artifact_path.write_text("example", encoding="utf-8")

    record_boot_image_diagnostic(
        metadata_path,
        label="Example log",
        path=artifact_path,
    )

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["diagnostics"]["artifacts"] == [
        {"label": "Example log", "path": str(artifact_path)}
    ]

    # Registering the same artifact twice should not create duplicates.
    record_boot_image_diagnostic(
        metadata_path,
        label="Example log",
        path=artifact_path,
    )

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["diagnostics"]["artifacts"] == [
        {"label": "Example log", "path": str(artifact_path)}
    ]
